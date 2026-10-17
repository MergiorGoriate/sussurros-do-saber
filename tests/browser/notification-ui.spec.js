const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');

for(const width of [320,390,1440]) {
  test(`notification menu, filters and reading at ${width}px`,async({page})=>{
    const d=JSON.parse(execFileSync('python',['tests/browser/lifecycle_fixture.py'],{encoding:'utf8'}));
    await page.context().addCookies([{name:'session',value:d.cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
    await page.setViewportSize({width,height:900});
    await page.goto('/admin/notificacoes');
    const bar=page.locator('[data-notice-bar]');
    await bar.locator('summary').click();
    await expect(bar.locator('[data-notice-status]')).toHaveText('Notificações actualizadas.');
    await expect(bar.locator('.notice-item')).toHaveCount(2);
    const bounds=await bar.locator('.notice-popover').boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x+bounds.width).toBeLessThanOrEqual(width);
    expect(bounds.y+bounds.height).toBeLessThanOrEqual(900);
    expect(await bar.locator('button').first().evaluate(el=>parseFloat(getComputedStyle(el).borderRadius))).toBeGreaterThan(0);
    await page.screenshot({path:`test-results/notification-menu-${width}.png`,fullPage:true});
    await bar.locator('summary').press('Escape');
    await expect(bar).not.toHaveAttribute('open','');
    await expect(bar.locator('summary')).toBeFocused();
    await page.locator('.notice-filters a').filter({hasText:'Por ler'}).click();
    await expect(page.locator('.notice-filters [aria-current]')).toContainText('Por ler');
    await expect(page.locator('.notice-card')).toHaveCount(2);
    await page.screenshot({path:`test-results/notification-inbox-${width}.png`,fullPage:true});
    await page.locator('.notice-card').first().getByRole('link',{name:'Abrir recurso'}).click();
    await page.goto('/admin/notificacoes?status=read');
    await expect(page.locator('.notice-card')).toHaveCount(1);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.evaluate(()=>document.body.classList.add('admin-dark'));
    await page.screenshot({path:`test-results/notification-dark-${width}.png`,fullPage:true});
  });
}
