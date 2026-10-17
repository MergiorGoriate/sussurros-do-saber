/* Google Privacy & messaging: initialise the documented paused Auto ads tag.
 * https://developers.google.com/funding-choices/fc-api-docs
 * https://support.google.com/adsense/answer/9042142
 */
(()=>{
  'use strict';
  const button=document.getElementById('googleCmpSettings');
  const status=document.getElementById('googleCmpStatus');
  if(!button||!status||window.sdsGoogleCmpBootstrapped)return;
  window.sdsGoogleCmpBootstrapped=true;
  window.adsbygoogle=window.adsbygoogle||[];
  window.adsbygoogle.pauseAdRequests=1;
  window.googlefc=window.googlefc||{};
  window.googlefc.callbackQueue=window.googlefc.callbackQueue||[];
  let ready=false,notApplicable=false,listening=false,retry=false;
  const label=button.textContent;
  const report=(message,canRetry)=>{
    if(ready||notApplicable)return;
    status.textContent=message;
    retry=canRetry;
    button.disabled=!canRetry;
    button.textContent=canRetry?'Tentar carregar as opções de publicidade':label;
  };
  const timer=setTimeout(()=>report('O Google ainda não disponibilizou as opções de publicidade para esta visita. Os anúncios continuam suspensos.',true),10000);
  const unavailable=()=>{
    clearTimeout(timer);
    report('Não foi possível carregar as opções de publicidade do Google. Os anúncios continuam suspensos.',true);
  };
  const updateReady=()=>{
    if(notApplicable)return;
    if(typeof window.googlefc.showRevocationMessage!=='function')return;
    ready=true;retry=false;
    clearTimeout(timer);
    button.hidden=false;
    button.disabled=false;
    button.textContent=label;
    status.textContent='As escolhas de publicidade são geridas pelo Google. Os anúncios continuam suspensos.';
  };
  window.googlefc.callbackQueue.push({CONSENT_API_READY:()=>{
    updateReady();
    if(listening||typeof window.__tcfapi!=='function')return;
    listening=true;
    // Read applicability from the real CMP; never infer location from a timeout.
    window.__tcfapi('addEventListener',0,(data,success)=>{
      if(!success||!data)return;
      if(data.gdprApplies===false){
        notApplicable=true;ready=false;retry=false;
        clearTimeout(timer);
        button.hidden=true;button.disabled=true;
        status.textContent='Segundo o Google, a mensagem de consentimento europeu não se aplica a esta visita. Os anúncios continuam suspensos.';
      }else if(data.gdprApplies===true){
        notApplicable=false;
        updateReady();
      }
    });
  }});
  // Methods may become available after the framework API or after a slow response.
  window.googlefc.callbackQueue.push({CONSENT_DATA_READY:updateReady});
  button.addEventListener('click',()=>{
    if(retry){window.location.reload();return}
    if(!ready||notApplicable)return;
    window.adsbygoogle.pauseAdRequests=1;
    window.googlefc.callbackQueue.push({CONSENT_API_READY:()=>{
      if(typeof window.googlefc.showRevocationMessage==='function')window.googlefc.showRevocationMessage();
    }});
  });
  // Initialising the publisher tag is separate from resuming ad requests.
  // The Google example queues this command while pauseAdRequests remains 1.
  window.adsbygoogle.push({google_ad_client:'ca-pub-7920973591685812',enable_page_level_ads:true});
  const script=document.createElement('script');
  script.async=true;
  script.crossOrigin='anonymous';
  script.src='https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-7920973591685812';
  script.addEventListener('error',unavailable,{once:true});
  document.head.appendChild(script);
})();
