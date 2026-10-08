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
