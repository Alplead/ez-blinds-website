// Deterministic, browser-evidence-based guard for Owner preview screenshots.
// A 200 response, one H1 and no overflow are NOT sufficient proof of styled UI.
// A 200 response after a redirect can be a screenshot of the wrong page.
// Reject all redirects, even when the final URL looks like the requested route.
export function previewNavigationFailure(requestedUrl, finalUrl, redirected = false) {
  try {
    const requested = new URL(requestedUrl);
    const actual = new URL(finalUrl);
    if (redirected || actual.origin !== requested.origin ||
        actual.pathname !== requested.pathname ||
        actual.search !== requested.search || actual.hash !== requested.hash ||
        actual.username || actual.password) {
      // Avoid echoing Basic-auth userinfo, signed query strings or fragments in CI logs.
      return 'unexpected navigation (redirect, origin, route or URL credentials)';
    }
    return '';
  } catch {
    return 'invalid preview navigation URL';
  }
}

// A screenshot can appear correct even if one or more actual <img> assets fail.
export function previewImageFailures(images) {
  const failures = [];
  for (const [index, image] of images.entries()) {
    // Identify a broken image by DOM order, never by an untrusted URL that may
    // contain Basic-auth credentials, signed query parameters or private data.
    const label = `image ${index + 1}`;
    if (!image.src) {
      failures.push(`${label} has no resolved source`);
    } else if (!image.complete) {
      failures.push(`${label} did not finish loading`);
    } else if (!(image.naturalWidth > 0)) {
      failures.push(`broken ${label}`);
    } else if (image.hasAlt === false) {
      failures.push(`${label} missing alt attribute`);
    }
  }
  return failures;
}

export function previewRenderFailures(evidence, isHome = false) {
  const failures = [];
  if (evidence.themeStylesheetCount !== 1 ||
      evidence.themeStylesheetPath !== '/wp-content/themes/ezb-theme/style.css') {
    failures.push('EZB theme stylesheet must resolve from the site root');
  }
  if (!evidence.themeStylesheetLoaded) {
    failures.push('EZB theme stylesheet did not load in the browser');
  }
  if (!evidence.themeStylesheetSameOrigin) {
    failures.push('EZB theme stylesheet must be served from the preview origin');
  }
  if (evidence.themeScriptCount !== 1 ||
      evidence.themeScriptPath !== '/wp-content/themes/ezb-theme/assets/js/site.js') {
    failures.push('EZB theme script must resolve from the site root');
  }
  if (!evidence.themeScriptSameOrigin) {
    failures.push('EZB theme script must be served from the preview origin');
  }
  if (!evidence.themeScriptFetched) {
    failures.push('EZB theme script was not fetched by the browser');
  }
  if (!/^#[0-9a-f]{6}$/i.test(evidence.accentValue || '')) {
    failures.push('EZB theme brand CSS variable was not applied');
  }
  if (evidence.rawShortcode) {
    failures.push('raw EZB shortcode leaked into rendered page');
  }
  if (isHome) {
    if (!evidence.homeHeroPresent) failures.push('homepage hero is missing');
    if (!evidence.homeHeroBackground || evidence.homeHeroBackground === 'none') {
      failures.push('homepage hero background styling is missing');
    }
    if (!(evidence.homeHeadingPx >= 30)) {
      failures.push('homepage heading typography is unexpectedly small');
    }
    if (!evidence.homeCardPresent) failures.push('homepage product card is missing');
    if (!(evidence.homeCardBorderPx >= 1)) {
      failures.push('homepage product card border styling is missing');
    }
    if (!(evidence.homeCardRadiusPx >= 8)) {
      failures.push('homepage product card radius styling is missing');
    }
  }
  return failures;
}
