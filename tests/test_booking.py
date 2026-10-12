import sys, tempfile, unittest, json, secrets, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as s
class BookingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();s.DB=Path(self.tmp.name)/'test.sqlite';s.init()
  self.c=json.loads((s.ROOT/'config.json').read_text())
  for b in self.c['branches']:b.update(bookingEnabled=True,capacity=1,hours={str(i):['08:00','20:00'] for i in range(7)})
  for v in self.c['services']:v['branches']={b:{c:{'duration':60,'price':None} for c in self.c['categories']} for b in ['dso','dip']}
  self.day=(datetime.now(s.TZ)+timedelta(days=3)).date(); self.start=datetime.combine(self.day,datetime.strptime('10:00','%H:%M').time())
  self.save_config();self.p={'branch':'dso','service':'wash','category':self.c['categories'][0],'start':self.start.isoformat(),'name':'Test Customer','mobile':'+971500000000','email':'test@example.com','notes':'Automated test','token':secrets.token_hex(16),'consent':True}
 def tearDown(self): self.tmp.cleanup()
 def save_config(self):
  with s.connect() as db:db.execute('UPDATE settings SET data=?',(json.dumps(self.c),))
 def book(self,**kwargs):
  with s.connect() as db:return s.book(db,{**self.p,**kwargs})
 def test_request_and_idempotency(self):
  r=self.book();self.assertEqual(r['status'],'pending');self.assertEqual(r['reference'],self.book()['reference'])
  with s.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM bookings').fetchone()[0],1)
  with self.assertRaises(ValueError):self.book(notes='changed')
 def test_overbooking_and_branch_isolation(self):
  self.book()
  with self.assertRaises(ValueError):self.book(token=secrets.token_hex(16),mobile='+971500000001')
  self.assertEqual(self.book(branch='dip',token=secrets.token_hex(16))['status'],'pending')
 def test_overlap_and_adjacent(self):
  self.book()
  with self.assertRaises(ValueError):self.book(start=(self.start+timedelta(minutes=30)).isoformat(),token=secrets.token_hex(16))
  self.book(start=(self.start+timedelta(minutes=60)).isoformat(),token=secrets.token_hex(16))
 def test_parallel_last_slot(self):
  barrier=threading.Barrier(6)
  def attempt(i):
   barrier.wait()
   try:return self.book(token=secrets.token_hex(16),mobile='+97150000000'+str(i))['status']
   except ValueError:return 'rejected'
  with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(attempt,range(6)))
  self.assertEqual(results.count('pending'),1);self.assertEqual(results.count('rejected'),5)
 def test_capacity_two(self):
  self.c['branches'][0]['capacity']=2;self.save_config();self.book();self.book(token=secrets.token_hex(16),mobile='+971500000001')
  with self.assertRaises(ValueError):self.book(token=secrets.token_hex(16),mobile='+971500000002')
 def test_blocked_day_and_interval(self):
  self.c['branches'][0]['blocked']=[{'date':str(self.day)}];self.save_config()
  with self.assertRaises(ValueError):self.book()
  self.c['branches'][0]['blocked']=[{'start':(self.start+timedelta(minutes=45)).isoformat(),'end':(self.start+timedelta(minutes=90)).isoformat()}];self.save_config()
  with self.assertRaises(ValueError):self.book()
 def test_hours_duration_and_past(self):
  for hour in [7,20]:
   with self.assertRaises(ValueError):self.book(start=self.start.replace(hour=hour).isoformat())
  with self.assertRaises(ValueError):self.book(start=(self.start-timedelta(days=10)).isoformat())
  with self.assertRaises(ValueError):self.book(start=self.start.replace(minute=7).isoformat())
 def test_validation(self):
  for change in [{'name':'a'},{'mobile':'abc'},{'email':'bad'},{'consent':False},{'branch':'bad'},{'category':'bad'},{'service':'bad'},{'notes':'x'*2001}]:
   with self.assertRaises(ValueError):self.book(**change)
 def test_missing_configuration(self):
  self.c['branches'][0]['bookingEnabled']=False;self.save_config()
  with self.assertRaises(ValueError):self.book()
 def test_duplicate_without_same_token(self):
  self.c['branches'][0]['capacity']=2;self.save_config();self.book()
  with self.assertRaises(ValueError):self.book(token=secrets.token_hex(16))
 def test_config_validation(self):
  s.validate_config(self.c);self.c['branches'][0]['capacity']=0
  with self.assertRaises(ValueError):s.validate_config(self.c)
 def test_cancelled_releases_capacity(self):
  r=self.book()
  with s.connect() as db:db.execute('UPDATE bookings SET status="cancelled" WHERE id=?',(r['reference'],))
  self.book(token=secrets.token_hex(16))
if __name__=='__main__':unittest.main(verbosity=2)
