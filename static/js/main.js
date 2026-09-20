const $=s=>document.querySelector(s),menu=$('#menuToggle'),nav=$('#mainNav'),searchToggle=$('#searchToggle'),searchPanel=$('#searchPanel');
menu?.addEventListener('click',()=>{const open=nav.classList.toggle('open');menu.setAttribute('aria-expanded',String(open));menu.setAttribute('aria-label',open?'Fechar menu':'Abrir menu')});
searchToggle?.addEventListener('click',()=>{searchPanel.classList.toggle('hidden');const open=!searchPanel.classList.contains('hidden');searchToggle.setAttribute('aria-expanded',String(open));searchToggle.setAttribute('aria-label',open?'Fechar pesquisa':'Abrir pesquisa');if(open)searchPanel.querySelector('input').focus()});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(nav?.classList.contains('open'))menu.click();if(searchPanel&&!searchPanel.classList.contains('hidden'))searchToggle.click()}});
if(localStorage.theme==='dark'||(!('theme'in localStorage)&&matchMedia('(prefers-color-scheme:dark)').matches))document.documentElement.classList.add('dark');
const themeToggle=$('#themeToggle');themeToggle?.setAttribute('aria-pressed',String(document.documentElement.classList.contains('dark')));themeToggle?.addEventListener('click',()=>{document.documentElement.classList.toggle('dark');const dark=document.documentElement.classList.contains('dark');localStorage.theme=dark?'dark':'light';themeToggle.setAttribute('aria-pressed',String(dark))});
let scrollFrame=0;addEventListener('scroll',()=>{if(scrollFrame)return;scrollFrame=requestAnimationFrame(()=>{const h=document.documentElement,total=h.scrollHeight-h.clientHeight,p=total>0?h.scrollTop/total*100:0,progress=$('#readingProgress');if(progress)progress.style.width=`${p}%`;scrollFrame=0})},{passive:true});
const savedIds=()=>{try{const value=JSON.parse(localStorage.savedArticles||'[]');return Array.isArray(value)?value.map(String):[]}catch{return[]}};function wireBookmarks(){document.querySelectorAll('.bookmark').forEach(btn=>{const render=()=>{const saved=savedIds().includes(btn.dataset.id);btn.textContent=saved?'♥':'♡';btn.classList.toggle('saved',saved);btn.setAttribute('aria-pressed',String(saved))};render();btn.addEventListener('click',()=>{let ids=savedIds();ids=ids.includes(btn.dataset.id)?ids.filter(id=>id!==btn.dataset.id):[...ids,btn.dataset.id];localStorage.savedArticles=JSON.stringify(ids);render()})})}wireBookmarks();
$('#newsletterForm')?.addEventListener('submit',async e=>{e.preventDefault();const m=$('#newsletterMessage'),email=e.currentTarget.querySelector('input').value;m.textContent='A confirmar...';try{const r=await fetch('/api/newsletter',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})}),d=await r.json();m.textContent=d.message;if(d.ok)e.currentTarget.reset()}catch{m.textContent='Não foi possível concluir agora.'}});
$('#calculateStats')?.addEventListener('click',()=>{const v=$('#dataValues').value.split(/[,;\s]+/).map(Number).filter(Number.isFinite).sort((a,b)=>a-b),o=$('#statsResult');if(!v.length){o.innerHTML='<p>Introduza valores válidos.</p>';return}const m=Math.floor(v.length/2),med=v.length%2?v[m]:(v[m-1]+v[m])/2,avg=v.reduce((a,b)=>a+b,0)/v.length;o.innerHTML=`<div><strong>${v.length}</strong><span>N</span></div><div><strong>${avg.toFixed(2)}</strong><span>Média</span></div><div><strong>${med}</strong><span>Mediana</span></div><div><strong>${v[0]}–${v.at(-1)}</strong><span>Amplitude</span></div>`});
$('#generateCitation')?.addEventListener('click',()=>{const v=id=>$(id).value.trim(),a=v('#citeAuthor'),y=v('#citeYear'),t=v('#citeTitle'),j=v('#citeJournal');$('#citationResult').textContent=a&&y&&t&&j?`${a} (${y}). ${t}. ${j}.`:'Preencha todos os campos.'});const terms=[['Amostra','Parte de uma população seleccionada para o estudo.'],['Correlação','Medida da associação entre duas variáveis.'],['Endófito','Organismo que vive no interior de uma planta sem causar dano aparente.'],['Hipótese','Proposição verificável que orienta uma investigação.'],['Microbiota','Conjunto de microrganismos presentes num ambiente.'],['Variável','Característica que pode assumir valores ou categorias diferentes.']],list=$('#glossaryList'),render=q=>{if(list)list.innerHTML=terms.filter(t=>t.join(' ').toLowerCase().includes(q.toLowerCase())).map(t=>`<div class="term"><strong>${t[0]}</strong><p>${t[1]}</p></div>`).join('')};render('');$('#glossarySearch')?.addEventListener('input',e=>render(e.target.value));
if($('#favoritesGrid')){const ids=savedIds().filter(id=>/^\d+$/.test(id)).slice(0,50),grid=$('#favoritesGrid');if(!ids.length){$('#favoritesEmpty').classList.remove('hidden')}else fetch('/api/artigos?ids='+encodeURIComponent(ids.join(','))).then(r=>{if(!r.ok)throw new Error();return r.json()}).then(items=>{if(!items.length){$('#favoritesEmpty').classList.remove('hidden');return}items.forEach(a=>{const link=document.createElement('a');link.className='story-card';link.href=`/artigo/${encodeURIComponent(a.slug||a.id)}`;const img=document.createElement('img');img.src=a.image;img.alt=`Imagem de apoio: ${a.title}`;img.loading='lazy';img.decoding='async';img.width=640;img.height=400;img.className='w-full aspect-[16/10] object-cover';const body=document.createElement('div');body.className='p-5';const category=document.createElement('span');category.className='eyebrow';category.textContent=a.category;const title=document.createElement('h2');title.className='font-serif text-2xl mt-2';title.textContent=a.title;const summary=document.createElement('p');summary.className='mt-2 opacity-60';summary.textContent=a.summary;body.append(category,title,summary);link.append(img,body);grid.appendChild(link)})}).catch(()=>{const empty=$('#favoritesEmpty');empty.classList.remove('hidden');empty.querySelector('p').textContent='Não foi possível carregar os favoritos agora.'})}
let proseSize=1.13;$('#increaseFont')?.addEventListener('click',()=>{$('.prose-article').style.fontSize=`${proseSize=Math.min(1.45,proseSize+.08)}rem`});$('#decreaseFont')?.addEventListener('click',()=>{$('.prose-article').style.fontSize=`${proseSize=Math.max(.95,proseSize-.08)}rem`});$('#shareArticle')?.addEventListener('click',async()=>{try{if(navigator.share)await navigator.share({title:document.title,url:location.href});else{await navigator.clipboard.writeText(location.href);$('#shareMessage').textContent='Ligação copiada.'}}catch{}});
const quiz=[{q:'Qual organelo produz a maior parte do ATP?',o:['Núcleo','Mitocôndria','Ribossoma'],a:1},{q:'O valor de p é usado principalmente para:',o:['Medir a amostra','Avaliar evidência contra a hipótese nula','Calcular a média'],a:1},{q:'Bactérias endofíticas vivem:',o:['Dentro dos tecidos vegetais','Apenas na água','Somente no solo'],a:0}];let qi=0,score=0;function showQuiz(){if(!$('#quizQuestion'))return;const x=quiz[qi];$('#quizQuestion').textContent=`${qi+1}. ${x.q}`;$('#quizOptions').innerHTML=x.o.map((o,i)=>`<button data-answer="${i}">${o}</button>`).join('');$('#quizFeedback').textContent='';$('#nextQuestion').classList.add('hidden');document.querySelectorAll('[data-answer]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-answer]').forEach(x=>x.disabled=true);const ok=Number(b.dataset.answer)===x.a;if(ok)score++;b.classList.add(ok?'correct':'wrong');$('#quizFeedback').textContent=ok?'Correcto!':'Resposta correcta: '+x.o[x.a];$('#nextQuestion').classList.remove('hidden')})}$('#nextQuestion')?.addEventListener('click',()=>{qi++;if(qi<quiz.length)showQuiz();else $('#quizBox').innerHTML=`<div class="quiz-score"><strong>${score}/${quiz.length}</strong><p>Desafio concluído.</p><button class="primary-btn mt-4" onclick="location.reload()">Tentar novamente</button></div>`});showQuiz();


