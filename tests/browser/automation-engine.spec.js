const { execFileSync } = require('node:child_process');
const { test, expect } = require('@playwright/test');

test('automation dashboard, configuration and queued run work at mobile and desktop widths', async ({ page, context }) => {
  const cookie = execFileSync('python', ['tests/browser/staff_fixture.py'], { encoding: 'utf8' }).trim();
  await context.addCookies([{name:'session', value:cookie, url:'http://127.0.0.1:5000', httpOnly:true, sameSite:'Lax'}]);
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/admin/automacao');
    await expect(page.getByRole('heading', { name:'Sussurros Automation Engine' })).toBeVisible();
    await expect(page.locator('.automation-grid > section')).toHaveCount(5);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
  }
  await page.goto('/admin/automacao/operadores/workflow');
  await page.getByLabel('Operador activo').check();
  await page.getByRole('button', {name:'Guardar configuração'}).click();
  await page.goto('/admin/automacao');
  const workflow = page.locator('.automation-grid > section').filter({ has:page.getByRole('heading', {name:'Fluxo editorial'}) });
  await workflow.getByRole('button', {name:'Executar'}).click();
  await expect(page.getByText('A execução aguarda o próximo comando', {exact:false})).toBeVisible();
  await page.getByRole('link', {name:'Execuções', exact:true}).click();
  await expect(page.locator('table')).toContainText('queued');
  await page.goto('/admin/automacao/operadores/workflow');
  await page.getByLabel('Operador activo').uncheck();
  await page.getByRole('button', {name:'Guardar configuração'}).click();
});
