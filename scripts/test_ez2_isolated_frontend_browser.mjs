import assert from 'node:assert/strict';
import { HOST, VIEWPORTS, validateScope, reviewEvidence } from './ez2_isolated_frontend_browser.mjs';
let cases = 0;
const validEnv = { EZ2_ISOLATED_BROWSER: 'YES_DISPOSABLE_ONLY',
  EZ2_SOURCE_SHA: 'a'.repeat(40), EZ2_BROWSER_OUTPUT: '/tmp/ez2-synthetic-browser' };
assert.doesNotThrow(() => validateScope(validEnv)); cases++;
for (const change of [
  { EZ2_ISOLATED_BROWSER: 'YES' },
  { EZ2_SOURCE_SHA: 'main' },
  { EZ2_SOURCE_SHA: 'A'.repeat(40) },
  { EZ2_BROWSER_OUTPUT: 'relative/path' },
  { EZ2_BROWSER_OUTPUT: '' }
]) { assert.throws(() => validateScope({ ...validEnv, ...change })); cases++; }
assert.deepEqual(VIEWPORTS.map(v => [v.width, v.height]),
  [[1440, 900], [390, 844], [320, 700]]); cases++;
assert.deepEqual(VIEWPORTS.map(v => v.reducedMotion),
  ['no-preference', 'no-preference', 'reduce']); cases++;
const good = { status: 200, host: HOST, hasMain: true, styleSheets: 2,
  horizontalOverflow: false, reducedMotion: true, expectedReducedMotion: true,
  pageErrors: [], failedLocalRequests: [] };
assert.deepEqual(reviewEvidence(good), []); cases++;
for (const change of [
  { status: 302 }, { host: 'ezbns.com.au' }, { hasMain: false },
  { styleSheets: 0 }, { horizontalOverflow: true },
  { reducedMotion: false }, { pageErrors: ['script failed'] },
  { failedLocalRequests: ['missing.css'] }
]) { assert.ok(reviewEvidence({ ...good, ...change }).length); cases++; }
assert.equal(cases, 17);
console.log('EZ2_ISOLATED_BROWSER_GUARD_PASS cases=' + cases);
