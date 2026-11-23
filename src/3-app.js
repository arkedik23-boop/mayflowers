let MENU_OPEN=false;
/* demo controls (studio bot preview, site/mini-app switch): only in the mock-up or with ?demo=1, never on the live shop */
const DEMO_UI=!ORDER_API.url||/[?&]demo=1\b/.test(location.search);
const FIELDS=['f_sign','f_paper','f_ribbon','f_com','f_rec','f_phone','f_addr','f_date','f_win','f_exact','f_occ','f_text','f_tone','f_you','f_yphone'];
function grab(){if(!$('#f_you'))return;FIELDS.forEach(k=>{const e=$('#'+k);if(e)S.draft[k]=e.value});
  ['f_anon','f_rem','f_pub'].forEach(k=>{const e=$('#'+k);if(e)S.draft[k]=e.checked});
  const to=document.querySelector('input[name=to]:checked');if(to)S.kind=to.value==='kind';
  const c=document.querySelector('input[name=card]:checked');if(c)S.draft.card=c.value;
  const p=document.querySelector('input[name=pay]:checked');if(p)S.draft.pay=p.value}
const dv=(k,d)=>S.draft[k]!==undefined?S.draft[k]:d;
const fld=(id,label,val,extra)=>'<label>'+label+'<input id="'+id+'" aria-describedby="e_'+id+'" '+(extra||'')+' value="'+esc(val)+'"><span class="err" id="e_'+id+'" data-e="'+id+'"></span></label>';
function emptyBox(msg,act,lbl){return '<div class="empty"><span>'+msg+'</span>'+(act?'<button class="btn" data-act="'+act+'">'+lbl+'</button>':'')+'</div>'}
function checkoutView(){
  if(!S.cart.length)return emptyBox(t('co_empty'),'shop',t('back'));
  const sub=cartSum(),tot=sub+DELIV,K=S.kind,card=dv('card','none'),win=dv('f_win','asap'),today=ymd(new Date());
  const items=S.cart.map(c=>{const p=PRODUCTS.find(x=>x.id===c.id),key=p.id+(c.promo?'p':'');return '<div class="line"><span>'+esc(pn(p))+(c.promo?' <span class="tagp">'+t('pr_tag')+'</span>':'')+'</span><span class="qty"><button type="button" data-act="dec" data-v="'+key+'" aria-label="'+t('less')+': '+esc(pn(p))+'">−</button>'+c.q+'<button type="button" data-act="inc" data-v="'+key+'" aria-label="'+t('more')+': '+esc(pn(p))+'">+</button></span><b class="nums">'+usd(priceOf(c)*c.q)+'</b></div>'}).join('');
  return '<h2 style="font-size:clamp(32px,6vw,56px);letter-spacing:-.04em;margin-bottom:32px">'+t('co_t')+'</h2>'
  +'<section class="blk"><span class="label">'+t('co_sub')+'</span>'+items+'<div class="line"><span>'+t('co_deliv')+'</span><b class="nums">'+usd(DELIV)+'</b></div></section>'
  +'<section class="blk"><span class="label">'+t('to_l')+'</span><div class="opts"><label><input type="radio" name="to" value="person"'+(K?'':' checked')+'>'+t('to_person')+'</label><label><input type="radio" name="to" value="kind"'+(K?' checked':'')+'>'+t('to_kind')+'</label></div></section>'
  +(K?'<section class="blk kindblk"><span class="label">'+t('kind_k')+'</span><div class="fields"><div class="full">'+fld('f_sign',t('co_sign'),dv('f_sign',''),'placeholder="'+esc(t('co_sign_ph'))+'" maxlength="40" aria-required="true"')+'</div></div>'
  +'<label class="check" style="margin-top:8px"><input type="checkbox" id="f_pub"'+(dv('f_pub',true)?' checked':'')+'>'+t('co_pub')+'</label><p class="note" style="margin-top:8px">'+t('co_kind_d')+'</p></section>':'')
  +(K?'':'<section class="blk"><span class="label">'+t('co_rec')+'</span><div class="fields">'
  +fld('f_rec',t('co_rec'),dv('f_rec',''),'autocomplete="off" aria-required="true"')+fld('f_phone',t('co_phone'),dv('f_phone',''),'type="tel" inputmode="tel" placeholder="+374" aria-required="true"')
  +'<div class="full">'+fld('f_addr',t('co_addr'),dv('f_addr',''),'autocomplete="street-address" aria-required="true"')+'</div>'
  +'<label>'+t('co_date')+'<input id="f_date" type="date" min="'+today+'" aria-describedby="e_f_date" value="'+esc(dv('f_date',today))+'"><span class="err" id="e_f_date" data-e="f_date"></span></label>'
  +'<label>'+t('co_win')+'<select id="f_win"><option value="asap"'+(win==='asap'?' selected':'')+'>'+t('win_asap')+'</option>'+WINDOWS.map(w=>'<option'+(win===w?' selected':'')+'>'+w+'</option>').join('')+'<option value="exact"'+(win==='exact'?' selected':'')+'>'+t('win_exact')+'</option></select></label>'
  +(win==='exact'?'<label>'+t('win_exact')+'<input id="f_exact" type="time" value="'+esc(dv('f_exact','12:00'))+'"></label>':'')
  +'<label>'+t('co_occ')+'<select id="f_occ">'+OCC.map(o=>'<option value="'+o+'"'+(dv('f_occ','bd')===o?' selected':'')+'>'+t('o_'+o)+'</option>').join('')+'</select></label></div></section>')
  +'<section class="blk"><span class="label">'+t('co_wrap')+'</span><div class="fields"><label>'+t('co_paper')+'<select id="f_paper">'+t('papers').map((x,i)=>'<option value="'+i+'"'+(+dv('f_paper',0)===i?' selected':'')+'>'+esc(x)+'</option>').join('')+'</select></label>'
  +'<label>'+t('co_ribbon')+'<select id="f_ribbon">'+t('ribbons').map((x,i)=>'<option value="'+i+'"'+(+dv('f_ribbon',0)===i?' selected':'')+'>'+esc(x)+'</option>').join('')+'</select></label>'
  +'<label class="full">'+t('co_com')+'<textarea id="f_com" placeholder="'+esc(t('co_com_ph'))+'">'+esc(dv('f_com',''))+'</textarea></label></div></section>'
  +(K?'':'<section class="blk"><span class="label">'+t('co_card')+'</span><div class="opts"><label><input type="radio" name="card" value="none"'+(card==='none'?' checked':'')+'>'+t('card_none')+'</label><label><input type="radio" name="card" value="text"'+(card==='text'?' checked':'')+'>'+t('card_text')+'</label><label><input type="radio" name="card" value="media"'+(card==='media'?' checked':'')+'>'+t('card_media')+'</label></div>'+(card==='media'?'<p class="note" style="margin-top:8px">'+t('card_media_d')+'</p>':'')
  +(card==='text'?'<div class="fields" style="margin-top:16px"><label class="full">'+t('co_card_text')+'<textarea id="f_text">'+esc(dv('f_text',''))+'</textarea></label>'
  +'<label>'+t('co_ai')+'<select id="f_tone">'+['ai_warm','ai_fun','ai_form'].map((k,i)=>'<option value="'+k+'"'+(dv('f_tone','ai_warm')===k?' selected':'')+'>'+t(['tone_warm','tone_fun','tone_form'][i])+'</option>').join('')+'</select></label>'
  +'<div style="align-self:end"><button type="button" class="btn" data-act="ai">'+t('co_ai')+'</button></div></div>':'')
  +'<label class="check" style="margin-top:8px"><input type="checkbox" id="f_anon"'+(dv('f_anon',false)?' checked':'')+'>'+t('co_anon')+'</label></section>')
  +'<section class="blk"><span class="label">'+t('co_you')+'</span><div class="fields">'+fld('f_you',t('co_yname'),dv('f_you',''),'autocomplete="name" aria-required="true"')+fld('f_yphone',t('co_yphone'),dv('f_yphone',''),'type="tel" inputmode="tel" autocomplete="tel" aria-required="true"')+'</div></section>'
  +'<section class="blk"><span class="label">'+t('co_pay')+'</span><div class="opts">'+PAYS.map(x=>'<label><input type="radio" name="pay" value="'+esc(x)+'"'+((dv('pay',PAYS[0])===x)?' checked':'')+'>'+esc(x)+'</label>').join('')+'</div><p class="note" style="margin-top:8px">'+t('pay_note')+'</p></section>'
  +(K?'':'<section class="blk"><label class="check"><input type="checkbox" id="f_rem"'+(dv('f_rem',true)?' checked':'')+'>'+t('co_rem')+'</label><p class="note" style="margin-left:36px">'+t('co_remwhen')+'</p></section>')
  +'<section class="blk"><div class="line"><span>'+t('co_sub')+'</span><b class="nums">'+usd(sub)+'</b></div><div class="line"><span>'+t('co_deliv')+'</span><b class="nums">'+usd(DELIV)+'</b></div>'
  +'<div class="line t"><span>'+t('co_total')+'</span><span class="tot">'+usd(tot)+(curNow()!=='usd'?' <small class="note">$'+tot+'</small>':'')+'</span></div>'+(curNow()==='rub'?'<p class="note" style="margin-top:8px">'+t('rub_note')+'</p>':'')
  +'<button class="btn primary" style="width:100%;margin-top:16px" data-act="place">'+t('co_place')+' · '+usd(tot)+'</button></section>'}
