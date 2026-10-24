/* Progressive enhancement for the Premium form; server validation remains authoritative. */
document.querySelectorAll('[data-premium-editor]').forEach(form => {
  const type = form.querySelector('[data-premium-resource-type]');
  const update = () => {
    const event = form.querySelector('[data-premium-event-fields]');
    const collection = form.querySelector('[data-premium-collection-fields]');
    if (event) event.hidden = type.value !== 'event';
    if (collection) collection.hidden = type.value !== 'collection';
  };
  type.addEventListener('change', update);
  update();
});

document.querySelectorAll('[data-premium-collection-search]').forEach(input => {
  const form = input.closest('form');
  const results = form.querySelector('[data-premium-collection-results]');
  const picker = form.querySelector('.premium-collection-picker');
  let timer, controller;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    if (controller) controller.abort();
    results.replaceChildren();
    const query = input.value.trim();
    if (query.length < 2) return;
    timer = setTimeout(async () => {
      controller = new AbortController();
      try {
        const url = new URL(input.dataset.searchUrl, location.origin);
        url.searchParams.set('q', query);
        const response = await fetch(url, {credentials:'same-origin', signal:controller.signal});
        if (!response.ok) throw new Error();
        const data = await response.json();
        results.replaceChildren();
        for (const item of data.items) {
          if ([...picker.querySelectorAll('[name=collection_member]')].some(node => node.value === String(item.id))) continue;
          const button = document.createElement('button');
          button.type = 'button'; button.textContent = 'Adicionar: ' + item.title;
          button.addEventListener('click', () => {
            if (picker.querySelectorAll('[name=collection_member]:checked').length >= 50) {
              results.textContent = 'Seleccione no máximo 50 recursos.'; return;
            }
            const row = document.createElement('div'); row.className = 'premium-collection-choice';
            const label = document.createElement('label'); label.className = 'premium-admin-check';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox'; checkbox.name = 'collection_member'; checkbox.value = item.id; checkbox.checked = true;
            label.append(checkbox, document.createTextNode(item.title));
            const orderLabel = document.createElement('label'); orderLabel.textContent = 'Ordem';
            const order = document.createElement('input');
            order.type = 'number'; order.name = 'collection_order_' + item.id; order.min = '1'; order.max = '1000';
            order.value = Math.min(1000, Math.max(0, ...[...picker.querySelectorAll('input[type=number]')].map(node => Number(node.value) || 0)) + 1);
            orderLabel.append(order); row.append(label, orderLabel); picker.append(row); button.remove();
          });
          results.append(button);
        }
        if (!results.children.length) results.textContent = 'Sem novos recursos para esta pesquisa.';
      } catch (error) {
        if (error.name !== 'AbortError') results.textContent = 'Não foi possível pesquisar. Tente novamente.';
      }
    }, 250);
  });
});

document.querySelectorAll('[data-premium-video-url]').forEach(video => {
  video.addEventListener('play', () => {
    fetch(video.dataset.premiumVideoUrl, {
      method:'POST', credentials:'same-origin',
      headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:new URLSearchParams({csrf_token:video.dataset.premiumCsrf})
    }).catch(() => {});
  }, {once:true});
});
