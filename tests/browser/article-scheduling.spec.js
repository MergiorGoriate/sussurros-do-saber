const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
async function setup(context){
 const cookie=execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();
 await context.addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
 return JSON.parse(execFileSync('python',['tests/browser/editor_fixture.py'],{encoding:'utf8'}));
}
for(const width of [320,768,1440])test(`schedule and cancel through the editor at ${width}px`,async({page,context})=>{
 const fixture=await setup(context);
 page.on('dialog',dialog=>dialog.accept());
 await page.setViewportSize({width,height:900});
 await page.goto(`/admin/artigos/${fixture.article_id}/editar`);
 const state=page.locator('select[name="status"]'),date=page.locator('[name="scheduled_at"]'),zone=page.locator('[name="schedule_timezone"]');
 await expect(date).toBeDisabled();
 await state.selectOption('scheduled');await expect(date).toBeEnabled();await expect(date).toHaveAttribute('required','');
 await date.fill('2099-01-02T12:30');await zone.selectOption('UTC');await expect(date).toHaveValue('2099-01-02T10:30');
 await zone.selectOption('Africa/Maputo');await expect(date).toHaveValue('2099-01-02T12:30');
 for(const dark of [false,true]){
  await page.evaluate(dark=>document.body.classList.toggle('admin-dark',dark),dark);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 }
 await page.getByRole('button',{name:'Guardar artigo',exact:true}).click();await expect(page).toHaveURL(/\/admin\/artigos$/);
 await page.goto(`/admin/artigos/${fixture.article_id}/editar`);await expect(state).toHaveValue('scheduled');await expect(date).toHaveValue('2099-01-02T12:30');
 await page.locator('[data-article-scheduling]').screenshot({path:`test-results/scheduling-${width}.png`});
 await state.selectOption('draft');await page.getByRole('button',{name:'Guardar artigo',exact:true}).click();
 await page.goto(`/admin/artigos/${fixture.article_id}/editar`);await expect(state).toHaveValue('draft');await expect(date).toHaveValue('');
});
test('scheduling works without JavaScript',async({browser})=>{
 const context=await browser.newContext({javaScriptEnabled:false});const fixture=await setup(context);const page=await context.newPage();
 await page.goto(`/admin/artigos/${fixture.article_id}/editar`);
 await page.locator('select[name="status"]').selectOption('scheduled');await page.locator('[name="scheduled_at"]').fill('2099-02-03T14:00');
 await page.getByRole('button',{name:'Guardar artigo',exact:true}).click();await expect(page).toHaveURL(/\/admin\/artigos$/);
 await page.goto(`/admin/artigos/${fixture.article_id}/editar`);await expect(page.locator('[name="scheduled_at"]')).toHaveValue('2099-02-03T14:00');
 await context.close();
});
