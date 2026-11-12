const { test, expect } = require('@playwright/test');
const path = require('node:path');

for (const language of ['pt-MZ', 'en']) {
  test(`assistant language and duplicate submission protection: ${language}`, async ({ page }) => {
    // Exercise the production widget in an isolated page, without contacting AI.
    await page.route('https://assistant.test/**', route => route.fulfill({ contentType: 'text/html', body: `<html lang="${language}"><head></head><body></body></html>` }));
    await page.goto('https://assistant.test/');
    let resolveResponse;
    const responseReady = new Promise(resolve => { resolveResponse = resolve; });
    const payloads = [];
    await page.route('**/api/assistente', async route => {
      payloads.push(route.request().postDataJSON());
      await responseReady;
      await route.fulfill({ json: { ok: true, answer: 'Test answer', links: [] } });
    });
    await page.addScriptTag({ path: path.join(__dirname, '../../static/js/assistant.js') });
    await page.getByRole('button', { name: language === 'en' ? 'Open assistant' : 'Abrir assistente' }).click();
    const input = page.getByRole('textbox', { name: language === 'en' ? 'Message' : 'Mensagem' });
    await input.fill('Question');
    await input.press('Enter');
    await expect(page.locator('.assistant-window')).toHaveAttribute('aria-busy', 'true');
    await input.fill('Duplicate');
    await input.press('Enter');
    await expect(page.locator('.assistant-form button')).toBeDisabled();
    await expect.poll(() => payloads.length).toBe(1);
    expect(payloads[0]).toEqual({ message: 'Question', language: language === 'en' ? 'en' : 'pt' });
    resolveResponse();
    await expect(page.locator('.assistant-message.bot').last()).toHaveText('Test answer');
    await expect(page.locator('.assistant-form button')).toBeEnabled();
    await expect(page.locator('.assistant-window')).toHaveAttribute('aria-busy', 'false');
    await page.setViewportSize({ width: 360, height: 640 });
    const box = await page.locator('.assistant-window').boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(360);
  });
}
