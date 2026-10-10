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

const rawMaxUrls = process.env.EZB_LINK_CHECK_MAX ?? '120';
const maxUrls = Number(rawMaxUrls);
if (!Number.isSafeInteger(maxUrls) || maxUrls < 1 || maxUrls > 10000) {
  console.error('EZB_LINK_CHECK_MAX must be a finite integer between 1 and 10000');
  process.exit(2);
}
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
    .replace(/&#(x[0-9a-f]+|[0-9]+);?/gi, (match, code) => {
      const number = code.startsWith('x') || code.startsWith('X')
        ? Number.parseInt(code.slice(1), 16) : Number.parseInt(code, 10);
      return number >= 0 && number <= 0x10ffff ? String.fromCodePoint(number) : match;
    })
    .replace(/&quot;/gi, '"')
    .replace(/&#0*39;/gi, "'")
    .trim();
}

function isDevelopmentTransportKey(key) {
  // URLSearchParams decodes one layer; reject bounded nested encodings too.
  // This crawler must not treat an encoded development route as public.
  let normalized = key;
  for (let pass = 0; pass <= 2; pass += 1) {
    if (normalized.toLowerCase() === 'ezb_page') return true;
    if (pass === 2) break;
    try {
      const decoded = decodeURIComponent(normalized);
      if (decoded === normalized) break;
      normalized = decoded;
    } catch {
      break;
    }
  }
  return false;
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
  // A valid HTML href need not be quoted; never overlook unquoted script
  // protocols. Scan opening tags and attributes separately so data-href and
  // other quoted attribute values cannot masquerade as real navigation.
  const tags = /<a\b(?:"[^"]*"|'[^']*'|[^'">])*>/gi;
  const attrPattern = /\s+([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
  let tag;
  while ((tag = tags.exec(html)) !== null) {
    attrPattern.lastIndex = 0;
    let attribute;
    while ((attribute = attrPattern.exec(tag[0])) !== null) {
      if (attribute[1].toLowerCase() !== 'href') continue;
      const rawValue = attribute[2] ?? attribute[3] ?? attribute[4];
      if (rawValue !== undefined) hrefs.push(decodeHref(rawValue));
      break;
    }
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
      redirect: 'manual',
      headers: { accept: 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8' }
    });
  } catch (error) {
    failures.push(`${href} -> fetch error: ${error.message}`);
    continue;
  }

  checked.set(href, response.status);

  // Never follow a redirect while crawling: even a bad same-origin route
  // must not cause this audit to request an unrelated external host.
  if (response.status >= 300 && response.status < 400) {
    const location = response.headers.get('location');
    let destination = 'missing Location';
    if (location) {
      try { destination = new URL(location, href).href; }
      catch { destination = 'invalid Location'; }
    }
    failures.push(`${href} unexpectedly redirected to ${destination}`);
    continue;
  }

  // Required public pages must be real HTTP 200 pages, not 204/206 responses.
  if (seeded.has(href) && response.status !== 200) {
    failures.push(`${href} -> required route expected HTTP 200, got ${response.status}`);
    continue;
  }

  if (response.status >= 400) {
    failures.push(`${href} -> HTTP ${response.status}`);
    continue;
  }
  // Discovered navigation must not silently pass with empty or partial bodies.
  if (response.status !== 200) {
    failures.push(`${href} -> internal link expected HTTP 200, got ${response.status}`);
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
  // Page-like links must serve HTML. Allow explicit file URLs (e.g. PDFs)
  // to retain their own content types without hiding wrong-page responses.
  const pageLike = seeded.has(href) || !/\.[a-z0-9]{2,8}$/i.test(requestedUrl.pathname);
  if (pageLike && !/^text\/html(?:\s*;|$)/i.test(contentType)) {
    failures.push(`${href} -> ${seeded.has(href) ? 'required route' : 'internal page'} expected text/html, got ${contentType || 'missing content-type'}`);
    continue;
  }
  if (!/^text\/html(?:\s*;|$)/i.test(contentType)) continue;

  const html = await response.text();
  for (const rawHref of extractAnchors(html)) {
    if (
      !rawHref ||
      rawHref.startsWith('#') ||
      /^(mailto:|tel:)/i.test(rawHref)
    ) {
      continue;
    }

    // HTML entity and ASCII whitespace tricks must not conceal script/data
    // protocols. Never fetch these links or treat them as valid public navigation.
    const compactHref = rawHref.replace(/[\u0000-\u0020]/g, '');
    const protocolMatch = /^([a-z][a-z0-9+.-]*):/i.exec(compactHref);
    const protocol = protocolMatch?.[1]?.toLowerCase() || '';
    // Only standard web, email and telephone schemes are valid public navigation.
    // Reject unknown schemes instead of silently skipping them as off-origin.
    if (protocol && !['http', 'https', 'mailto', 'tel'].includes(protocol)) {
      failures.push(`${href} contains unsafe internal link protocol: ${protocol}:`);
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

    if ([...url.searchParams.keys()].some(key => isDevelopmentTransportKey(key))) {
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
