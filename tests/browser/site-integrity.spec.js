const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
test('oversized pagination and numeric paths return controlled responses',async({request})=>{
  const huge='9'.repeat(100);
  for(const path of ['/artigos?page='+huge,'/conta/notificacoes?page='+huge]){
    expect((await request.get(path)).status(),path).toBe(200);
  }
  for(const path of ['/artigo/'+huge,'/autor/'+huge,'/admin/artigos/'+huge+'/editar']){
    expect((await request.get(path)).status(),path).toBe(404);
  }
});
test('manual save keeps Markdown indentation and trailing line breaks',async({page})=>{
  const cookie=execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();
  const data=JSON.parse(execFileSync('python',['tests/browser/workflow_fixture.py'],{encoding:'utf8'}));
  await page.context().addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
  const path='/admin/artigos/'+data.article_id+'/editar';
  const text='    print("código indentado")\n\nParágrafo com quebra final  \n';
  await page.goto(path);
  await page.locator('#bodyEditor').fill(text);
  await page.getByRole('button',{name:'Guardar artigo',exact:true}).click();
  await expect(page).toHaveURL(/\/admin\/artigos$/);
  await page.goto(path);
  await expect(page.locator('#bodyEditor')).toHaveValue(text);
});
