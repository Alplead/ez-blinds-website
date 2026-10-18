/**
 * Synthetic-only Chromium preview smoke. Requires an isolated WordPress draft,
 * a short-lived WordPress logged-in cookie, and a disposable Docker runtime.
 * No deployment, publication, customer media, or Owner LocalWP access.
 */
import fs from 'node:fs/promises';
import path from 'node:path';

export const HOST = 'ez2-review.local';
export const VIEWPORTS = Object.freeze([
  { name: 'desktop', width: 1440, height: 900, reducedMotion: 'no-preference' },
  { name: 'mobile', width: 390, height: 844, reducedMotion: 'no-preference' },
  { name: 'small-mobile-reduced', width: 320, height: 700, reducedMotion: 'reduce' }
]);

export function validateAuth(auth) {
  if (!auth || typeof auth !== 'object' || Array.isArray(auth) ||
      auth.host !== HOST || !Number.isSafeInteger(auth.draft_id) || auth.draft_id < 1 ||
      !/^wordpress_logged_in_[a-f0-9]{32}$/.test(auth.cookie_name || '') ||
      typeof auth.cookie_value !== 'string' ||
      !/^[^\s;]{20,2000}$/.test(auth.cookie_value)) {
    throw new Error('Invalid disposable preview authorization');
  }
  return auth;
}

export function reviewEvidence(e) {
  const errors = [];
  if (e.httpStatus !== 200 || e.host !== HOST) errors.push('preview origin/status');
  if (e.h1Count !== 1 || !e.headingText.includes('Blinds & Shutters')) errors.push('hero heading');
  if (!e.quoteLink) errors.push('local quote link');
  if (e.horizontalOverflow) errors.push('horizontal overflow');
  if (e.syntheticGalleryCount !== 4) errors.push('synthetic image mapping');
  if (!Number.isSafeInteger(e.slideshowContainers) || e.slideshowContainers < 1) errors.push('Elementor slideshow not rendered');
  if (e.pageErrors.length || e.failedLocalRequests.length ||
      e.failedLocalResponses.length || e.blockedExternalRequests.length) {
    errors.push('browser/asset errors');
  }
  if (e.reducedMotion !== e.expectedReducedMotion) errors.push('reduced motion');
  return errors;
}

async function run() {
  const env = process.env;
  if (env.EZ2_BROWSER_OPT_IN !== 'YES_DISPOSABLE_DRAFT_ONLY' ||
      !['4.3.4', '4.3.5'].includes(env.EZ2_BROWSER_VERSION) ||
      !/^[a-f0-9]{40}$/.test(env.EZ2_BROWSER_SOURCE_SHA || '') ||
      !env.EZ2_BROWSER_AUTH_FILE || !env.EZ2_BROWSER_OUTPUT) {
    throw new Error('Disposable-only opt-in, exact source SHA, version and paths required');
  }
  const auth = validateAuth(JSON.parse(await fs.readFile(env.EZ2_BROWSER_AUTH_FILE, 'utf8')));
  const output = env.EZ2_BROWSER_OUTPUT;
  const { chromium } = await import('playwright');
  const results = [];
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    await fs.mkdir(output, { recursive: true });
    for (const viewport of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        reducedMotion: viewport.reducedMotion, serviceWorkers: 'block'
      });
      try {
        await context.addCookies([{ name: auth.cookie_name, value: auth.cookie_value,
          url: 'http://' + HOST + '/', httpOnly: true, sameSite: 'Lax' }]);
        const blockedExternalRequests = [];
        await context.route('**/*', async route => {
          const u = new URL(route.request().url());
          if (u.protocol !== 'http:' || u.hostname !== HOST || u.port ||
              u.username || u.password) {
            blockedExternalRequests.push(u.origin + u.pathname);
            return route.abort('blockedbyclient');
          }
          const target = 'http://127.0.0.1:8080' + u.pathname + u.search;
          try {
            const response = await route.fetch({
              url: target, maxRedirects: 0,
              headers: { ...route.request().headers(), host: HOST }
            });
            return route.fulfill({ response });
          } catch { return route.abort('failed'); }
        });
        const page = await context.newPage();
        const pageErrors = [], failedLocalRequests = [], failedLocalResponses = [];
        page.on('pageerror', e => pageErrors.push(e.message));
        page.on('requestfailed', r => {
          if (new URL(r.url()).hostname === HOST) failedLocalRequests.push(r.url().split('?')[0]);
        });
        page.on('response', r => {
          if (new URL(r.url()).hostname === HOST && r.status() >= 400) {
            failedLocalResponses.push({ status: r.status(), path: new URL(r.url()).pathname });
          }
        });
        const response = await page.goto('http://' + HOST + '/?page_id=' + auth.draft_id + '&preview=true',
          { waitUntil: 'networkidle', timeout: 45000 });
        const body = await page.content();
        const observed = await page.evaluate(() => ({
          host: location.hostname,
          h1Count: document.querySelectorAll('h1').length,
          headingText: document.querySelector('h1')?.textContent?.trim() || '',
          quoteLink: [...document.querySelectorAll('a[href]')].some(a => {
            const u = new URL(a.href, location.href);
            return /Request a Quote/i.test(a.textContent || '') &&
              u.hostname === location.hostname && u.pathname === '/contact/';
          }),
          horizontalOverflow: document.documentElement.scrollWidth >
            document.documentElement.clientWidth + 1,
          reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
          slideshowContainers: document.querySelectorAll('.elementor-background-slideshow').length
        }));
        const evidence = {
          viewport: viewport.name, version: env.EZ2_BROWSER_VERSION,
          httpStatus: response?.status() || 0, ...observed,
          expectedReducedMotion: viewport.reducedMotion === 'reduce',
          syntheticGalleryCount: [1, 2, 3, 4].filter(i =>
            body.includes('ez2-ci-synthetic-hero-' + i + '.png')).length,
          pageErrors, failedLocalRequests, failedLocalResponses, blockedExternalRequests,
          realMediaUsed: false,
          localwpInstalled: false, animationTimingVerified: false,
          ownerVisualApproved: false, deploymentAuthorized: false
        };
        evidence.failures = reviewEvidence(evidence);
        results.push(evidence);
        if (!evidence.failures.length) {
          await page.screenshot({ path: path.join(output, viewport.name + '.png'), fullPage: true });
        }
      } finally { await context.close(); }
    }
  } finally {
    if (browser) await browser.close();
    await fs.rm(env.EZ2_BROWSER_AUTH_FILE, { force: true });
  }
  await fs.writeFile(path.join(output, 'synthetic-browser-evidence.json'),
    JSON.stringify({ sourceSha: env.EZ2_BROWSER_SOURCE_SHA, scope: 'disposable-draft-only',
      results, realMediaVerified: false, localwpVisualQaVerified: false,
      motionTimingVerified: false, deploymentAuthorized: false }, null, 2) + '\n');
  const errors = results.flatMap(e => e.failures.map(f => e.viewport + ': ' + f));
  if (errors.length || results.length !== VIEWPORTS.length) {
    throw new Error('EZ2_SYNTHETIC_BROWSER_SMOKE_FAIL ' + errors.join('; '));
  }
  console.log('EZ2_SYNTHETIC_BROWSER_SMOKE_PASS viewports=3 version=' +
    env.EZ2_BROWSER_VERSION + ' real_media=false owner_visual_qa=false');
}
if (process.argv[1]?.endsWith('/ez2_elementor_browser_smoke.mjs')) {
  run().catch(e => { console.error(e.message); process.exitCode = 1; });
}
