import assert from 'node:assert/strict';
import { inspectMediaImage, heroImageCountFailure } from './media-image-readiness.mjs';

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
console.log('EZB_MEDIA_IMAGE_READINESS_TEST_PASS cases=8');
