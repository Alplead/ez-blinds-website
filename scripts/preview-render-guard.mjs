// Deterministic, browser-evidence-based guard for Owner preview screenshots.
// A 200 response, one H1 and no overflow are NOT sufficient proof of styled UI.
export function previewRenderFailures(evidence, isHome = false) {
  const failures = [];
  if (evidence.themeStylesheetCount !== 1 ||
      evidence.themeStylesheetPath !== '/wp-content/themes/ezb-theme/style.css') {
    failures.push('EZB theme stylesheet must resolve from the site root');
  }
  if (!evidence.themeStylesheetLoaded) {
    failures.push('EZB theme stylesheet did not load in the browser');
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
