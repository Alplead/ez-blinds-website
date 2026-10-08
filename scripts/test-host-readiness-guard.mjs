import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(new URL('./host-readiness.mjs', import.meta.url));
const routes = new Set(['/', '/roller-blinds/', '/retractable-flyscreens/', '/plantation-shutters/', '/projects/', '/advice/', '/contact/', '/projects/prototype-roller-blinds-project/', '/roller-blinds-blockout-vs-sunscreen/']);

async function check({ name, indexable = false, allowDevTransport = false, missingNoindexPath = '', forceNoindexPath = '', leakPath = '', markerPath = '', redirectPath = '', badRedirectQueryPath = '', badGonePath = '', expectRedirects = false, expectedError = '' }) {
  const server = createServer((req, res) => {
    const pathname = new URL(req.url, 'http://127.0.0.1').pathname;
    const origin = `http://127.0.0.1:${server.address().port}`;
    if (pathname === '/robots.txt') {
      res.writeHead(200, { 'content-type': 'text/plain' });
      res.end(indexable ? 'User-agent: *\nAllow: /' : 'User-agent: *\nDisallow: /');
      return;
    }
    if (pathname === '/wp-sitemap.xml') {
      res.writeHead(indexable ? 200 : 404, { 'content-type': 'text/xml' });
      res.end('<sitemapindex>' + ['page', 'post', 'ezb_project'].map(type =>
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
    const html = '<link rel="canonical" href="' + origin + pathname + '">' +
      '<meta name="robots" content="' + (noindex ? 'noindex, nofollow' : 'index, follow') + '">' +
      (leakPath === pathname ? '<a href="/?ezb_page=roller-blinds">dev</a>' : '') +
      (markerPath === pathname ? '<div>Prototype project</div>' : '');
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

await check({ name: 'staging all seven routes noindex' });
await check({ name: 'secondary route missing noindex rejected', missingNoindexPath: '/contact/', expectedError: '/contact/ lacks noindex protection' });
await check({ name: 'staging dev query leak rejected', leakPath: '/advice/', expectedError: '/advice/ leaked development' });
await check({ name: 'prototype runtime explicit dev transport opt-in', allowDevTransport: true, leakPath: '/advice/' });
await check({ name: 'non-indexable development marker tolerated', markerPath: '/projects/' });
await check({ name: 'indexable release mode clean', indexable: true });
await check({ name: 'indexable opt-in rejected', indexable: true, allowDevTransport: true, expectedError: 'indexable mode forbids development ezb_page transport opt-in' });
await check({ name: 'indexable dev query leakage rejected', indexable: true, leakPath: '/advice/', expectedError: '/advice/ leaked development' });
await check({ name: 'indexable development marker rejected', indexable: true, markerPath: '/projects/', expectedError: '/projects/ contains development-only publication marker' });
await check({ name: 'indexable secondary noindex rejected', indexable: true, forceNoindexPath: '/projects/', expectedError: '/projects/ is unexpectedly noindex' });
await check({ name: 'canonical route redirected to home rejected', redirectPath: '/contact/', expectedError: '/contact/ resolved to unexpected route /' });
await check({ name: 'indexable prototype project in sitemap rejected', indexable: true, markerPath: '/projects/prototype-roller-blinds-project/', expectedError: '/projects/prototype-roller-blinds-project/ indexed development-only publication marker' });
await check({ name: 'indexable starter blog in sitemap rejected', indexable: true, markerPath: '/roller-blinds-blockout-vs-sunscreen/', expectedError: '/roller-blinds-blockout-vs-sunscreen/ indexed development-only publication marker' });
await check({ name: 'indexable starter blog dev transport rejected', indexable: true, leakPath: '/roller-blinds-blockout-vs-sunscreen/', expectedError: '/roller-blinds-blockout-vs-sunscreen/ indexed development transport leak' });
await check({ name: 'all verified 301 and retired 410 routes', expectRedirects: true });
await check({ name: 'legacy 301 with query rejected', expectRedirects: true, badRedirectQueryPath: '/portfolio/', expectedError: '/portfolio/ -> expected Location' });
await check({ name: 'retired URL redirect rejected', expectRedirects: true, badGonePath: '/roman-blinds/', expectedError: '/roman-blinds/ -> expected HTTP 410' });
await check({ name: 'legacy 302 rejected', expectRedirects: true, redirectPath: '/portfolio/', expectedError: '/portfolio/ -> expected 301' });
console.log('EZB_HOST_READINESS_GUARD_TEST_PASS cases=18');
