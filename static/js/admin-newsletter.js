/* Progressive enhancement: permissions, validation and sending remain server-side. */
(() => {
  'use strict';
  const page = document.querySelector('.subscribers-page');
  if (!page) return;
  const tools = page.querySelector('.newsletter-directory-tools');
  if (tools) {
    const search = page.querySelector('#subscriber-search');
    const state = page.querySelector('#subscriber-status-filter');
    const result = page.querySelector('#subscriber-filter-result');
    const rows = [...page.querySelectorAll('[data-subscriber-state]')];
    const filter = () => {
      const term = search.value.trim().toLocaleLowerCase();
      let visible = 0;
      rows.forEach(row => {
        const email = row.querySelector('.subscriber-identity').textContent.toLocaleLowerCase();
        row.hidden = !email.includes(term) || (state.value !== 'all' && row.dataset.subscriberState !== state.value);
        if (!row.hidden) visible++;
      });
      result.textContent = visible ? visible + ' de ' + rows.length + ' inscrições apresentadas.' : 'Nenhuma inscrição corresponde aos filtros.';
    };
    tools.hidden = false;
    result.hidden = false;
    search.addEventListener('input', filter);
    state.addEventListener('change', filter);
    page.querySelector('#subscriber-clear-filters').addEventListener('click', () => {
      search.value = '';
      state.value = 'all';
      filter();
      search.focus();
    });
    filter();
  }
  const plan = page.querySelector('.newsletter-plan-form');
  if (plan) {
    const checks = [...plan.querySelectorAll('[name="article_ids"]')];
    const status = document.createElement('p');
    status.className = 'newsletter-selection-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    plan.querySelector('.newsletter-picker').before(status);
    const snapshot = () => JSON.stringify([...new FormData(plan)].filter(([key]) => key !== 'csrf_token'));
    const initial = snapshot();
    let submitting = false;
    const update = () => {
      const manual = plan.querySelector('[name="selection_mode"]:checked').value === 'manual';
      const count = checks.filter(input => input.checked).length;
      status.textContent = (manual ? count + ' de 20 artigos seleccionados.' : 'Selecção automática activa; as escolhas manuais não serão utilizadas.') +
        (snapshot() !== initial ? ' Existem alterações por guardar.' : '');
      checks.forEach(input => {
        input.setCustomValidity(manual && count > 20 ? 'Seleccione no máximo 20 artigos.' : '');
      });
    };
    plan.addEventListener('change', update);
    plan.addEventListener('input', update);
    plan.addEventListener('submit', event => {
      const manual = plan.querySelector('[name="selection_mode"]:checked').value === 'manual';
      if (manual && !checks.some(input => input.checked)) {
        event.preventDefault();
        status.textContent = 'Seleccione pelo menos um artigo antes de guardar.';
        status.scrollIntoView({block: 'center'});
        checks[0]?.focus();
        return;
      }
      submitting = true;
    });
    window.addEventListener('beforeunload', event => {
      if (!submitting && snapshot() !== initial) {
        event.preventDefault();
        event.returnValue = '';
      }
    });
    update();
  }
  const prepare = page.querySelector('.newsletter-prepare-form');
  if (prepare) {
    const mode = prepare.querySelector('[name="delivery_mode"]');
    const date = prepare.querySelector('[name="scheduled_at"]');
    const confirmation = prepare.querySelector('[name="confirm"]');
    const button = prepare.querySelector('[type="submit"]');
    const update = () => {
      date.closest('label').hidden = mode.value !== 'schedule';
      date.required = mode.value === 'schedule';
      date.disabled = mode.value !== 'schedule';
      confirmation.checked = false;
      button.textContent = {review: 'Preparar para revisão', now: 'Aprovar e colocar na fila', schedule: 'Aprovar e programar envio'}[mode.value];
    };
    mode.addEventListener('change', update);
    update();
  }
})();
