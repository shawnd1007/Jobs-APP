"""Local test service for the iPhone search workflow, with a disposable database."""
import json
import os
from pathlib import Path
import sys
import tempfile
from http.server import ThreadingHTTPServer
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE))


def fixture_board(platform, slug):
    if (platform, slug) != ('ashby', 'fictional'):
        raise ValueError('Unexpected board in the fictional search test.')
    return [dict(
        title='Payment Operations Specialist', employer='Fictional Lantern Payments',
        description='Responsibilities:\nBuild SQL reports.\nReconcile invoices in Excel.',
        location='Remote - United States', remote=True, availability='Open',
        url='https://jobs.ashbyhq.com/fictional/job-new/application',
    )]


def serve():
    with tempfile.TemporaryDirectory(prefix='jobs-search-qa-') as folder:
        root = Path(folder)
        os.environ['JOBS_DATA'] = str(root / 'data')
        import app

        cfg = json.loads((SOURCE / 'config.example.json').read_text(encoding='utf-8'))
        cfg.update(
            categories=['billing analyst'], preferred_skills=['Excel', 'SQL'],
            profile='Fictional experience reconciling accounts using Excel and SQL.',
            additional_boards={'ashby': ['fictional']}, target_locations=['United States'],
            workplace_types=['remote'], request_delay_seconds=0, generic_urls_per_run=0,
        )
        (root / 'config.json').write_text(json.dumps(cfg), encoding='utf-8')
        with patch.object(app, 'ROOT', root), patch.object(app, 'SEED', SOURCE / 'seed.empty.html'), \
             patch.object(app, 'board_jobs', side_effect=fixture_board):
            app.init()
            with app.connect() as connection:
                for key, title in [('billing', 'Billing Analyst'), ('software', 'Software Engineer')]:
                    app.upsert(connection, dict(
                        title=title, employer='Fictional Cedar Accounts', description='Fictional starter listing.',
                        location='Remote - United States', remote=True, availability='Open',
                        url=f'https://example.com/{key}',
                    ))
            with ThreadingHTTPServer(('127.0.0.1', 18085), app.Handler) as server:
                print('Jobs search fixture ready at http://127.0.0.1:18085', flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    return


if __name__ == '__main__':
    serve()
