/** Public-home Chromium smoke on a disposable WordPress CI instance only.
 * This does NOT validate Elementor drafts, real photographs or Owner LocalWP.
 */
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

export const HOST = 'ez2-review.local';
export const VIEWPORTS = Object.freeze([
  { name: 'desktop', width: 1440, height: 900, reducedMotion: 'no-preference' },
  { name: 'mobile', width: 390, height: 844, reducedMotion: 'no-preference' },
  { name: 'small-mobile-reduced', width: 320, height: 700, reducedMotion: 'reduce' }
]);

export function validateScope(env) {
  if (env.EZ2_ISOLATED_BROWSER !== 'YES_DISPOSABLE_ONLY' ||
      !/^[a-f0-9]{40}$/.test(env.EZ2_SOURCE_SHA || '') ||
      !env.EZ2_BROWSER_OUTPUT || !path.isAbsolute(env.EZ2_BROWSER_OUTPUT)) {
    throw Error('DISPOSABLE_BROWSER_GATE');
  }
}

export function reviewEvidence(e) {
  const errors = [];
  if (e.status !== 200 || e.host !== HOST) errors.push('origin/status');
  if (!e.hasMain || e.styleSheets < 1) errors.push('missing layout/styles');
  if (e.horizontalOverflow) errors.push('horizontal overflow');
  if (e.reducedMotion !== e.expectedReducedMotion) errors.push('reduced-motion');
  if (e.pageErrors.length || e.failedLocalRequests.length) errors.push('browser/asset errors');
  if (e.contactStatus !== 200 || e.contactHost !== HOST ||
      !e.contactFormPresent || !e.contactNameRequired ||
      !e.contactPhone || !e.contactEmail || !e.contactNonce ||
      e.contactActionPath !== '/wp-admin/admin-post.php' ||
      e.contactActionHost !== HOST || !e.contactSubmitLabel ||
      e.contactMethod !== 'post') errors.push('contact form render');
  if (e.contactHorizontalOverflow) errors.push('contact horizontal overflow');
  const top = ['Products', 'Projects', 'Advice', 'Blog', 'About', 'Contact'];
  const products = ['Roller Blinds', 'Sheer Curtains', 'Plantation Shutters',
    'Retractable Flyscreens', 'Motorised Blinds'];
  if (JSON.stringify(e.navTopLevel) !== JSON.stringify(top)) errors.push('D-017 top-level navigation');
  if (JSON.stringify(e.navProductChildren) !== JSON.stringify(products)) errors.push('D-017 product submenu');
  if (e.navServiceAreasTopLevel || !e.footerServiceAreasLink ||
      !e.contactServiceAreasLink) errors.push('D-017 Service Areas placement');
  return errors;
}

