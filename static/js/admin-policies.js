(() => {
  const form = document.querySelector('.editorial-policy-editor');
  if (!form) return;
  const field = form.querySelector('[name="author_guidelines"]');
  const button = document.getElementById('preview-guidelines');
  const preview = document.getElementById('guidelines-preview');
  const status = document.getElementById('guidelines-preview-status');
  const snapshot=()=>JSON.stringify([...new FormData(form)].filter(([key])=>key!=='csrf_token'));
  const initial=snapshot();
  let submitting=false;
  form.addEventListener('submit',()=>{submitting=true;});
  window.addEventListener('beforeunload',event=>{
    if(!submitting&&snapshot()!==initial){event.preventDefault();event.returnValue='';}
  });
  field.addEventListener('input', () => {
    if (!preview.hidden) status.textContent = 'Texto alterado. Atualize a pré-visualização.';
  });
  button.addEventListener('click', async () => {
    const content=field.value;
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),15000);
    button.disabled = true;
    status.textContent = 'A preparar a pré-visualização…';
    try {
      const data = new FormData();
      data.set('csrf_token', form.querySelector('[name="csrf_token"]').value);
      data.set('author_guidelines', content);
      const response = await fetch(form.dataset.previewUrl, {method: 'POST', body: data, credentials: 'same-origin', signal:controller.signal});
      if (!response.ok) throw new Error('Não foi possível pré-visualizar. Verifique o limite do texto e a sessão.');
      const result = await response.json();
      if(typeof result.html!=='string')throw new Error('Resposta de pré-visualização inválida.');
      if(field.value!==content){status.textContent='Texto alterado. Actualize a pré-visualização.';return;}
      preview.innerHTML = result.html;
      preview.hidden = false;
      status.textContent = result.default ? 'Diretrizes predefinidas. O campo vazio mantém este conteúdo público.' : 'Pré-visualização atualizada. Guarde para publicar as alterações.';
    } catch (error) {
      status.textContent = error.message || 'Não foi possível pré-visualizar. Tente novamente.';
    } finally { clearTimeout(timeout);button.disabled = false; }
  });
})();
