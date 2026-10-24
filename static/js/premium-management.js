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
