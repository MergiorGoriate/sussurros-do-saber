const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(require('node:path').join(__dirname, '../../static/js/admin-newsletter.js'), 'utf8');
function element(extra = {}) {
  return Object.assign({value: '', hidden: false, listeners: {}, addEventListener(type, fn) {this.listeners[type] = fn;}, focus() {}}, extra);
}
test('filters combine email and subscription state and can be reset', () => {
  const search = element(), state = element({value: 'all'}), result = element(), clear = element();
  const rows = ['active', 'inactive'].map((status, i) => element({dataset: {subscriberState: status}, querySelector() {return {textContent: ['Ana@exemplo.com', 'rui@exemplo.com'][i]};}}));
  const nodes = {'.newsletter-directory-tools': element(), '#subscriber-search': search, '#subscriber-status-filter': state, '#subscriber-filter-result': result, '#subscriber-clear-filters': clear};
  const page = {querySelector: key => nodes[key], querySelectorAll: () => rows};
  vm.runInNewContext(source, {document: {querySelector: () => page}});
  assert.equal(rows.filter(row => !row.hidden).length, 2);
  search.value = ' ANA@ ';
  search.listeners.input();
  assert.equal(rows[0].hidden, false);
  assert.equal(rows[1].hidden, true);
  state.value = 'inactive';
  state.listeners.change();
  assert.equal(rows.every(row => row.hidden), true);
  assert.match(result.textContent, /Nenhuma/);
  clear.listeners.click();
  assert.equal(rows.every(row => !row.hidden), true);
});
test('scheduling requires a date and clears approval when delivery mode changes', () => {
  const mode = element({value: 'review'}), label = element(), date = element({closest: () => label});
  const confirmation = element({checked: true}), button = element();
  const nodes = {'[name="delivery_mode"]': mode, '[name="scheduled_at"]': date, '[name="confirm"]': confirmation, '[type="submit"]': button};
  const prepare = {querySelector: key => nodes[key]};
  const page = {querySelector: key => key === '.newsletter-prepare-form' ? prepare : null};
  vm.runInNewContext(source, {document: {querySelector: () => page}});
  assert.equal(date.disabled, true);
  assert.equal(label.hidden, true);
  mode.value = 'schedule';
  mode.listeners.change();
  assert.equal(date.required, true);
  assert.equal(date.disabled, false);
  assert.equal(label.hidden, false);
  assert.equal(confirmation.checked, false);
  mode.value = 'now';
  mode.listeners.change();
  assert.equal(date.required, false);
  assert.equal(date.disabled, true);
  assert.match(button.textContent, /fila/);
});
test('script is safe on unrelated admin pages', () => {
  assert.doesNotThrow(() => vm.runInNewContext(source, {document: {querySelector: () => null}}));
});
