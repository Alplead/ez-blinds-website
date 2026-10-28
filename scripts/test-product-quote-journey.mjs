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
const core = readFileSync(new URL('../wp-content/plugins/ezb-core/ezb-core.php', import.meta.url), 'utf8');
const productSelect = core.match(/<select name="product">([\s\S]*?)<\/select>/)?.[1];
assert.ok(productSelect, 'contact form must contain product selector');
const optionLabels = [...productSelect.matchAll(/selected\( \$selected_product, '([^']+)' \)/g)].map(match => match[1]);
assert.deepEqual(optionLabels, approved.map(([, label]) => label),
  'contact form choices must follow D-017 Owner-approved product order');
const quoteHandler = core.slice(core.indexOf('function ezb_handle_quote_form()'),
  core.indexOf("add_action( 'admin_post_nopriv_ezb_quote'"));
assert.match(core, /function ezb_quote_product_is_allowed\( \$product \)/,
  'server must define a product allowlist');
assert.match(core, /array_values\( ezb_quote_product_labels\(\) \)/,
  'allowlist must derive from D-017 labels');
assert.match(core, /array\( 'Other \/ Not sure' \)/,
  'neutral enquiry must remain available');
assert.match(quoteHandler, /if \( ! ezb_quote_product_is_allowed\( \$product \) \) \{[\s\S]*?quote_status=invalid/,
  'POST must reject unapproved product values');
assert.ok(quoteHandler.indexOf('ezb_quote_product_is_allowed( $product )') < quoteHandler.indexOf('wp_mail('),
  'product validation must precede any mail call');
assert.match(core, /wp_unique_id\( 'ezb-contact-method-note-' \)/,
  'each form needs a distinct contact help ID');
assert.equal((core.match(/esc_attr\( \$contact_note_id \)/g) || []).length, 3,
  'phone, email and help text must reference the same unique ID');
assert.doesNotMatch(core, /id="ezb-contact-method-note"/,
  'do not render a duplicate static ID across forms');
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
