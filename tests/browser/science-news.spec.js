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
  const source = page.getByRole('link', { name: 'Publicação primária de ensaio' });
  await expect(source).toHaveAttribute('href', 'https://example.org/primary-source');
  await expect(page.locator('.news-detail')).toBeVisible();
  await page.route('https://example.org/primary-source', route =>
    route.fulfill({ contentType: 'text/html', body: '<h1>Original source fixture</h1>' }));
  await source.click();
  await expect(page).toHaveURL('https://example.org/primary-source');
  await expect(page.getByRole('heading', { name: 'Original source fixture' })).toBeVisible();
  await page.goBack();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
  await page.getByRole('link', { name: 'Voltar às Notícias de Ciência' }).click();
  await expect(page.getByLabel('Tema', { exact: true })).toHaveValue(fixture.theme);
  await expect(page).toHaveURL(new RegExp('/noticias\\?tema=' + fixture.theme + '$'));
});
