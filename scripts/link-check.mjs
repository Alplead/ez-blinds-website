const base = new URL(process.env.EZB_BASE_URL || 'http://127.0.0.1:8080');

const seeds = [
  '/',
  '/products/',
  '/roller-blinds/',
  '/sheer-curtains/',
  '/plantation-shutters/',
  '/retractable-flyscreens/',
  '/motorised-blinds/',
  '/projects/',
  '/projects/retractable-flyscreen-large-opening/',
  '/projects/retractable-flyscreen-indoor-outdoor-opening/',
  '/projects/prototype-roller-blinds-project/',
  '/projects/prototype-sheer-curtains-project/',
  '/advice/',
  '/advice/privacy-vs-daylight/',
  '/advice/retractable-flyscreen-suitability/',
  '/advice/when-motorisation-makes-sense/',
  '/service-areas/',
  '/about/',
  '/contact/'
];

const maxUrls = Number(process.env.EZB_LINK_CHECK_MAX || 120);
const queue = seeds.map((path) => new URL(path, base).href);
const queued = new Set(queue);
const seeded = new Set(queue);
const checked = new Map();
const failures = [];
const devTransportLinks = [];

function decodeHref(value) {
  return value
    .replace(/&amp;/gi, '&')
    .replace(/&#0*38;/gi, '&')
    .replace(/&#x0*26;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#0*39;/gi, "'")
    .trim();
}

function shouldSkip(url) {
  return (
    url.pathname.startsWith('/wp-admin/') ||
    url.pathname === '/wp-login.php' ||
    url.pathname === '/xmlrpc.php' ||
    url.pathname.startsWith('/wp-json/') ||
    url.pathname === '/wp-admin/admin-post.php'
  );
}

function extractAnchors(html) {
  const hrefs = [];
  const pattern = /<a\b[^>]*\bhref\s*=\s*(["'])(.*?)\1/gi;
  let match;
  while ((match = pattern.exec(html)) !== null) {
    hrefs.push(decodeHref(match[2]));
  }
  return hrefs;
}

while (queue.length) {
  if (checked.size >= maxUrls) {
    failures.push(`crawl exceeded bounded limit of ${maxUrls} URLs`);
    break;
  }

  const href = queue.shift();
  if (checked.has(href)) continue;

  let response;
  try {
    response = await fetch(href, {
      redirect: 'follow',
      headers: { accept: 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8' }
    });
  } catch (error) {
    failures.push(`${href} -> fetch error: ${error.message}`);
    continue;
  }

  checked.set(href, response.status);

  // Required public pages must be real HTTP 200 pages, not 204/206 responses.
  if (seeded.has(href) && response.status !== 200) {
    failures.push(`${href} -> required route expected HTTP 200, got ${response.status}`);
    continue;
  }

  if (response.status >= 400) {
    failures.push(`${href} -> HTTP ${response.status}`);
    continue;
  }

  const finalUrl = new URL(response.url);
  if (finalUrl.origin !== base.origin) {
    failures.push(`${href} unexpectedly redirected off-origin to ${finalUrl.href}`);
    continue;
  }
  // All discovered internal links must resolve to their intended canonical path.
  // A broken article link silently redirected to Home is not a valid link.
  const requestedUrl = new URL(href);
  if (finalUrl.pathname !== requestedUrl.pathname || finalUrl.search !== requestedUrl.search || finalUrl.hash) {
    failures.push(`${href} unexpectedly redirected to ${finalUrl.href}`);
    continue;
  }

  const contentType = (response.headers.get('content-type') || '').trim();
  if (seeded.has(href) && !/^text\/html(?:\s*;|$)/i.test(contentType)) {
    failures.push(`${href} -> required route expected text/html, got ${contentType || 'missing content-type'}`);
    continue;
  }
  if (!contentType.includes('text/html')) continue;

  const html = await response.text();
  for (const rawHref of extractAnchors(html)) {
    if (
      !rawHref ||
      rawHref.startsWith('#') ||
      /^(mailto:|tel:|javascript:|data:)/i.test(rawHref)
    ) {
      continue;
    }

    let url;
    try {
      url = new URL(rawHref, finalUrl);
    } catch {
      failures.push(`${href} contains malformed href: ${rawHref}`);
      continue;
    }

    if (url.origin !== base.origin || shouldSkip(url)) continue;

    if (url.searchParams.has('ezb_page')) {
      devTransportLinks.push(`${href} -> ${url.pathname}${url.search}`);
      continue;
    }

    url.hash = '';
    const normalized = url.href;
    if (!queued.has(normalized) && !checked.has(normalized)) {
      queued.add(normalized);
      queue.push(normalized);
    }
  }
}

console.log(`EZB_LINK_CHECK checked=${checked.size} queued=${queued.size}`);
for (const [href, status] of checked) {
  console.log(`${status} ${new URL(href).pathname}${new URL(href).search}`);
}

if (devTransportLinks.length) {
  console.error('Public pretty-route HTML exposed development ezb_page links:');
  for (const item of devTransportLinks) console.error(`- ${item}`);
  process.exitCode = 1;
}

if (failures.length) {
  console.error('Broken internal links / crawl failures:');
  for (const item of failures) console.error(`- ${item}`);
  process.exitCode = 1;
}

if (!process.exitCode) {
  console.log('EZB_LINK_CHECK_PASS');
}
