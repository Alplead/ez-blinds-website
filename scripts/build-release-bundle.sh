#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${EZB_RELEASE_DIR:-$ROOT/.release}"

THEME="$ROOT/wp-content/themes/ezb-theme"
PLUGIN="$ROOT/wp-content/plugins/ezb-core"

for dir in "$THEME" "$PLUGIN"; do
  test -d "$dir"
done

grep -q '^Theme Name: EZB Theme$' "$THEME/style.css"
grep -q '^ \* Plugin Name: EZB Core$' "$PLUGIN/ezb-core.php"

rm -rf "$OUT"
mkdir -p "$OUT"

(
  cd "$ROOT/wp-content/themes"
  zip -qr "$OUT/ezb-theme.zip" ezb-theme \
    -x '*/.DS_Store' '*/Thumbs.db'
)

(
  cd "$ROOT/wp-content/plugins"
  zip -qr "$OUT/ezb-core.zip" ezb-core \
    -x '*/.DS_Store' '*/Thumbs.db'
)

COMMIT="unknown"
if command -v git >/dev/null 2>&1 && git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
fi

THEME_VERSION="$(sed -n 's/^Version:[[:space:]]*//p' "$THEME/style.css" | head -1)"
PLUGIN_VERSION="$(sed -n 's/^ \* Version:[[:space:]]*//p' "$PLUGIN/ezb-core.php" | head -1)"

cat > "$OUT/RELEASE_METADATA.txt" <<EOF
EZ Blinds & Shutters rebuild release bundle
commit=$COMMIT
theme=ezb-theme
theme_version=$THEME_VERSION
plugin=ezb-core
plugin_version=$PLUGIN_VERSION
media_included=no
database_included=no
secrets_included=no
external_mail_delivery=manual_gate
owner_ui_acceptance=manual_gate
EOF

(
  cd "$OUT"
  sha256sum ezb-theme.zip ezb-core.zip RELEASE_METADATA.txt > SHA256SUMS
)

# Package-safety assertions.
for archive in "$OUT/ezb-theme.zip" "$OUT/ezb-core.zip"; do
  listing="$(unzip -Z1 "$archive")"
  if printf '%s\n' "$listing" | grep -E '(^|/)(\.env|wp-config\.php|uploads/|\.git/|\.devcontainer/|node_modules/|vendor/|.*\.sql$|.*\.wpress$)' >/dev/null; then
    echo "Unsafe path found in $archive" >&2
    exit 1
  fi
done

unzip -Z1 "$OUT/ezb-theme.zip" | grep -Fxq 'ezb-theme/style.css'
unzip -Z1 "$OUT/ezb-theme.zip" | grep -Fxq 'ezb-theme/theme.json'
unzip -Z1 "$OUT/ezb-core.zip" | grep -Fxq 'ezb-core/ezb-core.php'

echo "EZB_RELEASE_BUNDLE_PASS"
echo "output=$OUT"
