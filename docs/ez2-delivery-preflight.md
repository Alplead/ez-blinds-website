# EZ2 isolated delivery contract (engineering preflight only)

This integration tool combines existing Elementor-export, third-party-plugin metadata, and Owner-edit conflict guards into a **read-only** exact-SHA delivery plan. It does not install/activate Elementor, change any WordPress site, download or import private media, back up/restore databases, verify a live runtime, or authorise publication.

Run: python3 scripts/ez2_delivery_preflight.py CONTRACT_DIRECTORY EXPECTED_EXACT_40_CHARACTER_SHA

Exit 0 means structurally ready for **future runtime testing only**; exit 2 means blocked by an unresolved media slot, content conflict or missing plugin checksum; exit 1 means malformed/unsafe input. Test: python3 scripts/test_ez2_delivery_preflight.py.

The contract directory contains delivery.json, installed.json, a plugin lock JSON and one controlled Elementor export JSON per template. All paths are single lower-case JSON filenames, not URLs. delivery.json has exactly schema_version: 1, target_site: "ez2-isolated-only", source_sha, plugin_lock, templates and media_slots. Each template declares a managed key, file, and nullable previous_sha256 baseline. The installed.json document contains only managed keys and SHA-256 digests, not Owner content. The plugin lock follows ez2_plugin_dependency_check.py schema. media_slots lists approved symbolic placeholders (e.g. hero-one), not private file bytes, media URLs, customer identifiers or attachment IDs.

The content plan now reports both `unmanaged_existing_count` and the sorted `unmanaged_existing_keys`. These are existing Owner-managed records omitted from the candidate template set: they are disclosed for review and left untouched, never silently deleted. The upgrade linkage rejects missing, duplicated, unordered or contradictory keys rather than trusting a summary count. The list contains only managed record keys, not Owner text or private media.

No dry-run PASS proves plugin provenance, archive hash verification, Elementor Free feature compatibility, Elementor runtime import, media matching, Owner visual acceptance, LocalWP installation, backup, or rollback. Those require separate isolated WordPress integration and Owner evidence. Existing WPC production, T2, EZ BNS New Dev and main remain NO-WRITE. An isolated EZ2 LP site has not been authorised or created by this code.

## Upgrade linkage and disposable scratch replay

`python3 scripts/ez2_upgrade_gate.py CONTRACT_DIR BACKUP_DIR INSTALLED_SHA CANDIDATE_SHA` now requires the installed-SHA backup to pass byte/structure checks **and** an auto-deleted, private scratch replay of its uploads, plugins and theme files before classifying the candidate delivery preflight. SQL is checked as a compressed backup but **never executed**. This is not a WordPress restore, database recovery test, LocalWP installation, or deployment permission; those remain separately gated. CI uses synthetic fixtures only. The gate returns explicit `scratch_file_replay_verified` and `scratch_deleted` flags; a missing or unsafe replay fails closed.

## Synthetic WordPress database restore rehearsal in CI

Release Install Smoke now clones its **synthetic CI WordPress database** through a compressed SQL dump into a separately named, disposable MariaDB database, compares WordPress table and row counts plus the home URL, verifies the source database remained intact, and deletes the clone and temporary dump. It is opt-in and guarded to the fixed GitHub Actions release fixture. The source database is never dropped. This is a genuine SQL import check **only in disposable CI**; it is not a restore of an Owner backup, does not touch LocalWP, and cannot establish full-site rollback or one-click readiness. The actual isolated EZ2 LocalWP restore remains Owner-gated and unverified.


The synthetic SQL restore rehearsal now additionally compares SHA-256 fingerprints of ordered, data-only SQL dumps before backup, after restoration, and again on the original database. Matching table counts alone can miss modified row values; mismatched fingerprints fail closed without printing SQL or credentials. This is still **synthetic CI-only** evidence, not an Owner LocalWP rollback test or installation authority.

## Verified release-to-delivery bridge (no installation)

