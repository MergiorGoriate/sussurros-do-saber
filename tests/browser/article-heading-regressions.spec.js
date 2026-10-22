const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
const fixture=()=>JSON.parse(execFileSync('python',['tests/browser/heading_regression_fixture.py'],{encoding:'utf8'}));
const cookie=()=>execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();
const hierarchy=locator=>locator.locator('h1,h2,h3,h4,h5,h6').evaluateAll(els=>els.map(el=>[el.tagName,el.textContent.trim(),el.id]));
for(const width of [320,1440]){
  test(`heading semantics, toolbar, persistence and themes at ${width}px`,async({page})=>{
    const data=fixture(), errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.context().addCookies([{name:'session',value:cookie(),url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
    await page.setViewportSize({width,height:1000});
    const path='/admin/artigos/'+data.article_id+'/editar';
    await page.goto(path);
    const editor=page.locator('#bodyEditor'),preview=page.locator('#markdownPreview');
    await expect(preview.locator('h1')).toHaveCount(0);
    await expect(preview.locator('h6')).toHaveText('Nível 6');
    await expect(preview.locator('pre code')).toContainText('# Literal');
    const initial=await hierarchy(preview);
    for(const level of [2,3,4,5,6]){
      await editor.fill('Secção de teste');
      await editor.evaluate(el=>el.setSelectionRange(4,4));
      await page.getByRole('button',{name:'H'+level,exact:true}).click();
      await expect(editor).toHaveValue('#'.repeat(level)+' Secção de teste');
      await expect(preview.locator('h'+level)).toHaveCount(1);
      await expect(preview.locator('h'+level)).toHaveText('Secção de teste');
    }
    await page.getByRole('button',{name:'H2',exact:true}).click();
    await expect(editor).toHaveValue('## Secção de teste');
    const before=await editor.inputValue();
    await page.locator('#titleField').focus();
    await expect(page.locator('#titleField')).toBeFocused();
    await expect(editor).toHaveValue(before);
    await editor.fill(data.body);
    await expect(preview.locator('h6')).toHaveText('Nível 6');
    await expect(preview).not.toHaveAttribute('aria-busy','true');
    for(const dark of [false,true]){
      await page.evaluate(d=>document.body.classList.toggle('admin-dark',d),dark);
      const sizes=await preview.locator('h2,h3,h4,h5,h6').evaluateAll(els=>els.slice(1,6).map(el=>parseFloat(getComputedStyle(el).fontSize)));
      for(let i=1;i<sizes.length;i++)expect(sizes[i-1]).toBeGreaterThan(sizes[i]);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await page.screenshot({path:`test-results/headings-editor-${width}-${dark?'dark':'light'}.png`,fullPage:true});
    }
    await page.getByRole('button',{name:'Guardar artigo',exact:true}).click();
    await expect(page).toHaveURL(/\/admin\/artigos$/);
    await page.goto(path);
    await expect(editor).toHaveValue(data.body);
    await expect(preview.locator('h6')).toHaveText('Nível 6');
    await page.goto('/artigo/'+data.slug);
    await expect(page.locator('h1')).toHaveText('Título principal de teste');
    const content=page.locator('.article-markdown').first();
    expect(await hierarchy(content)).toEqual(initial);
    for(const dark of [false,true]){
      await page.evaluate(d=>document.documentElement.classList.toggle('dark',d),dark);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await page.screenshot({path:`test-results/headings-public-${width}-${dark?'dark':'light'}.png`,fullPage:true});
    }
    await content.getByRole('link',{name:'Secção',exact:true}).click();
    await expect(content.locator('#sec-nivel-2')).toBeInViewport();
    expect(errors).toEqual([]);
  });
}
test('existing journal index includes deeper headings and working anchors',async({page})=>{
  const data=fixture();
  await page.goto('/revistas/'+data.journal_slug);
  for(const level of [2,3,4,5,6]){
    const link=page.locator('#journal-content-index a').filter({hasText:'Secção '+level});
    await expect(link).toHaveCount(1);
    const href=await link.getAttribute('href');
    await expect(page.locator(href)).toHaveText('Secção '+level);
  }
  const ids=await page.locator('.journal-sections [id]').evaluateAll(els=>els.map(el=>el.id));
  expect(new Set(ids).size).toBe(ids.length);
});
test('a failed or stale preview never replaces newer input',async({page})=>{
  const data=fixture();
  await page.context().addCookies([{name:'session',value:cookie(),url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
  await page.goto('/admin/artigos/'+data.article_id+'/editar');
  await page.route('**/admin/artigos/previsualizar',route=>route.fulfill({status:503,body:'unavailable'}));
  const editor=page.locator('#bodyEditor');
  await editor.fill('###### Ainda por guardar');
  await expect(page.locator('#footnotePreviewStatus')).toContainText('Não foi possível actualizar');
  await expect(editor).toHaveValue('###### Ainda por guardar');
  await expect(page.locator('#markdownPreview')).toHaveText('###### Ainda por guardar');
  await page.unroute('**/admin/artigos/previsualizar');
  await editor.fill('###### Recuperado');
  await expect(page.locator('#markdownPreview h6')).toHaveText('Recuperado');
});
test('slower previous responses cannot overwrite the current preview',async({page})=>{
  const data=fixture();
  await page.context().addCookies([{name:'session',value:cookie(),url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
  await page.goto('/admin/artigos/'+data.article_id+'/editar');
  await expect(page.locator('#markdownPreview')).not.toHaveAttribute('aria-busy','true');
  let release;
  const delayed=new Promise(resolve=>{release=resolve;});
  await page.route('**/admin/artigos/previsualizar',async route=>{
    if(route.request().postData().includes('Antigo')){
      await delayed;
      try{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({html:'<h6>Antigo</h6>'})});}catch{}
    }else await route.continue();
  });
  const request=page.waitForRequest(req=>req.url().endsWith('/admin/artigos/previsualizar')&&req.postData().includes('Antigo'));
  await page.locator('#bodyEditor').fill('###### Antigo');
  await request;
  await page.locator('#bodyEditor').fill('###### Actual');
  await expect(page.locator('#markdownPreview h6')).toHaveText('Actual');
  release();
  await expect(page.locator('#markdownPreview h6')).toHaveText('Actual');
});
test('external cover preview keeps its video helper after Markdown consolidation',async({page})=>{
  const data=fixture(), errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.context().addCookies([{name:'session',value:cookie(),url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
  await page.goto('/admin/artigos/'+data.article_id+'/editar');
  await page.locator('#coverMode').selectOption('video_controls');
  await page.locator('#coverVideoUrl').fill('https://youtu.be/abcdefghijk');
  await expect(page.locator('#coverEditorStatus')).toContainText('Pré-visualização com controlos');
  const embed=await page.locator('#coverPreview template').evaluate(el=>el.content.querySelector('iframe')?.getAttribute('src'));
  expect(embed).toBe('https://www.youtube-nocookie.com/embed/abcdefghijk');
  await expect(page.locator('#coverPreview .cover-toggle')).toBeVisible();
  expect(errors).toEqual([]);
});
