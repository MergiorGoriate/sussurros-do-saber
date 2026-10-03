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

test('journal header and first content have compact spacing on desktop and mobile', async ({ page }) => {
  for (const width of [1440, 360]) {
    await page.setViewportSize({width, height:900});
    await page.goto('/revistas/revista-de-teste-cientifico', {waitUntil:'domcontentloaded'});
    const gaps=await page.evaluate(()=>{
      const hero=document.querySelector('.journal-hero').getBoundingClientRect();
      const header=document.querySelector('.journal-article-header').getBoundingClientRect();
      const content=document.querySelector('#conteudo-revista .article-markdown').firstElementChild.getBoundingClientRect();
      return {above:header.top-hero.bottom,below:content.top-header.bottom};
    });
    expect(gaps.above).toBeGreaterThanOrEqual(0);
    expect(gaps.above).toBeLessThanOrEqual(16);
    expect(gaps.below).toBeGreaterThanOrEqual(16);
    expect(gaps.below).toBeLessThanOrEqual(24);
  }
});

test('journal administrator can filter the catalog and preview Markdown tables', async ({ page }) => {
  const login=await page.request.get('/admin/login');
  const html=await login.text();
  const token=html.match(/name="csrf_token"[^>]*value="([^"]+)"/);
  expect(token).not.toBeNull();
  const response=await page.request.post('/admin/login',{form:{
    username:process.env.ADMIN_USERNAME||'admin',
    password:process.env.ADMIN_PASSWORD||'a-strong-test-password',
    csrf_token:token[1]
  }});
  expect(response.ok()).toBeTruthy();
  const challenge=await response.text();
  const challengeToken=challenge.match(/name="csrf_token"[^>]*value="([^"]+)"/);
  expect(challengeToken).not.toBeNull();
  const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const bits=[...(process.env.ADMIN_TOTP_SECRET||'JBSWY3DPEHPK3PXP')].map(c=>alphabet.indexOf(c).toString(2).padStart(5,'0')).join('');
  const key=Buffer.from(bits.match(/.{8}/g).map(byte=>parseInt(byte,2)));
  const counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));
  const digest=require('node:crypto').createHmac('sha1',key).update(counter).digest();
  const offset=digest[digest.length-1]&15;
  const code=String((digest.readUInt32BE(offset)&0x7fffffff)%1000000).padStart(6,'0');
  const verified=await page.request.post('/admin/verificar-2fa',{form:{csrf_token:challengeToken[1],code}});
  expect(verified.ok()).toBeTruthy();
  await page.goto('/admin/revistas', {waitUntil:'domcontentloaded'});
  await expect(page.locator('#journal-admin-search')).toBeVisible();
  await page.locator('#journal-admin-search').fill('nenhuma-revista-corresponde');
  await expect(page.locator('#journal-admin-empty')).toBeVisible();
  await page.goto('/admin/revistas/nova', {waitUntil:'domcontentloaded'});
  await page.locator('[name="content_markdown"]').fill('## Introdução\n\n| Grupo | Valor |\n| --- | --- |\n| A | 12 |');
  await expect(page.locator('[data-md-preview] table')).toBeVisible();
  await expect(page.locator('[data-md-preview]')).toContainText('Introdução');
  await expect(page.locator('#journal-word-count')).toContainText('palavras');
  await expect(page.locator('#journal-editor-status')).toHaveText('Alterações por guardar.');
  await page.locator('[data-md="chart"]').click();
  await expect(page.locator('[data-md-preview] .article-chart')).toBeVisible();
});

test('citation icon opens an accessible dialog with the article reference', async ({ page }) => {
  await page.addInitScript(() => {
    window.copiedCitation='';
    Object.defineProperty(navigator, 'clipboard', {configurable:true,value:{
      writeText: async text => {window.copiedCitation=text;}
    }});
  });
  for (const width of [1440, 320]) {
    await page.setViewportSize({width,height:800});
    await page.goto('/revistas/revista-de-teste-cientifico', {waitUntil:'domcontentloaded'});
    const consent=page.locator('#cookieReject');
    if(await consent.isVisible())await consent.click();
    if(width===320)await page.locator('#themeToggle').click();
    await page.locator('.journal-cite-btn').click();
    const dialog=page.getByRole('dialog', {name:'Citar este artigo'});
    await expect(dialog).toBeVisible();
    await expect(page.locator('#journal-citation-text')).toHaveValue(/Artigo de teste/);
    await expect(page.locator('#journal-citation-text')).toHaveValue(/Revista de Teste Científico/);
    const bounds=await dialog.boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x+bounds.width).toBeLessThanOrEqual(width);
    expect(await page.evaluate(()=>window.copiedCitation)).toBe('');
    await page.locator('#journal-citation-copy').click();
    await expect(page.locator('#journal-citation-status')).toHaveText('Citação copiada.');
    expect(await page.evaluate(()=>window.copiedCitation)).toContain('Artigo de teste');
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(page.locator('.journal-cite-btn')).toBeFocused();
    await page.evaluate(()=>{window.copiedCitation='';});
    await page.locator('.journal-cite-btn').click();
    await page.getByRole('button',{name:'Fechar citação',exact:true}).click();
    await expect(dialog).toBeHidden();
  }
});

test('citation remains available when clipboard permission is denied', async ({ page }) => {
  await page.addInitScript(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{
    writeText:async()=>{throw new Error('denied');}
  }}));
  await page.goto('/revistas/revista-de-teste-cientifico', {waitUntil:'domcontentloaded'});
  await page.locator('#cookieReject').click();
  await page.locator('.journal-cite-btn').click();
  await page.locator('#journal-citation-copy').click();
  await expect(page.locator('#journal-citation-status')).toContainText('copie a citação');
  await expect(page.locator('#journal-citation-text')).toBeFocused();
  await expect(page.locator('#journal-citation-text')).toHaveValue(/Artigo de teste/);
});
