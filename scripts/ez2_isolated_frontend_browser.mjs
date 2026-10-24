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
      !env.EZ2_BROWSER_OUTPUT || !path.isAbsolute(env.EZ2_BROWSER_OUTPUT) ||
      !/^[1-9][0-9]{0,9}$/.test(env.EZ2_CI_DRAFT_ID || '')) {
    throw Error('DISPOSABLE_BROWSER_GATE');
  }
}

export function reviewEvidence(e) {
  const errors = [];
  if (e.status !== 200 || e.host !== HOST) errors.push('origin/status');
  if (!e.hasMain || e.styleSheets < 1) errors.push('missing layout/styles');
  if (e.horizontalOverflow) errors.push('horizontal overflow');
  if (!e.skipLinkKeyboardFocus) errors.push('keyboard skip link');
  if (e.mobileMenuRequired && (!e.mobileMenuOpen || !e.mobileMenuContactVisible ||
      !e.mobileMenuEscapeClose)) errors.push('mobile menu interaction');
  if (e.reducedMotion !== e.expectedReducedMotion) errors.push('reduced-motion');
  if (e.pageErrors.length || e.failedLocalRequests.length ||
      e.failedLocalResponses.length || e.blockedExternalRequests.length) {
    errors.push('browser/asset errors');
  }
  if (e.contactStatus !== 200 || e.contactHost !== HOST ||
      !e.contactFormPresent || !e.contactNameRequired ||
      !e.contactPhone || !e.contactEmail || !e.contactNonce ||
      e.contactActionPath !== '/wp-admin/admin-post.php' ||
      e.contactActionHost !== HOST || !e.contactSubmitLabel || !e.contactPreviewNote ||
      e.contactMethod !== 'post') errors.push('contact form render');
  if (e.contactHorizontalOverflow) errors.push('contact horizontal overflow');
  if (!e.contactEmptyRejected || !e.contactPhoneAccepted ||
      !e.contactEmailAccepted || !e.contactPostPrevented) {
    errors.push('contact client-side validation (no POST)');
  }
  if (!e.draftRestDenied || !e.draftDirectHidden) errors.push('synthetic draft public exposure');
  const expectedTop = ['Products', 'Projects', 'Advice', 'Blog', 'About', 'Contact'];
  const expectedProducts = ['Roller Blinds', 'Sheer Curtains', 'Plantation Shutters',
    'Retractable Flyscreens', 'Motorised Blinds'];
  if (JSON.stringify(e.navTopLevel) !== JSON.stringify(expectedTop)) errors.push('D-017 top-level navigation');
  if (JSON.stringify(e.navProductChildren) !== JSON.stringify(expectedProducts)) errors.push('D-017 product submenu');
  if (e.navServiceAreasTopLevel || e.footerServiceAreasCount !== 1 ||
      e.contactServiceAreasCount !== 1 || !e.serviceAreaFooterValid ||
      !e.serviceAreaContactValid) errors.push('D-017 Service Areas destination');
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
        const blockedExternalRequests = [];
        await context.route('**/*', async route => {
          const u = new URL(route.request().url());
          if (u.protocol !== 'http:' || u.hostname !== HOST || u.port ||
              u.username || u.password) {
            blockedExternalRequests.push(u.origin + u.pathname);
            return route.abort('blockedbyclient');
          }
          try {
            const response = await route.fetch({
              url: 'http://127.0.0.1:8080' + u.pathname + u.search,
              headers: { ...route.request().headers(), host: HOST }, maxRedirects: 0
            });
            return route.fulfill({ response });
          } catch { return route.abort('failed'); }
        });
        const page = await context.newPage();
        const pageErrors = [], failedLocalRequests = [], failedLocalResponses = [];
        page.on('pageerror', e => pageErrors.push(e.message));
        page.on('response', r => {
          const u = new URL(r.url());
          if (u.hostname === HOST && r.status() >= 400) {
            failedLocalResponses.push({ status: r.status(), path: u.pathname });
          }
        });
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
            a.textContent?.trim() === 'Service Areas'),
          footerServiceAreasLinks: [...document.querySelectorAll('footer a[href]')].filter(a =>
            a.textContent?.trim() === 'Service Areas').map(a => a.href),
          reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches
        }));
        // Exercise real keyboard focus and the WordPress mobile overlay, not just static markup.
        await page.keyboard.press('Tab');
        const firstSkipFocus = await page.evaluate(() => {
          const el = document.activeElement;
          const href = el?.getAttribute('href') || '';
          const target = href.startsWith('#') ? document.getElementById(href.slice(1)) : null;
          const main = document.querySelector('main');
          return {
            native: el?.matches('a.skip-link.screen-reader-text') === true,
            theme: el?.matches('a.ezb-skip-link[href="#main-content"]') === true,
            reachesMain: Boolean(target && main && (target === main || main.contains(target)))
          };
        });
        let secondSkipFocus = null;
        if (firstSkipFocus.native) {
          await page.keyboard.press('Tab');
          secondSkipFocus = await page.evaluate(() => {
            const el = document.activeElement;
            const target = document.getElementById('main-content');
            return el?.matches('a.ezb-skip-link[href="#main-content"]') === true &&
              Boolean(target && document.querySelector('main')?.contains(target));
          });
        }
        // WordPress core already provides the first working skip link. A theme
        // link is optional; do not require a duplicate second keyboard target.
        const skipLinkKeyboardFocus = firstSkipFocus.reachesMain &&
          (firstSkipFocus.native || firstSkipFocus.theme);
        const mobileMenuRequired = viewport.width <= 390;
        let mobileMenuOpen = false, mobileMenuContactVisible = false, mobileMenuEscapeClose = false;
        if (mobileMenuRequired) {
          const opener = page.locator('header .wp-block-navigation__responsive-container-open').first();
          if (await opener.isVisible()) {
            await opener.click();
            const panel = page.locator('header .wp-block-navigation__responsive-container.is-menu-open').first();
            mobileMenuOpen = await panel.isVisible();
            if (mobileMenuOpen) {
              mobileMenuContactVisible = await panel.getByRole('link', { name: 'Contact', exact: true }).isVisible();
              await page.keyboard.press('Escape');
              mobileMenuEscapeClose = !(await panel.isVisible());
              if (!mobileMenuEscapeClose) {
                const closer = page.locator('header .wp-block-navigation__responsive-container-close').first();
                if (await closer.isVisible()) await closer.click();
              }
            }
          }
        }
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
            contactServiceAreasLinks: [...document.querySelectorAll('.ezb-contact-service-areas a[href]')].filter(a =>
              a.textContent?.trim() === 'Service Areas').map(a => a.href),
            contactSubmitLabel: form?.querySelector('button[type="submit"]')?.textContent?.trim() === 'Test form (no email sent)',
            contactPreviewNote: [...document.querySelectorAll('.ezb-form-note[role="note"]')].some(note =>
              note.textContent?.trim() === 'Preview only: this form does not send email.'),
            contactHorizontalOverflow: document.documentElement.scrollWidth >
              document.documentElement.clientWidth + 1
          };
        });
        // Exercise the real form's client-side contact-method guard without
        // submitting to admin-post, sending email, or modifying WordPress.
        // A capturing preventDefault listener and synthetic submit events keep
        // all three probes entirely inside the disposable browser.
        const contactValidation = await page.evaluate(() => {
          const form = document.querySelector('.ezb-quote-form');
          const phone = form?.querySelector('input[name="phone"]');
          const email = form?.querySelector('input[name="email"]');
          if (!form || !phone || !email) return {
            contactEmptyRejected: false, contactPhoneAccepted: false,
            contactEmailAccepted: false, contactPostPrevented: false
          };
          const originalPhone = phone.value, originalEmail = email.value;
          let intercepted = 0;
          const preventPost = event => { event.preventDefault(); intercepted++; };
          const sendSynthetic = () => form.dispatchEvent(
            new Event('submit', { bubbles: true, cancelable: true }));
          form.addEventListener('submit', preventPost, true);
          try {
            phone.value = '';
            email.value = '';
            sendSynthetic();
            const contactEmptyRejected = !phone.checkValidity() &&
              phone.getAttribute('aria-invalid') === 'true' &&
              document.activeElement === phone;
            phone.value = '0000000000';
            phone.dispatchEvent(new Event('input', { bubbles: true }));
            sendSynthetic();
            const contactPhoneAccepted = phone.checkValidity() &&
              !phone.hasAttribute('aria-invalid');
            phone.value = '';
            phone.dispatchEvent(new Event('input', { bubbles: true }));
            email.value = 'synthetic@example.invalid';
            email.dispatchEvent(new Event('input', { bubbles: true }));
            sendSynthetic();
            const contactEmailAccepted = phone.checkValidity() &&
              !phone.hasAttribute('aria-invalid');
            return { contactEmptyRejected, contactPhoneAccepted,
              contactEmailAccepted, contactPostPrevented: intercepted === 3 };
          } finally {
            form.removeEventListener('submit', preventPost, true);
            phone.value = originalPhone;
            email.value = originalEmail;
            phone.setCustomValidity('');
            phone.removeAttribute('aria-invalid');
          }
        });
        // Disposable WordPress may use ?page_id= permalinks: test the actual destination.
        // Only read-only GET requests are allowed; no form submission or production access.
        const checkServiceDestination = async links => {
          if (links.length !== 1) return false;
          let u;
          try { u = new URL(links[0]); } catch { return false; }
          if (u.protocol !== 'http:' || u.hostname !== HOST || u.port ||
              u.username || u.password) return false;
          const target = await page.goto(u.href, { waitUntil: 'networkidle', timeout: 45000 });
          const heading = await page.evaluate(() =>
            document.querySelector('main h1')?.textContent?.trim() || '');
          return target?.status() === 200 && heading === 'Melbourne service area' &&
            new URL(page.url()).hostname === HOST;
        };
        const serviceAreaFooterValid = await checkServiceDestination(observed.footerServiceAreasLinks);
        const serviceAreaContactValid = await checkServiceDestination(contact.contactServiceAreasLinks);
        // Anonymous REST and direct-link probes must not reveal the synthetic draft.
        // A separate page keeps expected 401/404 out of asset error reporting.
        const draftProbe = await context.newPage();
        let draftRestDenied = false, draftDirectHidden = false;
        try {
          const api = await draftProbe.goto('http://' + HOST + '/?rest_route=/wp/v2', {
            waitUntil: 'domcontentloaded', timeout: 45000
          });
          const rest = await draftProbe.goto('http://' + HOST +
            '/?rest_route=/wp/v2/pages/' + env.EZ2_CI_DRAFT_ID, {
              waitUntil: 'domcontentloaded', timeout: 45000
            });
          draftRestDenied = api?.status() === 200 && [401, 403, 404].includes(rest?.status());
          const direct = await draftProbe.goto('http://' + HOST +
            '/?page_id=' + env.EZ2_CI_DRAFT_ID, {
              waitUntil: 'domcontentloaded', timeout: 45000
            });
          const draftLeaked = await draftProbe.evaluate(id =>
            Boolean(document.querySelector('[data-elementor-id="' + id + '"]')) ||
            (document.body?.textContent || '').includes('OWNER EDIT PROBE') ||
            (document.body?.textContent || '').includes('NOT FOR PUBLICATION'),
            env.EZ2_CI_DRAFT_ID);
          draftDirectHidden = Boolean(direct && direct.status() < 500 && !draftLeaked);
        } finally { await draftProbe.close(); }
        const result = {
          viewport: viewport.name, status: response?.status() || 0, ...observed,
          footerServiceAreasCount: observed.footerServiceAreasLinks.length,
          contactServiceAreasCount: contact.contactServiceAreasLinks.length,
          serviceAreaFooterValid, serviceAreaContactValid,
          contactStatus: contactResponse?.status() || 0, ...contact,
          ...contactValidation,
          expectedReducedMotion: viewport.reducedMotion === 'reduce',
          skipLinkKeyboardFocus, firstSkipFocus, secondSkipFocus,
          mobileMenuRequired, mobileMenuOpen,
          mobileMenuContactVisible, mobileMenuEscapeClose,
          draftRestDenied, draftDirectHidden,
          pageErrors, failedLocalRequests, failedLocalResponses, blockedExternalRequests,
          elementorDraftVerified: false, realMediaVerified: false,
          localwpVerified: false, animationTimingVerified: false,
          deploymentAuthorized: false
        };
        result.failures = reviewEvidence(result);
        evidence.push(result);
        if (!result.failures.length) {
          await page.screenshot({
            path: path.join(env.EZ2_BROWSER_OUTPUT, viewport.name + '-service-areas.png'),
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
