# Isolated LocalWP VM preview (Owner's 2026-10-11 direction)

This is **not** WordPress.com production, not the abandoned historical LocalWP site, and not a cloud staging deployment.

## Required isolation

1. In the existing Windows Oracle VM, open LocalWP and **leave every existing site unchanged** (including `T2 Ez Blinds & Shutters`).
2. Create a **new, separate** LocalWP site named `EZ-New-Dev`, with its own database. Open its WP Admin and confirm the site is the newly created one.
3. Download the exact approved GitHub feature revision from the PR #1 release artifact, or the public GitHub source archive pinned to its full 40-character SHA. Never use `main` or a floating branch download for an installation.
4. Extract `wp-content/themes/ezb-theme` and `wp-content/plugins/ezb-core` into the **new site's** `app/public/wp-content/themes` and `app/public/wp-content/plugins`. Back up any existing same-name directories before replacing them. Do not copy `wp-content/uploads`, `wp-config.php`, or any database.
5. In the **new** site's WP Admin, activate the theme and plugin. Review the page/navigation setup before claiming the full site is ready.
6. On the new site's **Media > Add New**, upload the 25 approved WebP files from the existing Drive V2.3 ZIP. This is a private development-only import, **not** permission to publish photos to the public website. Do not upload the ZIP itself to the Media Library.
7. Check Home, all five product pages, gallery, mobile menu, image alt text and Quote/Contact. Count **25 unique attachments**; inspect desktop and mobile. Keep test contact email disabled. Do not claim image acceptance until browser checks pass.

## Updates / rollback

- Record the exact GitHub SHA and three CI results before each update.
- Back up the two code directories of the **new site** and restore them if an update fails.
- No automatic synchronization from GitHub to LocalWP exists yet.
- GitHub public repository must never contain the 25 private image files, customer data or credentials.
- The existing `ezbns.com.au` production site and the historical LocalWP site are strictly no-write.
- The Owner must confirm actual VM/LocalWP installation; cloud CI does not prove it.

## Status

Instructions only. No remote access to the Owner's Windows VM, no completed LocalWP install or visual acceptance is claimed.
