const {test,expect}=require('@playwright/test');

for(const width of [320,1440]){
  test(`editorial labels and existing signup at ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:1000});
    await page.goto('/');
    const refuse=page.getByRole('button',{name:'Recusar não essenciais',exact:true});
    if(await refuse.isVisible())await refuse.click();
    await expect(page.getByRole('heading',{name:'Artigos recentes',exact:true})).toBeVisible();
    await expect(page.getByText('Mais lidos',{exact:true})).toHaveCount(0);
    await expect(page.getByText('Boletim semanal',{exact:true})).toHaveCount(0);
    await expect(page.getByText('O envio do boletim ainda não está activo.',{exact:false})).toBeVisible();
    const form=page.locator('#newsletterForm');
    await form.scrollIntoViewIfNeeded();
    await expect(form.getByRole('button',{name:'Registar interesse',exact:true})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
    await page.locator('section').filter({has:form}).screenshot({path:test.info().outputPath('newsletter.png')});
    await form.locator('input[type=email]').fill(`discovery-${width}-${Date.now()}@example.org`);
    const response=page.waitForResponse(r=>r.url().endsWith('/api/newsletter')&&r.request().method()==='POST');
    await form.getByRole('button',{name:'Registar interesse',exact:true}).click();
    const saved=await response;
    expect(saved.status()).toBe(200);
    expect((await saved.json()).ok).toBe(true);
    // Existing UI reset failure is documented in docs/EDITORIAL_DISCOVERY.md.
  });
}
