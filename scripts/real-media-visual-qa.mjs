import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import { inspectMediaImage } from './media-image-readiness.mjs';

const rawBase = process.env.EZB_BASE_URL || '';
if (!rawBase) throw new Error('EZB_BASE_URL is required');

const base = new URL(rawBase);
if (base.protocol !== 'https:' && process.env.EZB_ALLOW_HTTP !== '1') {
  throw new Error('real-media visual QA requires HTTPS unless EZB_ALLOW_HTTP=1');
}

const output = process.env.EZB_MEDIA_QA_OUTPUT || 'real-media-qa-output';
const routes = [
  ['home', '/', null],
  ['roller-blinds', '/roller-blinds/', 6],
  ['plantation-shutters', '/plantation-shutters/', 4],
  ['retractable-flyscreens', '/retractable-flyscreens/', 10],
  ['sheer-curtains', '/sheer-curtains/', null],
  ['retractable-flyscreen-large-opening', '/projects/retractable-flyscreen-large-opening/', 3]
];
const viewports = [
  ['desktop', { width: 1440, height: 900 }],
  ['tablet', { width: 834, height: 1112 }],
  ['mobile', { width: 390, height: 844 }]
];

await fs.mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const failures = [];

try {
  for (const [viewportName, viewport] of viewports) {
    const context = await browser.newContext({ viewport, reducedMotion: 'reduce' });
    const page = await context.newPage();

    for (const [name, path, galleryCount] of routes) {
      const isProject = path.startsWith('/projects/');
      const requestedUrl = new URL(path, base);
      const response = await page.goto(requestedUrl.href, { waitUntil: 'networkidle' });
      if (!response || response.status() !== 200) {
        failures.push(`${viewportName} ${name}: HTTP ${response?.status() ?? 'no response'}`);
        continue;
      }
      const finalUrl = new URL(page.url());
      if (finalUrl.origin !== base.origin || finalUrl.pathname !== requestedUrl.pathname || finalUrl.search || finalUrl.hash) {
        failures.push(`${viewportName} ${name}: unexpected navigation to ${finalUrl.href}`);
        continue;
      }

      const placeholderCount = await page.locator('.ezb-media-placeholder').count();
      if (name === 'home' && placeholderCount > 0) {
        failures.push(`${viewportName} home still contains a media placeholder`);
      }

      const heroImages = page.locator('img.ezb-media-slot__image');
      if (await heroImages.count()) {
        if (await heroImages.first().getAttribute('loading') === 'lazy') {
          failures.push(`${viewportName} ${name}: hero image should not be lazy-loaded`);
        }
        const heroOk = await inspectMediaImage(heroImages.first());
        if (!heroOk.complete || heroOk.naturalWidth <= 0 || heroOk.naturalHeight <= 0) {
          failures.push(`${viewportName} ${name}: hero image failed to load`);
        }
        if (!heroOk.alt.trim()) {
          failures.push(`${viewportName} ${name}: hero image has empty alt text`);
        }
      } else if (name !== 'home' && !isProject) {
        failures.push(`${viewportName} ${name}: expected a real hero image`);
      }

      if (galleryCount !== null) {
        const gallery = page.locator(isProject ? 'img.ezb-project-gallery__image' : 'img.ezb-product-gallery__image');
        const count = await gallery.count();
        if (count !== galleryCount) {
          failures.push(`${viewportName} ${name}: expected ${galleryCount} gallery images, found ${count}`);
        }

        for (let i = 0; i < count; i += 1) {
          const state = await inspectMediaImage(gallery.nth(i));
          if (!state.complete || state.naturalWidth <= 0 || state.naturalHeight <= 0) {
            failures.push(`${viewportName} ${name}: gallery image ${i + 1} failed to load`);
          }
          if (!state.alt.trim()) {
            failures.push(`${viewportName} ${name}: gallery image ${i + 1} has empty alt text`);
          }
        }
      }

      const overflow = await page.evaluate(() =>
        document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
      );
      if (overflow) failures.push(`${viewportName} ${name}: horizontal overflow`);

      await page.screenshot({
        path: `${output}/${viewportName}-${name}.png`,
        fullPage: true
      });
    }

    await context.close();
  }
} finally {
  await browser.close();
}

if (failures.length) {
  failures.forEach((failure) => console.error(`FAIL ${failure}`));
  process.exit(1);
}

console.log('EZB_REAL_MEDIA_VISUAL_QA_AUTOMATION_PASS');
console.log('OWNER_VISUAL_JUDGEMENT=MANUAL_GATE');
