const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');

test('signed cancellation needs confirmation and allows a later subscription',async({page})=>{
  const data=JSON.parse(execFileSync('python',['tests/browser/newsletter_fixture.py'],{encoding:'utf8'}));
  await page.goto(data.path);
  await expect(page.getByRole('heading',{name:'Cancelar o boletim',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Cancelar inscrição',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Inscrição cancelada',exact:true})).toBeVisible();
  await page.goto('/');
  const refuse=page.getByRole('button',{name:'Recusar não essenciais',exact:true});
  if(await refuse.isVisible())await refuse.click();
  const form=page.locator('#newsletterForm');
  await form.locator('input[type=email]').fill(data.email);
  await form.getByRole('button',{name:'Subscrever',exact:true}).click();
  await expect(page.locator('#newsletterMessage')).toContainText('Inscrição confirmada');
  await expect(form.locator('input[type=email]')).toHaveValue('');
});
