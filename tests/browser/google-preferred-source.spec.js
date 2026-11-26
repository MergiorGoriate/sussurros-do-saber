const { execFileSync } = require('node:child_process');
const { test, expect } = require('@playwright/test');

const publisherScript = 'https://news.google.com/swg/js/v1/publisher.js';
const preferenceLink = 'https://www.google.com/preferences/source?q=www.sussurrosdosaber.com';

test('preferred source stays visible beside the author when the Google script is unavailable', async ({ page }) => {
  execFileSync('python', ['tests/browser/science_news_fixture.py']);
  await page.route(publisherScript, route => route.abort());
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const articlePath = await page.locator('a[href^="/artigo/"]').first().getAttribute('href');
  for (const path of ['/', '/en/', '/artigos', '/en/artigos', '/noticias', '/en/news']) {
    await page.goto(path);
    await expect(page.locator('.google-preferred-source')).toHaveCount(0);
    await expect(page.locator('script[src="' + publisherScript + '"]')).toHaveCount(0);
  }

  for (const path of [articlePath, '/noticias/ensaio-noticia-movel']) {
    await page.goto(path);
    const row = page.locator('.author-preferred-row');
    const identity = row.locator('.author-preferred-identity');
    const button = row.locator('.google-preferred-source-fallback');
    await expect(button).toBeVisible();
    await expect(button).toHaveAttribute('href', preferenceLink);
    const authorBox = await identity.boundingBox();
    const buttonBox = await button.boundingBox();
    expect(buttonBox.x).toBeGreaterThan(authorBox.x + authorBox.width);
    expect(Math.abs((buttonBox.y + buttonBox.height / 2) - (authorBox.y + authorBox.height / 2))).toBeLessThan(3);

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(button).toBeVisible();
    const mobileAuthor = await identity.boundingBox();
    const mobileButton = await button.boundingBox();
    expect(mobileButton.y).toBeGreaterThanOrEqual(mobileAuthor.y + mobileAuthor.height);
    expect(mobileButton.x + mobileButton.width).toBeLessThanOrEqual(390);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
    await page.setViewportSize({ width: 1440, height: 900 });
  }
});

test('the direct-link alternative disappears after the official widget renders', async ({ page }) => {
  execFileSync('python', ['tests/browser/science_news_fixture.py']);
  await page.route(publisherScript, route => route.fulfill({
    contentType: 'application/javascript',
    body: `const render = () => {
      const widget = document.querySelector('[google-add-preferred-source-btn]');
      const button = document.createElement('button');
      button.textContent = 'Google widget test';
      button.style.height = '40px';
      widget.attachShadow({mode: 'open'}).appendChild(button);
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', render);
    else render();`,
  }));
  await page.goto('/noticias/ensaio-noticia-movel');
  await expect(page.getByRole('button', { name: 'Google widget test' })).toBeVisible();
  await expect(page.locator('.google-preferred-source-fallback')).toBeHidden();
});