function place(){
  grab();const d=S.draft,K=S.kind,req=K?['f_sign','f_you','f_yphone']:['f_rec','f_phone','f_addr','f_date','f_you','f_yphone'];let bad=0;
  req.forEach(k=>{const e=$('#'+k),m=document.querySelector('[data-e='+k+']'),ok=e&&String(e.value).trim();
    if(e)e.setAttribute('aria-invalid',ok?'false':'true');if(m)m.textContent=ok?'':t('req');if(!ok)bad++});
  if(bad){const f=document.querySelector('[aria-invalid=true]');if(f)f.focus();return}
  const sub=cartSum(),sign=K?d.f_sign.trim():'',o={id:'MF-'+(1000+S.orders.length+1),items:S.cart.map(c=>({id:c.id,q:c.q,usd:priceOf(c),promo:!!c.promo})),total:sub+DELIV,kind:K,sign,pub:K&&d.f_pub!==false,
    date:K?ymd(new Date()):d.f_date,win:K?'asap':(d.f_win||'asap'),exact:K?'':(d.f_exact||''),rec:K?t('kind_rec'):d.f_rec.trim(),phone:K?d.f_yphone.trim():d.f_phone.trim(),addr:K?t('kind_addr'):d.f_addr.trim(),
    occ:K?'thanks':(d.f_occ||'bd'),card:K?'text':(d.card||'none'),text:K?t('sign_card').replace('{n}',sign):(d.card==='text'?(d.f_text||''):''),anon:K?false:!!d.f_anon,you:d.f_you.trim(),yphone:d.f_yphone.trim(),pay:d.pay||PAYS[0],remind:K?false:d.f_rem!==false,status:0,ts:Date.now(),paper:+(d.f_paper||0),ribbon:+(d.f_ribbon||0),com:(d.f_com||'').trim()};
  sendToBot(o);if(TG)S.me=null;
  S.recLink=null;S.remLink=null;S.orders.unshift(o);save();S.last=o.id;S.cart=[];S.draft={};S.kind=false;S.view='done';render();window.scrollTo(0,0)}
