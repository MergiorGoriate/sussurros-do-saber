(() => {
  const toggle = document.querySelector('#articleScienceVideo');
  const mode = document.querySelector('#coverMode');
  if (!toggle || !mode) return;
  const container = toggle.closest('fieldset');
  const fields = document.querySelector('#articleScienceVideoFields');
  const update = () => {
    container.hidden = !['video_animated', 'video_controls'].includes(mode.value);
    toggle.disabled = container.hidden;
    fields.hidden = container.hidden || !toggle.checked;
    fields.disabled = fields.hidden;
  };
  mode.addEventListener('change', update);
  toggle.addEventListener('change', update);
  update();
})();
