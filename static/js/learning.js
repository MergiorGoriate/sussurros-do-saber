window.sdsText = window.sdsText || (text => text);
(() => {
  const $ = selector => document.querySelector(selector);
  const cards = [...document.querySelectorAll('.learning-card')];
  const controls = ['#resourceSearch', '#typeFilter', '#topicFilter', '#levelFilter', '#savedFilter'];
  const normalise = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();

  function readCollection() {
    try {
      const items = JSON.parse(localStorage.getItem('learningCollection') || '[]');
      return Array.isArray(items) ? [...new Set(items.filter(id => typeof id === 'string'))] : [];
    } catch {
      return [];
    }
  }

  function filter() {
    const query = normalise($('#resourceSearch')?.value || '');
    const type = $('#typeFilter')?.value || '';
    const topic = $('#topicFilter')?.value || '';
    const level = $('#levelFilter')?.value || '';
    const savedOnly = $('#savedFilter')?.checked || false;
    const saved = readCollection();
    let count = 0;
    cards.forEach(card => {
      const show = (!query || normalise(card.dataset.search).includes(query))
        && (!type || card.dataset.type === type)
        && (!topic || card.dataset.topic === topic)
        && (!level || card.dataset.level === level)
        && (!savedOnly || saved.includes(card.dataset.resourceId));
      card.hidden = !show;
      if (show) count++;
    });
    if ($('#resourceCount')) $('#resourceCount').textContent = count;
    $('#resourceEmpty')?.classList.toggle('hidden', count > 0);
  }

  function updateSavedButtons() {
    const saved = readCollection();
    document.querySelectorAll('.save-resource').forEach(button => {
      const active = saved.includes(button.dataset.resource);
      button.setAttribute('aria-pressed', String(active));
      button.textContent = window.sdsText(active ? 'Guardado ✓' : 'Adicionar à colecção');
      button.title = window.sdsText(active ? 'Remover da colecção' : 'Adicionar à colecção');
    });
  }

  controls.forEach(selector => $(selector)?.addEventListener('input', filter));
  $('#clearLearningFilters')?.addEventListener('click', () => {
    controls.forEach(selector => {
      const control = $(selector);
      if (!control) return;
      if (control.type === 'checkbox') control.checked = false;
      else control.value = '';
    });
    filter();
    $('#resourceSearch')?.focus();
  });
  document.querySelectorAll('.save-resource').forEach(button => {
    button.addEventListener('click', () => {
      const saved = readCollection();
      const id = button.dataset.resource;
      const next = saved.includes(id) ? saved.filter(value => value !== id) : [...saved, id];
      try {
        localStorage.setItem('learningCollection', JSON.stringify(next));
        updateSavedButtons();
        filter();
      } catch {
        button.textContent = window.sdsText('Não foi possível guardar neste navegador.');
      }
    });
  });
  window.addEventListener('storage', event => {
    if (event.key === 'learningCollection' || event.key === null) {
      updateSavedButtons();
      filter();
    }
  });
  document.querySelectorAll('.open-learning-resource').forEach(button => {
    button.addEventListener('click', () => {
      document.getElementById('learning-lesson-' + button.dataset.lesson)?.showModal();
    });
  });
  document.querySelectorAll('[data-close-lesson]').forEach(button => {
    button.addEventListener('click', () => button.closest('dialog').close());
  });
  document.querySelectorAll('.learning-question').forEach(form => {
    form.addEventListener('submit', event => {
      event.preventDefault();
      const answer = new FormData(form).get('answer');
      if (answer === null) return;
      const correct = answer === form.dataset.correct;
      form.querySelector('.learning-feedback').textContent = window.sdsText(
        correct ? 'Resposta correcta.' : 'Reveja a explicação e tente novamente.');
      form.querySelector('.learning-explanation').hidden = false;
    });
    form.addEventListener('reset', () => {
      form.querySelector('.learning-feedback').textContent = '';
      form.querySelector('.learning-explanation').hidden = true;
    });
  });
  updateSavedButtons();
  filter();
  const range=$('#concentration');function updateLab(){if(!range)return;const v=Number(range.value),cell=$('#cell');$('#concentrationValue').textContent=v;cell.style.transform=`scale(${v>50?Math.max(.72,1-(v-50)/170):Math.min(1.3,1+(50-v)/170)})`;if(v>60){$('#labState').textContent=window.sdsText("Meio hipertónico");$('#labExplanation').textContent=window.sdsText("A concentração externa é maior. A água tende a sair da célula, reduzindo o seu volume.")}else if(v<40){$('#labState').textContent=window.sdsText("Meio hipotónico");$('#labExplanation').textContent=window.sdsText("A concentração externa é menor. A água tende a entrar na célula, aumentando o seu volume.")}else{$('#labState').textContent=window.sdsText("Equilíbrio isotónico");$('#labExplanation').textContent=window.sdsText("As concentrações estão próximas do equilíbrio e não há movimento líquido predominante de água.")}}range?.addEventListener('input',updateLab);$('#resetLab')?.addEventListener('click',()=>{range.value=50;updateLab()});updateLab()
})();