function doneView(){const o=S.orders.find(x=>x.id===S.last);if(!o)return '';
  return '<div class="done"><span class="label nums">'+esc(o.id)+'</span><h2>'+t('ok_t')+'</h2><p>'+t('ok_d')+'</p><div class="acts">'
  +'<button class="btn primary" data-act="cabinet">'+t('ok_cab')+'</button>'
  +(o.remind&&!TG&&S.remLink?'<a class="btn primary" target="_blank" rel="noopener" href="'+esc(S.remLink)+'">'+t('ok_rem')+'</a>':'')+(o.remind?'<a class="btn" target="_blank" rel="noopener" href="'+calLink(o)+'">'+t('ok_cal')+'</a>':'')
  +(DEMO_UI?'<button class="btn" data-act="studio">'+t('nav_studio')+'</button>':'')+'</div>'
  +(o.card==='media'?'<div class="blk" style="margin-top:32px"><span class="label">'+t('card_media')+'</span>'+(TG?'<p>'+t('ok_rec_tg')+'</p>':(S.recLink?'<a class="btn primary" target="_blank" rel="noopener" href="'+esc(S.recLink)+'">'+t('ok_rec')+'</a>':'<p class="note">'+t('card_media_d')+'</p>'))+'</div>':'')+'</div>'}
function itemsText(o){return o.items.map(i=>{const p=PRODUCTS.find(x=>x.id===i.id);return pn(p)+' × '+i.q}).join(', ')}
function whenText(o){return fdate(o.date)+', '+(o.win==='asap'?t('win_asap'):o.win==='exact'?o.exact:o.win)}
function h2(s){return '<h2 style="font-size:clamp(32px,6vw,56px);letter-spacing:-.04em;margin-bottom:32px">'+s+'</h2>'}
function cabinetView(){
  if(TG&&ORDER_API.url)return srvCabinet();
  const rem=S.orders.filter(o=>o.remind),book={};S.orders.forEach(o=>{if(!o.kind)book[o.rec+o.addr]=o});
  const ol=S.orders.length?S.orders.map(o=>'<div class="ord"><div class="h"><b class="nums">'+esc(o.id)+' · '+usd(o.total)+'</b><span class="label" style="'+(o.status===5?'color:var(--ink)':'')+'">'+T[S.lang].st[o.status]+'</span></div>'
    +'<div class="muted">'+esc(itemsText(o))+'<br>'+esc(o.rec)+' · '+esc(o.addr)+'<br>'+esc(whenText(o))+(o.kind?'<br>'+t('cab_kind'):'')+'</div><div class="prog" aria-hidden="true">'+[0,1,2,3,4,5].map(i=>'<i class="'+(i<=o.status?'on':'')+'"></i>').join('')+'</div>'
    +'<button class="btn sm" data-act="reorder" data-v="'+esc(o.id)+'">'+t('reorder')+'</button></div>').join(''):emptyBox(t('cab_none'),'shop',t('back'));
  const rl=rem.length?rem.map(o=>'<div class="ord"><div class="h"><b>'+fdate(nextYear(o.date))+'</b><span class="label">'+t('o_'+o.occ)+'</span></div><div class="muted">'+esc(o.rec)+'</div><div class="acts"><a class="btn sm" target="_blank" rel="noopener" href="'+calLink(o)+'">'+t('to_cal')+'</a><button class="btn sm" data-act="reorder" data-v="'+esc(o.id)+'">'+t('reorder')+'</button></div></div>').join(''):'<p class="muted ord">'+t('cab_none')+'</p>';
  const bl=Object.values(book).length?Object.values(book).map(o=>'<div class="line"><span><b>'+esc(o.rec)+'</b><br><span class="muted">'+esc(o.addr)+'</span></span><span class="muted nums">'+esc(o.phone)+'</span></div>').join(''):'<p class="muted ord">'+t('cab_none')+'</p>';
  return h2(t('cab_t'))+(TG?'':'<p class="note" style="margin:-16px 0 24px">'+t('cab_local')+'</p>')+bonusBlock(S.orders.map(o=>({usd:o.total,ts:o.ts,done:o.status===5})))+'<section class="blk"><span class="label">'+t('cab_orders')+'</span>'+ol+'</section><section class="blk"><span class="label">'+t('cab_rem')+'</span>'+rl+'</section><section class="blk"><span class="label">'+t('cab_book')+'</span>'+bl+'</section>'}
const BTN=['b_acc','b_bui','b_pho','b_cou','b_don'];
function studioView(){
  const o=S.orders.find(x=>x.id===S.last)||S.orders[0];
  const head=h2(t('bot_t'))+'<p class="lead">'+t('bot_hint')+'</p>';
  if(!o)return head+emptyBox(t('bot_none'),'shop',t('back'));
  const m=t('msg_new')+' '+o.id+'\n\n'+t('m_it')+': '+itemsText(o)+'\n'+t('m_rec')+': '+o.rec+'\n'+t('m_ph')+': '+o.phone+'\n'+t('m_ad')+': '+o.addr+'\n'+t('m_wh')+': '+whenText(o)+'\n'+t('m_ca')+': '+(o.card==='text'?'«'+o.text+'»':o.card==='media'?t('m_media'):t('nocard'))+(o.anon?' ('+t('anon')+')':'')+'\n'+t('m_wrap')+': '+t('papers')[o.paper||0]+', '+t('ribbons')[o.ribbon||0]+(o.com?'\n'+t('m_com')+': '+o.com:'')+'\n'+t('m_sum')+': '+usdRaw(Math.round((o.total-DELIV)*0.7))+(o.kind?'\n'+t('m_kind'):'')+'\n\n'+T[S.lang].st[o.status];
  return head+'<div class="tg-win"><span class="label">May Flowers · Studio bot</span><div class="msg">'+esc(m)+'</div><div class="kb">'+BTN.map((b,i)=>'<button data-act="adv" data-v="'+o.id+'|'+i+'"'+(o.status===i?'':' disabled')+'>'+t(b)+'</button>').join('')+'</div></div><p class="note" style="margin-top:16px;max-width:480px">'+t('bot_rule')+'</p>'}
