(() => {
  const editor = document.querySelector('#bodyEditor');
  if (!editor) return;
  const form = editor.closest('form');
  const panel = document.querySelector('#footnotePanel');
  const open = document.querySelector('#openFootnote');
  const text = document.querySelector('#footnoteText');
  const status = document.querySelector('#footnoteStatus');
  const preview = document.querySelector('#markdownPreview');
  const previewStatus = document.querySelector('#footnotePreviewStatus');
  let source = '', position = 0, sequence = 0, timer, controller;
  function close() {
    panel.hidden = true;
    open.setAttribute('aria-expanded', 'false');
    open.focus();
  }
  open.addEventListener('click', () => {
    source = editor.value;
    position = editor.selectionEnd;
    status.textContent = '';
    panel.hidden = false;
    open.setAttribute('aria-expanded', 'true');
    text.focus();
  });
  document.querySelector('#closeFootnote').addEventListener('click', close);
  panel.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); close(); }
  });
  document.querySelector('#insertFootnote').addEventListener('click', () => {
    const note = text.value.trim();
    if (!note || note.length > 10000) {
      status.textContent = 'Escreva uma nota com até 10 000 caracteres.';
      return;
    }
    if (editor.value !== source) {
      status.textContent = 'O texto mudou. Feche e volte a abrir a nota na posição desejada.';
      return;
    }
    let number = 1;
    const used = new Set(Array.from(source.matchAll(/\[\^([^\]\n]+)\]/g), match => match[1]));
    while (used.has(`nota-${number}`)) number++;
    const label = `nota-${number}`;
    const reference = `[^${label}]`;
    const lines = note.replace(/\r\n?/g, '\n').split('\n');
    const definition = `[^${label}]: ${lines[0]}` + lines.slice(1).map(line => `\n    ${line}`).join('');
    const value = source.slice(0, position) + reference + source.slice(position) + '\n\n' + definition + '\n';
    if (value.length > 400000) {
      status.textContent = 'A nota excede o limite de tamanho do artigo.';
      return;
    }
    editor.setRangeText(value, 0, source.length, 'end');
    editor.setSelectionRange(position + reference.length, position + reference.length);
    close();
    text.value = '';
    editor.focus();
    editor.dispatchEvent(new Event('input', {bubbles: true}));
  });
  function updatePreview() {
    const current = ++sequence;
    clearTimeout(timer);
    controller?.abort();
    preview.removeAttribute('aria-busy');
    previewStatus.textContent = '';
    const content = editor.value;
    // Do not display stale content while a new version is being rendered.
    preview.replaceChildren();
    previewStatus.textContent = 'A actualizar a pré-visualização…';
    preview.setAttribute('aria-busy', 'true');
    timer = setTimeout(async () => {
      const requestController = new AbortController();
      controller = requestController;
      const timeout = setTimeout(() => requestController.abort(), 10000);
      try {
        const response = await fetch(form.dataset.notesPreviewUrl, {
          method: 'POST', credentials: 'same-origin', cache: 'no-store',
          signal: requestController.signal,
          body: new URLSearchParams({content, csrf_token: form.elements.csrf_token.value})
        });
        if (!response.ok) throw new Error('preview');
        const result = await response.json();
        if (typeof result.html !== 'string') throw new Error('preview');
        if (current !== sequence || editor.value !== content) return;
        preview.innerHTML = result.html;
        previewStatus.textContent = '';
      } catch (_) {
        if (current === sequence) previewStatus.textContent = 'Não foi possível actualizar a pré-visualização. O texto mantém-se no editor.';
      } finally {
        clearTimeout(timeout);
        if (current === sequence) preview.removeAttribute('aria-busy');
      }
    }, 500);
  }
  editor.addEventListener('editor:rendered', updatePreview);
  updatePreview();
})();
