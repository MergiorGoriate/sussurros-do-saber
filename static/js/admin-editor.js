(() => {
  const editor = document.querySelector('#bodyEditor');
  const preview = document.querySelector('#markdownPreview');
  if (!editor || !preview) return;

  const escape = (text) => text.replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const videoPreview = (title, rawUrl) => {
    try {
      const url = new URL(rawUrl.replace(/&amp;/g,'&'));
      const host = url.hostname.toLowerCase().replace(/^www\./,'');
      let embed = '';
      if (['youtube.com','m.youtube.com','youtube-nocookie.com'].includes(host)) {
        const id = url.pathname.includes('/embed/') ? url.pathname.split('/embed/')[1].split('/')[0] : url.searchParams.get('v');
        if (/^[A-Za-z0-9_-]{6,20}$/.test(id||'')) embed = `https://www.youtube-nocookie.com/embed/${id}`;
      } else if (host === 'youtu.be') {
        const id=url.pathname.slice(1).split('/')[0]; if (/^[A-Za-z0-9_-]{6,20}$/.test(id)) embed=`https://www.youtube-nocookie.com/embed/${id}`;
      } else if (['vimeo.com','player.vimeo.com'].includes(host)) {
        const match=url.pathname.match(/(?:video\/)?(\d{5,12})/); if(match)embed=`https://player.vimeo.com/video/${match[1]}`;
      }
      if(embed)return `<figure class="preview-video"><div><iframe src="${embed}" title="${title}" loading="lazy"></iframe></div><figcaption>${title}</figcaption></figure>`;
      if (/\.(mp4|webm|ogg)$/i.test(url.pathname)) return `<figure class="preview-video"><video src="${escape(rawUrl)}" controls preload="metadata"></video><figcaption>${title}</figcaption></figure>`;
    } catch {}
    return `<p><a href="${escape(rawUrl)}">Vídeo: ${title}</a></p>`;
  };
  const render = () => {
    const html = escape(editor.value)
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>')
      .replace(/\[video:\s*([^\]]*)\]\((https?:\/\/[^\s)]+)\)/gi, (_,title,url) => videoPreview(title,url))
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

  const videoPanel=document.querySelector('#inlineVideoPanel');
  const openVideo=document.querySelector('#openInlineVideo');
  const closeVideo=document.querySelector('#closeInlineVideo');
  const insertVideo=document.querySelector('#insertInlineVideo');
  const videoUrl=document.querySelector('#inlineVideoUrl');
  const videoTitle=document.querySelector('#inlineVideoTitleInput');
  const videoStatus=document.querySelector('#inlineVideoStatus');
  let videoInsertionPoint=0;
  const setVideoPanel=(open)=>{
    videoPanel.hidden=!open;
    openVideo.setAttribute('aria-expanded',String(open));
    if(open){videoInsertionPoint=editor.selectionStart;videoUrl.focus()}else{openVideo.focus()}
  };
  openVideo?.addEventListener('click',()=>setVideoPanel(videoPanel.hidden));
  closeVideo?.addEventListener('click',()=>setVideoPanel(false));
  insertVideo?.addEventListener('click',()=>{
    const url=videoUrl.value.trim(),title=cleanText(videoTitle.value);
    if(!/^https?:\/\//i.test(url)){videoStatus.textContent='Informe um endereço válido iniciado por https://.';videoUrl.focus();return}
    if(!title){videoStatus.textContent='Escreva um título ou uma legenda para o vídeo.';videoTitle.focus();return}
    try{
      const parsed=new URL(url),host=parsed.hostname.toLowerCase().replace(/^www\./,'');
      const direct=/\.(mp4|webm|ogg)$/i.test(parsed.pathname);
      const supported=['youtube.com','m.youtube.com','youtube-nocookie.com','youtu.be','vimeo.com','player.vimeo.com'].includes(host)||direct;
      if(!supported){videoStatus.textContent='Use uma ligação do YouTube, Vimeo, MP4, WebM ou OGG.';return}
      editor.setRangeText(`\n\n[video: ${title}](${url})\n\n`,videoInsertionPoint,videoInsertionPoint,'end');
      render();videoUrl.value='';videoTitle.value='';videoStatus.textContent='Vídeo inserido no artigo.';setVideoPanel(false);editor.focus();
    }catch{videoStatus.textContent='O endereço do vídeo não é válido.'}
  });

  editor.addEventListener('input', render);
  render();

  const titleField=document.querySelector('#titleField');
  const slugField=document.querySelector('#slugField');
  const slugPreview=document.querySelector('#slugPreview');
  const slugify=(value)=>value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,260);
  if(slugField?.value)slugField.value=slugify(slugField.value);
  let slugWasEdited=Boolean(slugField?.value);
  const updateSlugPreview=()=>{
    if(!slugWasEdited&&slugField)slugField.value=slugify(titleField?.value||'');
    if(slugPreview)slugPreview.textContent=`URL: ${location.origin}/artigo/${slugField?.value||'gerado-a-partir-do-titulo'}`;
  };
  slugField?.addEventListener('input',()=>{slugWasEdited=true;const cursor=slugField.selectionStart;slugField.value=slugify(slugField.value);slugField.setSelectionRange(cursor,cursor);updateSlugPreview()});
  titleField?.addEventListener('input',updateSlugPreview);
  editor.closest('form')?.addEventListener('submit',()=>{
    if(slugField)slugField.value=slugify(slugField.value||titleField?.value||'artigo');
  });
  updateSlugPreview();

  const url=document.querySelector('#imageUrl'),file=document.querySelector('#imageFile'),image=document.querySelector('#imagePreview');
  url?.addEventListener('input',()=>{image.src=url.value;image.hidden=!url.value});
  file?.addEventListener('change',()=>{if(file.files[0]){image.src=URL.createObjectURL(file.files[0]);image.hidden=false}});
})();
