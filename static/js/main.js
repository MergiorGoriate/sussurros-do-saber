const $=s=>document.querySelector(s),menu=$('#menuToggle'),nav=$('#mainNav'),searchToggle=$('#searchToggle'),searchPanel=$('#searchPanel');
menu?.addEventListener('click',()=>{const open=nav.classList.toggle('open');menu.setAttribute('aria-expanded',String(open));menu.setAttribute('aria-label',open?'Fechar menu':'Abrir menu')});
searchToggle?.addEventListener('click',()=>{searchPanel.classList.toggle('hidden');const open=!searchPanel.classList.contains('hidden');searchToggle.setAttribute('aria-expanded',String(open));searchToggle.setAttribute('aria-label',open?'Fechar pesquisa':'Abrir pesquisa');if(open)searchPanel.querySelector('input').focus()});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(nav?.classList.contains('open'))menu.click();if(searchPanel&&!searchPanel.classList.contains('hidden'))searchToggle.click()}});
let sessionTheme='light';try{sessionTheme=sessionStorage.getItem('theme')||'light'}catch{}
const brandLogoSource=$('.brand-link source[data-dark-srcset]');
const updateBrandLogo=dark=>{if(brandLogoSource)brandLogoSource.srcset=dark?brandLogoSource.dataset.darkSrcset:brandLogoSource.dataset.lightSrcset};
document.documentElement.classList.toggle('dark',sessionTheme==='dark');
updateBrandLogo(sessionTheme==='dark');
const themeToggle=$('#themeToggle');themeToggle?.setAttribute('aria-pressed',String(sessionTheme==='dark'));themeToggle?.addEventListener('click',()=>{document.documentElement.classList.toggle('dark');const dark=document.documentElement.classList.contains('dark');updateBrandLogo(dark);try{sessionStorage.setItem('theme',dark?'dark':'light')}catch{}themeToggle.setAttribute('aria-pressed',String(dark))});
let scrollFrame=0;
const scrollTasks=[];
const scheduleScrollUpdate=()=>{if(scrollFrame)return;scrollFrame=requestAnimationFrame(()=>{scrollFrame=0;const h=document.documentElement,total=h.scrollHeight-h.clientHeight,top=h.scrollTop,percent=total>0?top/total*100:0;const progress=$('#readingProgress');if(progress)progress.style.width=`${percent}%`;scrollTasks.forEach(task=>task(top,percent))})};
addEventListener('scroll',scheduleScrollUpdate,{passive:true});
const backToTop=$('#backToTop');
if(backToTop){
  const updateBackToTop=()=>{backToTop.hidden=window.scrollY<320};
  updateBackToTop();
  scrollTasks.push(updateBackToTop);
  backToTop.addEventListener('click',()=>window.scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'}));
}

$('#newsletterForm')?.addEventListener('submit',async e=>{e.preventDefault();const m=$('#newsletterMessage'),email=e.currentTarget.querySelector('input').value;m.textContent='A confirmar...';try{const r=await fetch('/api/newsletter',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})}),d=await r.json();m.textContent=d.message;if(d.ok)e.currentTarget.reset()}catch{m.textContent='Não foi possível concluir agora.'}});
$('#calculateStats')?.addEventListener('click',()=>{const v=$('#dataValues').value.trim().split(/[,;\s]+/).filter(Boolean).map(Number).filter(Number.isFinite).sort((a,b)=>a-b),o=$('#statsResult');if(!v.length){o.innerHTML='<p>Introduza valores válidos.</p>';return}const m=Math.floor(v.length/2),med=v.length%2?v[m]:(v[m-1]+v[m])/2,avg=v.reduce((a,b)=>a+b,0)/v.length;o.innerHTML=`<div><strong>${v.length}</strong><span>N</span></div><div><strong>${avg.toFixed(2)}</strong><span>Média</span></div><div><strong>${med}</strong><span>Mediana</span></div><div><strong>${v[0]}–${v.at(-1)}</strong><span>Amplitude</span></div>`});
$('#generateCitation')?.addEventListener('click',()=>{const v=id=>$(id).value.trim(),a=v('#citeAuthor'),y=v('#citeYear'),t=v('#citeTitle'),j=v('#citeJournal');$('#citationResult').textContent=a&&y&&t&&j?`${a} (${y}). ${t}. ${j}.`:'Preencha todos os campos.'});const terms=[['Amostra','Parte de uma população seleccionada para o estudo.'],['Correlação','Medida da associação entre duas variáveis.'],['Endófito','Organismo que vive no interior de uma planta sem causar dano aparente.'],['Hipótese','Proposição verificável que orienta uma investigação.'],['Microbiota','Conjunto de microrganismos presentes num ambiente.'],['Variável','Característica que pode assumir valores ou categorias diferentes.']],list=$('#glossaryList'),render=q=>{if(list)list.innerHTML=terms.filter(t=>t.join(' ').toLowerCase().includes(q.toLowerCase())).map(t=>`<div class="term"><strong>${t[0]}</strong><p>${t[1]}</p></div>`).join('')};render('');$('#glossarySearch')?.addEventListener('input',e=>render(e.target.value));
let proseSize=1.13;$('#increaseFont')?.addEventListener('click',()=>{$('.prose-article').style.fontSize=`${proseSize=Math.min(1.45,proseSize+.08)}rem`});$('#decreaseFont')?.addEventListener('click',()=>{$('.prose-article').style.fontSize=`${proseSize=Math.max(.95,proseSize-.08)}rem`});$('#shareArticle')?.addEventListener('click',async()=>{try{if(navigator.share)await navigator.share({title:document.title,url:location.href});else{await navigator.clipboard.writeText(location.href);$('#shareMessage').textContent='Ligação copiada.'}}catch{}});
const quiz=[{q:'Qual organelo produz a maior parte do ATP?',o:['Núcleo','Mitocôndria','Ribossoma'],a:1},{q:'O valor de p é usado principalmente para:',o:['Medir a amostra','Avaliar evidência contra a hipótese nula','Calcular a média'],a:1},{q:'Bactérias endofíticas vivem:',o:['Dentro dos tecidos vegetais','Apenas na água','Somente no solo'],a:0}];let qi=0,score=0;function showQuiz(){if(!$('#quizQuestion'))return;const x=quiz[qi];$('#quizQuestion').textContent=`${qi+1}. ${x.q}`;$('#quizOptions').innerHTML=x.o.map((o,i)=>`<button data-answer="${i}">${o}</button>`).join('');$('#quizFeedback').textContent='';$('#nextQuestion').classList.add('hidden');document.querySelectorAll('[data-answer]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-answer]').forEach(x=>x.disabled=true);const ok=Number(b.dataset.answer)===x.a;if(ok)score++;b.classList.add(ok?'correct':'wrong');$('#quizFeedback').textContent=ok?'Correcto!':'Resposta correcta: '+x.o[x.a];$('#nextQuestion').classList.remove('hidden')})}$('#nextQuestion')?.addEventListener('click',()=>{qi++;if(qi<quiz.length)showQuiz();else $('#quizBox').innerHTML=`<div class="quiz-score"><strong>${score}/${quiz.length}</strong><p>Desafio concluído.</p><button class="primary-btn mt-4" data-reload-page>Tentar novamente</button></div>`});showQuiz();


