#!/usr/bin/env python3
"""Bind an exact-head public release to a private EZ2 rollback archive (read-only).

The two sources are independently checked and a private scratch file replay
is performed. This does NOT restore SQL, install WordPress, attest LocalWP,
or grant a deployment. Never copy private backup bytes into Git or CI logs.
"""
import json
import re
import sys
from pathlib import Path

from ez2_backup_archive_guard import inspect
from ez2_backup_scratch_replay import replay
from ez2_release_set import run as verify_release

SHA = re.compile(r"[0-9a-f]{40}\Z")


def _directory(value):
    path = Path(value)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("A release or private backup directory is missing or linked")
    resolved = path.resolve(strict=True)
    if resolved != path.absolute():
        raise ValueError("Linked ancestor in a release or private backup path")
    return resolved


def bind(release_dir, private_backup_dir, exact_sha):
    if not isinstance(exact_sha, str) or not SHA.fullmatch(exact_sha):
        raise ValueError("Exact 40-character source SHA required")
    release = _directory(release_dir)
    backup = _directory(private_backup_dir)
    if release == backup or release in backup.parents or backup in release.parents:
        raise ValueError("Public release and private backup trees must be disjoint")

    catalog = verify_release("verify", release, exact_sha)
    required = {
        "source_sha": exact_sha,
        "scope": "engineering-evidence-only",
        "target_site": "ez2-isolated-only",
        "one_click_complete": False,
        "private_media_included": False,
        "localwp_installed": False,
        "deployment_authorized": False,
    }
    if any(catalog.get(key) is not expected if isinstance(expected, bool)
           else catalog.get(key) != expected for key, expected in required.items()):
        raise ValueError("Public release scope or exact SHA rejected")

    archive = inspect(backup, exact_sha)
    if (archive.get("status") != "BACKUP_ARCHIVE_STRUCTURE_VERIFIED_ONLY"
            or archive.get("target_site") != "ez2-isolated-only"
            or archive.get("byte_integrity_verified") is not True
            or archive.get("archive_contents_inspected") is not True
            or archive.get("deployment_authorized") is not False):
        raise ValueError("Private rollback archive verification failed")
    scratch = replay(backup, exact_sha)
    if (scratch.get("status") != "SCRATCH_FILE_REPLAY_VERIFIED_ONLY"
            or scratch.get("source_sha") != exact_sha
            or scratch.get("scratch_deleted") is not True
            or scratch.get("wordpress_restored") is not False
            or scratch.get("deployment_authorized") is not False):
        raise ValueError("Private scratch replay verification failed")

    return {
        "status": "EXACT_HEAD_RELEASE_AND_PRIVATE_BACKUP_VERIFIED_ONLY",
        "source_sha": exact_sha,
        "target_site": "ez2-isolated-only",
        "release_catalog_verified": True,
        "private_backup_byte_integrity_verified": True,
        "private_backup_archive_structure_verified": True,
        "private_scratch_file_replay_verified": True,
        "private_scratch_files_replayed": scratch["replayed_files"],
        "database_restore_rehearsed": False,
        "consistent_database_and_files_snapshot_verified": False,
        "installed_site_identity_attested": False,
        "localwp_touched": False,
        "deployment_authorized": False,
        "can_apply": False,
        "one_click_complete": False,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4:
            raise ValueError("Usage: ez2_backup_release_binding.py RELEASE_DIR PRIVATE_BACKUP_DIR EXACT_SHA")
        print(json.dumps(bind(*sys.argv[1:]), sort_keys=True))
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("EZ2_BACKUP_RELEASE_BINDING_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
