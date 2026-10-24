import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { MovieData } from '../docs/data-store.mjs';

const original = JSON.parse(await readFile(new URL('../docs/data/movies.json', import.meta.url), 'utf8'));
const displayed = movie => Object.fromEntries(Object.entries(movie).filter(([key]) => key !== 'sources'));
function fixture() {
  const requests = [];
  let active = 0, maximum = 0, failures = 0;
  const store = new MovieData('', async name => {
    requests.push(name);
    maximum = Math.max(maximum, ++active);
    try {
      if (failures) { failures -= 1; throw new Error('offline'); }
      const text = await readFile(new URL('../docs/data/' + name, import.meta.url), 'utf8');
      return { ok: true, json: async () => JSON.parse(text) };
    } finally { active -= 1; }
  });
  return { store, requests, maximum: () => maximum, fail: () => { failures = 1; } };
}

test('initial page reads only manifest, selected descriptor and one page; 25/50/100 and page reuse preserve rank', async () => {
  const { store, requests } = fixture();
  await store.init();
  const rows = original.movies.filter(movie => movie.sources.includes(0)).map(displayed);
  assert.deepEqual(await store.page(0, null, 0, 50), rows.slice(0, 50));
  assert.equal(requests.length, 3);
  assert.ok(!requests.some(name => name.includes('search.') || name.includes('members.') || name === 'movies.json'));
  assert.deepEqual(await store.page(0, null, 50, 50), rows.slice(50, 100));
  assert.deepEqual(await store.page(0, null, 25, 25), rows.slice(25, 50));
  assert.equal(requests.length, 3);
  assert.deepEqual(await store.page(0, null, 100, 100), rows.slice(100, 200));
  assert.deepEqual(await store.page(0, null, 37250, 50), rows.slice(37250, 37300));
});

test('complete current-list search matches legacy ID/title semantics and reuses one shared search index', async () => {
  const { store, requests, maximum } = fixture();
  await store.init();
  for (const source of [0, 2, 51, 133, 224]) {
    const rows = original.movies.filter(movie => movie.sources.includes(source));
    for (const query of ['霸王', '12', 'love', '不存在的影视条目']) {
      const matches = rows.filter(movie => movie.id.includes(query) || movie.title.toLocaleLowerCase('zh-CN').includes(query));
      const positions = await store.search(source, query);
      assert.equal(positions.length, matches.length);
      assert.deepEqual(await store.page(source, positions, 0, 50), matches.slice(0, 50).map(displayed));
    }
  }
  assert.equal(requests.filter(name => name.includes('search.')).length, 1);
  assert.ok(maximum() <= 3);
  assert.ok(store.caches.page.size <= 8);
  assert.ok(store.caches.source.size <= 4);
  assert.ok(store.caches.members.size <= 3);
});

test('simultaneous page reads share requests; failed reads retry; stale work stops without filling further pages', async () => {
  const context = fixture(), { store, requests } = context;
  await store.init();
  const [first, shared] = await Promise.all([store.page(0, null, 0, 50), store.page(0, null, 0, 50)]);
  assert.deepEqual(first, shared);
  assert.equal(requests.length, 3);
  context.fail();
  await assert.rejects(store.page(0, null, 100, 50), /offline/);
  assert.equal((await store.page(0, null, 100, 50)).length, 50);
  const count = requests.length;
  assert.deepEqual(await store.page(0, null, 200, 50, () => false), []);
  assert.equal(requests.length, count);
});

for (const phase of ['fetch', 'body']) {
  test(`a stalled ${phase} times out, releases queued downloads and allows shared readers to retry`, async () => {
    const attempts = new Map(), signals = [], dispatched = [];
    const store = new MovieData('', async (name, { signal }) => {
      dispatched.push(name);
      assert.ok(store.active <= 3);
      const attempt = (attempts.get(name) || 0) + 1;
      attempts.set(name, attempt);
      if (name !== 'ready' && attempt === 1) {
        signals.push(signal);
        const stalled = new Promise(() => {});
        if (phase === 'fetch') return stalled;
        return { ok: true, json: () => stalled };
      }
      return { ok: true, json: async () => [name] };
    }, { timeoutMs: 40 });

    const blocked = ['a', 'b', 'c'].map(name => store.cached('page', name, 8));
    const shared = store.cached('page', 'a', 8);
    const ready = store.cached('page', 'ready', 8);
    assert.deepEqual(dispatched, ['a', 'b', 'c']);
    const results = await Promise.allSettled([...blocked, shared, ready]);
    for (const result of results.slice(0, 4)) {
      assert.equal(result.status, 'rejected');
      assert.equal(result.reason.name, 'TimeoutError');
    }
    assert.deepEqual(results[4], { status: 'fulfilled', value: ['ready'] });
    assert.ok(signals.every(signal => signal.aborted));
    assert.equal(attempts.get('a'), 1);
    assert.equal(store.pending.size, 0);
    assert.equal(store.active, 0);
    assert.deepEqual(await store.cached('page', 'a', 8), ['a']);
    assert.equal(attempts.get('a'), 2);
  });
}
