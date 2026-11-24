const REEL=document.createElement('video');
(()=>{const rm=!!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches);
  REEL.src='vid/hero.mp4';REEL.poster='vid/hero.jpg';REEL.muted=true;REEL.loop=true;REEL.playsInline=true;REEL.setAttribute('playsinline','');REEL.preload='metadata';REEL.autoplay=!rm})();
const S={cur:null,fOpen:false,f:{min:0,max:null,fl:[],col:[],fmt:[],mais:false,sort:'pop'},vip:{open:false,status:'idle'},lang:'ru',mode:'site',view:'shop',cart:[],filter:'all',orders:[],last:null,draft:{},kind:false,ai:{q:'',status:'idle',reply:'',picks:[],card:'',local:false},pick:101,pq:5,rot:0,crTarget:null};
const LOC={ru:'ru-RU',en:'en-GB',hy:'hy-AM'};
const $=s=>document.querySelector(s);
const t=k=>T[S.lang][k];
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pn=p=>p.n[S.lang], pk=p=>p.k[S.lang];
const amd=u=>(Math.round(u*RATE/100)*100).toLocaleString(LOC[S.lang])+'\u00a0֏';
/* валюта показа: ru → ₽, hy → ֏, en → $, пока клиент не выбрал сам */
const curNow=()=>S.cur||CUR_BY_LANG[S.lang]||'usd';
const usd=u=>{const c=curNow();if(c==='rub')return (Math.round(u*RUB_RATE/10)*10).toLocaleString(LOC[S.lang])+'\u00a0₽';if(c==='amd')return (Math.round(u*RATE/100)*100).toLocaleString(LOC[S.lang])+'\u00a0֏';return '$'+Number(u).toLocaleString('en-US')};
const usdRaw=u=>'$'+u;
function load(){try{S.orders=JSON.parse(localStorage.getItem('may_orders')||'[]')}catch(e){S.orders=[]}try{const c=localStorage.getItem('may_cur');if(['rub','amd','usd'].includes(c))S.cur=c}catch(e){}}
function save(){try{localStorage.setItem('may_orders',JSON.stringify(S.orders))}catch(e){}}
function ymd(d){return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')}
function fdate(s){const [y,m,d]=s.split('-').map(Number);return new Date(y,m-1,d).toLocaleDateString(LOC[S.lang],{day:'numeric',month:'long',year:'numeric'})}
function nextYear(s){const [y,m,d]=s.split('-').map(Number);return ymd(new Date(y+1,m-1,d))}
function toast(m){const h=$('#toastHost');h.innerHTML='<div class="toast">'+esc(m)+'</div>';setTimeout(()=>{h.innerHTML=''},2200)}
function calLink(o){const d=nextYear(o.date).replace(/-/g,'');const e=ymd(new Date(+d.slice(0,4),+d.slice(4,6)-1,+d.slice(6,8)+1)).replace(/-/g,'');
  const title='May Flowers: '+(o.rec||'')+' ('+t('o_'+o.occ)+')';
  return 'https://calendar.google.com/calendar/render?action=TEMPLATE&text='+encodeURIComponent(title)+'&dates='+d+'/'+e+'&details='+encodeURIComponent('Заказать цветы / Order flowers / Պատվիրել ծաղիկներ')}
function art(p,eager){return '<img src="'+p.img+'" alt="'+esc(pn(p))+'" width="720" height="900"'+(eager?'':' loading="lazy"')+' decoding="async">'}
/* bouquet of the day: active until local midnight */
const promoEnd=()=>{const d=new Date();d.setHours(23,59,59,999);return d};
const promoOn=()=>!!(PROMO&&PRODUCTS.find(p=>p.id===PROMO.id))&&Date.now()<promoEnd().getTime();
const priceOf=c=>c.promo&&promoOn()&&c.id===PROMO.id?PROMO.usd:PRODUCTS.find(p=>p.id===c.id).usd;
const cartSum=()=>S.cart.reduce((a,c)=>a+priceOf(c)*c.q,0);
const cartCount=()=>S.cart.reduce((a,c)=>a+c.q,0);
function add(id,promo){promo=!!promo;const c=S.cart.find(x=>x.id===id&&!!x.promo===promo);c?c.q++:S.cart.push(promo?{id,q:1,promo:true}:{id,q:1});chrome();toast(t('add')+': '+pn(PRODUCTS.find(p=>p.id===id)))}
function promoLeft(){const ms=Math.max(0,promoEnd()-Date.now()),h=Math.floor(ms/36e5),m=Math.floor(ms%36e5/6e4);return t('pr_left').replace('{t}',(h?h+'\u00a0'+t('pr_h')+' ':'')+m+'\u00a0'+t('pr_m'))}
function promoBlock(){if(!promoOn())return '';const p=PRODUCTS.find(x=>x.id===PROMO.id),pr=usd(PROMO.usd);
  return '<section class="promo" id="promo" aria-labelledby="promoT"><div class="tintbox">'+art(p)+'<span class="promo-tag">\u2212'+Math.round((1-PROMO.usd/p.usd)*100)+'%</span></div><div class="promo-body"><p class="label">'+t('pr_k')+' · <span id="promoLeft" class="nums">'+promoLeft()+'</span></p><h2 id="promoT">'+esc(pn(p))+'</h2><p class="comp">'+esc(pk(p))+'</p>'
  +'<p class="promo-price"><s class="nums">'+usd(p.usd)+'</s><b class="nums">'+pr+'</b></p>'
  +'<button class="btn primary" data-act="promo">'+t('pr_btn').replace('{p}',pr)+'</button><p class="note">'+t('pr_note')+'</p></div></section>'}
setInterval(()=>{const el=document.getElementById('promoLeft');if(!el)return;if(!promoOn()){if(S.view==='shop')render();return}el.textContent=promoLeft()},30000);
function marquee(){const s=('<span>'+esc(t('rib'))+'</span>').repeat(3);return '<div class="marq" role="marquee" aria-label="'+esc(t('rib'))+'"><div class="marq-track" aria-hidden="true">'+s+s+'</div></div>'}
function fridge(){
  const st=PRODUCTS.filter(p=>p.stem);
  const ring='<div class="stage-scroll" id="stageScroll"><div class="stage" id="stage">'+st.map((p,k)=>'<button type="button" class="cr-item'+(S.pick===p.id?' on':'')+'" data-act="pick" data-v="'+p.id+'" data-k="'+k+'" aria-pressed="'+(S.pick===p.id)+'"><span class="cr-img"><img src="'+p.img+'" alt="" width="360" height="500" decoding="async" draggable="false"></span><span class="stem-name">'+esc(pn(p))+'</span></button>').join('')+'</div></div>';
  return '<section class="fridge'+(S.pick?' has-pick':'')+'" id="fridge"><div class="fridge-in"><div class="fridge-head"><div><p class="label">'+t('fr_k')+'</p><h1>'+t('hero_t')+'</h1></div><div><p class="lead">'+t('fr_s')+'</p><button class="btn ghost-w" data-act="catalog">'+t('fr_ready')+'</button></div></div>'
  +'<div class="case">'+ring+'</div><div class="pick" id="pickPanel" aria-live="polite">'+pickPanel()+'</div></div></section>'}
function pickPanel(){const p=PRODUCTS.find(x=>x.id===S.pick);if(!p)return '<p class="hint">'+t('fr_hint')+'</p>';
  return '<div class="pick-name"><span class="label">'+t('fr_sel')+'</span><b>'+esc(pn(p))+'</b></div>'
  +'<div class="qty"><button type="button" data-act="pq" data-v="-1" aria-label="'+t('less')+'">−</button><span class="nums">'+S.pq+'</span><button type="button" data-act="pq" data-v="1" aria-label="'+t('more')+'">+</button></div>'
  +'<button class="btn primary" data-act="addstem">'+t('fr_add')+' · '+usd(p.usd*S.pq)+'</button>'}
function shopView(){
  return '<section class="hero hero-full"><div class="hero-bg" id="reelSlot"><div class="hero-shade"></div></div>'
  +'<div class="hero-in"><p class="label">'+t('hero_k')+'</p><h1><span class="h-serif">'+t('hero_t1')+'</span> <span class="h-sans">'+t('hero_t2')+'</span></h1><p class="lead">'+t('hero_s')+'</p><button class="btn primary" data-act="catalog">'+t('hero_cta')+'</button></div>'
  +'<div class="hero-foot"><span class="label">'+t('hero_vid')+'</span></div></section>'
  +promoBlock()
  +'<section class="ai" id="ai">'+aiInner()+'</section>'
  +'<section class="kind" id="kind"><div><p class="label">'+t('kind_k')+'</p><h2>'+t('kind_t')+'</h2></div><div><p>'+t('kind_d')+'</p><button class="btn'+(S.kind?' ink':'')+'" data-act="kind" aria-pressed="'+S.kind+'">'+(S.kind?t('kind_on'):t('kind_add'))+'</button></div></section>'
  +vipBlock()
  +catalogBlock()
  +'<div class="custom"><div><h3>'+t('cu_t')+'</h3><p>'+t('cu_d')+'</p></div><button class="btn" data-act="mgr">'+t('cu_cta')+'</button></div>'}

/* smart assistant: asks Claude through the page's sample capability, falls back to keyword matching */
let SAMPLE=null,AI_CTL=null;
function aiInner(){const a=S.ai,busy=a.status==='loading';
  let res='';
  if(busy)res='<p class="ai-status" aria-live="polite">'+t('ai_load')+'</p>';
  else if(a.status==='done'){
    const ps=a.picks.map(x=>({p:PRODUCTS.find(p=>p.id===x.id),why:x.why})).filter(x=>x.p);
    res='<div class="ai-res" aria-live="polite">'+(a.reply?'<p class="ai-reply">'+esc(a.reply)+'</p>':'')
    +(ps.length?'<div class="ai-picks">'+ps.map(({p,why})=>'<article class="item"><div class="tintbox">'+art(p)+'</div><h3>'+esc(pn(p))+'</h3><p class="comp">'+esc(why||pk(p))+'</p><div class="buy"><span class="price">'+usd(p.usd)+'</span><button class="btn sm" data-act="add" data-v="'+p.id+'">'+t('add')+'</button></div></article>').join('')+'</div>':'<p class="muted">'+t('ai_none')+'</p>')
    +(a.card?'<div class="ai-card"><span class="label">'+t('ai_card')+'</span><p>«'+esc(a.card)+'»</p><button class="btn sm" data-act="aicard">'+t('ai_use')+'</button></div>':'')
    +(a.local?'<p class="note">'+t('ai_local')+'</p>':'')+'</div>'}
  else if(a.status==='error')res='<p class="err">'+esc(a.err||'')+'</p>';
  return '<div class="ai-head"><div><p class="label">'+t('ai_k')+'</p><h2>'+t('ai_t')+'</h2></div><p class="ai-d">'+t('ai_d')+'</p></div>'
  +'<form class="ai-form" id="aiForm"><label class="sr" for="ai_q">'+t('ai_k')+'</label><textarea id="ai_q" rows="2" placeholder="'+esc(t('ai_ph'))+'">'+esc(a.q)+'</textarea>'
  +'<button class="btn primary" type="submit"'+(busy?' hidden':'')+'>'+t('ai_btn')+'</button><button class="btn" type="button" data-act="aistop"'+(busy?'':' hidden')+'>'+t('ai_stop')+'</button></form>'
  +'<div class="tabs ai-ex">'+['ai_ex1','ai_ex2','ai_ex3'].map(k=>'<button type="button" class="tab" data-act="aiex" data-v="'+k+'">'+t(k)+'</button>').join('')+'</div>'+res}
function aiPaint(){const el=document.getElementById('ai');if(!el)return;const f=document.activeElement&&document.activeElement.id==='ai_q';el.innerHTML=aiInner();if(f){const q=document.getElementById('ai_q');q.focus();q.setSelectionRange(q.value.length,q.value.length)}}
function aiLocal(q){const s=q.toLowerCase();const occ={mom:/мам|mom|mother|մայր/,love:/люб|девушк|жен[аеуы]|любим|romant|love|girlfriend|wife|սեր|աղջ|կին/,bd:/рожд|юбил|birthday|anniversar|ծնունդ|ծննդ|ամյակ/,thanks:/спасиб|благодар|коллег|учител|thank|colleague|teacher|շնորհակալ|գործընկեր/,sorry:/прост|извин|sorry|apolog|ներող/};
  const kw=[[/бел|white|սպիտակ/,[2,7,12,18]],[/красн|red|կարմիր/,[10,19,11]],[/розов|pink|нежн|վարդագույն/,[5,9,16,20]],[/пион|peon|քաջվարդ/,[5,20,16]],[/сух|dried|չոր/,[6,13]],[/подсолн|sunflower|արևածաղ/,[4,14]],[/тюльпан|tulip|կակաչ/,[9,15]],[/лили|lil|շուշան/,[18,7]],[/орхид|orchid|խոլորձ/,[11,12,19,1]],[/роз|rose|վարդ/,[10,19,2]],[/полев|wild|դաշտ/,[8]],[/коробк|box|տուփ/,[13,16,20,19]],[/экзот|тропи|exotic|tropic/,[1,17]],[/дорог|роскош|премиум|luxur|premium/,[11,12,19]]];
  let budget=null;const bm=s.match(/(?:до|не дороже|не больше|бюджет|up to|under|max|budget|մինչև)\s*\$?\s*(\d[\d\s]{0,7})\s*(драм|amd|֏|դրամ)?/)||s.match(/\$\s*(\d[\d\s]{0,7})()/)||s.match(/(\d[\d\s]{0,7})\s*(\$|usd|долл|драм|amd|֏|դրամ)/);
  if(bm){let n=+bm[1].replace(/\s/g,'');if((bm[2]&&/драм|amd|֏|դրամ/.test(bm[2]))||n>2500)n=n/RATE;if(n>=15)budget=n}
  const sc=PRODUCTS.filter(p=>!p.stem).map(p=>{let v=0;for(const o in occ)if(occ[o].test(s)&&p.occ.includes(o))v+=3;for(const [r,ids] of kw)if(r.test(s)&&ids.includes(p.id))v+=2;if(budget&&p.usd>budget)v-=100;return{p,v}}).filter(x=>x.v>0).sort((a,b)=>b.v-a.v||a.p.usd-b.p.usd).slice(0,3);
  return{reply:'',picks:sc.map(x=>({id:x.p.id,why:pk(x.p)})),card:'',local:true}}
async function aiAsk(){const q=(S.ai.q||'').trim();if(!q){toast(t('ai_empty'));return}
  S.ai.status='loading';aiPaint();
  if(SAMPLE){AI_CTL=new AbortController();
    const cat=PRODUCTS.filter(p=>!p.stem).map(p=>({id:p.id,name:pn(p),composition:pk(p),price_usd:p.usd,occasions:p.occ.map(o=>t('o_'+o))}));
    const prompt='Ты флорист-консультант цветочного сервиса May Flowers в Ереване. Покупатель написал:\n"""'+q.slice(0,600)+'"""\n\nКаталог (JSON, цены в долларах США):\n'+JSON.stringify(cat)
      +'\n\nПодбери до 3 букетов ТОЛЬКО из этого каталога по поводу, получателю, вкусам и бюджету. Если бюджет указан, не превышай его. Если запрос не про цветы или подарок, верни пустой picks и вежливо скажи, что помогаешь только с цветами.'
      +'\nПиши на '+t('ai_lang')+' языке, тепло и коротко.'
      +'\nОтветь только JSON: {"reply":"1–2 предложения","picks":[{"id":число из каталога,"why":"почему подходит, до 15 слов"}],"card":"текст открытки на 1–2 предложения или пустая строка"}';
    try{const r=await SAMPLE.json(prompt,{modelTier:'quick',signal:AI_CTL.signal});
      const ok=new Set(PRODUCTS.filter(p=>!p.stem).map(p=>p.id));
      const picks=Array.isArray(r&&r.picks)?r.picks.map(x=>({id:Number(x&&x.id),why:String((x&&x.why)||'')})).filter(x=>ok.has(x.id)).slice(0,3):[];
      S.ai=Object.assign(S.ai,{status:'done',reply:String((r&&r.reply)||''),picks,card:String((r&&r.card)||''),local:false});aiPaint();return}
    catch(e){const code=e&&e.code;if(code==='cancelled'){S.ai.status='idle';aiPaint();return}
      if(['not_granted','sampling_disabled','not_declared','capability_disabled','capability_removed'].includes(code))SAMPLE=null}}
  if(ORDER_API.url){AI_CTL=new AbortController();
    try{const r=await fetch(ORDER_API.url.replace(/\/$/,'')+'/api/ai',{method:'POST',signal:AI_CTL.signal,headers:TG?{'Content-Type':'application/json','X-Telegram-Init-Data':TG.initData}:{'Content-Type':'application/json','X-Intake-Key':ORDER_API.key},body:JSON.stringify({q:q.slice(0,600),lang:S.lang})});
      if(r.ok){const d=await r.json(),ok=new Set(PRODUCTS.filter(p=>!p.stem).map(p=>p.id));
        S.ai=Object.assign(S.ai,{status:'done',reply:String(d.reply||''),picks:(d.picks||[]).filter(x=>ok.has(+x.id)).map(x=>({id:+x.id,why:String(x.why||'')})).slice(0,3),card:String(d.card||''),local:false});aiPaint();return}}
    catch(e){if(e&&e.name==='AbortError'){S.ai.status='idle';aiPaint();return}}}
  S.ai=Object.assign(S.ai,{status:'done'},aiLocal(q));aiPaint()}
(async()=>{try{if(window.claude&&typeof claude.use==='function')SAMPLE=await claude.use('sample')}catch(e){SAMPLE=null}})();

/* «Маис лично»: премиум-вручение от $1000, только по заявке */
function vipBlock(){const v=S.vip,li=t('vip_li');
  const media=VIP.video?'<video src="'+esc(VIP.video)+'" poster="vid/mais.jpg" controls playsinline preload="none"></video>':'<img src="vid/mais.jpg" alt="" loading="lazy" decoding="async"><span class="vip-soon">'+t('vip_vid')+'</span>';
  let act;
  if(v.status==='ok')act='<p class="vip-ok" role="status">'+t('vip_ok')+'</p>';
  else if(v.open)act='<form class="vip-form" id="vipForm" novalidate><div class="fields">'
    +fld('v_name',t('co_yname'),S.draft.f_you||'','autocomplete="name" aria-required="true"')+fld('v_phone',t('co_yphone'),S.draft.f_yphone||'','type="tel" inputmode="tel" autocomplete="tel" aria-required="true"')
    +fld('v_rec',t('vip_rec'),'','aria-required="true"')+fld('v_date',t('vip_date'),'','type="date" min="'+ymd(new Date())+'"')
    +'<label class="full">'+t('vip_com')+'<textarea id="v_com" placeholder="'+esc(t('vip_com_ph'))+'"></textarea></label></div>'
    +(v.status==='err'?'<p class="err" role="alert" style="margin-top:12px">'+t('vip_fail')+'</p>':'')
    +'<button class="btn primary" type="submit" style="margin-top:16px"'+(v.status==='sending'?' disabled':'')+'>'+t('vip_send')+'</button></form>';
  else act='<button class="btn primary" type="button" data-act="vip">'+t('vip_btn')+'</button>';
  return '<section class="vip" id="vip" aria-labelledby="vipT"><div class="vip-in"><div class="vip-body"><p class="label">'+t('vip_k')+'</p>'
  +'<h2 id="vipT"><span class="h-serif">'+t('vip_t1')+'</span> '+t('vip_t2')+'</h2><p class="vip-d">'+t('vip_d')+'</p>'
  +'<p class="vip-price"><span>'+t('vip_from')+'</span> <b class="nums">'+usd(VIP.from)+'</b></p>'
  +'<ul class="vip-li">'+li.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>'+act+'<p class="note">'+t('vip_note')+'</p></div>'
  +'<figure class="vip-media">'+media+'</figure></div></section>'}

/* ---------- каталог: поводы плитками, фильтры, сортировка, валюта ---------- */
const OCC_TILES=[['all',5],['bd',3],['love',10],['mom',20],['thanks',8],['sorry',7],['premium',12]];
const PMAX=()=>Math.max(...PRODUCTS.filter(p=>!p.stem).map(p=>p.usd));
function itemCard(p){return '<article class="item"><div class="tintbox">'+art(p)+(p.mais?'<span class="mais-tag">'+t('f_mais')+'</span>':'')+'</div><h3>'+esc(pn(p))+'</h3><p class="comp">'+esc(pk(p))+'</p>'
  +'<div class="buy"><span class="price nums">'+usd(p.usd)+'</span><button class="btn sm" data-act="add" data-v="'+p.id+'">'+t('add')+'</button></div></article>'}
function fList(){const f=S.f,mx=f.max==null?Infinity:f.max;
  let l=PRODUCTS.filter(p=>!p.stem&&(S.filter==='all'||(S.filter==='premium'?p.usd>=150:p.occ.includes(S.filter)))&&p.usd>=f.min&&p.usd<=mx
    &&(!f.fl.length||f.fl.some(x=>p.fl.includes(x)))&&(!f.col.length||f.col.some(x=>p.col.includes(x)))&&(!f.fmt.length||f.fmt.includes(p.fmt))&&(!f.mais||p.mais));
  if(f.sort==='cheap')l.sort((a,b)=>a.usd-b.usd);else if(f.sort==='exp')l.sort((a,b)=>b.usd-a.usd);else l.sort((a,b)=>(b.mais-a.mais)||(a.id-b.id));
  return l}
function fCount(){const f=S.f;return f.fl.length+f.col.length+f.fmt.length+(f.mais?1:0)+((f.min>0||f.max!=null)?1:0)}
function priceLabel(){const f=S.f;return f.max==null?(f.min>0?t('f_from')+' '+usd(f.min):''):(f.min>0?usd(f.min)+' – '+usd(f.max):t('f_to')+' '+usd(f.max))}
function fChips(){const f=S.f,c=[];
  if(f.min>0||f.max!=null)c.push(['price','',priceLabel()]);
  f.fl.forEach(v=>c.push(['fl',v,t('fl_'+v)]));f.col.forEach(v=>c.push(['col',v,t('col_'+v)]));f.fmt.forEach(v=>c.push(['fmt',v,t('fmt_'+v)]));
  if(f.mais)c.push(['mais','',t('f_mais')]);
  return c.map(([k,v,l])=>'<button type="button" class="chip on" data-act="fchip" data-k="'+k+'" data-v="'+v+'" aria-label="'+esc(t('f_reset'))+': '+esc(l)+'">'+esc(l)+' <span aria-hidden="true">×</span></button>').join('')
    +(c.length?'<button type="button" class="chip ghost" data-act="freset">'+t('f_reset')+'</button>':'')}
function curSwitch(){return '<div class="cur-sw" role="group" aria-label="'+t('cur_t')+'">'+[['rub','₽'],['amd','֏'],['usd','$']].map(([c,s])=>'<button type="button" data-act="cur" data-v="'+c+'" aria-pressed="'+(curNow()===c)+'" aria-label="'+c.toUpperCase()+'">'+s+'</button>').join('')+'</div>'}
function fPanel(){const f=S.f,mx=PMAX(),hi=f.max==null?mx:f.max;
  const tg=(k,arr,lab,extra)=>'<button type="button" class="chip" data-act="ftog" data-k="'+k+'" data-v="'+arr+'" aria-pressed="'+f[k].includes(arr)+'">'+(extra||'')+lab+'</button>';
  return '<div class="f-head"><b>'+t('f_btn')+'</b><button type="button" class="burger sm" data-act="fopen" aria-label="'+t('f_close')+'"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button></div>'
  +'<fieldset><legend>'+t('pr_t')+' · <span id="fPriceLbl">'+(priceLabel()||usd(0)+' – '+usd(mx))+'</span></legend>'
  +'<div class="range"><span class="track"></span><span class="fill" id="fFill"></span><input type="range" id="f_min" min="0" max="'+mx+'" step="5" value="'+f.min+'" aria-label="'+t('pr_t')+', '+t('f_from')+'"><input type="range" id="f_max" min="0" max="'+mx+'" step="5" value="'+hi+'" aria-label="'+t('pr_t')+', '+t('f_to')+'"></div>'
  +'<div class="f-row">'+[[0,50],[50,100],[100,200],[200,null]].map(([a,b])=>'<button type="button" class="chip" data-act="fprice" data-v="'+a+'-'+(b==null?'':b)+'" aria-pressed="'+(f.min===a&&f.max===b)+'">'+(b==null?t('f_from')+' '+usd(a):a?usd(a)+' – '+usd(b):t('f_to')+' '+usd(b))+'</button>').join('')+'</div></fieldset>'
  +'<fieldset><legend>'+t('fl_t')+'</legend><div class="f-row">'+FLOWERS.map(v=>tg('fl',v,t('fl_'+v))).join('')+'</div></fieldset>'
  +'<fieldset><legend>'+t('col_t')+'</legend><div class="f-row">'+Object.keys(COLORS).map(v=>tg('col',v,t('col_'+v),'<span class="dot" style="background:'+COLORS[v]+'"></span>')).join('')+'</div></fieldset>'
  +'<fieldset><legend>'+t('fmt_t')+'</legend><div class="f-row">'+FORMATS.map(v=>tg('fmt',v,t('fmt_'+v))).join('')+'<button type="button" class="chip" data-act="fmais" aria-pressed="'+f.mais+'">★ '+t('f_mais')+'</button></div></fieldset>'
  +'<div class="f-foot"><button type="button" class="btn primary" data-act="fopen" id="fShow">'+t('f_show')+' · '+fList().length+'</button><button type="button" class="btn" data-act="freset">'+t('f_reset')+'</button></div>'}
function catalogBlock(){const l=fList(),n=fCount();
  return '<div class="sec" id="catalog"><h2>'+t('cat_t')+'</h2></div>'
  +'<div class="occ-row" role="group" aria-label="'+t('cat_t')+'">'+OCC_TILES.map(([o,img])=>{const p=PRODUCTS.find(x=>x.id===img);
    return '<button type="button" class="occ" data-act="occ" data-v="'+o+'" aria-pressed="'+(S.filter===o)+'"><img src="'+p.img+'" alt="" loading="lazy" width="112" height="112"><span>'+(o==='all'?t('f_all'):o==='premium'?t('f_prem'):t('o_'+o))+'</span></button>'}).join('')+'</div>'
  +'<div class="cat-bar"><button type="button" class="btn sm" data-act="fopen" aria-expanded="'+S.fOpen+'" aria-controls="filters" id="fBtn">'+t('f_btn')+(n?' · '+n:'')+'</button>'
  +'<label class="sr" for="f_sort">'+t('sort_t')+'</label><select id="f_sort">'+[['pop','so_pop'],['cheap','so_cheap'],['exp','so_exp']].map(([v,k])=>'<option value="'+v+'"'+(S.f.sort===v?' selected':'')+'>'+t(k)+'</option>').join('')+'</select>'+curSwitch()+'</div>'
  +'<div class="f-chips" id="fChips">'+fChips()+'</div>'
  +(S.fOpen?'<div class="f-bg" data-act="fopen"></div>':'')+'<div class="filters" id="filters"'+(S.fOpen?'':' hidden')+'>'+(S.fOpen?fPanel():'')+'</div>'
  +'<p class="note f-count" id="fCount" aria-live="polite">'+t('f_found').replace('{n}',l.length)+(curNow()==='rub'?' · '+t('rub_note'):'')+'</p>'
  +'<div class="grid" id="grid">'+(l.length?l.map(itemCard).join(''):'')+'</div>'+(l.length?'':'<p class="muted f-empty">'+t('f_none')+'</p>')}
function catPaint(keepPanel){const c=document.getElementById('catalog');if(!c)return;
  const y=window.scrollY;const wrap=document.createElement('div');wrap.innerHTML=catalogBlock();
  /* заменяем всё от заголовка каталога до блока «Особый заказ» */
  let el=c;const parent=c.parentNode,stop=parent.querySelector('.custom');const old=[];
  while(el&&el!==stop){old.push(el);el=el.nextSibling}
  const focusId=document.activeElement&&document.activeElement.id,focusAct=document.activeElement&&document.activeElement.dataset&&(document.activeElement.dataset.act+'|'+(document.activeElement.dataset.k||'')+'|'+(document.activeElement.dataset.v||''));
  old.forEach(x=>x.remove());while(wrap.firstChild)parent.insertBefore(wrap.firstChild,stop);
  window.scrollTo(0,y);
  if(focusId&&document.getElementById(focusId))document.getElementById(focusId).focus({preventScroll:true});
  else if(focusAct){const [a,k,v]=focusAct.split('|');const b=document.querySelector('[data-act="'+a+'"]'+(k?'[data-k="'+k+'"]':'')+(v?'[data-v="'+v+'"]':''));if(b)b.focus({preventScroll:true})}
  fFill();document.body.classList.toggle('f-on',S.fOpen&&matchMedia('(max-width:720px)').matches)}
function fFill(){const a=document.getElementById('f_min'),b=document.getElementById('f_max'),fill=document.getElementById('fFill');if(!a||!fill)return;
  const mx=+a.max,lo=Math.min(+a.value,+b.value),hi=Math.max(+a.value,+b.value);fill.style.left=(lo/mx*100)+'%';fill.style.width=((hi-lo)/mx*100)+'%'}
