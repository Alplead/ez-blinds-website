import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('./owner-preview-capture.mjs', import.meta.url), 'utf8');

// Every top-level customer route needs an Owner-facing preview, plus one
// grounded project example. This is coverage of the PREVIEW TOOL, not a claim
// that screenshots or Owner approval have happened.
const routes = [
  '/', '/products/', '/roller-blinds/', '/sheer-curtains/',
  '/plantation-shutters/', '/retractable-flyscreens/',
  '/motorised-blinds/', '/projects/', '/advice/', '/blog/',
  '/service-areas/', '/about/', '/contact/',
  '/projects/retractable-flyscreen-indoor-outdoor-opening/'
];
for (const route of routes) {
  assert.ok(source.includes(`path: '${route}'`),
    `owner preview does not cover route ${route}`);
}
for (const [name, width, height] of [
  ['desktop', 1440, 900],
  ['tablet', 834, 1112],
  ['mobile', 390, 844],
  ['small-mobile', 320, 700]
]) {
  assert.ok(source.includes(`name: '${name}', width: ${width}, height: ${height}`),
    `owner preview does not cover ${name} ${width}px`);
}
assert.match(source, /document\.documentElement\.scrollWidth\s*>/,
  'owner preview must detect horizontal page overflow');
assert.match(source, /page\.locator\('h1'\)\.count\(\)/,
  'owner preview must reject missing or duplicate page headings');
assert.match(source, /captures\.length !== expectedCaptureCount/,
  'owner preview must fail if a screenshot is missing');
assert.ok(source.includes("previewRenderFailures(renderEvidence, route.path === '/')"),
  'screenshots must be rejected when actual browser styling is missing');
assert.ok(source.includes('rawShortcode: /\\[(?:\\/)?ezb_'),
  'browser must explicitly recognise unrendered EZB shortcodes');
assert.match(source, /themeStylesheetLoaded/,
  'screenshots must check the actual linked theme stylesheet');
assert.match(source, /rawShortcode/,
  'screenshots must reject leaked shortcode placeholders');
assert.match(source, /homeHeadingPx/,
  'screenshots must check real computed hero typography');
assert.match(source, /homeCardBorderPx/,
  'screenshots must check real computed card framing');
assert.match(source, /reducedMotion: 'reduce'/,
  'previews should not force animated visual effects');
assert.ok(source.includes("page.on('pageerror'"),
  'owner preview must fail on uncaught browser JavaScript errors');
assert.ok(source.includes("page.on('response'") && source.includes("page.on('requestfailed'"),
  'owner preview must detect failed theme CSS/JS requests');
assert.ok(source.includes('pageErrors.length || assetFailures.length'),
  'browser errors and failed theme assets must block screenshot acceptance');

console.log('EZB_OWNER_PREVIEW_COVERAGE_PASS routes=14 viewports=4 captures=56');
