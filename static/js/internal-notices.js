/* Private, bounded inbox summary. All notification text is inserted as text. */
(() => {
  const bar = document.querySelector('[data-notice-bar]');
  if (!bar) return;
  const status = bar.querySelector('[data-notice-status]');
  const retry = bar.querySelector('[data-notice-retry]');
  const list = bar.querySelector('[data-notice-items]');
  const template = bar.querySelector('form');
  const node = (tag, text, className) => { const el = document.createElement(tag); if (text) el.textContent = text; if (className) el.className = className; return el; };
  const hidden = (name, value) => { const el = node('input'); el.type = 'hidden'; el.name = name; el.value = value; return el; };
  const fitPopover = () => {
    if (!bar.open) return;
    const rect = bar.querySelector('summary').getBoundingClientRect();
    const below = window.innerHeight - rect.bottom - 26;
    const above = rect.top - 26;
    const flip = below < 240 && above > below;
    const popover = bar.querySelector('.notice-popover');
    popover.classList.toggle('opens-above', flip);
    popover.style.maxHeight = `${Math.max(100, flip ? above : below)}px`;
  };
  window.addEventListener('resize', fitPopover);
  window.addEventListener('scroll', fitPopover, {passive: true, capture: true});
  let busy = false;
  const refresh = async () => {
    if (busy || document.hidden) return;
    busy = true;
    bar.setAttribute('aria-busy', 'true');
    retry.disabled = true;
    if (bar.open) status.textContent = 'A actualizar notificações…';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(bar.dataset.summaryUrl, {credentials: 'same-origin', cache: 'no-store', signal: controller.signal});
      if (!response.ok) throw new Error('inbox');
      const data = await response.json();
      if (!Number.isInteger(data.unread) || data.unread < 0 || !Array.isArray(data.items)) throw new Error('inbox');
      document.querySelectorAll('[data-notice-count]').forEach(el => { el.textContent = String(data.unread); if (el.classList.contains('notice-badge')) el.hidden = !data.unread; });
      bar.querySelector('[data-notice-preview-count]').textContent = String(data.unread);
      bar.querySelector('[data-notice-label]').textContent = `Notificações · ${data.unread} por ler`;
      bar.querySelector('summary').setAttribute('aria-label', `Notificações internas · ${data.unread} por ler`);
      bar.querySelector('[data-notice-read-all]').disabled = !data.unread;
      const items = document.createDocumentFragment();
      for (const item of data.items) {
        const section = node('section', '', `notice-item${item.unread ? ' is-unread' : ''}`);
        const heading = node('div', '', 'notice-item-heading');
        heading.append(node('strong', item.title), node('span', item.unread ? 'Por ler' : 'Lida', `notice-state${item.unread ? ' notice-state-unread' : ''}`));
        section.append(heading, node('p', item.description, 'notice-preview-body'), node('time', item.date));
        const actions = node('div', '', 'notice-item-actions');
        if (item.url) { const link = node('a', 'Abrir recurso', 'notice-button'); link.setAttribute('href', item.url); actions.append(link); }
        const form = node('form'); form.method = 'post'; form.setAttribute('action', template.getAttribute('action'));
        form.append(hidden('csrf_token', template.querySelector('[name="csrf_token"]').value), hidden('id', item.id));
        for (const [action, label] of [['read', 'Marcar como lida'], ['delete', 'Eliminar aviso']]) {
          if (action === 'read' && !item.unread) continue;
          const button = node('button', '', `notice-button notice-icon-action${action === 'delete' ? ' notice-button-danger' : ''}`);
          button.title = label;
          const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
          for (const [key,value] of Object.entries({viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':'1.7','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'})) icon.setAttribute(key,value);
          const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
          path.setAttribute('d', action === 'read' ? 'M5 12l4 4L19 6' : 'M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7');
          icon.append(path); button.append(icon, node('span', label, 'notice-sr-only'));
          button.type = 'submit'; button.name = 'action'; button.value = action; form.append(button);
        }
        actions.append(form); section.append(actions); items.append(section);
      }
      if (!data.items.length) items.append(node('p', 'Sem notificações.', 'notice-preview-empty'));
      list.replaceChildren(items);
      bar.classList.remove('has-error');
      retry.hidden = true;
      fitPopover();
      status.textContent = bar.open ? 'Notificações actualizadas.' : '';
    } catch (_) {
      bar.classList.add('has-error'); retry.hidden = false;
      if (bar.open) status.textContent = 'Não foi possível actualizar. Os avisos apresentados continuam disponíveis.';
      fitPopover();
    }
    finally { clearTimeout(timeout); busy = false; retry.disabled = false; bar.removeAttribute('aria-busy'); }
  };
  retry.addEventListener('click', refresh);
  bar.addEventListener('toggle', () => { if (bar.open) { fitPopover(); refresh(); } });
  document.addEventListener('click', event => { if (!bar.contains(event.target)) bar.open = false; });
  bar.addEventListener('keydown', event => { if (event.key === 'Escape') { bar.open = false; bar.querySelector('summary').focus(); } });
  document.addEventListener('visibilitychange', refresh);
  document.addEventListener('notice-inbox-change', refresh);
  setInterval(refresh, 60000);
})();
