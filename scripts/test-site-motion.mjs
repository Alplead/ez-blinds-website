import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const script = readFileSync(new URL('../wp-content/themes/ezb-theme/assets/js/site.js', import.meta.url), 'utf8');

function simulate({ reduced, observerSupported }) {
  const rootClasses = new Set();
  const targetClasses = new Set();
  const video = { autoplay: true, pauseCount: 0, pause() { this.pauseCount++; } };
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
assert.equal(initiallyReduced.rootClasses.has('ezb-motion-ready'), false);
assert.equal(initiallyReduced.observerInstance, undefined);

const withoutObserver = simulate({ reduced: false, observerSupported: false });
assert.equal(withoutObserver.rootClasses.has('ezb-motion-ready'), true);
assert.equal(withoutObserver.targetClasses.has('ezb-in-view'), true);
withoutObserver.setReduced(true);
assert.equal(withoutObserver.video.autoplay, false);
assert.equal(withoutObserver.video.pauseCount, 1);
assert.equal(withoutObserver.rootClasses.has('ezb-motion-ready'), false);

const withObserver = simulate({ reduced: false, observerSupported: true });
assert.equal(withObserver.observerInstance.observed.length, 1);
withObserver.observerInstance.callback([{ isIntersecting: true, target: withObserver.target }], withObserver.observerInstance);
assert.equal(withObserver.targetClasses.has('ezb-in-view'), true);
withObserver.setReduced(true);
assert.equal(withObserver.rootClasses.has('ezb-motion-ready'), false);
assert.equal(withObserver.video.pauseCount, 1);
withObserver.setReduced(false);
assert.equal(withObserver.rootClasses.has('ezb-motion-ready'), false);

console.log('EZB_SITE_MOTION_TEST_PASS cases=3');
