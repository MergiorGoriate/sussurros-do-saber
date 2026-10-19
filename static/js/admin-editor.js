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
  const tablePreview = (block) => {
    const rows=block.trim().split('\n').map(line=>line.trim().replace(/^\||\|$/g,'').split('|').map(cell=>cell.trim()));
    if(rows.length<2||!rows[1].every(cell=>/^:?-{3,}:?$/.test(cell)))return block;
    const header='<thead><tr>'+rows[0].map(cell=>`<th>${cell}</th>`).join('')+'</tr></thead>';
    const body='<tbody>'+rows.slice(2).map(row=>'<tr>'+rows[0].map((_,index)=>`<td>${row[index]||''}</td>`).join('')+'</tr>').join('')+'</tbody>';
    return `<div class="preview-table-wrapper"><table>${header}${body}</table></div>`;
  };
  const chartPreview = (type,title,data) => {
    const points=data.split(';').slice(0,12).map(item=>{const index=item.lastIndexOf('=');return index>0?{label:item.slice(0,index).trim(),value:Number(item.slice(index+1).trim().replace(',','.'))}:null}).filter(point=>point&&point.label&&Number.isFinite(point.value)&&point.value>=0);
    const maximum=Math.max(...points.map(point=>point.value),0);
    if(!points.length||maximum<=0)return '<p class="preview-error">Dados do gráfico inválidos.</p>';
    const colours=['#087f72','#e85d4a','#2f6db0','#d69e2e','#805ad5','#319795','#c05621','#4a5568','#38a169','#b83280','#718096','#dd6b20'];
    let shapes='';
    if(type==='bar'){
      const step=680/points.length,width=Math.min(58,step*.65);
      points.forEach((point,index)=>{const height=260*point.value/maximum,x=80+index*step+(step-width)/2,y=315-height;shapes+=`<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="5" fill="${colours[index%colours.length]}"/><text x="${x+width/2}" y="${y-7}" text-anchor="middle">${point.value}</text><text x="${x+width/2}" y="342" text-anchor="middle">${point.label}</text>`;});
    }else if(type==='line'){
      const coords=points.map((point,index)=>({x:80+(680/Math.max(1,points.length-1))*index,y:315-260*point.value/maximum,...point}));
      shapes=`<polyline points="${coords.map(point=>`${point.x},${point.y}`).join(' ')}" fill="none" stroke="#087f72" stroke-width="4"/>`+coords.map((point,index)=>`<circle cx="${point.x}" cy="${point.y}" r="6" fill="${colours[index%colours.length]}"/><text x="${point.x}" y="${point.y-12}" text-anchor="middle">${point.value}</text><text x="${point.x}" y="342" text-anchor="middle">${point.label}</text>`).join('');
    }else{
      const total=points.reduce((sum,point)=>sum+point.value,0);let offset=0;
      shapes=points.map((point,index)=>{const part=point.value/total*100,current=offset;offset+=part;return `<circle cx="270" cy="210" r="125" fill="none" stroke="${colours[index%colours.length]}" stroke-width="250" pathLength="100" stroke-dasharray="${part} ${100-part}" stroke-dashoffset="${-current}" transform="rotate(-90 270 210)"/><rect x="500" y="${75+index*27}" width="16" height="16" rx="3" fill="${colours[index%colours.length]}"/><text x="525" y="${89+index*27}">${point.label}: ${point.value}</text>`;}).join('');
    }
    return `<figure class="preview-chart"><svg viewBox="0 0 800 390" role="img" aria-label="${title}"><line x1="80" y1="315" x2="760" y2="315" stroke="#94a3b8"/>${shapes}</svg><figcaption>${title}</figcaption></figure>`;
  };
  let estimatedReadingMinutes = 1;
  const updateEditorStatistics = () => {
    const words = editor.value.replace(/^\[capitular\]\s*/gm, '').match(/[\p{L}\p{N}]+(?:[’'-][\p{L}\p{N}]+)*/gu) || [];
    estimatedReadingMinutes = Math.max(1, Math.min(120, Math.ceil(words.length / 200)));
    const count = document.querySelector('#editorWordCount');
    const reading = document.querySelector('#editorReadingTime');
    if (count) count.textContent = `${words.length} palavras`;
    if (reading) reading.textContent = `${estimatedReadingMinutes} min de leitura estimada`;
  };
  const render = () => {
    updateEditorStatistics();
    const html = escape(editor.value)
      .replace(/^\[destaque:\s*([^\]\n]+)\]\s*$/gm, (_,details) => {
        const [text,author='']=details.split('|');
        return '<figure class="article-pullquote"><blockquote><p>'+text+'</p></blockquote><figcaption>'+author+'</figcaption></figure>';
      })
      .replace(/\[portrait:\s*([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/gi, (_,details,url) => {
        const [alt,caption='',credit='']=details.split('|');
        return '<figure class="article-portrait"><img src="'+url+'" alt="'+alt+'" loading="lazy"><figcaption>'+caption+'<small>'+credit+'</small></figcaption></figure>';
      })
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>')
      .replace(/\[video:\s*([^\]]*)\]\((https?:\/\/[^\s)]+)\)/gi, (_,title,url) => videoPreview(title,url))
      .replace(/^\[chart:\s*(bar|line|pie)\|([^\]\n]+)\|([^\]\n]+)\]\s*$/gim, (_,type,title,data) => chartPreview(type.toLowerCase(),title,data))
      .replace(/((?:^\|.*\|\s*$\n?){2,})/gm, (_,block) => tablePreview(block))
      .replace(/!\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g, '<figure><img src="$2" alt="$1" loading="lazy"></figure>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2">$1</a>')
      .replace(/^- (.+)$/gm, '<li>$1</li>')
      .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
      .split(/\n{2,}/)
      .map((part) => {
        if (/^\[capitular\]/.test(part)) return `<p class="article-dropcap">${part.replace(/^\[capitular\]\s*/, '').replace(/\n/g, '<br>')}</p>`;
        return /^<(h|ul|blockquote|figure)/.test(part) ? part : `<p>${part.replace(/\n/g, '<br>')}</p>`;
      })
      .join('');
    preview.innerHTML = html || '<p class="preview-empty">A pré-visualização aparecerá aqui.</p>';
    editor.dispatchEvent(new Event('editor:rendered'));
  };

  const dropcapButton = document.querySelector('#toggleDropcap');
  const dropcapStatus = document.querySelector('#dropcapStatus');
  const currentParagraph = () => {
    const value = editor.value, cursor = editor.selectionStart;
    const breaks = /\n[ \t]*\n/g;
    let start = 0, match;
    while ((match = breaks.exec(value)) && match.index + match[0].length <= cursor) start = match.index + match[0].length;
    const rest = value.slice(start), end = rest.search(/\n[ \t]*\n/);
    return {start, text: end < 0 ? rest : rest.slice(0,end)};
  };
  const updateDropcapState = () => {
    if (dropcapButton) dropcapButton.setAttribute('aria-pressed', String(/^\[capitular\]/.test(currentParagraph().text)));
  };
  dropcapButton?.addEventListener('click', () => {
    const {start,text} = currentParagraph();
    if (/^\s*(?:#{1,6}\s|>|[-*+]\s|\d+[.)]\s|\x60{3}|~{3}|\||!\[|\[(?:destaque|chart|video|portrait):)/.test(text)) {
      dropcapStatus.textContent = 'Coloque o cursor num parágrafo de texto para aplicar a capitular.';
      return;
    }
    const marker = text.match(/^\[capitular\][ \t]*/)?.[0];
    const cursor = editor.selectionStart;
    editor.setRangeText(marker ? '' : '[capitular] ', start, marker ? start+marker.length : start, 'preserve');
    const next = Math.max(start,cursor+(marker ? -marker.length : '[capitular] '.length));
    editor.setSelectionRange(next,next);
    dropcapStatus.textContent = marker ? 'Capitular removida deste parágrafo.' : 'Capitular aplicada a este parágrafo.';
    editor.focus(); render(); updateDropcapState();
  });
  for (const event of ['click','keyup','select','input','editor:rendered']) editor.addEventListener(event,updateDropcapState);
  updateDropcapState();

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
      const layout=document.querySelector('#inlineImageLayout').value;
      const credit=cleanText(document.querySelector('#inlineImageCredit').value);
      const safeUrl=url.replace(/\(/g,'%28').replace(/\)/g,'%29');
      const parts=[alt,caption,credit].map(text=>text.replace(/\|/g,' '));
      const markdown=layout==='portrait'
        ? '\n\n[portrait: '+parts.join('|')+']('+safeUrl+')\n\n'
        : '\n\n!['+alt+']('+safeUrl+')'+(caption?'\n*'+caption+'*':'')+(credit?'\n*Crédito: '+credit+'*':'')+'\n\n';
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
  insertVideo?.addEventListener('click',async()=>{
    let url=videoUrl.value.trim();
    const title=cleanText(videoTitle.value),file=document.querySelector('#inlineVideoFile').files[0];
    if(file && (file.size > 50*1024*1024 || !/\.(mp4|webm|ogg)$/i.test(file.name))){videoStatus.textContent='Use MP4, WebM ou OGG com no máximo 50 MB.';return}
    if(file){
      if(!title){videoStatus.textContent='Escreva um título ou uma legenda para o vídeo.';return}
      insertVideo.disabled=true;videoStatus.textContent='A carregar vídeo...';
      try{
        const data=new FormData();
        data.append('csrf_token',document.querySelector('input[name="csrf_token"]').value);
        data.append('video',file);
        const response=await fetch('/admin/api/videos',{method:'POST',body:data,headers:{'Accept':'application/json'}});
        const result=await response.json().catch(()=>({error:'Não foi possível carregar o vídeo. Verifique o tamanho e tente novamente.'}));
        if(!response.ok||!result.ok)throw new Error(result.error||'Não foi possível carregar o vídeo.');
        url=result.url;videoUrl.value=url;document.querySelector('#inlineVideoFile').value='';
      }catch(error){videoStatus.textContent=error.message;return}
      finally{insertVideo.disabled=false}
    }
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

  const tablePanel=document.querySelector('#tablePanel'),openTable=document.querySelector('#openTable'),closeTable=document.querySelector('#closeTable'),insertTable=document.querySelector('#insertTable'),tableColumns=document.querySelector('#tableColumns'),tableRows=document.querySelector('#tableRows'),tableStatus=document.querySelector('#tableStatus');
  let tableInsertionPoint=0;
  const setTablePanel=(open)=>{tablePanel.hidden=!open;openTable.setAttribute('aria-expanded',String(open));if(open){tableInsertionPoint=editor.selectionStart;tableColumns.focus()}else{openTable.focus()}};
  openTable?.addEventListener('click',()=>setTablePanel(tablePanel.hidden));
  closeTable?.addEventListener('click',()=>setTablePanel(false));
  insertTable?.addEventListener('click',()=>{
    const columns=Math.max(2,Math.min(8,Number(tableColumns.value)||3)),rows=Math.max(1,Math.min(20,Number(tableRows.value)||3));
    const header='| '+Array.from({length:columns},(_,index)=>`Coluna ${index+1}`).join(' | ')+' |';
    const separator='| '+Array(columns).fill('---').join(' | ')+' |';
    const body=Array.from({length:rows},()=>('| '+Array(columns).fill('Conteúdo').join(' | ')+' |')).join('\n');
    editor.setRangeText(`\n\n${header}\n${separator}\n${body}\n\n`,tableInsertionPoint,tableInsertionPoint,'end');
    render();tableStatus.textContent='Tabela inserida. Edite os títulos e conteúdos no texto.';setTablePanel(false);editor.focus();
  });

  const chartPanel=document.querySelector('#chartPanel'),openChart=document.querySelector('#openChart'),closeChart=document.querySelector('#closeChart'),insertChart=document.querySelector('#insertChart'),chartType=document.querySelector('#chartType'),chartTitle=document.querySelector('#chartTitle'),chartLabels=document.querySelector('#chartLabels'),chartValues=document.querySelector('#chartValues'),chartStatus=document.querySelector('#chartStatus');
  let chartInsertionPoint=0;
  const setChartPanel=(open)=>{chartPanel.hidden=!open;openChart.setAttribute('aria-expanded',String(open));if(open){chartInsertionPoint=editor.selectionStart;chartTitle.focus()}else{openChart.focus()}};
  openChart?.addEventListener('click',()=>setChartPanel(chartPanel.hidden));
  closeChart?.addEventListener('click',()=>setChartPanel(false));
  insertChart?.addEventListener('click',()=>{
    const title=cleanText(chartTitle.value),labels=chartLabels.value.split(',').map(cleanText).filter(Boolean),values=chartValues.value.split(',').map(value=>Number(value.trim().replace(',','.')));
    if(!title){chartStatus.textContent='Escreva o título do gráfico.';chartTitle.focus();return}
    if(labels.length<1||labels.length>12||labels.length!==values.length){chartStatus.textContent='Informe entre 1 e 12 categorias e a mesma quantidade de valores.';return}
    if(values.some(value=>!Number.isFinite(value)||value<0)||Math.max(...values)<=0){chartStatus.textContent='Use valores numéricos não negativos e pelo menos um valor maior que zero.';return}
    const data=labels.map((label,index)=>`${label.replace(/[;=|\[\]]/g,' ')}=${values[index]}`).join('; ');
    editor.setRangeText(`\n\n[chart: ${chartType.value}|${title.replace(/[|\[\]]/g,' ')}|${data}]\n\n`,chartInsertionPoint,chartInsertionPoint,'end');
    render();chartTitle.value='';chartLabels.value='';chartValues.value='';chartStatus.textContent='Gráfico inserido no artigo.';setChartPanel(false);editor.focus();
  });

  document.querySelector('#insertPullQuote')?.addEventListener('click',()=>{
    const start=editor.selectionStart,end=editor.selectionEnd;
    const text=window.prompt('Texto da citação em destaque:',editor.value.slice(start,end));
    if(text===null)return;
    if(!text.trim()){window.alert('Escreva o texto da citação.');return;}
    const author=window.prompt('Autor e instituição (opcional):','');
    if(author===null)return;
    const clean=value=>value.trim().replace(/[\r\n\[\]|]+/g,' ');
    editor.setRangeText('\n\n[destaque: '+clean(text)+'|'+clean(author)+']\n\n',start,end,'end');
    editor.focus();editor.dispatchEvent(new Event('input',{bubbles:true}));
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
  const editorForm = editor.closest('form');
  const formState = () => JSON.stringify(Array.from(new FormData(editorForm)).filter(([key, value]) => typeof value === 'string' && !['csrf_token','version_token'].includes(key)));
  let initialState = formState();
  let submitting = false;
  const hasChanges = () => formState() !== initialState || Array.from(editorForm.querySelectorAll('input[type="file"]')).some(input => input.files.length);
  const updateSaveState = () => {
    const state = document.querySelector('#editorSaveState');
    if (state) state.textContent = hasChanges() ? 'Alterações por guardar' : '';
  };
  editorForm.addEventListener('editor:autosaved', event => {
    initialState = event.detail.fingerprint;
    updateSaveState();
  });
  editor.addEventListener('editor:rendered', updateSaveState);
  editorForm.addEventListener('input', updateSaveState);
  editorForm.addEventListener('change', updateSaveState);
  editorForm.addEventListener('submit', () => { submitting = true; });
  window.addEventListener('beforeunload', event => {
    if (!submitting && hasChanges()) { event.preventDefault(); event.returnValue = ''; }
  });
  document.querySelector('#useEstimatedReadingTime')?.addEventListener('click', () => {
    const input = editorForm.querySelector('input[name="read_minutes"]');
    if (input) { input.value = estimatedReadingMinutes; input.dispatchEvent(new Event('input', {bubbles:true})); }
  });

  const url=document.querySelector('#imageUrl'),file=document.querySelector('#imageFile'),image=document.querySelector('#imagePreview');
  url?.addEventListener('input',()=>{image.src=url.value;image.hidden=!url.value});
  file?.addEventListener('change',()=>{if(file.files[0]){image.src=URL.createObjectURL(file.files[0]);image.hidden=false}});
})();

