document.querySelectorAll('[data-dc-copy]').forEach(button => {
  button.addEventListener('click', async () => {
    const field = document.getElementById(button.dataset.dcCopy);
    if (!field) return;
    try {
      await navigator.clipboard.writeText(field.value);
      button.textContent = 'Texto e ligação copiados';
    } catch {
      field.focus();
      field.select();
      button.textContent = 'Texto seleccionado. Use a opção de copiar do dispositivo.';
    }
  });
});
