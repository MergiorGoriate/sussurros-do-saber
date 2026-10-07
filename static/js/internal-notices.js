/* Private, bounded summary, refreshed only in a visible tab. Text is never HTML. */
(() => {
  const bar = document.querySelector('[data-notice-bar]');
  if (!bar) return;
  const status = bar.querySelector('[data-notice-status]');
  const list = bar.querySelector('[data-notice-items]');
  const template = bar.querySelector('form');
  const node = (tag, text) => { const el = document.createElement(tag); if (text) el.textContent = text; return el; };
  const hidden = (name, value) => { const el = node('input'); el.type = 'hidden'; el.name = name; el.value = value; return el; };
  let busy = false;
  const refresh = async () => {
    if (busy || document.hidden) return;
    busy = true; status.textContent = 'A actualizar notificações…';
    try {
      const response = await fetch(bar.dataset.summaryUrl, {credentials: 'same-origin', cache: 'no-store'});
      if (!response.ok) throw new Error('inbox');
      const data = await response.json();
      document.querySelectorAll('[data-notice-count]').forEach(el => { el.textContent = String(data.unread); });
      list.replaceChildren();
      for (const item of data.items) {
        const section = node('section');
        section.append(node('strong', item.title), node('p', item.description), node('time', item.date), node('p', item.unread ? 'Por ler' : 'Lida'));
        if (item.url) { const link = node('a', 'Abrir recurso'); link.setAttribute('href', item.url); section.append(link); }
        const form = node('form'); form.method = 'post'; form.setAttribute('action', template.getAttribute('action'));
        form.append(hidden('csrf_token', template.querySelector('[name="csrf_token"]').value), hidden('id', item.id));
        for (const [action, label] of [['read', 'Marcar como lida'], ['delete', 'Eliminar aviso']]) {
          if (action === 'read' && !item.unread) continue;
          const button = node('button', label); button.name = 'action'; button.value = action; form.append(button);
        }
        section.append(form); list.append(section);
      }
      if (!data.items.length) list.append(node('p', 'Sem notificações.'));
      status.textContent = 'Notificações actualizadas.';
    } catch (_) { status.textContent = 'Não foi possível actualizar. Volte a abrir a página de notificações.'; }
    finally { busy = false; }
  };
  bar.addEventListener('toggle', () => { if (bar.open) refresh(); });
  document.addEventListener('visibilitychange', refresh);
  document.addEventListener('notice-inbox-change', refresh);
  setInterval(refresh, 60000);
})();
