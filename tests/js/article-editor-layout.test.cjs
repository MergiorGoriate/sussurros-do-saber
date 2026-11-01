const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../../static/js/article-editor-layout.js'),'utf8');
function setup(stored,blocked=false){
  const values={};
  const buttons=['write','split','preview'].map(mode=>({dataset:{editorView:mode},attributes:{},listeners:{},setAttribute(k,v){this.attributes[k]=v;},addEventListener(k,fn){this.listeners[k]=fn;}}));
  const controls={hidden:true,querySelectorAll:()=>buttons};
  const workspace={dataset:{}},text={hidden:false},preview={hidden:false};
  const fields={'.editor-view-switch':controls,'[data-editor-workspace]':workspace,'#articleEditorTextPanel':text,'#articleEditorPreviewPanel':preview};
  const form={querySelector:key=>fields[key]};
  vm.runInNewContext(source,{document:{querySelector:()=>form},localStorage:{getItem(){if(blocked)throw Error();return stored;},setItem(k,v){if(blocked)throw Error();values[k]=v;}}});
  return {buttons,workspace,text,preview,controls,values};
}
test('view controls switch only the visible panes and preserve the selected preference',()=>{
  const s=setup(null);assert.equal(s.controls.hidden,false);
  assert.equal(s.text.hidden,false);assert.equal(s.preview.hidden,false);
  s.buttons[0].listeners.click();assert.equal(s.preview.hidden,true);assert.equal(s.text.hidden,false);
  s.buttons[2].listeners.click();assert.equal(s.preview.hidden,false);assert.equal(s.text.hidden,true);
  assert.equal(s.buttons[2].attributes['aria-pressed'],'true');assert.equal(s.buttons[0].attributes['aria-pressed'],'false');
  assert.equal(s.values['sussurros.admin.articleEditor.view'],'preview');
});
test('restores a valid preference and falls back to both panes for invalid or blocked storage',()=>{
  assert.equal(setup('write').preview.hidden,true);
  for(const s of [setup('invalid'),setup(null,true)]){
    assert.equal(s.workspace.dataset.editorView,'split');assert.equal(s.text.hidden,false);assert.equal(s.preview.hidden,false);
    assert.doesNotThrow(()=>s.buttons[2].listeners.click());
  }
});
test('does nothing on other administrative pages',()=>{
  assert.doesNotThrow(()=>vm.runInNewContext(source,{document:{querySelector:()=>null}}));
});
