#!/usr/bin/env python3
"""Rehearse a verified private EZ2 rollback archive through a candidate file swap.

All extracted private bytes and all candidate writes stay in auto-deleted
scratch. This NEVER accepts a WordPress root, changes an installed site, runs
SQL, installs Elementor, or authorizes a release. Never log private filenames.
"""
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from ez2_backup_release_binding import _directory, bind
from ez2_backup_archive_guard import inspect
from ez2_backup_preflight import ROLES
from ez2_backup_scratch_replay import (
    MAX_SCRATCH_BYTES, MAX_SCRATCH_FILES, _replay_archive, _sha256,
)
from ez2_ci_file_upgrade import COMPONENTS, snapshot, unpack
from ez2_installed_code_parity import check as check_parity
from ez2_release_set import run as verify_release

SHA = re.compile(r"[0-9a-f]{40}\Z")
PHASES = ("after_theme_backup", "after_theme_install",
          "after_core_backup", "after_core_install",
          "after_candidate_verification")


def _scope(release, sha):
    catalog = verify_release("verify", release, sha)
    if (catalog.get("source_sha") != sha
            or catalog.get("target_site") != "ez2-isolated-only"
            or catalog.get("scope") != "engineering-evidence-only"
            or catalog.get("deployment_authorized") is not False
            or catalog.get("localwp_installed") is not False
            or catalog.get("one_click_complete") is not False):
        raise ValueError("Unapproved exact-head release")
    return catalog


