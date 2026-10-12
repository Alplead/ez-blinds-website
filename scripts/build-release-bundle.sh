#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${EZB_RELEASE_DIR:-$ROOT/.release}"
THEME_PATH="wp-content/themes/ezb-theme"
PLUGIN_PATH="wp-content/plugins/ezb-core"

# Only a clean, committed HEAD is eligible for a distributable release.
# Never zip the working directory: it may contain private or unreviewed files.
if ! git -C "$ROOT" rev-parse --is-inside-work-tree | grep -qx true; then
  echo "Release source must be a Git worktree" >&2
  exit 1
fi
COMMIT="$(git -C "$ROOT" rev-parse --verify HEAD)"
if [[ -n "${EZB_EXPECTED_SHA:-}" && "$COMMIT" != "$EZB_EXPECTED_SHA" ]]; then
  echo "Release HEAD differs from expected exact SHA" >&2
  exit 1
fi
if [[ -n "$(git -C "$ROOT" status --porcelain --untracked-files=all -- "$THEME_PATH" "$PLUGIN_PATH")" ]]; then
  echo "Release source contains staged, modified or untracked files" >&2
  exit 1
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
# git archive excludes ignored/untracked content by construction.
git -C "$ROOT" archive --format=tar "$COMMIT" -- "$THEME_PATH" "$PLUGIN_PATH" | tar -xf - -C "$STAGE"
THEME="$STAGE/$THEME_PATH"
PLUGIN="$STAGE/$PLUGIN_PATH"
test -f "$THEME/style.css"
test -f "$THEME/theme.json"
test -f "$PLUGIN/ezb-core.php"
if find "$STAGE/wp-content" -type l -print -quit | grep -q .; then
  echo "Release source contains a tracked symbolic link" >&2
  exit 1
fi
grep -q '^Theme Name: EZB Theme$' "$THEME/style.css"
grep -q '^ \* Plugin Name: EZB Core$' "$PLUGIN/ezb-core.php"

# Only the repository's dedicated release directory may be replaced.
# Never recursively remove arbitrary caller-supplied paths.
OUT="$(realpath -m "$OUT")"
if [[ "$OUT" != "$ROOT/.release" ]]; then
  echo "Unsafe release output directory" >&2
  exit 1
fi
rm -rf -- "$OUT"
mkdir -p -- "$OUT"
(
  cd "$STAGE/wp-content/themes"
  zip -qr "$OUT/ezb-theme.zip" ezb-theme -x '*/.DS_Store' '*/Thumbs.db'
)
(
  cd "$STAGE/wp-content/plugins"
  zip -qr "$OUT/ezb-core.zip" ezb-core -x '*/.DS_Store' '*/Thumbs.db'
)
THEME_VERSION="$(sed -n 's/^Version:[[:space:]]*//p' "$THEME/style.css" | head -1)"
PLUGIN_VERSION="$(sed -n 's/^ \* Version:[[:space:]]*//p' "$PLUGIN/ezb-core.php" | head -1)"
cat > "$OUT/RELEASE_METADATA.txt" <<META
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
META
# Explicitly label this release as first-party theme/core ONLY. The manifest
# is not a promise of Elementor, third-party plugins, content, or media delivery.
python3 - "$OUT" "$COMMIT" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

out, commit = Path(sys.argv[1]), sys.argv[2]
archives = [
    {"name": name, "install_path": target, "sha256": hashlib.sha256((out / name).read_bytes()).hexdigest()}
    for name, target in (
        ("ezb-theme.zip", "wp-content/themes/ezb-theme"),
        ("ezb-core.zip", "wp-content/plugins/ezb-core"),
    )
]
manifest = {
    "schema_version": 1,
    "commit": commit,
    "delivery_scope": "theme-and-core-only",
    "archives": archives,
    "includes": {key: False for key in ("third_party_plugins", "elementor_templates", "wordpress_content", "media", "database")},
    "localwp_installed": False,
    "owner_visual_acceptance": False,
}
(out / "RELEASE_CONTENTS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
(
  cd "$OUT"
  sha256sum ezb-theme.zip ezb-core.zip RELEASE_METADATA.txt RELEASE_CONTENTS.json > SHA256SUMS
)
python3 "$ROOT/scripts/verify_release_scope.py" "$OUT" "$COMMIT"
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
