const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
async function contrast(locator){
  return locator.evaluate(el=>{
    const rgb=value=>(value.match(/[\d.]+/g)||[]).map(Number);
    const luminance=c=>c.slice(0,3).map(v=>{v/=255;return v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[0.2126,0.7152,0.0722][i],0);
    const fg=rgb(getComputedStyle(el).color);
    let parent=el,bg;
    while(parent){const c=rgb(getComputedStyle(parent).backgroundColor);if(c.length===3||c[3]===1){bg=c;break;}parent=parent.parentElement;}
    if(!bg)throw new Error('Missing opaque background');
    const a=luminance(fg),b=luminance(bg);
    return (Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
  });
}
for(const width of [320,1440]){
  test(`dark empty inbox and management forms remain readable at ${width}px`,async({page})=>{
    const data=JSON.parse(execFileSync('python',['tests/browser/lifecycle_fixture.py'],{encoding:'utf8'}));
    await page.context().addCookies([{name:'session',value:data.cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
    await page.addInitScript(()=>localStorage.setItem('sussurros.admin.theme','dark'));
    await page.setViewportSize({width,height:900});
    await page.goto('/admin/notificacoes');
    for(let i=0;i<2;i++)await page.locator('.notice-card').first().getByRole('button',{name:'Eliminar aviso',exact:true}).click();
    const empty=page.locator('.notice-empty');
    await expect(empty).toBeVisible();
    await expect(page.locator('body')).toHaveClass(/admin-dark/);
    expect(await contrast(empty.locator('h2'))).toBeGreaterThanOrEqual(4.5);
    expect(await contrast(empty.locator('p'))).toBeGreaterThanOrEqual(4.5);
    const disabled=page.locator('.management-toolbar button');
    await expect(disabled).toBeDisabled();
    expect(await contrast(disabled)).toBeGreaterThanOrEqual(4.5);
    await page.screenshot({path:`/tmp/dark-panel-previews/empty-dark-${width}.png`,fullPage:true,animations:'disabled'});
    await page.getByRole('button',{name:'Alternar tema do painel',exact:true}).click();
    expect(await contrast(empty.locator('h2'))).toBeGreaterThanOrEqual(4.5);
    expect(await contrast(empty.locator('p'))).toBeGreaterThanOrEqual(4.5);
    await page.getByRole('button',{name:'Alternar tema do painel',exact:true}).click();
    await page.context().addCookies([{name:'session',value:data.founder_cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
    await page.goto('/admin/equipa');
    const field=page.locator('.staff-management input:not([type=hidden]):not([type=checkbox])').first();
    await expect(field).toBeVisible();
    expect(await field.evaluate(el=>getComputedStyle(el).colorScheme)).toBe('dark');
    expect(await contrast(field)).toBeGreaterThanOrEqual(4.5);
    await page.screenshot({path:`/tmp/dark-panel-previews/team-dark-${width}.png`,fullPage:true,animations:'disabled'});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  });
}
