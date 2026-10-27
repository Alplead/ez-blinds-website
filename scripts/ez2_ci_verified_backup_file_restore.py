#!/usr/bin/env python3
"""REAL filesystem rename/rollback rehearsal of an EZ2 verified 4-part backup.

Only inside a new auto-deleted, private, disposable CI directory. Source
WordPress, LocalWP, SQL, production and original private archives are NEVER
modified. SQL is separately rehearsed by ez2_ci_wordpress_db_restore.sh.

Unlike archive extraction-only verification, this exercises installed ->
backup, incoming -> installed, injected faults and explicit rollback for all
three restored WordPress file components (uploads, plugins, theme).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

from ez2_backup_archive_guard import inspect
from ez2_backup_preflight import ROLES
from ez2_backup_scratch_replay import _replay_archive

ROLES_TO_RESTORE = ("uploads", "plugins", "theme")
MAX_BYTES = 64 * 1024 * 1024
MAX_FILES = 500
SHA = re.compile(r"[0-9a-f]{40}\Z")
CHUNK = 1024 * 1024


def fingerprint(root: Path) -> dict[str, str]:
    """Inspect exact bytes and relative paths, refusing links and special files."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Unsafe synthetic restore directory")
    files: dict[str, str] = {}
    total = 0
    for where, directories, filenames in os.walk(root, followlinks=False):
        for dirname in directories:
            entry = Path(where) / dirname
            if entry.is_symlink() or not entry.is_dir():
                raise ValueError("Symlink or special directory in restore fixture")
        for filename in filenames:
            entry = Path(where) / filename
            info = entry.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("Link or special file in restore fixture")
            if info.st_size > MAX_BYTES:
                raise ValueError("Oversized restore fixture file")
            total += info.st_size
            if total > MAX_BYTES or len(files) >= MAX_FILES:
                raise ValueError("Restore fixture budget exceeded")
            name = entry.relative_to(root).as_posix()
            digest = hashlib.sha256()
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            with os.fdopen(os.open(entry, flags), "rb") as file:
                for block in iter(lambda: file.read(CHUNK), b""):
                    digest.update(block)
                if os.fstat(file.fileno()).st_size != info.st_size:
                    raise ValueError("Restore file modified during fingerprint")
            files[name] = digest.hexdigest()
    if not files:
        raise ValueError("Empty restore fixture component")
    return dict(sorted(files.items()))


def verify_role_set(root: Path, expected: dict[str, dict[str, str]]) -> None:
    if set(path.name for path in root.iterdir()) != set(ROLES_TO_RESTORE):
        raise ValueError("Restored component inventory differs")
    for role in ROLES_TO_RESTORE:
        if fingerprint(root / role) != expected[role]:
            raise ValueError("Restored component bytes differ")


