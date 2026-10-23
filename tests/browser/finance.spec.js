const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
let admin;
test.beforeAll(()=>{
 execFileSync('python',['tests/browser/billing_fixture.py'],{encoding:'utf8'});
 admin=JSON.parse(execFileSync('python',['tests/browser/premium_fixture.py'],{encoding:'utf8'}));
});
for(const width of [320,768,1440]){
 test(`financial administration layout at ${width}px`,async({page,context})=>{
  await context.addCookies([{name:'session',value:admin.admin_cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
  await page.setViewportSize({width,height:1000});
  const writes=[];page.on('request',request=>{if(request.method()==='POST')writes.push(request.url());});
  await page.goto('/admin/premium/financeiro');
  await expect(page.getByRole('heading',{name:'Gestão financeira do Premium',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Movimentos financeiros',exact:true})).toBeVisible();
  await expect(page.locator('.premium-finance-balance').filter({hasText:'Teste'}).first()).toBeVisible();
  await expect(page.getByRole('link',{name:'Exportar diário financeiro CSV',exact:true})).toHaveAttribute('href','/admin/premium/financeiro/exportar.csv');
  const form=page.locator('.premium-finance-order form').first();
  await expect(form).toHaveAttribute('method','post');
  await expect(form.locator('input[name="csrf_token"]')).toHaveAttribute('value',/.+/);
  await page.getByText('Como interpretar estes valores',{exact:true}).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByText(/Taxas, liquidação bancária e reconhecimento de receita/)).toBeVisible();
  for(const dark of [false,true]){
   await page.evaluate(dark=>document.body.classList.toggle('admin-dark',dark),dark);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
   await page.screenshot({path:`test-results/finance-${width}-${dark?'dark':'light'}.png`,fullPage:true});
  }
  expect(writes).toEqual([]);
 });
}
