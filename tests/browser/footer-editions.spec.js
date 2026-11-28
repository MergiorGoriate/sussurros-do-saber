const {test,expect} = require('@playwright/test');

test('publication strip replaces the gap, keeps all three logos clickable, and adapts to mobile', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  for (const width of [1440,768,390,320]) {
    await page.setViewportSize({width,height:900});
    await page.goto('/');
    const consent = page.getByRole('button',{name:'Recusar não essenciais'});
    if (await consent.isVisible()) await consent.click();
    const strip = page.locator('.footer-editions');
    await strip.scrollIntoViewIfNeeded();
    const links=strip.getByRole('link');
    await expect(links).toHaveCount(3);
    for (const item of await links.all()) {
      await expect(item).toBeVisible();
      const image=item.locator('img');
      await expect.poll(() => image.evaluate(img=>img.complete&&img.naturalWidth>0)).toBeTruthy();
      const box=await item.boundingBox();
      expect(box.height).toBeGreaterThanOrEqual(44);
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x+box.width).toBeLessThanOrEqual(width+1);
    }
    const bottom=await page.locator('.newsletter-signup').boundingBox();
    const band=await strip.boundingBox();
    expect(Math.abs(band.y-(bottom.y+bottom.height))).toBeLessThanOrEqual(1);
    await expect(page.locator('.footer-layout')).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width+1);
    await page.evaluate(()=>document.documentElement.classList.add('dark'));
    await expect(strip).toHaveCSS('background-color','rgb(32, 44, 53)');
  }
  await page.goto('/en/');
  const strip=page.locator('.footer-editions');
  await expect(strip).toHaveAttribute('aria-label','Sussurros do Saber publications');
  for (const [name,href] of [['Sussurros do Saber','/en/'],['SS News','/en/news'],['Scientific journal','/en/revistas']]) {
    await expect(strip.getByRole('link',{name,exact:true})).toHaveAttribute('href',href);
  }
  await strip.getByRole('link',{name:'SS News',exact:true}).click();
  await expect(page).toHaveURL(/\/en\/news$/);
  await page.locator('.footer-editions').getByRole('link',{name:'Scientific journal',exact:true}).click();
  await expect(page).toHaveURL(/\/en\/revistas$/);
});
