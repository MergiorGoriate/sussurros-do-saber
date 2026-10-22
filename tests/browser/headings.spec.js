const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
const headings=async root=>root.locator('h2,h3,h4,h5,h6').evaluateAll(nodes=>nodes.map(h=>({tag:h.tagName,text:h.textContent,id:h.id})));
for(const width of [320,1440]){
  test(`headings persist and share preview/public semantics at ${width}px`,async({page})=>{
    const data=JSON.parse(execFileSync('python',['tests/browser/headings_fixture.py'],{encoding:'utf8'}));
    const cookie=execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();
    await page.context().addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
    await page.setViewportSize({width,height:1000});
    const path='/admin/artigos/'+data.article_id+'/editar';
    await page.route('https://example.org/**', route=>route.abort());
    await page.goto(path);
    const editor=page.locator('#bodyEditor'),preview=page.locator('#markdownPreview');
    await expect(preview.locator('h6')).toHaveCount(1);
    await expect(preview.locator('h1')).toHaveCount(0);
    expect((await headings(preview)).map(h=>h.tag)).toEqual(['H2','H2','H3','H4','H5','H6','H2','H4']);
    await expect(preview.locator('pre code')).toHaveText('# Código literal\n###### Código literal\n');
    await expect(preview.locator('.article-chart svg')).toHaveCount(1);
    await expect(preview.locator('.article-video video')).toHaveCount(1);
    await expect(preview.locator('.chart-line')).toHaveCSS('fill','none');
    const previewWidth=await preview.evaluate(el=>el.clientWidth);
    for(const media of ['.article-chart svg','.article-video video']){
      expect(await preview.locator(media).evaluate(el=>el.getBoundingClientRect().width)).toBeLessThanOrEqual(previewWidth);
    }
    const rendered=await headings(preview);
    for(const mode of ['light','dark']){
      if(mode==='dark')await page.getByRole('button',{name:'Alternar tema do painel',exact:true}).click();
      const fontSizes=await preview.locator('h2,h3,h4,h5,h6').evaluateAll(nodes=>nodes.slice(1,6).map(h=>parseFloat(getComputedStyle(h).fontSize)));
      expect(fontSizes.every((size,i)=>i===0||size<fontSizes[i-1])).toBeTruthy();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await preview.screenshot({path:`/tmp/headings-editor-${mode}-${width}.png`});
    }
    // Replace an existing line's level without adding a second hash prefix.
    await editor.evaluate(el=>{const pos=el.value.indexOf('### Secção 3');el.focus();el.setSelectionRange(pos+5,pos+5);});
    await page.getByRole('button',{name:'H5',exact:true}).click();
    await expect(editor).toHaveValue(data.body.replace('### Secção 3','##### Secção 3'));
    await expect(preview.locator('#sec-seccao-3')).toHaveJSProperty('tagName','H5');
    await page.getByRole('button',{name:'Guardar artigo',exact:true}).click();
    await expect(page).toHaveURL(/\/admin\/artigos$/);
    await page.goto(path);
    await expect(editor).toHaveValue(data.body.replace('### Secção 3','##### Secção 3'));
    await expect(preview.locator('#sec-seccao-3')).toHaveJSProperty('tagName','H5');
    await page.goto('/artigo/'+data.slug);
    const consent=page.getByRole('button',{name:'Recusar não essenciais',exact:true});
    if(await consent.isVisible())await consent.click();
    const publicBody=page.locator('.article-headings').first();
    await expect(page.locator('h1')).toHaveCount(1);
    expect(await headings(publicBody)).toEqual(rendered);
    const link=publicBody.getByRole('link',{name:'Ir à secção',exact:true});
    await link.click();
    await expect(publicBody.locator('#sec-seccao-6')).toBeInViewport();
    for(const mode of ['light','dark']){
      if(mode==='dark')await page.locator('#themeToggle').click();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await publicBody.screenshot({path:`/tmp/headings-public-${mode}-${width}.png`});
    }
  });
}
test('server preview sanitizes all articles and discards stale responses',async({page})=>{
  const cookie=execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();
  await page.context().addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
  await page.goto('/admin/artigos/novo');
  const editor=page.locator('#bodyEditor'),preview=page.locator('#markdownPreview');
  await editor.fill('###### Seguro\n\n<img src="x" onerror="window.headingXss=1">\n\n<script>window.headingXss=1</script>');
  await expect(preview.locator('h6')).toHaveText('Seguro');
  await expect(preview.locator('script,[onerror]')).toHaveCount(0);
  expect(await page.evaluate(()=>window.headingXss)).toBeUndefined();
  let first=true,started;
  const pending=new Promise(resolve=>{started=resolve;});
  await page.route('**/admin/artigos/previsualizar',async route=>{
    if(first){first=false;started();await new Promise(resolve=>setTimeout(resolve,900));}
    await route.continue().catch(()=>{});
  });
  await editor.fill('## Antigo');
  await pending;
  await editor.fill('## Actual');
  await expect(preview.locator('h2')).toHaveText('Actual');
  await expect(preview).not.toContainText('Antigo');
});
