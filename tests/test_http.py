import json, threading, urllib.request, urllib.error, http.cookiejar, secrets, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_booking
import unittest
import server as s
from datetime import timedelta
class HTTPTests(unittest.TestCase):
 save_config=test_booking.BookingTests.save_config
 book=test_booking.BookingTests.book
 def setUp(self):
  test_booking.BookingTests.setUp(self);s.ATTEMPTS.clear();salt=secrets.token_hex(16)
  with s.connect() as db:db.execute('INSERT INTO staff VALUES(?,?,?)',('teststaff',salt,s.password_hash('Local-QA-only-7826',salt)))
  self.server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);threading.Thread(target=self.server.serve_forever,daemon=True).start();self.url='http://127.0.0.1:'+str(self.server.server_port);self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));self.csrf=''
 def tearDown(self):self.server.shutdown();self.server.server_close();test_booking.BookingTests.tearDown(self)
 def req(self,path,data=None,csrf=True):
  headers={'Content-Type':'application/json'}
  if csrf:headers['X-CSRF-Token']=self.csrf
  req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
  try:
   with self.client.open(req) as r:return r.status,json.loads(r.read())
  except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
 def login(self):
  code,data=self.req('/api/login',{'username':'teststaff','password':'Local-QA-only-7826'});self.assertEqual(code,200);self.csrf=data['csrf']
 def test_staff_auth_csrf_and_logout(self):
  self.assertEqual(self.req('/api/staff/bookings')[0],401);self.assertEqual(self.req('/api/staff/config',self.c)[0],401)
  self.login();self.assertEqual(self.req('/api/staff/config',self.c,False)[0],403)
  self.assertEqual(self.req('/api/staff/config',self.c)[0],200)
  self.assertEqual(self.req('/api/logout',{})[0],200);self.assertEqual(self.req('/api/staff/bookings')[0],401)
 def test_staff_lifecycle_conflict_and_filters(self):
  ref=self.book()['reference'];self.login()
  self.assertEqual(len(self.req('/api/staff/bookings?branch=dso')[1]),1);self.assertEqual(len(self.req('/api/staff/bookings?branch=dip')[1]),0)
  self.assertEqual(self.req('/api/staff/booking',{'id':ref,'status':'confirmed'})[0],200)
  later=(self.start+timedelta(hours=2)).isoformat();self.assertEqual(self.req('/api/staff/booking',{'id':ref,'status':'confirmed','start':later})[0],200)
  self.book(token=secrets.token_hex(16));self.assertEqual(self.req('/api/staff/booking',{'id':ref,'status':'confirmed','start':self.start.isoformat()})[0],400)
  self.assertEqual(self.req('/api/staff/booking',{'id':ref,'status':'completed'})[0],400)
  self.assertEqual(self.req('/api/staff/booking',{'id':ref,'status':'cancelled'})[0],200)
  self.assertEqual(self.req('/api/staff/booking',{'id':ref,'status':'confirmed'})[0],400)
 def test_contact_storage(self):
  self.assertEqual(self.req('/api/contact',{'name':'QA Customer','mobile':'+971500000000','branch':'dso','message':'Automated QA enquiry','consent':True})[0],201)
  self.login();self.assertEqual(len(self.req('/api/staff/contacts')[1]),1)
 def test_config_cannot_break_reservations(self):
  self.book();self.login();self.c['branches'][0]['blocked']=[{'date':str(self.day)}];self.assertEqual(self.req('/api/staff/config',self.c)[0],400)
 def test_completed_releases_capacity(self):
  ref=self.book()['reference'];self.login()
  with s.connect() as db:db.execute('UPDATE bookings SET start=?,end=? WHERE id=?',((self.start-timedelta(days=4)).isoformat(),(self.start-timedelta(days=4)+timedelta(hours=1)).isoformat(),ref))
  self.assertEqual(self.req('/api/staff/booking',{'id':ref,'status':'completed'})[0],200)
 def test_public_post_and_all_routes(self):
  self.assertEqual(self.req('/api/bookings',self.p)[0],201)
  for path in ['/','/services','/branches','/about','/book','/contact','/staff','/privacy','/logo-concepts.html','/logos/favicon.svg','/assets/hero-car.webp']:
   with self.client.open(self.url+path) as r:self.assertEqual(r.status,200)
 def test_private_status_link_and_updates(self):
  code,receipt=self.req('/api/bookings',self.p);self.assertEqual(code,201)
  secret=receipt['statusUrl'].split('#')[1]
  self.assertEqual(self.req('/api/bookings',self.p)[1]['statusUrl'],receipt['statusUrl'])
  code,status=self.req('/api/booking-status',{'token':secret});self.assertEqual(code,200);self.assertEqual(status['status'],'pending')
  for field in ['name','mobile','email','notes','token','payload_hash']:self.assertNotIn(field,status)
  self.assertEqual(self.req('/api/booking-status',{'token':receipt['reference']})[0],404)
  self.assertEqual(self.req('/api/booking-status',{'token':'x'*43})[0],404)
  self.login();later=(self.start+timedelta(hours=2)).isoformat()
  self.assertEqual(self.req('/api/staff/booking',{'id':receipt['reference'],'status':'confirmed','start':later})[0],200)
  status=self.req('/api/booking-status',{'token':secret})[1];self.assertEqual(status['status'],'confirmed');self.assertTrue(status['rescheduled']);self.assertEqual(status['start'],later)
  self.req('/api/staff/booking',{'id':receipt['reference'],'status':'cancelled'})
  self.assertEqual(self.req('/api/booking-status',{'token':secret})[1]['status'],'cancelled')
  with self.client.open(self.url+'/booking-status') as response:self.assertEqual(response.headers['X-Robots-Tag'],'noindex, nofollow')
