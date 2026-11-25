import json,threading,time,subprocess,os,sys,queue,urllib.parse,urllib.request,re,sqlite3
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
db=D+'card.db'
for f in [db]:
  if os.path.exists(f):os.remove(f)
import shutil;shutil.rmtree(D+'cards',ignore_errors=True)
env=dict(os.environ,BOT_TOKEN='T',ADMIN_IDS='100',INTAKE_KEY='k',PORT='18081',DB_PATH=db,TELEGRAM_API='http://127.0.0.1:18999',WEBAPP_URL='https://arkedik23-boop.github.io/mayflowers/',PYTHONPATH=D+'stub')
bot=subprocess.Popen([sys.executable,REPO+'/bot/bot.py'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
ok=lambda c,t:print(('✔ ' if c else '✘ ')+t)
try:
  time.sleep(1.5)
  n=len(CALLS);msg(100,'/invite Роза');p=wait(lambda:find('sendMessage',100,'start=',n));code=re.search(r'start=(\S+)',p['text']).group(1);msg(201,'/start '+code);wait(lambda:find('sendMessage',201,'подключена'))
  order={'items':[{'name':'Весна','qty':1,'price_usd':70}],'delivery':{'date':'2026-12-01','window':'asap'},'recipient':{'name':'Мама','phone':'1','address':'a'},'sender':{'name':'Анна','phone':'2','anonymous':False},'card':{'type':'media','text':'🎙 Аудио/видео-открытка'},'lang':'ru'}
  st,h,b=http('/api/orders',json.dumps(order).encode(),{'Content-Type':'application/json','X-Intake-Key':'k'});j=json.loads(b)
  ok(st==200 and j.get('record_link','').startswith('https://t.me/mayflowers_bot?start=rec_'),'site order returns record_link: '+j.get('record_link',''))
  oid=j['id'];rec=j['record_link'].split('start=')[1]
  adm=wait(lambda:find('sendMessage',100,'card.html?c='));token=re.search(r'card\.html\?c=([\w-]+)',adm['text']).group(1);ok(len(token)>=20,'admin got card link, token len %d'%len(token))
  stud=wait(lambda:find('sendMessage',201,oid));ok('QR-код пришлю после принятия' in stud['text'],'studio offer mentions QR card')
  st,h,b=http('/api/card/'+token);d=json.loads(b);ok(st==200 and d['status']=='pending' and d['from']=='Анна','card pending before recording: %s'%d)
  ok(http('/api/card/nope')[0]==404 and http('/api/card/'+token+'/media')[0]==404,'unknown token and missing media -> 404')
  n=len(CALLS);msg(555,'/start '+rec);a=wait(lambda:find('sendMessage',555,'Запишите поздравление',n));ok(True,'client deep link -> ask to record')
  n=len(CALLS);msg(555,voice={'file_id':'VOICE1','file_size':5000,'duration':2});s=wait(lambda:find('sendMessage',555,'Сохранил',n))
  btn=s['reply_markup']['inline_keyboard'][0][0];ok(btn.get('url','').endswith('card.html?c='+token+'&me=1'),'saved + url button to card page')
  st,h,b=http('/api/card/'+token);d=json.loads(b);ok(d['status']=='ready' and d['kind']=='voice','card ready, kind voice')
  n=len(CALLS);http('/api/card/'+token+'/media?preview=1');time.sleep(.4);ok(not find('sendMessage',555,'открыл',n),'sender preview does not count as opened')
  n=len(CALLS);st,h,b=http('/api/card/'+token+'/media');ok(st==200 and h.get('Content-Type')=='audio/mp4' and b[4:8]==b'ftyp','voice converted to m4a, %d bytes'%len(b))
  wait(lambda:find('sendMessage',555,'открыл ваше поздравление',n));ok(True,'sender notified: opened')
  st,h,b=http('/api/card/'+token+'/media',headers={'Range':'bytes=0-99'});ok(st==206 and len(b)==100 and h.get('Content-Range','').startswith('bytes 0-99/'),'range request 206')
  n=len(CALLS);http('/api/card/'+token+'/media');time.sleep(.5);ok(not find('sendMessage',555,'открыл',n),'opened notified only once')
  n=len(CALLS);cb(201,'acc:'+oid);qr=wait(lambda:find('sendPhoto',201,None,n));ok(qr.get('_multipart') and 'QR-код' in qr['caption'],'studio got QR photo on accept: '+str(qr['_files']))
  ok(bool(find('sendDocument',201,None,n)),'studio got QR file for print')
  n=len(CALLS);st,h,b=http('/api/card/'+token+'/reply',open(HERE+'media/reply.webm','rb').read(),{'Content-Type':'audio/webm;codecs=opus'},'POST');v=wait(lambda:find('sendVoice',555,None,n))
  ok(st==200 and v.get('_multipart') and 'Ответ на ваше поздравление' in v['caption'],'browser reply -> sendVoice to sender')
  ok(http('/api/card/'+token+'/reply',b'x',{'Content-Type':'text/plain'},'POST')[0]==415,'non-audio reply rejected')
  for i in range(5):http('/api/card/'+token+'/reply',open(HERE+'media/reply.webm','rb').read(),{'Content-Type':'audio/webm'},'POST')
  ok(http('/api/card/'+token+'/reply',open(HERE+'media/reply.webm','rb').read(),{'Content-Type':'audio/webm'},'POST')[0]==429,'reply rate limit')
  n=len(CALLS);msg(777,'/start '+rec);wait(lambda:find('sendMessage',777,'другому аккаунту',n));ok(True,'link cannot be hijacked by another account')
  # re-record then deliver then late
  n=len(CALLS);msg(555,video_note={'file_id':'VN2','file_size':9000});wait(lambda:find('sendMessage',555,'Сохранил',n));d=json.loads(http('/api/card/'+token)[2]);ok(d['kind']=='video_note','re-record replaces with video_note')
  cb(201,'photo:'+oid);time.sleep(.4);msg(201,photo=[{'file_id':'P'}]);time.sleep(.6);cb(201,'st:%s:courier'%oid);time.sleep(.4);cb(201,'st:%s:delivered'%oid);time.sleep(.6)
  n=len(CALLS);msg(555,voice={'file_id':'V3','file_size':10});wait(lambda:find('sendMessage',555,'уже доставлен',n));ok(True,'after delivery: cannot change')
  # mini-app style: plain order without media has no record_link
  st,h,b=http('/api/orders',json.dumps(dict(order,card={'type':'text','text':'hi'})).encode(),{'Content-Type':'application/json','X-Intake-Key':'k'});ok('record_link' not in json.loads(b),'text-card order has no record_link')
  st,h,b=http('/api/vip',json.dumps({'name':'Арк','phone':'+374','recipient':'Мама','date':'2026-12-20','comment':'юбилей','price_from_usd':1000}).encode(),{'Content-Type':'application/json','X-Intake-Key':'k'},'POST')
  v=wait(lambda:find('sendMessage',100,'Маис лично'));ok(st==200 and '20 декабря' in v['text'] and 'Мама' in v['text'],'vip request -> admin')
  ok(http('/api/vip',b'{"name":"a"}',{'Content-Type':'application/json','X-Intake-Key':'k'},'POST')[0]==422,'vip missing fields 422')
  ok(http('/api/vip',b'{"name":"a","phone":"1","recipient":"r"}',{'Content-Type':'application/json','X-Intake-Key':'bad'},'POST')[0]==401,'vip bad key 401')
finally:
  bot.terminate();out=bot.communicate(timeout=5)[0];errs=[l for l in out.splitlines() if 'Traceback' in l or 'ERROR' in l or 'Exception' in l]
  print('bot errors:',errs[:5] or 'none')
