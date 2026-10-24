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
    var hovering = false;
    var focusing = false;
    var inView = true;
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
      if (!slides.length) hero.classList.add('ezb-cinema--missing-media');
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
      return slides.length < 2 || paused || hovering || focusing ||
        reduced.matches || document.hidden || !inView;
    }

    function syncTimer() {
      stopTimer();
      hero.classList.toggle('is-paused', shouldStop());
      if (!shouldStop()) {
        interval = window.setInterval(function () { showSlide(current + 1); }, intervalMs);
      }
      if (toggle) {
        // Manual navigation remains available when autoplay is disallowed.
        var motionBlocked = reduced.matches || slides.length < 2;
        toggle.disabled = motionBlocked;
        toggle.setAttribute('aria-pressed', paused ? 'true' : 'false');
        toggle.textContent = motionBlocked
          ? 'Automatic slideshow unavailable'
          : (paused ? 'Play slideshow' : 'Pause slideshow');
      }
    }

    if (previous) previous.addEventListener('click', function () {
      showSlide(current - 1, true);
      syncTimer();
    });
    if (next) next.addEventListener('click', function () {
      showSlide(current + 1, true);
      syncTimer();
    });
    if (toggle) toggle.addEventListener('click', function () {
      paused = !paused;
      syncTimer();
    });

    hero.addEventListener('mouseenter', function () { hovering = true; syncTimer(); });
    hero.addEventListener('mouseleave', function () { hovering = false; syncTimer(); });
    hero.addEventListener('focusin', function () { focusing = true; syncTimer(); });
    hero.addEventListener('focusout', function (event) {
      if (!hero.contains(event.relatedTarget)) {
        focusing = false;
        syncTimer();
      }
    });
    // Keep offscreen slides still. Manual navigation remains available, and
    // browsers without IntersectionObserver keep the existing fallback.
    if ('IntersectionObserver' in window) {
      var observer = new window.IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.target !== hero) return;
          inView = entry.isIntersecting;
          syncTimer();
        });
      }, { threshold: 0 });
      observer.observe(hero);
    }
    document.addEventListener('visibilitychange', syncTimer);
    if (reduced.addEventListener) {
      reduced.addEventListener('change', syncTimer);
    } else if (reduced.addListener) {
      reduced.addListener(syncTimer);
    }
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
  if (compact.addEventListener) compact.addEventListener('change', requestUpdate);
  if (reduced.addEventListener) reduced.addEventListener('change', requestUpdate);
  requestUpdate();
}());
