(function () {
	'use strict';

	var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

	document.querySelectorAll('[data-ezb-autoplay-video]').forEach(function (video) {
		if (reduceMotion) {
			video.autoplay = false;
			video.pause();
		}
	});

	if (reduceMotion) {
		return;
	}

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
