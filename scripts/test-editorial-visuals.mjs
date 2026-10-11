import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = path => readFileSync(path, 'utf8');
const php = read('wp-content/plugins/ezb-core/includes/ezb-editorial-visuals.php');
const plugin = read('wp-content/plugins/ezb-core/ezb-core.php');
const home = read('wp-content/themes/ezb-theme/templates/front-page.html');
const css = read('wp-content/themes/ezb-theme/assets/css/editorial.css');
const js = read('wp-content/themes/ezb-theme/assets/js/editorial.js');
const functions = read('wp-content/themes/ezb-theme/functions.php');

const required = [
  [plugin, "includes/ezb-editorial-visuals.php", 'Registered plugin include'],
  [php, "add_shortcode(", 'WordPress photo shortcodes'],
  [php, "'ezb_editorial_hero'", 'Photo led hero'],
  [php, "'ezb_editorial_interlude'", 'Large editorial photo chapter'],
  [php, "ezb_find_attachment_by_basename", 'Resolve photos from WordPress Media Library'],
  [php, "wp_get_attachment_image", 'WordPress image sources'],
  [php, "'loading' => 'lazy'", 'Non-hero images lazy loaded'],
  [home, '[ezb_editorial_hero]', 'Home must use curated image hero'],
  [home, '[ezb_editorial_interlude photo="flyscreen"]', 'Flyscreen chapter'],
  [home, '[ezb_editorial_interlude photo="roller"]', 'Roller chapter'],
  [css, '.ezb-cinema', 'Full bleed hero CSS'],
  [css, '.ezb-product-hero', 'Product immersive hero CSS'],
  [css, '.ezb-product-gallery-block .ezb-project-gallery', 'Editorial gallery CSS'],
  [css, '@media (prefers-reduced-motion: reduce)', 'Reduced motion CSS'],
  [js, 'var intervalMs = 7700', 'Approximately 31 seconds for 4 photo cycle'],
  [js, 'prefers-reduced-motion: reduce', 'Reduced motion JS'],
  [js, 'visibilitychange', 'Pause when the tab is hidden'],
  [js, 'mouseenter', 'Pause on hover'],
  [js, 'focusin', 'Pause for keyboard interaction'],
  [js, 'requestAnimationFrame', 'Bound scroll work'],
  [js, 'toggle.disabled = motionBlocked', 'Autoplay control disabled when motion is blocked'],
  [js, 'reduced.matches || slides.length < 2', 'Disabled control for reduced-motion or a single slide'],
  [functions, "'ezb-editorial-motion'", 'JS enqueued'],
  [functions, "'ezb-editorial'", 'CSS enqueued'],
];
for (const [source, needle, description] of required) {
  assert.ok(source.includes(needle), description + ' missing');
}
assert.ok(!php.includes('uploads/'), 'Do not hard-code private uploads paths');
assert.ok(!php.includes('https://'), 'Do not hard-code public media URLs');
assert.ok(php.includes("return ''; // Missing photo:"), 'Unknown media should fail closed');

const imageCount = [...php.matchAll(/'file'\s*=>/g)].length;
assert.equal(imageCount, 4, 'Only four curated and registry-grounded slide sources');

console.log('EZB_EDITORIAL_ART_DIRECTION_TEST_PASS checks=' + (required.length + 4));
