const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');

test('delivery controls preserve responsive themes and require explicit authorisation',async({page,context})=>{
  const fixture=JSON.parse(execFileSync('python',['tests/browser/mail_delivery_fixture.py'],{encoding:'utf8'}));
  const cookie=execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();
  await context.addCookies([{name:'session',value:cookie,domain:'127.0.0.1',path:'/'}]);
  await page.goto('/admin/subscritores');
  await expect(page.getByRole('heading',{name:'Limites e entrega',exact:true})).toBeVisible();
  for(const width of [320,390,768,1440]){
    await page.setViewportSize({width,height:1000});
    for(const dark of [false,true]){
      await page.evaluate(value=>document.body.classList.toggle('admin-dark',value),dark);
      await expect(page.getByRole('button',{name:'Pausar todos os envios',exact:true})).toBeVisible();
      await expect(page.getByRole('button',{name:'Retomar todos os envios',exact:true})).toBeVisible();
      await page.getByText('Editar limites e quotas',{exact:true}).click();
      await expect(page.getByLabel('Limite interno por hora',{exact:true})).toBeVisible();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
      await page.getByText('Editar limites e quotas',{exact:true}).click();
    }
  }
  await page.getByRole('button',{name:'Pausar todos os envios',exact:true}).click();
  await expect(page.locator('.mail-delivery [role=status]')).toContainText('Pausa administrativa');
  await page.getByRole('button',{name:'Retomar todos os envios',exact:true}).click();
  await expect(page.locator('.mail-delivery [role=status]')).toContainText('Disponível');
  await expect(page.getByText('Quotas do fornecedor desconhecidas ou incompletas.',{exact:false})).toBeVisible();
  await page.goto('/admin/subscritores?campaign='+fixture.campaign_id);
  await expect(page.getByRole('button',{name:'Aprovar campanha',exact:true})).toBeVisible();
  await page.getByLabel('Revi o conteúdo guardado e aprovo esta campanha.',{exact:false}).check();
  await page.getByRole('button',{name:'Aprovar campanha',exact:true}).click();
  await expect(page.getByRole('button',{name:'Autorizar processamento agora',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Autorizar processamento agora',exact:true}).click();
  await expect(page.getByRole('heading',{name:/2099-W50.*Agendada/})).toBeVisible();
});
