import assert from 'node:assert/strict';
import { previewRenderFailures, previewNavigationFailure } from './preview-render-guard.mjs';

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
assert.equal(cases.length + 2 + navigationCases.length, 26);
console.log('EZB_PREVIEW_RENDER_GUARD_PASS cases=26');
