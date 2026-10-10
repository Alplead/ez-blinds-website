import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = path => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const header = read('wp-content/themes/ezb-theme/parts/header.html');
const footer = read('wp-content/themes/ezb-theme/parts/footer.html');
const contact = read('wp-content/themes/ezb-theme/templates/page-contact.html');
const decision = read('docs/information-architecture-v2-provisional.md');

function parseLine(line) {
  const json = line.slice(line.indexOf('{'), line.lastIndexOf('}') + 1);
  return JSON.parse(json);
}
const topLevel = header.split('\n')
  .filter(line => /^\t{3}<!-- wp:navigation-(?:link|submenu) \{/.test(line))
  .map(parseLine);
const expected = [
  ['Products', '/products/'], ['Projects', '/projects/'],
  ['Advice', '/advice/'], ['Blog', '/blog/'],
  ['About', '/about/'], ['Contact', '/contact/']
];
assert.deepEqual(topLevel.map(({ label, url }) => [label, url]), expected,
  'Owner-approved top-level navigation must stay in the agreed order');
assert.equal(topLevel.some(link => link.url === '/service-areas/'), false,
  'Service Areas must not be top-level');
const productBlock = header.match(
  /<!-- wp:navigation-submenu \{"label":"Products"[^\n]*-->[\s\S]*?<!-- \/wp:navigation-submenu -->/
)?.[0];
assert.ok(productBlock, 'Products must contain its submenu');
const children = productBlock.split('\n')
  .filter(line => /^\t{4}<!-- wp:navigation-link \{/.test(line))
  .map(parseLine);
assert.deepEqual(children.map(({ label, url }) => [label, url]), [
  ['Roller Blinds', '/roller-blinds/'],
  ['Sheer Curtains', '/sheer-curtains/'],
  ['Plantation Shutters', '/plantation-shutters/'],
  ['Retractable Flyscreens', '/retractable-flyscreens/'],
  ['Motorised Blinds', '/motorised-blinds/']
], 'Products submenu labels and order must match D-017');
assert.equal((footer.match(/href="\/service-areas\/"/g) || []).length, 1,
  'footer must expose one Service Areas supporting link');
assert.equal((contact.match(/href="\/service-areas\/"/g) || []).length, 1,
  'Contact must expose one Service Areas supporting link');
assert.match(contact, /include your suburb in the enquiry so we can check/,
  'Contact must not imply automatic coverage');
assert.match(decision, /Owner APPROVED the A\/B\/C navigation structure/,
  'engineering IA note must reflect Owner decision');
assert.match(decision, /geographic coverage remains unapproved/i,
  'geographic claims must remain pending');
console.log('EZB_OWNER_APPROVED_NAV_PASS cases=7');
