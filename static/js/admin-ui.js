document.addEventListener('click', (event) => {
  const confirmButton = event.target.closest('[data-confirm]');
  if (confirmButton && !window.confirm(confirmButton.dataset.confirm)) {
    event.preventDefault();
    event.stopImmediatePropagation();
    return;
  }
  if (event.target.closest('[data-print-recovery]')) {
    window.print();
  }
});


// Only presentation is stored; the server continues to determine visible links.
(() => {
  const toggle = document.querySelector('[data-sidebar-toggle]');
  if (!toggle) return;
  const key = 'sussurros.admin.sidebar.collapsed';
  function apply(collapsed) {
    document.body.classList.toggle('admin-sidebar-collapsed', collapsed);
    toggle.setAttribute('aria-expanded', String(!collapsed));
    const label = collapsed ? 'Expandir barra lateral' : 'Recolher barra lateral';
    toggle.setAttribute('aria-label', label);
    toggle.title = label;
  }
  try { apply(localStorage.getItem(key) === 'true'); } catch (_) { apply(false); }
  toggle.addEventListener('click', () => {
    const collapsed = !document.body.classList.contains('admin-sidebar-collapsed');
    apply(collapsed);
    try { localStorage.setItem(key, String(collapsed)); } catch (_) { /* Storage may be disabled. */ }
  });
  window.addEventListener('storage', event => {
    if (event.key === key) apply(event.newValue === 'true');
  });
})();

// Theme is a local presentation preference; authorization remains server-side.
(() => {
  const button = document.querySelector('[data-admin-theme-toggle]');
  if (!button) return;
  const key = 'sussurros.admin.theme';
  const systemDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  let stored = null;
  try { stored = localStorage.getItem(key); } catch (_) { /* Private browsing. */ }
  let dark = stored === 'dark' || (stored !== 'light' && systemDark);
  function apply() {
    document.body.classList.toggle('admin-dark', dark);
    button.setAttribute('aria-pressed', String(dark));
    button.title = dark ? 'Activar tema claro' : 'Activar tema escuro';
  }
  apply();
  button.addEventListener('click', () => {
    dark = !dark;
    apply();
    try { localStorage.setItem(key, dark ? 'dark' : 'light'); } catch (_) { /* Optional. */ }
  });
  window.addEventListener('storage', event => {
    if (event.key === key) {
      dark = event.newValue === 'dark' || (event.newValue !== 'light' && systemDark);
      apply();
    }
  });
})();
