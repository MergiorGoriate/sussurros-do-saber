const {test, expect} = require('@playwright/test');

const googleStub = `
window.google={accounts:{id:{
 initialize(config){window.gisConfig=config;},
 renderButton(container){const b=document.createElement('button');b.textContent='Entrar via Google';b.onclick=()=>window.gisConfig.callback({credential:'signed-token-fixture'});container.append(b);},
 prompt(){window.gisPromptCount=(window.gisPromptCount||0)+1;},
 cancel(){window.gisCancelled=true;}
}}};`;

async function configuredPage(page, path='/revistas/revista-de-teste-cientifico') {
  let signedIn=false, saved=false, following=false, actions=[];
  await page.route('https://pagead2.googlesyndication.com/**', route=>route.fulfill({contentType:'application/javascript',body:''}));
  await page.route('https://accounts.google.com/gsi/client', route=>route.fulfill({contentType:'application/javascript',body:googleStub}));
  await page.route('**/conta/sessao', route=>route.fulfill({json:{ok:true,authenticated:signedIn,verified:true,name:'Leitor Google',csrf:signedIn?'rotated-csrf':'initial-csrf',saved_articles:[]}}));
  await page.route('**/conta/google/preparar', route=>route.fulfill({json:{ok:true,nonce:'browser-bound-nonce'}}));
  await page.route('**/conta/google/entrar', route=>{
    expect(route.request().postData()).toContain('signed-token-fixture');
    signedIn=true;return route.fulfill({json:{ok:true,verified:true,csrf:'rotated-csrf'}});
  });
  await page.route('**/conta/revistas/*', route=>{
    if(route.request().method()==='POST') {
      const body=route.request().postData();
      expect(body).toContain('rotated-csrf');
      expect(body).toContain('true');
      if(body.includes('following'))following=true;else saved=true;
      actions.push(body);
    }
    return route.fulfill({json:{ok:true,saved,following}});
  });
  await page.route('**'+path,async route=>{
    const response=await route.fetch();
    await route.fulfill({response,body:(await response.text()).replace('data-client-id=""','data-client-id="browser-test.apps.googleusercontent.com"')});
  });
  await page.goto(path,{waitUntil:'domcontentloaded'});
  return actions;
}

test('Google manual button preserves favorite intent and rotates CSRF at 360px',async({page})=>{
  await page.setViewportSize({width:360,height:800});
  const actions=await configuredPage(page);
  await page.locator('.journal-save-btn').click();
  await expect(page.locator('#reader-dialog')).toBeVisible();
  await page.locator('#reader-google-button button').click();
  await expect(page.locator('#reader-dialog')).not.toBeVisible();
  await expect(page.locator('.journal-save-btn')).toHaveAttribute('aria-pressed','true');
  expect(actions.length).toBe(1);
  await expect(page.locator('.reader-header-login')).toHaveText('Conta');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});

test('Google login resumes notification intent',async({page})=>{
  const actions=await configuredPage(page);
  await page.locator('.journal-alert-btn').click();
  await page.locator('#reader-google-button button').click();
  await expect(page.locator('.journal-alert-btn')).toHaveAttribute('aria-pressed','true');
  expect(actions.length).toBe(1);
  await expect(page.locator('#journal-action-status')).toContainText('Notificações activadas');
});

test('One Tap is optional, attempted once and manual entry remains available',async({page})=>{
  await configuredPage(page);
  await expect.poll(()=>page.evaluate(()=>window.gisPromptCount||0)).toBe(1);
  await expect(page.locator('#reader-dialog')).not.toBeVisible();
  await expect(page.locator('main')).toContainText('Artigo de teste');
  await page.reload({waitUntil:'domcontentloaded'});
  await page.locator('.reader-header-login').click();
  await expect(page.locator('#reader-google-button button')).toBeVisible();
  expect(await page.evaluate(()=>window.gisPromptCount||0)).toBe(0);
  await page.locator('[data-reader-close]').click();
  await expect(page.locator('#reader-dialog')).not.toBeVisible();
  await expect(page.locator('main')).toBeVisible();
});

test('Google unavailable does not block reading or existing login',async({page})=>{
  await configuredPage(page);
  await page.route('https://accounts.google.com/gsi/client',route=>route.abort());
  await page.locator('.reader-header-login').click();
  await expect(page.locator('#reader-google-status')).toContainText('Google indisponível');
  await expect(page.locator('#reader-auth-form')).toBeVisible();
  await page.locator('[data-reader-close]').click();
  await expect(page.locator('main')).toBeVisible();
});
