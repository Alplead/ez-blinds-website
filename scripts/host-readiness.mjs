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


function xmlLocations(xml) {
  return [...xml.matchAll(/<loc\b[^>]*>([\s\S]*?)<\/loc\s*>/gi)]
    .map(match => decodeHtml(match[1]));
}

async function fetchPage(path, options = {}) {
  const requested = new URL(path, base);
  const response = await fetch(requested, {
    redirect: options.redirect || 'manual',
    headers: { accept: 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8' }
  });
  return { requested, response };
}

const developmentPublicationMarkers = [
  'Prototype project',
  'prototype product map',
  'Photo upload will be added after',
  'once the upload path is enabled',
  // This video contains people and has no Owner publication/privacy clearance.
  'EZ_Retractable_Flyscreen_WEB_V1_720x1280_muted.mp4',
  'PROJECT PLACEHOLDER',
  'Development case-study shell',
  'Working copy for review.',
  'Development preview only.',
  'REAL EZ PROJECT MEDIA'
];

// Reject case-only changes to draft markers on indexable release hosts.
function decodeNumericHtmlReferences(html) {
  // Browsers decode numeric character references in both text and href values.
  return html.replace(/&#(?:x([0-9a-f]{1,6})|([0-9]{1,7}));?/gi, (entity, hex, decimal) => {
    const point = Number.parseInt(hex ?? decimal, hex ? 16 : 10);
    return point >= 0 && point <= 0x10ffff && !(point >= 0xd800 && point <= 0xdfff)
      ? String.fromCodePoint(point) : entity;
  });
}

function findDevelopmentMarker(html) {
  const renderedText = decodeNumericHtmlReferences(html).toLowerCase();
  return developmentPublicationMarkers.find(marker => renderedText.includes(marker.toLowerCase()));
}

function hasDevelopmentTransport(html) {
  // Fail closed on case variants and HTML numeric references in query keys.
  return /ezb_page\s*=/i.test(decodeNumericHtmlReferences(html));
}

// Include every current structural top-level route. A staging host must not
// accidentally index a page omitted from the small original smoke subset.
const canonicalRoutes = [
  '/',
  '/products/',
  '/roller-blinds/',
  '/sheer-curtains/',
  '/plantation-shutters/',
  '/retractable-flyscreens/',
  '/motorised-blinds/',
  '/projects/',
  '/advice/',
  '/blog/',
  '/about/',
  '/service-areas/',
  '/contact/'
];

