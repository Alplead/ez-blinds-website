#!/usr/bin/env python3
"""Build a private pre-install checkpoint for an independently approved EZ2 site.

Order matters: verify separate installed/candidate releases, attest installed
first-party bytes, then capture private files/SQL labelled with INSTALLED_SHA.
Never label the installed rollback backup with the incoming candidate SHA.
No WordPress installation, activation, migration or restore is performed.
Never send backup paths, SQL, media or customer details to CI or GitHub.
"""
import json
import shutil
import sys
from pathlib import Path

from ez2_backup_release_binding import _directory, bind as bind_release
from ez2_installed_code_parity import check as check_installed_parity
from ez2_release_set import run as verify_release
from ez2_wp_snapshot_capture import capture

EXPECTED_SITE = "ez2-isolated-only"


def prepare(candidate_release_dir, installed_release_dir, wp_root, private_parent,
            backup_name, host, elementor_version, installed_sha, candidate_sha,
            *, wp_executable="wp"):
    """Return a non-deployable receipt; on failure remove only our new archive."""
    # A rollback backup describes the INSTALLED baseline, not the new candidate.
    if installed_sha == candidate_sha:
        raise ValueError("Installed and candidate SHAs must differ")
    candidate = _directory(candidate_release_dir)
    installed = _directory(installed_release_dir)
    parent = _directory(private_parent)
    root = _directory(wp_root)
    if any(root == release or root in release.parents or release in root.parents
           for release in (candidate, installed)):
        raise ValueError("Release directories must be outside WordPress root")
    directories = (candidate, installed, parent)
    if any(a == b or a in b.parents or b in a.parents
           for index, a in enumerate(directories)
           for b in directories[index + 1:]):
        raise ValueError("Candidate, installed release and backup paths must be disjoint")
    for directory, sha in ((candidate, candidate_sha), (installed, installed_sha)):
        catalog = verify_release("verify", directory, sha)
        if (catalog.get("source_sha") != sha
                or catalog.get("target_site") != EXPECTED_SITE
                or catalog.get("scope") != "engineering-evidence-only"
                or catalog.get("deployment_authorized") is not False
                or catalog.get("one_click_complete") is not False):
            raise ValueError("Exact-head isolated release rejected")
    # Byte parity is not proof of who originally installed the site.
    parity = check_installed_parity(installed, installed_sha,
                                    root / "wp-content")
    if (parity.get("status") != "CODE_BYTES_MATCH_RELEASE_ONLY"
            or parity.get("source_sha") != installed_sha
            or parity.get("theme_core_byte_parity") is not True
            or parity.get("mismatch_count") != 0
            or type(parity.get("checked_release_files")) is not int
            or parity["checked_release_files"] < 1
            or parity.get("deployment_authorized") is not False):
        raise ValueError("Installed first-party bytes do not match baseline release")
    # Capture only the verified installed baseline; no candidate is applied.
    result = capture(wp_root, parent, backup_name, host, elementor_version,
                     installed_sha, wp_executable=wp_executable)
    destination = parent / backup_name
    try:
        if (result.get("status") != "EZ2_PRIVATE_CAPTURE_ARCHIVED_AND_SCRATCH_FILE_REPLAYED_ONLY"
                or result.get("source_sha") != installed_sha
                or result.get("database_export_generated") is not True
                or result.get("file_replay_verified") is not True
                or result.get("deployment_authorized") is not False):
            raise ValueError("Private WordPress capture was not verified")
        linked = bind_release(installed, destination, installed_sha)
        if (linked.get("status") != "EXACT_HEAD_RELEASE_AND_PRIVATE_BACKUP_VERIFIED_ONLY"
                or linked.get("private_backup_byte_integrity_verified") is not True
                or linked.get("private_scratch_file_replay_verified") is not True
                or linked.get("deployment_authorized") is not False
                or linked.get("can_apply") is not False):
            raise ValueError("Public release and private archive binding rejected")
    except BaseException:
        # This path is created by capture() only after it has rejected pre-existing
        # names. Refuse to traverse a swapped link or an unexpected ancestor.
        if (destination.is_dir() and not destination.is_symlink()
                and destination.parent.resolve(strict=True) == parent):
            shutil.rmtree(destination)
        raise
    return {
        "status": "PRIVATE_PREINSTALL_CHECKPOINT_VERIFIED_ONLY",
        "installed_source_sha": installed_sha,
        "candidate_source_sha": candidate_sha,
        "installed_code_byte_parity_verified": True,
        "installed_source_attested": False,
        "candidate_release_verified": True,
        "target_site": EXPECTED_SITE,
        "public_release_verified": True,
        "private_backup_created": True,
        "private_backup_byte_integrity_verified": True,
        "private_file_replay_verified": True,
        "database_export_generated": True,
        "database_restore_rehearsed": False,
        "consistent_database_and_files_snapshot_verified": False,
        "localwp_installed": False,
        "deployment_authorized": False,
        "can_apply": False,
        "one_click_complete": False,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 10:
            raise ValueError("Usage: ez2_wp_preinstall_checkpoint.py CANDIDATE_RELEASE_DIR INSTALLED_RELEASE_DIR WP_ROOT PRIVATE_PARENT NEW_BACKUP_NAME EZ2_HOST ELEMENTOR_VERSION INSTALLED_SHA CANDIDATE_SHA")
        print(json.dumps(prepare(*sys.argv[1:]), sort_keys=True))
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        # Never print SQL, WP-CLI stderr, or private filesystem paths.
        print("EZ2_PREINSTALL_CHECKPOINT_FAIL: " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
