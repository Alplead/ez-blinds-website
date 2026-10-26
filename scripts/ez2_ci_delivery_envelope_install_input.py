#!/usr/bin/env python3
"""Consume the exact-head EZ2 envelope for disposable WordPress install tests.

The staged theme/core ZIPs are actually installed by Release Install Smoke.
This tool never touches LocalWP, a live website, SQL, uploads or production.
"""
import io
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

from ez2_delivery_envelope import DEPENDENCY, FILES, MAX_BYTES, OUT_NAME, verify_bytes
from ez2_release_set import run as verify_release, safe_read

OUTPUT = "ez2-envelope-install-input"
EXACT_SHA = re.compile(r"[0-9a-f]{40}\Z")
RELEASE_NAMES = tuple(n.removeprefix("release/") for n in FILES if n.startswith("release/"))


def stage(release_dir, exact_sha):
    root = Path(release_dir)
    if not isinstance(exact_sha, str) or not EXACT_SHA.fullmatch(exact_sha):
        raise ValueError("Invalid exact source SHA")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Unsafe release directory")
    archive = root / OUT_NAME
    if (archive.is_symlink() or not archive.is_file()
            or archive.stat().st_nlink != 1
            or not 0 < archive.stat().st_size <= MAX_BYTES):
        raise ValueError("Unsafe envelope file")
    destination = root / OUTPUT
    if destination.exists() or destination.is_symlink():
        raise ValueError("Refusing to replace existing install inputs")
    raw = archive.read_bytes()
    receipt = verify_bytes(raw, exact_sha)
    if (receipt.get("source_sha") != exact_sha
            or receipt.get("can_apply") is not False
            or receipt.get("deployment_authorized") is not False):
        raise ValueError("Envelope is not exact-head and non-deployable")
    with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
        # Verify both the complete envelope and parity with the original
        # release before making any executable WordPress installation input.
        payloads = {}
        for name in RELEASE_NAMES:
            data = zipped.read("release/" + name)
            if data != safe_read(root, name):
                raise ValueError("Envelope differs from exact-head release bytes")
            payloads[name] = data
        # The official Elementor dependency must come from the SAME verified
        # envelope as the installed first-party ZIPs, never a separate lock.
        source_lock = root.parent / "design" / "ez2-elementor-pinned-plugin.json"
        if (source_lock.is_symlink() or not source_lock.is_file()
                or source_lock.stat().st_nlink != 1
                or not 0 < source_lock.stat().st_size <= 32768):
            raise ValueError("Unsafe source plugin lock")
        if DEPENDENCY not in zipped.namelist():
            raise ValueError("Missing pinned plugin dependency")
        dependency = zipped.read(DEPENDENCY)
        if dependency != source_lock.read_bytes():
            raise ValueError("Envelope plugin dependency differs from exact source")
        payloads[DEPENDENCY] = dependency
    with tempfile.TemporaryDirectory(prefix=".ez2-envelope-stage-", dir=root) as tmp:
        scratch = Path(tmp)
        for name, data in payloads.items():
            destination_file = scratch / name
            destination_file.parent.mkdir(parents=True, exist_ok=True)
            destination_file.write_bytes(data)
        catalog = verify_release("verify", scratch, exact_sha)
        if (catalog.get("source_sha") != exact_sha
                or catalog.get("target_site") != "ez2-isolated-only"
                or catalog.get("scope") != "engineering-evidence-only"
                or catalog.get("deployment_authorized") is not False
                or catalog.get("one_click_complete") is not False):
            raise ValueError("Staged release catalog rejected")
        if destination.exists() or destination.is_symlink():
            raise ValueError("Install input appeared during staging")
        scratch.rename(destination)
    return {
        "status": "DISPOSABLE_ENVELOPE_INSTALL_INPUT_VERIFIED",
        "source_sha": exact_sha,
        "component_count": len(RELEASE_NAMES) + 1,
        "pinned_plugin_manifest_from_envelope": True,
        "wordpress_install_input": True,
        "localwp_installed": False,
        "one_click_complete": False,
        "deployment_authorized": False,
    }


if __name__ == "__main__":
    try:
        if (len(sys.argv) != 3 or os.environ.get("GITHUB_ACTIONS") != "true"
                or os.environ.get("EZ2_CI_ENVELOPE_INSTALL") != "YES_DISPOSABLE_RELEASE_ONLY"):
            raise ValueError("CI-only explicit opt-in required")
        import subprocess
        root = Path(__file__).resolve().parents[1]
        release = Path(sys.argv[1])
        if release.resolve(strict=True) != (root / ".release").resolve(strict=True):
            raise ValueError("Only the CI release directory is permitted")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        if head != sys.argv[2]:
            raise ValueError("Checked-out source differs from expected SHA")
        print(json.dumps(stage(release, head), sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        print("EZ2_CI_ENVELOPE_INSTALL_INPUT_FAIL: " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
