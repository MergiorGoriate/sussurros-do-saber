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
  // Third-party advertising is tested separately; avoid external network and
  // consent-dependent noise in the first-party CSP regression test.
  await page.route('https://pagead2.googlesyndication.com/**', route =>
    route.fulfill({ status: 200, contentType: 'application/javascript', body: '' })
  );
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

test('back-to-top stays above the assistant and returns to the start', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const button = page.getByRole('button', { name: 'Voltar ao topo' });
  await expect(button).toBeHidden();
  await page.evaluate(() => window.scrollTo(0, 700));
  await expect(button).toBeVisible();
  const launcher = page.getByRole('button', { name: 'Abrir assistente' });
  await expect(launcher).toBeVisible();
  const boxes = await Promise.all([button.boundingBox(), launcher.boundingBox()]);
  expect(boxes[0].y + boxes[0].height).toBeLessThan(boxes[1].y);
  await button.click();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeLessThan(20);
  await page.evaluate(() => window.scrollTo(0, 700));
  await launcher.click();
  await expect(button).toBeHidden();
});


test('journal mobile index stays inside the viewport and can be collapsed', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  const response = await page.goto('/revistas/revista-de-teste-cientifico', { waitUntil: 'domcontentloaded' });
  expect(response.status()).toBe(200);
  const details = page.locator('#journal-mobile-toc');
  const summary = details.locator('summary');
  await expect(summary).toBeVisible();
  await summary.click();
  await expect(details).toHaveAttribute('open', '');
  const toc = page.locator('#journal-toc');
  await expect(toc).toBeVisible();
  const box = await toc.boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(360);
  expect(box.width).toBeLessThanOrEqual(360);
  await summary.click();
  await expect(details).not.toHaveAttribute('open', '');
});


for (const width of [320, 768]) {
  test(`journal index preserves all sections at ${width}px and closes with Escape`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await page.goto('/revistas/revista-de-teste-cientifico', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#journal-article-title')).toHaveText('Artigo de teste');
    await expect(page.locator('#conteudo-revista h2').first()).toHaveText('Introdução');
    await page.locator('#cookieReject').click();
    await page.locator('#themeToggle').click();
    await page.locator('#journal-mobile-toc summary').click();
    const links=page.locator('#journal-content-index a');
    await expect(links).toHaveCount(4);
    const bounds=await page.locator('#journal-toc').boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x+bounds.width).toBeLessThanOrEqual(width);
    const color=await links.first().evaluate(element=>getComputedStyle(element).color);
    expect(color).toBe('rgb(226, 232, 240)');
    await page.keyboard.press('Escape');
    await expect(page.locator('#journal-mobile-toc')).not.toHaveAttribute('open','');
  });
}

test('journal bookmarks survive malformed storage and appear in Favorites', async ({ page }) => {
  await page.addInitScript(()=>{if(!localStorage.getItem('savedJournalArticles'))localStorage.setItem('savedJournalArticles','invalid json');if(!localStorage.getItem('journalAlerts'))localStorage.setItem('journalAlerts','{}');});
  await page.goto('/revistas/revista-de-teste-cientifico', { waitUntil: 'domcontentloaded' });
  await page.locator('#cookieReject').click();
  await page.locator('.journal-save-btn').click();
  await expect(page.locator('.journal-save-btn')).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('#journal-action-status')).toContainText('Artigo guardado');
  await page.goto('/favoritos', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#favoritesGrid')).toContainText('Artigo de teste');
  await expect(page.locator('#favoritesEmpty')).toBeHidden();
});
