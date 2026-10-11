#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIX="$(mktemp -d)"
trap 'rm -rf "$FIX"' EXIT
mkdir -p "$FIX/scripts" "$FIX/wp-content/themes/ezb-theme" "$FIX/wp-content/plugins/ezb-core"
cp "$ROOT/scripts/build-release-bundle.sh" "$FIX/scripts/build-release-bundle.sh"
cat > "$FIX/wp-content/themes/ezb-theme/style.css" <<'THEME'
Theme Name: EZB Theme
Version: 0.2.0
THEME
printf '{}\n' > "$FIX/wp-content/themes/ezb-theme/theme.json"
cat > "$FIX/wp-content/plugins/ezb-core/ezb-core.php" <<'PLUGIN'
<?php
 * Plugin Name: EZB Core
 * Version: 0.2.0
PLUGIN
git -C "$FIX" init -q
git -C "$FIX" config user.name 'EZB test'
git -C "$FIX" config user.email 'test@example.invalid'
git -C "$FIX" add .
git -C "$FIX" commit -qm 'Fixture'
run_ok() { (cd "$FIX" && bash scripts/build-release-bundle.sh >/dev/null); }
run_bad() { if (cd "$FIX" && bash scripts/build-release-bundle.sh >/dev/null 2>&1); then echo "Expected release rejection: $1" >&2; exit 1; fi; }
run_ok
unzip -p "$FIX/.release/ezb-theme.zip" ezb-theme/style.css | grep -q '^Theme Name: EZB Theme$'
# Untracked files must never enter a release.
printf 'private fixture\n' > "$FIX/wp-content/themes/ezb-theme/private-customer.txt"
run_bad untracked
rm "$FIX/wp-content/themes/ezb-theme/private-customer.txt"
# Modified tracked files and staged changes must be rejected.
printf 'changed\n' >> "$FIX/wp-content/themes/ezb-theme/style.css"
run_bad modified
git -C "$FIX" add wp-content/themes/ezb-theme/style.css
run_bad staged
git -C "$FIX" restore --staged --worktree wp-content/themes/ezb-theme/style.css
# Committed symlinks cannot enter an installable ZIP.
ln -s /etc/passwd "$FIX/wp-content/themes/ezb-theme/external-link"
git -C "$FIX" add wp-content/themes/ezb-theme/external-link
git -C "$FIX" commit -qm 'Tracked symlink fixture'
run_bad symlink
# Exact-head pinning must fail closed on mismatch.
rm "$FIX/wp-content/themes/ezb-theme/external-link"
git -C "$FIX" add -u
git -C "$FIX" commit -qm 'Remove symlink fixture'
if (cd "$FIX" && EZB_EXPECTED_SHA=0000000000000000000000000000000000000000 bash scripts/build-release-bundle.sh >/dev/null 2>&1); then
  echo 'Expected exact SHA mismatch rejection' >&2; exit 1
fi
run_ok
(cd "$FIX/.release" && sha256sum -c SHA256SUMS >/dev/null)
echo 'EZB_RELEASE_SOURCE_GUARD_TEST_PASS cases=7'
