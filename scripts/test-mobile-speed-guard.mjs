import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const root = new URL('../', import.meta.url);
const css = readFileSync(new URL('wp-content/themes/ezb-theme/style.css', root), 'utf8');
const theme = readFileSync(new URL('wp-content/themes/ezb-theme/functions.php', root), 'utf8');
const visual = readFileSync(new URL('scripts/visual-qa.mjs', root), 'utf8');

assert.match(css, /@media \(max-width: 360px\) \{[\s\S]*?overflow-wrap: anywhere;/,
  'compact viewport must wrap long customer headings');
assert.match(css, /\.ezb-product-switcher a,[\s\S]*?min-height:\s*44px;/,
  'compact viewport must preserve 44px CTA targets');
assert.match(visual, /\['small-mobile', \{ width: 320, height: 700 \}\]/,
  'browser QA must include 320px narrow phones');
assert.match(visual, /document\.documentElement\.scrollWidth\s*>\s*document\.documentElement\.clientWidth/,
  'browser QA must reject horizontal overflow');
assert.match(theme, /'ezb-theme-site'[\s\S]*?'strategy'\s*=>\s*'defer'[\s\S]*?'in_footer'\s*=>\s*true/,
  'front-end JS must be deferred in footer');
console.log('EZB_MOBILE_SPEED_GUARD_PASS cases=5');
