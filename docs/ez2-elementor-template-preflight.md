# EZ2 Elementor controlled-export preflight

This is a read-only, synthetic-only engineering guard for a future EZ2 A-scheme migration. It does not install Elementor, migrate WordPress content, resolve private photographs, prove a live Elementor feature, or validate LocalWP.

Run: python3 scripts/ez2_elementor_export_check.py CONTROLLED_EXPORT.json
Tests: python3 scripts/test_ez2_elementor_export_check.py

The controlled export has title, type=page, version, page_settings and content. Supported node types are container, section, column and widget. Supported widgets are heading, text-editor, image, button, divider, spacer, icon and image-carousel. Unsupported widgets and malformed nodes fail closed. Media must use ez2-media://approved-slot placeholders rather than URLs or private file bytes. These placeholders are not directly importable: a separately approved importer must map them against the target site's private media library.

The test's synthetic slideshow timing is not evidence of Elementor Free feature availability. Before any real import: pin an official plugin version, verify its licensing and compatibility in a real isolated WordPress runtime, add full backup/rollback and content conflict handling, validate visual/mobile results, and obtain the Owner's authorisation to create an isolated EZ2 LP site. Never write to the existing production site, historical T2, or EZ BNS New Dev from this tool.