function render(){
  const L=T[S.lang];document.documentElement.lang=S.lang;
  document.querySelectorAll('[data-i]').forEach(e=>{e.textContent=L[e.dataset.i]});
  $('#burgerLbl').textContent=L.mn_open;$('#burger').setAttribute('aria-label',L.mn_open);if(MENU_OPEN)$('#menu').innerHTML=menuInner();
  document.body.classList.toggle('tg',S.mode==='tg');
  $('#cartBtn').textContent=L.cart+' · '+cartCount();
  if(S._tl!==S.lang){S._tl=S.lang;$('#tickHost').innerHTML=marquee()}
  const v={shop:shopView,checkout:checkoutView,cabinet:cabinetView,studio:studioView,done:doneView}[S.view];
  $('#main').innerHTML='<div class="view">'+v()+'</div>';
  crLayout();crCenter();reelMount();fFill();
  chrome();
}
function chrome(){const L=T[S.lang];$('#cartBtn').textContent=L.cart+' · '+cartCount();
  const n=cartCount();$('#stickyHost').innerHTML=(S.view==='shop'&&n&&!TG)?'<div class="sticky"><button class="btn ink" data-act="checkout">'+L.cart+' · '+n+' · '+usd(cartSum())+'</button></div>':'';tgSync();
}
function go(v){grab();S.view=v;render();window.scrollTo(0,0)}
document.addEventListener('click',e=>{const b=e.target.closest('[data-act],[data-view],[data-lang],[data-mode],[data-nav],#logo,#cartBtn,#burger');if(!b)return;
  if(b.id==='logo'){menuClose(true);return go('shop')}if(b.id==='cartBtn'){menuClose(true);return go(cartCount()?'checkout':'shop')}
  if(b.dataset.view){menuClose(true);return go(b.dataset.view)}
  if(b.dataset.lang){grab();S.lang=b.dataset.lang;return render()}
  if(b.id==='burger')return MENU_OPEN?menuClose():menuOpen();
  if(b.dataset.nav){menuClose(true);return navTo(b.dataset.nav)}
  if(b.dataset.mode){S.mode=b.dataset.mode;menuClose(true);return render()}
  if(b.dataset.view&&MENU_OPEN)menuClose(true);
  const a=b.dataset.act,v=b.dataset.v;
  if(a==='add')add(+v);else if(a==='filter'||a==='occ'){S.filter=v;catPaint()}
  else if(a==='fopen'){S.fOpen=!S.fOpen;catPaint();if(S.fOpen){const f=document.querySelector('#filters .chip,#filters input');if(f)f.focus({preventScroll:true})}else{const fb=$('#fBtn');if(fb)fb.focus({preventScroll:true})}}
  else if(a==='ftog'){const k=b.dataset.k,arr=S.f[k],i=arr.indexOf(v);i<0?arr.push(v):arr.splice(i,1);catPaint()}
  else if(a==='fmais'){S.f.mais=!S.f.mais;catPaint()}
  else if(a==='fprice'){const [lo,hi]=v.split('-');S.f.min=+lo;S.f.max=hi===''?null:+hi;catPaint()}
  else if(a==='freset'){S.f={min:0,max:null,fl:[],col:[],fmt:[],mais:false,sort:S.f.sort};catPaint()}
  else if(a==='fchip'){const k=b.dataset.k;if(k==='price'){S.f.min=0;S.f.max=null}else if(k==='mais')S.f.mais=false;else S.f[k]=S.f[k].filter(x=>x!==v);catPaint()}
  else if(a==='cur'){S.cur=v;try{localStorage.setItem('may_cur',v)}catch(e){}const y=window.scrollY;render();window.scrollTo(0,y);if(MENU_OPEN)$('#menu').innerHTML=menuInner()}
  else if(a==='catalog'){const c=$('#catalog');if(c)c.scrollIntoView({behavior:'smooth'})}
  else if(a==='mgr'){menuClose(true);toast(t('mgr'))}
  else if(a==='menuclose')menuClose();
  else if(a==='vip'){S.vip.open=true;render();const f=$('#v_name');if(f){f.focus({preventScroll:true});$('#vip').scrollIntoView({behavior:'smooth',block:'start'})}}
  else if(a==='checkout'||a==='cabinet'||a==='studio'||a==='shop')go(a);
  else if(a==='inc'||a==='dec'){grab();const pr=/p$/.test(v),c=S.cart.find(x=>x.id===parseInt(v)&&!!x.promo===pr);if(c){c.q+=a==='inc'?1:-1;if(c.q<1)S.cart=S.cart.filter(x=>x!==c)}render()}
  else if(a==='ai'){grab();const n=(S.draft.f_rec||'').trim();S.draft.f_text=t(S.draft.f_tone||'ai_warm').replace('{n}',n||'').replace(/^[,\s]+/,'');render()}
  else if(a==='place')place();
  else if(a==='mereload'){meLoad()}
  else if(a==='srvre'){const o=(S.me&&S.me.data&&S.me.data.orders||[]).find(x=>x.id===v);if(o){S.cart=o.items.map(i=>({id:+i.sku||(PRODUCTS.find(p=>p.n.ru===i.name)||{}).id,q:+i.qty||1})).filter(i=>i.id);S.draft={f_rec:o.recipient.name||'',f_phone:o.recipient.phone||'',f_addr:o.recipient.address||'',f_occ:o.occasion||'bd'};go('checkout')}}
  else if(a==='remdel'){meApi('/api/reminders/delete',{method:'POST',body:JSON.stringify({id:+v})}).then(meLoad).catch(()=>toast(t('cab_err')))}
  else if(a==='snd'){REEL.muted=!REEL.muted;if(!REEL.muted)REEL.play().catch(()=>{});reelBtn()}
  else if(a==='aiex'){S.ai.q=t(v);aiAsk()}
  else if(a==='aistop'){if(AI_CTL)AI_CTL.abort()}
  else if(a==='aicard'){S.draft.card='text';S.draft.f_text=S.ai.card;toast(t('ai_used'))}
  else if(a==='pick'){crSelect(+v)}
  else if(a==='pq'){S.pq=Math.max(1,Math.min(101,S.pq+(+v)));$('#pickPanel').innerHTML=pickPanel()}
  else if(a==='addstem'){const p=PRODUCTS.find(x=>x.id===S.pick);if(p){const c=S.cart.find(x=>x.id===p.id);c?c.q+=S.pq:S.cart.push({id:p.id,q:S.pq});chrome();toast(pn(p)+' × '+S.pq)}}
  else if(a==='kind'){S.kind=!S.kind;render();if(S.kind){toast(t('kind_toast'));const c=$('#catalog');if(c)c.scrollIntoView({behavior:'smooth'})}}
  else if(a==='promo'){if(promoOn())add(PROMO.id,true)}
  else if(a==='reorder'){const o=S.orders.find(x=>x.id===v);if(o){S.cart=o.items.map(i=>({id:i.id,q:i.q}));S.draft={f_rec:o.rec,f_phone:o.phone,f_addr:o.addr,f_occ:o.occ,f_you:o.you,f_yphone:o.yphone};go('checkout')}}
  else if(a==='adv'){const [id,i]=v.split('|'),o=S.orders.find(x=>x.id===id);if(o&&o.status===+i){o.status=+i+1;save();render();toast(T[S.lang].st[o.status])}}
});
document.addEventListener('submit',e=>{if(e.target.id==='aiForm'){e.preventDefault();aiAsk()}else if(e.target.id==='vipForm'){e.preventDefault();sendVip()}});
document.addEventListener('input',e=>{if(e.target.id==='ai_q')S.ai.q=e.target.value;
  else if(e.target.id==='f_min'||e.target.id==='f_max'){const a=+$('#f_min').value,b=+$('#f_max').value,mx=+$('#f_max').max;S.f.min=Math.min(a,b);S.f.max=Math.max(a,b)>=mx?null:Math.max(a,b);fFill();
    const l=$('#fPriceLbl');if(l)l.textContent=priceLabel()||usd(0)+' – '+usd(mx);clearTimeout(S._ft);S._ft=setTimeout(()=>catPaint(),120)}});
