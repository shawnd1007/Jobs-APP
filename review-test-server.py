"""Isolated UI test service; never opens the production database."""
import json
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
import app
app.SEED=Path(__file__).resolve().parent/'fixtures'/'seed.html'

with tempfile.TemporaryDirectory(prefix='review-qa-',dir=app.DATA) as folder:
    original_data=app.DATA.resolve();target=Path(folder).resolve()
    if not target.is_relative_to(original_data):raise RuntimeError('QA folder outside workspace')
    app.DATA=target;app.DB=target/'qa.sqlite3';app.init()
    with app.connect() as c:
        for j in app.records():
            if j['id']<=4:
                j.update(employer='QA Fixture '+str(j['id']),title='Financial Analyst QA '+str(j['id']),url='https://example.com/qa-'+str(j['id']),location='Remote - United States' if j['id']!=4 else 'Remote - Mexico',remote=True,availability='Open',queue='Review',score=80,description='Isolated test record; no employment claim.',explanation='Test salary and location review.',salary_text='Salary not yet verified',application_evidence='QA application evidence only.')
            else:j['availability']='Closed'
            c.execute('UPDATE jobs SET listing=? WHERE id=?',(json.dumps(j),j['id']))
    class QAHandler(app.Handler):
        def do_POST(self):
            if self.path=='/qa-stop':
                self.send(200,{'stopped':True});threading.Thread(target=self.server.shutdown,daemon=True).start();return
            return super().do_POST()
    server=ThreadingHTTPServer(('127.0.0.1',18084),QAHandler)
    print('QA_READY',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
