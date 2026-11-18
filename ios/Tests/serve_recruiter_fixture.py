"""Run the isolated V2 experience with simulated AI and employer responses."""
from pathlib import Path
import sys
import time
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fixtures.recruiter_fixture import MARA, environment, fake_ai

if __name__ == '__main__':
    pay_test = '--market-pay-test' in sys.argv
    with environment() as (app, calls), ExitStack() as fixtures:
        if '--progress-test' in sys.argv or pay_test:
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
                jobs = board_jobs(*args)
                if pay_test:
                    for job in jobs:
                        if job['requisition'] == 'lab':
                            job.update(title='Fictional Revenue Cycle Director',
                                       description='Review denial queues. Manage managers and lead multiple teams.')
                        if job['requisition'] in ('unknown', 'lab'):
                            for key in ('salary_min', 'salary_max', 'salary_currency', 'salary_period', 'salary_type'):
                                job.pop(key, None)
                            job['salary_text'] = 'Salary Not Published'
                return jobs

            def slow_match(*args):
                time.sleep(1.5)
                return match(*args)

            fixtures.enter_context(patch.object(app, 'board_jobs', side_effect=slow_board))
            fixtures.enter_context(patch.object(recruiter, 'match', side_effect=slow_match))
            if pay_test:
                def fictional_pay(a, name, inputs, schema):
                    if name != 'market_pay':
                        return fake_ai(a, name, inputs, schema)
                    summary = 'Geography: Oregon\nData period: May 2025\nRange: USD 75,000–95,000 per year.'
                    return dict(summary=summary, geography='Oregon', data_period='May 2025',
                                salary_min=75000, salary_max=95000, salary_period='year', citations=[
                        dict(url='https://example.com/fictional-wages', title='Fictional wage data', end=len(summary))])
                fixtures.enter_context(patch.object(recruiter, 'ai', side_effect=fictional_pay))
        with ThreadingHTTPServer(('127.0.0.1', 18087), app.Handler) as server:
            print('Jobs V2 QA at http://127.0.0.1:18087 using fictional feeds and simulated AI.', flush=True)
            server.serve_forever()
