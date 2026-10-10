import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const approved = [
  ['roller-blinds', 'Roller Blinds'],
  ['sheer-curtains', 'Sheer Curtains'],
  ['plantation-shutters', 'Plantation Shutters'],
  ['retractable-flyscreens', 'Retractable Flyscreens'],
  ['motorised-blinds', 'Motorised Blinds']
];
for (const [slug] of approved) {
  const html = readFileSync(new URL('../wp-content/themes/ezb-theme/templates/page-' + slug + '.html', import.meta.url), 'utf8');
  assert.equal(html.includes('/contact/?quote_product=' + slug), true,
    'product page must preserve chosen product in its quote CTA: ' + slug);
}
console.log('EZB_PRODUCT_QUOTE_STATIC_PASS routes=5');

if (process.env.EZB_BASE_URL) {
  const origin = new URL(process.env.EZB_BASE_URL);
  async function get(path) {
    const response = await fetch(new URL(path, origin));
    assert.equal(response.status, 200, path + ' must be HTTP 200');
    return response.text();
  }
  function selectedOptions(html) {
    const match = html.match(/<select\b[^>]*name=["']product["'][^>]*>([\s\S]*?)<\/select>/);
    assert.ok(match, 'Contact must render a product selector');
    return [...match[1].matchAll(/<option\b([^>]*)>([\s\S]*?)<\/option>/g)]
      .filter(([, attrs]) => /\bselected(?:\s*=|\s|$)/i.test(attrs))
      .map(([, , text]) => text.replace(/<[^>]+>/g, '').trim());
  }
  for (const [slug, label] of approved) {
    const html = await get('/' + slug + '/');
    assert.ok(html.includes('/contact/?quote_product=' + slug),
      slug + ' must offer a contextual quote link');
    const contact = await get('/contact/?quote_product=' + slug);
    assert.deepEqual(selectedOptions(contact), [label],
      slug + ' must preselect only the approved product');
  }
  for (const path of [
    '/contact/', '/contact/?quote_product=not-approved',
    '/contact/?quote_product%5B%5D=roller-blinds'
  ]) {
    assert.deepEqual(selectedOptions(await get(path)), [],
      'Invalid/array/unset product context cannot preselect: ' + path);
  }
  console.log('EZB_PRODUCT_QUOTE_RUNTIME_PASS routes=5 invalid=3');
}
