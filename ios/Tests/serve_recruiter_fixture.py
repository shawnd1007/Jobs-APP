"""Run the isolated V2 experience with simulated AI and employer responses."""
from pathlib import Path
import sys
from http.server import ThreadingHTTPServer
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fixtures.recruiter_fixture import environment

if __name__ == '__main__':
    with environment() as (app, calls):
        with ThreadingHTTPServer(('127.0.0.1', 18087), app.Handler) as server:
            print('Jobs V2 QA at http://127.0.0.1:18087 — fictional feeds and simulated AI; empty profile and database.', flush=True)
            server.serve_forever()
