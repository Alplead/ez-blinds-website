#!/usr/bin/env node
// Cloudflare Pages preview security preflight. Never bypasses Access.
const hosts = process.argv.slice(2);
if (hosts.length !== 2) {
  console.error('Usage: node scripts/verify-cloudflare-access.mjs https://PROJECT.pages.dev https://BRANCH.PROJECT.pages.dev');
  process.exit(2);
}
const urls = hosts.map(value => {
  const url = new URL(value);
  if (url.protocol !== 'https:' || !url.hostname.endsWith('.pages.dev') || url.username || url.password || url.search || url.hash) {
    throw new Error('Expected a clean HTTPS *.pages.dev host only');
  }
  return url;
});
if (urls[0].hostname === urls[1].hostname) throw new Error('Root and preview hosts must be different');
let failures = 0;
for (const url of urls) {
  try {
    const response = await fetch(url.href, {
      redirect: 'manual',
      headers: { 'cache-control': 'no-cache', 'accept': 'text/html' },
      signal: AbortSignal.timeout(12000)
    });
    const redirect = response.headers.get('location') || '';
    const target = redirect ? new URL(redirect, url.href) : null;
    const accessTarget = target &&
      (target.hostname.endsWith('.cloudflareaccess.com') || target.pathname.startsWith('/cdn-cgi/access/'));
    if ([301,302,303,307,308].includes(response.status) && accessTarget) {
      console.log('EZB_CF_ACCESS_GUARD_PASS ' + url.hostname + ' status=' + response.status);
    } else {
      failures += 1;
      console.error('EZB_CF_ACCESS_GUARD_FAIL ' + url.hostname +
        ' status=' + response.status + ' reason=no-verified-access-login');
    }
  } catch (err) {
    failures += 1;
    console.error('EZB_CF_ACCESS_GUARD_BLOCKED ' + url.hostname + ' ' + String(err));
  }
}
if (failures) {
  console.error('CLOUDFLARE_DEPLOYMENT_PROHIBITED: one or more Pages hosts lack proven Access');
  process.exit(1);
}
console.log('EZB_CF_ACCESS_PREFLIGHT_PASS both hosts reject unauthenticated visits. Human policy/incognito verification still required.');
