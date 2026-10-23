const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
let fixture;
test.beforeAll(()=>{fixture=JSON.parse(execFileSync('python',['tests/browser/billing_fixture.py'],{encoding:'utf8'}));});
test.beforeEach(async({context})=>{await context.addCookies([{name:'session',value:fixture.cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);});
test('payment history shows clear financial states without enabling test access',async({page})=>{
 await page.goto('/premium/pagamentos');
 await expect(page.getByRole('heading',{name:'A minha assinatura',exact:true})).toBeVisible();
 for(const text of ['Pendente','Confirmado','Recusado','Expirado'])await expect(page.getByText(`${text} · Teste`,{exact:true})).toBeVisible();
 for(const width of [320,768,1440]){
  await page.setViewportSize({width,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 }
});
test('pending payment and disabled checkout do not request card data',async({page})=>{
 await page.goto(`/premium/pagamentos/${fixture.orders.pending}`);
 await expect(page.getByRole('heading',{name:'Pendente',exact:true})).toBeVisible();
 await expect(page.getByText('Teste: este pedido não activa acesso real.',{exact:true})).toBeVisible();
 await page.goto(`/premium/aderir/${fixture.plan}`);
 await expect(page.getByText('Os pagamentos deste plano ainda não estão disponíveis. Nenhuma cobrança foi iniciada.',{exact:true})).toBeVisible();
 await expect(page.locator('input[autocomplete="cc-number"],input[name="pan"],input[name="cvv"],input[name="card_number"]')).toHaveCount(0);
});

test('confirmation retains accessible layout at mobile, tablet and desktop widths',async({page})=>{
 await page.goto(`/premium/aderir/${fixture.plan}`);
 await expect(page.getByRole('heading',{name:'Confirmar subscrição',exact:true})).toBeVisible();
 for(const width of [320,768,1440]){
  await page.setViewportSize({width,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  await page.screenshot({path:`test-results/subscription-confirm-${width}.png`,fullPage:true});
 }
 await page.goto(`/premium/pagamentos/${fixture.orders.paid}`);
 await expect(page.getByRole('link',{name:'Descarregar comprovativo PDF'})).toBeVisible();
});

test('monthly and annual plan survive authentication in the existing account form',async({page,context})=>{
 for(const ident of [fixture.plan,fixture.annual]){
  await context.clearCookies();
  await page.goto(`/premium/aderir/${ident}`);
  await expect(page).toHaveURL(/submissoes\/entrar/);
  const form=page.locator('form').filter({has:page.locator('input[name="premium_return"]')});
  await form.locator('input[name="email"]').fill(fixture.email);
  await form.locator('input[name="password"]').fill(fixture.password);
  await form.getByRole('button',{name:'Entrar',exact:true}).click();
  await expect(page).toHaveURL(new RegExp(`/premium/aderir/${ident}$`));
  await expect(page.getByRole('heading',{name:'Confirmar subscrição',exact:true})).toBeVisible();
 }
});
