const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../../static/js/admin-editor.js'),'utf8');
// Exercise the actual box controller without unrelated upload and cover widgets.
const controller=source.slice(source.indexOf('  const explainerPanel='),source.indexOf("  const panel=document.querySelector('#inlineImagePanel');"));
function setup(value='Antes texto Depois'){
  const nodes={};
  for(const id of ['explainerPanel','openExplainer','explainerTitle','explainerBody','explainerStatus','closeExplainer','insertExplainer','explainerLayout']){
    nodes['#'+id]={value:'',hidden:true,textContent:'',events:{},focus(){},setAttribute(){},addEventListener(name,fn){this.events[name]=fn;}};
  }
  const editor={value,selectionStart:6,selectionEnd:11,events:[],focus(){},
    setRangeText(text,start,end){this.value=this.value.slice(0,start)+text+this.value.slice(end);},
    dispatchEvent(event){this.events.push(event.type);}};
  vm.runInNewContext(controller,{document:{querySelector:key=>nodes[key]},editor,Event:class{constructor(type){this.type=type;}}});
  nodes['#openExplainer'].events.click();
  return {editor,nodes,insert:()=>nodes['#insertExplainer'].events.click()};
}
test('inserts a real multiline box and preserves surrounding text',()=>{
  const {editor,nodes,insert}=setup();
  nodes['#explainerTitle'].value='RNA: estrutura e função';
  nodes['#explainerBody'].value='Primeiro parágrafo.\n\nSegundo parágrafo.';
  nodes['#explainerLayout'].value='full';insert();
  assert.equal(editor.value,'Antes \n\n[caixa: RNA: estrutura e função|full]\nPrimeiro parágrafo.\n\nSegundo parágrafo.\n[/caixa]\n\n Depois');
  assert.deepEqual(editor.events,['input']);
  assert.equal(nodes['#explainerPanel'].hidden,true);
});
test('refuses a stale selection instead of replacing subsequently edited text',()=>{
  const {editor,nodes,insert}=setup();editor.value='Texto alterado entretanto';
  nodes['#explainerBody'].value='Uma explicação';insert();
  assert.equal(editor.value,'Texto alterado entretanto');
  assert.match(nodes['#explainerStatus'].textContent,/texto mudou/);
});
test('rejects box delimiters and empty explanations without changing the article',()=>{
  for(const body of ['', 'Texto\n[/caixa]\nOutro texto']){
    const {editor,nodes,insert}=setup();nodes['#explainerBody'].value=body;insert();
    assert.equal(editor.value,'Antes texto Depois');assert.ok(nodes['#explainerStatus'].textContent);
  }
});

test('refuses a box that would exceed the article limit',()=>{
  const {editor,nodes,insert}=setup('x'.repeat(400000));
  nodes['#explainerBody'].value='Uma explicação demasiado longa para o espaço disponível';
  insert();assert.equal(editor.value.length,400000);assert.match(nodes['#explainerStatus'].textContent,/limite/);
});
