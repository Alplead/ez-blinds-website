import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const script = readFileSync(new URL('../wp-content/themes/ezb-theme/assets/js/site.js', import.meta.url), 'utf8');

function simulate({ reduced = false, hidden = false, hasVideo = true } = {}) {
  const listeners = {};
  const pref = {
    matches: reduced,
    addEventListener(event, fn) { listeners['motion-' + event] = fn; }
  };
  const video = {
    autoplay: false, paused: true, playCount: 0, pauseCount: 0,
    play() { this.playCount++; this.paused = false; return Promise.resolve(); },
    pause() { this.pauseCount++; this.paused = true; }
  };
  const target = { classList: { add() {} }, style: { setProperty() {} } };
  const document = {
    hidden,
    documentElement: { classList: { add() {}, remove() {} } },
    querySelectorAll(selector) {
      if (selector === '.ezb-quote-form') return [];
      if (selector === '[data-ezb-autoplay-video]') return hasVideo ? [video] : [];
      return [target];
    },
    addEventListener(event, fn) { listeners[event] = fn; }
  };
  runInNewContext(script, { document, window: { matchMedia() { return pref; } } });
  return {
    video, listeners,
    visibility(value) { document.hidden = value; listeners.visibilitychange?.(); },
    motion(value) { pref.matches = value; listeners['motion-change']?.({ matches: value }); }
  };
}

const background = simulate({ hidden: true });
assert.equal(background.video.playCount, 0, 'hidden initial load must not play');
background.visibility(false);
assert.equal(background.video.playCount, 1, 'visible tab may autoplay');
background.visibility(true);
assert.equal(background.video.autoplay, false, 'hidden tab disables autoplay');
assert.ok(background.video.pauseCount >= 1, 'hidden tab pauses active video');
background.motion(true);
background.visibility(false);
assert.equal(background.video.playCount, 1, 'reduced motion prevents resume');
background.motion(false);
assert.equal(background.video.playCount, 2, 'visible tab may resume when motion is permitted');
background.visibility(true);
background.motion(true);
background.motion(false);
assert.equal(background.video.playCount, 2, 'hidden motion changes must not resume');

const reducedInitially = simulate({ reduced: true });
assert.equal(reducedInitially.video.playCount, 0);
reducedInitially.visibility(true);
reducedInitially.visibility(false);
assert.equal(reducedInitially.video.playCount, 0, 'visibility cannot override reduced motion');

const noVideo = simulate({ hasVideo: false });
assert.equal(noVideo.listeners.visibilitychange, undefined, 'avoid unused listener');
console.log('EZB_VIDEO_VISIBILITY_REGRESSION_PASS cases=3');