def rehearse(candidate_release, installed_release, private_backup,
             installed_sha, candidate_sha, *, fault_phase=None):
    if (not isinstance(installed_sha, str) or not SHA.fullmatch(installed_sha)
            or not isinstance(candidate_sha, str) or not SHA.fullmatch(candidate_sha)
            or installed_sha == candidate_sha):
        raise ValueError("Distinct exact installed and candidate SHAs required")
    if fault_phase is not None and fault_phase not in PHASES:
        raise ValueError("Unknown scratch-only fault phase")
    candidate = _directory(candidate_release)
    installed = _directory(installed_release)
    backup = _directory(private_backup)
    paths = (candidate, installed, backup)
    if any(a == b or a in b.parents or b in a.parents
           for i, a in enumerate(paths) for b in paths[i + 1:]):
        raise ValueError("Release and private backup paths must be disjoint")
    _scope(candidate, candidate_sha)
    _scope(installed, installed_sha)
    proof = bind(installed, backup, installed_sha)
    if (proof.get("status") != "EXACT_HEAD_RELEASE_AND_PRIVATE_BACKUP_VERIFIED_ONLY"
            or proof.get("private_scratch_file_replay_verified") is not True
            or proof.get("deployment_authorized") is not False):
        raise ValueError("Installed backup is not verified")
    inventory = inspect(backup, installed_sha)["components"]
    roles = ("uploads", "plugins", "theme")
    files = sum(inventory[role]["files"] for role in roles)
    byte_count = sum(inventory[role]["uncompressed_bytes"] for role in roles)
    if files > MAX_SCRATCH_FILES or byte_count > MAX_SCRATCH_BYTES:
        raise ValueError("Scratch extraction budget exceeded")
    digests = {role: _sha256(backup / ROLES[role])
               for role in ("database", *roles)}

    with tempfile.TemporaryDirectory(prefix="ez2-upgrade-rehearsal-") as temp:
        root = Path(temp)
        live = root / "live" / "wp-content"
        stage = root / "stage" / "wp-content"
        saved = root / "rollback"
        live.mkdir(parents=True, mode=0o700)
        stage.mkdir(parents=True, mode=0o700)
        saved.mkdir(mode=0o700)
        count = total = 0
        for role in roles:
            n, size = _replay_archive(backup / ROLES[role], role, live,
                                       {"files": MAX_SCRATCH_FILES - count,
                                        "bytes": MAX_SCRATCH_BYTES - total})
            count += n
            total += size
        if count != files or total != byte_count:
            raise ValueError("Restored inventory differs from private backup")
        (live / "theme").rename(live / "themes")
        parity = check_parity(installed, installed_sha, live)
        if (parity.get("status") != "CODE_BYTES_MATCH_RELEASE_ONLY"
                or parity.get("mismatch_count") != 0
                or parity.get("deployment_authorized") is not False):
            raise ValueError("Backup first-party bytes differ from installed release")
        original = snapshot(live)
        for archive_name, category, folder, required in COMPONENTS:
            category = "themes" if category == "themes" else "plugins"
            destination = stage / category
            destination.mkdir(exist_ok=True)
            unpack(candidate / archive_name, destination, folder)
            if not (destination / folder / required).is_file():
                raise ValueError("Candidate release entrypoint missing")
        staged = check_parity(candidate, candidate_sha, stage)
        if staged.get("status") != "CODE_BYTES_MATCH_RELEASE_ONLY":
            raise ValueError("Staged candidate byte parity failed")

        moved = []
        injected = False
        try:
            for index, (_, category, folder, _) in enumerate(COMPONENTS):
                ordinal = ("theme", "core")[index]
                current = live / category / folder
                old = saved / category / folder
                old.parent.mkdir(parents=True, exist_ok=True)
                os.replace(current, old)
                moved.append((current, old))
                if fault_phase == "after_" + ordinal + "_backup":
                    raise RuntimeError("INJECTED_SCRATCH_ONLY_FAULT")
                os.replace(stage / category / folder, current)
                if fault_phase == "after_" + ordinal + "_install":
                    raise RuntimeError("INJECTED_SCRATCH_ONLY_FAULT")
            installed_candidate = check_parity(candidate, candidate_sha, live)
            if installed_candidate.get("status") != "CODE_BYTES_MATCH_RELEASE_ONLY":
                raise ValueError("Candidate scratch installation differs from release")
            if fault_phase == "after_candidate_verification":
                raise RuntimeError("INJECTED_SCRATCH_ONLY_FAULT")
        except RuntimeError as exc:
            if str(exc) != "INJECTED_SCRATCH_ONLY_FAULT":
                raise
            injected = True
        finally:
            for current, old in reversed(moved):
                if current.exists():
                    shutil.rmtree(current)
                os.replace(old, current)
        if snapshot(live) != original:
            raise ValueError("Scratch rollback did not restore original bytes")
        restored = check_parity(installed, installed_sha, live)
        if restored.get("status") != "CODE_BYTES_MATCH_RELEASE_ONLY":
            raise ValueError("Installed release not restored")
        if injected != (fault_phase is not None):
            raise ValueError("Scratch fault did not behave as requested")
        if any(_sha256(backup / ROLES[role]) != digest
               for role, digest in digests.items()):
            raise ValueError("Private backup changed during rehearsal")
    return {
        "status": "PRIVATE_BACKUP_CANDIDATE_SCRATCH_UPGRADE_ROLLBACK_VERIFIED_ONLY",
        "installed_source_sha": installed_sha,
        "candidate_source_sha": candidate_sha,
        "restored_private_files": files,
        "scratch_candidate_swap_rehearsed": True,
        "scratch_original_bytes_restored": True,
        "fault_injected": injected,
        "fault_phase": fault_phase or "none",
        "private_backup_unchanged": True,
        "database_sql_executed": False,
        "database_restore_rehearsed": False,
        "consistent_database_and_files_snapshot_verified": False,
        "wordpress_installed": False,
        "localwp_touched": False,
        "deployment_authorized": False,
        "can_apply": False,
        "one_click_complete": False,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 6:
            raise ValueError("Usage: ez2_checkpoint_upgrade_rehearsal.py CANDIDATE_RELEASE INSTALLED_RELEASE PRIVATE_BACKUP INSTALLED_SHA CANDIDATE_SHA")
        print(json.dumps(rehearse(*sys.argv[1:]), sort_keys=True))
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print("EZ2_CHECKPOINT_UPGRADE_REHEARSAL_FAIL: " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
