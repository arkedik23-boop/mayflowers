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
db=D+'cabup.db'
for f in [db]:
  if os.path.exists(f):os.remove(f)
import shutil;shutil.rmtree(D+'cards',ignore_errors=True)
env=dict(os.environ,BOT_TOKEN='T',ADMIN_IDS='100',INTAKE_KEY='k',PORT='18081',DB_PATH=db,TELEGRAM_API='http://127.0.0.1:18999',WEBAPP_URL='https://arkedik23-boop.github.io/mayflowers/',PYTHONPATH=D+'stub')
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
  order={'items':[{'name':'Весна','qty':1,'price_usd':70}],'delivery':{'date':'2026-12-01','window':'asap'},'recipient':{'name':'Мама','phone':'1','address':'a'},'sender':{'name':'Анна','phone':'2','anonymous':False},'card':{'type':'text','text':'Мама, люблю'},'lang':'ru'}
  J={'Content-Type':'application/json'}
  st,h,b=http('/api/orders',json.dumps(order).encode(),dict(J,**{'X-Intake-Key':'k'}));j=json.loads(b);oid=j['id'];mg=j['manage']
  wait(lambda:find('sendMessage',201,oid));cb(201,'acc:'+oid);time.sleep(.5)
  U=lambda f,ct,kind,man=mg,o=oid:http('/api/card/upload',open(HERE+'media/'+f,'rb').read() if isinstance(f,str) else f,{'Content-Type':ct,'X-Order-Id':o,'X-Manage':man,'X-Card-Kind':kind},'POST')
  ok(U('reply.webm','audio/webm;codecs=opus','voice',man='bad')[0]==404,'upload wrong manage -> 404')
  ok(U(b'x'*2000,'text/plain','voice')[0]==415,'non-media -> 415')
  ok(U(b'x'*500,'audio/webm','voice')[0]==413,'tiny -> 413')
  n=len(CALLS);st,h,b=U('reply.webm','audio/webm;codecs=opus','voice');d=json.loads(b)
  ok(st==200 and d['media']['recorded'] and d['media']['kind']=='voice' and d['processing'] is False,'chrome webm voice -> recorded voice immediately')
  wait(lambda:find('sendPhoto',201,None,n));ok(True,'studio got QR (card created by upload)')
  tok=re.search(r'c=([\w-]+)',d['media']['listen']).group(1)
  st,h,b=http('/api/card/'+tok+'/media?preview=1');ok(st==200 and h.get('Content-Type')=='audio/mp4' and b[4:8]==b'ftyp','served as m4a (%d bytes)'%len(b))
  ok(json.loads(http('/api/card/'+tok)[2])['status']=='ready','card page: ready')
  st,h,b=U(b'\x00'*5000,'audio/webm','voice');ok(st==422,'garbage audio -> 422')
  st,h,b=U('web_voice.m4a','audio/mp4','voice');ok(st==200 and json.loads(b)['media']['recorded'],'safari m4a voice ok')
  # video webm -> processing -> mp4
  st,h,b=U('web_video.webm','video/webm;codecs=vp8,opus','video');d=json.loads(b);ok(st==200 and d['processing'] is True and d['media']['processing'],'video webm -> processing')
  wait(lambda:find('sendMessage',100,'записал поздравление на сайте (video)'),30)
  P=lambda d:http('/api/card/state',json.dumps(d).encode(),J,'POST')
  s2=json.loads(P({'order_id':oid,'manage':mg})[2]);ok(s2['media']['kind']=='video' and not s2['media']['processing'],'state after processing: video ready')
  st,h,b=http('/api/card/'+tok+'/media?preview=1');ok(st==200 and h.get('Content-Type')=='video/mp4','served as mp4 (%d bytes)'%len(b))
  pr=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_name','-of','csv=p=0','-'],input=b,capture_output=True).stdout.decode().split();ok('h264' in pr and 'aac' in pr,'transcoded to h264+aac: '+str(pr))
  st,h,b=U('web_video.mp4','video/mp4','video');ok(st==200,'iphone mp4 accepted');time.sleep(3)
  # telegram re-record still works after local
  # delivered -> late
  q=sqlite3.connect(db);q.execute("UPDATE orders SET status='delivered' WHERE id=?",(oid,));q.commit();q.close()
  ok(U('reply.webm','audio/webm','voice')[0]==409,'delivered -> 409')
  ok(len(os.listdir(D+'cards'))<=4,'raw files cleaned: '+str(os.listdir(D+'cards')))
finally:
  bot.terminate();out=bot.communicate(timeout=5)[0];errs=[l for l in out.splitlines() if 'Traceback' in l or 'ERROR' in l or 'Exception' in l]
  print('bot errors:',errs[:5] or 'none')
