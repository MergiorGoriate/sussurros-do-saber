const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
const fs=require('node:fs');
const video=fs.readFileSync('tests/fixtures/article-cover.webm');
const poster='<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="600"><rect width="1200" height="600" fill="#24558c"/><circle cx="600" cy="300" r="100" fill="#9acbff"/></svg>';
test.setTimeout(90000);
function fixture(){return JSON.parse(execFileSync('python',['tests/browser/cover_fixture.py'],{encoding:'utf8'}));}
async function assets(page){
 await page.route('https://res.cloudinary.com/**/video/upload/**',route=>route.fulfill({status:200,contentType:'video/webm',body:video}));
 await page.route('https://example.org/cover-poster.svg',route=>route.fulfill({status:200,contentType:'image/svg+xml',body:poster}));
 await page.context().addCookies([{name:'cookie_consent_v3',value:encodeURIComponent(JSON.stringify({essential:true,analytics:false,ads:false,updatedAt:new Date().toISOString()})),url:'http://127.0.0.1:5000'}]);
}
async function signin(context){const cookie=execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();await context.addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);}
async function open(page,slug){await page.goto('/artigo/'+slug,{waitUntil:'domcontentloaded'});await page.locator('.article-video-cover').scrollIntoViewIfNeeded();}
async function fits(page){expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));}

test('animated cover plays muted inline, loops and pauses with the keyboard',async({page})=>{
 const d=fixture();await assets(page);await page.emulateMedia({reducedMotion:'no-preference'});await open(page,d.video_animated.slug);
 const root=page.locator('[data-article-cover]'),player=root.locator('video');
 await expect(root).toHaveAttribute('data-state','playing');expect(await player.evaluate(v=>v.muted&&v.loop&&v.playsInline)).toBe(true);
 await expect.poll(()=>player.evaluate(v=>v.currentTime)).toBeGreaterThan(0);
 const toggle=page.getByRole('button',{name:'Pausar animação da capa',exact:true});await toggle.focus();await page.keyboard.press('Enter');
 await expect(root).toHaveAttribute('data-state','paused');expect(await player.evaluate(v=>v.paused)).toBe(true);await expect(root.locator('.cover-status')).toBeHidden();await expect(toggle).toHaveAttribute('aria-pressed','false');
 await page.getByRole('button',{name:'Reproduzir animação da capa',exact:true}).click();await expect(root).toHaveAttribute('data-state','playing');
});

test('reduced motion and data saving show poster without fetching video',async({page})=>{
 const d=fixture();await assets(page);await page.emulateMedia({reducedMotion:'reduce'});const requests=[];page.on('request',r=>{if(r.url().includes('/video/upload/'))requests.push(r.url());});
 await open(page,d.video_animated.slug);await expect(page.locator('.cover-poster')).toBeVisible();await expect(page.locator('.cover-status')).toContainText('desactivada');
 expect(requests).toEqual([]);expect(await page.locator('video').getAttribute('src')).toBeNull();
 await page.getByRole('button',{name:'Reproduzir animação da capa',exact:true}).click();await expect(page.locator('[data-article-cover]')).toHaveAttribute('data-state','playing');
 await page.emulateMedia({reducedMotion:'no-preference'});
 await page.addInitScript(()=>Object.defineProperty(navigator,'connection',{value:{saveData:true,effectiveType:'2g'},configurable:true}));
 requests.length=0;await open(page,d.video_animated.slug);await expect(page.locator('.cover-status')).toContainText('desactivada');expect(requests).toEqual([]);
});

test('blocked autoplay and failed delivery preserve a functional static cover',async({page,browser})=>{
 const d=fixture();await assets(page);await page.emulateMedia({reducedMotion:'no-preference'});
 await page.addInitScript(()=>{HTMLMediaElement.prototype.play=function(){return Promise.reject(new DOMException('Blocked for test','NotAllowedError'));};});
 await open(page,d.video_animated.slug);await expect(page.locator('[data-article-cover]')).toHaveAttribute('data-state','blocked');await expect(page.locator('.cover-poster')).toBeVisible();
 await expect(page.locator('.cover-status')).toContainText('não iniciou');
 const context=await browser.newContext({reducedMotion:'no-preference'}),failed=await context.newPage();await assets(failed);
 await failed.unroute('https://res.cloudinary.com/**/video/upload/**');await failed.route('https://res.cloudinary.com/**/video/upload/**',r=>r.abort());
 await open(failed,d.video_animated.slug);await expect(failed.locator('[data-article-cover]')).toHaveAttribute('data-state','error');await expect(failed.locator('.cover-poster')).toBeVisible();await context.close();
});

test('controlled cover waits for interaction and lists do not request videos',async({page})=>{
 const d=fixture();await assets(page);const requests=[];page.on('request',r=>{if(r.url().includes('/video/upload/'))requests.push(r.url());});
 await open(page,d.video_controls.slug);const player=page.locator('.cover-video');expect(await player.getAttribute('controls')).not.toBeNull();expect(await player.getAttribute('autoplay')).toBeNull();expect(await player.getAttribute('loop')).toBeNull();expect(requests).toEqual([]);
 await page.getByRole('button',{name:'Reproduzir vídeo da capa',exact:true}).click();await expect(page.locator('[data-article-cover]')).toHaveAttribute('data-state','playing');
 await expect.poll(()=>player.evaluate(v=>v.duration)).toBeGreaterThan(0);
 for(const path of ['/','/artigos']){requests.length=0;await page.goto(path,{waitUntil:'domcontentloaded'});await expect(page.locator('[data-article-cover]')).toHaveCount(0);expect(requests).toEqual([]);}
});

