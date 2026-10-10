# EZ BNS — Release Evidence Matrix (working v1)

Status: engineering checklist only. Not Owner acceptance, launch permission, or proof that an untested production host is ready.

## Rules

- Each release claim must cite an exact commit SHA and a reproducible run/artifact or real-world Owner evidence. A green CI run for an older SHA is not valid for a newer SHA.
- The development Codespaces WordPress instance is disposable; it is not a persistent public staging host.
- Keep PR #1 Draft and main/production unchanged until the applicable explicit Owner authority.
- If a check is unavailable, record BLOCKED or NOT_TESTED rather than PASS. Never infer email delivery, media rights, business claims or hosting configuration from code alone.

## Verification matrix

| Gate | Minimum evidence | Current classification | Next bounded action |
| --- | --- | --- | --- |
| Source and CI | Exact feature head; Quality, Runtime Smoke, Release Install Smoke all successful on same head | HISTORICAL PASS at 52d38b5035204e12bd24cf174c73967d25936bf0 (2026-10-10); any later head requires its own three checks | Fresh-check PR head and three CI runs |
| Install package | Artifact tied to exact head; install smoke and expiry recorded | HISTORICAL PASS at 52d38b5035204e12bd24cf174c73967d25936bf0; artifact 11667861037 expires 2026-10-24T11:00:53Z | Verify artifact for each new head |
| Sitemap | Owner accepts top navigation, Products subpages, Blog placement, Service Areas entry | APPROVED_NAV_ONLY — Owner D-017 on 2026-10-10 approves A/B/C navigation and supporting Service Areas placement; NOT geographic coverage, copy, layout or publication | Keep section-order, content and launch gates separate |
| Page sections | Owner accepts sequence for Home, Products, product pages, Projects, Advice, About, Contact | OWNER_REVIEW_PENDING | Produce page-order comparison after sitemap decision |
| Real media | Selected image bundle checksum, mapping to actual product, alt text, privacy and publish rights | PARTIAL — approved V2.3 ZIP verified offline 2026-10-10 (SHA-256 3d3a2a2a66c66e3d8a37dbcda2de96900ba9f939f7799f887725f27799faa142; 25/25 WebP decoded, manifest hashes/dimensions/size/EXIF checked; 25 names match plugin registry). This does **not** prove persistent WordPress import, browser QA, or publication rights. | Run import and visual checks on approved persistent staging; retain Owner media gate |
| Sheer gallery | Real approved sheer images, or Owner explicitly chooses hero-only | OWNER_DECISION_PENDING | Do not fill with unrelated images |
| Motorisation | Approved genuine photos/video and verified current systems/controls | OWNER_EVIDENCE_PENDING | Leave unsupported claims unpublished |
| Retractable flyscreen video | Explicit publication/privacy decision plus approved web derivative | OWNER_DECISION_PENDING | Keep video development-only |
| Copy and claims | Owner-approved product facts, warranties, material, origin, size limits, service coverage, project stories | OWNER_EVIDENCE_PENDING | Keep drafts non-authoritative |
| Blog and Advice | No duplicated search intent; factual review; publish status and images approved | PARTIAL | Keep five starter posts development-only |
| SEO and retired URLs | Canonical/noindex/robots checks; redirect register and crawl reconciliation; truthful retirement or 410 | PARTIAL | Test against final host; never blanket redirect retired products to Home |
| Persistent staging | Real WordPress staging host, correct HTTPS, no dev transport, expected indexability and robots behavior | NOT_TESTED | Await host availability/authority; run host-readiness guard |
| Contact email | End-to-end exact-token message received at intended mailbox; spam and failure path verified | NOT_TESTED | Run real receipt test when staging mail transport is configured |
| Form upload | Approved privacy/storage/retention design and tested file handling if enabled | DEFERRED | Keep photo upload disabled until approved |
| Visual acceptance | Owner checks desktop/mobile, navigation, content, imagery, motion, accessibility | OWNER_REVIEW_PENDING | Perform after sitemap and section-order approval |
| Cutover and rollback | Backups, DNS/hosting access, rollback rehearsal, Owner explicit go/no-go | NOT_AUTHORIZED | Do not purchase, merge, switch DNS or deploy production |

## Next safe engineering tasks independent of Owner decisions

1. Verify feature-head CI and release artifact remain exact-SHA matched; treat new commits as invalidating prior PASS.
2. Check that development-only video, sample project data, unapproved copy and noindex/robots markers cannot escape into an indexable release; add deterministic regressions if any gap is found.
3. Audit image manifest and templates for broken paths, unsupported galleries, lazy-loading/alt-text regressions and mobile navigation accessibility.
4. Reconcile internal links and retired-route behavior without changing final redirect decisions that depend on Owner evidence.
5. Prepare an Owner page-section review packet, clearly marked provisional, after sitemap/hierarchy feedback.

## Last reconciled baseline

Feature branch: `feature/vertical-slice-v1`; PR #1 Draft. Last verified historical head `52d38b5035204e12bd24cf174c73967d25936bf0`, Quality 38046826674, Runtime Smoke 38046826685, Release Install Smoke 38046826683 all PASS on 2026-10-10; artifact 11667861037. This is historical once a newer commit is created. The next code commit invalidates this as a current-head claim. Owner D-017 navigation approved; Owner visual preview and page-section-order acceptance remain open.
