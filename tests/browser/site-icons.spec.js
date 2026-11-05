const {test,expect}=require('@playwright/test');
for(const width of [1440,390]){
 test(`site icon files decode and manifest resolves at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:900});
  await page.goto('/');
  const links=await page.locator('head link[rel="icon"], head link[rel="apple-touch-icon"], head link[rel="manifest"]').evaluateAll(nodes=>nodes.map(node=>({rel:node.rel,href:node.href,sizes:node.getAttribute('sizes')})));
  expect(links).toHaveLength(5);
  expect(links.filter(link=>link.rel!=='manifest').map(link=>link.sizes).sort())
   .toEqual(['16x16','180x180','192x192','32x32']);
  for(const link of links.filter(link=>link.rel!=='manifest')){
   const dimensions=await page.evaluate(async href=>{
    const image=new Image();image.src=href;await image.decode();
    return `${image.naturalWidth}x${image.naturalHeight}`;
   },link.href);
   expect(dimensions).toBe(link.sizes);
  }
  const href=links.find(link=>link.rel==='manifest').href;
  const response=await page.request.get(href);expect(response.status()).toBe(200);
  const manifest=await response.json();expect(manifest.name).toBe('Sussurros do Saber');
  for(const icon of manifest.icons){
   const response=await page.request.get(new URL(icon.src,href).href);
   expect(response.status()).toBe(200);expect(response.headers()['content-type']).toContain('image/png');
  }
 });
}