// Comportamento responsivo da navegação
const desktopNav=matchMedia('(min-width: 768px)');
const closeMobileNav=()=>{if(nav?.classList.contains('open')){nav.classList.remove('open');menu?.setAttribute('aria-expanded','false');menu?.setAttribute('aria-label','Abrir menu')}};
desktopNav.addEventListener?.('change',e=>{if(e.matches)closeMobileNav()});
nav?.querySelectorAll('a').forEach(link=>link.addEventListener('click',closeMobileNav));
document.addEventListener('click',e=>{if(!desktopNav.matches&&nav?.classList.contains('open')&&!nav.contains(e.target)&&!menu?.contains(e.target))closeMobileNav()});
document.querySelectorAll('.article-markdown table').forEach(table=>{if(table.parentElement?.classList.contains('table-wrapper'))return;const wrap=document.createElement('div');wrap.className='table-wrapper';wrap.setAttribute('role','region');wrap.setAttribute('aria-label','Tabela com deslocamento horizontal');wrap.tabIndex=0;table.parentNode.insertBefore(wrap,table);wrap.appendChild(table)});



// Google Tag Manager, Consent Mode v2 e eventos essenciais
const pushAnalyticsEvent=(event,parameters={})=>{
  window.dataLayer=window.dataLayer||[];
  window.dataLayer.push({event,...parameters});
};
window.sdsTrack=pushAnalyticsEvent;

