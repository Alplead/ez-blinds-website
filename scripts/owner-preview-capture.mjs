import { chromium } from 'playwright';
import { previewRenderFailures } from './preview-render-guard.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';

const baseUrl = process.env.EZB_BASE_URL;

if (!baseUrl) {
  console.error('Error: EZB_BASE_URL environment variable is required.');
  process.exit(1);
}

const outDir = 'owner-preview-output';

const coreRoutes = [
  { name: 'home', path: '/' },
  { name: 'products', path: '/products/' },
  { name: 'roller-blinds', path: '/roller-blinds/' },
  { name: 'sheer-curtains', path: '/sheer-curtains/' },
  { name: 'plantation-shutters', path: '/plantation-shutters/' },
  { name: 'retractable-flyscreens', path: '/retractable-flyscreens/' },
  { name: 'motorisation', path: '/motorised-blinds/' },
  { name: 'projects', path: '/projects/' },
  { name: 'project-example', path: '/projects/retractable-flyscreen-indoor-outdoor-opening/' },
  { name: 'about', path: '/about/' },
  { name: 'advice', path: '/advice/' },
  { name: 'blog', path: '/blog/' },
  { name: 'service-areas', path: '/service-areas/' },
  { name: 'contact', path: '/contact/' }
];

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 834, height: 1112 },
  { name: 'mobile', width: 390, height: 844 },
  { name: 'small-mobile', width: 320, height: 700 }
];

