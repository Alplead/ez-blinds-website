import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const script = readFileSync(new URL('../wp-content/themes/ezb-theme/assets/js/site.js', import.meta.url), 'utf8');

function simulate({ reduced, observerSupported }) {
  const rootClasses = new Set();
  const targetClasses = new Set();
  const video = { autoplay: false, pauseCount: 0, playCount: 0, pause() { this.pauseCount++; }, play() { this.playCount++; return Promise.resolve(); } };
  const target = {
    classList: { add(name) { targetClasses.add(name); } },
    style: { setProperty() {} }
  };
  let changeListener;
  let observerInstance;
  const preference = {
    matches: reduced,
    addEventListener(name, listener) { if (name === 'change') changeListener = listener; }
  };
  const document = {
    documentElement: { classList: {
      add(name) { rootClasses.add(name); },
      remove(name) { rootClasses.delete(name); }
    } },
    querySelectorAll(selector) {
      if (selector === '.ezb-quote-form') return [];
      return selector === '[data-ezb-autoplay-video]' ? [video] : [target];
    }
  };
  const window = { matchMedia() { return preference; } };
  const context = { window, document };
  if (observerSupported) {
    class FakeObserver {
      constructor(callback) { this.callback = callback; this.observed = []; observerInstance = this; }
      observe(element) { this.observed.push(element); }
      unobserve(element) { this.observed = this.observed.filter(item => item !== element); }
    }
    window.IntersectionObserver = FakeObserver;
    context.IntersectionObserver = FakeObserver;
  }
  runInNewContext(script, context);
  return {
    rootClasses, targetClasses, video, observerInstance,
    setReduced(value) { preference.matches = value; changeListener?.({ matches: value }); },
    target
  };
}

const initiallyReduced = simulate({ reduced: true, observerSupported: true });
assert.equal(initiallyReduced.video.autoplay, false);
assert.equal(initiallyReduced.video.pauseCount, 1);
assert.equal(initiallyReduced.video.playCount, 0, 'reduced motion must never autoplay');
assert.equal(initiallyReduced.rootClasses.has('ezb-motion-ready'), false);
assert.equal(initiallyReduced.observerInstance, undefined);

const withoutObserver = simulate({ reduced: false, observerSupported: false });
assert.equal(withoutObserver.rootClasses.has('ezb-motion-ready'), true);
assert.equal(withoutObserver.video.playCount, 1, 'normal motion may autoplay');
assert.equal(withoutObserver.targetClasses.has('ezb-in-view'), true);
withoutObserver.setReduced(true);
assert.equal(withoutObserver.video.autoplay, false);
assert.equal(withoutObserver.video.pauseCount, 1);
assert.equal(withoutObserver.rootClasses.has('ezb-motion-ready'), false);

const withObserver = simulate({ reduced: false, observerSupported: true });
assert.equal(withObserver.observerInstance.observed.length, 1);
assert.equal(withObserver.video.playCount, 1);
withObserver.observerInstance.callback([{ isIntersecting: true, target: withObserver.target }], withObserver.observerInstance);
assert.equal(withObserver.targetClasses.has('ezb-in-view'), true);
withObserver.setReduced(true);
assert.equal(withObserver.rootClasses.has('ezb-motion-ready'), false);
assert.equal(withObserver.video.pauseCount, 1);
withObserver.setReduced(false);
assert.equal(withObserver.rootClasses.has('ezb-motion-ready'), false);
assert.equal(withObserver.video.autoplay, true);
assert.equal(withObserver.video.playCount, 2, 'autoplay resumes after motion preference allows it');

const plugin = readFileSync(new URL('../wp-content/plugins/ezb-core/ezb-core.php', import.meta.url), 'utf8');
const videoTag = plugin.match(/<video data-ezb-autoplay-video[^>]*>/)?.[0] || '';
assert.ok(videoTag, 'development video shortcode must be present');
assert.match(videoTag, /\scontrols(?:\s|>)/, 'manual video controls are required');
assert.doesNotMatch(videoTag, /\sautoplay(?:\s|>)/, 'HTML must not start playing before JS checks preference');

console.log('EZB_SITE_MOTION_TEST_PASS cases=4');
