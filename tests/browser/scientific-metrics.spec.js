const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
let fixture;
test.beforeAll(()=>{fixture=JSON.parse(execFileSync('python',['tests/browser/scientific_metrics_fixture.py'],{encoding:'utf8'}));});
async function rejectCookies(page){const reject=page.getByRole('button',{name:'Recusar não essenciais',exact:true});if(await reject.isVisible())await reject.click();}
for(const width of [320,768,1440]){
 test(`public scientific metrics and charts at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:1000});
  await page.goto(`/revistas/${fixture.slug}`);await rejectCookies(page);
  const button=page.getByRole('button',{name:'Métricas Científicas',exact:true});await expect(button).toBeVisible();
  await button.focus();await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog',{name:'Métricas do artigo',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Fechar métricas',exact:true})).toBeFocused();
  expect(await page.locator('#scientific-metrics-dialog').evaluate(node=>node.scrollWidth<=node.clientWidth+1)).toBeTruthy();
  for(let i=0;i<6;i++){await page.keyboard.press('Tab');expect(await page.locator('#scientific-metrics-dialog').evaluate(node=>node.contains(document.activeElement))).toBeTruthy();}
  await expect(page.locator('#scientific-metrics-panel .science-stat').filter({hasText:'Citações'}).locator('strong')).toHaveText('2');
  await expect(page.locator('#scientific-metrics-panel').getByRole('rowheader',{name:'MZ',exact:true})).toBeVisible();
  await expect(page.locator('#scientific-metrics-panel').getByRole('rowheader',{name:'ZA',exact:true})).toHaveCount(0);
  await page.locator('#scientific-metrics-panel').getByRole('button',{name:'Downloads',exact:true}).click();
  await expect(page.locator('#scientific-metrics-panel [data-chart-status]')).toContainText('downloads');
  await expect(page.getByRole('button',{name:'Fechar métricas',exact:true})).toBeInViewport();
  for(const dark of [false,true]){
   await page.evaluate(dark=>document.documentElement.classList.toggle('dark',dark),dark);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
   await page.locator('#scientific-metrics-dialog').screenshot({path:`test-results/scientific-public-${width}-${dark?'dark':'light'}.png`});
  }
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog',{name:'Métricas do artigo',exact:true})).not.toBeVisible();
  await expect(button).toBeFocused();
  await page.keyboard.press('Space');await page.getByRole('button',{name:'Fechar métricas',exact:true}).click();
  await expect(button).toBeFocused();
  await button.click();await page.mouse.click(1,1);
  await expect(page.getByRole('dialog',{name:'Métricas do artigo',exact:true})).not.toBeVisible();
  await expect(page.locator('html')).not.toHaveClass(/science-modal-open/);
 });
}
test('scientific administration filters, export and scoped navigation',async({page,context})=>{
 await context.addCookies([{name:'session',value:fixture.admin_cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
 await page.goto(`/admin/revistas/metricas?article=${fixture.id}`);
 await expect(page.getByRole('heading',{name:'Métricas Científicas',exact:true})).toBeVisible();
 await page.getByRole('combobox',{name:'Fonte de citações',exact:true}).selectOption('openalex');
 await page.getByRole('button',{name:'Aplicar filtros',exact:true}).click();
 await expect(page.locator('.science-stat').filter({hasText:'Citações'}).locator('strong')).toHaveText('4');
 await expect(page.getByRole('link',{name:'Exportar CSV',exact:true})).toHaveAttribute('href',/source=openalex/);
 for(const width of [320,768,1440]){
  await page.setViewportSize({width,height:1000});
  for(const dark of [false,true]){
   await page.evaluate(dark=>document.body.classList.toggle('admin-dark',dark),dark);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
   const chart=page.locator('.science-admin [data-chart]');
   expect((await chart.boundingBox()).height).toBeLessThanOrEqual(230);
   await page.screenshot({path:`test-results/scientific-admin-${width}-${dark?'dark':'light'}.png`,fullPage:true});
  }
 }
});
test('real reader requests deduplicate views and record a separate PDF request',async({browser})=>{
 const context=await browser.newContext({userAgent:'Mozilla/5.0 scientific-metrics-reader'});
 const page=await context.newPage();
 await page.goto(`/revistas/${fixture.counter_slug}`);await rejectCookies(page);
 await page.reload();
 await page.goto(`/revistas/${fixture.counter_slug}/metricas`);
 await expect(page.locator('.science-stat').filter({hasText:'Visualizações'}).locator('strong')).toHaveText('1');
 await expect(page.locator('.science-stat').filter({hasText:'Downloads PDF'}).locator('strong')).toHaveText('0');
 await page.goto(`/revistas/${fixture.counter_slug}`);
 const downloaded=page.waitForEvent('download');await page.getByRole('link',{name:'Baixar PDF',exact:true}).click();
 const file=await downloaded;expect(await file.failure()).toBeNull();
 await page.goto(`/revistas/${fixture.counter_slug}/metricas`);
 await expect(page.locator('.science-stat').filter({hasText:'Downloads PDF'}).locator('strong')).toHaveText('1');
 await context.close();
});
test('scientific metrics are usable without JavaScript',async({browser})=>{
 const context=await browser.newContext({javaScriptEnabled:false});const page=await context.newPage();
 await page.goto(`/revistas/${fixture.slug}/metricas`);
 await expect(page.getByRole('heading',{name:'Métricas do artigo',exact:true})).toBeVisible();
 await expect(page.getByText('Consultar dados do gráfico',{exact:true})).toBeVisible();
 await page.getByText('Consultar dados do gráfico',{exact:true}).click();
 await expect(page.getByRole('table').first()).toBeVisible();await context.close();
});

test('administrative preview opens scientific metrics without counting a visit',async({page,context})=>{
 await context.addCookies([{name:'session',value:fixture.admin_cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
 await page.goto(`/admin/revistas/${fixture.id}/previsualizar`);
 await page.getByRole('button',{name:'Métricas Científicas',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'Métricas do artigo',exact:true})).toBeVisible();
 await expect(page.locator('#scientific-metrics-panel .science-stat').filter({hasText:'Visualizações'}).locator('strong')).toHaveText('10');
});
test('article metrics link works without JavaScript',async({browser})=>{
 const context=await browser.newContext({javaScriptEnabled:false});const page=await context.newPage();
 await page.goto(`/revistas/${fixture.slug}`);
 await page.getByRole('link',{name:'Métricas Científicas',exact:true}).click();
 await expect(page).toHaveURL(new RegExp(`/revistas/${fixture.slug}/metricas$`));
 await expect(page.getByRole('heading',{name:'Métricas do artigo',exact:true})).toBeVisible();await context.close();
});
