/* Google Privacy & messaging bootstrap. No ad inventory is enabled here.
 * Official deployment: the AdSense tag obtains messages published in the account.
 * https://developers.google.com/funding-choices/fc-api-docs
 * https://support.google.com/adsense/answer/9042142
 */
(()=>{
  'use strict';
  const button=document.getElementById('googleCmpSettings');
  const status=document.getElementById('googleCmpStatus');
  if(!button||!status)return;
  // Set the documented pause before appending the asynchronous Google tag.
  // Neither a local cookie nor CMP readiness is permission to unpause ads.
  window.adsbygoogle=window.adsbygoogle||[];
  window.adsbygoogle.pauseAdRequests=1;
  window.googlefc=window.googlefc||{};
  window.googlefc.callbackQueue=window.googlefc.callbackQueue||[];
  let ready=false;
  const unavailable=()=>{
    if(ready)return;
    button.disabled=true;
    status.textContent='As opções de publicidade do Google estão indisponíveis. Os anúncios continuam suspensos. Pode tentar novamente ao recarregar a página.';
  };
  const timer=setTimeout(unavailable,10000);
  window.googlefc.callbackQueue.push({CONSENT_API_READY:()=>{
    if(typeof window.googlefc.showRevocationMessage!=='function'){unavailable();return}
    ready=true;
    clearTimeout(timer);
    button.disabled=false;
    status.textContent='As escolhas de publicidade são geridas pelo Google. Os anúncios continuam suspensos.';
  }});
  button.addEventListener('click',()=>{
    if(!ready)return;
    window.adsbygoogle.pauseAdRequests=1;
    // Run every Google function via its supported asynchronous callback queue.
    window.googlefc.callbackQueue.push({CONSENT_API_READY:()=>{
      if(typeof window.googlefc.showRevocationMessage==='function'){
        window.googlefc.showRevocationMessage();
      }
    }});
  });
  const script=document.createElement('script');
  script.async=true;
  script.crossOrigin='anonymous';
  script.src='https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-7920973591685812';
  script.addEventListener('error',unavailable,{once:true});
  document.head.appendChild(script);
})();
