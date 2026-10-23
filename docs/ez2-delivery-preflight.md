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
