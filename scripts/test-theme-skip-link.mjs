import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

const templates = fileURLToPath(new URL('../wp-content/themes/ezb-theme/templates/', import.meta.url));
const header = readFileSync(new URL('../wp-content/themes/ezb-theme/parts/header.html', import.meta.url), 'utf8');
assert.match(header, /class="ezb-skip-link"[^>]*href="#main-content"/, 'header must link to main-content');
let count = 0;
for (const name of readdirSync(templates).filter(name => name.endsWith('.html'))) {
  const source = readFileSync(join(templates, name), 'utf8');
  if (!/<main\b/i.test(source)) continue;
  assert.equal((source.match(/<main\b/gi) || []).length, 1, name + ': exactly one main landmark');
  assert.match(source, /<!-- wp:group \{[^\n]*"tagName":"main"[^\n]*"anchor":"main-content"/, name + ': main must have the skip-link target');
  count++;
}
assert.ok(count >= 10, 'expected the primary WordPress templates to be checked');
console.log('EZB_SKIP_LINK_TEST_PASS templates=' + count);
