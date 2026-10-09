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
		}

		phone.addEventListener('input', clearContactError);
		email.addEventListener('input', clearContactError);
		form.addEventListener('submit', function (event) {
			clearContactError();
			if (phone.value.trim() || email.value.trim()) return;
			phone.setCustomValidity('Please enter a phone number or email address so we can reply.');
			event.preventDefault();
			phone.reportValidity();
		});
	});


	var motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
	var videos = document.querySelectorAll('[data-ezb-autoplay-video]');

	function stopAutoplayVideos() {
		videos.forEach(function (video) {
			video.autoplay = false;
			video.pause();
		});
	}

	// Never autoplay from HTML before reduced-motion preference is known.
	function startAutoplayVideos() {
		videos.forEach(function (video) {
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

	function onMotionPreferenceChange(event) {
		if (!event.matches) {
			startAutoplayVideos();
			return;
		}
		stopAutoplayVideos();
		// Reveal all animated items when reduced motion is enabled mid-session.
		document.documentElement.classList.remove('ezb-motion-ready');
	}

	if (motionPreference.addEventListener) {
		motionPreference.addEventListener('change', onMotionPreferenceChange);
	} else if (motionPreference.addListener) {
		motionPreference.addListener(onMotionPreferenceChange);
	}

	if (motionPreference.matches) {
		stopAutoplayVideos();
		return;
	}

	startAutoplayVideos();
	document.documentElement.classList.add('ezb-motion-ready');

	var targets = document.querySelectorAll([
		'.ezb-card',
		'.ezb-proof',
		'.ezb-cta',
		'.ezb-product-media',
		'.ezb-media-placeholder',
		'.ezb-map-placeholder',
		'.ezb-contact-aside',
		'.ezb-split-panel',
		'.ezb-blog-card',
		'.ezb-project-gallery',
		'.ezb-product-gallery-block'
	].join(','));

	if (!('IntersectionObserver' in window)) {
		targets.forEach(function (el) {
			el.classList.add('ezb-in-view');
		});
		return;
	}

	var observer = new IntersectionObserver(function (entries, obs) {
		entries.forEach(function (entry) {
			if (!entry.isIntersecting) return;
			entry.target.classList.add('ezb-in-view');
			obs.unobserve(entry.target);
		});
	}, {
		rootMargin: '0px 0px -8% 0px',
		threshold: 0.08
	});

	targets.forEach(function (el, index) {
		el.style.setProperty('--ezb-reveal-delay', Math.min(index % 3, 2) * 55 + 'ms');
		observer.observe(el);
	});
}());
