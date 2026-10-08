const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');

async function adminLogin(page) {
  const cookie = execFileSync('python', ['tests/browser/staff_fixture.py'], { encoding: 'utf8' }).trim();
  await page.context().addCookies([{ name: 'session', value: cookie,
    url: 'http://127.0.0.1:5000', httpOnly: true, sameSite: 'Lax' }]);
}

test('staff management pages render at desktop and mobile widths', async ({ page }) => {
  await adminLogin(page);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const [path, title] of [
      ['/admin/equipa', 'Equipa e convites'], ['/admin/funcoes', 'Funções e permissões'],
      ['/admin/trabalho', 'Área de trabalho'], ['/admin/documentos-equipa', 'Documentos privados da equipa'],
      ['/admin/historico-remocoes', 'Histórico de remoções'], ['/admin/notificacoes', 'Notificações internas'], ['/admin/relatorios-equipa', 'Relatórios e auditoria']
    ]) {
      const response = await page.goto(path, { waitUntil: 'domcontentloaded' });
      expect(response.status(), path).toBe(200);
      expect(response.headers()['cache-control']).toContain('no-store');
      await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
      if (['/admin/equipa','/admin/funcoes','/admin/historico-remocoes','/admin/notificacoes'].includes(path)) {
        await page.screenshot({path: `test-results/management-${path.split('/').pop()}-${width}.png`, fullPage:true});
      }
      if (path === '/admin/funcoes') {
        expect(await page.locator('input[name="permissions"]').count()).toBe(24);
        const codes = await page.locator('input[name="permissions"]').evaluateAll(items => items.map(item => item.value));
        expect(new Set(codes).size).toBe(codes.length);
      }
      const overflow = await page.evaluate(() => ({width: innerWidth, document: document.documentElement.scrollWidth,
        elements: [...document.querySelectorAll('body *')].filter(e => { const r=e.getBoundingClientRect(); return r.right>innerWidth+1 && !e.closest('.table-wrap, nav'); }).slice(0,8).map(e=>({tag:e.tagName,classes:e.className,width:e.getBoundingClientRect().width}))}));
      expect(overflow.document <= width, JSON.stringify({path,...overflow})).toBeTruthy();
    }
  }
  expect(errors).toEqual([]);
});

test('public team page offers a confirmed-team empty state without private data', async ({ page }) => {
  await page.route('https://**/*', route => route.abort());
  const response = await page.goto('/equipa', { waitUntil: 'domcontentloaded' });
  expect(response.status()).toBe(200);
  await expect(page.getByRole('heading', { name: 'A nossa equipa' })).toBeVisible();
  expect(await page.locator('#conteudo input[name="email"], #conteudo textarea[name="contact_note"]').count()).toBe(0);
});
