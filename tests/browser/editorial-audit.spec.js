const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');

test('assigned editor reads delivered report on mobile and desktop without assignment powers', async ({ page }) => {
  const data = JSON.parse(execFileSync('python', ['tests/browser/editorial_audit_fixture.py'], { encoding: 'utf8' }));
  await page.context().addCookies([{ name: 'session', value: data.cookie,
    url: 'http://127.0.0.1:5000', httpOnly: true, sameSite: 'Lax' }]);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const dark of [false, true]) {
      await page.goto(`/admin/submissoes/${data.manuscript_id}`);
      await page.emulateMedia({ colorScheme: dark ? 'dark' : 'light' });
      await page.getByRole('link', { name: 'Consultar pareceres científicos', exact: true }).click();
      await expect(page.getByRole('heading', { name: 'Revisão científica', exact: true })).toBeVisible();
      await expect(page.locator('select[name="reviewer_id"]')).toHaveCount(0);
      await page.locator('td details summary').click();
      await expect(page.getByText(data.report, { exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      await page.screenshot({ path: `test-results/assigned-editor-${width}-${dark ? 'dark' : 'light'}.png`, fullPage: true });
    }
  }
  expect(errors).toEqual([]);
});
