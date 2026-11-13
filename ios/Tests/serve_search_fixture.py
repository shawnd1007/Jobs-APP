"""Local test service for the iPhone search workflow, with a disposable database."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from http.server import ThreadingHTTPServer
from unittest.mock import MagicMock, patch

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE))


def serve():
    with tempfile.TemporaryDirectory(prefix='jobs-search-qa-') as folder:
        root = Path(folder)
        os.environ['JOBS_DATA'] = str(root / 'data')
        import app

        cfg = json.loads((SOURCE / 'config.example.json').read_text(encoding='utf-8'))
        cfg.update(
            categories=['billing analyst'], preferred_skills=['Excel', 'SQL'],
            profile='Reconciled fictional accounts using Excel and SQL.',
            additional_boards={'ashby': ['fictional-slow'], 'recruitee': ['fictional']}, target_locations=['United States'],
            workplace_types=['remote'], request_delay_seconds=0, generic_urls_per_run=0,
        )
        (root / 'config.json').write_text(json.dumps(cfg), encoding='utf-8')
        feed = (SOURCE / 'fixtures' / 'recruitee.xml').read_bytes()
        slow_checks = 0

        def slow_board(request, timeout):
            nonlocal slow_checks
            assert request.full_url == 'https://api.ashbyhq.com/posting-api/job-board/fictional-slow?includeCompensation=true'
            slow_checks += 1
            if slow_checks == 1:
                time.sleep(8)
            return fixture_response(request, timeout, b'{"jobs":[]}')

        def fixture_response(request, timeout, payload=None):
            url = request.full_url
            payloads = {
                'https://fictional.recruitee.com/api/feeds/offers.xml': feed,
                'https://fictional.recruitee.com/o/payment-operations-specialist': b'<h1>Payment Operations Specialist</h1>',
            }
            response = MagicMock()
            response.__enter__.return_value = response
            response.url = url
            response.read.return_value = payload if payload is not None else payloads[url]
            return response
        with patch.object(app, 'ROOT', root), patch.object(app, 'SEED', SOURCE / 'seed.empty.html'), \
             patch.object(app, 'safe_url', side_effect=lambda url: url), \
             patch.object(app, 'BOARD_SECONDS', 4), \
             patch.object(app.OPENER, 'open', side_effect=slow_board), \
             patch.object(app.PERSONIO_OPENER, 'open', side_effect=fixture_response), \
             patch.object(app.POSTING_OPENER, 'open', side_effect=fixture_response):
            app.init()
            app.prototype.change_saved_search(app, {'action': 'save', 'criteria': dict(
                name='Fictional payments search', skills=['Excel'], locations=['United States'],
                workplace_types=['remote'], salary_min=80000, salary_max=None, enabled=True,
            )})
            with app.connect() as connection:
                search_id = app.prototype.saved_searches(connection)[0]['id']
                for key, title in [('billing', 'Billing Analyst'), ('software', 'Software Engineer')]:
                    job = dict(
                        title=title, employer='Fictional Cedar Accounts',
                        description=('Responsibilities:\nReconcile payments using Excel.' if key == 'billing'
                                     else 'Fictional starter listing.'),
                        location='Remote - United States', remote=True, availability='Open',
                        url=f'https://example.com/{key}',
                    )
                    if key == 'billing':
                        job.update(posting_verified=app.now(), salary_min=85000, salary_max=105000,
                                   salary_currency='USD', salary_period='year', salary_type='base')
                    job_id, _ = app.upsert(connection, job)
                    app.prototype.record_match_alerts(connection, job_id, [search_id], app.now())
            with ThreadingHTTPServer(('127.0.0.1', 18085), app.Handler) as server:
                print('Jobs search fixture ready at http://127.0.0.1:18085', flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    return


if __name__ == '__main__':
    serve()
