const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
for(const width of [320,1440]){
  test(`compact theme control stays beside notifications at ${width}px`,async({page})=>{
    const cookie=execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();
    await page.context().addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
    await page.setViewportSize({width,height:900});
    await page.goto('/admin');
    const toggle=page.getByRole('button',{name:'Alternar tema do painel',exact:true});
    await expect(toggle.locator('svg')).toBeVisible();
    const theme=await toggle.boundingBox();
    const bell=await page.locator('.notice-bar > summary').boundingBox();
    expect(theme.width).toBe(44);
    expect(theme.height).toBe(44);
    expect(Math.abs(theme.y-bell.y)).toBeLessThan(2);
    expect(theme.x+theme.width).toBeLessThan(bell.x);
    expect(await toggle.evaluate(el=>getComputedStyle(el).position)).not.toBe('fixed');
    const before=await toggle.getAttribute('aria-pressed');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-pressed',before==='true'?'false':'true');
    await expect(toggle.locator('svg')).toBeVisible();
    await page.reload();
    await expect(toggle).toHaveAttribute('aria-pressed',before==='true'?'false':'true');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  });
}
