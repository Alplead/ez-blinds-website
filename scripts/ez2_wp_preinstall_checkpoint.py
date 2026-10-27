#!/usr/bin/env python3
"""Build a private pre-install checkpoint for an independently approved EZ2 site.

Order matters: verify separate installed/candidate releases, attest installed
first-party bytes, then capture private files/SQL labelled with INSTALLED_SHA.
Never label the installed rollback backup with the incoming candidate SHA.
Only a disposable scratch candidate file-swap and rollback is rehearsed.
No WordPress installation, activation, migration or database restore is performed.
Never send backup paths, SQL, media or customer details to CI or GitHub.
"""
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path

from ez2_backup_release_binding import _directory, bind as bind_release
from ez2_checkpoint_upgrade_rehearsal import rehearse as rehearse_candidate
from ez2_installed_code_parity import check as check_installed_parity
from ez2_release_set import CATALOG, run as verify_release
from ez2_wp_snapshot_capture import NAME, _private_parent_outside_git, capture

EXPECTED_SITE = "ez2-isolated-only"

RECEIPT_SUFFIX = ".checkpoint.json"
RECEIPT_MAX_BYTES = 4096


def _fingerprint(path):
    """Hash a bounded single-link regular evidence file without following links."""
    path = Path(path)
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or not 0 < before.st_size <= 1024 * 1024):
        raise ValueError("Unsafe checkpoint evidence file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        opened = os.fstat(source.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise ValueError("Checkpoint evidence changed before reading")
        data = source.read(1024 * 1024 + 1)
        after = os.fstat(source.fileno())
        if (after.st_size, after.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns):
            raise ValueError("Checkpoint evidence changed during reading")
    if len(data) != before.st_size:
        raise ValueError("Checkpoint evidence size mismatch")
    return hashlib.sha256(data).hexdigest()


def _receipt_data(backup, installed, candidate, installed_sha, candidate_sha):
    if (not isinstance(installed_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", installed_sha)
            or not isinstance(candidate_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", candidate_sha)
            or installed_sha == candidate_sha):
        raise ValueError("Distinct exact checkpoint SHAs required")
    return {
        "schema_version": 1,
        "status": "PRIVATE_CHECKPOINT_EVIDENCE_ONLY",
        "target_site": EXPECTED_SITE,
        "installed_source_sha": installed_sha,
        "candidate_source_sha": candidate_sha,
        "backup_manifest_sha256": _fingerprint(backup / "backup-manifest.json"),
        "installed_release_catalog_sha256": _fingerprint(installed / CATALOG),
        "candidate_release_catalog_sha256": _fingerprint(candidate / CATALOG),
        "database_restore_rehearsed": False,
        "installed_release_attested": False,
        "can_apply": False,
        "one_click_complete": False,
    }


def verify_receipt(receipt, backup, installed, candidate, installed_sha, candidate_sha):
    """Rebind durable private evidence to BOTH releases; never authorize apply."""
    receipt = Path(receipt)
    info = receipt.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or not 0 < info.st_size <= RECEIPT_MAX_BYTES):
        raise ValueError("Unsafe checkpoint receipt")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(receipt, flags), "rb") as source:
        data = source.read(RECEIPT_MAX_BYTES + 1)
        opened = os.fstat(source.fileno())
    if len(data) != info.st_size or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
        raise ValueError("Checkpoint receipt changed during reading")
    expected = _receipt_data(Path(backup), Path(installed), Path(candidate),
                             installed_sha, candidate_sha)
    canonical = (json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if data != canonical:
        raise ValueError("Checkpoint receipt does not match exact source evidence")
    return {
        "status": "PRIVATE_CHECKPOINT_RECEIPT_VERIFIED_ONLY",
        "installed_source_sha": installed_sha,
        "candidate_source_sha": candidate_sha,
        "durable_receipt_verified": True,
        "backup_manifest_bound": True,
        "both_release_catalogs_bound": True,
        "can_apply": False,
        "one_click_complete": False,
    }


def _persist_receipt(receipt, backup, installed, candidate, installed_sha, candidate_sha):
    expected = _receipt_data(backup, installed, candidate, installed_sha, candidate_sha)
    data = (json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(data) > RECEIPT_MAX_BYTES:
        raise ValueError("Oversized checkpoint receipt")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(receipt, flags, 0o600)
    created = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        result = verify_receipt(receipt, backup, installed, candidate,
                                installed_sha, candidate_sha)
        if result["status"] != "PRIVATE_CHECKPOINT_RECEIPT_VERIFIED_ONLY":
            raise ValueError("Durable checkpoint receipt verification failed")
        return result
    except BaseException:
        # Only remove our own inode; never delete an unexpected replacement.
        try:
            current = receipt.lstat()
            if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                receipt.unlink()
        except FileNotFoundError:
            pass
        raise




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
    if not isinstance(backup_name, str) or not NAME.fullmatch(backup_name):
        raise ValueError("Unsafe private checkpoint name")
    receipt_path = parent / (backup_name + RECEIPT_SUFFIX)
    if receipt_path.exists() or receipt_path.is_symlink():
        raise ValueError("Private checkpoint receipt already exists")
    if any(root == release or root in release.parents or release in root.parents
           for release in (candidate, installed)):
        raise ValueError("Release directories must be outside WordPress root")
    directories = (candidate, installed, parent)
    if any(a == b or a in b.parents or b in a.parents
           for index, a in enumerate(directories)
           for b in directories[index + 1:]):
        raise ValueError("Candidate, installed release and backup paths must be disjoint")
    # Fail before any expensive verification or WP-CLI: private backups cannot
    # be stored under a public Git checkout, including linked worktrees.
    _private_parent_outside_git(parent)
    # The release and installed code may change while a private capture runs.
    # Re-attest both immediately before accepting the backup as a checkpoint.
    def verify_baseline():
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
    verify_baseline()
    # Capture only the verified installed baseline; no candidate is applied.
    result = capture(wp_root, parent, backup_name, host, elementor_version,
                     installed_sha, wp_executable=wp_executable)
    destination = parent / backup_name
    receipt_created = False
    try:
        verify_baseline()  # Fail closed if release or installed bytes drifted during capture.
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
        rehearsal = rehearse_candidate(candidate, installed, destination,
                                       installed_sha, candidate_sha)
        if (rehearsal.get("status") != "PRIVATE_BACKUP_CANDIDATE_SCRATCH_UPGRADE_ROLLBACK_VERIFIED_ONLY"
                or rehearsal.get("scratch_original_bytes_restored") is not True
                or rehearsal.get("private_backup_unchanged") is not True
                or rehearsal.get("can_apply") is not False):
            raise ValueError("Private backup candidate scratch upgrade failed")
        receipt = _persist_receipt(receipt_path, destination, installed, candidate,
                                   installed_sha, candidate_sha)
        receipt_created = True
        if receipt["durable_receipt_verified"] is not True:
            raise ValueError("Private checkpoint receipt not verified")
    except BaseException:
        if receipt_created and receipt_path.is_file() and not receipt_path.is_symlink():
            receipt_path.unlink()
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
        "scratch_candidate_upgrade_and_rollback_verified": True,
        "private_checkpoint_receipt_persisted": True,
        "private_checkpoint_receipt_verified": True,
        "receipt_authorizes_installation": False,
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
