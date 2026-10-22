const {test, expect} = require('@playwright/test');
const {execFileSync} = require('node:child_process');

async function setup(page) {
  const cookie = execFileSync('python', ['tests/browser/staff_fixture.py'], {encoding:'utf8'}).trim();
  const data = JSON.parse(execFileSync('python', ['tests/browser/heading_parity_fixture.py'], {encoding:'utf8'}));
  await page.context().addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);
  await page.goto(`/admin/artigos/${data.article_id}/editar`);
  await expect(page.locator('#markdownPreview h6')).toHaveText('Último nível');
  return data;
}

const headings = root => root.locator('h2,h3,h4,h5,h6').evaluateAll(nodes => nodes.map(node => ({
  tag:node.tagName, text:node.textContent, id:node.id,
  size:getComputedStyle(node).fontSize, weight:getComputedStyle(node).fontWeight,
  family:getComputedStyle(node).fontFamily, lineHeight:getComputedStyle(node).lineHeight
})));

for (const width of [320, 390, 768, 1440]) {
  test(`heading semantics and visual hierarchy agree at ${width}px`, async ({page}, testInfo) => {
    await page.setViewportSize({width, height:1000});
    const data = await setup(page);
    const preview = page.locator('#markdownPreview');
    await expect(preview.locator('h1')).toHaveCount(0);
    await expect(preview.locator('pre code')).toHaveText('# Código literal\n## Não é uma secção\n');
    const expected = await headings(preview);
    expect(expected.map(h => h.tag)).toEqual(['H2','H2','H3','H4','H5','H6']);
    for (let i=2; i<expected.length; i++) expect(parseFloat(expected[i-1].size)).toBeGreaterThan(parseFloat(expected[i].size));
    await page.getByRole('button',{name:'Alternar tema do painel',exact:true}).click();
    await expect(page.locator('body')).toHaveClass(/admin-dark/);
    const select = page.locator('#headingLevel');
    expect(await select.evaluate(el => getComputedStyle(el).backgroundColor)).not.toBe('rgb(255, 255, 255)');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({path:testInfo.outputPath('headings-editor-dark.png'),fullPage:true});
    await page.goto('/artigo/' + data.slug);
    const reject = page.getByRole('button',{name:'Recusar não essenciais',exact:true});
    if (await reject.isVisible()) await reject.click();
    const body = page.locator('.article-markdown').first();
    await expect(page.locator('h1')).toHaveCount(1);
    await expect(page.locator('h1')).toHaveText(data.title);
    expect(await headings(body)).toEqual(expected);
    const target = expected[2].id;
    await page.goto('/artigo/' + data.slug + '#' + target);
    await expect(page.locator('#' + target)).toBeInViewport();
    await page.locator('#themeToggle').click();
    expect(await headings(body)).toEqual(expected);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({path:testInfo.outputPath('headings-public-dark.png'),fullPage:true});
  });
}

test('toolbar applies H2 through H6 to whole lines and saves exact Markdown', async ({page}) => {
  const data = await setup(page);
  const editor = page.locator('#bodyEditor');
  await editor.fill('Parágrafo preservado.\n\nDetalhe');
  for (const level of [2,3,4,5,6]) {
    await editor.evaluate(el => el.setSelectionRange(el.value.length-2, el.value.length-2));
    await page.getByRole('combobox',{name:'Inserir nível de subtítulo'}).selectOption(String(level));
    await expect(editor).toHaveValue('Parágrafo preservado.\n\n' + '#'.repeat(level) + ' Detalhe');
    await expect(page.locator('#markdownPreview h' + level).filter({hasText:/^Detalhe$/})).toHaveCount(1);
  }
  const saved = await editor.inputValue();
  await page.getByRole('button',{name:'Guardar artigo',exact:true}).click();
  await expect(page).toHaveURL(/\/admin\/artigos$/);
  await page.goto(`/admin/artigos/${data.article_id}/editar`);
  await expect(editor).toHaveValue(saved);
  await expect(page.locator('#markdownPreview h6')).toHaveText('Detalhe');
});

test('preview reports connection failure and recovers without changing source', async ({page}) => {
  await setup(page);
  await page.route('**/admin/artigos/previsualizar', route => route.abort());
  const source = '###### Texto preservado';
  await page.locator('#bodyEditor').fill(source);
  await expect(page.locator('#footnotePreviewStatus')).toContainText('Não foi possível actualizar');
  await expect(page.locator('#bodyEditor')).toHaveValue(source);
  await page.unroute('**/admin/artigos/previsualizar');
  await page.locator('#bodyEditor').fill(source + '.');
  await expect(page.locator('#markdownPreview h6')).toHaveText('Texto preservado.');
  await expect(page.locator('#footnotePreviewStatus')).toBeEmpty();
});

test('a late preview response cannot replace the current document', async ({page}) => {
  await setup(page);
  let releaseOld, oldStarted;
  const gate = new Promise(resolve => { releaseOld = resolve; });
  const started = new Promise(resolve => { oldStarted = resolve; });
  await page.route('**/admin/artigos/previsualizar', async route => {
    const old = route.request().postData().includes('Antigo');
    const response = await route.fetch();
    if (old) { oldStarted(); await gate; }
    await route.fulfill({response});
  });
  await page.locator('#bodyEditor').fill('## Antigo');
  await started;
  await page.locator('#bodyEditor').fill('###### Actual');
  await expect(page.locator('#markdownPreview h6')).toHaveText('Actual');
  releaseOld();
  await expect(page.locator('#markdownPreview h2')).toHaveCount(0);
  await expect(page.locator('#bodyEditor')).toHaveValue('###### Actual');
});

test('the existing external video cover preview remains available', async ({page}) => {
  await setup(page);
  await page.route('https://www.youtube-nocookie.com/**', route => route.fulfill({contentType:'text/html',body:'<p>Vídeo de teste</p>'}));
  await page.locator('#coverMode').selectOption('video_controls');
  await page.locator('#coverVideoUrl').fill('https://youtu.be/dQw4w9WgXcQ');
  await expect(page.locator('#coverPreview template.cover-external-template')).toHaveCount(1);
  await page.locator('#coverPreview .cover-toggle').click();
  await expect(page.locator('#coverPreview .cover-external-player iframe')).toHaveAttribute('src','https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ');
});
