/* Private draft autosave. Never persists article text in browser storage. */
(() => {
  const form=document.querySelector('form[data-autosave-url]');
  const status=document.querySelector('#editorAutosaveStatus');
  const retry=document.querySelector('#retryAutosave');
  if(!form||!status||!retry)return;
  const banner=status.closest('.editor-autosave');
  const show=(message,state='',canRetry=false)=>{
    status.textContent=message;banner.dataset.state=state;retry.hidden=!canRetry;
  };
  const url=form.dataset.autosaveUrl;
  if(!url)return;
  if(form.dataset.articleStatus!=='draft'){
    show('Gravação automática pausada: guarde manualmente como rascunho antes de continuar.');return;
  }
  const fields=['title','summary','body','references','keywords','doi','read_minutes'];
  const state=()=>JSON.stringify(Array.from(new FormData(form)).filter(([key,value])=>typeof value==='string'&&!['csrf_token','version_token'].includes(key)));
  const protectedState=()=>JSON.stringify(Array.from(new FormData(form)).filter(([key,value])=>typeof value==='string'&&!fields.includes(key)&&!['csrf_token','version_token'].includes(key)));
  let saved=state(), protectedSaved=protectedState(), timer=null, inFlight=null, lastSaved=0, stopped=false, submitting=false;
  const hasFiles=()=>Array.from(form.querySelectorAll('input[type=file]')).some(input=>input.files.length);
  const hasChanges=()=>state()!==saved;
  const schedule=()=>{
    clearTimeout(timer);
    if(stopped||submitting||!hasChanges())return;
    timer=setTimeout(save,Math.max(2000,30000-(Date.now()-lastSaved)));
  };
  function save(force=false){
    clearTimeout(timer);
    if(inFlight||stopped||submitting||!hasChanges())return inFlight;
    if(hasFiles()||protectedState()!==protectedSaved){
      show('Gravação automática pausada: use Guardar artigo para guardar alterações às opções, autoria, categoria ou ficheiros.');return;
    }
    if(fields.some(name=>!form.elements.namedItem(name)?.checkValidity())){
      show('Gravação automática pausada: reveja o título, o resumo e os campos assinalados.');return;
    }
    if(!navigator.onLine){show('Sem ligação. O texto continua neste editor; mantenha esta página aberta até confirmar a gravação.','error',true);return;}
    if(!force&&Date.now()-lastSaved<30000){schedule();return;}
    const fingerprint=state(), payload=new URLSearchParams();
    for(const name of [...fields,'csrf_token','version_token'])payload.set(name,form.elements.namedItem(name)?.value||'');
    show('A guardar rascunho…');banner.setAttribute('aria-busy','true');retry.disabled=true;
    const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),15000);
    inFlight=(async()=>{
      try{
        const response=await fetch(url,{method:'POST',body:payload,credentials:'same-origin',cache:'no-store',signal:controller.signal});
        if(response.redirected||response.status===401||response.status===403){
          stopped=true;show('A sessão ou as permissões mudaram. O texto continua neste editor; copie-o antes de iniciar sessão novamente.','error');return;
        }
        const data=await response.json();
        if(!response.ok||data.ok!==true){
          stopped=response.status===409;
          show(data.error||'Não foi possível guardar. O texto continua no editor.','error',!stopped);return;
        }
        if(typeof data.version_token!=='string')throw new Error('invalid response');
        form.elements.namedItem('version_token').value=data.version_token;
        saved=fingerprint;lastSaved=Date.now();
        form.dispatchEvent(new CustomEvent('editor:autosaved',{detail:{fingerprint}}));
        const time=new Date(data.saved_at+'Z').toLocaleTimeString('pt-MZ',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
        show(hasChanges()?'Há alterações pendentes; serão guardadas automaticamente.':'Guardado automaticamente às '+time+'.');
      }catch(_){
        show('Não foi possível confirmar a gravação. O texto continua neste editor; mantenha a página aberta e tente novamente.','error',true);
      }finally{
        clearTimeout(timeout);inFlight=null;retry.disabled=false;banner.removeAttribute('aria-busy');
        if(hasChanges()&&banner.dataset.state!=='error')schedule();
      }
    })();
    return inFlight;
  }
  form.addEventListener('input',schedule);
  form.addEventListener('change',schedule);
  form.querySelector('#bodyEditor')?.addEventListener('editor:rendered',schedule);
  retry.addEventListener('click',()=>save(true));
  window.addEventListener('online',schedule);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)save(true);});
  form.addEventListener('submit',event=>{
    clearTimeout(timer);
    if(inFlight){
      event.preventDefault();event.stopImmediatePropagation();
      const pending=inFlight, submitter=event.submitter;
      pending.then(()=>{if(!stopped&&form.isConnected){if(submitter)form.requestSubmit(submitter);else form.requestSubmit();}});
      return;
    }
    submitting=true;
  },true);
  show('Gravação automática activa para o texto deste rascunho. As versões ficam disponíveis no histórico.');
})();
