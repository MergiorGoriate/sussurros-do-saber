const { test, expect } = require('@playwright/test');

test('strict CSP authorizes scripts with a per-response nonce', async ({ request }) => {
  const first = await request.get('/');
  const second = await request.get('/');
  expect(first.ok()).toBeTruthy();
  const firstPolicy = first.headers()['content-security-policy'];
  const secondPolicy = second.headers()['content-security-policy'];
  expect(firstPolicy).toContain("'strict-dynamic'");
  expect(firstPolicy).toContain("script-src-attr 'none'");
  expect(firstPolicy).not.toContain("'unsafe-eval'");
  const firstNonce = firstPolicy.match(/script-src 'nonce-([^']+)'/);
  const secondNonce = secondPolicy.match(/script-src 'nonce-([^']+)'/);
  expect(firstNonce).not.toBeNull();
  expect(secondNonce).not.toBeNull();
  expect(firstNonce[1]).not.toBe(secondNonce[1]);
  expect(await first.text()).toContain(`nonce="${firstNonce[1]}"`);
});

test('public pages load without JavaScript or CSP errors', async ({ page }) => {
  const failures = [];
  page.on('pageerror', error => failures.push(error.message));
  page.on('console', message => {
    const text = message.text();
    if (
      message.type() === 'error'
      && /content security policy|refused to execute|violates.*script-src/i.test(text)
    ) failures.push(text);
  });

  for (const path of ['/', '/artigos', '/autores', '/revistas', '/contacto']) {
    const response = await page.goto(path, { waitUntil: 'networkidle' });
    expect(response.status(), path).toBe(200);
    await expect(page.locator('body')).toBeVisible();
  }

  expect(failures, failures.join('\n')).toEqual([]);
});

test('compiled Tailwind and application JavaScript are served locally', async ({ page }) => {
  const responses = new Map();
  page.on('response', response => responses.set(new URL(response.url()).pathname, response.status()));
  await page.goto('/', { waitUntil: 'networkidle' });
  expect(responses.get('/static/css/tailwind.css')).toBe(200);
  expect(responses.get('/static/js/main.js')).toBe(200);
  const cdnScripts = await page.locator('script[src*="cdn.tailwindcss.com"]').count();
  expect(cdnScripts).toBe(0);
});

test('broken external images switch to the local fallback', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    const image = document.createElement('img');
    image.id = 'ci-broken-image';
    image.alt = 'Imagem de teste';
    image.src = 'https://invalid.example.invalid/not-found.jpg';
    document.body.appendChild(image);
  });
  await expect(page.locator('#ci-broken-image')).toHaveAttribute(
    'src',
    '/static/img/image-fallback.svg',
    { timeout: 10000 }
  );
  const fallback = await page.request.get('/static/img/image-fallback.svg');
  expect(fallback.status()).toBe(200);
});

test('admin login remains protected and free of inline handlers', async ({ page }) => {
  const response = await page.goto('/admin/login', { waitUntil: 'networkidle' });
  expect(response.status()).toBe(200);
  await expect(page.locator('form')).toBeVisible();
  expect(await page.locator('[onclick], [onload], [onerror]').count()).toBe(0);
});
