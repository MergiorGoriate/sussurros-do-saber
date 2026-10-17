const {test,expect}=require('@playwright/test');
test.skip(process.env.GOOGLE_CMP_ENABLED!=='true','Requires isolated server with GOOGLE_CMP_ENABLED=true');
test('Google CMP message controls become available through API; ads remain paused',async({page})=>{
 await page.route(/googletagmanager\.com|doubleclick\.net/,route=>route.fulfill({contentType:'application/javascript',body:''}));
 await page.route('**/pagead/js/adsbygoogle.js?*',route=>route.fulfill({contentType:'application/javascript',body:`
  window.__pauseAtLoad=window.adsbygoogle.pauseAdRequests;
  window.googlefc.showRevocationMessage=()=>{window.__revocationCount=(window.__revocationCount||0)+1};
  const callbacks=window.googlefc.callbackQueue.splice(0);
  window.googlefc.callbackQueue.push=entry=>{entry.CONSENT_API_READY?.();return 0};
  callbacks.forEach(entry=>entry.CONSENT_API_READY?.());
 `}));
 await page.goto('/');
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
 await expect(page.locator('#googleCmpStatus')).toContainText('indisponíveis');
 await expect(page.locator('#googleCmpSettings')).toBeDisabled();
 expect(await page.evaluate(()=>window.adsbygoogle.pauseAdRequests)).toBe(1);
});