// Comportamento responsivo da navegação
const desktopNav=matchMedia('(min-width: 768px)');
const closeMobileNav=()=>{if(nav?.classList.contains('open')){nav.classList.remove('open');menu?.setAttribute('aria-expanded','false');menu?.setAttribute('aria-label','Abrir menu')}};
desktopNav.addEventListener?.('change',e=>{if(e.matches)closeMobileNav()});
nav?.querySelectorAll('a').forEach(link=>link.addEventListener('click',closeMobileNav));
document.addEventListener('click',e=>{if(!desktopNav.matches&&nav?.classList.contains('open')&&!nav.contains(e.target)&&!menu?.contains(e.target))closeMobileNav()});
document.querySelectorAll('.article-markdown table').forEach(table=>{if(table.parentElement?.classList.contains('table-wrapper'))return;const wrap=document.createElement('div');wrap.className='table-wrapper';wrap.setAttribute('role','region');wrap.setAttribute('aria-label','Tabela com deslocamento horizontal');wrap.tabIndex=0;table.parentNode.insertBefore(wrap,table);wrap.appendChild(table)});



// Invalid, stale and malformed choices never grant optional processing.
const readSiteConsent=()=>{
  try{
    const raw=document.cookie.split('; ').find(value=>value.startsWith('cookie_consent_v3='));
    if(!raw)return null;
    const c=JSON.parse(decodeURIComponent(raw.slice('cookie_consent_v3='.length)));
    const age=Date.now()-Date.parse(c.updatedAt);
    return c.essential===true&&typeof c.analytics==='boolean'&&typeof c.ads==='boolean'&&Number.isFinite(age)&&age>=0&&age<15552000000?c:null;
  }catch{return null}
};
// Google Tag Manager, Consent Mode v2 e eventos essenciais
const pushAnalyticsEvent=(event,parameters={})=>{
  if(readSiteConsent()?.analytics!==true)return;
  window.dataLayer=window.dataLayer||[];
  window.dataLayer.push({event,...parameters});
};
window.sdsTrack=pushAnalyticsEvent;

