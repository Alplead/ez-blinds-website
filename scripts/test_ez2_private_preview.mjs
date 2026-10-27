import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { createPreviewServer } from '../tools/ez2-private-preview/auth-proxy.mjs';

const password = 'only-a-temporary-secret-123456789';
const host = 'sb-testcase123.vercel.run';
let cases = 0;
const upstream = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain', 'Set-Cookie': 'should-never-leave=1' });
  res.end(JSON.stringify({
    path: req.url,
    auth: req.headers.authorization || null,
    cookie: req.headers.cookie || null,
    host: req.headers.host,
    forwardedProto: req.headers['x-forwarded-proto'],
    forwardedFor: req.headers['x-forwarded-for'] || null,
  }));
});
upstream.listen(0, '127.0.0.1');
await once(upstream, 'listening');
const proxy = createPreviewServer({
  password, publicHost: host, upstreamPort: upstream.address().port,
});
proxy.listen(0, '127.0.0.1');
await once(proxy, 'listening');
const url = 'http://127.0.0.1:' + proxy.address().port;
const auth = 'Basic ' + Buffer.from('ez2-review:' + password).toString('base64');

async function check(path, init, code, label) {
  const r = await fetch(url + path, init);
  assert.equal(r.status, code, label);
  assert.equal(r.headers.get('cache-control'), 'private, no-store', label);
  assert.match(r.headers.get('x-robots-tag'), /noindex/, label);
  cases++;
  return r;
}
try {
  const unauth = await check('/', {}, 401, 'anonymous blocked');
  assert.match(unauth.headers.get('www-authenticate'), /Basic/);
  await check('/', {headers: {'Authorization': 'Basic ' + Buffer.from('ez2-review:invalid').toString('base64')}}, 401, 'bad password blocked');
  await check('/', {headers: {'Authorization': 'Basic @@garbage@@'}}, 401, 'invalid authentication blocked');
  const ok = await check('/?preview=1', {headers: {
    Authorization: auth, Cookie: 'fake-session=123', 'X-Forwarded-For':'10.0.0.1',
    'X-Forwarded-Proto': 'http', 'X-Forwarded-Host':'other.example',
  }}, 200, 'authorised read-only homepage');
  assert.equal(ok.headers.get('set-cookie'), null);
  const echo = await ok.json();
  assert.deepEqual(echo, {path:'/?preview=1',auth:null,cookie:null,host,forwardedProto:'https',forwardedFor:null});
  cases++;
  await check('/wp-admin/', {headers:{Authorization:auth}}, 403, 'admin blocked');
  await check('/wp-login.php', {headers:{Authorization:auth}}, 403, 'login blocked');
  await check('/wp-json/wp/v2/users', {headers:{Authorization:auth}}, 403, 'REST API blocked');
  await check('/?rest_route=/wp/v2/users', {headers:{Authorization:auth}}, 403, 'REST route parameter blocked');
  await check('/xmlrpc.php', {headers:{Authorization:auth}}, 403, 'XMLRPC blocked');
  await check('/contact/', {method:'POST',headers:{Authorization:auth}}, 403, 'inquiries cannot send');
  await check('/?x=y', {method:'HEAD',headers:{Authorization:auth}}, 200, 'HEAD allowed');
  assert.throws(()=>createPreviewServer({password:'short',publicHost:host,upstreamPort:8081}), /configuration not safe/); cases++;
  assert.throws(()=>createPreviewServer({password,publicHost:'ezbns.com.au',upstreamPort:8081}), /configuration not safe/); cases++;
  assert.throws(()=>createPreviewServer({password,publicHost:'sb-ok.vercel.run.evil.example',upstreamPort:8081}), /configuration not safe/); cases++;
  assert.throws(()=>createPreviewServer({password,publicHost:host,upstreamPort:80}), /configuration not safe/); cases++;
  console.log('EZ2_PRIVATE_PREVIEW_AUTH_PASS cases=' + cases);
} finally {
  proxy.close();
  upstream.close();
}
