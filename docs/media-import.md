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