(()=>{
  const banner=document.querySelector('#cookieConsent');
  if(!banner)return;
  const preferences=document.querySelector('#cookiePreferences');
  const analytics=document.querySelector('#analyticsConsent');
  const customize=document.querySelector('#cookieCustomize');
  const accept=document.querySelector('#cookieAccept');
  const reject=document.querySelector('#cookieReject');
  const save=document.querySelector('#cookieSave');
  const settings=document.querySelector('#cookieSettingsLink');
  const cookieName='cookie_consent_v2';
  const read=()=>{
    const item=document.cookie.split('; ').find(value=>value.startsWith(cookieName+'='));
    if(!item)return null;
    try{return JSON.parse(decodeURIComponent(item.split('=').slice(1).join('=')))}catch{return null}
  };
  const updateGoogleConsent=consent=>{
    const state=consent.analytics?'granted':'denied';
    if(typeof window.gtag==='function')window.gtag('consent','update',{
      analytics_storage:state,
      ad_storage:'denied',
      ad_user_data:'denied',
      ad_personalization:'denied',
      functionality_storage:'granted',
      security_storage:'granted'
    });
    pushAnalyticsEvent('consent_update',{analytics_consent:state});
  };
  const activateOptionalScripts=consent=>{
    document.querySelectorAll('script[type="text/plain"][data-cookie-category]').forEach(source=>{
      const category=source.dataset.cookieCategory;
      if(category==='analytics'&&!consent.analytics)return;
      const script=document.createElement('script');
      [...source.attributes].forEach(attribute=>{
        if(!['type','data-cookie-category'].includes(attribute.name))script.setAttribute(attribute.name,attribute.value);
      });
      script.text=source.text;
      source.replaceWith(script);
    });
  };
  const persist=consent=>{
    const secure=location.protocol==='https:'?'; Secure':'';
    document.cookie=cookieName+'='+encodeURIComponent(JSON.stringify(consent))+'; Max-Age=15552000; Path=/; SameSite=Lax'+secure;
    updateGoogleConsent(consent);
    banner.hidden=true;
    activateOptionalScripts(consent);
    dispatchEvent(new CustomEvent('cookieconsentchange',{detail:consent}));
  };
  const open=()=>{
    const current=read();
    analytics.checked=Boolean(current?.analytics);
    preferences.hidden=true;
    save.hidden=true;
    accept.hidden=false;
    customize.setAttribute('aria-expanded','false');
    banner.hidden=false;
    setTimeout(()=>accept.focus(),0);
  };
  customize.addEventListener('click',()=>{
    const expanded=preferences.hidden;
    preferences.hidden=!expanded;
    save.hidden=!expanded;
    accept.hidden=expanded;
    customize.setAttribute('aria-expanded',String(expanded));
  });
  accept.addEventListener('click',()=>persist({essential:true,analytics:true,updatedAt:new Date().toISOString()}));
  reject.addEventListener('click',()=>persist({essential:true,analytics:false,updatedAt:new Date().toISOString()}));
  save.addEventListener('click',()=>persist({essential:true,analytics:analytics.checked,updatedAt:new Date().toISOString()}));
  settings?.addEventListener('click',open);
  const current=read();
  if(current){updateGoogleConsent(current);activateOptionalScripts(current)}else open();
})();