document.addEventListener('change',e=>{if(e.target.id==='f_sort'){S.f.sort=e.target.value;catPaint()}});
document.addEventListener('keydown',e=>{if(e.target.id==='ai_q'&&e.key==='Enter'&&!e.shiftKey){e.preventDefault();aiAsk()}});
document.addEventListener('change',e=>{if(S.view!=='checkout')return;const id=e.target.id,nm=e.target.name;if(nm==='card'||nm==='to'||id==='f_win'){grab();render()}});
load();render();
if(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches){new MutationObserver(()=>document.querySelectorAll('animateTransform').forEach(x=>x.remove())).observe(document.body,{childList:true,subtree:true});document.querySelectorAll('animateTransform').forEach(x=>x.remove())}

/* static semicircle: centre flowers lowest and largest, edges smaller and higher */
function crSelect(id){S.pick=id;document.querySelectorAll('.cr-item').forEach(x=>{const on=+x.dataset.v===id;x.classList.toggle('on',on);x.setAttribute('aria-pressed',String(on))});
  crLayout();const f=$('#fridge');if(f)f.classList.add('has-pick');const pp=$('#pickPanel');if(pp)pp.innerHTML=pickPanel()}
function crLayout(){const items=document.querySelectorAll('.cr-item');if(!items.length)return;const st=$('#stage'),w=st.clientWidth,n=items.length,iw=items[0].offsetWidth,gap=(w-iw*.75)/(n-1);
  items.forEach(el=>{const k=+el.dataset.k,u=k/(n-1)*2-1,dp=Math.cos(u*Math.PI*.45),x=(k-(n-1)/2)*gap,s=.72+.28*dp,on=el.classList.contains('on'),y=-(1-dp)*(w>600?70:48)-(on?20:0);
    el.style.transform='translate('+x.toFixed(1)+'px,'+y.toFixed(1)+'px) scale('+(on?s*1.06:s).toFixed(3)+')';el.style.zIndex=String(on?200:Math.round(dp*100))})}
function crCenter(){const sc=$('#stageScroll');if(sc&&sc.scrollWidth>sc.clientWidth)sc.scrollLeft=(sc.scrollWidth-sc.clientWidth)/2}
window.addEventListener('resize',crLayout);

/* hero reel: one persistent <video>, moved into the slot after each render so playback is not restarted */
function reelBtn(){const b=document.querySelector('.snd');if(b){b.textContent=REEL.muted?t('snd_on'):t('snd_off');b.setAttribute('aria-pressed',String(!REEL.muted))}}
function reelMount(){const s=document.getElementById('reelSlot');if(!s)return;REEL.setAttribute('aria-label',t('hero_vid'));s.insertBefore(REEL,s.firstChild);if(REEL.autoplay||!REEL.paused)REEL.play().catch(()=>{});reelBtn()}

