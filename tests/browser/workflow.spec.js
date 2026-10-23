const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
for(const label of ['Aprovar e publicar sem revisão','Publicar directamente']){
 test(`primary administrator can ${label} from a draft`,async({page})=>{
  const cookie=execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();
  const data=JSON.parse(execFileSync('python',['tests/browser/workflow_fixture.py'],{encoding:'utf8'}));
  await page.context().addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
  await page.goto('/admin/fluxo-artigos/'+data.article_id);
  await page.getByRole('button',{name:label,exact:true}).click();
  await expect(page.locator('[aria-current="step"]')).toContainText('Publicação');
  await expect(page.getByText('Publicação autorizada directamente pelo administrador principal, sem revisão registada.',{exact:true})).toBeVisible();
  await expect(page.getByText('Ainda sem pareceres. As revisões entregues aparecerão aqui, com responsável e data.',{exact:true})).toBeVisible();
  const link=page.getByRole('link',{name:'Ver artigo publicado',exact:true});
  const response=await page.request.get(await link.getAttribute('href'));
  expect(response.status()).toBe(200);
 });
}
for(const width of [1440,390,320]){
 test(`editorial workflow layout and submission at ${width}px`,async({page})=>{
  const cookie=execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();
  const data=JSON.parse(execFileSync('python',['tests/browser/workflow_fixture.py'],{encoding:'utf8'}));
  await page.context().addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
  await page.setViewportSize({width,height:1000});
  const response=await page.goto('/admin/fluxo-artigos/'+data.article_id);
  expect(response.status()).toBe(200);
  await expect(page.getByRole('heading',{name:'Fluxo editorial do portal',exact:true})).toBeVisible();
  await expect(page.locator('.workflow-progress li')).toHaveCount(5);
  await expect(page.locator('[aria-current="step"]')).toContainText('Preparação');
  await expect(page.getByRole('button',{name:'Aprovar e publicar artigo',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Publicar artigo aprovado',exact:true})).toHaveCount(0);
  await page.getByText('Ler conteúdo',{exact:true}).click();
  await expect(page.locator('.workflow-body')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  await page.screenshot({path:`test-results/editorial-workflow-${width}.png`,fullPage:true});
  await page.getByRole('button',{name:'Submeter para revisão',exact:true}).click();
  await expect(page.locator('[aria-current="step"]')).toContainText('Submissão');
  await expect(page.getByRole('button',{name:'Submeter para revisão',exact:true})).toHaveCount(0);
  await page.reload();await expect(page.locator('[aria-current="step"]')).toContainText('Submissão');
 });
}