(()=>{
  const pagePath=location.pathname;
  const pageType=pagePath.startsWith('/artigo/')?'article':pagePath==='/'?'home':pagePath.split('/').filter(Boolean)[0]||'home';
  pushAnalyticsEvent('page_context',{page_type:pageType});
  if(pageType==='article'){
    pushAnalyticsEvent('article_view',{
      article_title:document.querySelector('h1')?.textContent?.trim().slice(0,150)||document.title.slice(0,150),
      article_path:pagePath
    });
  }
  document.querySelector('#searchPanel')?.addEventListener('submit',()=>pushAnalyticsEvent('search',{search_location:'header'}));
  document.querySelector('#shareArticle')?.addEventListener('click',()=>pushAnalyticsEvent('share',{method:navigator.share?'native':'copy_link',content_type:'article'}));
  document.querySelector('#newsletterForm')?.addEventListener('submit',()=>pushAnalyticsEvent('newsletter_submit',{form_location:'site'}));
  document.querySelector('#contactForm')?.addEventListener('submit',()=>pushAnalyticsEvent('contact_submit',{form_location:'contact_page'}));
  document.addEventListener('click',event=>{
    const bookmark=event.target.closest('.bookmark');
    if(bookmark)pushAnalyticsEvent('bookmark_toggle',{article_id:String(bookmark.dataset.id||'')});
    const link=event.target.closest('a[href]');
    if(!link)return;
    try{
      const target=new URL(link.href,location.href);
      if(target.origin!==location.origin)pushAnalyticsEvent('outbound_click',{link_domain:target.hostname,link_url:target.href.slice(0,300)});
    }catch{}
  });
  const sent=new Set();
  addEventListener('scroll',()=>{
    const total=document.documentElement.scrollHeight-innerHeight;
    if(total<=0)return;
    const percent=Math.round(scrollY/total*100);
    [25,50,75,90].forEach(depth=>{
      if(percent>=depth&&!sent.has(depth)){
        sent.add(depth);
        pushAnalyticsEvent('scroll_depth',{percent_scrolled:depth,page_type:pageType});
      }
    });
  },{passive:true});
})();


// Mantém cartões e artigos legíveis quando uma origem externa remove ou bloqueia a imagem.
document.addEventListener('error', (event) => {
  const image = event.target;
  if (!(image instanceof HTMLImageElement) || image.dataset.fallbackApplied === 'true') return;
  image.dataset.fallbackApplied = 'true';
  image.removeAttribute('srcset');
  image.removeAttribute('sizes');
  image.src = '/static/img/image-fallback.svg';
  if (!image.alt) image.alt = 'Imagem temporariamente indisponível';
}, true);

document.querySelectorAll('img[src^="http"]').forEach((image) => {
  image.referrerPolicy = 'no-referrer';
});
