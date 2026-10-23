const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
let fixture;
test.beforeAll(()=>{fixture=JSON.parse(execFileSync('python',['tests/browser/premium_fixture.py'],{encoding:'utf8'}));});
async function cookie(context,value){await context.addCookies([{name:'session',value,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);}
for(const width of [320,768,1440]){
 test(`Premium layout and keyboard at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:900});
  await page.goto('/premium');
  const reject=page.getByRole('button',{name:'Recusar não essenciais',exact:true});
  if(await reject.isVisible())await reject.click();
  await expect(page.getByRole('heading',{level:1})).toHaveText('Mais espaço para aprender.');
  await expect(page.getByText('O conhecimento científico continua aberto')).toBeVisible();
  for(const dark of [false,true]){
   await page.evaluate(dark=>document.documentElement.classList.toggle('dark',dark),dark);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
   await page.screenshot({path:`test-results/premium-${width}-${dark?'dark':'light'}.png`,fullPage:true});
  }
  await page.goto('/premium/biblioteca');
  await page.locator('#premium-kind').focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.locator('#premium-kind')).toHaveValue('course');
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Categoria',{exact:true})).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button',{name:'Filtrar',exact:true})).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(url=>url.pathname==='/premium/biblioteca' && url.searchParams.get('tipo')==='course');
  for(const dark of [false,true]){
   await page.evaluate(dark=>document.documentElement.classList.toggle('dark',dark),dark);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
   await page.screenshot({path:`test-results/library-${width}-${dark?'dark':'light'}.png`,fullPage:true});
  }
 });
}
test('anonymous, free reader and subscriber access are distinct',async({page,context})=>{
 const path=`/premium/conteudos/${fixture.content_id}`;
 let response=await page.goto(path);expect(response.status()).toBe(403);
 expect(await page.content()).not.toContain(fixture.secret);
 await cookie(context,fixture.free_cookie);
 response=await page.goto(path);expect(response.status()).toBe(403);
 expect(await page.content()).not.toContain(fixture.secret);
 await cookie(context,fixture.member_cookie);
 response=await page.goto(path);expect(response.status()).toBe(200);
 await expect(page.getByText(fixture.secret)).toBeVisible();
 expect(response.headers()['cache-control']).toContain('no-store');
});
test('primary admin grants and cancels complimentary access',async({page,context,browser})=>{
 await cookie(context,fixture.admin_cookie);
 await page.goto('/admin/premium/assinaturas/nova');
 await page.getByLabel('Identificador da conta').fill(String(fixture.owner_id));
 await page.getByLabel('Plano',{exact:true}).selectOption(String(fixture.plan_id));
 await page.getByLabel('Início em UTC').fill('2026-01-01T00:00');
 await page.getByLabel('Fim em UTC').fill('2090-01-01T00:00');
 await page.getByLabel('Motivo da oferta').fill('Oferta para ensaio no navegador');
 await page.getByLabel('Confirmo que este acesso é uma oferta sem cobrança.').check();
 await page.getByRole('button',{name:'Conceder acesso',exact:true}).click();
 await expect(page).toHaveURL(/\/admin\/premium\/?$/);
 const row=page.locator('.premium-admin-card').filter({hasText:`Conta #${fixture.owner_id}`});
 await row.getByRole('link',{name:'Gerir acesso'}).click();
 await page.setViewportSize({width:320,height:900});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 const reader=await browser.newContext();await cookie(reader,fixture.free_cookie);
 const readerPage=await reader.newPage();
 expect((await readerPage.goto(`/premium/conteudos/${fixture.content_id}`)).status()).toBe(200);
 await page.getByLabel('Estado',{exact:true}).selectOption('cancelled');
 await page.getByLabel('Motivo da alteração').fill('Cancelamento da oferta de teste');
 await page.getByRole('button',{name:'Guardar alteração'}).click();
 expect((await readerPage.goto(`/premium/conteudos/${fixture.content_id}`)).status()).toBe(403);
 await reader.close();
});

test('library combines search and category without exposing reserved body',async({page})=>{
 await page.goto('/premium/biblioteca');
 await page.getByLabel('Pesquisar recursos',{exact:true}).fill(fixture.title);
 await page.getByLabel('Categoria',{exact:true}).selectOption('Investigação de teste');
 await page.getByRole('button',{name:'Filtrar',exact:true}).click();
 await expect(page.getByRole('heading',{name:fixture.title})).toBeVisible();
 expect(await page.content()).not.toContain(fixture.secret);
 await page.getByLabel('Pesquisar recursos',{exact:true}).fill('sem-resultado-inexistente');
 await page.getByRole('button',{name:'Filtrar',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Sem resultados para estes filtros'})).toBeVisible();
});

for(const width of [320,768,1440]){
 test(`Premium administration layout at ${width}px`,async({page,context})=>{
  await cookie(context,fixture.admin_cookie);
  await page.setViewportSize({width,height:1000});
  await page.goto('/admin/premium/');
  await expect(page.getByRole('navigation',{name:'Gestão Premium'}).getByRole('link',{name:'Visão geral',exact:true})).toHaveAttribute('aria-current','page');
  await expect(page.getByRole('heading',{name:'Planos Premium',exact:true})).toBeVisible();
  for(const dark of [false,true]){
   await page.evaluate(dark=>document.body.classList.toggle('admin-dark',dark),dark);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
   await page.screenshot({path:`test-results/admin-premium-${width}-${dark?'dark':'light'}.png`,fullPage:true});
  }
 });
}
test('a single configured plan stays readable on desktop',async({page})=>{
 await page.setViewportSize({width:1440,height:1000});
 await page.goto('/premium');
 const reject=page.getByRole('button',{name:'Recusar não essenciais',exact:true});
 if(await reject.isVisible())await reject.click();
 // Exercise the one-card layout without changing configured products or prices.
 await page.locator('.premium-plan-card').evaluateAll(cards=>cards.slice(1).forEach(card=>card.remove()));
 const card=page.locator('.premium-plan-card');
 await expect(card).toHaveCount(1);
 const box=await card.boundingBox();
 expect(box.width).toBeLessThanOrEqual(541);
 await card.screenshot({path:'test-results/premium-single-plan.png'});
});
