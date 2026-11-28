const { execFileSync } = require('node:child_process');
const { test, expect } = require('@playwright/test');

test('mobile news menu, topic filter, original source and return to the filtered list', async ({ page }) => {
  const fixture = JSON.parse(execFileSync('python', ['tests/browser/science_news_fixture.py'], { encoding: 'utf8' }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.locator('#menuToggle').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#menuToggle')).toHaveAttribute('aria-expanded', 'true');
  await page.locator('#mainNav').getByRole('link', { name: 'Notícias', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Notícias de Ciência', exact: true })).toBeVisible();
  await page.getByLabel('Tema', { exact: true }).selectOption(fixture.theme);
  await page.getByRole('button', { name: 'Filtrar', exact: true }).click();
  await expect(page).toHaveURL(new RegExp('/noticias\\?tema=' + fixture.theme + '$'));
  await page.getByRole('link', { name: fixture.title, exact: true }).click();
  await expect(page.getByRole('heading', { name: fixture.title, exact: true })).toBeVisible();
  const reference = page.locator('.news-reference-list li').filter({ hasText: 'Publicação primária de ensaio' });
  await expect(reference).toHaveCount(1);
  const source = reference.getByRole('link', { name: 'Consultar fonte' });
  await expect(source).toHaveAttribute('href', 'https://example.org/primary-source');
  await expect(source).toHaveAttribute('target', '_blank');
  await expect(page.locator('.news-detail')).toBeVisible();
  await page.context().route('https://example.org/primary-source', route =>
    route.fulfill({ contentType: 'text/html', body: '<h1>Original source fixture</h1>' }));
  const [sourcePage] = await Promise.all([
    page.waitForEvent('popup'),
    source.click(),
  ]);
  await expect(sourcePage).toHaveURL('https://example.org/primary-source');
  await expect(sourcePage.getByRole('heading', { name: 'Original source fixture' })).toBeVisible();
  await sourcePage.close();
  await expect(page.getByRole('heading', { name: fixture.title, exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
  await page.getByRole('link', { name: 'Voltar às Notícias de Ciência' }).click();
  await expect(page.getByLabel('Tema', { exact: true })).toHaveValue(fixture.theme);
  await expect(page).toHaveURL(new RegExp('/noticias\\?tema=' + fixture.theme + '$'));
});

test('science news headings and secondary links have readable colours in dark mode', async ({ page }) => {
  const fixture = JSON.parse(execFileSync('python', ['tests/browser/science_news_fixture.py'], { encoding: 'utf8' }));
  await page.goto('/noticias');
  await page.evaluate(() => {
    document.documentElement.classList.add('dark');
    document.body.classList.add('dark');
  });
  const heading = page.locator('.sn-lead-heading');
  await expect(heading).toBeVisible();
  await expect(heading).toHaveCSS('color', 'rgb(241, 245, 252)');
  await expect(page.locator('.sn-filters label')).toHaveCSS('color', 'rgb(241, 245, 252)');
  const secondary = page.locator('.sn-side .news-card-copy h2 a').filter({ hasText: fixture.secondary_title });
  await expect(secondary).toHaveCount(1);
  await expect(secondary).toBeVisible();
  await expect(secondary).toHaveCSS('color', 'rgb(241, 245, 252)');
  await expect(page.locator('.sn-side .eyebrow').first()).toHaveCSS('color', 'rgb(157, 204, 255)');
});

test('SS News masthead, editorial composition and topic tabs respond to screen width', async ({ page }) => {
  const fixture = JSON.parse(execFileSync('python', ['tests/browser/science_news_fixture.py'], { encoding: 'utf8' }));
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/noticias');
    const logo = page.locator('.sn-brand-link img');
    await expect(logo).toBeVisible();
    await expect.poll(() => logo.evaluate(image => image.complete && image.naturalWidth > 0)).toBeTruthy();
    await expect(page.locator('.sn-brand-copy p')).toHaveText('Notícias de ciência e investigação');
    await expect(page.locator('.sn-read-link')).toBeVisible();
    const image = page.locator('.news-lead .news-cover');
    await image.scrollIntoViewIfNeeded();
    await expect.poll(() => image.evaluate(img => img.complete && img.naturalWidth > 0)).toBeTruthy();
    const picture = await image.boundingBox();
    const headline = await page.locator('.news-lead h2').boundingBox();
    if (width > 700) expect(headline.x).toBeGreaterThanOrEqual(picture.x + picture.width - 1);
    else expect(headline.y).toBeGreaterThanOrEqual(picture.y + picture.height - 1);
    await expect(page.locator('.sn-side .news-card')).toHaveCount(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    if (width > 700) {
      const tab = page.locator('.sn-topic-nav a').filter({hasText:'Saúde'});
      await expect(tab).toBeVisible();
      await tab.click();
      await expect(page).toHaveURL(new RegExp('/noticias\\?tema=' + fixture.theme + '$'));
      await expect(page.locator('.sn-topic-nav [aria-current="page"]')).toHaveText('Saúde');
    } else {
      await expect(page.getByLabel('Tema', {exact:true})).toBeVisible();
    }
  }
  await page.goto('/en/news');
  await expect(page.locator('.sn-brand-copy p')).toHaveText('Science and research news');
  await expect(page.locator('.sn-brand-link')).toHaveAttribute('href', '/en/news');
});

for (const [path, selector] of [['/', '.home-science-news'], ['/noticias', '.science-news']]) {
  for (const reducedMotion of ['no-preference', 'reduce']) {
    test(`news entrance on ${path} respects ${reducedMotion}`, async ({ page }) => {
      execFileSync('python', ['tests/browser/science_news_fixture.py']);
      await page.setViewportSize({ width: 390, height: 844 });
      await page.emulateMedia({ reducedMotion });
      await page.addInitScript(() => {
        window.newsEntrances = [];
        const animate = Element.prototype.animate;
        Element.prototype.animate = function (...args) {
          if (this.matches('.home-science-news .news-card, .science-news .news-card')) window.newsEntrances.push(this.className);
          return animate.apply(this, args);
        };
      });
      await page.goto(path);
      const cards = page.locator(selector + ' .news-card');
      await expect(cards.first()).toBeAttached();
      await cards.first().scrollIntoViewIfNeeded();
      await expect(cards.first()).toBeVisible();
      if (reducedMotion === 'no-preference') {
        await expect.poll(() => page.evaluate(() => window.newsEntrances.length)).toBeGreaterThan(0);
      } else {
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        expect(await page.evaluate(() => window.newsEntrances.length)).toBe(0);
        await expect(cards.first()).toHaveCSS('opacity', '1');
      }
      await expect(cards.first().getByRole('link').first()).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
    });
  }
}
