const { expect, test } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

test.beforeAll(() => {
  execFileSync(process.env.PYTHON_BIN || 'python', [join(__dirname, 'science_video_fixture.py')], {
    stdio: 'pipe',
  });
});

test('mobile science videos, language, colour scheme and native playback', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 820 });
  const videoBytes = Buffer.from(readFileSync(join(__dirname, 'science-video-fixture.base64'), 'ascii'), 'base64');
  await page.route('https://example.test/science-video-e2e.webm', route =>
    route.fulfill({ status: 200, contentType: 'video/webm', body: videoBytes }));
  await page.route('https://example.test/science-video-e2e.jpg', route => route.fulfill({ status: 404 }));
  await page.goto('/en/videos');
  await expect(page.getByRole('heading', { name: 'Science Videos' })).toBeVisible();
  await page.locator('#cookieAccept').click();
  await page.locator('#menuToggle').click();
  await expect(page.locator('#mainNav').getByRole('link', { name: 'Science Videos' })).toBeVisible();
  await page.locator('#menuToggle').click();
  await page.getByRole('searchbox', { name: 'Search videos' }).fill('Synthetic');
  await page.getByRole('button', { name: 'Apply', exact: true }).click();
  await expect(page).toHaveURL(/q=Synthetic/);
  await page.locator('#themeToggle').click();
  await expect(page.locator('#themeToggle')).toHaveAttribute('aria-pressed', 'true');
  const view = page.waitForResponse(response => response.url().endsWith('/api/videos/playback') && response.status() === 204);
  await page.getByRole('link', { name: /Synthetic science video/ }).click();
  await view;
  await expect(page.getByRole('heading', { name: 'Synthetic science video' })).toBeVisible();
  const player = page.locator('video.science-player');
  await expect(player).toBeVisible();
  await expect(player).toHaveAttribute('controls', '');
  await expect(player).not.toHaveAttribute('autoplay');
  const ended = page.waitForResponse(response => response.url().endsWith('/api/videos/playback') &&
    response.request().postDataJSON()?.event === 'end' && response.status() === 204);
  await player.evaluate(element => { element.muted = true; return element.play(); });
  await ended;
  const bounds = await player.boundingBox();
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(390);
});
