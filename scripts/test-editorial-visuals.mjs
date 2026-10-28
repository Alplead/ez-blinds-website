import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = path => readFileSync(path, 'utf8');
const php = read('wp-content/plugins/ezb-core/includes/ezb-editorial-visuals.php');
const plugin = read('wp-content/plugins/ezb-core/ezb-core.php');
const home = read('wp-content/themes/ezb-theme/templates/front-page.html');
const css = read('wp-content/themes/ezb-theme/assets/css/editorial.css');
const js = read('wp-content/themes/ezb-theme/assets/js/editorial.js');
const functions = read('wp-content/themes/ezb-theme/functions.php');

const required = [
  [plugin, "includes/ezb-editorial-visuals.php", 'Registered plugin include'],
  [php, "add_shortcode(", 'WordPress photo shortcodes'],
  [php, "'ezb_editorial_hero'", 'Photo led hero'],
  [php, "'ezb_editorial_interlude'", 'Large editorial photo chapter'],
  [php, "ezb_find_attachment_by_basename", 'Resolve photos from WordPress Media Library'],
  [php, "wp_get_attachment_image", 'WordPress image sources'],
  [php, "'loading' => 'lazy'", 'Non-hero images lazy loaded'],
  [home, '[ezb_editorial_hero]', 'Home must use curated image hero'],
  [home, '[ezb_editorial_interlude photo="flyscreen"]', 'Flyscreen chapter'],
  [home, '[ezb_editorial_interlude photo="roller"]', 'Roller chapter'],
  [css, '.ezb-cinema', 'Full bleed hero CSS'],
  [css, '.ezb-product-hero', 'Product immersive hero CSS'],
  [css, '.ezb-product-gallery-block .ezb-project-gallery', 'Editorial gallery CSS'],
  [css, '@media (prefers-reduced-motion: reduce)', 'Reduced motion CSS'],
  [js, 'var intervalMs = 7700', 'Approximately 31 seconds for 4 photo cycle'],
  [js, 'prefers-reduced-motion: reduce', 'Reduced motion JS'],
  [js, 'visibilitychange', 'Pause when the tab is hidden'],
  [js, 'mouseenter', 'Pause on hover'],
  [js, 'focusin', 'Pause for keyboard interaction'],
  [js, 'requestAnimationFrame', 'Bound scroll work'],
  [js, 'toggle.disabled = motionBlocked', 'Autoplay control disabled when motion is blocked'],
  [js, 'reduced.matches || slides.length < 2', 'Disabled control for reduced-motion or a single slide'],
  [functions, "'ezb-editorial-motion'", 'JS enqueued'],
  [functions, "'ezb-editorial'", 'CSS enqueued'],
];
for (const [source, needle, description] of required) {
  assert.ok(source.includes(needle), description + ' missing');
}
assert.ok(!php.includes('uploads/'), 'Do not hard-code private uploads paths');
assert.ok(!php.includes('https://'), 'Do not hard-code public media URLs');
assert.ok(php.includes("return ''; // Missing photo:"), 'Unknown media should fail closed');

const imageCount = [...php.matchAll(/'file'\s*=>/g)].length;
assert.equal(imageCount, 4, 'Only four curated and registry-grounded slide sources');


import { runInNewContext } from 'node:vm';

