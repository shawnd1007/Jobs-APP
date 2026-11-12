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
    app.DATA=target;app.DB=target/'qa.sqlite3'
    (target/'preferences.json').write_text(json.dumps({
        'profile': 'Used Excel and SQL for fictional monthly reporting.',
        'preferred_skills': ['Excel', 'SQL'],
    }), encoding='utf-8')
    app.init()
    with app.connect() as c:
        for j in app.records():
            if j['id']<=4:
                j.update(employer='QA Fixture '+str(j['id']),title='Financial Analyst QA '+str(j['id']),url='https://example.com/qa-'+str(j['id']),location='Remote - United States' if j['id']!=4 else 'Remote - Mexico',remote=True,availability='Open',queue='Review',score=80,description='Isolated test record; no employment claim.',explanation='Test salary and location review.',salary_text='Salary not yet verified',application_evidence='QA application evidence only.')
                if j['id']==1:
                    j['description']='Responsibilities:\nReconcile sample accounts in Excel.\nBuild SQL reports.'
                elif j['id']==2:
                    j['posting_verified'] = app.now()
            else:j['availability']='Closed'
            c.execute('UPDATE jobs SET listing=? WHERE id=?',(json.dumps(j),j['id']))
        for requisition in ('101', '102'):
            app.upsert(c, dict(
                title='Fictional Reconciliation Analyst', employer='Fictional Employer',
                url='https://example.com/careers?posting=' + requisition, location='Remote - United States',
                workplace_type='hybrid' if requisition == '101' else 'remote',
                salary_min=75000, salary_max=110000, salary_currency='USD', salary_period='year',
                salary_type='base', salary_text='$75,000 – $110,000 annual base',
                description='Fictional employer posting for browser tests.', availability='Open',
            ))
    class QAHandler(app.Handler):
        def do_POST(self):
            if self.path=='/qa-stop':
                self.send(200,{'stopped':True});threading.Thread(target=self.server.shutdown,daemon=True).start();return
            return super().do_POST()
    server=ThreadingHTTPServer(('127.0.0.1',18084),QAHandler)
    print('QA_READY',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
