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
console.log('EZB_MEDIA_QA_COVERAGE_TEST_PASS cases=6');
