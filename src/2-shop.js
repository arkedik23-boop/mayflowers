const REEL=document.createElement('video');
(()=>{const rm=!!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches);
  REEL.src='vid/mais.mp4';REEL.poster='vid/mais.jpg';REEL.muted=true;REEL.loop=true;REEL.playsInline=true;REEL.setAttribute('playsinline','');REEL.preload='metadata';REEL.autoplay=!rm;if(rm)REEL.controls=true})();
const S={vip:{open:false,status:'idle'},lang:'ru',mode:'site',view:'shop',cart:[],filter:'all',orders:[],last:null,draft:{},kind:false,ai:{q:'',status:'idle',reply:'',picks:[],card:'',local:false},pick:101,pq:5,rot:0,crTarget:null};
const LOC={ru:'ru-RU',en:'en-GB',hy:'hy-AM'};
const $=s=>document.querySelector(s);
const t=k=>T[S.lang][k];
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pn=p=>p.n[S.lang], pk=p=>p.k[S.lang];
const amd=u=>(Math.round(u*RATE/100)*100).toLocaleString(LOC[S.lang])+'\u00a0֏';
const usd=u=>'$'+u;
function load(){try{S.orders=JSON.parse(localStorage.getItem('may_orders')||'[]')}catch(e){S.orders=[]}}
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
  +'<p class="promo-price"><s class="nums">'+usd(p.usd)+' · '+amd(p.usd)+'</s><b class="nums">'+pr+'</b><small class="nums">'+amd(PROMO.usd)+'</small></p>'
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
  const list=PRODUCTS.filter(p=>!p.stem&&(S.filter==='all'||p.occ.includes(S.filter)));
  return '<section class="hero"><div><p class="label">'+t('hero_k')+'</p><h1><span class="h-serif">'+t('hero_t1')+'</span> <span class="h-sans">'+t('hero_t2')+'</span></h1><p class="lead">'+t('hero_s')+'</p><button class="btn primary" data-act="catalog">'+t('hero_cta')+'</button></div>'
  +'<figure class="gift"><div class="reel" id="reelSlot"><button type="button" class="snd" data-act="snd" aria-pressed="false">'+t('snd_on')+'</button></div><figcaption class="label">'+t('hero_vid')+'</figcaption></figure></section>'
  +promoBlock()
  +'<section class="ai" id="ai">'+aiInner()+'</section>'
  +'<ol class="steps"><li><span class="label">01</span><b>'+t('s1t')+'</b>'+t('s1d')+'</li><li><span class="label">02</span><b>'+t('s2t')+'</b>'+t('s2d')+'</li><li><span class="label">03</span><b>'+t('s3t')+'</b>'+t('s3d')+'</li></ol>'
  +'<section class="kind" id="kind"><div><p class="label">'+t('kind_k')+'</p><h2>'+t('kind_t')+'</h2></div><div><p>'+t('kind_d')+'</p><button class="btn'+(S.kind?' ink':'')+'" data-act="kind" aria-pressed="'+S.kind+'">'+(S.kind?t('kind_on'):t('kind_add'))+'</button></div></section>'
  +vipBlock()
  +'<div class="sec" id="catalog"><h2>'+t('cat_t')+'</h2><div class="tabs" role="group">'
  +['all'].concat(OCC).map(o=>'<button class="tab" data-act="filter" data-v="'+o+'" aria-pressed="'+(S.filter===o)+'">'+(o==='all'?t('f_all'):t('o_'+o))+'</button>').join('')+'</div></div>'
  +'<div class="grid">'+list.map(p=>'<article class="item"><div class="tintbox">'+art(p)+'</div><h3>'+esc(pn(p))+'</h3><p class="comp">'+esc(pk(p))+'</p>'
  +'<div class="buy"><span class="price">'+usd(p.usd)+'<small>'+amd(p.usd)+'</small></span><button class="btn sm" data-act="add" data-v="'+p.id+'">'+t('add')+'</button></div></article>').join('')+'</div>'
  +'<div class="custom"><div><h3>'+t('cu_t')+'</h3><p>'+t('cu_d')+'</p></div><button class="btn" data-act="mgr">'+t('cu_cta')+'</button></div>'}

/* smart assistant: asks Claude through the page's sample capability, falls back to keyword matching */
let SAMPLE=null,AI_CTL=null;
function aiInner(){const a=S.ai,busy=a.status==='loading';
  let res='';
  if(busy)res='<p class="ai-status" aria-live="polite">'+t('ai_load')+'</p>';
  else if(a.status==='done'){
    const ps=a.picks.map(x=>({p:PRODUCTS.find(p=>p.id===x.id),why:x.why})).filter(x=>x.p);
    res='<div class="ai-res" aria-live="polite">'+(a.reply?'<p class="ai-reply">'+esc(a.reply)+'</p>':'')
    +(ps.length?'<div class="ai-picks">'+ps.map(({p,why})=>'<article class="item"><div class="tintbox">'+art(p)+'</div><h3>'+esc(pn(p))+'</h3><p class="comp">'+esc(why||pk(p))+'</p><div class="buy"><span class="price">'+usd(p.usd)+'<small>'+amd(p.usd)+'</small></span><button class="btn sm" data-act="add" data-v="'+p.id+'">'+t('add')+'</button></div></article>').join('')+'</div>':'<p class="muted">'+t('ai_none')+'</p>')
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
  +'<p class="vip-price"><span>'+t('vip_from')+'</span> <b class="nums">$'+VIP.from.toLocaleString('en-US')+'</b></p>'
  +'<ul class="vip-li">'+li.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>'+act+'<p class="note">'+t('vip_note')+'</p></div>'
  +'<figure class="vip-media">'+media+'</figure></div></section>'}
