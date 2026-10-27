window.sdsText=window.sdsText||(text=>text);
window.sdsHTML=window.sdsHTML||(text=>window.sdsText(text).replace(/[&<>"\']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","\'":"&#39;"}[c])));
/* A single native cover player, also used by the existing editor preview. */
(() => {
  const instances=new WeakMap(),motion=matchMedia('(prefers-reduced-motion: reduce)');
  let activeAnimation=null;
  function mountExternal(root){
    const template=root.querySelector('.cover-external-template'),player=root.querySelector('.cover-external-player'),button=root.querySelector('.cover-toggle'),restore=root.querySelector('.cover-restore');
    if(!template||!player||!button||!restore)return;
    let disposed=false;
    const reset=()=>{if(disposed)return;player.replaceChildren();root.dataset.state='idle';button.hidden=false;restore.hidden=true;};
    button.hidden=false;button.textContent=window.sdsText("Reproduzir vídeo da capa");button.title=button.textContent;
    button.addEventListener('click',()=>{player.replaceChildren(template.content.cloneNode(true));root.dataset.state='playing';button.hidden=true;restore.hidden=false;player.querySelector('iframe')?.addEventListener('error',reset);});
    restore.addEventListener('click',()=>{reset();button.focus();});
    instances.set(root,{dispose:()=>{reset();disposed=true;}});
  }
  function mount(root){
    if(!root||instances.has(root))return;
    if(root.dataset.external==='true'){mountExternal(root);return;}
    const video=root.querySelector('.cover-video'),button=root.querySelector('.cover-toggle'),status=root.querySelector('.cover-status');
    if(!video||!button||!status||!video.dataset.src)return;
    const animated=root.dataset.mode==='video_animated';
    let visible=false,userPaused=false,explicit=false,blocked=false,failed=false,ready=false,disposed=false,timer=null;
    const connection=navigator.connection;
    const restricted=()=>motion.matches||connection?.saveData||['slow-2g','2g'].includes(connection?.effectiveType);
    const say=message=>{if(disposed)return;status.textContent=message;status.hidden=!message;};
    const state=value=>{if(disposed)return;root.dataset.state=value;button.textContent=value==='playing'?window.sdsText("Pausar animação da capa"):(failed?window.sdsText("Voltar a tentar reproduzir a capa"):(animated?window.sdsText("Reproduzir animação da capa"):window.sdsText("Reproduzir vídeo da capa")));if(animated)button.setAttribute('aria-pressed',String(value==='playing'));button.title=button.textContent;button.hidden=!animated&&ready;};
    const pause=()=>{video.pause();clearTimeout(timer);if(ready)state('paused');};
    async function play(manual=false){
      if(disposed||!root.isConnected||document.hidden||(!manual&&(userPaused||blocked||restricted()||!visible)))return;
      explicit=manual;userPaused=false;blocked=false;
      if(animated){video.muted=true;video.defaultMuted=true;video.loop=true;if(activeAnimation&&activeAnimation!==video)activeAnimation.pause();activeAnimation=video;}
      say('');state('loading');clearTimeout(timer);
      video.autoplay=false;
      if(!video.getAttribute('src')){video.poster=root.querySelector('.cover-poster')?.currentSrc||video.dataset.poster||'';video.src=video.dataset.src;}
      if(failed){failed=false;video.load();}
      timer=setTimeout(()=>{blocked=true;video.autoplay=false;pause();state('blocked');say(window.sdsText("A imagem de reserva está disponível. Use o botão para tentar reproduzir."));},15000);
      try{await video.play();}catch(_){clearTimeout(timer);if(disposed)return;blocked=true;if(failed||video.error){failed=true;ready=false;state('error');say(window.sdsText("Não foi possível carregar o vídeo. A imagem de reserva mantém-se disponível."));}else{state('blocked');say(window.sdsText("A reprodução não iniciou. Pode continuar a ler ou usar o botão para tentar novamente."));}}
    }
    state('idle');
    button.hidden=false;
    button.addEventListener('click',()=>{if(!video.paused){userPaused=true;pause();say('');}else play(true);});
    video.addEventListener('playing',()=>{clearTimeout(timer);ready=true;failed=false;say('');state('playing');});
    video.addEventListener('pause',()=>{clearTimeout(timer);if(ready)state('paused');});
    video.addEventListener('error',()=>{clearTimeout(timer);failed=true;ready=false;blocked=true;video.autoplay=false;video.pause();state('error');say(window.sdsText("Não foi possível carregar o vídeo. A imagem de reserva mantém-se disponível."));});
    // Native controlled video starts only after explicit user interaction.
    if(!animated)video.autoplay=false;
    if(animated&&restricted()){video.autoplay=false;say(window.sdsText("Reprodução automática desactivada pelas preferências de movimento ou de poupança de dados."));}
    const observer='IntersectionObserver' in window?new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(!visible)pause();else if(animated)play();},{threshold:.15}):null;
    if(observer)observer.observe(root);else{visible=true;if(animated)play();}
    const visibility=()=>{if(document.hidden)pause();else if(animated&&visible&&!explicit)play();};
    const preferences=()=>{if(restricted()){pause();explicit=false;say(window.sdsText("Reprodução automática desactivada pelas preferências de movimento ou de poupança de dados."));}else if(animated&&visible)play();};
    document.addEventListener('visibilitychange',visibility);motion.addEventListener?.('change',preferences);connection?.addEventListener?.('change',preferences);
    const dispose=()=>{disposed=true;if(activeAnimation===video)activeAnimation=null;observer?.disconnect();clearTimeout(timer);document.removeEventListener('visibilitychange',visibility);motion.removeEventListener?.('change',preferences);connection?.removeEventListener?.('change',preferences);video.pause();video.removeAttribute('src');video.load();};
    instances.set(root,{dispose});
  }
  document.querySelectorAll('[data-article-cover]').forEach(mount);
  document.addEventListener('cover:mount',event=>mount(event.detail?.root));
  document.addEventListener('cover:dispose',event=>{const root=event.detail?.root;instances.get(root)?.dispose();instances.delete(root);});
})();