export async function run(env = process.env) {
  validateScope(env);
  const browser = await chromium.launch({ headless: true });
  const evidence = [];
  try {
    await fs.mkdir(env.EZ2_BROWSER_OUTPUT, { recursive: true });
    for (const viewport of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        reducedMotion: viewport.reducedMotion, serviceWorkers: 'block'
      });
      try {
        await context.route('**/*', async route => {
          const u = new URL(route.request().url());
          if (u.protocol !== 'http:' || u.hostname !== HOST || u.port ||
              u.username || u.password) return route.abort('blockedbyclient');
          try {
            const response = await route.fetch({
              url: 'http://127.0.0.1:8080' + u.pathname + u.search,
              headers: { ...route.request().headers(), host: HOST }, maxRedirects: 0
            });
            return route.fulfill({ response });
          } catch { return route.abort('failed'); }
        });
        const page = await context.newPage();
        const pageErrors = [], failedLocalRequests = [];
        page.on('pageerror', e => pageErrors.push(e.message));
        page.on('requestfailed', r => {
          if (new URL(r.url()).hostname === HOST) failedLocalRequests.push(r.url().split('?')[0]);
        });
        const response = await page.goto('http://' + HOST + '/', {
          waitUntil: 'networkidle', timeout: 45000
        });
        const observed = await page.evaluate(() => ({
          host: location.hostname,
          hasMain: Boolean(document.querySelector('main')),
          horizontalOverflow: document.documentElement.scrollWidth >
            document.documentElement.clientWidth + 1,
          styleSheets: document.styleSheets.length,
          navTopLevel: [...document.querySelectorAll('header .wp-block-navigation__container > li')].map(li =>
            li.querySelector(':scope > a')?.textContent?.trim() || ''),
          navProductChildren: [...document.querySelectorAll('header .wp-block-navigation__container > li:first-child > ul > li')].map(li =>
            li.querySelector(':scope > a')?.textContent?.trim() || ''),
          navServiceAreasTopLevel: [...document.querySelectorAll('header .wp-block-navigation__container > li > a')].some(a =>
            new URL(a.href, location.href).pathname.replace(/\\/+$/, '') === '/service-areas'),
          footerLinkPaths: [...document.querySelectorAll('footer a[href]')].map(a => new URL(a.href, location.href).pathname),
          footerServiceAreasLink: [...document.querySelectorAll('footer a[href]')].some(a =>
            new URL(a.href, location.href).pathname.replace(/\\/+$/, '') === '/service-areas'),
          reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches
        }));
        await page.screenshot({
          path: path.join(env.EZ2_BROWSER_OUTPUT, viewport.name + '-home.png'),
          fullPage: true
        });
        // Read-only contact journey: never click submit or call admin-post.
        const contactResponse = await page.goto('http://' + HOST + '/contact/', {
          waitUntil: 'networkidle', timeout: 45000
        });
        const contact = await page.evaluate(() => {
          const form = document.querySelector('.ezb-quote-form');
          const action = form ? new URL(form.getAttribute('action') || '', location.href) : null;
          return {
            contactHost: location.hostname,
            contactFormPresent: Boolean(form),
            contactNameRequired: Boolean(form?.querySelector('input[name="name"][required]')),
            contactPhone: Boolean(form?.querySelector('input[name="phone"]')),
            contactEmail: Boolean(form?.querySelector('input[name="email"]')),
            contactNonce: Boolean(form?.querySelector('input[name="ezb_quote_nonce"]')),
            contactActionPath: action?.pathname || '',
            contactActionHost: action?.hostname || '',
            contactMethod: form?.method?.toLowerCase() || '',
            contactSubmitLabel: Boolean(form?.querySelector('button[type="submit"]')?.textContent?.includes('Send enquiry')),
            contactLinkPaths: [...document.querySelectorAll('.ezb-contact-service-areas a[href]')].map(a => new URL(a.href, location.href).pathname),
            contactServiceAreasLink: [...document.querySelectorAll('.ezb-contact-service-areas a[href]')].some(a =>
              new URL(a.href, location.href).pathname.replace(/\\/+$/, '') === '/service-areas'),
            contactHorizontalOverflow: document.documentElement.scrollWidth >
              document.documentElement.clientWidth + 1
          };
        });
        const result = {
          viewport: viewport.name, status: response?.status() || 0, ...observed,
          contactStatus: contactResponse?.status() || 0, ...contact,
          expectedReducedMotion: viewport.reducedMotion === 'reduce',
          pageErrors, failedLocalRequests,
          elementorDraftVerified: false, realMediaVerified: false,
          localwpVerified: false, animationTimingVerified: false,
          deploymentAuthorized: false
        };
        result.failures = reviewEvidence(result);
        evidence.push(result);
        if (!result.failures.length) {
          await page.screenshot({
            path: path.join(env.EZ2_BROWSER_OUTPUT, viewport.name + '-contact.png'),
            fullPage: true
          });
        }
      } finally { await context.close(); }
    }
  } finally {
    await browser.close();
    await fs.mkdir(env.EZ2_BROWSER_OUTPUT, { recursive: true });
    await fs.writeFile(path.join(env.EZ2_BROWSER_OUTPUT, 'evidence.json'),
      JSON.stringify({ sourceSha: env.EZ2_SOURCE_SHA,
        scope: 'isolated-wordpress-public-home-and-contact-read-only',
        evidence, realMediaVerified: false, elementorDraftVerified: false,
        localwpVerified: false, deploymentAuthorized: false }, null, 2) + '\n');
  }
  const errors = evidence.flatMap(e => e.failures.map(f => e.viewport + ': ' + f));
  if (errors.length || evidence.length !== VIEWPORTS.length) {
    throw Error('EZ2_ISOLATED_BROWSER_FAIL ' + errors.join('; '));
  }
  console.log('EZ2_ISOLATED_BROWSER_PASS viewports=3 contact_read_only=true mail_sent=false draft=false real_media=false localwp=false');
}

if (process.argv[1]?.endsWith('/ez2_isolated_frontend_browser.mjs')) {
  run().catch(e => { console.error(e.message); process.exitCode = 1; });
}
