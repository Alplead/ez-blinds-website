import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(new URL('./seo-audit.mjs', import.meta.url));

async function check(name, mode, expectedFailure = '') {
  const server = createServer((req, res) => {
    const path = new URL(req.url, 'http://localhost').pathname;
    if (path === '/contact/' && (mode === 'redirect' || mode === 'off-origin-redirect')) {
      res.writeHead(302, { location: mode === 'redirect' ? '/' : 'https://example.com/not-our-site/' });
      res.end();
      return;
    }
    if (path === '/contact/' && mode === 'non-html') {
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end('{}');
      return;
    }
    if (path === '/contact/' && mode === 'missing-content-type') {
      res.writeHead(200);
      res.end('<html><title>Contact</title></html>');
      return;
    }
    const port = server.address().port;
    const canonical = mode === 'off-origin-canonical' && path === '/contact/'
      ? 'https://example.com/contact/'
      : 'http://127.0.0.1:' + port + path;
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    res.end('<!doctype html><html><head><title>EZB ' + path +
      '</title><link rel="canonical" href="' + canonical + '"></head><body></body></html>');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let result;
  try {
    result = await new Promise((resolve, reject) => {
      const child = spawn(process.execPath, [script], {
        env: { ...process.env, EZB_BASE_URL: 'http://127.0.0.1:' + server.address().port + '/' }
      });
      let output = '';
      child.stdout.on('data', data => { output += data; });
      child.stderr.on('data', data => { output += data; });
      child.on('error', reject);
      child.on('close', code => resolve({ code, output }));
    });
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
  if (expectedFailure) {
    assert.notEqual(result.code, 0, name + ': expected failure');
    assert.ok(result.output.includes(expectedFailure), name + ': wrong failure: ' + result.output);
  } else {
    assert.equal(result.code, 0, name + ': ' + result.output);
    assert.match(result.output, /EZB_SEO_AUDIT_PASS pages=26 uniqueTitles=26/);
  }
  console.log('PASS ' + name);
}

await check('valid routes and canonicals', 'clean');
await check('same-origin redirect rejected', 'redirect', 'unexpected redirect: /');
await check('off-origin redirect rejected without fetching destination',
  'off-origin-redirect', 'unexpected redirect: https://example.com/not-our-site/');
await check('JSON response rejected', 'non-html', 'expected text/html');
await check('missing HTML content-type rejected', 'missing-content-type', 'expected text/html');
await check('off-origin canonical rejected', 'off-origin-canonical', 'canonical left test origin');
console.log('EZB_SEO_AUDIT_GUARD_PASS cases=6');
