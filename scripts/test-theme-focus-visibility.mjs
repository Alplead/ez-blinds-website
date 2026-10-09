import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const css = readFileSync(new URL('../wp-content/themes/ezb-theme/style.css', import.meta.url), 'utf8');
const header = readFileSync(new URL('../wp-content/themes/ezb-theme/parts/header.html', import.meta.url), 'utf8');

function body(pattern, label) {
  const match = css.match(pattern);
  assert.ok(match, label + ' CSS rule must exist');
  return match[1];
}
function hexValue(variable) {
  const match = css.match(new RegExp('--' + variable + ':\\s*(#[0-9a-fA-F]{6})\\s*;'));
  assert.ok(match, variable + ' must have a six-digit hex colour');
  return match[1];
}
function luminance(hex) {
  const channels = [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16) / 255);
  const linear = channels.map(channel => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
}
function contrast(a, b) {
  const [lighter, darker] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (lighter + 0.05) / (darker + 0.05);
}

const globalFocus = body(/a:focus-visible,\s*button:focus-visible,\s*input:focus-visible,\s*select:focus-visible,\s*textarea:focus-visible,\s*summary:focus-visible\s*\{([^}]*)\}/, 'global keyboard focus');
assert.match(globalFocus, /outline:\s*3px solid var\(--ezb-accent-dark\)\s*;/);
assert.match(globalFocus, /outline-offset:\s*3px\s*;/);
assert.ok(contrast(hexValue('ezb-accent-dark'), hexValue('ezb-white')) >= 3,
  'keyboard focus ring must have at least 3:1 contrast on the light site background');

const formFocus = body(/\.ezb-quote-form input:focus,\s*\.ezb-quote-form select:focus,\s*\.ezb-quote-form textarea:focus\s*\{([^}]*)\}/, 'quote field focus');
assert.match(formFocus, /outline:\s*3px solid var\(--ezb-accent-dark\)\s*;/);
assert.match(formFocus, /outline-offset:\s*2px\s*;/);

const footerFocus = body(/\.ezb-footer a:focus-visible\s*\{([^}]*)\}/, 'dark footer focus');
assert.match(footerFocus, /outline-color:\s*var\(--ezb-white\)\s*;/);
assert.ok(contrast(hexValue('ezb-white'), '#211a16') >= 3,
  'footer focus ring must have at least 3:1 contrast on the dark footer');

assert.match(css, /\.wp-block-navigation-submenu:focus-within\s*>\s*\.wp-block-navigation__submenu-container/,
  'keyboard focus must reveal desktop submenus');
assert.match(css, /\.wp-block-navigation__responsive-container\.is-menu-open\s*\{[^}]*overflow-y:\s*auto\s*;/s,
  'mobile navigation must scroll when content exceeds viewport');
assert.match(header, /class="ezb-skip-link"[^>]*href="#main-content"/,
  'keyboard skip link must target main content');
console.log('EZB_THEME_FOCUS_VISIBILITY_TEST_PASS cases=8');
