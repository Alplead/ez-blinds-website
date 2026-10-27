/**
 * EZ2 temporary preview reverse proxy.
 * No customer data; read-only; secret supplied by the isolated sandbox.
 * Never deploy this as a production front controller.
 */
import http from 'node:http';
import fs from 'node:fs';
import { timingSafeEqual } from 'node:crypto';
import { pathToFileURL } from 'node:url';

const SAFE_HOST = /^sb-[a-z0-9]+\.vercel\.run$/;

export function createPreviewServer({ password, publicHost, upstreamPort = 8081 }) {
  if (typeof password !== 'string' || password.length < 20 ||
      typeof publicHost !== 'string' || !SAFE_HOST.test(publicHost) ||
      !Number.isInteger(upstreamPort) || upstreamPort < 1024 || upstreamPort > 65535) {
    throw new Error('Preview configuration not safe');
  }
  const expected = Buffer.from('ez2-review:' + password);
  const protectedHeaders = {
    'Cache-Control': 'private, no-store',
    'X-Robots-Tag': 'noindex, nofollow, noarchive',
    'Referrer-Policy': 'no-referrer',
    'X-Frame-Options': 'DENY',
    'X-Content-Type-Options': 'nosniff',
  };

  return http.createServer((request, response) => {
    const auth = request.headers.authorization || '';
    let authenticated = false;
    if (auth.startsWith('Basic ')) {
      try {
        const candidate = Buffer.from(auth.slice(6), 'base64');
        authenticated = candidate.length === expected.length && timingSafeEqual(candidate, expected);
      } catch {
        authenticated = false;
      }
    }
    if (!authenticated) {
      response.writeHead(401, {
        ...protectedHeaders,
        'WWW-Authenticate': 'Basic realm="EZ2 private preview", charset="UTF-8"',
      });
      response.end('Private review login required');
      return;
    }

    const path = String(request.url || '/').split('?')[0];
    const blockedPath = /^(?:\/wp-admin(?:\/|$)|\/wp-login\.php$|\/wp-json(?:\/|$)|\/xmlrpc\.php$)/i.test(path);
    const blockedQuery = /(?:^|[?&])rest_route=/i.test(String(request.url || ''));
    if (!['GET', 'HEAD'].includes(request.method) || blockedPath || blockedQuery) {
      response.writeHead(403, protectedHeaders);
      response.end('Preview is read-only');
      return;
    }

    // Never forward the preview password or untrusted reverse-proxy headers.
    const {
      authorization, cookie, 'x-forwarded-for': untrustedFor,
      'x-forwarded-proto': untrustedProto, 'x-forwarded-host': untrustedHost,
      ...safeHeaders
    } = request.headers;
    const upstream = http.request({
      hostname: '127.0.0.1',
      port: upstreamPort,
      path: request.url,
      method: request.method,
      headers: {
        ...safeHeaders,
        host: publicHost,
        'x-forwarded-host': publicHost,
        'x-forwarded-proto': 'https',
      },
    }, (reply) => {
      const { 'set-cookie': droppedCookies, 'www-authenticate': droppedAuth, ...upstreamHeaders } = reply.headers;
      response.writeHead(reply.statusCode || 502, { ...upstreamHeaders, ...protectedHeaders });
      reply.pipe(response);
    });
    upstream.on('error', () => {
      if (!response.headersSent) response.writeHead(502, protectedHeaders);
      response.end('Private preview backend unavailable');
    });
    upstream.end();
  });
}

// Execution is opt-in and restricted to the transient sandbox route.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (process.env.EZ2_PRIVATE_PREVIEW !== 'YES_TEMPORARY_SANDBOX_ONLY' ||
      !process.env.EZ2_PREVIEW_AUTH_FILE ||
      !process.env.EZ2_PREVIEW_HOST) {
    throw new Error('Explicit private-preview sandbox opt-in required');
  }
  const file = process.env.EZ2_PREVIEW_AUTH_FILE;
  const info = fs.lstatSync(file);
  if (!info.isFile() || info.isSymbolicLink() || (info.mode & 0o077) !== 0) {
    throw new Error('Private preview password file must be owner-only and not linked');
  }
  const password = fs.readFileSync(file, 'utf8').trim();
  const server = createPreviewServer({
    password,
    publicHost: process.env.EZ2_PREVIEW_HOST,
    upstreamPort: 8081,
  });
  server.listen(8080, '0.0.0.0', () => console.log('EZ2_PRIVATE_PREVIEW_PROXY_READY'));
}
