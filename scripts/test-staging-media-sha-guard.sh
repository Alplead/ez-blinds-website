#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$ROOT/scripts/staging-media-acceptance.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/bin" "$TMP/src"
ATTACHED="$TMP/attached.webp"

cat > "$TMP/bin/wp" <<'WP'
#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "core" && "${2:-}" == "is-installed" ]]; then
  exit 0
fi

if [[ "${1:-}" == "eval" ]]; then
  code="${2:-}"
  if [[ "$code" == *"ezb_find_attachment_by_basename"* ]]; then
    printf '%s' "${FAKE_EXISTING_ID:-0}"
    exit 0
  fi
  if [[ "$code" == *"get_attached_file"* ]]; then
    printf '%s' "${FAKE_ATTACHMENT_PATH:-}"
    exit 0
  fi
fi

if [[ "${1:-}" == "media" && "${2:-}" == "import" ]]; then
  src="${3:-}"
  if [[ "${FAKE_IMPORT_CORRUPT:-0}" == "1" ]]; then
    printf 'corrupt' > "$FAKE_ATTACHMENT_PATH"
  else
    cp "$src" "$FAKE_ATTACHMENT_PATH"
  fi
  printf '%s\n' "101"
  exit 0
fi

if [[ "${1:-}" == "eval-file" ]]; then
  echo "EZB_MEDIA_LIBRARY_READINESS_PASS"
  echo "expected_assets=25"
  echo "resolved_unique_attachments=25"
  echo "media_budget=max_2500px,max_750KB_per_source_webp"
  exit 0
fi

echo "Unexpected fake wp call: $*" >&2
exit 91
WP
chmod +x "$TMP/bin/wp"
export PATH="$TMP/bin:$PATH"
export FAKE_ATTACHMENT_PATH="$ATTACHED"

make_bundle() {
  local count="$1"
  local bundle="$2"
  rm -rf "$TMP/src"
  mkdir -p "$TMP/src"
  local i
  for i in $(seq -w 1 "$count"); do
    printf 'canonical-media-bytes' > "$TMP/src/asset-$i.webp"
  done
  (cd "$TMP/src" && zip -q "$bundle" ./*.webp)
}

run_ok() {
  local name="$1"
  shift
  if ! "$@" >"$TMP/$name.log" 2>&1; then
    cat "$TMP/$name.log" >&2
    echo "Expected PASS: $name" >&2
    exit 1
  fi
}

run_fail() {
  local name="$1"
  local pattern="$2"
  shift 2
  if "$@" >"$TMP/$name.log" 2>&1; then
    cat "$TMP/$name.log" >&2
    echo "Expected FAIL: $name" >&2
    exit 1
  fi
  grep -q "$pattern" "$TMP/$name.log"
}

BUNDLE="$TMP/bundle.zip"
make_bundle 25 "$BUNDLE"
GOOD_BUNDLE_SHA="$(sha256sum "$BUNDLE" | awk '{print $1}')"

# 1. Existing attachment with correct bytes.
printf 'canonical-media-bytes' > "$ATTACHED"
export FAKE_EXISTING_ID=101
unset FAKE_IMPORT_CORRUPT || true
run_ok existing_correct env EZB_MEDIA_BUNDLE_SHA256="$GOOD_BUNDLE_SHA" "$TARGET" "$BUNDLE"
test "$(grep -c '^MEDIA_SHA256_OK|' "$TMP/existing_correct.log")" -eq 25

# 2. Existing attachment with wrong bytes.
printf 'wrong-existing-bytes' > "$ATTACHED"
run_fail existing_wrong 'Attachment checksum mismatch' env EZB_MEDIA_BUNDLE_SHA256="$GOOD_BUNDLE_SHA" "$TARGET" "$BUNDLE"

# 3. Fresh imports preserve source bytes.
rm -f "$ATTACHED"
export FAKE_EXISTING_ID=0
unset FAKE_IMPORT_CORRUPT || true
run_ok fresh_correct env EZB_MEDIA_BUNDLE_SHA256="$GOOD_BUNDLE_SHA" "$TARGET" "$BUNDLE"
test "$(grep -c '^MEDIA_SHA256_OK|' "$TMP/fresh_correct.log")" -eq 25

# 4. Fresh import that stores corrupted bytes fails.
rm -f "$ATTACHED"
export FAKE_IMPORT_CORRUPT=1
run_fail fresh_corrupt 'Attachment checksum mismatch' env EZB_MEDIA_BUNDLE_SHA256="$GOOD_BUNDLE_SHA" "$TARGET" "$BUNDLE"
unset FAKE_IMPORT_CORRUPT

# 5. Existing attachment record with missing file fails.
rm -f "$ATTACHED"
export FAKE_EXISTING_ID=101
run_fail missing_attachment 'Attachment file is missing' env EZB_MEDIA_BUNDLE_SHA256="$GOOD_BUNDLE_SHA" "$TARGET" "$BUNDLE"

# 6. Wrong whole-bundle digest fails before import.
printf 'canonical-media-bytes' > "$ATTACHED"
run_fail wrong_bundle 'V2.3 bundle checksum mismatch' env EZB_MEDIA_BUNDLE_SHA256="0000000000000000000000000000000000000000000000000000000000000000" "$TARGET" "$BUNDLE"

# 7. Bundle with 24 WebPs fails count guard.
BUNDLE24="$TMP/bundle24.zip"
make_bundle 24 "$BUNDLE24"
BUNDLE24_SHA="$(sha256sum "$BUNDLE24" | awk '{print $1}')"
run_fail wrong_count 'Expected 25 WebP files' env EZB_MEDIA_BUNDLE_SHA256="$BUNDLE24_SHA" "$TARGET" "$BUNDLE24"

echo "EZB_STAGING_MEDIA_SHA_GUARD_TEST_PASS cases=7"