def safe_move(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_dir() or destination.exists() or destination.is_symlink():
        raise ValueError("Unsafe or pre-existing synthetic restore target")
    source.rename(destination)


def restore(saved: Path, installed: Path, incoming: Path,
            baseline: dict[str, dict[str, str]],
            candidate: dict[str, dict[str, str]]) -> None:
    """Fail closed BEFORE moves if any backup, candidate or marker was changed."""
    verify_role_set(saved, baseline)
    verify_role_set(installed, candidate)
    if list(incoming.iterdir()):
        raise ValueError("Restore input unexpectedly populated")

    # This is only a disposable CI rehearsal. Live LocalWP restore also needs
    # a durable journal, application-level maintenance lock and real site gate.
    for role in ROLES_TO_RESTORE:
        safe_move(installed / role, incoming / role)
        safe_move(saved / role, installed / role)
    verify_role_set(installed, baseline)
    verify_role_set(incoming, candidate)


def run_one(master: Path, expected: dict[str, dict[str, str]],
            scenario: str | None, parent: Path) -> None:
    current = parent / ("case-" + (scenario or "success").replace(":", "-"))
    current.mkdir(mode=0o700)
    incoming = current / "incoming"
    installed = current / "installed"
    saved = current / "backup"
    incoming.mkdir(mode=0o700)
    installed.mkdir(mode=0o700)
    saved.mkdir(mode=0o700)
    for role in ROLES_TO_RESTORE:
        # Fresh read-only archive extract was already verified byte-for-byte;
        # copy into the private attempt before any synthetic installation.
        import shutil
        shutil.copytree(master / role, incoming / role, symlinks=False)
        (installed / role).mkdir(mode=0o700)
        (installed / role / "original-ci-marker.txt").write_bytes(
            ("SYNTHETIC-OLD-ONLY:" + role + "\n").encode("ascii"))
    original = {role: fingerprint(installed / role) for role in ROLES_TO_RESTORE}
    verify_role_set(incoming, expected)

    backed_up: list[str] = []
    candidates_installed: list[str] = []
    injected = False
    try:
        for role in ROLES_TO_RESTORE:
            safe_move(installed / role, saved / role)
            backed_up.append(role)
            if scenario == "after-backup:" + role:
                raise OSError("INJECTED_SYNTHETIC_RENAME_ERROR")
            safe_move(incoming / role, installed / role)
            candidates_installed.append(role)
            if scenario == "after-install:" + role:
                raise OSError("INJECTED_SYNTHETIC_RENAME_ERROR")
        verify_role_set(installed, expected)
        verify_role_set(saved, original)
    except (OSError, ValueError, RuntimeError) as error:
        # Real operating-system rename failures must trigger the SAME recovery
        # as deliberately injected faults. After a verified rollback, propagate
        # any unexpected error rather than pretending an install succeeded.
        injected = str(error) == "INJECTED_SYNTHETIC_RENAME_ERROR"
        # Rollback last-touched component first; preserve the candidate for
        # inspection and restore old bytes to their exact original paths.
        for role in reversed(backed_up):
            if role in candidates_installed:
                safe_move(installed / role, incoming / role)
            safe_move(saved / role, installed / role)
        verify_role_set(installed, original)
        verify_role_set(incoming, expected)
        if list(saved.iterdir()):
            raise ValueError("Synthetic rollback left orphaned backups")
        if not injected:
            raise
    if scenario is not None:
        if not injected:
            raise ValueError("Requested synthetic fault was not exercised")
        return

    # Completed candidate transaction still holds all three original backups.
    verify_role_set(saved, original)
    restore(saved, installed, incoming, original, expected)

    # A forged or damaged retained backup must NOT replace installed data.
    # Start another clean successful swap to exercise corrupt-backup refusal.
    # Following restore, "incoming" contains candidate and installed originals.
    for role in ROLES_TO_RESTORE:
        safe_move(installed / role, saved / role)
        safe_move(incoming / role, installed / role)
    verify_role_set(installed, expected)
    damaged = saved / "theme" / "original-ci-marker.txt"
    original_bytes = damaged.read_bytes()
    damaged.write_bytes(b"TAMPERED-SYNTHETIC-RECOVERY")
    try:
        restore(saved, installed, incoming, original, expected)
    except ValueError as exc:
        if "Restored component bytes differ" not in str(exc):
            raise
    else:
        raise ValueError("Tampered original backup was incorrectly accepted")
    verify_role_set(installed, expected)
    damaged.write_bytes(original_bytes)
    restore(saved, installed, incoming, original, expected)


def rehearse(backup_dir: str | Path, source_sha: str) -> dict:
    """Never run from desktop/LocalWP; CI fixture opt-in required."""
    if os.environ.get("GITHUB_ACTIONS") != "true" or (
        os.environ.get("EZ2_CI_VERIFIED_FILE_RESTORE") != "YES_DISPOSABLE_RELEASE_STACK"
    ):
        raise ValueError("Verified file restore only allowed in disposable CI")
    if not isinstance(source_sha, str) or not SHA.fullmatch(source_sha):
        raise ValueError("Exact source SHA required")
    proof = inspect(backup_dir, source_sha)
    if (proof["status"] != "BACKUP_ARCHIVE_STRUCTURE_VERIFIED_ONLY"
            or not proof["byte_integrity_verified"]
            or proof["target_site"] != "ez2-isolated-only"):
        raise ValueError("Backup source not verified")
    count = sum(proof["components"][role]["files"] for role in ROLES_TO_RESTORE)
    total = sum(proof["components"][role]["uncompressed_bytes"] for role in ROLES_TO_RESTORE)
    if count > MAX_FILES or total > MAX_BYTES:
        raise ValueError("Synthetic backup too large for disposable recovery rehearsal")

    with tempfile.TemporaryDirectory(prefix="ez2-ci-verified-file-restore-") as temp:
        workspace = Path(temp)
        workspace.chmod(0o700)
        master = workspace / "verified-source"
        master.mkdir(mode=0o700)
        for role in ROLES_TO_RESTORE:
            _replay_archive(Path(backup_dir) / ROLES[role], role, master,
                            {"files": MAX_FILES, "bytes": MAX_BYTES})
        expected = {role: fingerprint(master / role) for role in ROLES_TO_RESTORE}
        if sum(len(v) for v in expected.values()) != count:
            raise ValueError("Backup extraction differs from verified file count")
        attempts = workspace / "attempts"
        attempts.mkdir(mode=0o700)
        scenarios = [action + ":" + role
                     for role in ROLES_TO_RESTORE
                     for action in ("after-backup", "after-install")]
        for scenario in scenarios:
            run_one(master, expected, scenario, attempts)
        run_one(master, expected, None, attempts)

    return {
        "status": "EZ2_CI_VERIFIED_BACKUP_FILE_RESTORE_PASS",
        "components": len(ROLES_TO_RESTORE),
        "files_rehearsed": count,
        "injected_faults_restored": len(scenarios),
        "successful_swap_and_explicit_restore": True,
        "tampered_backup_refused": True,
        "private_scratch_deleted": True,
        "source_sha": source_sha,
        "database_restore_rehearsed_here": False,
        "owner_localwp_touched": False,
        "one_click_ready": False,
        "can_apply": False,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("Usage: ez2_ci_verified_backup_file_restore.py BACKUP_DIR EXACT_SHA")
        print(json.dumps(rehearse(sys.argv[1], sys.argv[2]), sort_keys=True))
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        print("EZ2_CI_VERIFIED_BACKUP_FILE_RESTORE_HOLD: " + str(exc), file=sys.stderr)
        sys.exit(1)
