import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { HOST, VIEWPORTS, validateScope, reviewEvidence } from './ez2_isolated_frontend_browser.mjs';
let cases = 0;
const validEnv = { EZ2_ISOLATED_BROWSER: 'YES_DISPOSABLE_ONLY',
  EZ2_SOURCE_SHA: 'a'.repeat(40), EZ2_BROWSER_OUTPUT: '/tmp/ez2-synthetic-browser',
  EZ2_CI_DRAFT_ID: '123' };
assert.doesNotThrow(() => validateScope(validEnv)); cases++;
for (const change of [
  { EZ2_ISOLATED_BROWSER: 'YES' },
  { EZ2_SOURCE_SHA: 'main' },
  { EZ2_SOURCE_SHA: 'A'.repeat(40) },
  { EZ2_BROWSER_OUTPUT: 'relative/path' },
  { EZ2_BROWSER_OUTPUT: '' },
  { EZ2_CI_DRAFT_ID: '' },
  { EZ2_CI_DRAFT_ID: '0' },
  { EZ2_CI_DRAFT_ID: 'bad-id' },
  { EZ2_CI_DRAFT_ID: '12345678901' }
]) { assert.throws(() => validateScope({ ...validEnv, ...change })); cases++; }
assert.deepEqual(VIEWPORTS.map(v => [v.width, v.height]),
  [[1440, 900], [390, 844], [320, 700]]); cases++;
assert.deepEqual(VIEWPORTS.map(v => v.reducedMotion),
  ['no-preference', 'no-preference', 'reduce']); cases++;
const good = { status: 200, host: HOST, hasMain: true, styleSheets: 2,
  horizontalOverflow: false, reducedMotion: true, expectedReducedMotion: true,
  skipLinkKeyboardFocus: true, mobileMenuRequired: true,
  mobileMenuOpen: true, mobileMenuContactVisible: true, mobileMenuEscapeClose: true,
  pageErrors: [], failedLocalRequests: [], failedLocalResponses: [],
  blockedExternalRequests: [], contactStatus: 200, contactHost: HOST,
  contactFormPresent: true, contactNameRequired: true, contactPhone: true,
  contactEmail: true, contactNonce: true, contactActionPath: '/wp-admin/admin-post.php',
  contactActionHost: HOST, contactMethod: 'post', contactSubmitLabel: true,
  contactPreviewNote: true,
  contactHorizontalOverflow: false,
  contactEmptyRejected: true, contactPhoneAccepted: true,
  contactEmailAccepted: true, contactPostPrevented: true,
  draftRestDenied: true,
  draftDirectHidden: true,
  navTopLevel: ['Products', 'Projects', 'Advice', 'Blog', 'About', 'Contact'],
  navProductChildren: ['Roller Blinds', 'Sheer Curtains', 'Plantation Shutters',
    'Retractable Flyscreens', 'Motorised Blinds'], navServiceAreasTopLevel: false,
  footerServiceAreasCount: 1, contactServiceAreasCount: 1,
  serviceAreaFooterValid: true, serviceAreaContactValid: true };
assert.deepEqual(reviewEvidence(good), []); cases++;
for (const change of [
  { status: 302 }, { host: 'ezbns.com.au' }, { hasMain: false },
  { styleSheets: 0 }, { horizontalOverflow: true },
  { skipLinkKeyboardFocus: false }, { mobileMenuOpen: false },
  { mobileMenuContactVisible: false }, { mobileMenuEscapeClose: false },
  { reducedMotion: false }, { pageErrors: ['script failed'] },
  { failedLocalRequests: ['missing.css'] },
  { failedLocalResponses: [{ status: 404, path: '/missing.css' }] },
  { blockedExternalRequests: ['https://example.invalid/style.css'] }, { contactStatus: 302 },
  { contactHost: 'other.local' }, { contactFormPresent: false },
  { contactNameRequired: false }, { contactPhone: false },
  { contactEmail: false }, { contactNonce: false },
  { contactActionPath: '/external' }, { contactActionHost: 'other.local' },
  { contactMethod: 'get' }, { contactSubmitLabel: false },
  { contactPreviewNote: false },
  { contactHorizontalOverflow: true },
  { contactEmptyRejected: false }, { contactPhoneAccepted: false },
  { contactEmailAccepted: false }, { contactPostPrevented: false },
  { draftRestDenied: false }, { draftDirectHidden: false },
  { navTopLevel: ['Products', 'Blog'] }, { navProductChildren: ['Roller Blinds'] },
  { navServiceAreasTopLevel: true }, { footerServiceAreasCount: 0 },
  { contactServiceAreasCount: 0 }, { serviceAreaFooterValid: false },
  { serviceAreaContactValid: false }
]) { assert.ok(reviewEvidence({ ...good, ...change }).length); cases++; }
const source = readFileSync(new URL('./ez2_isolated_frontend_browser.mjs', import.meta.url), 'utf8');
assert.ok(source.includes("form.getAttribute('action')"),
  'Form input named action must not shadow the HTMLFormElement action property'); cases++;
assert.ok(source.includes("=== 'Test form (no email sent)'")); cases++;
assert.ok(source.includes("=== 'Preview only: this form does not send email.'")); cases++;
// Browser smoke also checks the real focus order in both pinned Elementor runtimes.
assert.ok(source.includes("firstSkipFocus.reachesMain"));
assert.ok(source.includes("firstSkipFocus.native || firstSkipFocus.theme"));
assert.ok(source.includes("document.getElementById('main-content')"));
assert.ok(source.includes('rest_route=/wp/v2/pages/')); cases++;
assert.ok(source.includes('data-elementor-id')); cases++;
assert.ok(source.includes("form.addEventListener('submit', preventPost, true)"));
assert.ok(source.includes("form.removeEventListener('submit', preventPost, true)"));
assert.ok(source.includes("contactPostPrevented: intercepted === 3"));
cases++;
assert.equal(cases, 59);
console.log('EZ2_ISOLATED_BROWSER_GUARD_PASS cases=' + cases);
