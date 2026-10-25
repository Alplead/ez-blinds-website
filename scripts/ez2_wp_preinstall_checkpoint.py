#!/usr/bin/env python3
"""Build a private pre-install checkpoint for an independently approved EZ2 site.

Order matters: verify the exact-head public release BEFORE touching the local
database; then capture private files/SQL and bind both verified inventories.
No WordPress installation, activation, migration or restore is performed.
Never send backup paths, SQL, media or customer details to CI or GitHub.
"""
import json
import shutil
import sys
from pathlib import Path

from ez2_backup_release_binding import _directory, bind as bind_release
from ez2_release_set import run as verify_release
from ez2_wp_snapshot_capture import capture

EXPECTED_SITE = "ez2-isolated-only"


def prepare(release_dir, wp_root, private_parent, backup_name, host,
            elementor_version, exact_sha, *, wp_executable="wp"):
    """Return a non-deployable receipt; on failure remove only our new archive."""
    # Verify public release before invoking WP-CLI or creating a private archive.
    release = _directory(release_dir)
    catalog = verify_release("verify", release, exact_sha)
    if (catalog.get("source_sha") != exact_sha
            or catalog.get("target_site") != EXPECTED_SITE
            or catalog.get("scope") != "engineering-evidence-only"
            or catalog.get("deployment_authorized") is not False
            or catalog.get("one_click_complete") is not False):
        raise ValueError("Exact-head isolated release rejected")
    parent = _directory(private_parent)
    # A private parent must not overlap public release, including ancestors.
    if release == parent or release in parent.parents or parent in release.parents:
        raise ValueError("Release and private backup parent overlap")
    # capture() validates the name, WordPress site and paths again. It refuses
    # existing destinations; do not clean up anything until it returns success.
    result = capture(wp_root, parent, backup_name, host, elementor_version,
                     exact_sha, wp_executable=wp_executable)
    destination = parent / backup_name
    try:
        if (result.get("status") != "EZ2_PRIVATE_CAPTURE_ARCHIVED_AND_SCRATCH_FILE_REPLAYED_ONLY"
                or result.get("source_sha") != exact_sha
                or result.get("database_export_generated") is not True
                or result.get("file_replay_verified") is not True
                or result.get("deployment_authorized") is not False):
            raise ValueError("Private WordPress capture was not verified")
        linked = bind_release(release, destination, exact_sha)
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
        "source_sha": exact_sha,
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
        if len(sys.argv) != 8:
            raise ValueError("Usage: ez2_wp_preinstall_checkpoint.py RELEASE_DIR WP_ROOT PRIVATE_PARENT NEW_BACKUP_NAME EZ2_HOST ELEMENTOR_VERSION EXACT_SHA")
        print(json.dumps(prepare(*sys.argv[1:]), sort_keys=True))
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        # Never print SQL, WP-CLI stderr, or private filesystem paths.
        print("EZ2_PREINSTALL_CHECKPOINT_FAIL: " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
