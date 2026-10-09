import { chromium } from 'playwright';
import fs from 'node:fs/promises';

const base = 'http://127.0.0.1:8080';
const pages = [
  ['home', '/'],
  ['products', '/?ezb_page=products'],
  ['roller-blinds', '/?ezb_page=roller-blinds'],
  ['sheer-curtains', '/?ezb_page=sheer-curtains'],
  ['plantation-shutters', '/?ezb_page=plantation-shutters'],
  ['retractable-flyscreens', '/?ezb_page=retractable-flyscreens'],
  ['motorisation', '/?ezb_page=motorised-blinds'],
  ['projects', '/?ezb_page=projects'],
  ['project-rfs-large-opening', '/?ezb_page=project&ezb_project=retractable-flyscreen-large-opening'],
  ['project-rfs-indoor-outdoor', '/?ezb_page=project&ezb_project=retractable-flyscreen-indoor-outdoor-opening'],
  ['project-roller-blinds', '/?ezb_page=project&ezb_project=prototype-roller-blinds-project'],
  ['project-sheer-curtains', '/?ezb_page=project&ezb_project=prototype-sheer-curtains-project'],
  ['project-retractable-flyscreen', '/?ezb_page=project&ezb_project=prototype-retractable-flyscreen-project'],
  ['advice', '/?ezb_page=advice'],
  ['advice-privacy-vs-daylight', '/?ezb_page=privacy-vs-daylight'],
  ['advice-rfs-suitability', '/?ezb_page=retractable-flyscreen-suitability'],
  ['advice-motorisation', '/?ezb_page=when-motorisation-makes-sense'],
  ['service-areas', '/?ezb_page=service-areas'],
  ['about', '/?ezb_page=about'],
  ['contact', '/?ezb_page=contact']
];

const discoveredInternalRoutes = new Set();

const viewports = [
  ['desktop', { width: 1440, height: 900 }],
  ['tablet', { width: 834, height: 1112 }],
  ['mobile', { width: 390, height: 844 }]
];

await fs.mkdir('visual-qa-output', { recursive: true });

const browser = await chromium.launch({ headless: true });

try {
  for (const [viewportName, viewport] of viewports) {
    const context = await browser.newContext({ viewport, reducedMotion: 'reduce' });
    const page = await context.newPage();

    for (const [name, path] of pages) {
      const response = await page.goto(base + path, { waitUntil: 'networkidle' });
      if (!response || !response.ok()) {
        throw new Error(`${viewportName} ${name} returned ${response?.status() ?? 'no response'}`);
      }

      const overflow = await page.evaluate(() =>
        document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
      );
      if (overflow) {
        throw new Error(`${viewportName} ${name} has horizontal overflow`);
      }

      const h1Count = await page.locator('h1').count();
      if (h1Count !== 1) {
        throw new Error(`${viewportName} ${name} expected exactly one h1, found ${h1Count}`);
      }

      const unnamedVisibleLinks = await page.locator('a[href]').evaluateAll((anchors) =>
        anchors
          .filter((anchor) => {
            const style = getComputedStyle(anchor);
            return (
              anchor.getClientRects().length > 0 &&
              style.display !== 'none' &&
              style.visibility !== 'hidden'
            );
          })
          .filter((anchor) => {
            const text = anchor.textContent?.trim() ?? '';
            const aria = anchor.getAttribute('aria-label')?.trim() ?? '';
            const title = anchor.getAttribute('title')?.trim() ?? '';
            const imageAlt = anchor.querySelector('img')?.getAttribute('alt')?.trim() ?? '';
            return !text && !aria && !title && !imageAlt;
          })
          .map((anchor) => anchor.outerHTML)
      );

      if (unnamedVisibleLinks.length) {
        throw new Error(
          `${viewportName} ${name} has visible links without an accessible name: ` +
          unnamedVisibleLinks.slice(0, 3).join(' | ')
        );
      }

      if (viewportName === 'desktop' && name === 'projects') {
        const titles = page.locator('.ezb-card h2');
        for (let i = 0; i < await titles.count(); i += 1) {
          const metrics = await titles.nth(i).evaluate((el) => {
            const style = getComputedStyle(el);
            const lineHeight = parseFloat(style.lineHeight);
            return {
              text: el.textContent?.trim() ?? '',
              lines: lineHeight ? el.getBoundingClientRect().height / lineHeight : 0
            };
          });

          if (metrics.lines > 3.25) {
            throw new Error(
              `desktop project card title wraps excessively: "${metrics.text}" (${metrics.lines.toFixed(1)} lines)`
            );
          }
        }
      }

      if (viewportName === 'desktop') {
        const hrefs = await page.locator('a[href]').evaluateAll((anchors) =>
          anchors
            .map((anchor) => anchor.href)
            .filter((href) => {
              try {
                const url = new URL(href);
                return url.searchParams.has('ezb_page');
              } catch {
                return false;
              }
            })
        );

        hrefs.forEach((href) => discoveredInternalRoutes.add(href));
      }

      await page.screenshot({
        path: `visual-qa-output/${viewportName}-${name}.png`,
        fullPage: true
      });
    }

    if (viewportName === 'desktop') {
      for (const href of discoveredInternalRoutes) {
        const response = await context.request.get(href);
        if (!response.ok()) {
          throw new Error(
            `internal route failed: ${href} -> HTTP ${response.status()}`
          );
        }
      }
    }

    await context.close();
  }

  await captureNavigationStates(browser);
  await verifyAccessibilityInteractions(browser);
} finally {
  await browser.close();
}


