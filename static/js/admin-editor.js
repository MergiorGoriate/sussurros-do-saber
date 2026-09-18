(() => {
  const editor = document.querySelector('#bodyEditor');
  const preview = document.querySelector('#markdownPreview');
  if (!editor || !preview) return;

  const escape = (text) => text.replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const render = () => {
    const html = escape(editor.value)
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>')
      .replace(/!\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g, '<figure><img src="$2" alt="$1" loading="lazy"></figure>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2">$1</a>')
      .replace(/^- (.+)$/gm, '<li>$1</li>')
      .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
      .split(/\n{2,}/)
      .map((part) => /^<(h|ul|blockquote|figure)/.test(part) ? part : `<p>${part.replace(/\n/g, '<br>')}</p>`)
      .join('');
    preview.innerHTML = html || '<p class="preview-empty">A pré-visualização aparecerá aqui.</p>';
  };

  document.querySelectorAll('.editor-toolbar button[data-before]').forEach((button) => button.addEventListener('click', () => {
    const start=editor.selectionStart,end=editor.selectionEnd,before=button.dataset.before||'',after=button.dataset.after||'';
    editor.setRangeText(before+editor.value.slice(start,end)+after,start,end,'end');
    editor.focus();
    render();
  }));

  const panel=document.querySelector('#inlineImagePanel');
  const openButton=document.querySelector('#openInlineImage');
  const closeButton=document.querySelector('#closeInlineImage');
  const insertButton=document.querySelector('#insertInlineImage');
  const inlineFile=document.querySelector('#inlineImageFile');
  const inlineUrl=document.querySelector('#inlineImageUrl');
  const inlineAlt=document.querySelector('#inlineImageAlt');
  const inlineCaption=document.querySelector('#inlineImageCaption');
  const inlineStatus=document.querySelector('#inlineImageStatus');
  let insertionPoint=0;

  const setPanel=(open)=>{
    panel.hidden=!open;
    openButton.setAttribute('aria-expanded',String(open));
    if(open){insertionPoint=editor.selectionStart;inlineAlt.focus()}else{openButton.focus()}
  };
  openButton?.addEventListener('click',()=>setPanel(panel.hidden));
  closeButton?.addEventListener('click',()=>setPanel(false));

  const cleanText=(value)=>value.trim().replace(/[\r\n\[\]]+/g,' ');
  const uploadImage=async(file)=>{
    const data=new FormData();
    data.append('csrf_token',document.querySelector('input[name="csrf_token"]').value);
    data.append('image',file);
    const response=await fetch('/admin/api/imagens',{method:'POST',body:data,headers:{'Accept':'application/json'}});
    const result=await response.json().catch(()=>({error:'Resposta inválida do servidor.'}));
    if(!response.ok||!result.ok)throw new Error(result.error||'Não foi possível carregar a imagem.');
    return result.url;
  };

  insertButton?.addEventListener('click',async()=>{
    const alt=cleanText(inlineAlt.value);
    const caption=cleanText(inlineCaption.value);
    const file=inlineFile.files[0];
    let url=inlineUrl.value.trim();
    if(!alt){inlineStatus.textContent='Escreva uma descrição acessível da imagem.';inlineAlt.focus();return}
    if(!file&&!url){inlineStatus.textContent='Seleccione um ficheiro ou informe o endereço da imagem.';return}
    if(url&&!/^https?:\/\//i.test(url)){inlineStatus.textContent='O endereço deve começar por https:// ou http://.';inlineUrl.focus();return}
    insertButton.disabled=true;
    inlineStatus.textContent=file?'A carregar imagem...':'A inserir imagem...';
    try{
      if(file)url=await uploadImage(file);
      const markdown=`\n\n![${alt}](${url})${caption?`\n*${caption}*`:''}\n\n`;
      editor.setRangeText(markdown,insertionPoint,insertionPoint,'end');
      render();
      inlineFile.value='';inlineUrl.value='';inlineAlt.value='';inlineCaption.value='';
      inlineStatus.textContent='Imagem inserida no artigo.';
      setPanel(false);
      editor.focus();
    }catch(error){inlineStatus.textContent=error.message}
    finally{insertButton.disabled=false}
  });

  editor.addEventListener('input', render);
  render();

  const url=document.querySelector('#imageUrl'),file=document.querySelector('#imageFile'),image=document.querySelector('#imagePreview');
  url?.addEventListener('input',()=>{image.src=url.value;image.hidden=!url.value});
  file?.addEventListener('change',()=>{if(file.files[0]){image.src=URL.createObjectURL(file.files[0]);image.hidden=false}});
})();
