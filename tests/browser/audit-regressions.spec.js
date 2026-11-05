const {test,expect}=require('@playwright/test');

test.beforeEach(async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.route('**/*',route=>{
    const url=new URL(route.request().url());
    return url.hostname==='127.0.0.1'?route.continue():route.abort();
  });
});

for(const width of [360,1280]){
  test(`public secondary text remains readable in both themes at ${width}px`,async({page})=>{
    test.setTimeout(90000); // Fourteen page visits, with a network-idle wait on each.
    await page.setViewportSize({width,height:900});
    for(const dark of [false,true]){
      await page.addInitScript(value=>sessionStorage.setItem('theme',value?'dark':'light'),dark);
      for(const [path,selector] of [
        ['/','.recent-publications-footer a'],
        ['/revistas','.open-badge'],
        ['/revistas','.publication-card dt'],
        ['/revistas','.publication-card footer a'],
        ['/autores','.contributor-call .eyebrow'],
        ['/aprender','.save-resource'],
        ['/diretrizes-para-autores','.legal-content a']
      ]){
        await page.goto(path,{waitUntil:'networkidle'});
        const node=page.locator(selector).first();
        await expect(node).toBeVisible();
        const ratio=await node.evaluate(element=>{
          const rgb=value=>(value.match(/[\d.]+/g)||[]).map(Number);
          const blend=(front,back)=>front.slice(0,3).map((v,i)=>v*(front[3]??1)+back[i]*(1-(front[3]??1)));
          const ancestors=[];for(let n=element;n;n=n.parentElement)ancestors.unshift(n);
          let background=[255,255,255];
          for(const n of ancestors)background=blend(rgb(getComputedStyle(n).backgroundColor),background);
          const style=getComputedStyle(element);
          const foreground=blend([...rgb(style.color).slice(0,3),Number(style.opacity)],background);
          const luminance=color=>color.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
          const a=luminance(foreground),b=luminance(background);
          return(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
        });
        expect(ratio,`${path} ${selector} ${dark?'dark':'light'}`).toBeGreaterThanOrEqual(4.5);
        expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
      }
    }
  });
}

for(const stored of ['{invalid','{}']){
  test(`learning collection recovers from malformed saved data: ${stored}`,async({page})=>{
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(value=>localStorage.setItem('learningCollection',value),stored);
    await page.goto('/aprender');
    const save=page.locator('.save-resource').first();await save.click();
    await expect(save).toHaveText('Guardado ✓');
    const values=await page.evaluate(()=>JSON.parse(localStorage.getItem('learningCollection')));
    expect(values).toContain(await save.getAttribute('data-resource'));
    await page.locator('#resourceSearch').fill('impossivel-encontrar-recurso');
    await expect(page.locator('#resourceEmpty')).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test('blocked browser storage reports the failure without breaking resource filters',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Blocked','SecurityError')}}));
  await page.goto('/aprender');
  const save=page.locator('.save-resource').first();await save.click();
  await expect(save).toContainText('Não foi possível guardar');
  await page.locator('#resourceSearch').fill('impossivel-encontrar-recurso');
  await expect(page.locator('#resourceEmpty')).toBeVisible();
  expect(errors).toEqual([]);
});
