/* Microsoft Clarity: no vendor request until optional analytics is accepted. */
(()=>{
  const ownScript=document.currentScript;
  const project=ownScript?.dataset.projectId;
  if(!/^[a-z0-9]{5,32}$/.test(project||'')||window.sdsClarityInitialized)return;
  window.sdsClarityInitialized=true;
  let loaded=false;
  const choice=()=>{
    try{
      const raw=document.cookie.split('; ').find(item=>item.startsWith('cookie_consent_v3='));
      if(!raw)return false;
      const value=JSON.parse(decodeURIComponent(raw.slice('cookie_consent_v3='.length)));
      const age=Date.now()-Date.parse(value.updatedAt);
      return value.essential===true&&value.analytics===true&&typeof value.ads==='boolean'
        &&Number.isFinite(age)&&age>=0&&age<15552000000;
    }catch{return false}
  };
  const mask=()=>document.querySelectorAll('form, input, textarea, select, #comentarios, #assistantWindow, .assistant-messages')
    .forEach(element=>element.setAttribute('data-clarity-mask','true'));
  const clearCookies=()=>{
    const parts=location.hostname.split('.');
    const domains=['',...parts.slice(0,-1).map((_,i)=>'; Domain=.'+parts.slice(i).join('.'))];
    for(const name of ['_clck','_clsk'])for(const domain of domains)
      document.cookie=name+'=; Max-Age=0; Path=/; SameSite=Lax'+domain;
  };
  const update=()=>{
    const accepted=choice(); // Stored choice is authoritative, never event payloads.
    if(!accepted){
      if(loaded&&typeof window.clarity==='function')
        window.clarity('consentv2',{analytics_Storage:'denied',ad_Storage:'denied'});
      clearCookies();
      return;
    }
    if(!loaded){
      loaded=true;
      mask();
      if(typeof MutationObserver==='function')new MutationObserver(mask)
        .observe(document.documentElement,{childList:true,subtree:true});
      window.clarity=window.clarity||function(){(window.clarity.q=window.clarity.q||[]).push(arguments)};
      window.clarity('consentv2',{analytics_Storage:'granted',ad_Storage:'denied'});
      const script=document.createElement('script');
      script.async=true;
      if(ownScript.nonce)script.nonce=ownScript.nonce;
      script.src='https://www.clarity.ms/tag/'+project+'?ref=bwt';
      document.head.appendChild(script);
    }else window.clarity('consentv2',{analytics_Storage:'granted',ad_Storage:'denied'});
  };
  window.addEventListener('cookieconsentchange',update);
  update();
})();
