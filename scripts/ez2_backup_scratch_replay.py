#!/usr/bin/env python3
"""Rehearse EZ2 rollback *file extraction* in an auto-deleted private scratch dir.

This is NOT a WordPress/database restore, an LP operation, or an install grant.
The only filesystem writes are beneath a newly created 0700 temporary directory.
Do not run against production backups or commit real backup bytes to public Git.
"""
import hashlib
import json
import os
import sys
import tarfile
import tempfile
from pathlib import Path

from ez2_backup_archive_guard import inspect, safe_member
from ez2_backup_preflight import ROLES

MAX_SCRATCH_BYTES = 1024 * 1024 * 1024  # 1 GiB; fail closed before filling a disk.
MAX_SCRATCH_FILES = 50000
CHUNK = 1024 * 1024


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _replay_archive(archive_path, role, scratch, budget):
    files = 0
    total = 0
    seen = set()
    with tarfile.open(archive_path, "r:gz") as archive:
        for item in archive:
            folded = safe_member(item.name, role, item.isdir())
            if folded in seen:
                raise ValueError("Duplicate archive entry on replay")
            seen.add(folded)
            if not (item.isfile() or item.isdir()):
                raise ValueError("Unsupported replay member type")
            relative = item.name.rstrip("/").split("/")
            destination = scratch.joinpath(*relative)
            # Paths were checked by safe_member; scratch is a fresh private dir.
            if item.isdir():
                if destination.is_file() or destination.is_symlink():
                    raise ValueError("Replay directory collides with file")
                destination.mkdir(parents=True, exist_ok=True, mode=0o700)
                continue
            if destination.exists() or destination.is_symlink():
                raise ValueError("Replay would overwrite a file")
            files += 1
            total += item.size
            if files > budget["files"] or total > budget["bytes"]:
                raise ValueError("Scratch replay exceeds file/byte budget")
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            source = archive.extractfile(item)
            if source is None:
                raise ValueError("Missing archive member bytes")
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            original = hashlib.sha256()
            actual = 0
            with source, os.fdopen(os.open(destination, flags, 0o600), "wb") as target:
                while True:
                    block = source.read(CHUNK)
                    if not block:
                        break
                    actual += len(block)
                    if actual > item.size:
                        raise ValueError("Member expanded beyond declared size")
                    original.update(block)
                    target.write(block)
            if actual != item.size or _sha256(destination) != original.hexdigest():
                raise ValueError("Scratch file failed round-trip verification")
    return files, total


def replay(backup_dir, exact_sha):
    backup_dir = Path(backup_dir)
    verified = inspect(backup_dir, exact_sha)
    if (verified["status"] != "BACKUP_ARCHIVE_STRUCTURE_VERIFIED_ONLY"
            or not verified["byte_integrity_verified"]
            or not verified["archive_contents_inspected"]
            or verified["target_site"] != "ez2-isolated-only"):
        raise ValueError("Backup archive guard did not pass")
    summaries = verified["components"]
    roles = ("uploads", "plugins", "theme")
    predicted_files = sum(summaries[role]["files"] for role in roles)
    predicted_bytes = sum(summaries[role]["uncompressed_bytes"] for role in roles)
    if predicted_files > MAX_SCRATCH_FILES or predicted_bytes > MAX_SCRATCH_BYTES:
        raise ValueError("Scratch replay budget exceeded before extraction")
    # Verify archive digests again before and after replay to detect changes
    # between the guard's read and this scratch-only extraction.
    manifest = json.loads((backup_dir / "backup-manifest.json").read_text(encoding="utf-8"))
    digests = {role: manifest["files"][role]["sha256"] for role in roles}
    if any(_sha256(backup_dir / ROLES[role]) != digests[role] for role in roles):
        raise ValueError("Backup archive changed after inspection")
    count = total = 0
    with tempfile.TemporaryDirectory(prefix="ez2-scratch-replay-") as private:
        scratch = Path(private)
        for role in roles:
            n, size = _replay_archive(backup_dir / ROLES[role], role, scratch,
                                      {"files": MAX_SCRATCH_FILES - count,
                                       "bytes": MAX_SCRATCH_BYTES - total})
            count += n
            total += size
        if count != predicted_files or total != predicted_bytes:
            raise ValueError("Scratch replay differs from verified archive inventory")
        if any(_sha256(backup_dir / ROLES[role]) != digests[role] for role in roles):
            raise ValueError("Backup archive changed during replay")
        # All replayed bytes disappear when the private TemporaryDirectory exits.
    return {
        "status": "SCRATCH_FILE_REPLAY_VERIFIED_ONLY",
        "target_site": "ez2-isolated-only",
        "source_sha": exact_sha,
        "replayed_files": count,
        "replayed_bytes": total,
        "scratch_deleted": True,
        "database_sql_executed": False,
        "wordpress_restored": False,
        "restore_rehearsed": False,
        "localwp_touched": False,
        "deployment_authorized": False,
        "applied": False,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("Usage: ez2_backup_scratch_replay.py BACKUP_DIR INSTALLED_EXACT_SHA")
        print(json.dumps(replay(sys.argv[1], sys.argv[2]), sort_keys=True))
    except (ValueError, OSError, TypeError, KeyError, tarfile.TarError) as exc:
        print("EZ2_SCRATCH_REPLAY_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
