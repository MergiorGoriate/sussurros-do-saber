(() => {
  const form = document.querySelector('.editorial-policy-editor');
  if (!form) return;
  const field = form.querySelector('[name="author_guidelines"]');
  const button = document.getElementById('preview-guidelines');
  const preview = document.getElementById('guidelines-preview');
  const status = document.getElementById('guidelines-preview-status');
  field.addEventListener('input', () => {
    if (!preview.hidden) status.textContent = 'Texto alterado. Atualize a pré-visualização.';
  });
  button.addEventListener('click', async () => {
    button.disabled = true;
    status.textContent = 'A preparar a pré-visualização…';
    try {
      const data = new FormData();
      data.set('csrf_token', form.querySelector('[name="csrf_token"]').value);
      data.set('author_guidelines', field.value);
      const response = await fetch(form.dataset.previewUrl, {method: 'POST', body: data, credentials: 'same-origin'});
      if (!response.ok) throw new Error('Não foi possível pré-visualizar. Verifique o limite do texto e a sessão.');
      const result = await response.json();
      preview.innerHTML = result.html;
      preview.hidden = false;
      status.textContent = result.default ? 'Diretrizes predefinidas. O campo vazio mantém este conteúdo público.' : 'Pré-visualização atualizada. Guarde para publicar as alterações.';
    } catch (error) {
      status.textContent = error.message || 'Não foi possível pré-visualizar. Tente novamente.';
    } finally { button.disabled = false; }
  });
})();
