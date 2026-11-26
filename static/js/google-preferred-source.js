// Keep the direct Google link usable until the official widget has rendered.
document.querySelectorAll('.google-preferred-source').forEach(container => {
  const widget = container.querySelector('[google-add-preferred-source-btn]');
  const fallback = container.querySelector('.google-preferred-source-fallback');
  if (!widget || !fallback) return;
  const sync = () => {
    fallback.hidden = widget.getBoundingClientRect().height > 0;
  };
  sync();
  if ('ResizeObserver' in window) {
    new ResizeObserver(sync).observe(widget);
  } else if ('MutationObserver' in window) {
    new MutationObserver(sync).observe(widget, { attributes: true, childList: true, subtree: true });
  }
});
