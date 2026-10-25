#!/usr/bin/env python3
"""CI-only: compare actual disposable WordPress theme/core bytes to exact-head ZIPs.

Copies code OUT of the disposable WordPress container to auto-deleted scratch.
No site writes, database access, LocalWP access, deployment, or public artifacts.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ez2_installed_code_parity import check

REPO = Path(__file__).resolve().parents[1]
COMPOSE = ("docker", "compose", "-f", ".github/release-install/docker-compose.yml")
COMPONENTS = (("themes", "ezb-theme"), ("plugins", "ezb-core"))


def validate_ci_scope(sha, git_head, actions, opt_in):
    if actions != "true" or opt_in != "YES_DISPOSABLE_RELEASE_ONLY":
        raise ValueError("Disposable GitHub CI opt-in required")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid exact-head SHA")
    if git_head != sha:
        raise ValueError("CI checkout differs from requested SHA")
    return True


def verify_copied(release, sha, content):
    result = check(release, sha, content)
    if (result.get("status") != "CODE_BYTES_MATCH_RELEASE_ONLY"
            or result.get("theme_core_byte_parity") is not True
            or result.get("mismatch_count") != 0
            or not isinstance(result.get("checked_release_files"), int)
            or result["checked_release_files"] < 1
            or result.get("deployment_authorized") is not False):
        raise ValueError("Disposable installed bytes differ from exact-head release")
    return result["checked_release_files"]


def run(sha):
    git_head = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=REPO, text=True).strip()
    validate_ci_scope(sha, git_head, os.getenv("GITHUB_ACTIONS"),
                      os.getenv("EZ2_CI_LIVE_PARITY"))
    release = REPO / ".release"
    if not release.is_dir() or release.is_symlink():
        raise ValueError("Expected CI release directory missing")
    # Do not allow a second site, a user-provided container or a non-CI target.
    preflight = (*COMPOSE, "exec", "-T", "release-wordpress", "sh", "-c",
                 'test "$WP_ENVIRONMENT_TYPE" = staging && '
                 'test -f /var/www/html/wp-config.php && '
                 'test -d /var/www/html/wp-content/themes/ezb-theme && '
                 'test -d /var/www/html/wp-content/plugins/ezb-core')
    subprocess.run(preflight, cwd=REPO, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with tempfile.TemporaryDirectory(prefix="ez2-ci-live-parity-") as tmp:
        content = Path(tmp) / "wp-content"
        for group, component in COMPONENTS:
            parent = content / group
            parent.mkdir(parents=True, exist_ok=True)
            source = ("release-wordpress:/var/www/html/wp-content/"
                      + group + "/" + component)
            subprocess.run((*COMPOSE, "cp", source, str(parent) + "/"),
                           cwd=REPO, check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        files = verify_copied(release, sha, content)
    return {
        "status": "EZ2_CI_LIVE_INSTALLED_PARITY_PASS",
        "source_sha": sha,
        "checked_release_files": files,
        "runtime_source": "disposable_wordpress_container",
        "source_container_modified": False,
        "scratch_deleted": True,
        "database_touched": False,
        "localwp_touched": False,
        "can_apply": False,
        "one_click_complete": False,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("Usage: ez2_ci_live_installed_parity.py EXACT_SHA")
        receipt = run(sys.argv[1])
        print(receipt["status"] + " source_sha=" + receipt["source_sha"]
              + " checked_files=" + str(receipt["checked_release_files"])
              + " source_container_modified=false localwp_touched=false"
              + " one_click_complete=false")
    except (ValueError, OSError, subprocess.SubprocessError, KeyError,
            TypeError) as exc:
        # Do not emit source paths, container stderr, or private bytes.
        print("EZ2_CI_LIVE_INSTALLED_PARITY_FAIL: " + type(exc).__name__,
              file=sys.stderr)
        sys.exit(1)