async function captureNavigationStates(browser) {
  const desktop = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: 'reduce'
  });
  const desktopPage = await desktop.newPage();
  await desktopPage.goto(base + '/', { waitUntil: 'networkidle' });

  const productsMenu = desktopPage
    .locator('.wp-block-navigation-submenu')
    .filter({ hasText: 'Products' })
    .first();

  await productsMenu.hover();
  await desktopPage.waitForTimeout(180);

  await desktopPage.screenshot({
    path: 'visual-qa-output/desktop-nav-products-open.png',
    fullPage: false
  });

  const desktopRoller = productsMenu.getByRole('link', { name: 'Roller Blinds' }).first();
  if (!(await desktopRoller.isVisible())) {
    const submenu = productsMenu.locator('.wp-block-navigation__submenu-container').first();
    const diagnostics = await submenu.evaluate((el) => {
      const style = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return {
        display: style.display,
        visibility: style.visibility,
        opacity: style.opacity,
        overflow: style.overflow,
        width: rect.width,
        height: rect.height
      };
    });

    throw new Error(
      'desktop Products submenu did not expose Roller Blinds: ' +
      JSON.stringify(diagnostics)
    );
  }
  await desktop.close();

  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 },
    reducedMotion: 'reduce'
  });
  const mobilePage = await mobile.newPage();
  await mobilePage.goto(base + '/', { waitUntil: 'networkidle' });

  const openButton = mobilePage.locator('.wp-block-navigation__responsive-container-open').first();
  await openButton.focus();
  await mobilePage.keyboard.press('Enter');

  const mobilePanel = mobilePage.locator('.wp-block-navigation__responsive-container.is-menu-open').first();
  if (!(await mobilePanel.isVisible())) {
    throw new Error('mobile navigation panel did not open');
  }

  const panelMetrics = await mobilePanel.evaluate((el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return {
      width: rect.width,
      height: rect.height,
      backgroundColor: style.backgroundColor
    };
  });

  if (panelMetrics.height < 800) {
    throw new Error(
      'mobile navigation panel does not cover viewport: ' +
      JSON.stringify(panelMetrics)
    );
  }

  if (
    panelMetrics.backgroundColor === 'transparent' ||
    panelMetrics.backgroundColor === 'rgba(0, 0, 0, 0)'
  ) {
    throw new Error(
      'mobile navigation panel background is transparent: ' +
      JSON.stringify(panelMetrics)
    );
  }

  const mobileProducts = mobilePanel
    .locator('.wp-block-navigation-submenu')
    .filter({ hasText: 'Products' })
    .first();

  const requiredMobileLinks = [
    mobileProducts.getByRole('link', { name: 'Roller Blinds' }).first(),
    mobileProducts.getByRole('link', { name: 'Retractable Flyscreens' }).first(),
    mobilePanel.getByRole('link', { name: 'About' }).first(),
    mobilePanel.getByRole('link', { name: 'Contact' }).first()
  ];

  for (const link of requiredMobileLinks) {
    if (!(await link.isVisible())) {
      throw new Error('mobile navigation is missing a required visible destination');
    }
  }

  await mobilePage.screenshot({
    path: 'visual-qa-output/mobile-nav-open.png',
    fullPage: false
  });

  await mobilePage.screenshot({
    path: 'visual-qa-output/mobile-nav-products-open.png',
    fullPage: false
  });

  await mobile.close();
}

