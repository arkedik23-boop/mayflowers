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
db=D+'cabadd.db'
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
  st,h,b=http('/api/orders',json.dumps(order).encode(),dict(J,**{'X-Intake-Key':'k'}));j=json.loads(b);oid=j['id']
  ok(st==200 and len(j.get('manage',''))>=12 and 'record_link' not in j,'site order without card returns manage code')
  P=lambda path,d,hd=None:http(path,json.dumps(d).encode(),dict(J,**(hd or {})),'POST')
  ok(P('/api/card/state',{'order_id':oid,'manage':'wrong'})[0]==404,'wrong manage -> 404')
  ok(P('/api/card/add',{'order_id':oid})[0]==404,'no manage -> 404')
  st,h,b=P('/api/card/state',{'order_id':oid,'manage':j['manage']});d=json.loads(b);ok(st==200 and d['media'] is None,'state: no card yet')
  # studio accepts first, then client adds card from cabinet
  wait(lambda:find('sendMessage',201,oid));n=len(CALLS);cb(201,'acc:'+oid);time.sleep(.6)
  ok(not find('sendPhoto',201,None,n),'no QR on accept for text-only order')
  n=len(CALLS);st,h,b=P('/api/card/add',{'order_id':oid,'manage':j['manage']});d=json.loads(b)
  ok(st==200 and d['media']['record_link'].startswith('https://t.me/mayflowers_bot?start=rec_') and not d['media']['recorded'],'add -> record_link, not recorded')
  sm=wait(lambda:find('sendMessage',201,'добавил аудио',n));ok('Мама, люблю' in sm['text'],'studio told card added, text kept')
  wait(lambda:find('sendPhoto',201,None,n));ok(True,'studio got QR after add')
  wait(lambda:find('sendMessage',100,'добавил аудио/видео-открытку',n));ok(True,'admin notified')
  st,h,b=P('/api/card/add',{'order_id':oid,'manage':j['manage']});d2=json.loads(b);ok(d2['media']['record_link']==d['media']['record_link'],'second add returns same card (idempotent)')
  n=len(CALLS);time.sleep(.4);ok(not find('sendPhoto',201,None,n),'no duplicate QR')
  rec=d['media']['record_link'].split('start=')[1]
  n=len(CALLS);msg(555,'/start '+rec);wait(lambda:find('sendMessage',555,'Запишите',n))
  n=len(CALLS);msg(555,voice={'file_id':'V1','file_size':100});wait(lambda:find('sendMessage',555,'Сохранил',n))
  st,h,b=P('/api/card/state',{'order_id':oid,'manage':j['manage']});d=json.loads(b);ok(d['media']['recorded'] and d['media']['kind']=='voice' and '&me=1' in d['media']['listen'],'state: recorded voice, listen link')
  # mini-app order: tg auth
  st,h,b=http('/api/orders',json.dumps(order).encode(),dict(J,**{'X-Telegram-Init-Data':init_data(700)}));j2=json.loads(b);o2=j2['id'];ok('manage' not in j2,'tg order: no manage code')
  ok(P('/api/card/add',{'order_id':o2},{'X-Telegram-Init-Data':init_data(701)})[0]==404,'other tg user -> 404')
  st,h,b=P('/api/card/add',{'order_id':o2},{'X-Telegram-Init-Data':init_data(700)});d=json.loads(b);ok(st==200 and d['media']['record_link'],'owner tg add ok')
  st,h,b=http('/api/me',headers={'X-Telegram-Init-Data':init_data(700)});me=json.loads(b);oo=[x for x in me['orders'] if x['id']==o2][0]
  ok(oo['media'] and oo['media']['recorded'] is False and oo['card']['type']=='media' and oo['card']['text']=='Мама, люблю','cabinet shows media card, text kept in payload')
  n=len(CALLS);msg(700,'/start '+d['media']['record_link'].split('start=')[1]);wait(lambda:find('sendMessage',700,'Запишите',n));ok(True,'owner deep link works')
  # delivered -> late
  cb(201,'acc:'+o2);time.sleep(.5);cb(201,'photo:'+o2);time.sleep(.3);msg(201,photo=[{'file_id':'P'}]);time.sleep(.5);cb(201,'st:%s:courier'%o2);time.sleep(.3);cb(201,'st:%s:delivered'%o2);time.sleep(.5)
  st,h,b=http('/api/orders',json.dumps(order).encode(),dict(J,**{'X-Telegram-Init-Data':init_data(700)}));o3=json.loads(b)['id']
  q=sqlite3.connect(db);q.execute("UPDATE orders SET status='delivered' WHERE id=?",(o3,));q.commit();q.close()
  ok(P('/api/card/add',{'order_id':o3},{'X-Telegram-Init-Data':init_data(700)})[0]==409,'delivered order -> 409 late')
finally:
  bot.terminate();out=bot.communicate(timeout=5)[0];errs=[l for l in out.splitlines() if 'Traceback' in l or 'ERROR' in l or 'Exception' in l]
  print('bot errors:',errs[:5] or 'none')
