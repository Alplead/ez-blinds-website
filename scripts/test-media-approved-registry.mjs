import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// Approved V2.3 derivative filenames only. No customer image bytes are in Git.
const approved = [
  "PXL_20231017_045427584~2.webp",
  "IMAG3884~2.webp",
  "IMG_4689.webp",
  "EZ blinds and shutters Retractable Flyscreen S 01.webp",
  "EZ blinds and shutters Retractable Flyscreen S 02.webp",
  "EZ blinds and shutters Retractable Flyscreen S 03.webp",
  "IMAG3550.webp",
  "IMAG3554.webp",
  "IMAG3558.webp",
  "EZ blinds and shutters Roller blinds 01.webp",
  "EZ blinds and shutters Roller blinds 02.webp",
  "EZ blinds and shutters Roller blinds 03.webp",
  "EZ blinds and shutters Roller blinds 06.webp",
  "EZ blinds and shutters Roller blinds 07.webp",
  "EZ blinds and shutters Roller blinds 08.webp",
  "EZ blinds and shutters Plantation shutters 01.webp",
  "EZ blinds and shutters Plantation shutters  11.webp",
  "EZ blinds and shutters Plantation shutters  14.webp",
  "EZ blinds and shutters Plantation shutters  18.webp",
  "EZ blinds and shutters Retractable Flyscreen S 04.webp",
  "IMAG4409.webp",
  "IMAG4430.webp",
  "IMAG4641 (2).webp",
  "IMAG6334.webp",
  "IMAG6475.webp"
];
const plugin = readFileSync(new URL('../wp-content/plugins/ezb-core/ezb-core.php', import.meta.url), 'utf8');
const references = [...plugin.matchAll(/['"]filename['"]\s*=>\s*['"]([^'"]+)['"]/g)]
  .map(match => match[1])
  .filter(name => /\.(?:jpe?g|png|webp)$/i.test(name))
  .map(name => name.replace(/\.(?:jpe?g|png)$/i, '.webp'));
const unique = [...new Set(references)].sort();
assert.equal(approved.length, 25, 'approved V2.3 registry must contain 25 assets');
assert.equal(new Set(approved).size, 25, 'approved V2.3 registry has duplicate filenames');
assert.deepEqual(unique, [...approved].sort(),
  'WordPress image candidates must exactly match the approved V2.3 derivative filenames');
assert.ok(references.length >= 25, 'expected multiple media slot/gallery references');
console.log('EZB_MEDIA_APPROVED_REGISTRY_TEST_PASS files=25');
