# EZ BNS 7 — Independent Private Review Hosting (Cloudflare Free)

Status: PREPARATION ONLY — DO NOT PUBLISH UNTIL ACCESS IS VERIFIED
Owner decision: keep existing WordPress.com Premium, no upgrade, no DNS or ezbns.com.au change.
Created: 2026-10-11 (Australia/Melbourne)

## Two separate environments

- Engineering truth: GitHub feature/vertical-slice-v1 + real WordPress/MariaDB in the existing Codespaces Docker devcontainer on port 8080. This is PHP WordPress, not a static site. Codespaces must be stopped when unused; verify GitHub included usage/billing ceiling before starting.
- Instant inspection: Cloudflare Pages Free serves a STATIC SNAPSHOT of the tested WordPress frontend (HTML, CSS, JavaScript, WebP). It remains online without an active PHP/database server. It does not run WP-admin, plugins' PHP, dynamic search, live forms or outbound emails. It is a review surface only, not a final production host.
- Browser review must never be confused with full release-mode WordPress staging acceptance.

## Before any files, including the 25 V2.3 WebP images, are uploaded

1. Owner creates a Cloudflare Free account, or uses an existing Free account. No paid plan, purchase, credit upgrade, new domain, DNS migration or ezbns.com.au changes.
2. In Workers & Pages, create a Pages **Direct Upload** project with a non-sensitive, text-only placeholder index.html. Do NOT upload customer photos yet. Choose Direct Upload so GitHub source commits do not accidentally publish public assets via a Git integration.
3. In Pages settings enable Cloudflare Access policy for preview deployments (the wildcard preview host). Configure allow-list for Owner's authenticated identity ONLY.
4. Protect the root `<project>.pages.dev` host TOO. Default Pages preview protection does NOT protect the root project host. Official known-issues instructions: modify root wildcard hostname in Access application then re-enable preview policy to create both protected host rules.
5. With a private browser window, verify that an unauthenticated visit to EACH of root and branch preview hosts redirects to Cloudflare Access login; no site content or image URLs may be readable without authentication. Optionally use `node scripts/verify-cloudflare-access.mjs https://PROJECT.pages.dev https://BRANCH.PROJECT.pages.dev`; its checks are defensive corroboration, not a substitute for human incognito testing and an explicit private Access policy.
6. Only after separate evidence for both hosts and exact domain routing is saved may first-party images be uploaded. Cloudflare Pages 'noindex' is NOT privacy protection. Avoid attaching a custom domain.

## From real WordPress to static preview

1. Work only from current, exact-head tested GitHub feature branch. No main merge.
2. On the private Codespaces WordPress environment, load current ezb-theme and ezb-core, verify siteurl/home and CSS render correctly.
3. Retrieve Drive V2.3 media ZIP directly into the private working environment. Source Google Drive ID `1GZjEOoFo6EgCOdCVRjI88hqoCe8xSg9i`, expected SHA-256 `3d3a2a2a66c66e3d8a37dbcda2de96900ba9f939f7799f887725f27799faa142`. Do not commit ZIP or photos into the PUBLIC source repository.
4. Run existing `scripts/staging-media-acceptance.sh <ZIP>` after confirming it is pointed to this isolated development WordPress only. Require 25 unique imported attachments and actual browser image checks. No customer-identifying metadata, private video or unapproved case-study facts.
5. Use the free Simply Static WordPress plugin within the disposable private WordPress environment to export static HTML/CSS/JS/media ZIP. Follow official Cloudflare WordPress static export instructions at https://developers.cloudflare.com/pages/how-to/deploy-a-wordpress-site/. The free plugin requires exporting again after each update; continuous automatic sync does NOT happen just by linking GitHub.
6. Before publishing, inspect extracted site for media and relative link correctness, no external customer-private resources, 200 responses on required routes, CSS computed styles on desktop/mobile, no shortcode leakage. Disable or clearly label static quote/contact form inputs: they cannot deliver email. Put `X-Robots-Tag: noindex, nofollow` and `robots.txt` into the static preview; still require Access.
7. Upload new export using Cloudflare Pages Direct Upload once Access has been independently proved and is still enabled. Refresh the protected preview URL to inspect it. Repeat export and upload following an actual GitHub WordPress source change.

## Update automation — future, NOT YET CONFIGURED

- An unattended GitHub-to-Pages pipeline requires safe GitHub Actions execution of real WordPress, secure delivery of the 25 media ZIP without putting private images in a public Git repository, a Cloudflare token limited to the one Pages project, deployment policy checks, and Access login verification before a publish. None of this can be assumed connected merely because GitHub/Vercel is connected.
- Do not create a workflow that deploys from the public source repo with the private media in its Git history. Do not make Pages Git integration publish the branch by default.
- Until the protected deploy transport is installed and verified, Owner will need to submit/import each rebuilt static export. Viewing already uploaded snapshots is instant; updates are only visible after redeployment.
- Dynamic contact-form mail delivery, WP admin and publication readiness remain later gates on a real WP runtime.

## Costs / rollback / ownership

- Cloudflare Pages Free currently documents 500 builds per month; free-tier restrictions and any existing Cloudflare billing configuration must be checked in Owner account. Avoid Pages Functions, Workers, paid storage and add-ons for this purely static review use.
- Creating a private Pages preview does NOT require purchasing a domain or altering WordPress.com Premium.
- If broken, stop publishing new previews or roll back to previous Pages deployment; never use WordPress.com's Push to Production.
- The public `ezbns.com.au` website and GitHub `main` stay untouched.
- Existing short-lived Vercel Sandbox remains stopped and is not part of this private review launch.

## Current verified status

- Source PR #1 at baseline `b22b1f56764ba4ed70ec9256d355a7028d63b127` has Quality / Runtime Smoke / Release Install Smoke all SUCCESS as of this preparation (fresh-read before future use).
- Exactly 25 V2.3 images have been recovered and hash-verified locally, and a local-only photo review ZIP has been created separately for Owner.
- Cloudflare account connection, Pages project creation, Access, online upload and live private URL: NOT YET EXECUTED (no connected Cloudflare management account/tool).
