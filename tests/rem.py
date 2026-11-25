import json,time,os,sys,subprocess,re
import os as _os
HERE=_os.path.dirname(_os.path.abspath(__file__))+'/'
REPO=_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
WORK=HERE+'_work/';_os.makedirs(WORK,exist_ok=True)
from datetime import date,timedelta
exec(open(HERE+'card.py').read().split("db=D+'card.db'")[0])
db=D+'rem.db'
if os.path.exists(db):os.remove(db)
env=dict(os.environ,BOT_TOKEN='T',ADMIN_IDS='100',INTAKE_KEY='k',PORT='18081',DB_PATH=db,TELEGRAM_API='http://127.0.0.1:18999',WEBAPP_URL='https://arkedik23-boop.github.io/mayflowers/',REMIND_HOUR='0',REMIND_EVERY='2',TZ_OFFSET='0')
bot=subprocess.Popen([sys.executable,REPO+'/bot/bot.py'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
ok=lambda c,t:print(('✔ ' if c else '✘ ')+t)
try:
  time.sleep(1.5)
  d3=(date.today()-timedelta(days=365)+timedelta(days=3))
  # last year: if leap-year shift ever mismatched, adjust to same month/day
  d3=date(date.today().year-1,(date.today()+timedelta(days=3)).month,(date.today()+timedelta(days=3)).day).isoformat()
  o={'items':[{'name':'Пионовое облако','qty':1,'price_usd':110,'sku':5}],'delivery':{'date':d3,'window':'asap'},'recipient':{'name':'Мама','phone':'1','address':'a'},'occasion':'bd','remind':True,'lang':'ru'}
  st,h,b=http('/api/orders',json.dumps(o).encode(),{'Content-Type':'application/json','X-Intake-Key':'k'},'POST');j=json.loads(b)
  ok(j.get('remind_link','').startswith('https://t.me/mayflowers_bot?start=rem_'),'site order returns remind_link')
  n=len(CALLS);msg(555,'/start '+j['remind_link'].split('start=')[1]);on=wait(lambda:find('sendMessage',555,'Напомню',n));print('  ',on['text'])
  r=wait(lambda:find('sendMessage',555,'Через 3 дня',n),15);print('  ',r['text']);btns=[b[0]['text'] for b in r['reply_markup']['inline_keyboard']]
  ok('для мамы' in r['text'] and 'Пионовое облако' in r['text'] and btns==['🔁 Повторить тот же букет','💐 Выбрать букет'],'3-day reminder text + buttons')
  ok('add=5' in r['reply_markup']['inline_keyboard'][0][0]['web_app']['url'],'repeat button opens same bouquet')
  time.sleep(5);ok(sum(1 for m,p in CALLS if m=='sendMessage' and p.get('chat_id')==555 and 'Через 3 дня' in p.get('text',''))==1,'sent only once')
  t1=date.today()+timedelta(days=1);d1=date(date.today().year-1,t1.month,t1.day).isoformat()
  n=len(CALLS);st,h,b=http('/api/orders',json.dumps(dict(o,delivery={'date':d1,'window':'asap'},recipient={'name':'Анна','phone':'1','address':'a'},occasion='love')).encode(),{'Content-Type':'application/json','X-Intake-Key':'k'},'POST');j=json.loads(b)
  msg(556,'/start '+j['remind_link'].split('start=')[1]);r=wait(lambda:find('sendMessage',556,'Завтра',n),15);print('  ',r['text'])
  ok('Анна' in r['text'],'day-before reminder')
  n=len(CALLS);msg(557,'/start rem_bad');wait(lambda:find('sendMessage',557,'не найдена',n));ok(True,'bad link handled')
finally:
  bot.terminate();out=bot.communicate(timeout=5)[0];print('bot errors:',[l for l in out.splitlines() if 'Traceback' in l or 'ERROR' in l][:5] or 'none')