/* Sends the order to the studio bot (bot.py, POST /api/orders). Bouquet and wrapping names go in Russian for the studios. */
function sendToBot(o){if(!ORDER_API.url)return;
  const R=T.ru,abs=u=>{try{return new URL(u,location.href).href}catch(e){return ''}};
  const items=o.items.map(i=>{const p=PRODUCTS.find(x=>x.id===i.id);return{sku:p.id,name:p.n.ru+(i.promo?' (букет дня)':''),qty:i.q,price_usd:i.usd||p.usd,promo:!!i.promo,composition:p.k.ru,image_url:abs(p.img)}});
  const com=o.kind?('🤍 БУКЕТ В ДОБРЫЕ РУКИ: подарить случайному прохожему на улице и снять видео вручения. Подпись: '+o.sign+'. Показывать видео в соцсетях: '+(o.pub?'да':'нет')+'.'+(o.com?'\n'+o.com:'')):o.com;
  const goods=items.reduce((s,i)=>s+i.price_usd*i.qty,0);
  const body={id:o.id,items,total_usd:o.total,payout_usd:Math.round(goods*0.7),
    delivery:{date:o.date,window:o.win,exact_time:o.exact},recipient:o.kind?{name:'Случайный прохожий (букет в добрые руки)',phone:o.yphone,address:'Ереван, вручить незнакомцу на улице'}:{name:o.rec,phone:o.phone,address:o.addr},
    sender:{name:o.you,phone:o.yphone,anonymous:o.anon},occasion:o.occ,card:{type:o.card,text:o.card==='media'?'🎙 Аудио/видео-открытка: QR-код бот пришлёт отдельно, распечатать и вложить':o.text},
    wrapping:{paper:R.papers[o.paper||0],ribbon:R.ribbons[o.ribbon||0]},kindness:!!o.kind,kind_hands:o.kind?{sign:o.sign,public:!!o.pub}:null,comment:com,payment:{method:o.pay,status:'demo'},lang:S.lang,remind:!!o.remind};
  fetch(ORDER_API.url.replace(/\/$/,'')+'/api/orders',{method:'POST',headers:TG?{'Content-Type':'application/json','X-Telegram-Init-Data':TG.initData}:{'Content-Type':'application/json','X-Intake-Key':ORDER_API.key},body:JSON.stringify(body)})
    .then(r=>{if(!r.ok)throw r.status;if(TG)try{TG.HapticFeedback.notificationOccurred('success')}catch(e){}return r.json().catch(()=>({}))})
    .then(j=>{let ch=false;if(j&&j.record_link&&/^https:\/\/t\.me\//.test(j.record_link)){S.recLink=j.record_link;ch=true}if(j&&j.remind_link&&/^https:\/\/t\.me\//.test(j.remind_link)){S.remLink=j.remind_link;ch=true}if(ch&&S.view==='done')render()}).catch(()=>toast(t('send_fail')))}

/* Telegram mini app: same page inside Telegram, with Telegram's own main and back buttons */
function tgSync(){if(!TG)return;
  const MB=TG.MainButton,BB=TG.BackButton,n=cartCount();let txt=null,fn=null;
  if(S.view==='checkout'&&n){txt=t('co_place')+' · '+usd(cartSum()+DELIV);fn=()=>place()}
  else if(n&&S.view!=='done'){txt=t('cart')+' · '+n+' · '+usd(cartSum());fn=()=>go('checkout')}
  if(TG._mb){MB.offClick(TG._mb);TG._mb=null}
  if(txt){TG._mb=()=>{try{TG.HapticFeedback.impactOccurred('light')}catch(e){}fn()};MB.setText(txt);MB.onClick(TG._mb);MB.show()}else MB.hide();
  if(TG._bb){BB.offClick(TG._bb);TG._bb=null}
  if(S.view!=='shop'){TG._bb=()=>go('shop');BB.onClick(TG._bb);BB.show()}else BB.hide()}
function tgInit(WA){TG=WA;try{WA.ready();WA.expand()}catch(e){}
  document.body.classList.add('tgapp');S.mode='tg';
  document.documentElement.setAttribute('data-theme',WA.colorScheme==='dark'?'dark':'light');
  try{WA.MainButton.setParams({color:'#c9306a',text_color:'#ffffff'})}catch(e){}
  const u=(WA.initDataUnsafe&&WA.initDataUnsafe.user)||{};
  if(u.language_code&&T[u.language_code.slice(0,2)])S.lang=u.language_code.slice(0,2);
  const nm=[u.first_name,u.last_name].filter(Boolean).join(' ');if(nm&&!S.draft.f_you)S.draft.f_you=nm;
  render()}
function tgBoot(){const WA=window.Telegram&&window.Telegram.WebApp;if(WA&&WA.initData)tgInit(WA)}
if(!(window.Telegram&&window.Telegram.WebApp)&&/tgWebAppData/.test(location.hash)){const sc=document.createElement('script');sc.src='https://telegram.org/js/telegram-web-app.js';sc.onload=tgBoot;document.head.appendChild(sc)}else tgBoot();

/* Personal account inside Telegram: orders, bouquet photos and reminders come from the bot server */
const ST_IDX={new:0,offered:0,unassigned:0,accepted:1,built:3,courier:4,delivered:5};
function meApi(path,opt){opt=opt||{};return fetch(ORDER_API.url.replace(/\/$/,'')+path,Object.assign({},opt,{headers:Object.assign({'Content-Type':'application/json','X-Telegram-Init-Data':TG.initData},opt.headers||{})}))
  .then(r=>{if(!r.ok)throw r.status;return r})}
function meLoad(){S.me={status:'loading',data:S.me&&S.me.data};if(S.view==='cabinet')render();
  meApi('/api/me').then(r=>r.json()).then(d=>{S.me={status:'ok',data:d};if(S.view==='cabinet')render()})
    .catch(()=>{S.me={status:'err',data:S.me.data};if(S.view==='cabinet')render()})}
function srvWhen(d){d=d||{};return (d.date?fdate(d.date):'')+', '+(d.window==='asap'?t('win_asap'):d.window==='exact'?(d.exact_time||''):(d.window||''))}
function srvCabinet(){
  if(!S.me){setTimeout(meLoad,0);return h2(t('cab_t'))+'<p class="muted">'+t('cab_loading')+'</p>'}
  const d=S.me.data,stt=S.me.status;
  let head=h2(t('cab_t'))+'<div class="acts" style="margin:-16px 0 24px"><button class="btn sm" data-act="mereload"'+(stt==='loading'?' disabled':'')+'>'+(stt==='loading'?t('cab_loading'):t('cab_refresh'))+'</button></div>';
  if(stt==='err')head+='<p class="err" style="margin-bottom:16px">'+t('cab_err')+'</p>';
  if(!d)return head;
  const stLabel=s=>s==='cancelled'?t('st_cancel'):(s==='new'||s==='offered'||s==='unassigned')?t('st_wait'):T[S.lang].st[ST_IDX[s]];
  const ol=d.orders.length?d.orders.map(o=>{const i=ST_IDX[o.status],cancel=o.status==='cancelled';
    return '<div class="ord"><div class="h"><b class="nums">'+esc(o.id)+' · '+usd(o.total_usd||0)+'</b><span class="label" style="'+(o.status==='delivered'?'color:var(--ink)':'')+'">'+esc(stLabel(o.status))+'</span></div>'
    +'<div class="muted">'+esc(o.items.map(x=>{const p=PRODUCTS.find(p=>p.id===+x.sku);return (p?pn(p):x.name)+' × '+x.qty}).join(', '))+'<br>'+(o.kindness?t('cab_kind'):esc(o.recipient.name||'')+' · '+esc(o.recipient.address||''))+'<br>'+esc(srvWhen(o.delivery))+'</div>'
    +(o.has_photo?'<figure class="ord-photo"><img data-photo="'+esc(o.id)+'" alt="'+esc(t('cab_photo'))+'" width="360" height="450"><figcaption class="note">'+t('cab_photo')+'</figcaption></figure>':'')
    +(cancel?'':'<div class="prog" aria-hidden="true">'+[0,1,2,3,4,5].map(k=>'<i class="'+(k<=i?'on':'')+'"></i>').join('')+'</div>')
    +'<button class="btn sm" data-act="srvre" data-v="'+esc(o.id)+'">'+t('reorder')+'</button></div>'}).join(''):emptyBox(t('cab_none'),'shop',t('back'));
  const rl=d.reminders.length?d.reminders.map(r=>'<div class="ord"><div class="h"><b>'+fdate(r.target)+'</b></div><div class="muted">'+esc(r.label)+'</div><div class="acts"><button class="btn sm" data-act="shop">'+t('reorder')+'</button><button class="btn sm" data-act="remdel" data-v="'+r.id+'">'+t('rem_del')+'</button></div></div>').join(''):'<p class="muted ord">'+t('rem_none')+'</p>';
  const bl=d.recipients.length?d.recipients.map(p=>'<div class="line"><span><b>'+esc(p.name||'')+'</b><br><span class="muted">'+esc(p.address||'')+'</span></span><span class="muted nums">'+esc(p.phone||'')+'</span></div>').join(''):'<p class="muted ord">'+t('cab_none')+'</p>';
  setTimeout(mePhotos,0);
  return head+bonusBlock(d.orders.filter(o=>o.status!=='cancelled').map(o=>({usd:o.total_usd||0,ts:(o.created||0)*1000,done:o.status==='delivered'})))+'<section class="blk"><span class="label">'+t('cab_orders')+'</span>'+ol+'</section><section class="blk"><span class="label">'+t('cab_rem')+'</span>'+rl+'</section><section class="blk"><span class="label">'+t('cab_book')+'</span>'+bl+'</section>'}
const PHOTO_URL={};
function mePhotos(){document.querySelectorAll('img[data-photo]').forEach(img=>{const id=img.dataset.photo;
  if(PHOTO_URL[id]){img.src=PHOTO_URL[id];return}
  meApi('/api/photo/'+encodeURIComponent(id)).then(r=>r.blob()).then(b=>{PHOTO_URL[id]=URL.createObjectURL(b);document.querySelectorAll('img[data-photo="'+CSS.escape(id)+'"]').forEach(x=>x.src=PHOTO_URL[id])}).catch(()=>{})})}

/* Links from the bot: ?add=ID opens checkout with that bouquet, ?v=cabinet opens the account */
(()=>{let qp;try{qp=new URLSearchParams(location.search)}catch(e){return}
  const add=+qp.get('add'),v=qp.get('v');
  if(add&&PRODUCTS.find(p=>p.id===add&&!p.stem)){S.cart=[{id:add,q:1}];go('checkout')}
  else if(v==='cabinet')go('cabinet')})();

/* My bonuses: level from the last 30 days of spending (AMD), cashback on delivered orders.
   Until the bot server keeps the ledger, the numbers here are computed from the order list. */
const amdN=n=>Math.round(n).toLocaleString(LOC[S.lang])+'\u00a0֏';
function bonusBlock(list){const now=Date.now(),spent=list.filter(x=>now-x.ts<30*864e5).reduce((a,x)=>a+x.usd*RATE,0);
  let li=0;LEVELS.forEach((l,i)=>{if(spent>=l.min)li=i});const cur=LEVELS[li],nx=LEVELS[li+1],names=t('lv'),perks=t('lv_perk');
  const bal=list.filter(x=>x.done).reduce((a,x)=>a+Math.round(x.usd*RATE*cur.cb/100),0);
  const pct=nx?Math.max(0,Math.min(100,Math.round((spent-cur.min)/(nx.min-cur.min)*100))):100;
  return '<section class="blk bonus" id="bonus"><span class="label">'+t('bn_t')+'</span><div class="bn-top">'
  +'<div><span class="note">'+t('bn_bal')+'</span><b class="nums bn-bal">'+amdN(bal)+'</b></div>'
  +'<div><span class="note">'+t('bn_lvl')+'</span><b>'+esc(names[li])+' · '+cur.cb+'% '+t('bn_cb')+'</b></div>'
  +'<div><span class="note">'+t('bn_spent')+'</span><b class="nums">'+amdN(spent)+'</b></div></div>'
  +'<div class="bn-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="'+pct+'" aria-label="'+esc(t('bn_lvl'))+'"><i style="width:'+pct+'%"></i></div>'
  +'<p class="note" style="margin-top:8px">'+(nx?t('bn_next').replace('{l}',names[li+1]).replace('{s}',amdN(nx.min-spent)):t('bn_max'))+'</p>'
  +'<ol class="bn-lv">'+LEVELS.map((l,i)=>'<li'+(i===li?' aria-current="true"':'')+'><b>'+esc(names[i])+'</b><span class="nums">'+(l.min?'≥ '+amdN(l.min):'0\u00a0֏')+'</span><span>'+l.cb+'% '+t('bn_cb')+'</span>'+(perks[i]?'<span class="note">'+esc(perks[i])+'</span>':'')+'</li>').join('')+'</ol>'
  +'<p class="note">'+t('bn_how')+'</p></section>'}

/* Burger menu: every section of the shop in one place */
function menuInner(){const L=T[S.lang];
  const items=[['catalog','mn_cat'],promoOn()?['promo','mn_promo']:null,['ai','mn_ai'],['kind','mn_kind'],['vip','mn_vip'],['cabinet','mn_cab'],['bonus','mn_bonus']].filter(Boolean);
  return '<div class="menu-h"><span class="label">'+L.mn_open+'</span><button class="burger" type="button" data-act="menuclose" aria-label="'+L.mn_close+'"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button></div>'
  +'<ul class="menu-list">'+items.map(([k,l])=>'<li><button type="button" data-nav="'+k+'">'+L[l]+'</button></li>').join('')
  +'<li><button type="button" data-act="mgr">'+L.mn_contact+'</button></li></ul>'
  +'<div class="menu-sub"><span class="label">'+L.cur_t+'</span>'+curSwitch()+'</div>'
  +'<div class="menu-sub"><span class="label">'+L.mn_lang+'</span><div class="tabs" role="group" aria-label="'+L.mn_lang+'">'+[['ru','RU'],['en','EN'],['hy','HY']].map(([c,n])=>'<button class="tab" type="button" data-lang="'+c+'" aria-pressed="'+(S.lang===c)+'">'+n+'</button>').join('')+'</div></div>'
  +(TG||!DEMO_UI?'':'<div class="menu-sub"><span class="label">'+L.mn_demo+'</span><div class="tabs"><button class="tab" type="button" data-view="studio" aria-pressed="'+(S.view==='studio')+'">'+L.nav_studio+'</button><button class="tab" type="button" data-mode="site" aria-pressed="'+(S.mode==='site')+'">'+L.m_site+'</button><button class="tab" type="button" data-mode="tg" aria-pressed="'+(S.mode==='tg')+'">'+L.m_tg+'</button></div></div>')}
function menuOpen(){MENU_OPEN=true;const w=$('#menuWrap'),m=$('#menu');m.innerHTML=menuInner();w.hidden=false;document.body.classList.add('menu-on');
  $('#burger').setAttribute('aria-expanded','true');requestAnimationFrame(()=>{w.classList.add('on');const f=m.querySelector('[data-nav]');if(f)f.focus()})}
function menuClose(silent){if(!MENU_OPEN)return;MENU_OPEN=false;const w=$('#menuWrap');w.classList.remove('on');w.hidden=true;document.body.classList.remove('menu-on');
  const b=$('#burger');b.setAttribute('aria-expanded','false');if(!silent)b.focus()}
function navTo(k){const anchors={catalog:'catalog',promo:'promo',ai:'ai',kind:'kind',vip:'vip'};
  if(anchors[k]){if(S.view!=='shop')go('shop');const el=document.getElementById(anchors[k]);if(el){el.scrollIntoView({behavior:'smooth',block:'start'});const f=el.querySelector('h2,h1');if(f){f.setAttribute('tabindex','-1');f.focus({preventScroll:true})}}return}
  if(k==='cabinet')return go('cabinet');
  if(k==='bonus'){go('cabinet');setTimeout(()=>{const el=document.querySelector('.bonus');if(el)el.scrollIntoView({behavior:'smooth',block:'start'})},60)}}
document.addEventListener('keydown',e=>{if(!MENU_OPEN&&S.fOpen&&e.key==='Escape'){S.fOpen=false;catPaint();const fb=$('#fBtn');if(fb)fb.focus();return}if(!MENU_OPEN)return;if(e.key==='Escape'){e.preventDefault();menuClose()}
  else if(e.key==='Tab'){const f=[...$('#menu').querySelectorAll('button')];if(!f.length)return;const a=f[0],z=f[f.length-1];
    if(e.shiftKey&&document.activeElement===a){e.preventDefault();z.focus()}else if(!e.shiftKey&&document.activeElement===z){e.preventDefault();a.focus()}}});

/* Заявка «Маис лично» уходит админам в бот (POST /api/vip), в студии не раздаётся */
function sendVip(){const g=id=>(($('#'+id)||{}).value||'').trim(),req=['v_name','v_phone','v_rec'];let bad=0;
  req.forEach(k=>{const e=$('#'+k),m=document.querySelector('[data-e='+k+']'),ok=!!g(k);if(e)e.setAttribute('aria-invalid',ok?'false':'true');if(m)m.textContent=ok?'':t('req');if(!ok)bad++});
  if(bad){const f=document.querySelector('#vipForm [aria-invalid=true]');if(f)f.focus();return}
  const body={name:g('v_name'),phone:g('v_phone'),recipient:g('v_rec'),date:g('v_date'),comment:g('v_com'),lang:S.lang,price_from_usd:VIP.from};
  S.draft.f_you=body.name;S.draft.f_yphone=body.phone;
  const done=()=>{S.vip.status='ok';render();const el=$('#vip');if(el)el.scrollIntoView({block:'start'})};
  if(!ORDER_API.url)return done();
  S.vip.status='sending';const btn=document.querySelector('#vipForm [type=submit]');if(btn)btn.disabled=true;
  fetch(ORDER_API.url.replace(/\/$/,'')+'/api/vip',{method:'POST',headers:TG?{'Content-Type':'application/json','X-Telegram-Init-Data':TG.initData}:{'Content-Type':'application/json','X-Intake-Key':ORDER_API.key},body:JSON.stringify(body)})
    .then(r=>{if(!r.ok)throw r.status;done()}).catch(()=>{S.vip.status='err';render()})}
