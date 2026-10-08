const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
function fixture(mode='grant') {
  return JSON.parse(execFileSync('python',['tests/browser/permissions_fixture.py',mode],{encoding:'utf8'}));
}
test('collaborator grants expose and execute actions, revocation works in the same session',async ({page})=>{
  const data=fixture();
  await page.context().addCookies([{name:'session',value:data.cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
  for(const width of [1440,390]) {
    await page.setViewportSize({width,height:1000});
    await page.goto('/admin/trabalho');
    for(const label of ['Artigos','Contactos','Submissões','Relatórios e auditoria','Distribuir tarefas'])
      await expect(page.getByRole('navigation').getByRole('link',{name:label,exact:true})).toBeVisible();
    await expect(page.locator('#distribuir-tarefa')).toBeVisible();
    await expect(page.getByRole('region',{name:'Resumo do trabalho'})).toBeVisible();
    const mandates=page.locator('summary').filter({hasText:'Mandatos válidos'});
    await mandates.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading',{name:'Secretariado — teste isolado',exact:true})).toBeVisible();
    await page.screenshot({path:`test-results/workspace-${width}.png`,fullPage:true});
  }
  const form=page.locator('#distribuir-tarefa form');
  const title='Tarefa isolada '+Date.now();
  await form.locator('[name="title"]').fill(title);
  await form.locator('[name="assignee_id"]').selectOption(String(data.member_id));
  await form.locator('[name="due_on"]').fill('2099-01-01');
  await form.getByRole('button',{name:'Atribuir tarefa'}).click();
  await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
  const task=page.locator('.workspace-task').filter({has:page.getByRole('heading',{name:title,exact:true})});
  await task.locator('[name="status"]').selectOption('in_progress');
  await task.locator('[name="comment"]').fill('Comentário de acompanhamento isolado.');
  await task.getByRole('button',{name:'Actualizar',exact:true}).click();
  await expect(task.locator('header')).toContainText('Em curso');
  await task.locator('summary').click();
  await expect(task.getByText('Comentário de acompanhamento isolado.',{exact:true})).toBeVisible();
  await page.screenshot({path:'test-results/workspace-task-mobile.png',fullPage:true});
  await page.goto('/admin/artigos/novo');
  await page.locator('[name="title"]').fill('Artigo próprio de teste '+Date.now());
  await page.locator('[name="summary"]').fill('Resumo científico para teste isolado.');
  await page.locator('[name="body"]').fill('Texto científico fundamentado para teste. '.repeat(8));
  await page.locator('[name="category_id"]').selectOption({index:0});
  await page.locator('form.editor-form button[type="submit"]').first().click();
  await expect(page).toHaveURL(/\/admin\/artigos$/);
  await page.goto('/admin/submissoes');
  await page.getByRole('link',{name:/BROWSER-PERMISSIONS/}).click();
  await expect(page.getByRole('button',{name:'Atribuir editor'})).toBeVisible();
  await expect(page.getByRole('link',{name:'Atribuir revisores e consultar pareceres'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Registar decisão e comunicar'})).toHaveCount(0);
  fixture('revoke');
  await page.goto('/admin/trabalho');
  await expect(page.locator('#distribuir-tarefa')).toHaveCount(0);
  await expect(page.getByRole('navigation').getByRole('link',{name:'Contactos',exact:true})).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Acessos de trabalho'}).getByRole('link',{name:/Contactos/})).toHaveCount(0);
  expect((await page.goto('/admin/contactos')).status()).toBe(403);
});
