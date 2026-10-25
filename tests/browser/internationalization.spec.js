const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
for(const width of [320,768,1440]){
 test(`reviewed PT/EN article, language switch and layout at ${width}px`,async({page})=>{
  const fixture=JSON.parse(execFileSync('python',['tests/browser/internationalization_fixture.py'],{encoding:'utf8'}));
  await page.setViewportSize({width,height:1000});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/artigo/'+fixture.slug);
  const selector=page.locator('.language-selector');await expect(selector).toBeVisible();
  await selector.getByRole('link',{name:'EN',exact:true}).click();
  await expect(page).toHaveURL(new RegExp('/en/artigo/'+fixture.slug+'$'));
  await expect(page.locator('html')).toHaveAttribute('lang','en');
  await expect(page.locator('h1').first()).toHaveText(fixture.title);
  for(const dark of [false,true]){
   await page.evaluate(dark=>document.documentElement.classList.toggle('dark',dark),dark);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  }
  await selector.getByRole('link',{name:'PT',exact:true}).click();
  await expect(page).toHaveURL(new RegExp('/artigo/'+fixture.slug+'$'));
  await expect(page.locator('html')).toHaveAttribute('lang','pt-MZ');
  await expect(page.locator('h1').first()).toHaveText(fixture.portuguese);
  expect(errors).toEqual([]);
 });
}
test('translation administration is private and exposes the queue and interface catalogue',async({page,context})=>{
 const cookie=execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();
 await context.addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
 await page.goto('/admin/internacionalizacao/');
 await expect(page.getByRole('heading',{name:'Tradução de artigos',exact:true})).toBeVisible();
 await page.getByRole('link',{name:'Traduzir interface e páginas institucionais',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Interface e páginas institucionais',exact:true})).toBeVisible();
});
