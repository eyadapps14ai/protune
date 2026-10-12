"""Protune: dependency-free web server with transactional SQLite bookings."""
import os, json, sqlite3, secrets, hashlib, hmac, re, time, argparse
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs
from http.cookies import SimpleCookie
import mimetypes
ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('PROTUNE_DB', ROOT / 'data/protune.sqlite3'))
TZ = ZoneInfo('Asia/Dubai')
SESSIONS = {}
ATTEMPTS = {}

def connect():
    db = sqlite3.connect(DB, timeout=15, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

def init():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS staff(username TEXT PRIMARY KEY, salt TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bookings(id TEXT PRIMARY KEY, token TEXT UNIQUE NOT NULL, payload_hash TEXT NOT NULL, branch TEXT NOT NULL, service TEXT NOT NULL, category TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, name TEXT NOT NULL, mobile TEXT NOT NULL, email TEXT, notes TEXT, status TEXT NOT NULL, created TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS booking_availability ON bookings(branch,start,end,status);
        CREATE TABLE IF NOT EXISTS booking_links(booking_id TEXT PRIMARY KEY REFERENCES bookings(id), secret TEXT UNIQUE NOT NULL, original_start TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS contacts(id TEXT PRIMARY KEY, branch TEXT NOT NULL, name TEXT NOT NULL, mobile TEXT NOT NULL, email TEXT, message TEXT NOT NULL, created TEXT NOT NULL);
        ''')
        db.execute('INSERT OR IGNORE INTO settings VALUES(1,?)', ((ROOT/'config.json').read_text(),))

def config(db):
    return json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])

def need(condition, message):
    if not condition: raise ValueError(message)

def parse_time(s):
    need(isinstance(s,str) and bool(re.fullmatch(r'\d{2}:\d{2}',s)), 'Use HH:MM times.')
    return datetime.strptime(s,'%H:%M').time()

def validate_config(c):
    need(c.get('timezone')=='Asia/Dubai' and c.get('currency')=='AED', 'Timezone must be Asia/Dubai and currency AED.')
    need(isinstance(c.get('categories'),list) and 0<len(c['categories'])<=20 and all(isinstance(x,str) and 0<len(x)<=100 for x in c['categories']), 'Vehicle categories are required.')
    need({b['id'] for b in c['branches']}=={'dso','dip'} and len(c['branches'])==2,'Keep the two branch IDs dso and dip.')
    for b in c['branches']:
        need(isinstance(b.get('name'),str) and len(b['name'])<=100,'Branch name required.')
        cap=b.get('capacity')
        need(cap is None or type(cap)==int and 1<=cap<=100,'Capacity must be 1–100.')
        need(type(b.get('bookingEnabled'))==bool,'bookingEnabled must be true or false.')
        for key,value in b.get('hours',{}).items():
            need(key in list('0123456') and isinstance(value,list) and len(value)==2,'Hours: 0 = Monday, through 6 = Sunday; use [open, close].')
            need(parse_time(value[0])<parse_time(value[1]),'Closing time must follow opening time; split overnight shifts.')
        if b['bookingEnabled']: need(cap and b.get('hours'),'Set capacity and hours before enabling bookings.')
        for block in b.get('blocked',[]):
            if 'date' in block: datetime.strptime(block['date'],'%Y-%m-%d')
            else:
                s=datetime.fromisoformat(block['start']); e=datetime.fromisoformat(block['end'])
                need(s.tzinfo is None and e.tzinfo is None and s<e,'Blocked intervals use Dubai local ISO times without timezone, and end after start.')
        for k in ['mapUrl','photo']:
            need(not b.get(k) or b[k].startswith('https://') or k=='photo' and b[k].startswith('/assets/'),'Maps/photos must use HTTPS or local /assets/ photos.')
        for k in ['phone','whatsapp']:
            need(not b.get(k) or re.fullmatch(r'\+?[0-9 ()-]{7,25}',b[k]),'Contact numbers must contain digits and optional +, spaces, parentheses or hyphens.')
    items=c.get('services',[])+c.get('packages',[])
    need(len({s['id'] for s in items})==len(items),'Service IDs must be unique.')
    for s in items:
        need(isinstance(s.get('name'),str) and len(s['name'])<=120,'Service name required.')
        for branch,options in s.get('branches',{}).items():
            need(branch in ['dso','dip'],'Unknown branch.')
            for category,opt in options.items():
                need(category in c['categories'],'Unknown vehicle category.')
                need(type(opt.get('duration'))==int and 15<=opt['duration']<=600,'Duration must be 15–600 minutes.')
                p=opt.get('price'); need(p is None or type(p) in (int,float) and 0<=p<=100000,'Price must be a positive AED amount or null.')
    for s in c.get('socials',[]): need(s['url'].startswith('https://'),'Social links must use HTTPS.')
    for g in c.get('gallery',[]):
        for k in ['before','after']: need(g[k].startswith('/assets/') or g[k].startswith('https://'),'Gallery URLs must be local assets or HTTPS.')

def service_option(c,branch,service,category):
    b=next((b for b in c['branches'] if b['id']==branch),None)
    s=next((s for s in c['services']+c.get('packages',[]) if s['id']==service),None)
    need(b and s and category in c['categories'],'Select a valid branch, service and vehicle category.')
    opt=s.get('branches',{}).get(branch,{}).get(category)
    need(b.get('bookingEnabled') and b.get('capacity') and opt,'Online booking is not yet available for this selection. Please request a quote.')
    return b,s,opt

def slot_ok(db,c,branch,service,category,start,exclude=None,check_future=True):
    b,s,opt=service_option(c,branch,service,category)
    need(start.tzinfo is None,'Use Dubai local time without a timezone suffix.')
    now=datetime.now(TZ).replace(tzinfo=None)
    end=start+timedelta(minutes=opt['duration'])
    if check_future: need(start>now+timedelta(minutes=30) and start<now+timedelta(days=91),'Bookings must be 30 minutes to 90 days ahead.')
    need(start.minute%15==0 and start.second==0 and start.microsecond==0,'Choose a listed 15-minute slot.')
    hours=b.get('hours',{}).get(str(start.weekday()))
    need(hours and start.date()==end.date() and start.time()>=parse_time(hours[0]) and end.time()<=parse_time(hours[1]),'This time is outside branch opening hours.')
    for block in b.get('blocked',[]):
        if 'date' in block: need(block['date']!=start.date().isoformat(),'The branch is unavailable on this date.')
        else: need(not (start<datetime.fromisoformat(block['end']) and end>datetime.fromisoformat(block['start'])),'This time is blocked.')
    rows=db.execute("SELECT start,end FROM bookings WHERE branch=? AND status IN ('pending','confirmed') AND start<? AND end>? AND id!=?",(branch,end.isoformat(),start.isoformat(),exclude or '')).fetchall()
    events=[(start,1),(end,-1)]
    for row in rows: events.extend([(max(start,datetime.fromisoformat(row['start'])),1),(min(end,datetime.fromisoformat(row['end'])),-1)])
    count=0
    for _,delta in sorted(events,key=lambda e:(e[0],e[1])):
        count+=delta; need(count<=b['capacity'],'This slot has just filled up. Please select another time.')
    return end

def contact_fields(p):
    need(isinstance(p.get('name'),str) and 2<=len(p['name'].strip())<=100,'Enter your name (2–100 characters).')
    need(isinstance(p.get('mobile'),str) and re.fullmatch(r'\+?[0-9 ()-]{7,25}',p['mobile']) and 7<=len(re.sub(r'\D','',p['mobile']))<=15,'Enter a valid mobile number with country code.')
    email=p.get('email',''); need(isinstance(email,str) and len(email)<=254 and (not email or re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email)),'Enter a valid email address.')
    need(isinstance(p.get('notes',''),str) and len(p.get('notes',''))<=2000,'Notes must be under 2,000 characters.')

def book(db,p):
    contact_fields(p)
    need(p.get('consent') is True,'Please agree to the booking privacy notice.')
    token=p.get('token',''); need(isinstance(token,str) and 16<=len(token)<=100,'Missing submission token. Refresh and try again.')
    digest=hashlib.sha256(json.dumps({k:v for k,v in p.items() if k!='token'},sort_keys=True).encode()).hexdigest()
    db.execute('BEGIN IMMEDIATE')
    try:
        existing=db.execute('SELECT id,status,payload_hash FROM bookings WHERE token=?',(token,)).fetchone()
        if existing:
            need(existing['payload_hash']==digest,'This submission token was already used for different details.')
            url=status_link(db,existing['id']);db.commit(); return {'reference':existing['id'],'status':existing['status'],'duplicate':True,'statusUrl':url}
        c=config(db); start=datetime.fromisoformat(p['start'])
        end=slot_ok(db,c,p['branch'],p['service'],p['category'],start)
        mobile=re.sub(r'\D','',p['mobile'])
        duplicate=db.execute("SELECT id FROM bookings WHERE branch=? AND mobile=? AND start=? AND status IN ('pending','confirmed')",(p['branch'],mobile,start.isoformat())).fetchone()
        need(not duplicate,'You already have a request at this branch and time. Contact the branch to change it.')
        ref=('DEMO-' if c.get('previewMode') else 'PT-')+secrets.token_hex(5).upper()
        db.execute('INSERT INTO bookings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(ref,token,digest,p['branch'],p['service'],p['category'],start.isoformat(),end.isoformat(),p['name'].strip(),mobile,p.get('email',''),p.get('notes',''),'pending',datetime.now(TZ).isoformat()))
        url=status_link(db,ref);db.commit(); return {'reference':ref,'status':'pending','statusUrl':url}
    except: db.rollback(); raise

def status_link(db,reference):
    row=db.execute('SELECT secret FROM booking_links WHERE booking_id=?',(reference,)).fetchone()
    if not row:
        start=db.execute('SELECT start FROM bookings WHERE id=?',(reference,)).fetchone()[0]
        db.execute('INSERT OR IGNORE INTO booking_links VALUES(?,?,?)',(reference,secrets.token_urlsafe(32),start))
        row=db.execute('SELECT secret FROM booking_links WHERE booking_id=?',(reference,)).fetchone()
    return '/booking-status#'+row['secret']

def customer_status(db,secret):
    if not isinstance(secret,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',secret): return None
    row=db.execute('SELECT b.*,l.original_start FROM bookings b JOIN booking_links l ON b.id=l.booking_id WHERE l.secret=?',(secret,)).fetchone()
    if not row:return None
    c=config(db)
    branch=next((b for b in c['branches'] if b['id']==row['branch']),{})
    service=next((v for v in c['services']+c.get('packages',[]) if v['id']==row['service']),{})
    return {'reference':row['id'],'status':row['status'],'branch':branch.get('name',row['branch']),
            'service':service.get('name',row['service']),'category':row['category'],'start':row['start'],'end':row['end'],
            'rescheduled':row['start']!=row['original_start'],'timezone':'Asia/Dubai','demo':row['id'].startswith('DEMO-')}

def password_hash(password,salt): return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def output(self,obj,status=200,cookie=None):
        data=json.dumps(obj).encode(); self.send_response(status)
        self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(data)
    def session(self):
        cookie=SimpleCookie(); cookie.load(self.headers.get('Cookie',''))
        sid=cookie.get('protune_session'); value=SESSIONS.get(sid.value if sid else '')
        return value if value and value['expires']>time.time() else None
    def do_GET(self):
        path=urlsplit(self.path).path; q={k:v[0] for k,v in parse_qs(urlsplit(self.path).query).items()}
        try:
            with connect() as db:
                if path=='/api/config': return self.output(config(db))
                if path=='/api/availability':
                    c=config(db); day=datetime.strptime(q['date'],'%Y-%m-%d'); result=[]
                    service_option(c,q['branch'],q['service'],q['category'])
                    for i in range(96):
                        start=day+timedelta(minutes=i*15)
                        try: slot_ok(db,c,q['branch'],q['service'],q['category'],start);result.append(start.isoformat())
                        except ValueError:pass
                    return self.output({'slots':result,'timezone':'Asia/Dubai'})
                if path.startswith('/api/staff/'):
                    session=self.session()
                    if not session:return self.output({'error':'Staff sign-in required.'},401)
                    if path=='/api/staff/session':return self.output({'username':session['user'],'csrf':session['csrf']})
                    if path=='/api/staff/bookings':
                        rows=db.execute('SELECT * FROM bookings WHERE (?="" OR branch=?) AND (?="" OR substr(start,1,10)=?) ORDER BY start',(q.get('branch',''),q.get('branch',''),q.get('date',''),q.get('date',''))).fetchall()
                        return self.output([{**{k:r[k] for k in r.keys() if k not in ('token','payload_hash')},'statusUrl':status_link(db,r['id'])} for r in rows])
                    if path=='/api/staff/contacts':return self.output([dict(r) for r in db.execute('SELECT * FROM contacts ORDER BY created DESC LIMIT 500')])
                if path.startswith('/api/'):return self.output({'error':'Not found'},404)
            target=(ROOT/'public'/path.lstrip('/')).resolve()
            if path=='/' or path in ['/services','/branches','/about','/contact','/book','/privacy','/booking-status']:target=ROOT/'public/index.html'
            if path=='/staff':target=ROOT/'public/staff.html'
            if not target.is_relative_to(ROOT/'public') or not target.is_file():return self.output({'error':'Not found'},404)
            data=target.read_bytes();self.send_response(200);
            if path=='/booking-status':self.send_header('X-Robots-Tag','noindex, nofollow');self.send_header('Cache-Control','no-store')
            self.send_header('Content-Type',mimetypes.guess_type(str(target))[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(data)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','strict-origin-when-cross-origin');self.send_header('X-Frame-Options','DENY');self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");self.end_headers();self.wfile.write(data)
        except (ValueError,KeyError,TypeError) as e:self.output({'error':str(e)},400)
    def do_POST(self):
        path=urlsplit(self.path).path
        try:
            origin=self.headers.get('Origin')
            need(not origin or urlsplit(origin).netloc==self.headers.get('Host'),'Cross-origin requests are not allowed.')
            need(self.headers.get('Content-Type','').startswith('application/json'),'JSON requests required.')
            length=int(self.headers.get('Content-Length',0));need(0<length<=100000,'Invalid request size.')
            p=json.loads(self.rfile.read(length));need(isinstance(p,dict),'Invalid payload.')
            with connect() as db:
                if path=='/api/booking-status':
                    key='status:'+self.client_address[0];recent=[t for t in ATTEMPTS.get(key,[]) if t>time.time()-60]
                    need(len(recent)<60,'Please wait a minute before checking again.');ATTEMPTS[key]=recent+[time.time()]
                    result=customer_status(db,p.get('token'))
                    return self.output(result if result else {'error':'This private booking link is invalid. Please contact the branch with your booking reference.'},200 if result else 404)
                if path=='/api/login':
                    key=self.client_address[0]; attempts=[t for t in ATTEMPTS.get(key,[]) if t>time.time()-900]
                    need(len(attempts)<10,'Too many login attempts. Try again in 15 minutes.')
                    ATTEMPTS[key]=attempts+[time.time()]
                    user=db.execute('SELECT * FROM staff WHERE username=?',(str(p.get('username','')),)).fetchone()
                    need(user and hmac.compare_digest(user['hash'],password_hash(str(p.get('password','')),user['salt'])),'Invalid username or password.')
                    sid=secrets.token_urlsafe(32);session={'user':user['username'],'csrf':secrets.token_urlsafe(24),'expires':time.time()+28800};SESSIONS[sid]=session
                    secure='; Secure' if os.environ.get('PROTUNE_SECURE_COOKIE')=='1' else ''
                    return self.output({'csrf':session['csrf'],'username':user['username']},cookie=f'protune_session={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{secure}')
                if path.startswith('/api/staff/') or path=='/api/logout':
                    session=self.session()
                    if not session:return self.output({'error':'Staff sign-in required.'},401)
                    if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']):return self.output({'error':'Invalid security token. Sign in again.'},403)
                    if path=='/api/logout':
                        cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''));SESSIONS.pop(cookie['protune_session'].value,None)
                        return self.output({'ok':True},cookie='protune_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
                    if path=='/api/staff/config':
                        validate_config(p); db.execute('BEGIN IMMEDIATE')
                        try:
                            # Reject configuration that invalidates outstanding reservations.
                            current=config(db)
                            for r in db.execute("SELECT * FROM bookings WHERE status IN ('pending','confirmed') AND end>?",(datetime.now(TZ).replace(tzinfo=None).isoformat(),)).fetchall():
                                b,s,opt=service_option(p,r['branch'],r['service'],r['category'])
                                need(opt['duration']==int((datetime.fromisoformat(r['end'])-datetime.fromisoformat(r['start'])).total_seconds()/60),'Reschedule or cancel affected appointments before changing their duration.')
                                slot_ok(db,p,r['branch'],r['service'],r['category'],datetime.fromisoformat(r['start']),r['id'],check_future=False)
                            db.execute('UPDATE settings SET data=? WHERE id=1',(json.dumps(p),));db.commit()
                        except: db.rollback();raise
                        return self.output({'ok':True})
                    if path=='/api/staff/booking':
                        db.execute('BEGIN IMMEDIATE')
                        try:
                            row=db.execute('SELECT * FROM bookings WHERE id=?',(p.get('id'),)).fetchone();need(row,'Booking not found.');status_link(db,row['id'])
                            status=p.get('status');need(status in ['pending','confirmed','cancelled','completed'],'Invalid booking status.')
                            need(row['status'] not in ['cancelled','completed'] or status==row['status'],'Closed appointments cannot be reopened. Create a new booking.')
                            start=datetime.fromisoformat((p.get('start') or row['start']) if status in ['pending','confirmed'] else row['start']); end=datetime.fromisoformat(row['end'])
                            if status in ['pending','confirmed']:
                                if start.isoformat()!=row['start']:end=slot_ok(db,config(db),row['branch'],row['service'],row['category'],start,row['id'])
                                else:
                                    need(row['status'] in ['pending','confirmed'],'Invalid state transition.')
                            if status=='completed':need(start<=datetime.now(TZ).replace(tzinfo=None),'Future appointments cannot be marked complete.')
                            db.execute('UPDATE bookings SET start=?,end=?,status=? WHERE id=?',(start.isoformat(),end.isoformat(),status,row['id']));db.commit()
                        except:db.rollback();raise
                        return self.output({'ok':True,'notificationSent':False})
                if path in ['/api/bookings','/api/contact']:
                    key='public:'+self.client_address[0];recent=[t for t in ATTEMPTS.get(key,[]) if t>time.time()-60];need(len(recent)<20,'Please wait a minute before trying again.');ATTEMPTS[key]=recent+[time.time()]
                    if path=='/api/bookings':return self.output(book(db,p),201)
                    contact_fields(p);need(p.get('branch') in ['dso','dip'],'Choose a branch.');need(isinstance(p.get('message'),str) and 10<=len(p['message'].strip())<=4000,'Enter a message of 10–4,000 characters.');need(p.get('consent') is True,'Please agree to the privacy notice.')
                    ref='ENQ-'+secrets.token_hex(4).upper();db.execute('INSERT INTO contacts VALUES(?,?,?,?,?,?,?)',(ref,p['branch'],p['name'],p['mobile'],p.get('email',''),p['message'],datetime.now(TZ).isoformat()))
                    return self.output({'reference':ref,'status':'received','notificationSent':False},201)
                return self.output({'error':'Not found'},404)
        except (ValueError,KeyError,TypeError,OverflowError) as e:self.output({'error':str(e)},400)
        except Exception:self.output({'error':'The request could not be saved. Please try again.'},500)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8080);parser.add_argument('--create-staff');args=parser.parse_args();init()
    if args.create_staff:
        import getpass
        password=getpass.getpass('New staff password (minimum 12 characters): ');need(len(password)>=12,'Use at least 12 characters.');salt=secrets.token_hex(16)
        with connect() as db:db.execute('INSERT OR REPLACE INTO staff VALUES(?,?,?)',(args.create_staff,salt,password_hash(password,salt)))
        print('Staff account saved.')
    else:
        print(f'Protune preview: http://127.0.0.1:{args.port}',flush=True)
        ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