async function main() {
  await fs.rm(outDir, { recursive: true, force: true });
  await fs.mkdir(outDir, { recursive: true });

  const browser = await chromium.launch();
  const captures = [];
  let hasFailure = false;

  try {
    for (const viewport of viewports) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        reducedMotion: 'reduce'
      });

      try {
        for (const route of coreRoutes) {
          console.log(`Capturing ${viewport.name} - ${route.name} (${route.path})`);
          const page = await context.newPage();
          const pageErrors = [];
          const assetFailures = [];
          const themeAsset = /\/wp-content\/themes\/ezb-theme\/(?:style\.css|assets\/js\/site\.js)(?:[?#]|$)/;
          page.on('pageerror', error => pageErrors.push(error.message));
          page.on('response', response => {
            if (themeAsset.test(response.url()) && response.status() !== 200) {
              assetFailures.push('HTTP ' + response.status() + ' ' + response.url());
            }
          });
          page.on('requestfailed', request => {
            if (themeAsset.test(request.url())) assetFailures.push('failed ' + request.url());
          });

          try {
            const fullUrl = new URL(route.path, baseUrl).toString();
            const response = await page.goto(fullUrl, {
              waitUntil: 'networkidle',
              timeout: 30000
            });

            if (!response || response.status() !== 200) {
              throw new Error(`HTTP ${response?.status() ?? 'no response'}`);
            }

            // Catch layout failures that full-page screenshots can conceal,
            // particularly on narrow 320px mobile screens.
            const horizontalOverflow = await page.evaluate(() =>
              document.documentElement.scrollWidth >
                document.documentElement.clientWidth + 1
            );
            if (horizontalOverflow) {
              throw new Error('horizontal layout overflow at ' + viewport.width + 'px');
            }

            const headingCount = await page.locator('h1').count();
            if (headingCount !== 1) {
              throw new Error('expected exactly one page heading, got ' + headingCount);
            }

            // Validate the *actual* linked stylesheet and computed browser CSS.
            // This catches the former /wordpress-site asset-root regression and
            // raw [ezb_media_slot] leak that HTTP 200 / H1 checks missed.
            const renderEvidence = await page.evaluate(() => {
              const themeLinks = Array.from(document.querySelectorAll('link[rel~="stylesheet"]'))
                .filter((link) => {
                  try {
                    return new URL(link.href, document.baseURI).pathname
                      .endsWith('/wp-content/themes/ezb-theme/style.css');
                  } catch {
                    return false;
                  }
                });
              const themeLink = themeLinks[0];
              const themeScripts = Array.from(document.querySelectorAll('script[src]'))
                .filter((script) => {
                  try {
                    return new URL(script.src, document.baseURI).pathname
                      .endsWith('/wp-content/themes/ezb-theme/assets/js/site.js');
                  } catch {
                    return false;
                  }
                });
              const themeScript = themeScripts[0];
              const scriptResources = performance.getEntriesByType('resource');
              const hero = document.querySelector('.ezb-hero');
              const heroHeading = hero?.querySelector('h1');
              const card = document.querySelector('.ezb-card');
              return {
                themeStylesheetCount: themeLinks.length,
                themeStylesheetPath: themeLink
                  ? new URL(themeLink.href, document.baseURI).pathname : '',
                themeStylesheetLoaded: Boolean(themeLink?.sheet),
                themeStylesheetSameOrigin: Boolean(themeLink &&
                  new URL(themeLink.href, document.baseURI).origin === location.origin),
                themeScriptCount: themeScripts.length,
                themeScriptPath: themeScript
                  ? new URL(themeScript.src, document.baseURI).pathname : '',
                themeScriptSameOrigin: Boolean(themeScript &&
                  new URL(themeScript.src, document.baseURI).origin === location.origin),
                themeScriptFetched: Boolean(themeScript && scriptResources.some((entry) =>
                  entry.name === themeScript.src)),
                accentValue: getComputedStyle(document.documentElement)
                  .getPropertyValue('--ezb-accent').trim(),
                rawShortcode: /\[(?:\/)?ezb_[a-z0-9_]+(?:\s|\])/i
                  .test(document.body.textContent || ''),
                homeHeroPresent: Boolean(hero),
                homeHeroBackground: hero ? getComputedStyle(hero).backgroundImage : '',
                homeHeadingPx: heroHeading ? parseFloat(getComputedStyle(heroHeading).fontSize) : 0,
                homeCardPresent: Boolean(card),
                homeCardBorderPx: card ? parseFloat(getComputedStyle(card).borderTopWidth) : 0,
                homeCardRadiusPx: card ? parseFloat(getComputedStyle(card).borderTopLeftRadius) : 0
              };
            });
            const renderFailures = previewRenderFailures(renderEvidence, route.path === '/');
            if (renderFailures.length) {
              throw new Error('unstyled or incomplete preview: ' + renderFailures.join('; '));
            }

            await page.waitForTimeout(1000);
            // Deferred script errors must be checked after settling.
            if (pageErrors.length || assetFailures.length) {
              throw new Error('browser or theme asset failure: ' +
                [...pageErrors, ...assetFailures].join('; '));
            }

            const filename = `${viewport.name}-${route.name}.png`;
            await page.screenshot({
              path: path.join(outDir, filename),
              fullPage: true
            });
            // A screenshot may itself trigger lazy resources and browser errors.
            if (pageErrors.length || assetFailures.length) {
              throw new Error('browser or theme asset failure after screenshot: ' +
                [...pageErrors, ...assetFailures].join('; '));
            }

            captures.push({
              viewport: viewport.name,
              route: route.name,
              filename
            });
          } catch (error) {
            hasFailure = true;
            console.error(
              `Failed to capture ${viewport.name} - ${route.name}: ${error.message}`
            );
          } finally {
            await page.close();
          }
        }
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }

  const expectedCaptureCount = coreRoutes.length * viewports.length;
  if (hasFailure || captures.length !== expectedCaptureCount) {
    console.error(
      `Owner preview incomplete: captured ${captures.length}/${expectedCaptureCount} required views.`
    );
    process.exit(1);
  }

  const html = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EZ Blinds & Shutters - Owner Preview</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; max-width: 1200px; margin: 0 auto; padding: 2rem; background: #f5f5f5; color: #333; }
    h1 { color: #111; }
    .disclaimer { background: #fff3cd; color: #856404; padding: 1rem; border-radius: 4px; border-left: 4px solid #ffeeba; margin-bottom: 2rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 2rem; }
    .card { background: white; padding: 1rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .card img { max-width: 100%; height: auto; border: 1px solid #eee; }
    .card h3 { margin-top: 0; font-size: 1.1rem; }
    .badge { display: inline-block; padding: 0.25rem 0.5rem; border-radius: 999px; font-size: 0.8rem; font-weight: bold; text-transform: uppercase; }
    .badge.desktop { background: #e0f2fe; color: #0369a1; }
    .badge.mobile { background: #fce7f3; color: #be185d; }
    .badge.tablet { background: #e3f4e9; color: #18582f; }
    .badge.small-mobile { background: #ece9f9; color: #433088; }
    a { display: block; margin-top: 1rem; text-decoration: none; color: #2563eb; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <h1>EZ Blinds & Shutters - Owner Preview</h1>
  <div class="disclaimer">
    <strong>Note:</strong> Visual preview only. This does not prove real mail, Owner UI acceptance, persistent Media Library readiness, SEO/release acceptance or production readiness.
  </div>
  <div class="grid">
    ${captures.map((capture) => `
      <div class="card">
        <h3>
          <span class="badge ${capture.viewport}">${capture.viewport}</span>
          ${capture.route}
        </h3>
        <a href="${capture.filename}" target="_blank">
          <img src="${capture.filename}" alt="${capture.viewport} ${capture.route} screenshot" loading="lazy">
        </a>
      </div>
    `).join('')}
  </div>
</body>
</html>
  `.trim();

  await fs.writeFile(path.join(outDir, 'index.html'), html);
  console.log(`EZB_OWNER_PREVIEW_CAPTURE_PASS views=${expectedCaptureCount}`);
  console.log(`output=${outDir}`);
}

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