test('editor preview preserves the resource across modes and saves explicitly',async({page})=>{
 const d=fixture();await assets(page);await signin(page.context());await page.emulateMedia({reducedMotion:'reduce'});page.on('dialog',d=>d.accept());
 const path='/admin/artigos/'+d.draft.id+'/editar';await page.goto(path);await expect(page.locator('#coverMode')).toHaveValue('image');
 const previous=await page.locator('#coverVideoUrl').inputValue();await page.locator('#coverMode').selectOption('video_animated');
 await expect(page.locator('#coverPreview').getByRole('button',{name:'Reproduzir animação da capa',exact:true})).toBeVisible();
 await expect(page.locator('#coverPreview video')).toHaveCount(1);await expect(page.locator('#editorAutosaveStatus')).toContainText('Gravação automática pausada');
 await page.locator('#coverVideoFile').setInputFiles('tests/fixtures/article-cover.webm');await expect(page.locator('#coverPreview video')).toHaveAttribute('data-src',/^blob:/);
 await page.locator('#coverPreview .cover-toggle').click();await expect(page.locator('#coverPreview')).toHaveAttribute('data-state','playing');
 await page.locator('#coverVideoFile').setInputFiles([]);await page.getByRole('button',{name:'Guardar artigo',exact:true}).click();
 await page.goto(path);await expect(page.locator('#coverMode')).toHaveValue('video_animated');await expect(page.locator('#coverVideoUrl')).toHaveValue(previous);
 await page.locator('#coverMode').selectOption('image');await page.getByRole('button',{name:'Guardar artigo',exact:true}).click();
 await page.goto(path);await expect(page.locator('#coverVideoUrl')).toHaveValue(previous);
 await page.getByRole('button',{name:'Remover vídeo da capa',exact:true}).click();await page.getByRole('button',{name:'Guardar artigo',exact:true}).click();
 await page.goto(path);await expect(page.locator('#coverMode')).toHaveValue('image');await expect(page.locator('#coverVideoUrl')).toHaveValue('');
});

for(const width of [320,768,1440])test(`cover and editor remain usable at ${width}px in both themes`,async({page})=>{
 const d=fixture();await assets(page);await signin(page.context());await page.emulateMedia({reducedMotion:'reduce'});page.on('dialog',d=>d.accept());await page.goto('/healthz');
 for(const theme of ['light','dark']){
  await page.setViewportSize({width,height:1000});await page.evaluate(t=>{sessionStorage.setItem('theme',t);localStorage.setItem('sussurros.admin.theme',t);},theme);
  for(const mode of ['video_animated','video_controls']){await open(page,d[mode].slug);await fits(page);await expect(page.locator('.cover-poster')).toBeVisible();await expect(page.locator('.cover-toggle')).toBeVisible();}
  await page.goto('/admin/artigos/'+d.draft.id+'/editar',{waitUntil:'domcontentloaded'});await page.locator('#coverMode').selectOption('video_animated');await fits(page);await expect(page.locator('#coverPreview')).toBeVisible();
 }
});

test('external controlled covers keep a poster until opened and can return to it',async({page})=>{
 const d=fixture();await assets(page);const requests=[];
 await page.route('https://www.youtube-nocookie.com/**',r=>{requests.push(r.request().url());return r.fulfill({status:200,contentType:'text/html',body:'<!doctype html><title>Isolated provider frame</title><p>Provider frame fixture</p>'});});
 await open(page,d.external.slug);expect(requests).toEqual([]);await expect(page.locator('.cover-poster')).toBeVisible();
 await page.getByRole('button',{name:'Reproduzir vídeo da capa',exact:true}).click();await expect(page.locator('.cover-external-player iframe')).toHaveAttribute('src',/youtube-nocookie.com/);
 await page.getByRole('button',{name:'Mostrar imagem de reserva',exact:true}).click();await expect(page.locator('.cover-external-player iframe')).toHaveCount(0);await expect(page.locator('.cover-poster')).toBeVisible();
});

for(const width of [320,1440])test(`homepage lead animation and independent navigation at ${width}px`,async({page})=>{
 const d=JSON.parse(execFileSync('python',['tests/browser/cover_fixture.py'],{encoding:'utf8',env:{...process.env,COVER_HERO_ANIMATED:'1'}}));
 await assets(page);await page.setViewportSize({width,height:900});await page.emulateMedia({reducedMotion:'no-preference'});
 await page.goto('/',{waitUntil:'domcontentloaded'});const root=page.locator('.home-animated-cover');await root.scrollIntoViewIfNeeded();
 await expect(root).toHaveAttribute('data-state','playing');await expect(page.locator('video')).toHaveCount(1);
 expect(await root.locator('video').evaluate(v=>v.muted&&v.loop&&v.playsInline)).toBe(true);
 await root.getByRole('button',{name:'Pausar animação da capa',exact:true}).click();await expect(root).toHaveAttribute('data-state','paused');
 await fits(page);await page.emulateMedia({reducedMotion:'reduce'});await page.reload({waitUntil:'domcontentloaded'});
 await expect(root.locator('video')).not.toHaveAttribute('src');await expect(root.locator('.cover-poster')).toBeVisible();
 await root.locator('.home-cover-link').click({position:{x:30,y:30}});await expect(page).toHaveURL(new RegExp('/artigo/'+d.video_animated.slug+'$'));
});
