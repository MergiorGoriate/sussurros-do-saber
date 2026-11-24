(() => {
  'use strict';
  const state = document.getElementById('news-publication-state');
  const fieldset = document.getElementById('news-schedule-options');
  const button = document.getElementById('news-apply-publication');
  const date = document.getElementById('news-scheduled-at');
  if (!state || !fieldset || !button || !date) return;
  function sync() {
    const scheduled = state.value === 'scheduled';
    fieldset.hidden = !scheduled;
    date.required = scheduled;
    button.disabled = state.value === 'draft' && !state.querySelector('option[value="scheduled"][selected]');
    if (state.value === 'scheduled') {
      button.value = 'schedule';
      button.textContent = 'Programar publicação';
    } else if (state.value === 'published') {
      button.value = 'publish';
      button.textContent = 'Publicar agora';
    } else {
      button.value = 'cancel_schedule';
      button.textContent = 'Cancelar programação';
    }
  }
  state.addEventListener('change',sync);
  sync();
})();
