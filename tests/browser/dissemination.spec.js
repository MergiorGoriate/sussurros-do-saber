const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
for(const width of [320,768,1440]) {
  test(`scientific dissemination review, corrections and layout at ${width}px`,async({page,context})=>{
    const fixture=JSON.parse(execFileSync('python',['tests/browser/dissemination_fixture.py'],{encoding:'utf8'}));
    await context.addCookies([{name:'session',value:fixture.cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
    await page.setViewportSize({width,height:950});
    for(const path of ['/admin/divulgacao/',`/admin/divulgacao/${fixture.id}`]) {
      await page.goto(path);
      await expect(page.locator('.dc h1')).toBeVisible();
      for(const dark of [false,true]) {
        await page.evaluate(dark=>document.body.classList.toggle('admin-dark',dark),dark);
        expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
      }
    }
    const visual=page.locator('.dc-review-grid .dc-slides img').first();
    await expect(visual).toBeVisible();
    expect(await visual.evaluate(image=>image.complete&&image.naturalWidth===1080)).toBeTruthy();
    await expect(page.getByRole('heading',{name:'Afirmações e trechos de suporte',exact:true})).toBeVisible();
    await expect(page.getByRole('link',{name:'Descarregar imagens e texto',exact:true})).toHaveCount(0);
    const section=page.locator('section').filter({has:page.getByRole('heading',{name:'Solicitar correcção',exact:true})});
    await section.getByRole('textbox',{name:'Problemas encontrados',exact:true}).fill('Rever a representação visual antes de divulgar.');
    await section.getByRole('button',{name:'Solicitar correcção e invalidar a aprovação',exact:true}).click();
    await expect(page.locator('.admin-header .dc-state')).toHaveText('Em correcção');
    await expect(page.getByRole('button',{name:'Aprovar material',exact:true})).toHaveCount(0);
    await page.screenshot({path:`test-results/dissemination-${width}.png`,fullPage:true});
  });
}
