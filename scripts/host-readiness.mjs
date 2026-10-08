const rawBase = process.env.EZB_BASE_URL || '';
if (!rawBase) {
  throw new Error('EZB_BASE_URL is required');
}

const base = new URL(rawBase);
const allowHttp = process.env.EZB_ALLOW_HTTP === '1';
const expectIndexable = process.env.EZB_EXPECT_INDEXABLE !== '0';
const expectRedirects = process.env.EZB_EXPECT_REDIRECTS !== '0';
const allowDevTransport = process.env.EZB_ALLOW_DEV_TRANSPORT === '1';

if (base.protocol !== 'https:' && !allowHttp) {
  throw new Error('host readiness requires HTTPS unless EZB_ALLOW_HTTP=1');
}

const failures = [];
const notes = [];

// An indexable release must never enable development-only query transport.
if (expectIndexable && allowDevTransport) {
  failures.push('indexable mode forbids development ezb_page transport opt-in');
}

function decodeHtml(value) {
  return value
    .replace(/&amp;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#0*39;/gi, "'")
    .trim();
}

function attr(tag, name) {
  const re = new RegExp(
    '\\b' + name + '\\s*=\\s*(?:"([^"]*)"|\'([^\']*)\'|([^\\s>]+))',
    'i'
  );
  const match = tag.match(re);
  return match ? decodeHtml(match[1] ?? match[2] ?? match[3] ?? '') : '';
}

function extractCanonical(html) {
  const values = [];
  for (const match of html.matchAll(/<link\b[^>]*>/gi)) {
    const tag = match[0];
    const rel = attr(tag, 'rel')
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);
    if (!rel.includes('canonical')) continue;
    const href = attr(tag, 'href');
    if (href) values.push(href);
  }
  return values;
}

function metaRobots(html) {
  const values = [];
  for (const match of html.matchAll(/<meta\b[^>]*>/gi)) {
    const tag = match[0];
    if (attr(tag, 'name').toLowerCase() !== 'robots') continue;
    values.push(attr(tag, 'content').toLowerCase());
  }
  return values;
}

