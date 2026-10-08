import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(new URL('./host-readiness.mjs', import.meta.url));
const routes = new Set(['/', '/roller-blinds/', '/retractable-flyscreens/', '/plantation-shutters/', '/projects/', '/advice/', '/contact/']);

async function check({ name, indexable = false, allowDevTransport = false, missingNoindexPath = '', forceNoindexPath = '', leakPath = '', markerPath = '', redirectPath = '', expectedError = '' }) {
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
      res.end('wp-sitemap-posts-page-1.xml wp-sitemap-posts-ezb_project-1.xml');
      return;
    }
    if (pathname === redirectPath) { res.writeHead(302, { location: '/' }); res.end(); return; }
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
      const env = { ...process.env, EZB_BASE_URL: `http://127.0.0.1:${server.address().port}/`, EZB_ALLOW_HTTP: '1', EZB_EXPECT_INDEXABLE: indexable ? '1' : '0', EZB_EXPECT_REDIRECTS: '0', EZB_ALLOW_DEV_TRANSPORT: allowDevTransport ? '1' : '0' };
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
await check({ name: 'indexable development marker rejected', indexable: true, markerPath: '/projects/', expectedError: '/projects/ contains development-only publication marker' });
await check({ name: 'indexable secondary noindex rejected', indexable: true, forceNoindexPath: '/projects/', expectedError: '/projects/ is unexpectedly noindex' });
await check({ name: 'canonical route redirected to home rejected', redirectPath: '/contact/', expectedError: '/contact/ resolved to unexpected route /' });
console.log('EZB_HOST_READINESS_GUARD_TEST_PASS cases=9');