for (const path of canonicalRoutes) {
  const { requested, response } = await fetchPage(path);
  if (response.status !== 200) {
    failures.push(`${path} -> expected HTTP 200 without redirects, got ${response.status}`);
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
  if (hasDevelopmentTransport(html) && (expectIndexable || !allowDevTransport)) {
    failures.push(`${path} leaked development ezb_page transport into public HTML`);
  }

  if (expectIndexable) {
    const marker = findDevelopmentMarker(html);
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

// Confirm the host does not silently serve its Home page for unknown paths.
const missingPath = '/ezb-readiness-nonexistent-404/';
const missingResponse = await fetch(new URL(missingPath, base), { redirect: 'manual' });
if (missingResponse.status !== 404 || missingResponse.headers.has('location')) {
  failures.push(missingPath + ' -> expected HTTP 404 without redirect, got ' + missingResponse.status);
}

const robotsResponse = await fetch(new URL('/robots.txt', base), { redirect: 'manual' });
if (robotsResponse.status !== 200) {
  failures.push(`/robots.txt -> expected HTTP 200, got ${robotsResponse.status}`);
} else {
  const robotsText = await robotsResponse.text();
  // A global wildcard block also prevents indexing; reject it on an
  // indexable release, and require a genuine wildcard group on staging.
  const groups = robotsText.split(/(?=^\s*User-agent\s*:)/gmi);
  const wildcardGroups = groups.filter(group => /^\s*User-agent\s*:\s*\*\s*$/mi.test(group));
  const broadBlock = wildcardGroups.some(group => /^\s*Disallow\s*:\s*\/(?:\*\$?)?\s*$/mi.test(group));
  const allowException = wildcardGroups.some(group => /^\s*Allow\s*:\s*\/\S*/mi.test(group));
  const blocksAll = broadBlock && !allowException;
  if (expectIndexable && broadBlock) {
    failures.push('/robots.txt blocks the entire site in indexable mode');
  }
  if (!expectIndexable && !blocksAll) {
    failures.push('/robots.txt does not block the entire site in non-indexable mode');
  }
}

const sitemapResponse = await fetch(new URL('/wp-sitemap.xml', base), { redirect: 'manual' });
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

    // A clean landing page is insufficient: published starter posts and
    // prototype Projects can appear in WordPress content sitemaps.
    // Inspect every indexed Page, Post and Project before declaring a host indexable.
    const indexLocations = xmlLocations(sitemap);
    const contentSitemaps = indexLocations.filter(location => {
      try {
        return /^\/wp-sitemap-posts-(?:page|post|ezb_project)-\d+\.xml$/.test(new URL(location, base).pathname);
      } catch {
        failures.push('sitemap index contains an invalid XML location');
        return false;
      }
    });
    if (!contentSitemaps.length || contentSitemaps.length > 30) {
      failures.push('sitemap index has an invalid number of content sitemaps');
    } else {
      // All three published content families must be represented. Otherwise a
      // missing Post sitemap could hide unreviewed development starter articles.
      for (const type of ['page', 'post', 'ezb_project']) {
        const expectedPath = '/wp-sitemap-posts-' + type + '-1.xml';
        if (!contentSitemaps.some(location => new URL(location, base).pathname === expectedPath)) {
          failures.push('sitemap index missing required content sitemap: ' + expectedPath);
        }
      }
      const checkedPages = new Set();
      for (const location of contentSitemaps) {
        const childUrl = new URL(location, base);
        if (childUrl.origin !== base.origin || childUrl.search || childUrl.hash) {
          failures.push('content sitemap location is not a clean same-origin URL');
          continue;
        }
        const childResponse = await fetch(childUrl, { redirect: 'manual' });
        if (childResponse.status !== 200) {
          failures.push(childUrl.pathname + ' -> expected sitemap HTTP 200, got ' + childResponse.status);
          continue;
        }
        const pageLocations = xmlLocations(await childResponse.text());
        if (!pageLocations.length || pageLocations.length > 250) {
          failures.push(childUrl.pathname + ' has an invalid number of content URLs');
          continue;
        }
        for (const pageLocation of pageLocations) {
          let pageUrl;
          try {
            pageUrl = new URL(pageLocation, base);
          } catch {
            failures.push(childUrl.pathname + ' contains an invalid content URL');
            continue;
          }
          if (pageUrl.origin !== base.origin || pageUrl.search || pageUrl.hash) {
            failures.push(childUrl.pathname + ' contains a non-canonical or off-origin content URL');
            continue;
          }
          if (checkedPages.has(pageUrl.href)) continue;
          checkedPages.add(pageUrl.href);
          if (checkedPages.size > 300) {
            failures.push('indexable content audit exceeds the bounded 300-URL safety limit');
            break;
          }
          const pageResponse = await fetch(pageUrl, { redirect: 'manual' });
          if (pageResponse.status !== 200) {
            failures.push(pageUrl.pathname + ' -> indexed content expected HTTP 200, got ' + pageResponse.status);
            continue;
          }
          const pageHtml = await pageResponse.text();
          // Canonical-route checks alone do not cover blog posts and Projects.
          // Every index-listed content page must self-canonicalise to its exact URL.
          const indexedCanonicals = extractCanonical(pageHtml);
          if (indexedCanonicals.length !== 1) {
            failures.push(pageUrl.pathname + ' indexed content expected exactly one canonical, found ' + indexedCanonicals.length);
          } else {
            try {
              const indexedCanonical = new URL(indexedCanonicals[0], pageUrl);
              if (indexedCanonical.href !== pageUrl.href) {
                failures.push(pageUrl.pathname + ' indexed content canonical mismatch: ' + indexedCanonical.href);
              }
            } catch {
              failures.push(pageUrl.pathname + ' indexed content has malformed canonical');
            }
          }
          const marker = findDevelopmentMarker(pageHtml);
          if (marker) failures.push(pageUrl.pathname + ' indexed development-only publication marker: ' + marker);
          if (hasDevelopmentTransport(pageHtml)) failures.push(pageUrl.pathname + ' indexed development transport leak');
          const robots = (pageResponse.headers.get('x-robots-tag') || '').toLowerCase() + ',' + metaRobots(pageHtml).join(',');
          if (robots.includes('noindex')) failures.push(pageUrl.pathname + ' appears in sitemap but is noindex');
        }
        if (checkedPages.size > 300) break;
      }
    }
  }
} else {
  notes.push(`non-indexable mode: sitemap status ${sitemapResponse.status} is informational`);
}

const verifiedRedirects = new Map([
  ['/retractable-fly-screen/', '/retractable-flyscreens/'],
  ['/portfolio/', '/projects/'],
  ['/portfolio/page/2/', '/projects/'],
  ['/category/roller-blinds/', '/roller-blinds/'],
  ['/2018/02/04/roller-blinds-showcase/', '/roller-blinds/'],
  ['/2018/02/04/plantation-shutters-showcase/', '/plantation-shutters/'],
  ['/2018/10/06/retractable-fly-screen-showcase/', '/retractable-flyscreens/']
]);

const retiredRoutes = [
  '/roman-blinds/',
  '/panel-guide-blinds/',
  '/venetian-blinds/',
  '/portfolio/venetian-blinds/',
  '/2018/02/04/roman-blinds-showcase/',
  '/2018/02/04/panel-guide-blinds-showcase/',
  '/2018/02/04/venetian-blinds-showcase/'
];

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

    if (resolved.origin !== base.origin || resolved.pathname !== expected.pathname || resolved.search || resolved.hash) {
      failures.push(
        `${source} -> expected Location ${expected.href}, got ${resolved.href}`
      );
    }
  }

  // A retired product with no truthful replacement must not silently redirect.
  for (const path of retiredRoutes) {
    const { response } = await fetchPage(path, { redirect: 'manual' });
    if (response.status !== 410 || response.headers.has('location')) {
      failures.push(path + ' -> expected HTTP 410 without redirect, got ' + response.status);
    }
  }
} else {
  notes.push('verified legacy 301 and 410 checks skipped because EZB_EXPECT_REDIRECTS=0');
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
