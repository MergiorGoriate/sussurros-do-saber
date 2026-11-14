const {test,expect}=require('@playwright/test');

test('Clarity respects rejection, acceptance and withdrawal without live telemetry',async({page})=>{
 const tags=[];
 await page.route(/googletagmanager\.com|googlesyndication\.com|doubleclick\.net/,r=>r.fulfill({contentType:'application/javascript',body:''}));
 await page.route(/https:\/\/[^/]*clarity\.ms\//,async route=>{
   tags.push(route.request().url());
   await route.fulfill({contentType:'application/javascript',body:`
     const queued=window.clarity.q||[];
     window.clarity=(...args)=>{
       const calls=JSON.parse(sessionStorage.getItem('clarity-test-calls')||'[]');
       calls.push(args);sessionStorage.setItem('clarity-test-calls',JSON.stringify(calls));
     };
     for(const args of queued)window.clarity(...args);
   `});
 });
 await page.goto('/idioma/pt');await page.goto('/');
 // CI disables the project globally so unrelated tests cannot send real data.
 // Mount the real local loader only after the vendor route has been mocked.
 if(await page.locator('script[src*="js/clarity.js"]').count()===0){
   await page.evaluate(()=>new Promise((resolve,reject)=>{
     const script=document.createElement('script');
     script.src='/static/js/clarity.js';script.dataset.projectId='zdbchcjjtg';
     script.nonce=document.querySelector('script[nonce]').nonce;
     script.onload=resolve;script.onerror=reject;document.head.appendChild(script);
   }));
 }
 await page.locator('#cookieReject').click();
 expect(tags).toEqual([]);
 await page.locator('#cookieSettingsLink').click();await page.locator('#cookieAccept').click();
 await expect.poll(()=>tags.length).toBe(1);
 expect(tags[0]).toBe('https://www.clarity.ms/tag/zdbchcjjtg?ref=bwt');
 await expect(page.locator('#searchPanel')).toHaveAttribute('data-clarity-mask','true');
 await page.evaluate(()=>{const form=document.createElement('form');form.id='dynamic-private-test';document.body.appendChild(form)});
 await expect(page.locator('#dynamic-private-test')).toHaveAttribute('data-clarity-mask','true');
 await page.locator('#cookieSettingsLink').click();
 await Promise.all([page.waitForEvent('load'),page.locator('#cookieReject').click()]);
 const calls=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('clarity-test-calls')));
 expect(calls.some(x=>x[0]==='consentv2'&&x[1].analytics_Storage==='granted'&&x[1].ad_Storage==='denied')).toBe(true);
 expect(calls.at(-1)).toEqual(['consentv2',{analytics_Storage:'denied',ad_Storage:'denied'}]);
 expect(tags).toHaveLength(1);
});

test('Clarity is excluded from search queries and private pages despite stored analytics consent',async({page,context})=>{
 await context.addCookies([{name:'cookie_consent_v3',value:encodeURIComponent(JSON.stringify({essential:true,analytics:true,ads:false,updatedAt:new Date().toISOString()})),url:'http://127.0.0.1:5000'}]);
 const tags=[];await page.route(/clarity\.ms/,r=>{tags.push(r.request().url());return r.fulfill({body:''})});
 await page.route(/googletagmanager\.com/,r=>r.fulfill({body:''}));
 for(const path of ['/artigos?q=private','/admin/login','/conta/biblioteca','/contacto']){
   await page.goto(path);await expect(page.locator('script[src*="js/clarity.js"]')).toHaveCount(0);
 }
 expect(tags).toEqual([]);
});
