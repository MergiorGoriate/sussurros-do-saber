const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
function fixture(){return JSON.parse(execFileSync('python',['tests/browser/lifecycle_fixture.py'],{encoding:'utf8'}));}
async function signin(context,cookie){await context.addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);}
for(const width of [1440,390]) {
 test(`inbox reads/deletes persist and bar/page agree at ${width}px`,async({page})=>{
  const d=fixture();await signin(page.context(),d.cookie);await page.setViewportSize({width,height:1000});
  await page.goto('/admin/trabalho');const bar=page.locator('[data-notice-bar]');
  await expect(bar.locator('[data-notice-count]')).toHaveText('2');
  await bar.locator('summary').click();await expect(bar.locator('[data-notice-status]')).toHaveText('Notificações actualizadas.');
  const item=bar.locator('[data-notice-items] section').filter({hasText:'Segundo aviso '+d.suffix});
  await item.getByRole('button',{name:'Eliminar aviso'}).click();
  await expect(page).toHaveURL(/\/admin\/notificacoes$/);
  await expect(page.locator('main > section').filter({hasText:'Segundo aviso '+d.suffix})).toHaveCount(0);
  await expect(page.locator('[data-notice-bar] [data-notice-count]')).toHaveText('1');
  await page.locator('main > form').getByRole('button',{name:'Marcar todas como lidas'}).click();
  await expect(page.locator('[data-notice-bar] [data-notice-count]')).toHaveText('0');
  await page.reload();await expect(page.locator('[data-notice-bar] [data-notice-count]')).toHaveText('0');
  await expect(page.locator('main > section').filter({hasText:'Segundo aviso '+d.suffix})).toHaveCount(0);
  expect((await page.goto(`/admin/remover/document/${d.document_id}`)).status()).toBe(403);
 });
}
test('founder confirmation cancellation, four archives, reassignment and open-session revocation',async({page,browser})=>{
 const d=fixture();await signin(page.context(),d.founder_cookie);
 const collaborator=await browser.newContext();await signin(collaborator,d.cookie);const other=await collaborator.newPage();
 await other.goto('/admin/trabalho');
 await page.goto(`/admin/remover/document/${d.document_id}`);
 await expect(page.getByRole('heading',{name:/Confirmar remoção: Termo/})).toBeVisible();
 await page.getByRole('link',{name:'Cancelar',exact:true}).click();
 await expect(page.locator(`#documento-${d.document_id}`)).toBeVisible();
 for(const [kind,id] of [['document',d.document_id],['report',d.report_id],['manuscript',d.manuscript_id],['member',d.member_id]]) {
   await page.goto(`/admin/remover/${kind}/${id}`);
   await page.getByRole('button',{name:'Confirmar remoção',exact:true}).click();
 }
 await expect(page).toHaveURL(new RegExp(`/admin/equipa/${d.member_id}/responsabilidades$`));
 const form=page.locator('section').filter({has:page.getByRole('heading',{name:new RegExp('Responsabilidade '+d.suffix)})}).locator('form');
 await form.locator('[name="target_id"]').selectOption(String(d.target_id));
 await form.getByRole('button',{name:'Reatribuir responsabilidade'}).click();
 await expect(page.getByRole('heading',{name:new RegExp('Responsabilidade '+d.suffix)})).toHaveCount(0);
 await other.goto('/admin/trabalho');await expect(other).toHaveURL(/\/admin\/login/);
 await page.goto('/admin/historico-remocoes');await expect(page.getByRole('heading',{name:'Histórico de remoções'})).toBeVisible();
 await collaborator.close();
});
test('notice loading/error state recovers and actions remain usable',async({page})=>{
 const d=fixture();await signin(page.context(),d.cookie);await page.goto('/admin/trabalho');
 await page.route('**/admin/api/notificacoes',route=>route.abort());
 const bar=page.locator('[data-notice-bar]');await bar.locator('summary').click();
 await expect(bar.locator('[data-notice-status]')).toContainText('Não foi possível actualizar');
 await expect(bar.getByRole('link',{name:'Todas as notificações'})).toBeVisible();
 await page.unroute('**/admin/api/notificacoes');await bar.locator('summary').click();await bar.locator('summary').click();
 await expect(bar.locator('[data-notice-status]')).toHaveText('Notificações actualizadas.');
});