`python3 scripts/ez2_release_delivery_bridge.py RELEASE_DIR EXACT_SHA PLUGIN_LOCK_JSON INSTALLED_DIGESTS_JSON [PREVIOUS_SHA256|-]` now verifies the exact-head cross-artifact catalog and Elementor candidate archive, checks the pinned Elementor Free version, and derives a managed-content create/update/unchanged/conflict plan from a digest-only installed snapshot. Exit 0 is **runtime-test planning only**, exit 2 is blocked (including missing official plugin archive checksum), and exit 1 is invalid input. The optional previous digest is a trusted, previously recorded managed-content baseline; without it, an existing changed page is blocked rather than overwritten. No private media mapping, WordPress state, LocalWP installation, official plugin provenance, full-site restore, or Owner approval is inferred. Quality runs synthetic end-to-end regressions; Release Install Smoke checks the real exact-head release bundle with an intentionally unpinned synthetic plugin lock and requires a truthful blocked result.

The delivery preflight also rejects a validated Elementor template if its exact
`version` differs from the approved `plugins.json` Elementor Free version. This
prevents a stand-alone preflight from declaring a cross-version candidate ready;
it does not assert runtime compatibility or authorize installation.

## Disposable theme/core file replacement and fault rollback

`scripts/ez2_ci_file_upgrade.py` verifies the exact-head release catalog, extracts only the two first-party ZIPs into a private auto-deleted scratch directory, then **actually swaps** synthetic installed theme/core directories. It injects a failure after replacing the first component and restores the original synthetic files byte-for-byte; a successful two-component swap is also rolled back in scratch. An unrelated synthetic uploads directory must remain unchanged. Quality exercises malformed ZIP, traversal, Windows case collision, symlink, missing entrypoint and oversized-entry regressions; Release Install Smoke runs the actual release ZIP rehearsal. This is a file-only CI rehearsal, **not** an Owner LocalWP update, Elementor/content installation, database restoration or full-site rollback. It does not accept a destination path and cannot touch any existing site.

## Synthetic database fault-and-recovery rehearsal

Release Install Smoke additionally changes the `home` option **only in the disposable restored clone**, verifies that the changed value and fingerprint differ from the original, destroys the clone, and reimports the verified compressed backup. It then checks table, post, page and option counts, the original home URL, the ordered-data fingerprint and the untouched source database. A second import that fails to recover the original bytes fails CI. This demonstrates a synthetic database rollback scenario; it does **not** restore an Owner LocalWP database, perform a combined files-plus-database transaction, or authorize an EZ2 deployment.


## Verified prior release baseline (not installed-site attestation)

An update can now derive the old managed Elementor content digest from a separately verified, exact-SHA prior release rather than trusting a caller-supplied digest:

`python3 scripts/ez2_release_delivery_bridge.py RELEASE_DIR NEW_SHA PLUGINS_JSON INSTALLED_DIGESTS_JSON --prior-release PRIOR_RELEASE_DIR PRIOR_SHA`

The previous release catalog, release ZIPs and Elementor candidate are checked before deriving the digest. A current installed snapshot differing from the previous candidate remains an Owner-edit conflict. A verified public release **does not prove that release was installed** on LocalWP, nor that the installed snapshot came from WordPress. The preview therefore remains `can_apply=false` with `prior_release_not_attested_as_installed_on_localwp` as an explicit blocker. An isolated-site agent must independently attest installed source, managed content and backup before any write. The older caller-supplied digest form remains diagnostic only and blocks update readiness.

## Pinned official Elementor ZIP installation in disposable release CI

Release Install Smoke now downloads Elementor Free 4.3.4 from the fixed official WordPress.org URL into a private, auto-deleted runner directory. The checked-in isolated-EZ2 dependency lock pins the SHA-256 observed in an earlier successful official-archive inspection; the installer verifies the exact bytes, ZIP structure, plugin entrypoint and version **before** installing and activating the ZIP in the disposable release-installed WordPress staging stack. The CI-only opt-in, exact Git HEAD, verified release catalog, localhost staging identity, and absence of preinstalled Elementor or Elementor Pro are mandatory. No third-party ZIP or private media is committed or uploaded as a release artifact.

This is the first executable pinned-archive third-party plugin installation in the release-stack workflow. It is **not** an isolated EZ2 LocalWP updater, a full plugin rollback, independent publisher-signature attestation, a complete Elementor design/media migration, or Owner publication approval. If WordPress.org changes the ZIP bytes, the pinned hash check fails closed until a new observation and review. The existing combined theme/core + synthetic SQL rollback rehearsal does not yet include third-party plugin file rollback.
