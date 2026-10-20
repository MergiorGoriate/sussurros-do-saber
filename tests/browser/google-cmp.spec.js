const {test,expect}=require('@playwright/test');
test.skip(process.env.GOOGLE_CMP_ENABLED!=='true','Requires isolated server with GOOGLE_CMP_ENABLED=true');
test('Google CMP message controls become available through API; ads remain paused',async({page})=>{
 await page.route(/googletagmanager\.com|doubleclick\.net/,route=>route.fulfill({contentType:'application/javascript',body:''}));
 await page.route('**/pagead/js/adsbygoogle.js?*',route=>route.fulfill({contentType:'application/javascript',body:`
  window.__pauseAtLoad=window.adsbygoogle.pauseAdRequests;
  if(window.adsbygoogle.some(command=>command.enable_page_level_ads))throw new Error('Only one enable_page_level_ads allowed per page');
  window.googlefc.showRevocationMessage=()=>{window.__revocationCount=(window.__revocationCount||0)+1};
  const callbacks=window.googlefc.callbackQueue.splice(0);
  window.googlefc.callbackQueue.push=entry=>{entry.CONSENT_API_READY?.();return 0};
  callbacks.forEach(entry=>entry.CONSENT_API_READY?.());
 `}));
 await page.goto('/');
 const privacyPanel=page.locator('.footer-privacy');
 await expect(privacyPanel).not.toHaveAttribute('open', '');
 await privacyPanel.locator('summary').click();
 await expect(privacyPanel).toHaveAttribute('open', '');
 const settings=page.locator('#googleCmpSettings');
 await expect(settings).toBeEnabled();
 expect(await page.evaluate(()=>window.__pauseAtLoad)).toBe(1);
 await settings.click();
 expect(await page.evaluate(()=>window.__revocationCount)).toBe(1);
 expect(await page.evaluate(()=>window.adsbygoogle.pauseAdRequests)).toBe(1);
 await page.locator('#cookieReject').click();
 expect(await page.evaluate(()=>window.adsbygoogle.pauseAdRequests)).toBe(1);
 await page.goto('/artigo/nao-existe-cmp');
 await expect(page.locator('script[src*="google-cmp.js"]')).toHaveCount(0);
});
test('failed CMP reports unavailable and cannot enable advertisements',async({page})=>{
 await page.route('**/pagead/js/adsbygoogle.js?*',route=>route.abort());
 await page.goto('/');
 const privacyPanel=page.locator('.footer-privacy');
 await expect(privacyPanel).not.toHaveAttribute('open', '');
 await privacyPanel.locator('summary').click();
 await expect(privacyPanel).toHaveAttribute('open', '');
 await expect(page.locator('#googleCmpStatus')).toContainText('Não foi possível carregar');
 await expect(page.locator('#googleCmpSettings')).toBeEnabled();
 await expect(page.locator('#googleCmpSettings')).toContainText('Tentar carregar');
 expect(await page.evaluate(()=>window.adsbygoogle.pauseAdRequests)).toBe(1);
});


test('slow CMP recovers after the initial waiting period',async({page})=>{
 await page.clock.install();
 await page.route('**/pagead/js/adsbygoogle.js?*',route=>route.fulfill({contentType:'application/javascript',body:`
  setTimeout(()=>{
   window.googlefc.showRevocationMessage=()=>{};
   window.googlefc.callbackQueue.splice(0).forEach(entry=>{entry.CONSENT_API_READY?.();entry.CONSENT_DATA_READY?.()});
  },20000);
 `}));
 await page.goto('/');
 const privacyPanel=page.locator('.footer-privacy');
 await expect(privacyPanel).not.toHaveAttribute('open', '');
 await privacyPanel.locator('summary').click();
 await expect(privacyPanel).toHaveAttribute('open', '');
 await page.clock.fastForward(11000);
 await expect(page.locator('#googleCmpStatus')).toContainText('ainda não disponibilizou');
 await page.clock.fastForward(10000);
 await expect(page.locator('#googleCmpStatus')).toContainText('geridas pelo Google');
 await expect(page.locator('#googleCmpSettings')).toHaveText('Gerir consentimento de publicidade');
 expect(await page.evaluate(()=>window.adsbygoogle.pauseAdRequests)).toBe(1);
});
test('confirmed non-applicable region does not display a CMP failure',async({page})=>{
 await page.route('**/pagead/js/adsbygoogle.js?*',route=>route.fulfill({contentType:'application/javascript',body:`
  window.googlefc.showRevocationMessage=()=>{};
  window.__tcfapi=(command,version,callback)=>callback({gdprApplies:false},true);
  window.googlefc.callbackQueue.splice(0).forEach(entry=>{entry.CONSENT_API_READY?.();entry.CONSENT_DATA_READY?.()});
 `}));
 await page.goto('/');
 const privacyPanel=page.locator('.footer-privacy');
 await expect(privacyPanel).not.toHaveAttribute('open', '');
 await privacyPanel.locator('summary').click();
 await expect(privacyPanel).toHaveAttribute('open', '');
 await expect(page.locator('#googleCmpStatus')).toContainText('não se aplica');
 await expect(page.locator('#googleCmpSettings')).toBeHidden();
 expect(await page.evaluate(()=>window.adsbygoogle.pauseAdRequests)).toBe(1);
});

