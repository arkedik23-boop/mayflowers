import hmac,hashlib,json,threading,time,subprocess,os,sys,queue,urllib.parse,urllib.request,re,sqlite3
import os as _os
HERE=_os.path.dirname(_os.path.abspath(__file__))+'/'
REPO=_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
WORK=HERE+'_work/';_os.makedirs(WORK,exist_ok=True)
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
D=WORK
CALLS=[];UPD=queue.Queue();LOCK=threading.Lock();MID=[1]
VOICE=open(HERE+'media/voice.ogg','rb').read()
class Mock(BaseHTTPRequestHandler):
  def do_GET(self):
    if '/file/' in self.path:
      b=VOICE;self.send_response(200);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
  def do_POST(self):
    m=self.path.rsplit('/',1)[1];n=int(self.headers.get('Content-Length') or 0);raw=self.rfile.read(n)
    if 'multipart' in (self.headers.get('Content-Type') or ''):
      txt=raw.decode('utf-8','replace');p={'_multipart':True,'chat_id':int(re.search(r'name="chat_id"\r\n\r\n(-?\d+)',txt).group(1)),'_len':n,'_files':re.findall(r'filename="([^"]+)"',txt),'caption':(re.search(r'name="caption"\r\n\r\n([^\r]*)',txt) or [None,''])[1]}
    else:p=json.loads(raw or b'{}')
    if m=='getUpdates':
      try:res=[UPD.get(timeout=1)]
      except queue.Empty:res=[]
    else:
      with LOCK: CALLS.append((m,p));MID[0]+=1;mid=MID[0]
      res={'id':1,'username':'mayflowers_bot'} if m=='getMe' else ({'file_path':'voice/f.oga'} if m=='getFile' else ({'message_id':mid} if m.startswith('send') else True))
    b=json.dumps({'ok':True,'result':res}).encode();self.send_response(200);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
  def log_message(self,*a):pass
threading.Thread(target=ThreadingHTTPServer(('127.0.0.1',18999),Mock).serve_forever,daemon=True).start()
u=[0]
def msg(chat,text=None,**extra):
  u[0]+=1;m={'message_id':u[0],'chat':{'id':chat},'from':{'id':chat,'language_code':'ru'}}
  if text:m['text']=text
  m.update(extra);UPD.put({'update_id':u[0],'message':m})
def cb(chat,data):
  u[0]+=1;UPD.put({'update_id':u[0],'callback_query':{'id':str(u[0]),'data':data,'from':{'id':chat},'message':{'message_id':1,'chat':{'id':chat}}}})
def find(method,chat=None,sub=None,after=0):
  with LOCK: cs=CALLS[after:]
  for m,p in cs:
    if m==method and (chat is None or p.get('chat_id')==chat) and (sub is None or sub in json.dumps(p,ensure_ascii=False)):return p
def wait(f,t=10):
  e=time.time()+t
  while time.time()<e:
    r=f()
    if r:return r
    time.sleep(.1)
  raise SystemExit('TIMEOUT')
API='http://127.0.0.1:18081'
def http(path,data=None,headers=None,method=None):
  r=urllib.request.Request(API+path,data=data,headers=headers or {},method=method)
  try:
    with urllib.request.urlopen(r) as x:return x.status,dict(x.headers),x.read()
  except urllib.error.HTTPError as e:return e.code,dict(e.headers),e.read()
db=D+'recui.db'
for f in [db]:
  if os.path.exists(f):os.remove(f)
