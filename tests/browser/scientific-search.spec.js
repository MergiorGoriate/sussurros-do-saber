const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
const fixture=()=>JSON.parse(execFileSync('python',['tests/browser/scientific_search_fixture.py'],{encoding:'utf8'}));

for(const width of [320,1440]){
  test(`scientific catalogue search and DOI at ${width}px`,async({page})=>{
    const data=fixture();
    await page.setViewportSize({width,height:1000});
    await page.goto('/revistas');
    const card=page.locator('#'+data.slug);
    await page.locator('#journalSearch').fill('https://doi.org/'+data.doi);
    await expect(card).toBeVisible();
    await expect(page.locator('#journalEmpty')).toBeHidden();
    await expect(page.locator('#'+data.private_slug)).toHaveCount(0);
    await page.locator('#journalSearch').fill(data.author);
    await expect(card).toBeVisible();
    await page.getByRole('button',{name:'Pesquisar',exact:true}).click();
    await expect(page).toHaveURL(new RegExp('/revistas\\?q='));
    await expect(card).toBeVisible();
    await expect(page.locator('#journalSearch')).toHaveValue(data.author);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
    await page.goto('/revistas/'+data.slug);
    await expect(page.locator('.journal-doi-link')).toHaveAttribute('href','https://doi.org/'+data.doi);
    await page.getByRole('button',{name:'Citar artigo',exact:true}).click();
    await expect(page.locator('#journal-citation-text')).toHaveValue(new RegExp('https://doi.org/'+data.doi.replaceAll('.','\\.')));
  });
}

test('catalogue GET search works without JavaScript',async({browser})=>{
  const data=fixture(), context=await browser.newContext({javaScriptEnabled:false});
  try{
    const page=await context.newPage();
    await page.goto('http://127.0.0.1:5000/revistas');
    await page.locator('#journalSearch').fill('https://doi.org/'+data.doi);
    await page.getByRole('button',{name:'Pesquisar',exact:true}).click();
    await expect(page.locator('#'+data.slug)).toBeVisible();
    await expect(page.locator('#'+data.private_slug)).toHaveCount(0);
    await page.locator('#journalSearch').fill('nonexistent-'+data.slug);
    await page.getByRole('button',{name:'Pesquisar',exact:true}).click();
    await expect(page.locator('#journalEmpty')).toBeVisible();
  }finally{await context.close();}
});
