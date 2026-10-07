const { test, expect } = require('@playwright/test');
const crypto = require('node:crypto');

async function adminLogin(page) {
  const response = await page.request.get('/admin/login');
  const token = (await response.text()).match(/name="csrf_token" value="([^"]+)"/)[1];
  const challenge = await page.request.post('/admin/login', { form: {
    csrf_token: token, username: process.env.ADMIN_USERNAME || 'ci-admin',
    password: process.env.ADMIN_PASSWORD || 'ci-only-strong-password'
  }});
  const challengeToken = (await challenge.text()).match(/name="csrf_token" value="([^"]+)"/)[1];
  const secret = process.env.ADMIN_TOTP_SECRET || 'JBSWY3DPEHPK3PXP';
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const bits = [...secret].map(c => alphabet.indexOf(c).toString(2).padStart(5, '0')).join('');
  const key = Buffer.from(bits.match(/.{8}/g).map(byte => parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const digest = crypto.createHmac('sha1', key).update(counter).digest();
  const offset = digest[19] & 15;
  const code = String((digest.readUInt32BE(offset) & 0x7fffffff) % 1000000).padStart(6, '0');
  const signedIn = await page.request.post('/admin/verificar-2fa', { form: { csrf_token: challengeToken, code }});
  expect(signedIn.status()).toBe(200);
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
      ['/admin/notificacoes', 'Notificações internas'], ['/admin/relatorios-equipa', 'Relatórios e auditoria']
    ]) {
      const response = await page.goto(path, { waitUntil: 'domcontentloaded' });
      expect(response.status(), path).toBe(200);
      expect(response.headers()['cache-control']).toContain('no-store');
      await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), path + ' at ' + width).toBeTruthy();
    }
  }
  expect(errors).toEqual([]);
});

test('public team page offers a confirmed-team empty state without private data', async ({ page }) => {
  await page.route('https://**/*', route => route.abort());
  const response = await page.goto('/equipa', { waitUntil: 'domcontentloaded' });
  expect(response.status()).toBe(200);
  await expect(page.getByRole('heading', { name: 'A nossa equipa' })).toBeVisible();
  expect(await page.locator('input[name="email"], textarea[name="contact_note"]').count()).toBe(0);
});
