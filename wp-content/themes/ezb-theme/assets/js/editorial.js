/* EZB editorial motion. No third-party slider or remote media dependencies. */
(function () {
  'use strict';

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  var hero = document.querySelector('[data-ezb-cinema]');
  var bands = Array.prototype.slice.call(document.querySelectorAll('[data-ezb-editorial-band]'));

  if (hero) {
    var slides = Array.prototype.slice.call(hero.querySelectorAll('[data-ezb-slide]'));
    var progress = hero.querySelector('[data-ezb-progress]');
    var previous = hero.querySelector('[data-ezb-prev]');
    var next = hero.querySelector('[data-ezb-next]');
    var toggle = hero.querySelector('[data-ezb-toggle]');
    var announcement = hero.querySelector('[data-ezb-announcement]');
    var current = 0;
    var interval = null;
    var paused = false;
    // Explicit Play overrides the hover/focus pause for this interaction.
    // Without this, clicking Play with the pointer or focus still on the
    // control misleadingly labels it Pause while no timer can start.
    var explicitPlay = false;
    // Deferred scripts may run after a visitor has already hovered or
    // focused the hero. Do not start autoplay underneath that interaction.
    var hovering = typeof hero.matches === 'function' && hero.matches(':hover');
    var focusing = !!document.activeElement && hero.contains(document.activeElement);
    var inView = true;
    var pageSuspended = false;
    // A visible tab can belong to an unfocused browser window. Suspend the
    // timer until focus returns, without overriding a deliberate Pause.
    var windowFocused = typeof document.hasFocus === 'function' ? document.hasFocus() : true;
    var initialising = true;
    var intervalMs = 7700; // four images rotate once in about 31 seconds.

    // WordPress may still return markup for a missing media file. Fail closed
    // on actual browser load errors rather than cycling through blank frames.
    function discardFailedSlide(slide) {
      var index = slides.indexOf(slide);
      if (index < 0) return;
      slides.splice(index, 1);
      slide.remove();
      if (index < current) current -= 1;
      if (current >= slides.length) current = 0;
      if (announcement) announcement.textContent = '';
      if (!slides.length) {
        hero.classList.add('ezb-cinema--missing-media');
        // Do not leave a stale slide counter after the last image fails.
        if (progress) progress.textContent = '';
      }
      var controls = hero.querySelector('.ezb-cinema__controls');
      if (controls) controls.hidden = slides.length < 2;
      if (!initialising) {
        showSlide(current);
        syncTimer();
      }
    }

    function showSlide(index, announce) {
      if (!slides.length) return;
      current = (index + slides.length) % slides.length;
      // Preload the next photo while the current frame is still on screen.
      var upcoming = slides[(current + 1) % slides.length].querySelector('img');
      if (upcoming && upcoming.loading === 'lazy') upcoming.loading = 'eager';
      slides.forEach(function (slide, position) {
        var active = position === current;
        slide.classList.toggle('is-active', active);
        slide.setAttribute('aria-hidden', active ? 'false' : 'true');
      });
      if (progress) {
        progress.textContent = String(current + 1).padStart(2, '0') +
          ' / ' + String(slides.length).padStart(2, '0');
      }
      // Only keyboard/button navigation speaks: automatic rotation stays quiet.
      if (announce && announcement) {
        var caption = slides[current].querySelector('.ezb-cinema__slide-label');
        announcement.textContent = 'Photo ' + (current + 1) + ' of ' + slides.length +
          (caption && caption.textContent ? ': ' + caption.textContent.trim() : '');
      }
    }

    function stopTimer() {
      if (interval !== null) {
        window.clearInterval(interval);
        interval = null;
      }
    }

    function shouldStop() {
      return slides.length < 2 || paused ||
        ((hovering || focusing) && !explicitPlay) ||
        reduced.matches || document.hidden || pageSuspended || !inView || !windowFocused;
    }

    function syncTimer() {
      // IntersectionObserver, visibility and preference events can repeat
      // without a state change. Keep the running interval in that case:
      // resetting it on every event can postpone the next photo indefinitely.
      var stopped = shouldStop();
      if (stopped) {
        stopTimer();
      } else if (interval === null) {
        interval = window.setInterval(function () { showSlide(current + 1); }, intervalMs);
      }
      hero.classList.toggle('is-paused', stopped);
      if (toggle) {
        // Manual navigation remains available when autoplay is disallowed.
        var motionBlocked = reduced.matches || slides.length < 2;
        toggle.disabled = motionBlocked;
        // The action label changes between Play and Pause. This is not a
        // fixed-label ARIA toggle button, so aria-pressed must not be used.
        toggle.textContent = motionBlocked
          ? 'Automatic slideshow unavailable'
          : (stopped ? 'Play slideshow' : 'Pause slideshow');
      }
    }

    if (previous) previous.addEventListener('click', function () {
      // An intentional photo selection stops rotation until explicit Play.
      paused = true;
      explicitPlay = false;
      showSlide(current - 1, true);
      syncTimer();
    });
    if (next) next.addEventListener('click', function () {
      paused = true;
      explicitPlay = false;
      showSlide(current + 1, true);
      syncTimer();
    });
    if (toggle) toggle.addEventListener('click', function () {
      if (reduced.matches || slides.length < 2) return;
      // Hover/focus is temporary: Play resumes without first setting Pause.
      // Only deliberate Pause and manual photo selection persist.
      var stopped = shouldStop();
      paused = !stopped;
      explicitPlay = stopped;
      syncTimer();
    });

    hero.addEventListener('mouseenter', function () {
      if (!hovering && !focusing) explicitPlay = false;
      hovering = true;
      syncTimer();
    });
    hero.addEventListener('mouseleave', function () {
      hovering = false;
      if (!focusing) explicitPlay = false;
      syncTimer();
    });
    hero.addEventListener('focusin', function () {
      if (!focusing && !hovering) explicitPlay = false;
      focusing = true;
      syncTimer();
    });
    // Hover/focus temporarily suspends rotation; only a deliberate visitor
    // pause persists after leaving. Explicit Play overrides the active pause.
    hero.addEventListener('focusout', function (event) {
      if (!hero.contains(event.relatedTarget)) {
        focusing = false;
        if (!hovering) explicitPlay = false;
        syncTimer();
      }
    });
    // Keep offscreen slides still. Manual navigation remains available, and
    // browsers without IntersectionObserver keep the existing fallback.
    if ('IntersectionObserver' in window) {
      var observer = new window.IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.target !== hero) return;
          // IntersectionObserver can report isIntersecting=true when only
          // the edge touches the viewport (zero visible pixels).
          inView = entry.isIntersecting && entry.intersectionRatio > 0;
          syncTimer();
        });
      }, { threshold: 0 });
      observer.observe(hero);
    }
    // BFCache can suspend a page without a visibilitychange event.
    window.addEventListener('pagehide', function () {
      pageSuspended = true;
      syncTimer();
    });
    window.addEventListener('pageshow', function () {
      pageSuspended = false;
      syncTimer();
    });
    window.addEventListener('blur', function () {
      windowFocused = false;
      syncTimer();
    });
    window.addEventListener('focus', function () {
      windowFocused = true;
      syncTimer();
    });
    document.addEventListener('visibilitychange', syncTimer);
    if (reduced.addEventListener) {
      reduced.addEventListener('change', syncTimer);
    } else if (reduced.addListener) {
      reduced.addListener(syncTimer);
    }
    // Server-rendered controls normally exist only with multiple images,
    // but an empty/one-photo DOM can also arrive after client-side changes.
    // Keep the fallback and controls correct before image error listeners run.
    var initialControls = hero.querySelector('.ezb-cinema__controls');
    if (initialControls) initialControls.hidden = slides.length < 2;
    // Carousel controls support arrows plus Home/End for first/last photo.
    // Never capture shortcuts outside these buttons, or modified keys used
    // for browser navigation. Manual selection persists until explicit Play.
    if (initialControls) initialControls.addEventListener('keydown', function (event) {
      var key = event.key;
      if (slides.length < 2 ||
          (key !== 'ArrowLeft' && key !== 'ArrowRight' && key !== 'Home' && key !== 'End') ||
          event.altKey || event.ctrlKey || event.metaKey || event.shiftKey ||
          (event.target !== previous && event.target !== next && event.target !== toggle)) return;
      event.preventDefault();
      paused = true;
      explicitPlay = false;
      var destination = key === 'Home' ? 0 :
        (key === 'End' ? slides.length - 1 : current + (key === 'ArrowRight' ? 1 : -1));
      showSlide(destination, true);
      syncTimer();
    });
    if (!slides.length) hero.classList.add('ezb-cinema--missing-media');
    slides.slice().forEach(function (slide) {
      var image = slide.querySelector('img');
      if (!image) { discardFailedSlide(slide); return; }
      image.addEventListener('error', function () { discardFailedSlide(slide); });
      // An image can fail before this deferred script attaches its listener.
      if (image.complete && image.naturalWidth === 0) discardFailedSlide(slide);
    });
    initialising = false;
    showSlide(current);
    syncTimer();
  }

  // Subtle depth follows the visible sections rather than scrolling a huge
  // background image in fixed-position mode; disabled for reduced motion/mobile.
  if (!bands.length) return;

  var compact = window.matchMedia('(max-width: 780px)');
  var scheduled = false;
  function updateBands() {
    scheduled = false;
    if (reduced.matches || compact.matches) {
      bands.forEach(function (band) {
        band.style.setProperty('--ezb-photo-offset', '0px');
      });
      return;
    }
    var viewport = window.innerHeight || 800;
    bands.forEach(function (band) {
      var bounds = band.getBoundingClientRect();
      if (bounds.bottom < 0 || bounds.top > viewport) return;
      var centreDistance = (viewport / 2 - (bounds.top + bounds.height / 2)) / viewport;
      var clamped = Math.max(-1, Math.min(1, centreDistance));
      band.style.setProperty('--ezb-photo-offset', Math.round(clamped * 24) + 'px');
    });
  }
  function requestUpdate() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(updateBands);
  }

  window.addEventListener('scroll', requestUpdate, { passive: true });
  window.addEventListener('resize', requestUpdate, { passive: true });
  // Legacy MediaQueryList implementations (including older Safari) only
  // expose addListener. Without this fallback, toggling reduced motion or
  // entering mobile width can leave a stale parallax offset on the page.
  function onMediaChange(query) {
    if (typeof query.addEventListener === 'function') {
      query.addEventListener('change', requestUpdate);
    } else if (typeof query.addListener === 'function') {
      query.addListener(requestUpdate);
    }
  }
  onMediaChange(compact);
  onMediaChange(reduced);
  requestUpdate();
}());
