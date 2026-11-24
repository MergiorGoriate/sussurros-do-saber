(() => {
  'use strict';
  const title = document.getElementById('news-title');
  const select = document.getElementById('news-category');
  const help = document.getElementById('news-category-help');
  if (!title || !select || !help) return;

  // Heurística transparente, sem envio de texto a serviços externos.
  const rules = [
    { names: ['tecnologia','technology','informática','informatica'], words: /\b(ia|ai|intelig[eê]ncia artificial|apple|computador(?:es)?|software|algoritm\w*|rob[oô]\w*|digital|tecnolog\w*|internet|ciberseguran[cç]a|aplica[cç][oõ]es?|tiktok|deepfake\w*)\b/i },
    { names: ['saúde','saude','health','medicina'], words: /\b(sa[uú]de|c[aâ]nc[ec]r|doen[cç]\w*|tratament\w*|vacina\w*|terapia\w*|pacient\w*|hospital\w*|medicament\w*|epilepsia)\b/i },
    { names: ['biologia','biology'], words: /\b(biolog\w*|c[eé]lula\w*|gen[eé]tic\w*|dna|genoma\w*|esp[eé]cie\w*|evolu[cç][aã]o)\b/i },
    { names: ['ambiente','environment','ecologia'], words: /\b(ambient\w*|clim[aá]tic\w*|polui[cç][aã]o|ecossistem\w*|biodiversidad\w*|aquecimento global)\b/i },
    { names: ['espaço','espaco','astronomia','space'], words: /\b(espa[cç]o|astronomi\w*|sat[eé]lit\w*|gal[aá]xia\w*|planeta\w*|telesc[oó]pi\w*|nasa)\b/i }
  ];
  const normalize = text => (text || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
  const options = [...select.options].filter(option => option.value);
  let userChanged = false;
  const initialValue = select.value;
  const suggest = () => {
    if (userChanged || (initialValue && initialValue !== '')) return;
    if (!title.value.trim()) return;
    const rule = rules.find(entry => entry.words.test(title.value));
    if (!rule) {
      help.textContent = 'Não foi identificado um tema com segurança. Pode escolher um tema ou publicar sem tema.';
      return;
    }
    const option = options.find(option => rule.names.includes(normalize(option.textContent)));
    if (!option) {
      help.textContent = 'Não existe um tema correspondente no catálogo. Pode publicar sem tema.';
      return;
    }
    select.value = option.value;
    help.textContent = 'Tema sugerido automaticamente: ' + option.textContent.trim() + '. Pode alterá-lo ou seleccionar «Sem tema».';
  };
  select.addEventListener('change', () => {
    userChanged = true;
    help.textContent = select.value ? 'Tema escolhido manualmente.' : 'Sem tema. A notícia pode ser publicada.';
  });
  title.addEventListener('input', suggest);
  suggest();
})();