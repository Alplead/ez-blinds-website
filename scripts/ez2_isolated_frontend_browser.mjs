/** Disposable WordPress-only Chromium smoke. No draft, Owner VM, or deployment. */
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const HOST = 'ez2-review.local';
const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
  { name: 'small-mobile', width: 320, height: 700 }
];
if (process.env.EZ2_ISOLATED_BROWSER !== 'YES_DISPOSABLE_ONLY' ||
    !/^[a-f0-9]{40}$/.test(process.env.EZ2_SOURCE_SHA || '') ||
    !process.env.EZ2_BROWSER_OUTPUT) throw Error('DISPOSABLE_BROWSER_GATE');
const browser = await chromium.launch({ headless: true });
const evidence = [];
try {
  await fs.mkdir(process.env.EZ2_BROWSER_OUTPUT, { recursive: true });
  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport, serviceWorkers: 'block' });
    try {
      await context.route('**/*', async route => {
        const u = new URL(route.request().url());
        if (u.protocol !== 'http:' || u.hostname !== HOST || u.port ||
            u.username || u.password) return route.abort('blockedbyclient');
        try {
          const r = await route.fetch({
            url: 'http://127.0.0.1:8080' + u.pathname + u.search,
            headers: { ...route.request().headers(), host: HOST }, maxRedirects: 0
          });
          return route.fulfill({ response: r });
        } catch { return route.abort('failed'); }
      });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      const response = await page.goto('http://' + HOST + '/', {
        waitUntil: 'networkidle', timeout: 45000
      });
      const observed = await page.evaluate(() => ({
        host: location.hostname,
        title: document.title,
        hasMain: Boolean(document.querySelector('main')),
        horizontalOverflow: document.documentElement.scrollWidth >
          document.documentElement.clientWidth + 1,
        styleSheets: document.styleSheets.length
      }));
      const passed = response?.status() === 200 && observed.host === HOST &&
        observed.hasMain && !observed.horizontalOverflow &&
        observed.styleSheets > 0 && errors.length === 0;
      evidence.push({ viewport: viewport.name, ...observed, status: response?.status(),
        pageErrors: errors, passed, realMediaVerified: false,
        elementorDraftVerified: false, localwpVerified: false });
      if (!passed) throw Error('EZ2_ISOLATED_BROWSER_FAIL ' + viewport.name);
      await page.screenshot({
        path: path.join(process.env.EZ2_BROWSER_OUTPUT, viewport.name + '.png'),
        fullPage: true
      });
    } finally { await context.close(); }
  }
} finally {
  await browser.close();
  await fs.writeFile(path.join(process.env.EZ2_BROWSER_OUTPUT, 'evidence.json'),
    JSON.stringify({ sourceSha: process.env.EZ2_SOURCE_SHA,
      scope: 'isolated-wordpress-public-home-only', evidence }, null, 2) + '\n');
}
console.log('EZ2_ISOLATED_BROWSER_PASS viewports=3 draft=false owner_lp=false');
