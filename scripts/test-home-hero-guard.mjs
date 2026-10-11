import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const home = readFileSync(new URL('../wp-content/themes/ezb-theme/patterns/hero-home.php', import.meta.url), 'utf8');
const core = readFileSync(new URL('../wp-content/plugins/ezb-core/ezb-core.php', import.meta.url), 'utf8');
const visual = readFileSync(new URL('./real-media-visual-qa.mjs', import.meta.url), 'utf8');

assert.ok(home.includes('[ezb_media_slot slot="home-hero"]'), 'Home must render its registered media slot');
assert.ok(core.includes("'home-hero' => array("), 'Home media slot must exist in core');
assert.ok(!home.includes('Homepage hero photography placeholder'), 'Hard-coded Home placeholder must not return');
assert.ok(visual.includes('heroImageCountFailure(heroCount, !isProject)'), 'Visual QA must reject missing or duplicate Home hero');
assert.ok(visual.includes('if (heroCountError) failures.push('), 'Visual QA must record hero count failures');
console.log('EZB_HOME_HERO_GUARD_PASS');
