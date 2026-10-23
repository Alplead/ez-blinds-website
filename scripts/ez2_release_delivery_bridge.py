#!/usr/bin/env python3
"""Read-only link from an exact-head EZ2 release to a protected delivery plan.

NOT a WordPress installer, LocalWP sync tool or publication gate. No private
media, plugins or pages are installed, downloaded or uploaded by this script.
"""
import io
import json
import re
import stat
import sys
import zipfile
from pathlib import Path

from ez2_content_candidate_bundle import NAME, verify as verify_candidate
from ez2_content_guard import read as read_installed
from ez2_delivery_preflight import check as check_delivery
from ez2_elementor_export_check import check as check_elementor, unique, reject_nonfinite
from ez2_plugin_dependency_check import read as read_lock
from ez2_release_set import run as check_release, safe_read

SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def regular_input(path, max_bytes):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Linked planning input refused")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= max_bytes:
        raise ValueError("Unsafe planning input")
    return path


def plan(release_dir, exact_sha, plugin_lock, installed_snapshot, previous_digest=None):
    if previous_digest is not None and (
            not isinstance(previous_digest, str) or not SHA256.fullmatch(previous_digest)):
        raise ValueError("Invalid previous managed-content digest")
    release_dir = Path(release_dir)
    catalog = check_release("verify", release_dir, exact_sha)
    for key, expected in (
            ("source_sha", exact_sha),
            ("target_site", "ez2-isolated-only"),
            ("scope", "engineering-evidence-only"),
            ("one_click_complete", False),
            ("elementor_candidate_installable", False),
            ("third_party_plugins_included", False),
            ("private_media_included", False),
            ("localwp_installed", False),
            ("deployment_authorized", False)):
        if catalog.get(key) != expected or (isinstance(expected, bool)
                                             and catalog.get(key) is not expected):
            raise ValueError("Unsafe release catalog: " + key)
    raw = safe_read(release_dir, "ez2-content-candidate.zip")
    manifest = verify_candidate(exact_sha, raw)
    if manifest.get("source_sha") != exact_sha or manifest.get("scope") != "public-review-candidate-only":
        raise ValueError("Wrong candidate source or publication scope")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        candidate = json.loads(archive.read(NAME), object_pairs_hook=unique,
                               parse_constant=reject_nonfinite)
    summary = check_elementor(candidate)
    lock = read_lock(regular_input(plugin_lock, 32768))
    if len(lock.get("plugins", [])) != 1 or lock["plugins"][0].get("slug") != "elementor":
        raise ValueError("Only approved Elementor Free evaluation is supported")
    if lock["plugins"][0].get("version") != candidate["version"]:
        raise ValueError("Pinned Elementor version differs from release candidate")
    installed = read_installed(regular_input(installed_snapshot, 32768))
    contract = {
        "schema_version": 1,
        "target_site": "ez2-isolated-only",
        "source_sha": exact_sha,
        "plugin_lock": "plugins.json",
        "templates": [{
            "key": "ez2-home-hero",
            "file": "home-hero.json",
            "previous_sha256": previous_digest,
        }],
        "media_slots": summary["media_slots"],
    }
    result = check_delivery(contract, installed, lock, {"home-hero.json": candidate}, exact_sha)
    return {
        "status": result["status"],
        "source_sha": exact_sha,
        "target_site": "ez2-isolated-only",
        "release_catalog_verified": True,
        "candidate_archive_verified": True,
        "elementor_version_pinned": candidate["version"],
        "plugin_status": result["plugin_status"],
        "missing_plugin_checksums": result["missing_plugin_checksums"],
        "content": result["content"],
        "symbolic_media_slots": summary["media_slots"],
        "unresolved_media_slots": result["unresolved_media_slots"],
        "media_mapping_verified_on_localwp": False,
        "plugin_archive_verified": False,
        "wordpress_runtime_verified": False,
        "restore_rehearsed_on_localwp": False,
        "one_click_complete": False,
        "localwp_installed": False,
        "deployment_authorized": False,
        "applied": False,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) not in (5, 6):
            raise ValueError("Usage: ez2_release_delivery_bridge.py RELEASE_DIR EXACT_SHA PLUGIN_LOCK INSTALLED_SNAPSHOT [PREVIOUS_SHA256|-]")
        previous = None if len(sys.argv) == 5 or sys.argv[5] == "-" else sys.argv[5]
        result = plan(*sys.argv[1:5], previous)
        print(json.dumps(result, sort_keys=True))
        sys.exit(2 if result["status"] == "BLOCKED_PREFLIGHT" else 0)
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        print("EZ2_RELEASE_DELIVERY_BRIDGE_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
