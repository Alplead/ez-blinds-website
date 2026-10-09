import assert from 'node:assert/strict';
import { inspectMediaImage, heroImageCountFailure, mediaImageSourceFailure } from './media-image-readiness.mjs';

function fakeLocator(image) {
  const calls = [];
  return {
    calls,
    async scrollIntoViewIfNeeded() { calls.push('scroll'); },
    async evaluate(fn) { calls.push('evaluate'); return fn(image); }
  };
}

let decoded = false;
const lazy = fakeLocator({
  complete: false, naturalWidth: 0, naturalHeight: 0,
  currentSrc: '', src: '/approved.webp',
  getAttribute(name) { return name === 'alt' ? 'Real installation' : null; },
  async decode() {
    decoded = true;
    this.complete = true;
    this.naturalWidth = 1200;
    this.naturalHeight = 800;
  }
});
const good = await inspectMediaImage(lazy);
assert.deepEqual(lazy.calls, ['scroll', 'evaluate']);
assert.equal(decoded, true);
assert.equal(good.complete, true);
assert.equal(good.naturalWidth, 1200);
assert.equal(good.alt, 'Real installation');

const broken = fakeLocator({
  complete: true, naturalWidth: 0, naturalHeight: 0,
  currentSrc: '/missing.webp', src: '/missing.webp',
  getAttribute() { return ''; },
  async decode() { throw new Error('image decode failed'); }
});
const failed = await inspectMediaImage(broken);
assert.equal(failed.naturalWidth, 0);
assert.equal(failed.alt, '');

const legacy = fakeLocator({
  complete: true, naturalWidth: 400, naturalHeight: 300,
  currentSrc: '/legacy.webp', src: '/legacy.webp',
  getAttribute() { return 'Legacy media'; }
});
const fallback = await inspectMediaImage(legacy);
assert.equal(fallback.naturalWidth, 400);
assert.equal(fallback.src, '/legacy.webp');

assert.equal(heroImageCountFailure(1), '');
assert.match(heroImageCountFailure(0), /exactly one hero image/);
assert.match(heroImageCountFailure(2), /exactly one hero image/);
assert.equal(heroImageCountFailure(0, false), '');
assert.match(heroImageCountFailure(2, false), /at most one hero image/);
const verifiedBase = 'https://staging.example.test/';
const mediaSources = [
  ['/wp-content/uploads/2026/10/hero.webp', ''],
  ['https://staging.example.test/wp-content/uploads/gallery.webp', ''],
  ['https://external.example.test/photo.webp', 'same-origin'],
  ['//external.example.test/photo.webp', 'same-origin'],
  ['data:image/webp;base64,AAAA', 'same-origin'],
  ['blob:https://staging.example.test/123', 'same-origin'],
  ['javascript:alert(1)', 'same-origin'],
  ['', 'missing']
];
for (const [source, expectedFailure] of mediaSources) {
  const failure = mediaImageSourceFailure(source, verifiedBase);
  if (expectedFailure) assert.match(failure, new RegExp(expectedFailure));
  else assert.equal(failure, '');
}
console.log('EZB_MEDIA_IMAGE_READINESS_TEST_PASS cases=16');
