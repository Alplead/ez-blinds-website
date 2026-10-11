# Media import workflow

The canonical media masters remain in Google Drive.

This repository stores only code and media-processing instructions.

## Development import

When approved web derivatives are available locally inside the Codespace workspace:

```bash
bash scripts/import-media.sh <file-or-folder>
```

The script imports JPG, JPEG, PNG and WebP files into the development WordPress Media Library.

## Rules

- Do not commit raw media masters into Git.
- Prefer WebP derivatives for development display.
- Strip EXIF/GPS metadata before public publication.
- Use genuine EZ project media only when provenance is known.
- Do not mix photographs from different installations into one case study.

## Current Owner decision (2026-10-11)

WordPress.com Staging was cancelled. Do not request a WordPress.com Staging verification or import as part of this workflow. Keep the 25 WebP derivatives out of the public GitHub repository until publication permission is confirmed. For private development, import them only into an isolated local WordPress environment and verify rendering there; the existing ezbns.com.au site must remain unchanged.
