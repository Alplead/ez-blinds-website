(function () {
	'use strict';

	// The server still validates contact details; catch the common missing
	// contact method before navigation so visitors do not lose their message.
	// Run independently of motion settings and fail open if markup changes.
	document.querySelectorAll('.ezb-quote-form').forEach(function (form) {
		var phone = form.querySelector('input[name="phone"]');
		var email = form.querySelector('input[name="email"]');
		if (!phone || !email || typeof phone.setCustomValidity !== 'function') return;

		function clearContactError() {
			phone.setCustomValidity('');
			phone.removeAttribute('aria-invalid');
		}

		phone.addEventListener('input', clearContactError);
		email.addEventListener('input', clearContactError);
		form.addEventListener('submit', function (event) {
			clearContactError();
			if (phone.value.trim() || email.value.trim()) return;
			phone.setCustomValidity('Please enter a phone number or email address so we can reply.');
			phone.setAttribute('aria-invalid', 'true');
			event.preventDefault();
			phone.focus();
			phone.reportValidity();
		});
	});


	var motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
	var videos = document.querySelectorAll('[data-ezb-autoplay-video]');

	// A visitor who paused the native video controls must not have playback
	// restarted merely by switching tabs or changing motion preferences.
	// Capture eligibility only on the first interruption, before our own pause.
	var videosInitialised = false;
	var videosSuspended = false;
	var resumeEligible = new WeakMap();
	videos.forEach(function (video) { resumeEligible.set(video, true); });

	function stopAutoplayVideos() {
		if (videosInitialised && !videosSuspended) {
			videos.forEach(function (video) {
				resumeEligible.set(video, video.paused === false);
			});
		}
		videosSuspended = true;
		videos.forEach(function (video) {
			video.autoplay = false;
			video.pause();
		});
	}

	// Never autoplay from HTML before reduced-motion preference is known.
	function startAutoplayVideos() {
		// A background tab must not start or resume autoplay.
		if (document.hidden) {
			stopAutoplayVideos();
			return;
		}
		if (videosInitialised && !videosSuspended) return;
		videosInitialised = true;
		videosSuspended = false;
		videos.forEach(function (video) {
			if (!resumeEligible.get(video)) return;
			video.autoplay = true;
			if (typeof video.play !== 'function') return;
			try {
				var attempt = video.play();
				if (attempt && typeof attempt.catch === 'function') {
					attempt.catch(function () { video.autoplay = false; });
				}
			} catch (_error) {
				video.autoplay = false;
			}
		});
	}

	// Motion preferences may change after page load. Initialise the scroll
	// reveal observer only when first needed, never twice after toggling.
	var targets = document.querySelectorAll([
		'.ezb-card', '.ezb-proof', '.ezb-cta', '.ezb-product-media',
		'.ezb-media-placeholder', '.ezb-map-placeholder', '.ezb-contact-aside',
		'.ezb-split-panel', '.ezb-blog-card', '.ezb-project-gallery',
		'.ezb-product-gallery-block'
	].join(','));
	var revealsInitialised = false;

	function initialiseReveals() {
		if (revealsInitialised) return;
		revealsInitialised = true;
		if (!('IntersectionObserver' in window)) {
			targets.forEach(function (el) { el.classList.add('ezb-in-view'); });
			return;
		}
		var observer = new IntersectionObserver(function (entries, obs) {
			entries.forEach(function (entry) {
				if (!entry.isIntersecting) return;
				entry.target.classList.add('ezb-in-view');
				obs.unobserve(entry.target);
			});
		}, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
		targets.forEach(function (el, index) {
			el.style.setProperty('--ezb-reveal-delay', Math.min(index % 3, 2) * 55 + 'ms');
			observer.observe(el);
		});
	}

	function syncMotionPreference() {
		if (motionPreference.matches) {
			stopAutoplayVideos();
			// Removing the motion class immediately reveals all content,
			// including items that have not yet entered the viewport.
			document.documentElement.classList.remove('ezb-motion-ready');
			return;
		}
		startAutoplayVideos();
		initialiseReveals();
		document.documentElement.classList.add('ezb-motion-ready');
	}

	// A hidden tab never resumes autoplay, even after a preference change.
	if (videos.length && typeof document.addEventListener === 'function') {
		document.addEventListener('visibilitychange', function () {
			if (document.hidden || motionPreference.matches) {
				stopAutoplayVideos();
			} else {
				startAutoplayVideos();
			}
		});
	}
	if (motionPreference.addEventListener) {
		motionPreference.addEventListener('change', syncMotionPreference);
	} else if (motionPreference.addListener) {
		motionPreference.addListener(syncMotionPreference);
	}
	syncMotionPreference();
}());
