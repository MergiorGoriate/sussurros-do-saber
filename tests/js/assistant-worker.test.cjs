const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../cloudflare-worker/worker.js'));
const worker = import('data:text/javascript;base64,' + source.toString('base64'));
const request = body => new Request('https://worker.test', {
  method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Assistant-Key': 'test' },
  body: JSON.stringify(body)
});

test('worker chooses English or Portuguese and keeps source accuracy instructions', async () => {
  for (const language of ['en', 'pt', 'unknown']) {
    let prompt;
    const env = { ASSISTANT_SHARED_KEY: 'test', AI: { run: async (_, options) => {
      prompt = options.messages[0].content;
      return { response: 'Answer' };
    } } };
    const response = await (await worker).default.fetch(request({ message: 'Question', language }), env);
    assert.equal(response.status, 200);
    assert.match(prompt, language === 'en' ? /English/ : /português/);
    assert.match(prompt, language === 'en' ? /Do not invent sources/ : /sem inventar fontes/);
  }
});

test('worker rejects malformed questions without invoking AI', async () => {
  const env = { ASSISTANT_SHARED_KEY: 'test', AI: { run: () => { throw Error('must not run'); } } };
  for (const payload of [null, [], {}, { message: 42 }, { message: 'x'.repeat(801) }]) {
    const response = await (await worker).default.fetch(request(payload), env);
    assert.equal(response.status, 400);
  }
});

test('worker explains English outages in English', async () => {
  const env = { ASSISTANT_SHARED_KEY: 'test', AI: { run: async () => { throw Error('offline'); } } };
  const response = await (await worker).default.fetch(request({ message: 'Question', language: 'en' }), env);
  assert.equal(response.status, 502);
  assert.match((await response.json()).answer, /temporarily unavailable/);
});

test('worker applies selected language to grounding and preserves source links', async () => {
  for (const language of ['en', 'pt']) {
    let messages;
    const env = { ASSISTANT_SHARED_KEY: 'test', AI: { run: async (_, options) => {
      messages = options.messages;
      return { response: language === 'en' ? 'English answer' : 'Resposta em português' };
    } } };
    const sources = [{ title: 'Biologia', url: 'https://www.sussurrosdosaber.com/artigo/biologia', excerpt: 'A célula é a unidade básica da vida.' }];
    const response = await (await worker).default.fetch(request({ message: 'What is a cell?', language, sources,
      history: [{ role: 'user', content: 'Previous question' }] }), env);
    const data = await response.json();
    assert.equal(response.status, 200);
    assert.equal(data.links.length, 1);
    assert.equal(data.links[0].title, 'Biologia');
    assert.equal(data.links[0].url, sources[0].url);
    assert.match(messages[1].content, language === 'en' ? /general knowledge/ : /conhecimento geral/);
    assert.match(messages[1].content, /Biologia/);
    assert.equal(messages[2].content, 'Previous question');
    assert.equal(messages.at(-1).content, 'What is a cell?');
  }
});

test('worker falls back to general knowledge without fabricated portal links', async () => {
  let messages;
  const env = { ASSISTANT_SHARED_KEY: 'test', AI: { run: async (_, options) => {
    messages = options.messages;
    return { response: 'General knowledge answer' };
  } } };
  const response = await (await worker).default.fetch(request({ message: 'Question', language: 'en', sources: [] }), env);
  const data = await response.json();
  assert.deepEqual(data.links, []);
  assert.match(messages[1].content, /general knowledge/);
});
