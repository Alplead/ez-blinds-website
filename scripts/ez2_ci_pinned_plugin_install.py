#!/usr/bin/env python3
"""Install a pinned official Elementor ZIP only into disposable CI WordPress.

This is NOT a LocalWP installer or a delivery authorization. Third-party ZIP
bytes live in an auto-deleted private runner directory, never in public Git.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ez2_plugin_archive_verify import verify as verify_archive
from ez2_plugin_dependency_check import check as check_lock, read as read_lock
from ez2_plugin_official_fetch import CHUNK, MAX_ARCHIVE, official_url, open_official
from ez2_release_set import run as verify_release

REPO = Path(__file__).resolve().parents[1]
# The CI installer consumes the pinned dependency staged from the same
# verified exact-head envelope as the theme/core WordPress installation.
LOCK_PATH = REPO / ".release/ez2-envelope-install-input/dependency/elementor-pinned.json"
SOURCE_LOCK_PATH = REPO / "design/ez2-elementor-pinned-plugin.json"
COMPOSE = ("docker", "compose", "-f", ".github/release-install/docker-compose.yml")
VERSION = "4.3.4"


def validate_lock(lock):
    checked = check_lock(lock)
    if (checked["missing_checksums"] or len(lock["plugins"]) != 1
            or lock["plugins"][0]["slug"] != "elementor"
            or lock["plugins"][0]["version"] != VERSION):
        raise ValueError("Expected one checksum-pinned Elementor Free 4.3.4 dependency")
    return lock["plugins"][0]


def download_verified(lock, directory, opener=open_official, repo_root=None):
    """Download, checksum, and inspect official ZIP before any WP CLI call."""
    plugin = validate_lock(lock)
    root = Path(directory).resolve(strict=True)
    repo = Path(repo_root or REPO).resolve(strict=True)
    if root == repo or repo in root.parents:
        raise ValueError("Private plugin ZIP must stay outside public repository")
    filename = plugin["slug"] + "." + plugin["version"] + ".zip"
    path = root / filename
    url = official_url(plugin["slug"], plugin["version"])
    digest, size = hashlib.sha256(), 0
    with opener(url) as response:
        if response.geturl() != url or getattr(response, "status", None) != 200:
            raise ValueError("Official plugin URL/status mismatch")
        length = response.headers.get("Content-Length")
        if length is not None and (not length.isdecimal()
                                   or not 0 < int(length) <= MAX_ARCHIVE):
            raise ValueError("Invalid official ZIP Content-Length")
        with path.open("xb") as output:
            while True:
                block = response.read(CHUNK)
                if not block:
                    break
                size += len(block)
                if size > MAX_ARCHIVE:
                    raise ValueError("Official plugin ZIP exceeds size cap")
                digest.update(block)
                output.write(block)
        if not size or (length is not None and size != int(length)):
            raise ValueError("Official plugin ZIP incomplete")
    if digest.hexdigest() != plugin["archive_sha256"]:
        raise ValueError("Official plugin ZIP differs from pinned SHA256")
    checked = verify_archive(lock, root, repo_root=repo)
    if (len(checked["plugins"]) != 1
            or checked["plugins"][0]["slug"] != "elementor"
            or not checked["plugins"][0]["checksum_verified"]):
        raise ValueError("Plugin ZIP structure not verified")
    return path


def wp(*args, env=None, allow_failure=False):
    cmd = (*COMPOSE, "run", "--rm", "--entrypoint", "wp",
           "release-bootstrap", *args, "--allow-root")
    result = subprocess.run(cmd, cwd=REPO, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode and not allow_failure:
        raise ValueError("Disposable WP CLI command failed: " + args[0])
    return result


def main(exact_sha):
    if (os.getenv("GITHUB_ACTIONS") != "true"
            or os.getenv("EZ2_CI_PINNED_PLUGIN_INSTALL") != "YES_DISPOSABLE_RELEASE_ONLY"
            or not re.fullmatch(r"[0-9a-f]{40}", exact_sha)):
        raise ValueError("CI-only explicit exact-SHA opt-in required")
    actual = subprocess.check_output(("git", "rev-parse", "HEAD"),
                                     cwd=REPO, text=True).strip()
    if actual != exact_sha:
        raise ValueError("CI checkout is not exact expected HEAD")
    verify_release("verify", REPO / ".release", exact_sha)
    if (LOCK_PATH.is_symlink() or not LOCK_PATH.is_file()
            or LOCK_PATH.stat().st_nlink != 1
            or LOCK_PATH.read_bytes() != SOURCE_LOCK_PATH.read_bytes()):
        raise ValueError("Staged envelope plugin lock missing or source mismatch")
    lock = read_lock(LOCK_PATH)
    validate_lock(lock)
    if json.loads((REPO / "design/ez2-home-hero-candidate.json").read_text())["version"] != VERSION:
        raise ValueError("Candidate and plugin lock versions differ")
    if (wp("option", "get", "home").stdout.strip() != "http://localhost:8081"
            or wp("eval", "echo wp_get_environment_type();").stdout.strip() != "staging"
            or wp("option", "get", "stylesheet").stdout.strip() != "ezb-theme"
            or wp("plugin", "is-active", "ezb-core").returncode != 0
            or wp("plugin", "is-installed", "elementor", allow_failure=True).returncode == 0
            or wp("plugin", "is-installed", "elementor-pro", allow_failure=True).returncode == 0):
        raise ValueError("Not a clean disposable EZ2 release staging fixture")
    with tempfile.TemporaryDirectory(prefix="ez2-ci-pinned-plugin-", dir="/tmp") as temp:
        path = download_verified(lock, temp)
        env = dict(os.environ, EZ2_CI_PINNED_PLUGIN_DIR=temp)
        installed = wp("plugin", "install",
                       "/opt/ez2-ci-pinned-plugin/" + path.name,
                       "--activate", env=env)
        if installed.returncode:
            raise ValueError("Pinned plugin install failed")
        if (wp("plugin", "get", "elementor", "--field=version").stdout.strip() != VERSION
                or wp("plugin", "is-active", "elementor").returncode != 0
                or wp("plugin", "is-installed", "elementor-pro", allow_failure=True).returncode == 0
                or wp("eval", "echo did_action('elementor/loaded');").stdout.strip() != "1"):
            raise ValueError("Pinned Elementor runtime activation failed")
    print("EZ2_CI_PINNED_ELEMENTOR_INSTALL_PASS version=" + VERSION
          + " exact_head=true official_archive_sha256_verified=true"
          + " staging_only=true localwp_touched=false one_click_complete=false")


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("Usage: ez2_ci_pinned_plugin_install.py EXACT_HEAD_SHA")
        main(sys.argv[1])
    except (OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError) as exc:
        print("EZ2_CI_PINNED_ELEMENTOR_INSTALL_FAIL: " + type(exc).__name__,
              file=sys.stderr)
        sys.exit(1)
