import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { HOST, VIEWPORTS, validateAuth, reviewEvidence } from './ez2_elementor_browser_smoke.mjs';
let n = 0;
const auth = { host: HOST, draft_id: 17,
  cookie_name: 'wordpress_logged_in_' + 'a'.repeat(32),
  cookie_value: 'syntheticcookie'.repeat(3) };
assert.equal(validateAuth(auth), auth); n++;
for (const change of [
  { host: 'ezbns.com.au' }, { host: 'ez-bns-new-dev.local' },
  { host: 't2-ez-blinds-shutters.local' }, { draft_id: 0 }, { draft_id: '17' },
  { cookie_name: 'wordpress_' + 'a'.repeat(32) },
  { cookie_value: 'bad; cookie' }, { cookie_value: '' }
]) { assert.throws(() => validateAuth({ ...auth, ...change })); n++; }
const good = { httpStatus: 200, host: HOST, h1Count: 1,
  headingText: 'Blinds & Shutters', quoteLink: true, horizontalOverflow: false,
  syntheticGalleryCount: 4, slideshowContainers: 1, pageErrors: [], failedLocalRequests: [],
  failedLocalResponses: [], blockedExternalRequests: [],
  reducedMotion: true, expectedReducedMotion: true };
assert.deepEqual(reviewEvidence(good), []); n++;
for (const change of [
  { httpStatus: 302 }, { host: 'ezbns.com.au' }, { h1Count: 0 },
  { headingText: 'Placeholder' }, { quoteLink: false },
  { horizontalOverflow: true }, { syntheticGalleryCount: 3 }, { slideshowContainers: 0 },
  { pageErrors: ['runtime error'] }, { failedLocalRequests: ['missing.css'] },
  { failedLocalResponses: [{ status: 404, path: '/missing.css' }] },
  { blockedExternalRequests: ['https://fonts.example.invalid/style.css'] },
  { reducedMotion: false }
]) { assert.ok(reviewEvidence({ ...good, ...change }).length); n++; }
assert.deepEqual(VIEWPORTS.map(x => x.width), [1440, 390, 320]); n++;
assert.equal(VIEWPORTS.at(-1).reducedMotion, 'reduce'); n++;
const draftSource = readFileSync(new URL('./ez2_elementor_browser_smoke.mjs', import.meta.url), 'utf8');
assert.ok(draftSource.includes("HOST + '/?page_id=' + auth.draft_id"), 'Draft pages must use page_id'); n++;
assert.equal(n, 26);
console.log('EZ2_SYNTHETIC_BROWSER_GUARD_PASS cases=' + n);
