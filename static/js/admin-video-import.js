document.querySelector('[data-video-import-all]')?.addEventListener('change', (event) => {
  for (const option of event.target.form.querySelectorAll('input[name="articles"]')) {
    option.checked = event.target.checked;
  }
});
