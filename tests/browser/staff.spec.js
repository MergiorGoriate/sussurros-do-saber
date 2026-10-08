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
      ['/admin', 'Visão geral'], ['/admin/equipa', 'Equipa e convites'], ['/admin/funcoes', 'Funções e permissões'],
      ['/admin/trabalho', 'Área de trabalho'], ['/admin/documentos-equipa', 'Documentos privados da equipa'],
      ['/admin/historico-remocoes', 'Histórico de remoções'], ['/admin/notificacoes', 'Notificações internas'], ['/admin/relatorios-equipa', 'Relatórios e auditoria']
    ]) {
      const response = await page.goto(path, { waitUntil: 'domcontentloaded' });
      expect(response.status(), path).toBe(200);
      expect(response.headers()['cache-control']).toContain('no-store');
      await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
      if (['/admin','/admin/equipa','/admin/funcoes','/admin/historico-remocoes','/admin/notificacoes'].includes(path)) {
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

for (const width of [1440,390]) {
 test(`sidebar toggles icons, keyboard and persistence at ${width}px`,async({page})=>{
  await adminLogin(page);await page.setViewportSize({width,height:900});
  await page.goto('/admin/trabalho');
  const sidebar=page.locator('#admin-sidebar');
  const toggle=page.getByRole('button',{name:'Recolher barra lateral',exact:true});
  const before=await page.locator('main').boundingBox();
  await toggle.focus();await toggle.press('Enter');
  await expect(page.getByRole('button',{name:'Expandir barra lateral',exact:true})).toHaveAttribute('aria-expanded','false');
  await expect(sidebar.getByRole('link',{name:'Equipa e convites',exact:true})).toHaveCount(1);
  expect(await sidebar.locator('nav a').evaluateAll(items=>items.every(a=>!!a.querySelector('svg')&&!!a.title))).toBeTruthy();
  expect(await sidebar.locator('.admin-menu-label').first().evaluate(e=>e.getBoundingClientRect().width)).toBe(1);
  if(width===1440) {
   expect((await sidebar.boundingBox()).width).toBe(80);
   // A scrollbar must reserve space without clipping any icon, including offscreen items.
   expect(await sidebar.locator('nav').evaluate(nav => {
    const left=nav.getBoundingClientRect().left;
    return [...nav.querySelectorAll('svg')].every(icon => {
     const box=icon.getBoundingClientRect();
     return box.left>=left && box.right<=left+nav.clientWidth+1;
    });
   })).toBeTruthy();
   await sidebar.locator('nav a').last().scrollIntoViewIfNeeded();
   await expect(sidebar.locator('nav a').last()).toBeInViewport();
   await sidebar.locator('nav a').first().scrollIntoViewIfNeeded();
   expect((await page.locator('main').boundingBox()).x).toBeLessThan(before.x);
  }
  await page.screenshot({path:`test-results/sidebar-collapsed-${width}.png`,fullPage:true});
  await page.reload();await expect(page.getByRole('button',{name:'Expandir barra lateral',exact:true})).toBeVisible();
  await sidebar.getByRole('link',{name:'Equipa e convites',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Equipa e convites',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Expandir barra lateral',exact:true}).click();
  await expect(page.getByRole('button',{name:'Recolher barra lateral',exact:true})).toHaveAttribute('aria-expanded','true');
  await page.reload();await expect(page.getByRole('button',{name:'Recolher barra lateral',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  await page.screenshot({path:`test-results/sidebar-expanded-${width}.png`,fullPage:true});
 });
}
