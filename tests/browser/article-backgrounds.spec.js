const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
test.setTimeout(90000);
function fixture(){return JSON.parse(execFileSync('python',['tests/browser/background_fixture.py'],{encoding:'utf8'}));}
async function signin(context){const cookie=execFileSync('python',['tests/browser/staff_fixture.py'],{encoding:'utf8'}).trim();await context.addCookies([{name:'session',value:cookie,url:'http://127.0.0.1:5000',httpOnly:true,sameSite:'Lax'}]);}
const fits=async page=>expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>innerWidth));

test('background preview remains unsaved until explicit save and survives reopening',async({page})=>{
 const d=fixture();await signin(page.context());await page.goto(`/admin/artigos/${d.draft_id}/editar`);
 const standard=page.getByRole('radio',{name:'Fundo padrão',exact:true}),paper=page.getByRole('radio',{name:'Papel antigo',exact:true});
 await expect(standard).toBeChecked();const writes=[];page.on('request',r=>{if(r.method()==='POST'&&!r.url().endsWith('/previsualizar'))writes.push(r.url());});
 await standard.focus();await page.keyboard.press('ArrowDown');await expect(paper).toBeChecked();
 await expect(page.locator('#articleSurfacePreview')).toHaveClass(/article-paper/);
 await expect(page.locator('#backgroundPreviewTitle')).toHaveText(await page.locator('#titleField').inputValue());
 await expect(page.locator('#articleBackgroundStatus')).toContainText('ainda não foi guardada');
 await expect(page.locator('#editorAutosaveStatus')).toContainText('Gravação automática pausada');
 expect(writes).toEqual([]);expect((await page.request.get('/artigo/'+d.draft_slug)).status()).toBe(404);
 await page.getByRole('button',{name:'Guardar artigo',exact:true}).click();
 await page.goto(`/admin/artigos/${d.draft_id}/editar`);await expect(paper).toBeChecked();
 await standard.check();await expect(page.locator('#articleSurfacePreview')).not.toHaveClass(/article-paper/);
 page.once('dialog',dialog=>dialog.accept());await page.reload();await expect(paper).toBeChecked();
});

test('editor background controls and preview fit mobile, tablet and desktop in both themes',async({page})=>{
 const d=fixture();await signin(page.context());page.on('dialog',dialog=>dialog.accept());
 for(const width of [320,768,1440])for(const theme of ['light','dark']){
  await page.setViewportSize({width,height:1000});await page.addInitScript(t=>localStorage.setItem('sussurros.admin.theme',t),theme);
  await page.goto(`/admin/artigos/${d.draft_id}/editar`,{waitUntil:'domcontentloaded'});
  for(const name of ['Papel antigo','Fundo padrão']){
   await page.getByRole('radio',{name,exact:true}).check();await fits(page);
   await expect(page.locator('#markdownPreview')).toBeVisible();
  }
 }
});

test('public paper preserves global surfaces and readable content in both themes',async({page})=>{
 const d=fixture();
 for(const width of [320,768,1440])for(const theme of ['light','dark']){
  await page.setViewportSize({width,height:1000});await page.addInitScript(t=>sessionStorage.setItem('theme',t),theme);
  await page.goto('/artigo/'+d.default_slug,{waitUntil:'domcontentloaded'});await expect(page.locator('.article-title')).toBeVisible();
  const outside=()=>page.evaluate(()=>['body','header','nav','footer','.share-panel','.article-comments'].map(s=>{const el=document.querySelector(s);const c=getComputedStyle(el);return [s,c.backgroundColor,c.color];}));
  const before=await outside();await expect(page.locator('.article-paper')).toHaveCount(0);
  await page.goto('/artigo/'+d.paper_slug,{waitUntil:'domcontentloaded'});await expect(page.locator('.article-paper')).toBeVisible();await fits(page);
  expect(await outside()).toEqual(before);
  const contrast=await page.locator('.article-paper').evaluate(root=>{
   const rgb=s=>s.match(/[\d.]+/g).slice(0,3).map(Number);
   const luminance=s=>rgb(s).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
   const ratio=(a,b)=>{const [x,y]=[luminance(a),luminance(b)].sort((a,b)=>b-a);return (x+.05)/(y+.05);};
   const base=getComputedStyle(root).backgroundColor;
   return ['.article-title','.article-summary','.article-meta','.article-markdown p','.article-markdown a','blockquote','figcaption','th','td','pre','code','.article-references a','.footnote-ref'].map(s=>{
    const el=root.querySelector(s);if(!el)return {selector:s,ratio:0};let parent=el,bg='rgba(0, 0, 0, 0)';
    while(parent&&parent!==root&&bg==='rgba(0, 0, 0, 0)'){bg=getComputedStyle(parent).backgroundColor;parent=parent.parentElement;}
    return {selector:s,ratio:ratio(getComputedStyle(el).color,bg==='rgba(0, 0, 0, 0)'?base:bg)};
   });
  });
  for(const item of contrast)expect(item.ratio,item.selector+' '+theme).toBeGreaterThanOrEqual(4.5);
 }
});
