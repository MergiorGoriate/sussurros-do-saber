const {test,expect}=require('@playwright/test');

test.beforeEach(async({context,page})=>{
 await context.addCookies([{name:'cookie_consent_v3',value:encodeURIComponent(JSON.stringify({essential:true,analytics:false,ads:false,updatedAt:new Date().toISOString()})),url:'http://127.0.0.1:5000'}]);
 await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
});

for(const width of [320,768,900])test(`navigation and search fit and restore keyboard focus at ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:844});await page.goto('/');
 const menu=page.getByRole('button',{name:'Abrir menu',exact:true});
 await expect(menu).toBeVisible();await menu.click();
 await expect(page.locator('#mainNav')).toBeVisible();
 for(const link of await page.locator('#mainNav a').all()){
  const box=await link.boundingBox();expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(width);expect(box.height).toBeGreaterThanOrEqual(44);
 }
 await page.locator('#mainNav a').first().focus();await page.keyboard.press('Escape');
 await expect(page.locator('#mainNav')).toBeHidden();await expect(menu).toBeFocused();
 await menu.click();await page.getByRole('button',{name:'Abrir pesquisa',exact:true}).click();
 await expect(page.locator('#mainNav')).toBeHidden();await expect(page.locator('#siteSearch')).toBeFocused();
 await page.keyboard.press('Escape');await expect(page.locator('#searchPanel')).toBeHidden();await expect(page.locator('#searchToggle')).toBeFocused();
 await menu.click();await page.setViewportSize({width:1280,height:844});
 await expect(page.locator('#mainNav')).toBeVisible();await expect(page.locator('#menuToggle')).toBeHidden();await expect(page.locator('#menuToggle')).toHaveAttribute('aria-expanded','false');
});

test('mobile forms and submission navigation have usable touch targets',async({page})=>{
 await page.setViewportSize({width:320,height:844});await page.goto('/contacto');
 const send=page.getByRole('button',{name:'Enviar mensagem',exact:true});
 expect((await send.boundingBox()).height).toBeGreaterThanOrEqual(44);
 for(const route of ['/submissoes/','/submissoes/nova']){
  await page.goto(route);
  for(const link of await page.locator('.submission-header nav a').all())expect((await link.boundingBox()).height).toBeGreaterThanOrEqual(44);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
 }
});

test('signed-in header fits at 320px with and without an account photo',async({page})=>{
 await page.setViewportSize({width:320,height:844});
 let picture='';
 await page.route('**/conta/sessao',route=>route.fulfill({json:{ok:true,authenticated:true,csrf:'mobile-fixture',picture,notification_count:12,saved_articles:[]}}));
 for(const photo of ['', '/static/img/favicon.png']){
  picture=photo;await page.goto('/');await expect(page.getByRole('button',{name:'Abrir a minha conta',exact:true})).toBeVisible();
  await expect(page.locator('.reader-header-notifications')).toBeVisible();
  for(const target of await page.locator('.reader-header-controls > :visible').all()){
   const box=await target.boundingBox();expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(320);expect(box.height).toBeGreaterThanOrEqual(44);
  }
 }
});
