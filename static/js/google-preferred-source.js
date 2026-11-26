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

// Explain the preference without changing the reader's Google settings.
document.querySelectorAll('.google-preferred-source-info').forEach(info => {
  const trigger = info.querySelector('.google-preferred-source-info-button');
  const tooltip = info.querySelector('.google-preferred-source-tooltip');
  if (!trigger || !tooltip) return;

  const position = () => {
    tooltip.removeAttribute('data-placement');
    tooltip.style.removeProperty('--preferred-tooltip-offset');
    const margin = 12;
    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = document.documentElement.clientHeight;
    const preferred = tooltip.getBoundingClientRect();
    if (preferred.right <= viewportWidth - margin && preferred.bottom <= viewportHeight - margin) return;
    tooltip.dataset.placement = 'below';
    const below = tooltip.getBoundingClientRect();
    if (below.bottom > viewportHeight - margin &&
        info.getBoundingClientRect().top > below.height + margin) {
      tooltip.dataset.placement = 'above';
    }
    const bounds = tooltip.getBoundingClientRect();
    const offset = Math.min(0, viewportWidth - margin - bounds.right) +
      Math.max(0, margin - bounds.left);
    tooltip.style.setProperty('--preferred-tooltip-offset', offset + 'px');
  };
  const open = () => {
    tooltip.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    position();
  };
  const close = () => {
    tooltip.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
  };

  info.addEventListener('pointerenter', event => {
    if (event.pointerType !== 'touch') open();
  });
  info.addEventListener('pointerleave', event => {
    if (event.pointerType !== 'touch' && !trigger.matches(':focus-visible')) close();
  });
  trigger.addEventListener('focus', () => {
    if (trigger.matches(':focus-visible')) open();
  });
  trigger.addEventListener('blur', () => {
    if (!info.matches(':hover')) close();
  });
  trigger.addEventListener('click', () => {
    if (tooltip.hidden) open();
    else close();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !tooltip.hidden) close();
  });
  document.addEventListener('pointerdown', event => {
    if (!info.contains(event.target)) close();
  });
  window.addEventListener('resize', () => {
    if (!tooltip.hidden) position();
  });
});
