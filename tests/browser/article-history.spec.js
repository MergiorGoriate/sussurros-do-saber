const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
for(const width of [320,1440]){
  test(`editor statistics and article restoration work at ${width}px`,async({page})=>{
    const cookie=execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();
    const data=JSON.parse(execFileSync('python',['tests/browser/workflow_fixture.py'],{encoding:'utf8'}));
    await page.context().addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
    await page.setViewportSize({width,height:1000});
    const editor='/admin/artigos/'+data.article_id+'/editar';
    await page.goto(editor);
    const original=await page.locator('#bodyEditor').inputValue();
    await page.locator('#bodyEditor').fill(Array(401).fill('ciência').join(' '));
    await expect(page.locator('#editorWordCount')).toHaveText('401 palavras');
    await expect(page.locator('#editorSaveState')).toHaveText('Alterações por guardar');
    await page.getByRole('button',{name:'Usar tempo estimado',exact:true}).click();
    await expect(page.locator('input[name="read_minutes"]')).toHaveValue('3');
    await page.getByRole('button',{name:'Guardar artigo',exact:true}).click();
    await expect(page).toHaveURL(/\/admin\/artigos$/);
    await page.goto(editor);
    await page.getByRole('link',{name:'Histórico de versões e recuperação',exact:true}).click();
    await page.getByRole('link',{name:'Versão 1',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Histórico de versões',exact:true})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({path:`test-results/history-layout-${width}.png`,fullPage:true});
    await page.getByText('Recuperar esta versão',{exact:true}).click();
    await page.getByRole('checkbox',{name:'Confirmo a recuperação como rascunho.',exact:true}).check();
    await page.getByRole('button',{name:'Recuperar versão 1 como rascunho',exact:true}).click();
    await expect(page).toHaveURL(new RegExp(editor+'$'));
    await expect(page.locator('#bodyEditor')).toHaveValue(original);
    await expect(page.locator('select[name="status"]')).toHaveValue('draft');
  });
}