// Exercise the real carousel script against a small DOM simulation, not just
// a substring assertion. Reduced-motion changes must update the control.
function exerciseMotionPreference(initialReduced, failImages = false, missingImage = false) {
  const media = { matches: initialReduced, addEventListener(_event, callback) { this.change = callback; } };
  const control = () => ({
    disabled: false, textContent: '', handlers: {}, attributes: {},
    addEventListener(event, callback) { this.handlers[event] = callback; },
    setAttribute(name, value) { this.attributes[name] = value; }
  });
  const toggle = control();
  const previous = control();
  const next = control();
  const status = { textContent: '' };
  const slides = Array.from({ length: 4 }, (_, position) => {
    const image = {
      loading: 'lazy', complete: false, naturalWidth: 640, handlers: {},
      addEventListener(event, callback) { this.handlers[event] = callback; }
    };
    const slide = {
      active: false, removed: false, image, attributes: {},
      setAttribute(name, value) { this.attributes[name] = value; },
      querySelector(selector) {
        if (selector === '.ezb-cinema__slide-label') return { textContent: 'Image ' + (position + 1) };
        return missingImage && position === 0 ? null : image;
      },
      remove() { this.removed = true; }
    };
    slide.classList = { toggle(_name, active) { slide.active = active; } };
    return slide;
  });
  const controls = { hidden: false };
  const heroFlags = new Set();
  const selectors = {
    '[data-ezb-toggle]': toggle, '[data-ezb-prev]': previous, '[data-ezb-next]': next,
    '.ezb-cinema__controls': controls, '[data-ezb-announcement]': status
  };
  const hero = {
    querySelectorAll() { return slides; },
    querySelector(selector) { return selectors[selector] || null; },
    classList: { toggle() {}, add(name) { heroFlags.add(name); } },
    handlers: {},
    addEventListener(event, callback) { this.handlers[event] = callback; },
    contains() { return false; }
  };
  let timerStarts = 0;
  let timerStops = 0;
  let lastTimerCallback = null;
  let observerCallback = null;
  let observedHero = null;
  const window = {
    matchMedia() { return media; },
    setInterval(callback) { lastTimerCallback = callback; return ++timerStarts; },
    clearInterval() { timerStops++; },
    IntersectionObserver: class {
      constructor(callback, options) {
        observerCallback = callback;
        assert.equal(options.threshold, 0, 'Offscreen observer watches visibility threshold');
      }
      observe(target) { observedHero = target; }
    }
  };
  const document = {
    hidden: false, querySelector() { return hero; },
    querySelectorAll() { return []; }, addEventListener() {}
  };
  runInNewContext(js, { window, document });
  if (missingImage) {
    assert.equal(slides[0].removed, true, 'Empty slide markup is discarded');
    assert.equal(slides[1].active, true, 'First valid image is shown');
    assert.equal(timerStarts, 1, 'Autoplay still works with three valid slides');
    return;
  }
  assert.equal(toggle.disabled, initialReduced, 'Initial autoplay button must reflect motion preference');
  assert.equal(toggle.attributes['aria-pressed'], undefined,
    'Play/Pause action labels must not masquerade as a fixed-label ARIA toggle');
  assert.equal(timerStarts > 0, !initialReduced, 'Autoplay timer must honour reduced motion');
  assert.equal(observedHero, hero, 'Hero is watched for offscreen pause');
  if (!initialReduced) {
    // A zero-pixel edge contact must not restart a slideshow offscreen.
    observerCallback([{ target: hero, isIntersecting: false, intersectionRatio: 0 }]);
    const beforeEdge = timerStarts;
    observerCallback([{ target: hero, isIntersecting: true, intersectionRatio: 0 }]);
    assert.equal(timerStarts, beforeEdge, 'Edge-only intersection must remain paused');
    observerCallback([{ target: hero, isIntersecting: true, intersectionRatio: 0.5 }]);
    assert.equal(timerStarts, beforeEdge + 1, 'Visible pixels may resume autoplay');
    const running = timerStarts;
    hero.handlers.mouseenter();
    assert.equal(toggle.textContent, 'Play slideshow', 'Hover exposes explicit Play control');
    toggle.handlers.click();
    assert.equal(timerStarts, running + 1,
      'Explicit Play must work while the pointer is still over the control');
    assert.equal(toggle.textContent, 'Pause slideshow',
      'A running carousel must not advertise an ineffective Play/Pause action');
    toggle.handlers.click();
    hero.handlers.mouseleave();
    assert.equal(timerStarts, running + 1, 'Leaving hover must not restart a visitor-paused carousel');
    toggle.handlers.click();
    assert.equal(timerStarts, running + 2, 'Explicit Play resumes after hover');
    hero.handlers.focusin();
    assert.equal(toggle.textContent, 'Play slideshow', 'Keyboard focus pauses autoplay');
    toggle.handlers.click();
    assert.equal(timerStarts, running + 3,
      'Explicit Play must work while the control still has keyboard focus');
    toggle.handlers.click();
    hero.handlers.focusout({ relatedTarget: null });
    assert.equal(timerStarts, running + 3, 'Leaving keyboard focus must not restart rotation');
    toggle.handlers.click();
    assert.equal(timerStarts, running + 4, 'Explicit Play resumes after keyboard focus');
  }
  const startsBeforeOffscreen = timerStarts;
  const stopsBeforeOffscreen = timerStops;
  observerCallback([{ target: hero, isIntersecting: false, intersectionRatio: 0 }]);
  assert.equal(timerStarts, startsBeforeOffscreen, 'Offscreen hero cannot start another timer');
  assert.equal(timerStops > stopsBeforeOffscreen, !initialReduced, 'Offscreen hero clears an active timer');
  next.handlers.click();
  assert.equal(status.textContent, 'Photo 2 of 4: Image 2', 'Manual Next announces the selected photo');
  assert.equal(slides[1].active, true, 'Manual navigation still works while offscreen');
  assert.equal(timerStarts, startsBeforeOffscreen, 'Offscreen manual navigation does not restart autoplay');
  previous.handlers.click();
  assert.equal(status.textContent, 'Photo 1 of 4: Image 1', 'Manual Previous announces the selected photo');
  observerCallback([{ target: {}, isIntersecting: true, intersectionRatio: 0.5 }]);
  assert.equal(timerStarts, startsBeforeOffscreen, 'Unrelated observer entries cannot restart autoplay');
  // A real, nonzero intersection can restore visibility, but must never
  // override a manual pause after photo selection.
  observerCallback([{ target: hero, isIntersecting: true, intersectionRatio: 0.5 }]);
  assert.equal(timerStarts, startsBeforeOffscreen,
    'Returning onscreen must not override a manual photo selection');
  if (!initialReduced) {
    assert.equal(toggle.textContent, 'Play slideshow', 'Manual navigation leaves an explicit resume control');
    toggle.handlers.click();
    assert.ok(timerStarts > startsBeforeOffscreen, 'Only explicit Play resumes manual navigation');
  }
  assert.equal(slides[0].active, true, 'First image must be visible');
  next.handlers.click();
  assert.equal(slides[1].active, true, 'Manual Next works without autoplay');
  previous.handlers.click();
  assert.equal(slides[0].active, true, 'Manual Previous works without autoplay');
  if (!initialReduced && !failImages) {
    toggle.handlers.click(); // Explicitly resume after the second manual selection.
    const lastAnnouncement = status.textContent;
    lastTimerCallback();
    assert.equal(slides[1].active, true, 'Automatic rotation still changes the visible frame');
    assert.equal(status.textContent, lastAnnouncement, 'Automatic rotation must not interrupt screen readers');
    previous.handlers.click();
  }
  if (failImages) {
    slides[0].image.handlers.error();
    assert.equal(status.textContent, '', 'Failed photos clear any stale announcement');
    assert.equal(slides[0].removed, true, 'Broken first photo is removed');
    assert.equal(slides[1].active, true, 'Next available photo becomes active');
    assert.equal(controls.hidden, false, 'Two or more photos retain controls');
    slides[1].image.handlers.error();
    slides[2].image.handlers.error();
    assert.equal(controls.hidden, true, 'One photo hides unnecessary controls');
    assert.equal(toggle.disabled, true, 'Single remaining photo cannot autoplay');
    slides[3].image.handlers.error();
    assert.equal(heroFlags.has('ezb-cinema--missing-media'), true, 'All failed photos reveal safe text hero');
    assert.equal(controls.hidden, true, 'No photos leaves controls hidden');
    return;
  }
  media.matches = !initialReduced;
  media.change();
  assert.equal(toggle.disabled, !initialReduced, 'Control must react to live preference changes');
  if (initialReduced) {
    assert.equal(timerStarts, 0, 'Manual selection while reduced motion must not auto-resume');
    toggle.handlers.click();
    assert.ok(timerStarts > 0, 'Explicit Play can resume after reduced motion is lifted');
  }
}
exerciseMotionPreference(true);
exerciseMotionPreference(false);
exerciseMotionPreference(false, true);
exerciseMotionPreference(false, false, true);
console.log('EZB_EDITORIAL_MOTION_RUNTIME_PASS cases=4');

console.log('EZB_EDITORIAL_ART_DIRECTION_TEST_PASS checks=' + (required.length + 4));
