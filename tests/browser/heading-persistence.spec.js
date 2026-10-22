const {test, expect} = require('@playwright/test');
const {execFileSync} = require('node:child_process');

async function fixture(page) {
  await page.route('https://**', route => route.abort());
  const cookie = execFileSync('python', ['tests/browser/staff_fixture.py'], {encoding: 'utf8'}).trim();
  const data = JSON.parse(execFileSync('python', ['tests/browser/heading_persistence_fixture.py'], {encoding: 'utf8'}));
  await page.context().addCookies([{name: 'session', value: cookie, url: 'http://127.0.0.1:5000', httpOnly: true, sameSite: 'Lax'}]);
  return data;
}

for (const width of [320, 1440]) {
  test(`headings persist and match publication in both themes at ${width}px`, async ({page}) => {
    const data = await fixture(page);
    await page.setViewportSize({width, height: 1000});
    const path = `/admin/artigos/${data.article_id}/editar`;
    await page.goto(path);
    const preview = page.locator('#markdownPreview');
    expect(await page.locator('#headingLevel').evaluate(el => el.getBoundingClientRect().width)).toBeGreaterThanOrEqual(140);
    await expect(preview.locator('h6')).toHaveText('Nível 6');
    const previewHeadings = await preview.locator('h2,h3,h4,h5,h6').evaluateAll(els => els.map(el => [el.tagName, el.textContent, el.id]));
    await expect(preview.locator('h1')).toHaveCount(0);
    await expect(preview.locator('pre code')).toHaveText('# literal\n');
    await expect(preview).toContainText('# escapado');
    const editor = page.locator('#bodyEditor');
    await editor.evaluate(el => {el.focus(); el.setSelectionRange(0, 0);});
    await page.locator('#headingLevel').selectOption('5');
    await expect(editor).toHaveValue('#####' + data.body.slice(1));
    await expect(preview.locator('h5').first()).toHaveText('Nível 1');
    await page.getByRole('button', {name: 'Guardar artigo', exact: true}).click();
    await expect(page).toHaveURL(/\/admin\/artigos$/);
    await page.goto(path);
    await expect(editor).toHaveValue('#####' + data.body.slice(1));
    await expect(preview.locator('h6')).toHaveText('Nível 6');
    await page.getByRole('button', {name: 'Alternar tema do painel', exact: true}).click();
    await expect(page.locator('body')).toHaveClass(/admin-dark/);
    expect(await preview.locator('h6').evaluate(el => getComputedStyle(el).color)).toBe(await preview.evaluate(el => getComputedStyle(el).color));
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({path: `/tmp/heading-previews/editor-dark-${width}.png`, fullPage: true});
    await page.goto('/artigo/' + data.slug);
    await page.getByRole('button', {name: 'Recusar não essenciais', exact: true}).click();
    await expect(page.locator('h1')).toHaveCount(1);
    const content = page.locator('.article-markdown').first();
    expect(await content.locator('h2,h3,h4,h5,h6').evaluateAll(els => els.map(el => [el.tagName, el.textContent, el.id]))).toEqual(previewHeadings);
    const sizes = await content.locator('h2,h3,h4,h5,h6').evaluateAll(els => els.slice(1,6).map(el => parseFloat(getComputedStyle(el).fontSize)));
    expect(sizes.every((size, i) => !i || size < sizes[i - 1])).toBeTruthy();
    const id = await content.locator('h6').getAttribute('id');
    await page.goto('/artigo/' + data.slug + '#' + id);
    await expect(content.locator('h6')).toBeInViewport();
    await page.locator('#themeToggle').click();
    expect(await content.locator('h6').evaluate(el => getComputedStyle(el).color)).toBe(await content.evaluate(el => getComputedStyle(el).color));
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({path: `/tmp/heading-previews/public-dark-${width}.png`, fullPage: true});
  });
}

test('failed preview stays literal and a stale response cannot replace newer text', async ({page}) => {
  const data = await fixture(page);
  await page.goto(`/admin/artigos/${data.article_id}/editar`);
  const editor = page.locator('#bodyEditor');
  const preview = page.locator('#markdownPreview');
  await expect(preview.locator('h6')).toHaveCount(1);
  await page.route('**/admin/artigos/previsualizar', route => route.fulfill({status: 403, body: 'Forbidden'}));
  const source = '## Nova secção\n\n<img src=x onerror="window.headingAttack=1">';
  await editor.fill(source);
  await expect(page.locator('#footnotePreviewStatus')).toContainText('Não foi possível');
  await expect(preview).toHaveText(source);
  await expect(preview.locator('img')).toHaveCount(0);
  expect(await page.evaluate(() => window.headingAttack)).toBeUndefined();
  await page.unroute('**/admin/artigos/previsualizar');
  await page.route('**/admin/artigos/previsualizar', async route => {
    if (route.request().postData().includes('Antigo')) {
      await new Promise(resolve => setTimeout(resolve, 1200));
      await route.fulfill({json: {html: '<h2>Antigo</h2>'}}).catch(() => {});
    } else await route.continue();
  });
  const oldRequest = page.waitForRequest(req => req.url().endsWith('/previsualizar') && req.postData().includes('Antigo'));
  await editor.fill('## Antigo');
  await oldRequest;
  await editor.fill('###### Actual');
  await expect(preview.locator('h6')).toHaveText('Actual');
  await expect(preview).not.toContainText('Antigo');
});

test('existing journal index includes H2 to H6 with working unique targets', async ({page}) => {
  const data = await fixture(page);
  await page.goto('/revistas/' + data.journal_slug);
  const links = page.locator('#journal-content-index a');
  for (const level of [2, 3, 4, 5, 6]) await expect(page.locator(`#journal-content-index a[data-heading-level="${level}"]`).first()).toBeVisible();
  const targets = await links.evaluateAll(els => els.map(el => el.hash.slice(1)));
  expect(new Set(targets).size).toBe(targets.length);
  for (const target of targets) await expect(page.locator(`[id="${target}"]`)).toHaveCount(1);
});
