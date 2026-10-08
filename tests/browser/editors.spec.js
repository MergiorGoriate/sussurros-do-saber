const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
test.use({ launchOptions: { ignoreDefaultArgs: ['--hide-scrollbars'] } });

for (const width of [320, 390, 768, 1440]) {
  test(`editing forms stay within the viewport at ${width}px`, async ({ page }, testInfo) => {
    const cookie = execFileSync('python', ['tests/browser/staff_fixture.py'], { encoding: 'utf8' }).trim();
    await page.context().addCookies([{ name: 'session', value: cookie, url: 'http://127.0.0.1:5000', httpOnly: true, sameSite: 'Lax' }]);
    const records = JSON.parse(execFileSync('python', ['tests/browser/editor_fixture.py'], { encoding: 'utf8' }));
    await page.setViewportSize({ width, height: 900 });
    const paths = [
      '/admin/artigos/novo', `/admin/artigos/${records.article_id}/editar`,
      '/admin/revistas/nova', `/admin/revistas/${records.journal_id}/editar`,
      '/admin/politicas-editoriais'
    ];
    for (const path of paths) {
      expect((await page.goto(path, { waitUntil: 'networkidle' })).status(), path).toBe(200);
      for (const collapsed of [false, true]) {
        const toggle = page.locator('.admin-sidebar-toggle');
        if ((await page.locator('body').evaluate(el => el.classList.contains('admin-sidebar-collapsed'))) !== collapsed) await toggle.click();
        const dimensions = await page.evaluate(() => {
          const viewport = document.documentElement.clientWidth;
          const selectors = ['.admin-main', '.editor-form', '.editor-main', '.editor-side', '.editor-toolbar', '.markdown-editor-grid', '.journal-author-card'];
          return { viewport, document: document.documentElement.scrollWidth,
            sidebar: document.querySelector('.admin-sidebar').getBoundingClientRect().width,
            outside: selectors.flatMap(selector => [...document.querySelectorAll(selector)].filter(el => el.getBoundingClientRect().right > viewport + 1).map(el => el.className)) };
        });
        expect(dimensions.document, JSON.stringify({ path, collapsed, ...dimensions })).toBeLessThanOrEqual(dimensions.viewport);
        expect(dimensions.outside, path).toEqual([]);
        if (width <= 850) expect(dimensions.sidebar).toBeCloseTo(dimensions.viewport, 0);
        const field = page.locator('input[name="title"]');
        if (await field.count()) {
          await field.fill('Título alterado no teste responsivo');
          await expect(field).toHaveValue('Título alterado no teste responsivo');
        }
      }
      if (path.includes('/artigos/')) {
        await page.locator('#openInlineImage').click();
        await expect(page.locator('#inlineImagePanel')).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();
        await page.locator('#closeInlineImage').click();
        const toolbar = page.locator('.editor-toolbar');
        await toolbar.evaluate(el => el.scrollLeft = el.scrollWidth);
        const last = toolbar.locator('button').last();
        await last.click();
        await expect(page.locator('#chartPanel')).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();
      }
      if (width === 390 && path.endsWith('/editar')) {
        await page.screenshot({ path: testInfo.outputPath(path.includes('/artigos/') ? 'edit-article-mobile.png' : 'edit-journal-mobile.png'), fullPage: true });
      }
    }
  });
}
