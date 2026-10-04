(() => {
  const dialog=document.getElementById('reader-dialog'),form=document.getElementById('reader-auth-form');
  if(!dialog||!form)return;
  const status=document.getElementById('reader-auth-status');
  let mode='login',csrf='',pending=null,opener=null;
  const api=async(path,data)=>{
    const response=await fetch(path,{method:data?'POST':'GET',body:data,credentials:'same-origin',headers:{Accept:'application/json'}});
    const result=await response.json().catch(()=>({ok:false,message:'Não foi possível concluir. Tente novamente.'}));
    if(!response.ok||!result.ok){const error=new Error(result.message||'Não foi possível concluir. Tente novamente.');error.code=response.status;throw error;}
    return result;
  };
  const sessionState=async()=>{const state=await api('/conta/sessao');csrf=state.csrf;return state;};
  const setMode=value=>{
    mode=value;const register=mode==='register';
    document.getElementById('reader-name-label').hidden=!register;
    form.elements.name.required=register;
    form.elements.password.minLength=register?12:1;
    form.elements.password.autocomplete=register?'new-password':'current-password';
    document.getElementById('reader-password-help').hidden=!register;
    document.getElementById('reader-submit').textContent=register?'Criar conta':'Entrar';
    dialog.querySelectorAll('[data-reader-mode]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.readerMode===mode)));
    status.textContent='';
  };
  const open=async(button,callback)=>{
    opener=button;pending=callback;setMode('login');dialog.showModal();form.elements.email.focus();
    try{await sessionState();}catch(error){status.textContent=error.message;}
  };
  dialog.querySelectorAll('[data-reader-mode]').forEach(button=>button.addEventListener('click',()=>setMode(button.dataset.readerMode)));
  dialog.querySelector('[data-reader-close]').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>{form.elements.password.value='';pending=null;opener?.focus();});
  document.querySelectorAll('[data-reader-open]').forEach(button=>button.addEventListener('click',()=>open(button,()=>location.reload())));
  form.addEventListener('submit',async event=>{
    event.preventDefault();const submit=document.getElementById('reader-submit');submit.disabled=true;status.textContent='A processar...';
    try{
      if(!csrf)await sessionState();
      const data=new FormData(form);data.set('csrf_token',csrf);
      const result=await api('/conta/'+(mode==='register'?'criar-conta':'entrar'),data);
      form.elements.password.value='';
      if(mode==='register'){setMode('login');status.textContent=result.message;return;}
      csrf=result.csrf;const callback=pending;dialog.close();if(callback)await callback();
    }catch(error){status.textContent=error.message;}
    finally{submit.disabled=false;}
  });
  const root=document.querySelector('[data-reader-journal]');
  if(!root)return;
  const slug=root.dataset.readerJournal;
  const save=root.querySelector('.journal-save-btn'),alert=root.querySelector('.journal-alert-btn');
  const message=document.getElementById('journal-action-status');
  let values={saved:false,following:false};
  const render=()=>{for(const [button,key,icon] of [[save,'saved','bookmark'],[alert,'following','bell']]){
    button?.setAttribute('aria-pressed',String(values[key]));
    const image=button?.querySelector('i');if(image)image.className=(values[key]?'fa-solid':'fa-regular')+' fa-'+icon;
  }};
  const load=async()=>{const state=await sessionState();if(state.authenticated)values=await api('/conta/revistas/'+encodeURIComponent(slug));else values={saved:false,following:false};render();};
  const toggle=async(key)=>{
    const data=new FormData();data.set('csrf_token',csrf);data.set('action',key);data.set('enabled',String(!values[key]));
    values=await api('/conta/revistas/'+encodeURIComponent(slug),data);render();
    message.textContent=key==='saved'?(values.saved?'Artigo guardado na sua conta. Consulte Os meus favoritos.':'Artigo removido dos favoritos.'):(values.following?'Notificações activadas. Consulte a página Notificações para ver actualizações deste artigo.':'Notificações desactivadas.');
  };
  for(const [button,key] of [[save,'saved'],[alert,'following']])button?.addEventListener('click',async()=>{
    button.disabled=true;
    const complete=async()=>{try{await load();await toggle(key);}catch(error){message.textContent=error.message;}};
    try{const state=await sessionState();if(!state.authenticated)await open(button,complete);else await complete();}
    catch(error){message.textContent=error.message;}
    finally{button.disabled=false;}
  });
  load().catch(()=>{message.textContent='Não foi possível consultar a conta. Pode tentar novamente ao clicar no ícone.';});
})();
