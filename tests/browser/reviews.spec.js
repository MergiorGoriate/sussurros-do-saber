const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
// Each scenario covers multiple real authenticated page transitions.
test.setTimeout(60000);
function fixture(mode){return JSON.parse(execFileSync('python',['tests/browser/reviews_fixture.py',...(mode?[mode]:[])],{encoding:'utf8'}));}
async function signin(context,cookie){await context.addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);}

test('editor assigns and reviewer accepts, downloads, delivers and declares a later conflict',async({page,browser})=>{
 const d=fixture();await signin(page.context(),d.founder);await page.goto('/admin/pareceres');
 await expect(page.getByRole('heading',{name:'Gestão de pareceres',exact:true})).toBeVisible();
 await page.locator('[name=manuscript_id]').selectOption(String(d.manuscript_id));await page.getByRole('button',{name:'Consultar e atribuir'}).click();
 await page.locator('[name=reviewer_id]').selectOption(String(d.member_id));await page.locator('[name=due_on]').fill(d.due_on);await page.getByRole('button',{name:'Atribuir parecer',exact:true}).click();
 await expect(page.locator('.review-state.is-invited')).toBeVisible();
 const context=await browser.newContext();await signin(context,d.reviewer);const reviewer=await context.newPage();
 await reviewer.goto('/admin/pareceres');await expect(reviewer.getByRole('link',{name:'Rever artigo de divulgação'})).toBeVisible();
 await reviewer.getByRole('link',{name:'Responder ao convite',exact:true}).click();await reviewer.locator('[name=no_conflict]').check();await reviewer.getByRole('button',{name:'Aceitar convite',exact:true}).click();
 const downloaded=reviewer.waitForEvent('download');await reviewer.locator('.review-file').first().click();expect((await downloaded).suggestedFilename()).toBe('privado.txt');
 await reviewer.locator('[name=recommendation]').selectOption('minor_revision');const report='Métodos e resultados verificados. Explicitar as limitações e fundamentar as conclusões. '.repeat(3);await reviewer.locator('[name=report]').fill(report);await reviewer.getByRole('button',{name:'Entregar parecer',exact:true}).click();
 await expect(reviewer.locator('.review-state.is-submitted')).toBeVisible();await expect(reviewer.getByText(report.trim(),{exact:true})).toBeVisible();
 await page.goto('/admin/pareceres');await page.getByText('Consultar parecer · Correcções menores',{exact:true}).click();await expect(page.getByText(report.trim(),{exact:true})).toBeVisible();
 await reviewer.goto('/admin/pareceres/'+d.conflict_id);await reviewer.locator('[name=conflict_note]').fill('Colaboração recente com a equipa de autores.');await reviewer.getByRole('button',{name:'Declarar conflito',exact:true}).click();await expect(reviewer.locator('.review-state.is-conflict')).toBeVisible();expect((await reviewer.request.get(`/admin/pareceres/${d.conflict_id}/ficheiros/${d.conflict_file_id}`)).status()).toBe(404);
 await context.close();
});

test('personal review list and detail fit phones and both administrative themes',async({page})=>{
 const d=fixture('layout');await signin(page.context(),d.reviewer);await page.emulateMedia({reducedMotion:'reduce'});
 for(const width of [320,1440])for(const theme of ['light','dark']){
  await page.setViewportSize({width,height:1000});await page.addInitScript(t=>localStorage.setItem('sussurros.admin.theme',t),theme);
  for(const route of ['/admin/pareceres','/admin/pareceres/'+d.conflict_id]){
   await page.goto(route);await expect(page.locator('.reviews-page')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
   await expect(page.getByRole('heading',{name:route.endsWith('pareceres')?'Meus pareceres':'Parecer científico',exact:true})).toBeVisible();
  }
 }
});
