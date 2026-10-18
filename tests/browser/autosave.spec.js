const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
async function openDraft(page){
  const cookie=execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();
  const data=JSON.parse(execFileSync('python',['tests/browser/workflow_fixture.py'],{encoding:'utf8'}));
  await page.context().addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
  data.path='/admin/artigos/'+data.article_id+'/editar';
  await page.goto(data.path);
  return data;
}
const savedResponse=page=>page.waitForResponse(r=>r.url().endsWith('/rascunho')&&r.request().method()==='POST');
for(const width of [320,1440]){
  test(`draft autosave survives reload and records history at ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:1000});
    const data=await openDraft(page),text='Texto guardado automaticamente com acentuação. '.repeat(12);
    const slug=await page.locator('[name=slug]').inputValue();
    const response=savedResponse(page);
    await page.locator('#bodyEditor').fill(text);
    expect((await response).status()).toBe(200);
    await expect(page.locator('#editorAutosaveStatus')).toContainText('Guardado automaticamente');
    await expect(page.locator('#editorSaveState')).toHaveText('');
    await page.reload();
    await expect(page.locator('#bodyEditor')).toHaveValue(text.trim());
    await page.getByRole('button',{name:'Alternar tema do painel',exact:true}).click();
    await page.screenshot({path:`/tmp/autosave-previews/editor-${width}.png`,fullPage:true,animations:'disabled'});
    await page.getByRole('link',{name:'Histórico de versões e recuperação',exact:true}).click();
    await expect(page.getByText('Gravação automática de rascunho',{exact:true})).toBeVisible();
    expect((await page.request.get('/artigo/'+slug)).status()).toBe(404);
  });
}
test('failed connection keeps text and retry saves it',async({page})=>{
  const data=await openDraft(page),text='Este texto deve sobreviver à falha de ligação. '.repeat(8);
  await page.route('**/rascunho',route=>route.abort());
  await page.locator('#bodyEditor').fill(text);
  await expect(page.locator('#editorAutosaveStatus')).toContainText('Não foi possível confirmar');
  await expect(page.locator('#bodyEditor')).toHaveValue(text);
  await expect(page.locator('#editorSaveState')).toHaveText('Alterações por guardar');
  await page.unroute('**/rascunho');
  const response=savedResponse(page);
  await page.locator('#retryAutosave').click();
  expect((await response).status()).toBe(200);
  await expect(page.locator('#editorSaveState')).toHaveText('');
  await page.reload();await expect(page.locator('#bodyEditor')).toHaveValue(text.trim());
});
test('two open editors never overwrite a newer draft',async({page,context})=>{
  const data=await openDraft(page),other=await context.newPage();await other.goto(data.path);
  const first='Primeira sessão com conteúdo válido. '.repeat(8),second='Segunda sessão com texto ainda não guardado. '.repeat(8);
  let response=savedResponse(page);await page.locator('#bodyEditor').fill(first);expect((await response).status()).toBe(200);
  await expect(page.locator('#editorSaveState')).toHaveText('');
  response=savedResponse(other);await other.locator('#bodyEditor').fill(second);expect((await response).status()).toBe(409);
  await expect(other.locator('#editorAutosaveStatus')).toContainText('alterado noutra sessão');
  await expect(other.locator('#bodyEditor')).toHaveValue(second);
  await expect(other.locator('#editorSaveState')).toHaveText('Alterações por guardar');
  await page.reload();await expect(page.locator('#bodyEditor')).toHaveValue(first.trim());
  await other.close();
});
test('manual save waits for an outstanding autosave and keeps later typing',async({page})=>{
  const data=await openDraft(page);
  let release,reached;
  const held=new Promise(resolve=>release=resolve),started=new Promise(resolve=>reached=resolve);
  await page.route('**/rascunho',async route=>{const response=await route.fetch();reached();await held;await route.fulfill({response});});
  await page.locator('#bodyEditor').fill('Primeiro conteúdo enviado automaticamente. '.repeat(8));
  await started;
  const final='Conteúdo escrito enquanto a gravação estava em curso. '.repeat(8);
  await page.locator('#bodyEditor').fill(final);
  await page.getByRole('button',{name:'Guardar artigo',exact:true}).click();
  release();
  await expect(page).toHaveURL(/\/admin\/artigos$/);
  await page.goto(data.path);await expect(page.locator('#bodyEditor')).toHaveValue(final.trim());
});
test('new article can be saved without leaving the editor to enable autosave',async({page})=>{
  await openDraft(page);
  const author=await page.locator('[name=author_id]').inputValue(),category=await page.locator('[name=category_id]').inputValue();
  await page.goto('/admin/artigos/novo');
  await page.locator('[name=title]').fill('Novo rascunho para gravação automática');
  await page.locator('[name=summary]').fill('Resumo completo do rascunho de teste.');
  await page.locator('[name=author_id]').selectOption(author);await page.locator('[name=category_id]').selectOption(category);
  await page.locator('#bodyEditor').fill('Texto inicial do rascunho.');
  await page.getByRole('button',{name:'Guardar e continuar',exact:true}).click();
  await expect(page).toHaveURL(/\/admin\/artigos\/\d+\/editar$/);
  await expect(page.locator('#editorAutosaveStatus')).toContainText('activa');
  const response=savedResponse(page),text='Nova versão do rascunho sem sair do editor.';
  await page.locator('#bodyEditor').fill(text);expect((await response).status()).toBe(200);
  await expect(page.locator('#editorSaveState')).toHaveText('');
  await page.reload();await expect(page.locator('#bodyEditor')).toHaveValue(text);
});