import shutil;shutil.rmtree(D+'cards',ignore_errors=True)
env=dict(os.environ,BOT_TOKEN='T',ADMIN_IDS='100',INTAKE_KEY=open(REPO+'/build.py').read().split('INTAKE_KEY = "')[1].split('"')[0],PORT='18081',DB_PATH=db,TELEGRAM_API='http://127.0.0.1:18999',WEBAPP_URL='https://arkedik23-boop.github.io/mayflowers/',PYTHONPATH=D+'stub')
bot=subprocess.Popen([sys.executable,REPO+'/bot/bot.py'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
def init_data(uid,token='T',lang='ru'):
  user=json.dumps({'id':uid,'first_name':'Ани','language_code':lang},separators=(',',':'),ensure_ascii=False)
  f={'user':user,'auth_date':str(int(time.time())),'query_id':'AAH'}
  chk='\n'.join(f'{k}={v}' for k,v in sorted(f.items()))
  sec=hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest()
  f['hash']=hmac.new(sec,chk.encode(),hashlib.sha256).hexdigest();return urllib.parse.urlencode(f)
ok=lambda c,t:print(('✔ ' if c else '✘ ')+t)
try:
  time.sleep(1.5)
  n=len(CALLS);msg(100,'/invite Роза');p=wait(lambda:find('sendMessage',100,'start=',n));code=re.search(r'start=(\S+)',p['text']).group(1);msg(201,'/start '+code);wait(lambda:find('sendMessage',201,'подключена'))
  web=subprocess.Popen([sys.executable,'-m','http.server','8767','-d',REPO],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);time.sleep(1)
  from playwright.sync_api import sync_playwright
  SH=WORK
  def fwd(route):
    rq=route.request;url=rq.url.replace('https://mayflowers.185-192-246-4.sslip.io',API)
    hd={k:v for k,v in rq.headers.items() if k.lower() in ('content-type','x-intake-key','x-telegram-init-data','x-order-id','x-manage','x-card-kind')}
    st,h,b=http(url[len(API):],rq.post_data_buffer if rq.method=='POST' else None,hd,rq.method)
    route.fulfill(status=st,headers={'Access-Control-Allow-Origin':'*','Content-Type':h.get('Content-Type','application/json')},body=b)
  with sync_playwright() as pw:
    br=pw.chromium.launch(args=['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
    ctx=br.new_context(viewport={'width':390,'height':844},device_scale_factor=2,permissions=['microphone','camera']);pg=ctx.new_page();errs=[]
    pg.on('pageerror',lambda e:errs.append(str(e)));ctx.route('https://mayflowers.185-192-246-4.sslip.io/**',fwd)
    pg.goto('http://127.0.0.1:8767/index.html');pg.wait_for_timeout(800)
    pg.evaluate("()=>{try{localStorage.setItem('may_promo_seen','x')}catch(e){};add(5);go('checkout')}")
    pg.fill('#f_phone','+37491112233');pg.fill('#f_addr','ул. Абовяна 12');pg.fill('#f_yphone','+37499000000')
    pg.evaluate("()=>{document.getElementById('more').open=true}");pg.check('#f_media');pg.wait_for_timeout(200)
    pg.click('[data-act=place]');pg.wait_for_selector('[data-act=recopen][data-k=voice]',timeout=6000);ok(True,'done view shows record buttons');pg.screenshot(path=SH+'r0.png')
    pg.click('[data-act=recopen][data-k=voice]');pg.wait_for_selector('#recHost [data-act=recstart]');pg.screenshot(path=SH+'r1.png')
    pg.click('[data-act=recstart]');pg.wait_for_selector('#rcTime',timeout=5000);pg.wait_for_timeout(2500);pg.screenshot(path=SH+'r2.png')
    pg.click('[data-act=recstop]');pg.wait_for_selector('#recHost audio.rc-play',timeout=5000);ok(True,'voice: review with player');pg.screenshot(path=SH+'r3.png')
    n=len(CALLS);pg.click('[data-act=recsend]');pg.wait_for_selector('#recHost',state='hidden',timeout=10000)
    wait(lambda:find('sendMessage',100,'записал поздравление на сайте (voice)',n),15);ok(True,'server got voice upload')
    pg.wait_for_selector('.cm:has-text("Поздравление записано")',timeout=5000);ok('голосовое' in pg.inner_text('.cm'),'done view: recorded voice');pg.screenshot(path=SH+'r4.png')
    pg.evaluate("()=>go('cabinet')");pg.wait_for_selector('[data-act=cmre]',timeout=6000);pg.click('[data-act=cmre]');pg.click('[data-act=recopen][data-k=video]')
    pg.click('[data-act=recstart]');pg.wait_for_selector('#rcCam',timeout=5000);pg.wait_for_timeout(2500);pg.screenshot(path=SH+'r5.png')
    pg.click('[data-act=recstop]');pg.wait_for_selector('#recHost video.rc-play',timeout=5000)
    n=len(CALLS);pg.click('[data-act=recsend]');pg.wait_for_selector('#recHost',state='hidden',timeout=15000);ok('обрабатывается' in pg.inner_text('.cm'),'video: processing shown')
    wait(lambda:find('sendMessage',100,'записал поздравление на сайте (video)',n),60);ok(True,'server transcoded video')
    pg.evaluate("()=>{Object.keys(MSTATE).forEach(k=>delete MSTATE[k]);render()}");pg.wait_for_selector('.cm:has-text("видео")',timeout=6000);ok('Поздравление записано · видео' in pg.inner_text('.cm'),'cabinet: recorded video')
    ok(not errs,'page errors: '+str(errs));br.close()
  web.terminate()
finally:
  bot.terminate();out=bot.communicate(timeout=5)[0];errs=[l for l in out.splitlines() if 'Traceback' in l or 'ERROR' in l or 'Exception' in l]
  print('bot errors:',errs[:5] or 'none')