(()=>{
  const banner=document.querySelector('#cookieConsent');
  if(!banner)return;
  const preferences=document.querySelector('#cookiePreferences');
  const analytics=document.querySelector('#analyticsConsent');
  const ads=document.querySelector('#adsConsent');
  const customize=document.querySelector('#cookieCustomize');
  const accept=document.querySelector('#cookieAccept');
  const reject=document.querySelector('#cookieReject');
  const save=document.querySelector('#cookieSave');
  const settings=document.querySelector('#cookieSettingsLink');
  const cookieName='cookie_consent_v3';
  const read=readSiteConsent;
  const updateGoogleConsent=consent=>{
    const state=consent.analytics?'granted':'denied';
    // Local preferences are not a certified CMP or a TCF signal.
    const advertising='denied';
    if(typeof window.gtag==='function')window.gtag('consent','update',{
      analytics_storage:state,
      ad_storage:advertising,
      ad_user_data:advertising,
      ad_personalization:advertising,
      functionality_storage:'granted',
      security_storage:'granted'
    });
    pushAnalyticsEvent('consent_update',{analytics_consent:state,ads_consent:advertising});
  };
  const activateOptionalScripts=consent=>{
    document.querySelectorAll('script[type="text/plain"][data-cookie-category]').forEach(source=>{
      const category=source.dataset.cookieCategory;
      // Advertising remains suspended pending a verified certified CMP integration.
      if(category!=='analytics'||consent.analytics!==true)return;
      const script=document.createElement('script');
      [...source.attributes].forEach(attribute=>{
        if(!['type','data-cookie-category'].includes(attribute.name))script.setAttribute(attribute.name,attribute.value);
      });
      script.text=source.text;
      source.replaceWith(script);
    });
  };
  const persist=consent=>{
    consent.ads=false; // Advertising is not active in this release.
    const previous=read();
    const withdrawing=previous?.analytics===true&&consent.analytics!==true;
    const secure=location.protocol==='https:'?'; Secure':'';
    document.cookie=cookieName+'='+encodeURIComponent(JSON.stringify(consent))+'; Max-Age=15552000; Path=/; SameSite=Lax'+secure;
    updateGoogleConsent(consent);
    if(withdrawing){location.reload();return}
    banner.hidden=true;
    activateOptionalScripts(consent);
    dispatchEvent(new CustomEvent('cookieconsentchange',{detail:consent}));
  };
  const open=()=>{
    const current=read();
    analytics.checked=Boolean(current?.analytics);
    ads.checked=false;
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
  accept.addEventListener('click',()=>persist({essential:true,analytics:true,ads:true,updatedAt:new Date().toISOString()}));
  reject.addEventListener('click',()=>persist({essential:true,analytics:false,ads:false,updatedAt:new Date().toISOString()}));
  save.addEventListener('click',()=>persist({essential:true,analytics:analytics.checked,ads:ads.checked,updatedAt:new Date().toISOString()}));
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
      if(target.origin!==location.origin)pushAnalyticsEvent('outbound_click',{link_domain:target.hostname});
    }catch{}
  });
  const sent=new Set();
  scrollTasks.push((_top,scrollPercent)=>{
    if(document.documentElement.scrollHeight-innerHeight<=0)return;
    const percent=Math.round(scrollPercent);
    [25,50,75,90].forEach(depth=>{
      if(percent>=depth&&!sent.has(depth)){
        sent.add(depth);
        pushAnalyticsEvent('scroll_depth',{percent_scrolled:depth,page_type:pageType});
      }
    });
  });
})();


// Mantém cartões e artigos legíveis quando uma origem externa remove ou bloqueia a imagem.
const applyImageFallback = (image) => {
  if (!(image instanceof HTMLImageElement) || image.hasAttribute('data-reader-avatar') || image.dataset.fallbackApplied === 'true') return;
  image.dataset.fallbackApplied = 'true';
  image.removeAttribute('srcset');
  image.removeAttribute('sizes');
  image.src = '/static/img/image-fallback.svg';
  if (!image.alt) image.alt = 'Imagem temporariamente indisponível';
};

document.addEventListener('error', (event) => {
  applyImageFallback(event.target);
}, true);

document.querySelectorAll('img').forEach((image) => {
  if (/^https?:/.test(image.currentSrc || image.src)) image.referrerPolicy = 'no-referrer';
  if (image.complete && image.naturalWidth === 0) applyImageFallback(image);
});


document.addEventListener('click', (event) => {
  if (event.target.closest('[data-reload-page]')) window.location.reload();
});


