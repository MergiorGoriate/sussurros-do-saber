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