async function fetchPage(path, options = {}) {
  const requested = new URL(path, base);
  const response = await fetch(requested, {
    redirect: options.redirect || 'follow',
    headers: { accept: 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8' }
  });
  return { requested, response };
}

const developmentPublicationMarkers = [
  'Prototype project',
  'PROJECT PLACEHOLDER',
  'Development case-study shell',
  'Working copy for review.',
  'Development preview only.',
  'REAL EZ PROJECT MEDIA'
];

const canonicalRoutes = [
  '/',
  '/roller-blinds/',
  '/retractable-flyscreens/',
  '/plantation-shutters/',
  '/projects/',
  '/advice/',
  '/contact/'
];

for (const path of canonicalRoutes) {
  const { requested, response } = await fetchPage(path);
  if (response.status !== 200) {
    failures.push(`${path} -> expected HTTP 200, got ${response.status}`);
    continue;
  }

  const finalUrl = new URL(response.url);
  if (finalUrl.origin !== base.origin) {
    failures.push(`${path} redirected off-origin to ${finalUrl.href}`);
  }
  if (finalUrl.pathname !== requested.pathname || finalUrl.search || finalUrl.hash) {
    failures.push(`${path} resolved to unexpected route ${finalUrl.pathname}${finalUrl.search}${finalUrl.hash}`);
  }

  const html = await response.text();
  if (html.includes('ezb_page=') && (expectIndexable || !allowDevTransport)) {
    failures.push(`${path} leaked development ezb_page transport into public HTML`);
  }

  if (expectIndexable) {
    const marker = developmentPublicationMarkers.find(value => html.includes(value));
    if (marker) {
      failures.push(`${path} contains development-only publication marker: ${marker}`);
    }
  }

  const canonicals = extractCanonical(html);
  if (canonicals.length !== 1) {
    failures.push(`${path} expected exactly one canonical, found ${canonicals.length}`);
  } else {
    const canonical = new URL(canonicals[0], finalUrl);
    const expected = new URL(finalUrl.pathname, base);
    if (
      canonical.origin !== base.origin ||
      canonical.pathname !== expected.pathname ||
      canonical.search ||
      canonical.hash
    ) {
      failures.push(
        `${path} canonical mismatch: expected ${expected.href}, got ${canonical.href}`
      );
    }
  }

  // Every required route must honour the indexing contract, not only Home.
  const xRobots = (response.headers.get('x-robots-tag') || '').toLowerCase();
  const robotsMeta = metaRobots(html).join(',');
  const hasNoindex = xRobots.includes('noindex') || robotsMeta.includes('noindex');

  if (expectIndexable && hasNoindex) {
    failures.push(`${path} is unexpectedly noindex in indexable mode`);
  } else if (!expectIndexable && !hasNoindex) {
    failures.push(`${path} lacks noindex protection in non-indexable mode`);
  }
}

const robotsResponse = await fetch(new URL('/robots.txt', base), { redirect: 'follow' });
if (robotsResponse.status !== 200) {
  failures.push(`/robots.txt -> expected HTTP 200, got ${robotsResponse.status}`);
} else {
  const robotsText = await robotsResponse.text();
  const blocksAll = /^\s*Disallow:\s*\/\s*$/mi.test(robotsText);
  if (expectIndexable && blocksAll) {
    failures.push('/robots.txt blocks the entire site in indexable mode');
  }
  if (!expectIndexable && !blocksAll) {
    failures.push('/robots.txt does not block the entire site in non-indexable mode');
  }
}

const sitemapResponse = await fetch(new URL('/wp-sitemap.xml', base), { redirect: 'follow' });
if (expectIndexable) {
  if (sitemapResponse.status !== 200) {
    failures.push(`/wp-sitemap.xml -> expected HTTP 200 in indexable mode, got ${sitemapResponse.status}`);
  } else {
    const sitemap = await sitemapResponse.text();
    if (!sitemap.includes('wp-sitemap-posts-page-1.xml')) {
      failures.push('sitemap index is missing the Page sitemap');
    }
    if (!sitemap.includes('wp-sitemap-posts-ezb_project-1.xml')) {
      failures.push('sitemap index is missing the Project sitemap');
    }
  }
} else {
  notes.push(`non-indexable mode: sitemap status ${sitemapResponse.status} is informational`);
}

const verifiedRedirects = new Map([
  ['/retractable-fly-screen/', '/retractable-flyscreens/'],
  ['/portfolio/', '/projects/'],
  ['/portfolio/page/2/', '/projects/'],
  ['/category/roller-blinds/', '/roller-blinds/']
]);

if (expectRedirects) {
  for (const [source, target] of verifiedRedirects) {
    const { response } = await fetchPage(source, { redirect: 'manual' });
    if (response.status !== 301) {
      failures.push(`${source} -> expected 301, got ${response.status}`);
      continue;
    }

    const location = response.headers.get('location') || '';
    const resolved = new URL(location, base);
    const expected = new URL(target, base);

    if (resolved.origin !== base.origin || resolved.pathname !== expected.pathname) {
      failures.push(
        `${source} -> expected Location ${expected.href}, got ${resolved.href}`
      );
    }
  }
} else {
  notes.push('verified legacy 301 checks skipped because EZB_EXPECT_REDIRECTS=0');
}

console.log(`EZB_HOST_READINESS base=${base.href}`);
console.log(`mode indexable=${expectIndexable ? 'yes' : 'no'} redirects=${expectRedirects ? 'yes' : 'no'} devTransport=${allowDevTransport ? 'allowed' : 'rejected'}`);
if (allowDevTransport) notes.push('development ezb_page transport explicitly allowed for prototype runtime only');
for (const note of notes) console.log(`NOTE ${note}`);

if (failures.length) {
  for (const failure of failures) console.error(`FAIL ${failure}`);
  process.exit(1);
}

console.log('EXTERNAL_MAIL_DELIVERY=MANUAL_GATE');
console.log('EZB_HOST_READINESS_PASS');
