const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');

test('modern article editor preserves content across view modes and remains responsive',async({page},testInfo)=>{
  test.setTimeout(60000);
  const screenshots='/tmp/article-editor-layout-previews';
  fs.mkdirSync(screenshots,{recursive:true});
  page.on('dialog',dialog=>dialog.type()==='beforeunload'?dialog.accept():dialog.dismiss());
  const cookie=execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();
  await page.context().addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
  const records=JSON.parse(execFileSync('python',['tests/browser/editor_fixture.py'],{encoding:'utf8'}));
  const url=`/admin/artigos/${records.article_id}/editar`;
  await page.setViewportSize({width:1600,height:1000});
  await page.goto(url);
  if(await page.locator('body').evaluate(el=>el.classList.contains('admin-dark')))await page.locator('[data-admin-theme-toggle]').click();
  await expect(page.locator('.editor-view-switch')).toBeVisible();
  await expect(page.locator('.editor-card')).toHaveCount(4);
  await page.screenshot({path:path.join(screenshots,'article-editor-desktop.png'),fullPage:true});
  await page.getByRole('button',{name:'Escrever',exact:true}).click();
  await expect(page.locator('#articleEditorPreviewPanel')).toBeHidden();
  await page.reload();
  await expect(page.locator('#articleEditorPreviewPanel')).toBeHidden();
  const value='## Texto conservado\n\nUm conteúdo de teste que deve permanecer intacto ao mudar entre os modos de edição.';
  await page.locator('#bodyEditor').fill(value);
  await page.getByRole('button',{name:'Pré-visualização',exact:true}).click();
  await expect(page.locator('#articleEditorTextPanel')).toBeHidden();
  await expect(page.locator('#markdownPreview')).toContainText('Texto conservado');
  await page.getByRole('button',{name:'Dividido',exact:true}).click();
  await expect(page.locator('#bodyEditor')).toHaveValue(value);
  await page.getByRole('button',{name:'Guardar artigo',exact:true}).click();
  await page.waitForURL('**/admin/artigos');
  await page.goto(url);
  await expect(page.locator('#bodyEditor')).toHaveValue(value);
  await page.locator('[data-admin-theme-toggle]').click();
  await page.getByRole('radio',{name:'Papel antigo',exact:true}).check();
  await expect(page.locator('#articleSurfacePreview')).toHaveCSS('background-color','rgb(48, 43, 34)');
  await page.screenshot({path:path.join(screenshots,'article-editor-dark.png'),fullPage:true});
  for(const width of [320,390,768,1440]){
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth),String(width)).toBeTruthy();
  }
  await page.setViewportSize({width:390,height:900});
  await page.screenshot({path:path.join(screenshots,'article-editor-mobile.png'),fullPage:true});
});
