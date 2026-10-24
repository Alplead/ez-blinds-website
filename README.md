# EZ Blinds & Shutters Website

Public engineering repository for the EZ Blinds & Shutters WordPress website.

## Architecture

- WordPress-compatible clean rebuild
- Gutenberg / block-pattern first
- `ezb-theme` for presentation, templates, global styles and patterns
- `ezb-core` for site-specific content types and reusable functionality
- GitHub for source code, tests and release artifacts

## Repository scope

This repository contains website source code and generic development/QA tooling.

It intentionally does **not** contain:

- production or staging credentials
- API keys or access tokens
- customer records or enquiries
- production database exports
- raw/private media masters
- internal account, billing or handoff records

## Development

The included development container and Docker Compose stack provide a disposable local WordPress environment.

Any credentials in local/CI fixtures are development-only and must never be reused for an Internet-facing staging or production environment.

## Guardrails

- No production mutation from repository workflows.
- No secrets, production database dumps or credential files.
- No unverified customer or business claims in public-facing code/content.
- Raw media masters remain outside Git.
- Prefer native WordPress capabilities over unnecessary plugin sprawl.
