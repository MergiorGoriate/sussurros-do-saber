const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../../static/js/admin-policies.js'),'utf8');
function setup(){
  const element=()=>({value:'',events:{},textContent:'',hidden:true,addEventListener(name,fn){this.events[name]=fn;}});
  const field=element(),button=element(),preview=element(),status=element();
  const form=element();form.dataset={previewUrl:'/preview'};form.querySelector=key=>key==='[name="author_guidelines"]'?field:{value:'csrf'};
  const win={events:{},addEventListener(name,fn){this.events[name]=fn;}};
  let resolve;
  const pending=new Promise(r=>{resolve=r;});
  class Data {constructor(f){this.rows=f?[['author_guidelines',field.value]]:[];}[Symbol.iterator](){return this.rows[Symbol.iterator]();}set(){}}
  vm.runInNewContext(source,{document:{querySelector:()=>form,getElementById:id=>({'preview-guidelines':button,'guidelines-preview':preview,'guidelines-preview-status':status})[id]},window:win,FormData:Data,AbortController,setTimeout,clearTimeout,fetch:()=>pending});
  return {field,button,preview,status,form,win,resolve};
}
test('warns only when policies have unsaved changes and allows normal saving',()=>{
  const {field,form,win}=setup();let warned=false;
  const event=()=>({preventDefault(){warned=true;}});
  win.events.beforeunload(event());assert.equal(warned,false);
  field.value='Política alterada';win.events.beforeunload(event());assert.equal(warned,true);
  warned=false;form.events.submit();win.events.beforeunload(event());assert.equal(warned,false);
});
test('an old preview response cannot be presented as the current policy',async()=>{
  const {field,button,preview,status,resolve}=setup();field.value='Primeira versão';
  const request=button.events.click();field.value='Texto revisto';
  resolve({ok:true,json:async()=>({html:'<p>Primeira versão</p>'})});await request;
  assert.equal(preview.innerHTML,undefined);assert.match(status.textContent,/Texto alterado/);assert.equal(button.disabled,false);
});
