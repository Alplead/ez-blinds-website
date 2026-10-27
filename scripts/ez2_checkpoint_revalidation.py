#!/usr/bin/env python3
"""Revalidate a private EZ2 checkpoint against CURRENT first-party WordPress files.

The durable checkpoint proves archive and release bytes, not whether the
installed theme/core changed after capture. This read-only gate checks both
at consumption time. It never identifies the WordPress installation, reads
private content into logs, performs a restore, or authorizes installation.
"""
import json
import re
import sys
from pathlib import Path

from ez2_installed_code_parity import check as check_parity
from ez2_wp_preinstall_checkpoint import RECEIPT_SUFFIX, _directory, verify_receipt
from ez2_wp_snapshot_capture import NAME, _private_parent_outside_git

SHA = re.compile(r"[0-9a-f]{40}\Z")


def revalidate(receipt_path, backup_dir, installed_release_dir,
               candidate_release_dir, wp_content_dir, installed_sha, candidate_sha):
    if (not isinstance(installed_sha, str) or not SHA.fullmatch(installed_sha)
            or not isinstance(candidate_sha, str) or not SHA.fullmatch(candidate_sha)
            or installed_sha == candidate_sha):
        raise ValueError("Distinct exact source SHAs required")
    backup = _directory(backup_dir)
    installed = _directory(installed_release_dir)
    candidate = _directory(candidate_release_dir)
    content = _directory(wp_content_dir)
    if content.name != "wp-content":
        raise ValueError("An isolated wp-content directory is required")
    if not NAME.fullmatch(backup.name):
        raise ValueError("Unsafe private backup name")
    _private_parent_outside_git(backup.parent)
    receipt = Path(receipt_path)
    if receipt.absolute() != backup.parent / (backup.name + RECEIPT_SUFFIX):
        raise ValueError("Checkpoint receipt is not beside its private backup")
    directories = (backup, installed, candidate, content)
    if any(a == b or a in b.parents or b in a.parents
           for index, a in enumerate(directories)
           for b in directories[index + 1:]):
        raise ValueError("Backup, release and WordPress directories must be disjoint")

    checkpoint = verify_receipt(receipt, backup, installed, candidate,
                                installed_sha, candidate_sha)
    if (checkpoint.get("status") != "PRIVATE_CHECKPOINT_RECEIPT_VERIFIED_ONLY"
            or checkpoint.get("durable_receipt_verified") is not True
            or checkpoint.get("installed_release_payload_verified") is not True
            or checkpoint.get("candidate_release_payload_verified") is not True
            or checkpoint.get("private_backup_payload_verified") is not True
            or checkpoint.get("private_scratch_replay_verified") is not True
            or checkpoint.get("can_apply") is not False):
        raise ValueError("Durable private checkpoint is no longer valid")

    parity = check_parity(installed, installed_sha, content)
    if (parity.get("status") != "CODE_BYTES_MATCH_RELEASE_ONLY"
            or parity.get("source_sha") != installed_sha
            or parity.get("theme_core_byte_parity") is not True
            or type(parity.get("checked_release_files")) is not int
            or parity["checked_release_files"] < 1
            or type(parity.get("mismatch_count")) is not int
            or parity["mismatch_count"] != 0
            or parity.get("deployment_authorized") is not False
            or parity.get("site_identity_verified") is not False
            or parity.get("installed_source_attested") is not False):
        raise ValueError("Current installed first-party bytes drifted from checkpoint")

    return {
        "status": "PRIVATE_CHECKPOINT_CURRENT_CODE_PARITY_VERIFIED_ONLY",
        "installed_source_sha": installed_sha,
        "candidate_source_sha": candidate_sha,
        "target_site": "ez2-isolated-only",
        "durable_receipt_verified": True,
        "current_theme_core_byte_parity_verified": True,
        "checked_release_files": parity["checked_release_files"],
        "private_backup_rechecked": True,
        "installed_site_identity_attested": False,
        "wordpress_runtime_rechecked": False,
        "owner_content_drift_checked": False,
        "database_restore_rehearsed": False,
        "localwp_touched": False,
        "deployment_authorized": False,
        "can_apply": False,
        "one_click_complete": False,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 8:
            raise ValueError("Expected receipt, backup, installed release, candidate release, wp-content and two SHAs")
        print(json.dumps(revalidate(*sys.argv[1:]), sort_keys=True))
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        # No private paths, SQL, media or WP-CLI diagnostics in public logs.
        print("EZ2_CHECKPOINT_REVALIDATION_FAIL: " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
