const base = new URL(process.env.EZB_BASE_URL || 'http://127.0.0.1:8080');

const paths = [
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
  '/projects/prototype-retractable-flyscreen-project/',
  '/advice/',
  '/blog/',
  '/roller-blinds-blockout-vs-sunscreen/',
  '/sheer-curtains-privacy-layering/',
  '/plantation-shutters-before-you-choose/',
  '/retractable-flyscreen-track-threshold-planning/',
  '/motorised-blinds-power-control-planning/',
  '/advice/privacy-vs-daylight/',
  '/advice/retractable-flyscreen-suitability/',
  '/advice/when-motorisation-makes-sense/',
  '/service-areas/',
  '/about/',
  '/contact/'
];

function decodeHtml(value) {
  return value
    .replace(/&amp;/gi, '&')
    .replace(/&#0*38;/gi, '&')
    .replace(/&#x0*26;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#0*39;/gi, "'")
    .replace(/&#8211;/g, '–')
    .replace(/&#8212;/g, '—')
    .replace(/&#039;/g, "'")
    .trim();
}

function attr(tag, name) {
  const re = new RegExp(
    "\\b" + name + "\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)'|([^\\s>]+))",
    'i'
  );
  const match = tag.match(re);
  return match ? decodeHtml(match[1] ?? match[2] ?? match[3] ?? '') : '';
}

function extractTitle(html) {
  const matches = [...html.matchAll(/<title\b[^>]*>([\s\S]*?)<\/title>/gi)];
  return {
    count: matches.length,
    value: matches.length === 1 ? decodeHtml(matches[0][1].replace(/<[^>]*>/g, '')) : ''
  };
}

function extractCanonicals(html) {
  const canonicals = [];
  for (const match of html.matchAll(/<link\b[^>]*>/gi)) {
    const tag = match[0];
    const rel = attr(tag, 'rel')
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);
    if (!rel.includes('canonical')) continue;
    const href = attr(tag, 'href');
    if (href) canonicals.push(href);
  }
  return canonicals;
}

const titles = new Map();
const failures = [];
const results = [];

for (const path of paths) {
  const requested = new URL(path, base);
  let response;
  try {
    response = await fetch(requested, {
      redirect: 'follow',
      headers: { accept: 'text/html,application/xhtml+xml;q=0.9' }
    });
  } catch (error) {
    failures.push(`${path} -> fetch failed: ${error.message}`);
    continue;
  }

  if (response.status !== 200) {
    failures.push(`${path} -> expected HTTP 200, got ${response.status}`);
    continue;
  }

  const finalUrl = new URL(response.url);
  if (finalUrl.origin !== base.origin) {
    failures.push(`${path} -> unexpected off-origin redirect: ${finalUrl.href}`);
    continue;
  }
  const html = await response.text();
  const title = extractTitle(html);
  const canonicals = extractCanonicals(html);

  if (title.count !== 1 || !title.value) {
    failures.push(`${path} -> expected exactly one non-empty <title>, found ${title.count}`);
  } else {
    const previous = titles.get(title.value);
    if (previous) {
      failures.push(`${path} -> duplicate title with ${previous}: ${title.value}`);
    } else {
      titles.set(title.value, path);
    }
  }

  if (canonicals.length !== 1) {
    failures.push(`${path} -> expected exactly one canonical link, found ${canonicals.length}`);
  } else {
    let canonical;
    try {
      canonical = new URL(canonicals[0], finalUrl);
    } catch {
      failures.push(`${path} -> malformed canonical: ${canonicals[0]}`);
    }

    if (canonical) {
      if (canonical.origin !== base.origin) {
        failures.push(`${path} -> canonical left test origin: ${canonical.href}`);
      }

      if (canonical.searchParams.has('ezb_page')) {
        failures.push(`${path} -> canonical leaked development ezb_page transport`);
      }

      const expectedPath = finalUrl.pathname.endsWith('/')
        ? finalUrl.pathname
        : finalUrl.pathname + '/';
      const canonicalPath = canonical.pathname.endsWith('/')
        ? canonical.pathname
        : canonical.pathname + '/';

      if (canonicalPath !== expectedPath || canonical.search || canonical.hash) {
        failures.push(
          `${path} -> canonical mismatch: expected ${expectedPath}, got ${canonical.pathname}${canonical.search}${canonical.hash}`
        );
      }
    }
  }

  results.push({
    path,
    title: title.value,
    canonical: canonicals[0] || ''
  });
}

for (const result of results) {
  console.log(`SEO ${result.path} | ${result.title} | ${result.canonical || 'NO_CANONICAL'}`);
}

if (failures.length) {
  console.error('SEO structural audit failures:');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exitCode = 1;
} else {
  console.log(`EZB_SEO_AUDIT_PASS pages=${results.length} uniqueTitles=${titles.size}`);
}
