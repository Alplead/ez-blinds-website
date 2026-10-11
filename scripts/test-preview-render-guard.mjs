import assert from 'node:assert/strict';
import { previewRenderFailures, previewNavigationFailure, previewImageFailures } from './preview-render-guard.mjs';

const valid = {
  themeStylesheetCount: 1,
  themeStylesheetPath: '/wp-content/themes/ezb-theme/style.css',
  themeStylesheetLoaded: true,
  themeStylesheetSameOrigin: true,
  themeScriptCount: 1,
  themeScriptPath: '/wp-content/themes/ezb-theme/assets/js/site.js',
  themeScriptSameOrigin: true,
  themeScriptFetched: true,
  accentValue: '#7a5a2b',
  rawShortcode: false,
  homeHeroPresent: true,
  homeHeroBackground: 'linear-gradient(rgb(250, 250, 250), rgb(240, 240, 240))',
  homeHeadingPx: 80,
  homeCardPresent: true,
  homeCardBorderPx: 1,
  homeCardRadiusPx: 18
};
assert.deepEqual(previewRenderFailures(valid, true), []);
assert.deepEqual(previewRenderFailures({ ...valid, homeHeroPresent: false }, false), []);
const cases = [
  [{ themeStylesheetCount: 0 }, /stylesheet must resolve/],
  [{ themeStylesheetPath: '/wordpress-site/wp-content/themes/ezb-theme/style.css' }, /stylesheet must resolve/],
  [{ themeStylesheetLoaded: false }, /did not load/],
  [{ themeStylesheetSameOrigin: false }, /stylesheet must be served/],
  [{ themeScriptCount: 0 }, /script must resolve/],
  [{ themeScriptPath: '/wordpress-site/wp-content/themes/ezb-theme/assets/js/site.js' }, /script must resolve/],
  [{ themeScriptSameOrigin: false }, /script must be served/],
  [{ themeScriptFetched: false }, /script was not fetched/],
  [{ accentValue: '' }, /brand CSS variable/],
  [{ rawShortcode: true }, /raw EZB shortcode/],
  [{ homeHeroPresent: false }, /hero is missing/],
  [{ homeHeroBackground: 'none' }, /background styling/],
  [{ homeHeadingPx: 12 }, /typography is unexpectedly small/],
  [{ homeCardPresent: false }, /product card is missing/],
  [{ homeCardBorderPx: 0 }, /border styling/],
  [{ homeCardRadiusPx: 0 }, /radius styling/]
];
for (const [delta, expected] of cases) {
  assert.match(previewRenderFailures({ ...valid, ...delta }, true).join('; '), expected);
}
const requestedRoute = 'https://preview.example.test/contact/';
const navigationCases = [
  ['https://preview.example.test/contact/', false, ''],
  ['https://preview.example.test/', false, 'unexpected navigation'],
  ['https://other.example.test/contact/', false, 'unexpected navigation'],
  ['https://preview.example.test/contact/?preview=1', false, 'unexpected navigation'],
  ['https://preview.example.test/contact/#intro', false, 'unexpected navigation'],
  ['https://preview.example.test/contact/', true, 'unexpected navigation'],
  ['https://user:pass@preview.example.test/contact/', false, 'unexpected navigation'],
  ['not a URL', false, 'invalid preview navigation URL']
];
for (const [actual, redirected, expectedFailure] of navigationCases) {
  const failure = previewNavigationFailure(requestedRoute, actual, redirected);
  if (expectedFailure) assert.match(failure, new RegExp(expectedFailure));
  else assert.equal(failure, '');
}
assert.deepEqual(previewImageFailures([{ src: '/approved.webp', complete: true, naturalWidth: 1200 }]), []);
assert.match(previewImageFailures([{ src: '/broken.webp', complete: true, naturalWidth: 0 }]).join('; '), /broken image/);
assert.match(previewImageFailures([{ src: '/slow.webp', complete: false, naturalWidth: 0 }]).join('; '), /did not finish/);
assert.match(previewImageFailures([{ src: '', complete: true, naturalWidth: 0 }]).join('; '), /no resolved source/);
assert.deepEqual(previewImageFailures([{ src: '/decorative.webp', complete: true, naturalWidth: 500, hasAlt: true }]), []);
assert.match(previewImageFailures([{ src: '/unlabelled.webp', complete: true, naturalWidth: 500, hasAlt: false }]).join('; '), /missing alt attribute/);
const sensitiveNavigation = previewNavigationFailure(
  requestedRoute,
  'https://viewer:synthetic@preview.example.test/contact/?token=synthetic#synthetic'
);
assert.match(sensitiveNavigation, /unexpected navigation/);
assert.doesNotMatch(sensitiveNavigation, /viewer|synthetic|token=/);
const sensitiveImageFailure = previewImageFailures([{
  src: 'https://viewer:synthetic@preview.example.test/image.webp?token=synthetic',
  complete: true,
  naturalWidth: 0
}]).join('; ');
assert.match(sensitiveImageFailure, /broken image 1/);
assert.doesNotMatch(sensitiveImageFailure, /viewer|synthetic|token=/);
const numberedImageFailure = previewImageFailures([
  { src: '/ok.webp', complete: true, naturalWidth: 100, hasAlt: true },
  { src: 'https://preview.example.test/slow.webp?token=synthetic', complete: false, naturalWidth: 0 }
]).join('; ');
assert.match(numberedImageFailure, /image 2 did not finish loading/);
assert.doesNotMatch(numberedImageFailure, /synthetic|token=/);
assert.equal(cases.length + 2 + navigationCases.length + 5 + 3, 34);
console.log('EZB_PREVIEW_RENDER_GUARD_PASS cases=34');
