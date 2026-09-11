(() => {
  const editor = document.querySelector('#bodyEditor');
  const preview = document.querySelector('#markdownPreview');
  if (!editor || !preview) return;
  const escape = (text) => text.replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const render = () => {
    const html = escape(editor.value).replace(/^### (.+)$/gm, '<h3>$1</h3>').replace(/^## (.+)$/gm, '<h2>$1</h2>').replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>').replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2">$1</a>').replace(/^- (.+)$/gm, '<li>$1</li>').replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>').split(/\n{2,}/).map((part) => /^<(h|ul|blockquote)/.test(part) ? part : `<p>${part.replace(/\n/g, '<br>')}</p>`).join('');
    preview.innerHTML = html || '<p class="preview-empty">A pré-visualização aparecerá aqui.</p>';
  };
  document.querySelectorAll('.editor-toolbar button').forEach((button) => button.addEventListener('click', () => { const start=editor.selectionStart,end=editor.selectionEnd,before=button.dataset.before||'',after=button.dataset.after||''; editor.setRangeText(before+editor.value.slice(start,end)+after,start,end,'end'); editor.focus(); render(); }));
  editor.addEventListener('input', render); render();
  const url=document.querySelector('#imageUrl'),file=document.querySelector('#imageFile'),image=document.querySelector('#imagePreview');
  url?.addEventListener('input',()=>{image.src=url.value;image.hidden=!url.value}); file?.addEventListener('change',()=>{if(file.files[0]){image.src=URL.createObjectURL(file.files[0]);image.hidden=false}});
})();
