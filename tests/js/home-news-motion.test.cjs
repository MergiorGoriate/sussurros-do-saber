const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/js/home-news-motion.js', 'utf8');

function harness({ reduced = false, desktop = true, supported = true, listing = false, width = desktop ? 1280 : 390 } = {}) {
  const observed = new Set();
  const played = [];
  const listeners = {};
  const document = { activeElement: null };
  const cards = [true, false, false].map(featured => ({
    closest: () => featured,
    contains: element => Boolean(element && element.card === featured),
    addEventListener(name, callback) { this[name] = callback; },
    animate(frames, options) {
      const animation = { cancelled: false, cancel() { this.cancelled = true; } };
      played.push({ frames, options, animation });
      return animation;
    }
  }));
  document.querySelector = () => ({ querySelectorAll: () => cards, matches: () => listing });
  let intersection;
  class Observer {
    constructor(callback) { intersection = callback; }
    observe(card) { observed.add(card); }
    unobserve(card) { observed.delete(card); }
    disconnect() { observed.clear(); }
  }
  const preference = {
    matches: reduced,
    addEventListener(name, callback) { listeners[name] = callback; }
  };
  const window = {
    IntersectionObserver: supported ? Observer : undefined,
    matchMedia: query => query.includes('reduced-motion') ? preference : { matches: width >= Number(query.match(/\d+/)[0]) }
  };
  vm.runInNewContext(source, { document, window, IntersectionObserver: window.IntersectionObserver });
  return {
    cards, observed, played,
    enter(index) {
      if (observed.has(cards[index])) intersection([{ target: cards[index], isIntersecting: true }]);
    },
    reduce() {
      preference.matches = true;
      listeners.change?.({ matches: true });
    }
  };
}

test('cards animate once as they enter, with directional and staggered effects', () => {
  const h = harness();
  assert.equal(h.observed.size, 3);
  assert.equal(h.played.length, 0);
  h.enter(0); h.enter(1); h.enter(2); h.enter(0);
  assert.equal(h.played.length, 3);
  assert.equal(h.played[0].frames[0].transform, 'translateX(18px)');
  assert.equal(h.played[1].frames[0].transform, 'translateY(14px)');
  assert.ok(h.played[1].options.delay < h.played[2].options.delay);
  assert.equal(h.observed.size, 0);
});

test('mobile entries remain vertical and keyboard focus cancels movement', () => {
  const h = harness({ desktop: false });
  h.enter(0);
  assert.equal(h.played[0].frames[0].transform, 'translateY(14px)');
  h.cards[0].focusin();
  assert.equal(h.played[0].animation.cancelled, true);
  h.cards[1].focusin();
  h.enter(1);
  assert.equal(h.played.length, 1);
});

test('reduced motion and unavailable observation leave the original content visible', () => {
  for (const options of [{ reduced: true }, { supported: false }]) {
    const h = harness(options);
    assert.equal(h.observed.size, 0);
    assert.equal(h.played.length, 0);
  }
  const h = harness();
  h.enter(0);
  h.reduce();
  assert.equal(h.played[0].animation.cancelled, true);
  assert.equal(h.observed.size, 0);
});

test('listing follows its own tablet breakpoint and uses vertical movement for stacked cards', () => {
  const tablet = harness({ listing: true, width: 850 });
  tablet.enter(0);
  assert.equal(tablet.played[0].frames[0].transform, 'translateY(14px)');
  const wide = harness({ listing: true, width: 1280 });
  wide.enter(0); wide.enter(1);
  assert.equal(wide.played[0].frames[0].transform, 'translateX(18px)');
  assert.equal(wide.played[1].frames[0].transform, 'translateY(14px)');
});
