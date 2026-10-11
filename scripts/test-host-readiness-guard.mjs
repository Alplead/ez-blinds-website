import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(new URL('./host-readiness.mjs', import.meta.url));
const routes = new Set(['/', '/products/', '/roller-blinds/', '/sheer-curtains/', '/plantation-shutters/', '/retractable-flyscreens/', '/motorised-blinds/', '/projects/', '/advice/', '/blog/', '/about/', '/service-areas/', '/contact/', '/projects/prototype-roller-blinds-project/', '/roller-blinds-blockout-vs-sunscreen/']);

async function check({ name, indexable = false, allowDevTransport = false, missingNoindexPath = '', forceNoindexPath = '', leakPath = '', leakText = '<a href="/?ezb_page=roller-blinds">dev</a>', markerPath = '', markerText = 'Prototype project', redirectPath = '', badRedirectQueryPath = '', badGonePath = '', missingPostSitemap = false, redirectRobots = false, redirectSitemap = false, badIndexedCanonicalPath = '', badCanonicalUserinfoPath = '', badIndexedCanonicalUserinfoPath = '', robotsTextOverride = '', expectRedirects = false, expectedError = '' }) {
  const server = createServer((req, res) => {
    const pathname = new URL(req.url, 'http://127.0.0.1').pathname;
    const origin = `http://127.0.0.1:${server.address().port}`;
    if (pathname === '/robots.txt') {
      if (redirectRobots) { res.writeHead(302, { location: '/robots-proxy.txt' }); res.end(); return; }
      res.writeHead(200, { 'content-type': 'text/plain' });
      res.end(robotsTextOverride || (indexable ? 'User-agent: *\nAllow: /' : 'User-agent: *\nDisallow: /'));
      return;
    }
    if (pathname === '/wp-sitemap.xml') {
      if (redirectSitemap) { res.writeHead(302, { location: '/sitemap-proxy.xml' }); res.end(); return; }
      res.writeHead(indexable ? 200 : 404, { 'content-type': 'text/xml' });
      res.end('<sitemapindex>' + ['page', 'post', 'ezb_project'].filter(type => !(missingPostSitemap && type === 'post')).map(type =>
        '<sitemap><loc>' + origin + '/wp-sitemap-posts-' + type + '-1.xml</loc></sitemap>'
      ).join('') + '</sitemapindex>');
      return;
    }
    if (/^\/wp-sitemap-posts-(?:page|post|ezb_project)-1\.xml$/.test(pathname)) {
      const paths = pathname.includes('-page-') ? [...routes].filter(p => !p.includes('prototype-') && !p.includes('blockout-vs-sunscreen')) :
        pathname.includes('-post-') ? ['/roller-blinds-blockout-vs-sunscreen/'] :
        ['/projects/prototype-roller-blinds-project/'];
      res.writeHead(200, { 'content-type': 'text/xml' });
      res.end('<urlset>' + paths.map(p => '<url><loc>' + origin + p + '</loc></url>').join('') + '</urlset>');
      return;
    }
    const legacyRedirects = new Map([
      ['/retractable-fly-screen/', '/retractable-flyscreens/'],
      ['/portfolio/', '/projects/'],
      ['/portfolio/page/2/', '/projects/'],
      ['/category/roller-blinds/', '/roller-blinds/'],
      ['/2018/02/04/roller-blinds-showcase/', '/roller-blinds/'],
      ['/2018/02/04/plantation-shutters-showcase/', '/plantation-shutters/'],
      ['/2018/10/06/retractable-fly-screen-showcase/', '/retractable-flyscreens/']
    ]);
    const goneRoutes = new Set([
      '/roman-blinds/', '/panel-guide-blinds/', '/venetian-blinds/',
      '/portfolio/venetian-blinds/', '/2018/02/04/roman-blinds-showcase/',
      '/2018/02/04/panel-guide-blinds-showcase/', '/2018/02/04/venetian-blinds-showcase/'
    ]);
    if (pathname === redirectPath) { res.writeHead(302, { location: '/' }); res.end(); return; }
    if (legacyRedirects.has(pathname)) {
      const location = legacyRedirects.get(pathname) + (pathname === badRedirectQueryPath ? '?tracking=1' : '');
      res.writeHead(301, { location }); res.end(); return;
    }
    if (goneRoutes.has(pathname)) {
      if (pathname === badGonePath) { res.writeHead(302, { location: '/' }); res.end(); return; }
      res.writeHead(410); res.end('retired'); return;
    }
    if (!routes.has(pathname)) {
      res.writeHead(404); res.end('not found'); return;
    }
    const noindex = forceNoindexPath === pathname || (!indexable && missingNoindexPath !== pathname);
    const canonical = new URL(badIndexedCanonicalPath === pathname ? '/wrong-article/' : pathname, origin);
    if (badCanonicalUserinfoPath === pathname || badIndexedCanonicalUserinfoPath === pathname) {
      canonical.username = 'viewer';
      canonical.password = 'synthetic';
    }
    const html = '<link rel="canonical" href="' + canonical.href + '">' +
      '<meta name="robots" content="' + (noindex ? 'noindex, nofollow' : 'index, follow') + '">' +
      (leakPath === pathname ? leakText : '') +
      (markerPath === pathname ? '<div>' + markerText + '</div>' : '');
    res.writeHead(200, { 'content-type': 'text/html' }); res.end(html);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let result;
  try {
    result = await new Promise((resolve, reject) => {
      const env = { ...process.env, EZB_BASE_URL: `http://127.0.0.1:${server.address().port}/`, EZB_ALLOW_HTTP: '1', EZB_EXPECT_INDEXABLE: indexable ? '1' : '0', EZB_EXPECT_REDIRECTS: expectRedirects ? '1' : '0', EZB_ALLOW_DEV_TRANSPORT: allowDevTransport ? '1' : '0' };
      const child = spawn(process.execPath, [script], { env });
      let output = '';
      child.stdout.on('data', data => { output += data.toString(); });
      child.stderr.on('data', data => { output += data.toString(); });
      child.on('error', reject);
      child.on('close', code => resolve({ code, output }));
    });
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
  if (expectedError) {
    if (result.code === 0 || !result.output.includes(expectedError)) throw Error(name + ' expected rejection: ' + JSON.stringify(result));
  } else if (result.code !== 0 || !result.output.includes('EZB_HOST_READINESS_PASS')) {
    throw Error(name + ' expected PASS: ' + JSON.stringify(result));
  }
  console.log('PASS ' + name);
}

await check({ name: 'staging all thirteen structural routes noindex' });
await check({ name: 'secondary route missing noindex rejected', missingNoindexPath: '/contact/', expectedError: '/contact/ lacks noindex protection' });
await check({ name: 'staging dev query leak rejected', leakPath: '/advice/', expectedError: '/advice/ leaked development' });
await check({ name: 'prototype runtime explicit dev transport opt-in', allowDevTransport: true, leakPath: '/advice/' });
await check({ name: 'non-indexable development marker tolerated', markerPath: '/projects/' });
await check({ name: 'indexable release mode clean', indexable: true });
await check({ name: 'indexable opt-in rejected', indexable: true, allowDevTransport: true, expectedError: 'indexable mode forbids development ezb_page transport opt-in' });
await check({ name: 'indexable dev query leakage rejected', indexable: true, leakPath: '/advice/', expectedError: '/advice/ leaked development' });
await check({ name: 'indexable development marker rejected', indexable: true, markerPath: '/projects/', expectedError: '/projects/ contains development-only publication marker' });
await check({ name: 'indexable lowercase prototype marker rejected', indexable: true, markerPath: '/projects/', markerText: 'prototype project', expectedError: '/projects/ contains development-only publication marker' });
await check({ name: 'indexable decimal-entity prototype marker rejected', indexable: true, markerPath: '/projects/', markerText: 'Pro&#116;otype project', expectedError: '/projects/ contains development-only publication marker: Prototype project' });
await check({ name: 'indexable hex-entity indexed article marker rejected', indexable: true, markerPath: '/roller-blinds-blockout-vs-sunscreen/', markerText: 'Pro&#x74;otype project', expectedError: '/roller-blinds-blockout-vs-sunscreen/ indexed development-only publication marker: Prototype project' });
await check({ name: 'indexable lowercase indexed article marker rejected', indexable: true, markerPath: '/roller-blinds-blockout-vs-sunscreen/', markerText: 'prototype project', expectedError: '/roller-blinds-blockout-vs-sunscreen/ indexed development-only publication marker' });
await check({ name: 'indexable prototype wording on homepage rejected', indexable: true, markerPath: '/', markerText: 'Browse the current prototype product map in one place.', expectedError: '/ contains development-only publication marker: prototype product map' });
await check({ name: 'indexable secondary noindex rejected', indexable: true, forceNoindexPath: '/projects/', expectedError: '/projects/ is unexpectedly noindex' });
await check({ name: 'canonical route redirected to home rejected', redirectPath: '/contact/', expectedError: '/contact/ -> expected HTTP 200 without redirects, got 302' });
await check({ name: 'indexable prototype project in sitemap rejected', indexable: true, markerPath: '/projects/prototype-roller-blinds-project/', expectedError: '/projects/prototype-roller-blinds-project/ indexed development-only publication marker' });
await check({ name: 'indexable starter blog in sitemap rejected', indexable: true, markerPath: '/roller-blinds-blockout-vs-sunscreen/', expectedError: '/roller-blinds-blockout-vs-sunscreen/ indexed development-only publication marker' });
await check({ name: 'indexable starter blog dev transport rejected', indexable: true, leakPath: '/roller-blinds-blockout-vs-sunscreen/', expectedError: '/roller-blinds-blockout-vs-sunscreen/ indexed development transport leak' });
await check({ name: 'indexable missing Post sitemap rejected', indexable: true, missingPostSitemap: true, expectedError: 'sitemap index missing required content sitemap: /wp-sitemap-posts-post-1.xml' });
await check({ name: 'indexable starter blog wrong canonical rejected', indexable: true, badIndexedCanonicalPath: '/roller-blinds-blockout-vs-sunscreen/', expectedError: '/roller-blinds-blockout-vs-sunscreen/ indexed content canonical mismatch' });
await check({ name: 'staging canonical URL userinfo rejected', badCanonicalUserinfoPath: '/contact/', expectedError: '/contact/ canonical contains URL credentials' });
await check({ name: 'indexable indexed article canonical URL userinfo rejected', indexable: true, badIndexedCanonicalUserinfoPath: '/roller-blinds-blockout-vs-sunscreen/', expectedError: '/roller-blinds-blockout-vs-sunscreen/ indexed content canonical contains URL credentials' });
await check({ name: 'all verified 301 and retired 410 routes', expectRedirects: true });
await check({ name: 'legacy 301 with query rejected', expectRedirects: true, badRedirectQueryPath: '/portfolio/', expectedError: '/portfolio/ -> expected Location' });
await check({ name: 'retired URL redirect rejected', expectRedirects: true, badGonePath: '/roman-blinds/', expectedError: '/roman-blinds/ -> expected HTTP 410' });
await check({ name: 'legacy 302 rejected', expectRedirects: true, redirectPath: '/portfolio/', expectedError: '/portfolio/ -> expected 301' });
await check({ name: 'motorisation route missing staging noindex rejected', missingNoindexPath: '/motorised-blinds/', expectedError: '/motorised-blinds/ lacks noindex protection' });
await check({ name: 'products route development transport leak rejected', leakPath: '/products/', expectedError: '/products/ leaked development' });
await check({ name: 'indexable blog index development marker rejected', indexable: true, markerPath: '/blog/', expectedError: '/blog/ contains development-only publication marker' });
await check({ name: 'indexable upload roadmap banner rejected', indexable: true, markerPath: '/contact/', markerText: 'Photo upload will be added after checks.', expectedError: '/contact/ contains development-only publication marker: Photo upload will be added after' });
await check({ name: 'indexable old upload path hint rejected', indexable: true, markerPath: '/contact/', markerText: 'photos can be added later once the upload path is enabled', expectedError: '/contact/ contains development-only publication marker: once the upload path is enabled' });
await check({ name: 'indexable product route cannot embed unapproved RFS video', indexable: true, markerPath: '/retractable-flyscreens/', markerText: '<source src="/wp-content/uploads/EZ_Retractable_Flyscreen_WEB_V1_720x1280_muted.mp4">', expectedError: '/retractable-flyscreens/ contains development-only publication marker: EZ_Retractable_Flyscreen_WEB_V1_720x1280_muted.mp4' });
await check({ name: 'indexable sitemap project cannot embed case-varied private video', indexable: true, markerPath: '/projects/prototype-roller-blinds-project/', markerText: '<video src="/uploads/ez_retractable_flyscreen_web_v1_720x1280_muted.mp4"></video>', expectedError: '/projects/prototype-roller-blinds-project/ indexed development-only publication marker: EZ_Retractable_Flyscreen_WEB_V1_720x1280_muted.mp4' });
await check({ name: 'robots redirect rejected', redirectRobots: true, expectedError: '/robots.txt -> expected HTTP 200, got 302' });
await check({ name: 'indexable sitemap redirect rejected', indexable: true, redirectSitemap: true, expectedError: '/wp-sitemap.xml -> expected HTTP 200 in indexable mode, got 302' });
await check({ name: 'indexable decimal entity query key rejected', indexable: true, leakPath: '/products/', leakText: '<a href="/?ezb&#95;page=roller-blinds">dev</a>', expectedError: '/products/ leaked development' });
await check({ name: 'non-indexable hex entity equals rejected', leakPath: '/advice/', leakText: '<a href="/?ezb_page&#x3d;roller-blinds">dev</a>', expectedError: '/advice/ leaked development' });
await check({ name: 'indexable case variant rejected', indexable: true, leakPath: '/contact/', leakText: '<a href="/?EZB_PAGE=roller-blinds">dev</a>', expectedError: '/contact/ leaked development' });
await check({ name: 'indexed blog numeric entity query rejected', indexable: true, leakPath: '/roller-blinds-blockout-vs-sunscreen/', leakText: '<a href="/?ezb&#x5f;page&#61;roller-blinds">dev</a>', expectedError: '/roller-blinds-blockout-vs-sunscreen/ indexed development transport leak' });
await check({ name: 'staging wildcard block with inline comments', robotsTextOverride: 'User-agent: * # all bots\nDisallow: / # whole site' });
await check({ name: 'staging consecutive agents share rules', robotsTextOverride: 'User-agent: ExampleBot\nUser-agent: *\nDisallow: /' });
await check({ name: 'staging wildcard before named agent shares rules', robotsTextOverride: 'User-agent: *\nUser-agent: ExampleBot\nDisallow: /' });
await check({ name: 'staging wildcard /*$ blocks entire site', robotsTextOverride: 'User-agent: *\nDisallow: /*$' });
await check({ name: 'staging named bot only does not protect all crawlers', robotsTextOverride: 'User-agent: ExampleBot\nDisallow: /\nUser-agent: *\nAllow: /', expectedError: '/robots.txt does not block the entire site' });
await check({ name: 'staging root-only disallow is insufficient', robotsTextOverride: 'User-agent: *\nDisallow: /$', expectedError: '/robots.txt does not block the entire site' });
await check({ name: 'staging inline-comment Allow exception rejected', robotsTextOverride: 'User-agent: *\nDisallow: / # whole site\nAllow: /private # exception', expectedError: '/robots.txt does not block the entire site' });
await check({ name: 'indexable inline-comment global block rejected', indexable: true, robotsTextOverride: 'User-agent: * # bots\nDisallow: / # whole site', expectedError: '/robots.txt blocks the entire site' });
await check({ name: 'indexable named bot block not global', indexable: true, robotsTextOverride: 'User-agent: ExampleBot\nDisallow: /\n\nUser-agent: *\nAllow: /' });
await check({ name: 'staging commented-out rules are not protection', robotsTextOverride: '# User-agent: *\n# Disallow: /\nUser-agent: *\nAllow: /', expectedError: '/robots.txt does not block the entire site' });
await check({ name: 'staging wildcard group after blank line', robotsTextOverride: 'User-agent: ExampleBot\nDisallow: /private\n\nUser-agent: *\nDisallow: /' });
await check({ name: 'indexable percent-encoded underscore in dev query rejected', indexable: true, leakPath: '/products/', leakText: '<a href="/?ezb%5Fpage=products">Dev</a>', expectedError: '/products/ leaked development' });
await check({ name: 'indexable percent-encoded equals in dev query rejected', indexable: true, leakPath: '/products/', leakText: '<a href="/?ezb_page%3Dproducts">Dev</a>', expectedError: '/products/ leaked development' });
await check({ name: 'indexable double-percent-encoded dev query rejected', indexable: true, leakPath: '/products/', leakText: '<a href="/?ezb%255Fpage%253Dproducts">Dev</a>', expectedError: '/products/ leaked development' });
await check({ name: 'staging percent-encoded dev query rejected without opt-in', leakPath: '/advice/', leakText: '<a href="/?ezb%5fpage=advice">Dev</a>', expectedError: '/advice/ leaked development' });
await check({ name: 'indexable numeric entity encoded percent rejected', indexable: true, leakPath: '/contact/', leakText: '<a href="/?ezb&#37;5Fpage=contact">Dev</a>', expectedError: '/contact/ leaked development' });
await check({ name: 'indexable named entity key and equals rejected', indexable: true, leakPath: '/products/', leakText: '<a href="/?ezb&lowbar;page&equals;products">Dev</a>', expectedError: '/products/ leaked development' });
await check({ name: 'staging named entity equals rejected', leakPath: '/advice/', leakText: '<a href="/?ezb_page&equals;advice">Dev</a>', expectedError: '/advice/ leaked development' });
await check({ name: 'indexable named percent entity rejected', indexable: true, leakPath: '/contact/', leakText: '<a href="/?ezb&lowbar;page&percnt;3Dcontact">Dev</a>', expectedError: '/contact/ leaked development' });
await check({ name: 'indexable mixed numeric and named entities rejected', indexable: true, leakPath: '/products/', leakText: '<a href="/?ezb&#95;page&equals;products">Dev</a>', expectedError: '/products/ leaked development' });
await check({ name: 'staging comment-only line preserves wildcard group', robotsTextOverride: 'User-agent: *\n# guidance for crawlers\nDisallow: /' });
await check({ name: 'indexable comment-only line preserves wildcard block', indexable: true, robotsTextOverride: 'User-agent: *\n# guidance for crawlers\nDisallow: /', expectedError: '/robots.txt blocks the entire site' });
console.log('EZB_HOST_READINESS_GUARD_TEST_PASS cases=62');
