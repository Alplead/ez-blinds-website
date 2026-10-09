import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(new URL('./link-check.mjs', import.meta.url));
async function check(name, mode, expectedFailure = '') {
  const server = createServer((req, res) => {
    const path = new URL(req.url, 'http://localhost').pathname;
    if ((mode === 'redirect' && path === '/contact/') || (mode === 'discovered-redirect' && path === '/redirected/')) {
      res.writeHead(302, { location: '/' }); res.end(); return;
    }
    if (path === '/missing/') { res.writeHead(404); res.end('missing'); return; }
    if (path === '/contact/' && mode === 'not-html') {
      res.writeHead(200, { 'content-type': 'application/json' }); res.end('{}'); return;
    }
    if (path === '/contact/' && mode === 'no-content') {
      res.writeHead(204); res.end(); return;
    }
    if (path === '/empty/' && mode === 'discovered-empty') {
      res.writeHead(204); res.end(); return;
    }
    if (path === '/partial/' && mode === 'discovered-partial') {
      res.writeHead(206, { 'content-type': 'text/html' }); res.end('<html></html>'); return;
    }
    if (path === '/json/' && mode === 'discovered-json') {
      res.writeHead(200, { 'content-type': 'application/json' }); res.end('{}'); return;
    }
    if (path === '/brochure.pdf' && mode === 'discovered-file') {
      res.writeHead(200, { 'content-type': 'application/pdf' }); res.end('%PDF-test'); return;
    }
    res.writeHead(200, { 'content-type': 'text/html' });
    const link = path === '/' && mode === 'unsafe-script' ? '<a href="javascript:alert(1)">Unsafe</a>' :
      path === '/' && mode === 'unsafe-data' ? '<a href="data:text/html,unsafe">Unsafe</a>' :
      path === '/' && mode === 'unsafe-entity' ? '<a href="java&#x73;cript:alert(1)">Unsafe</a>' :
      path === '/' && mode === 'unsafe-whitespace' ? '<a href="java&#x09;script:alert(1)">Unsafe</a>' :
      path === '/' && mode === 'unsafe-unquoted' ? '<a href=javascript:alert(1)>Unsafe</a>' :
      path === '/' && mode === 'data-unquoted' ? '<a href=data:text/html,x>Unsafe</a>' :
      path === '/' && mode === 'broken-unquoted' ? '<a href=/missing/>Broken</a>' :
      path === '/' && mode === 'transport-unquoted' ? '<a href=/products/?ezb_page=products>Dev</a>' :
      path === '/' && mode === 'data-href-decoy' ? '<a data-href="/missing/">No navigation</a>' :
      path === '/' && mode === 'quoted-label-decoy' ? '<a aria-label="href=/missing/" href="/contact/">Contact</a>' :
      path === '/' && mode === 'discovered-redirect' ? '<a href="/redirected/">Wrong destination</a>' :
      path === '/' && mode === 'discovered-empty' ? '<a href="/empty/">Empty</a>' :
      path === '/' && mode === 'discovered-partial' ? '<a href="/partial/">Partial</a>' :
      path === '/' && mode === 'discovered-json' ? '<a href="/json/">Wrong content</a>' :
      path === '/' && mode === 'discovered-file' ? '<a href="/brochure.pdf">Download PDF</a>' :
      path === '/' && mode === 'broken' ? '<a href="/missing/">Broken</a>' :
      path === '/' && mode === 'transport' ? '<a href="/products/?ezb_page=products">Development</a>' : '';
    res.end('<!doctype html><html><body>' + link + '</body></html>');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let result;
  try {
    result = await new Promise((resolve, reject) => {
      const child = spawn(process.execPath, [script], {
        env: { ...process.env, EZB_BASE_URL: 'http://127.0.0.1:' + server.address().port + '/', EZB_LINK_CHECK_MAX: '120' }
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
    assert.ok(result.output.includes(expectedFailure), name + ': wrong failure ' + result.output);
  } else {
    assert.equal(result.code, 0, name + ': ' + result.output);
    assert.ok(result.output.includes('EZB_LINK_CHECK_PASS'));
  }
  console.log('PASS ' + name);
}
await check('clean internal links', 'clean');
await check('required route redirect to Home rejected', 'redirect', 'unexpectedly redirected to');
await check('discovered link redirect to Home rejected', 'discovered-redirect', 'unexpectedly redirected to');
await check('broken internal link rejected', 'broken', 'HTTP 404');
await check('development transport link rejected', 'transport', 'development ezb_page links');
await check('required public route must return HTML', 'not-html', 'required route expected text/html');
await check('required public route must not return 204', 'no-content', 'required route expected HTTP 200');
await check('javascript href rejected', 'unsafe-script', 'unsafe internal link protocol: javascript:');
await check('data href rejected', 'unsafe-data', 'unsafe internal link protocol: data:');
await check('HTML-encoded javascript href rejected', 'unsafe-entity', 'unsafe internal link protocol: javascript:');
await check('whitespace-obfuscated javascript href rejected', 'unsafe-whitespace', 'unsafe internal link protocol: javascript:');
await check('discovered link must not return 204', 'discovered-empty', 'internal link expected HTTP 200');
await check('discovered link must not return 206', 'discovered-partial', 'internal link expected HTTP 200');
await check('discovered page must serve HTML', 'discovered-json', 'internal page expected text/html');
await check('explicit file link may serve PDF', 'discovered-file');
await check('unquoted javascript href rejected', 'unsafe-unquoted', 'unsafe internal link protocol: javascript:');
await check('unquoted data href rejected', 'data-unquoted', 'unsafe internal link protocol: data:');
await check('unquoted broken internal href rejected', 'broken-unquoted', 'HTTP 404');
await check('unquoted development transport rejected', 'transport-unquoted', 'development ezb_page links');
await check('data-href is not a real navigation link', 'data-href-decoy');
await check('href in quoted aria-label cannot override actual href', 'quoted-label-decoy');
console.log('EZB_LINK_CHECK_GUARD_TEST_PASS cases=21');
