/* Presentation preferences only: content, validation and saving stay unchanged. */
(() => {
  const form=document.querySelector('.article-edit-form');
  if(!form)return;
  const controls=form.querySelector('.editor-view-switch');
  const workspace=form.querySelector('[data-editor-workspace]');
  const text=form.querySelector('#articleEditorTextPanel');
  const preview=form.querySelector('#articleEditorPreviewPanel');
  if(!controls||!workspace||!text||!preview)return;
  const buttons=[...controls.querySelectorAll('[data-editor-view]')];
  const key='sussurros.admin.articleEditor.view';
  const modes=new Set(['write','split','preview']);
  const apply=mode=>{
    const selected=modes.has(mode)?mode:'split';
    workspace.dataset.editorView=selected;
    text.hidden=selected==='preview';preview.hidden=selected==='write';
    for(const button of buttons)button.setAttribute('aria-pressed',String(button.dataset.editorView===selected));
    return selected;
  };
  let stored='split';
  try{stored=localStorage.getItem(key)||'split';}catch(_){}
  apply(stored);controls.hidden=false;
  for(const button of buttons)button.addEventListener('click',()=>{
    const selected=apply(button.dataset.editorView);
    try{localStorage.setItem(key,selected);}catch(_){}
  });
})();
