"""Disposable local-only UI QA fixture. Never use for customer appointments."""
import sys,tempfile,json,secrets,atexit
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as s
folder=tempfile.TemporaryDirectory(prefix='protune-ui-qa-');atexit.register(folder.cleanup);s.DB=Path(folder.name)/'qa.sqlite';s.init()
c=json.loads((s.ROOT/'config.json').read_text());c['previewMode']=True
for b in c['branches']:b.update(bookingEnabled=True,capacity=1,hours={str(i):['08:00','20:00'] for i in range(7)})
for v in c['services']:v['branches']={b:{cat:{'duration':60,'price':None} for cat in c['categories']} for b in ['dso','dip']}
salt=secrets.token_hex(16)
with s.connect() as db:
 db.execute('UPDATE settings SET data=?',(json.dumps(c),))
 db.execute('INSERT INTO staff VALUES(?,?,?)',('qa-staff',salt,s.password_hash('Local-QA-only-7826',salt)))
print('Disposable UI QA only: http://127.0.0.1:8081',flush=True)
s.ThreadingHTTPServer(('127.0.0.1',8081),s.Handler).serve_forever()
