"""Run the isolated V2 experience with simulated AI and employer responses."""
from pathlib import Path
import sys
import time
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fixtures.recruiter_fixture import MARA, environment

if __name__ == '__main__':
    with environment() as (app, calls), ExitStack() as fixtures:
        if '--progress-test' in sys.argv:
            import recruiter

            preferences = dict(salary=70000, currency='USD', period='year', flexible=False,
                               commute='', remote_region='Oregon, United States', modes=['remote'])
            recruiter.start(app, dict(action='analyze', version=0, resume=MARA))
            deadline = time.monotonic() + 5
            while recruiter.LOCK.locked() and time.monotonic() < deadline:
                time.sleep(0.01)
            state = recruiter.read(app, private=True)
            if state['stage'] != 'ready':
                raise RuntimeError('Fictional profile failed to initialize.')
            state['preferences'] = preferences
            recruiter.write(app, state)

            board_jobs = app.board_jobs
            match = recruiter.match

            def slow_board(*args):
                time.sleep(5)
                return board_jobs(*args)

            def slow_match(*args):
                time.sleep(1.5)
                return match(*args)

            fixtures.enter_context(patch.object(app, 'board_jobs', side_effect=slow_board))
            fixtures.enter_context(patch.object(recruiter, 'match', side_effect=slow_match))
        with ThreadingHTTPServer(('127.0.0.1', 18087), app.Handler) as server:
            print('Jobs V2 QA at http://127.0.0.1:18087 using fictional feeds and simulated AI.', flush=True)
            server.serve_forever()