async function verifyAccessibilityInteractions(browser) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: 'reduce'
  });
  const page = await context.newPage();

  await page.goto(base + '/', { waitUntil: 'networkidle' });

  const motionReady = await page.evaluate(() =>
    document.documentElement.classList.contains('ezb-motion-ready')
  );
  if (motionReady) {
    throw new Error('reduced-motion context still enabled motion-ready effects');
  }

  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
  });
  await page.keyboard.press('Tab');

  const firstFocused = await page.evaluate(() => {
    const active = document.activeElement;
    const href = active?.getAttribute?.('href') ?? '';
    let fragment = '';

    try {
      fragment = href ? new URL(href, window.location.href).hash : '';
    } catch (error) {}

    const target = fragment ? document.querySelector(fragment) : null;

    return {
      className: active?.className ?? '',
      href,
      fragment,
      targetExists: Boolean(target),
      targetTag: target?.tagName ?? '',
      targetInsideMain: Boolean(target && (target.tagName === 'MAIN' || target.closest('main')))
    };
  });

  if (
    !String(firstFocused.className).includes('skip-link') ||
    !firstFocused.fragment ||
    !firstFocused.targetExists ||
    !firstFocused.targetInsideMain
  ) {
    throw new Error(
      'first keyboard focus is not a valid skip link to main content: ' +
      JSON.stringify(firstFocused)
    );
  }

  await page.keyboard.press('Enter');
  if (await page.evaluate(() => window.location.hash) !== firstFocused.fragment) {
    throw new Error(
      'skip link did not activate its declared target: ' + JSON.stringify(firstFocused)
    );
  }

  await page.goto(base + '/?ezb_page=roller-blinds', { waitUntil: 'networkidle' });
  const firstSummary = page.locator('summary').first();
  if (!(await firstSummary.isVisible())) {
    throw new Error('roller-blinds FAQ has no visible summary control');
  }
  await firstSummary.focus();
  await page.keyboard.press('Enter');
  const detailsOpen = await firstSummary.evaluate((summary) =>
    Boolean(summary.closest('details')?.open)
  );
  if (!detailsOpen) {
    throw new Error('FAQ details did not open from keyboard activation');
  }

  await page.goto(base + '/?ezb_page=contact', { waitUntil: 'networkidle' });
  const controls = await page
    .locator(
      '.ezb-quote-form input:not([type="hidden"]):not([name="website"]), ' +
      '.ezb-quote-form select, .ezb-quote-form textarea'
    )
    .evaluateAll((elements) =>
      elements.map((element) => ({
        name: element.getAttribute('name') ?? '',
        labelled: Boolean(element.labels?.length),
        required: element.hasAttribute('required')
      }))
    );

  const unlabelled = controls.filter((control) => !control.labelled);
  if (unlabelled.length) {
    throw new Error(
      'quote form controls missing labels: ' + JSON.stringify(unlabelled)
    );
  }

  const nameControl = controls.find((control) => control.name === 'name');
  if (!nameControl?.required) {
    throw new Error('quote form Name control is not required');
  }

  const phoneInput = page.locator('.ezb-quote-form input[name="phone"]').first();
  const emailInput = page.locator('.ezb-quote-form input[name="email"]').first();
  if (!(await phoneInput.isVisible()) || !(await emailInput.isVisible())) {
    throw new Error('quote form contact-method inputs are not visible');
  }
  await phoneInput.fill('');
  await emailInput.fill('');
  const quoteForm = page.locator('.ezb-quote-form').first();
  const blockedEmptyContact = await quoteForm.evaluate((form) => {
    let prevented = false;
    const event = new Event('submit', { bubbles: true, cancelable: true });
    form.addEventListener('submit', (submitted) => {
      prevented = submitted.defaultPrevented;
    }, { once: true });
    form.dispatchEvent(event);
    return prevented;
  });
  if (!blockedEmptyContact) {
    throw new Error('quote form allowed submission without phone or email');
  }
  if (!(await phoneInput.evaluate((input) => document.activeElement === input))) {
    throw new Error('missing contact-method validation did not focus phone field');
  }

  const submit = page.locator('.ezb-quote-form button[type="submit"]').first();
  if (!(await submit.isVisible()) || !(await submit.textContent())?.trim()) {
    throw new Error('quote form submit control is not visibly named');
  }

  await context.close();
}

