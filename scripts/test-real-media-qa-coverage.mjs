import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const qa = readFileSync(new URL('./real-media-visual-qa.mjs', import.meta.url), 'utf8');
const plugin = readFileSync(new URL('../wp-content/plugins/ezb-core/ezb-core.php', import.meta.url), 'utf8');
const start = plugin.indexOf('function ezb_project_media_groups()');
const end = plugin.indexOf('function ezb_product_media_galleries()', start);
assert.ok(start >= 0 && end > start, 'canonical project media groups must exist');
const groups = plugin.slice(start, end);

for (const slug of [
  'retractable-flyscreen-large-opening',
  'retractable-flyscreen-indoor-outdoor-opening'
]) {
  assert.ok(groups.includes("'" + slug + "' => array("),
    slug + ': WordPress project media mapping must exist');
  assert.ok(qa.includes("['" + slug + "', '/projects/" + slug + "/', 3]"),
    slug + ': desktop/tablet/mobile visual QA must check all three images');
}

assert.match(qa, /reducedMotion: 'reduce'/,
  'real-media QA must request reduced-motion browser contexts');
assert.match(qa, /document\.documentElement\.classList\.contains\('ezb-motion-ready'\)/,
  'real-media QA must verify reduced-motion is honoured on each route');
assert.match(qa, /\['small-mobile', \{ width: 320, height: 700 \}\]/,
  'real-media QA must cover narrow 320px mobile screens');
assert.match(qa, /gallery\.nth\(i\)\.getAttribute\('loading'\) !== 'lazy'/,
  'real-media QA must reject eager-loaded galleries');
assert.match(qa, /const state = await inspectMediaImage\(gallery\.nth\(i\)\)/,
  'real-media QA must decode lazy-loaded images before asserting readiness');
assert.match(qa, /previewNavigationFailure\(/,
  'real-media QA must reject redirects, including redirects back to the same route');
assert.match(qa, /response\.request\(\)\.redirectedFrom\(\)/,
  'real-media QA must check the actual redirect chain');
assert.match(qa, /page\.on\('pageerror'/,
  'real-media QA must catch uncaught browser errors');
assert.match(qa, /page\.on\('requestfailed'/,
  'real-media QA must catch failed theme CSS and JavaScript requests');
assert.match(qa, /pageErrors\.length \|\| themeAssetFailures\.length/,
  'real-media QA must reject browser and theme asset failures');
console.log('EZB_MEDIA_QA_COVERAGE_TEST_PASS cases=14');
