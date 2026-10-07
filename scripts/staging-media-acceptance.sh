#!/usr/bin/env bash
set -euo pipefail

BUNDLE="${1:-}"
EXPECTED_SHA="${EZB_MEDIA_BUNDLE_SHA256:-3d3a2a2a66c66e3d8a37dbcda2de96900ba9f939f7799f887725f27799faa142}"

if [[ -z "$BUNDLE" || ! -f "$BUNDLE" ]]; then
  echo "Usage: $0 /path/to/EZB_WEB_DERIVATIVES_V2_3_PUBLIC_SELECTED_IMPORT_BUNDLE.zip" >&2
  exit 2
fi

if ! command -v wp >/dev/null 2>&1; then
  echo "wp (WP-CLI) is required on the staging host." >&2
  exit 3
fi

if ! wp core is-installed --allow-root >/dev/null 2>&1; then
  echo "Run this from the staging WordPress root (or configure WP-CLI accordingly)." >&2
  exit 4
fi

ACTUAL_SHA="$(sha256sum "$BUNDLE" | awk '{print $1}')"
if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
  echo "V2.3 bundle checksum mismatch." >&2
  echo "expected=$EXPECTED_SHA" >&2
  echo "actual=$ACTUAL_SHA" >&2
  exit 5
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKER="$ROOT/scripts/media-library-readiness.php"
if [[ ! -f "$CHECKER" ]]; then
  echo "Media readiness checker not found: $CHECKER" >&2
  exit 6
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
unzip -q "$BUNDLE" -d "$TMP_DIR"

mapfile -d '' WEBPS < <(find "$TMP_DIR" -maxdepth 1 -type f -iname '*.webp' -print0 | sort -z)
if [[ "${#WEBPS[@]}" -ne 25 ]]; then
  echo "Expected 25 WebP files in V2.3 bundle, found ${#WEBPS[@]}." >&2
  exit 7
fi

echo "EZB_MEDIA_IMPORT_START count=25"

for file in "${WEBPS[@]}"; do
  base="$(basename "$file")"
  stem="${base%.*}"

  existing_id="$(
    wp eval "echo function_exists('ezb_find_attachment_by_basename') ? (int) ezb_find_attachment_by_basename('$base') : 0;" --allow-root
  )"

  if [[ "$existing_id" =~ ^[1-9][0-9]*$ ]]; then
    echo "MEDIA_SKIP_EXISTING|$base|id=$existing_id"
    continue
  fi

  imported_id="$(wp media import "$file" --porcelain --allow-root)"
  if [[ ! "$imported_id" =~ ^[1-9][0-9]*$ ]]; then
    echo "Failed to import $base" >&2
    exit 8
  fi

  echo "MEDIA_IMPORTED|$base|id=$imported_id"
done

wp eval-file "$CHECKER" --allow-root | tee "$TMP_DIR/media-readiness.log"

grep -q '^EZB_MEDIA_LIBRARY_READINESS_PASS$' "$TMP_DIR/media-readiness.log"
grep -q '^expected_assets=25$' "$TMP_DIR/media-readiness.log"
grep -q '^resolved_unique_attachments=25$' "$TMP_DIR/media-readiness.log"
grep -q '^media_budget=max_2500px,max_750KB_per_source_webp$' "$TMP_DIR/media-readiness.log"

echo "EZB_STAGING_MEDIA_IMPORT_PASS"
echo "REAL_IMAGE_VISUAL_QA=NEXT_GATE"
