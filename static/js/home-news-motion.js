(() => {
  const section = document.querySelector('.home-science-news');
  if (!section || !window.IntersectionObserver || !window.matchMedia) return;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (reducedMotion.matches) return;

  const items = [...section.querySelectorAll('.home-news-feature .news-card, .home-news-rail .news-card')];
  const animations = new Map();
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      const card = entry.target;
      observer.unobserve(card);
      if (reducedMotion.matches || card.contains(document.activeElement) || !card.animate) continue;

      const featured = Boolean(card.closest('.home-news-feature'));
      const slide = featured && window.matchMedia('(min-width: 761px)').matches
        ? 'translateX(18px)' : 'translateY(14px)';
      const animation = card.animate([
        { opacity: 0.35, transform: slide },
        { opacity: 1, transform: 'none' }
      ], {
        duration: featured ? 520 : 420,
        delay: featured ? 0 : Math.min(items.indexOf(card) * 65, 130),
        easing: 'cubic-bezier(0.2, 0.7, 0.3, 1)',
        fill: 'backwards'
      });
      animations.set(card, animation);
      animation.onfinish = () => animations.delete(card);
    }
  }, { threshold: 0.12 });

  for (const card of items) {
    observer.observe(card);
    card.addEventListener('focusin', () => {
      observer.unobserve(card);
      animations.get(card)?.cancel();
      animations.delete(card);
    }, { once: true });
  }

  reducedMotion.addEventListener?.('change', event => {
    if (!event.matches) return;
    observer.disconnect();
    for (const animation of animations.values()) animation.cancel();
    animations.clear();
  });
})();
