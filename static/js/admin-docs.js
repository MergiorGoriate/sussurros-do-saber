'use strict';
(() => {
  const root = document.querySelector('.docs-workspace');
  if (!root) return;
  const search = root.querySelector('#docs-query');
  const sections = [...root.querySelectorAll('.docs-section')];
  const links = [...root.querySelectorAll('[data-docs-link]')];
  const status = root.querySelector('#docs-search-status');
  const clear = root.querySelector('[data-docs-clear]');
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt').replace(/\s+/g, ' ').trim();
  const content = new Map(sections.map(section => [section.id, normalize(section.textContent)]));
  let scheduled = false;
  function markCurrent() {
    scheduled = false;
    const visible = sections.filter(section => !section.hidden);
    let current = visible[0];
    for (const section of visible) {
      if (section.getBoundingClientRect().top <= 180) current = section;
    }
    links.forEach(link => {
      if (current && link.hash === '#' + current.id) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
  }
  function filter() {
    const query = normalize(search.value);
    let count = 0;
    sections.forEach(section => {
      section.hidden = Boolean(query) && !content.get(section.id).includes(query);
      if (!section.hidden) count++;
    });
    links.forEach(link => { link.parentElement.hidden = document.getElementById(link.hash.slice(1)).hidden; });
    root.querySelectorAll('.docs-index-group').forEach(group => {
      group.hidden = ![...group.querySelectorAll('li')].some(item => !item.hidden);
    });
    root.querySelector('[data-docs-empty]').hidden = count !== 0;
    clear.hidden = !search.value;
    status.textContent = query ? `${count} ${count === 1 ? 'secção encontrada' : 'secções encontradas'}.` : `${sections.length} secções disponíveis. Pesquise por palavra ou expressão.`;
    markCurrent();
  }
  function reset() { search.value = ''; filter(); search.focus(); }
  function revealHash() {
    const id = location.hash.slice(1);
    const target = sections.find(section => section.id === id);
    if (target && target.hidden) {
      search.value = ''; filter(); target.scrollIntoView(); target.focus({preventScroll: true});
    }
    markCurrent();
  }
  search.addEventListener('input', filter);
  clear.addEventListener('click', reset);
  root.querySelector('[data-docs-reset]').addEventListener('click', reset);
  // Quick links remain useful even while a search hides their target section.
  root.querySelectorAll('a[href^="#"]').forEach(link => link.addEventListener('click', () => {
    const target = sections.find(section => '#' + section.id === link.hash);
    if (target && target.hidden) { search.value = ''; filter(); }
  }));
  window.addEventListener('hashchange', revealHash);
  window.addEventListener('scroll', () => {
    if (!scheduled) { scheduled = true; requestAnimationFrame(markCurrent); }
  }, {passive: true});
  root.querySelector('[data-docs-search]').hidden = false;
  filter(); revealHash();
})();
