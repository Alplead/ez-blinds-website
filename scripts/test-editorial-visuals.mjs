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
function exerciseMotionPreference(initialReduced, failImages = false, missingImage = false, initialFocused = true, initialSlideCount = 4, initialHover = false, initialFocusWithin = false, initialSaveData = false) {
  const media = { matches: initialReduced, addEventListener(_event, callback) { this.change = callback; } };
  const connection = { saveData: initialSaveData, addEventListener(event, callback) {
    assert.equal(event, 'change'); this.change = callback;
  } };
  const control = () => ({
    disabled: false, textContent: '', handlers: {}, attributes: {},
    addEventListener(event, callback) { this.handlers[event] = callback; },
    setAttribute(name, value) { this.attributes[name] = value; }
  });
  const toggle = control();
  const previous = control();
  const next = control();
  const status = { textContent: '' };
  const progress = { textContent: '' };
  const slides = Array.from({ length: initialSlideCount }, (_, position) => {
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
  const controls = {
    hidden: false, handlers: {},
    addEventListener(event, callback) { this.handlers[event] = callback; }
  };
  const heroFlags = new Set();
  const selectors = {
    '[data-ezb-toggle]': toggle, '[data-ezb-prev]': previous, '[data-ezb-next]': next,
    '.ezb-cinema__controls': controls, '[data-ezb-announcement]': status,
    '[data-ezb-progress]': progress
  };
  const hero = {
    querySelectorAll() { return slides; },
    querySelector(selector) { return selectors[selector] || null; },
    classList: { toggle() {}, add(name) { heroFlags.add(name); } },
    handlers: {},
    addEventListener(event, callback) { this.handlers[event] = callback; },
    contains(target) { return initialFocusWithin && target === toggle; },
    matches(selector) { assert.equal(selector, ':hover'); return initialHover; }
  };
  let timerStarts = 0;
  let timerStops = 0;
  let lastTimerCallback = null;
  let observerCallback = null;
  let observedHero = null;
  const lifecycle = {};
  const window = {
    navigator: { connection },
    matchMedia() { return media; },
    addEventListener(event, callback) { lifecycle[event] = callback; },
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
    hidden: false, activeElement: initialFocusWithin ? toggle : null,
    hasFocus() { return initialFocused; }, querySelector() { return hero; },
    querySelectorAll() { return []; },
    addEventListener(event, callback) {
      if (event === 'visibilitychange') this.visibility = callback;
    }
  };
  runInNewContext(js, { window, document });
  if (initialSlideCount < 2) {
    assert.equal(controls.hidden, true, 'Zero or one photo cannot expose slideshow controls');
    assert.equal(timerStarts, 0, 'Zero or one photo cannot start autoplay');
    assert.equal(toggle.disabled, true, 'Zero or one photo disables autoplay');
    if (initialSlideCount === 0) {
      assert.equal(heroFlags.has('ezb-cinema--missing-media'), true,
        'Empty initial photo collection must reveal safe text fallback');
      assert.equal(progress.textContent, '', 'Empty initial carousel has no photo counter');
    } else {
      assert.equal(slides[0].active, true, 'Single photo remains visible');
      assert.equal(progress.textContent, '01 / 01', 'Single photo counter remains accurate');
    }
    return;
  }
  if (initialHover || initialFocusWithin) {
    assert.equal(timerStarts, 0, 'Existing hover or keyboard focus must block initial autoplay');
    assert.equal(toggle.textContent, 'Play slideshow', 'Visitor interaction initially offers Play');
    if (initialHover) hero.handlers.mouseleave();
    if (initialFocusWithin) hero.handlers.focusout({ relatedTarget: null });
    assert.equal(timerStarts, initialReduced ? 0 : 1,
      'Autoplay may resume only after the initial interaction ends');
    return;
  }
  if (!initialFocused) {
    assert.equal(timerStarts, 0, 'An initially unfocused browser must not start autoplay');
    assert.equal(toggle.textContent, 'Play slideshow', 'Initially unfocused window offers Play');
    lifecycle.focus();
    assert.equal(timerStarts, 1, 'First window focus may start eligible autoplay');
    return;
  }
  if (missingImage) {
    assert.equal(slides[0].removed, true, 'Empty slide markup is discarded');
    assert.equal(slides[1].active, true, 'First valid image is shown');
    assert.equal(timerStarts, 1, 'Autoplay still works with three valid slides');
    return;
  }
  if (initialSaveData) {
    assert.equal(toggle.disabled, true, 'Save-Data disables automatic rotation');
    assert.equal(timerStarts, 0, 'Save-Data must not start a timer');
    assert.equal(slides[1].image.loading, 'lazy', 'Save-Data must not eager-load next photo');
    next.handlers.click();
    assert.equal(slides[1].active, true, 'Save-Data still permits manual navigation');
    assert.equal(slides[2].image.loading, 'lazy', 'Manual navigation must not prefetch under Save-Data');
    connection.saveData = false;
    connection.change();
    assert.equal(toggle.disabled, false, 'Disabling Save-Data restores Play control');
    assert.equal(timerStarts, 0, 'A prior manual selection remains paused');
    toggle.handlers.click();
    assert.equal(timerStarts, 1, 'Explicit Play resumes when Save-Data is off');
    connection.saveData = true;
    connection.change();
    assert.equal(timerStops, 1, 'Re-enabling Save-Data stops a running timer');
    assert.equal(toggle.disabled, true, 'Re-enabling Save-Data disables Play');
    return;
  }
  assert.equal(toggle.disabled, initialReduced, 'Initial autoplay button must reflect motion preference');
  assert.equal(toggle.attributes['aria-pressed'], undefined,
    'Play/Pause action labels must not masquerade as a fixed-label ARIA toggle');
  assert.equal(timerStarts > 0, !initialReduced, 'Autoplay timer must honour reduced motion');
  assert.equal(observedHero, hero, 'Hero is watched for offscreen pause');
  // Duplicate visibility/intersection/preference events must not restart the
  // 7.7-second countdown while the same slide is already playing.
  const startsBeforeRepeatedEvents = timerStarts;
  const stopsBeforeRepeatedEvents = timerStops;
  observerCallback([{ target: hero, isIntersecting: true, intersectionRatio: 0.75 }]);
  observerCallback([{ target: hero, isIntersecting: true, intersectionRatio: 0.5 }]);
  document.visibility();
  media.change();
  assert.equal(timerStarts, startsBeforeRepeatedEvents,
    'Repeated visible-state notifications must not restart the slide interval');
  assert.equal(timerStops, stopsBeforeRepeatedEvents,
    'Repeated visible-state notifications must not cancel the slide interval');
  // BFCache navigation must pause the timer and preserve the motion gate.
  const startsBeforePagehide = timerStarts;
  const stopsBeforePagehide = timerStops;
  lifecycle.pagehide();
  lifecycle.pagehide();
  assert.equal(timerStarts, startsBeforePagehide, 'pagehide cannot start autoplay');
  assert.equal(timerStops, stopsBeforePagehide + (initialReduced ? 0 : 1),
    'repeated pagehide stops the interval only once');
  lifecycle.pageshow();
  assert.equal(timerStarts, startsBeforePagehide + (initialReduced ? 0 : 1),
    'pageshow resumes only if motion is permitted');
  if (!initialReduced) {
    lifecycle.pagehide();
    document.hidden = true;
    lifecycle.pageshow();
    assert.equal(timerStarts, startsBeforePagehide + 1,
      'pageshow cannot resume autoplay in a background tab');
    document.hidden = false;
    document.visibility();
    assert.equal(timerStarts, startsBeforePagehide + 2,
      'visible eligible page may resume autoplay');
    // A browser window can lose focus while its tab remains visible. Pause
    // once and resume only when focus returns, without resetting the timer
    // on duplicate blur/focus notifications.
    const startsBeforeBlur = timerStarts;
    const stopsBeforeBlur = timerStops;
    lifecycle.blur();
    lifecycle.blur();
    assert.equal(timerStops, stopsBeforeBlur + 1,
      'unfocused window suspends an active slideshow exactly once');
    assert.equal(toggle.textContent, 'Play slideshow',
      'unfocused window offers Play rather than an ineffective Pause');
    lifecycle.focus();
    lifecycle.focus();
    assert.equal(timerStarts, startsBeforeBlur + 1,
      'returning window focus resumes once without duplicating timers');
    document.hidden = true;
    document.visibility();
    const startsWhileHidden = timerStarts;
    lifecycle.blur();
    lifecycle.focus();
    assert.equal(timerStarts, startsWhileHidden,
      'focus must not restart autoplay in a hidden tab');
    document.hidden = false;
    document.visibility();
    assert.equal(timerStarts, startsWhileHidden + 1,
      'visible, focused window can resume after tab becomes active');
  }
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
    assert.equal(toggle.textContent, 'Play slideshow', 'Hover temporarily pauses rotation');
    hero.handlers.mouseleave();
    assert.equal(timerStarts, running + 1,
      'Simply moving the pointer away must resume automatic rotation');
    hero.handlers.mouseenter();
    toggle.handlers.click();
    assert.equal(timerStarts, running + 2,
      'Explicit Play must work while the pointer is still over the control');
    assert.equal(toggle.textContent, 'Pause slideshow',
      'A running carousel must offer an effective Pause action');
    toggle.handlers.click();
    hero.handlers.mouseleave();
    assert.equal(timerStarts, running + 2,
      'A deliberate Pause must survive leaving hover');
    lifecycle.blur();
    lifecycle.focus();
    assert.equal(timerStarts, running + 2,
      'A deliberate Pause must survive browser blur and refocus');
    toggle.handlers.click();
    assert.equal(timerStarts, running + 3, 'Explicit Play resumes after manual pause');
    hero.handlers.focusin();
    assert.equal(toggle.textContent, 'Play slideshow', 'Keyboard focus temporarily pauses rotation');
    hero.handlers.focusout({ relatedTarget: null });
    assert.equal(timerStarts, running + 4,
      'Leaving keyboard focus without manual action resumes rotation');
    hero.handlers.focusin();
    toggle.handlers.click();
    assert.equal(timerStarts, running + 5,
      'Explicit Play must work while the control still has keyboard focus');
    toggle.handlers.click();
    hero.handlers.focusout({ relatedTarget: null });
    assert.equal(timerStarts, running + 5,
      'A deliberate keyboard Pause must survive leaving focus');
    toggle.handlers.click();
    assert.equal(timerStarts, running + 6, 'Explicit Play resumes after keyboard pause');
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
    assert.equal(progress.textContent, '', 'Last broken image clears stale photo counter');
    assert.equal(toggle.disabled, true, 'No remaining photo disables autoplay');
    let prevented = false;
    controls.handlers.keydown({ key: 'ArrowRight', target: next, preventDefault() { prevented = true; } });
    assert.equal(prevented, false, 'Empty slideshow never captures arrow keys');
    return;
  }
  // Keyboard arrows only work on the actual slideshow buttons, keep focus
  // in place, announce deliberate changes and never override reduced motion.
  const press = (key, target = next, modifiers = {}) => {
    let prevented = 0;
    controls.handlers.keydown({ key, target, ...modifiers, preventDefault() { prevented++; } });
    return prevented;
  };
  const beforeKeyboard = timerStarts;
  assert.equal(press('ArrowRight', {}), 0, 'unrelated targets cannot hijack page arrows');
  assert.equal(press('ArrowRight', next, { ctrlKey: true }), 0, 'modified shortcuts remain untouched');
  assert.equal(press('ArrowLeft', previous, { shiftKey: true }), 0, 'selection shortcuts remain untouched');
  assert.equal(press('ArrowRight', next), 1, 'Right arrow on Next is handled');
  assert.equal(slides[1].active, true, 'Right arrow selects the next photo');
  assert.equal(status.textContent, 'Photo 2 of 4: Image 2', 'Keyboard selection is announced');
  assert.equal(press('ArrowLeft', previous), 1, 'Left arrow on Previous is handled');
  assert.equal(slides[0].active, true, 'Left arrow selects the previous photo');
  assert.equal(press('End', {}), 0, 'Home/End cannot hijack unrelated page controls');
  assert.equal(press('End', next, { metaKey: true }), 0, 'modified End stays with the browser');
  assert.equal(press('End', toggle), 1, 'End on a carousel control selects the last photo');
  assert.equal(slides[3].active, true, 'End selects the last photo');
  assert.equal(status.textContent, 'Photo 4 of 4: Image 4', 'End announces the selected photo');
  assert.equal(press('Home', previous), 1, 'Home on a carousel control selects the first photo');
  assert.equal(slides[0].active, true, 'Home selects the first photo');
  assert.equal(status.textContent, 'Photo 1 of 4: Image 1', 'Home announces the selected photo');
  assert.equal(timerStarts, beforeKeyboard, 'Keyboard selection must not restart autoplay');
  assert.equal(toggle.textContent, initialReduced ? 'Automatic slideshow unavailable' : 'Play slideshow',
    'Manual keyboard navigation never bypasses reduced motion or pause');
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
exerciseMotionPreference(false, false, false, false);
exerciseMotionPreference(false, false, false, true, 0);
exerciseMotionPreference(false, false, false, true, 1);
exerciseMotionPreference(false, false, false, true, 4, true, false);
exerciseMotionPreference(false, false, false, true, 4, false, true);
exerciseMotionPreference(false, false, false, true, 4, true, true);
exerciseMotionPreference(false, false, false, true, 4, false, false, true);
// Older Safari exposes MediaQueryList.addListener but not addEventListener.
// A live preference or viewport-width change must reset a previously applied
// depth offset; otherwise reduced-motion users retain a moving backdrop.
function exerciseLegacyBandMediaQueries() {
  const offsets = [];
  const band = {
    style: { setProperty(key, value) {
      assert.equal(key, '--ezb-photo-offset');
      offsets.push(value);
    } },
    getBoundingClientRect() { return { top: 100, bottom: 500, height: 400 }; }
  };
  const reducedQuery = { matches: false, addListener(callback) { this.notify = callback; } };
  const compactQuery = { matches: false, addListener(callback) { this.notify = callback; } };
  const window = {
    innerHeight: 800,
    matchMedia(query) {
      return query === '(prefers-reduced-motion: reduce)' ? reducedQuery : compactQuery;
    },
    addEventListener() {},
    requestAnimationFrame(callback) { callback(); }
  };
  const document = {
    querySelector() { return null; },
    querySelectorAll(selector) { return selector === '[data-ezb-editorial-band]' ? [band] : []; }
  };
  runInNewContext(js, { window, document });
  assert.equal(offsets.at(-1), '3px', 'desktop depth starts at the calculated offset');
  assert.equal(typeof reducedQuery.notify, 'function', 'legacy reduced-motion listener is attached');
  assert.equal(typeof compactQuery.notify, 'function', 'legacy compact-width listener is attached');
  compactQuery.matches = true;
  compactQuery.notify();
  assert.equal(offsets.at(-1), '0px', 'compact viewport clears existing parallax');
  compactQuery.matches = false;
  compactQuery.notify();
  assert.equal(offsets.at(-1), '3px', 'desktop viewport can restore subtle depth');
  reducedQuery.matches = true;
  reducedQuery.notify();
  assert.equal(offsets.at(-1), '0px', 'reduced motion clears existing parallax');
  reducedQuery.matches = false;
  reducedQuery.notify();
  assert.equal(offsets.at(-1), '3px', 're-enabling motion restores normal depth');
}
exerciseLegacyBandMediaQueries();

console.log('EZB_EDITORIAL_MOTION_RUNTIME_PASS cases=12');

console.log('EZB_EDITORIAL_ART_DIRECTION_TEST_PASS checks=' + (required.length + 4));
