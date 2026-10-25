#!/usr/bin/env python3
"""Package a pre-captured isolated EZ2 snapshot into a private rollback set.

FILE packer only: no WordPress connection, SQL dump, SQL execution, install,
or production access. Input must be a pre-captured isolated snapshot.
Never commit a generated backup, manifest or private media to public Git.
"""
import gzip
import hashlib
import json
import os
import shutil
import stat
import sys
import tarfile
from pathlib import Path

from ez2_backup_archive_guard import (
    MAX_ARCHIVE_BYTES, MAX_MEMBER_BYTES, MAX_MEMBERS, safe_member, inspect,
)
from ez2_backup_preflight import ROLES

CHUNK = 1024 * 1024
SOURCE_FILES = {"database": "database.sql", "uploads": "uploads",
                "plugins": "plugins", "theme": "theme"}


def _regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Snapshot contains a link or non-regular file")
    if info.st_size <= 0 or info.st_size > MAX_MEMBER_BYTES:
        raise ValueError("Snapshot file size outside safe bounds")
    return info


def _files(root, role):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Snapshot component must be a real directory")
    result = []
    seen = set()
    total = 0
    for base, directories, files in os.walk(root, followlinks=False):
        for name in directories:
            directory = Path(base) / name
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError("Snapshot directory link or special entry")
            relative = directory.relative_to(root).as_posix()
            safe_member(role + "/" + relative, role, is_dir=True)
        for name in files:
            path = Path(base) / name
            info = _regular(path)
            member = role + "/" + path.relative_to(root).as_posix()
            folded = safe_member(member, role)
            if folded in seen:
                raise ValueError("Case-colliding snapshot file")
            seen.add(folded)
            result.append((path, member, info))
            total += info.st_size
            if len(result) > MAX_MEMBERS or total > MAX_ARCHIVE_BYTES:
                raise ValueError("Snapshot exceeds archive safety budget")
    if not result:
        raise ValueError("Empty snapshot component")
    return sorted(result, key=lambda item: item[1])


def _write_tar(destination, role, entries):
    with destination.open("xb") as output:
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for path, member, initial in entries:
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                with os.fdopen(os.open(path, flags), "rb") as source:
                    before = os.fstat(source.fileno())
                    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                            != (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns)):
                        raise ValueError("Snapshot file changed during packaging")
                    entry = tarfile.TarInfo(member)
                    entry.size = before.st_size
                    entry.mode = 0o600
                    entry.mtime = 0
                    archive.addfile(entry, source)
                    after = os.fstat(source.fileno())
                    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
                        raise ValueError("Snapshot file changed while reading")
    destination.chmod(0o600)


def _write_sql(source_path, destination):
    initial = _regular(source_path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(source_path, flags), "rb") as source:
        before = os.fstat(source.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns):
            raise ValueError("SQL source changed before packaging")
        with destination.open("xb") as output:
            with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as compressed:
                while True:
                    block = source.read(CHUNK)
                    if not block:
                        break
                    compressed.write(block)
        after = os.fstat(source.fileno())
        if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
            raise ValueError("SQL source changed while reading")
    destination.chmod(0o600)


def _digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def pack(snapshot_dir, destination_dir, exact_sha):
    if (not isinstance(exact_sha, str) or len(exact_sha) != 40
            or any(c not in "0123456789abcdef" for c in exact_sha)):
        raise ValueError("Exact 40-character source SHA required")
    source = Path(snapshot_dir)
    destination = Path(destination_dir)
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Snapshot source must be an existing real directory")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Backup destination must not exist")
    parent = destination.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("Backup parent must be an existing real directory")
    source_real = source.resolve(strict=True)
    parent_real = parent.resolve(strict=True)
    destination_real = parent_real / destination.name
    if (source_real == destination_real or source_real in destination_real.parents
            or destination_real in source_real.parents):
        raise ValueError("Backup must be outside the snapshot tree")
    if (source_real / "wp-config.php").exists() or (source_real / "wp-admin").exists():
        raise ValueError("Live WordPress roots are not accepted as snapshots")
    if {p.name for p in source.iterdir()} != set(SOURCE_FILES.values()):
        raise ValueError("Snapshot must contain only database.sql, uploads, plugins and theme")
    inventory = {role: _files(source / role, role)
                 for role in ("uploads", "plugins", "theme")}
    _regular(source / "database.sql")
    created = False
    try:
        destination.mkdir(mode=0o700)
        created = True
        _write_sql(source / "database.sql", destination / ROLES["database"])
        for role in ("uploads", "plugins", "theme"):
            _write_tar(destination / ROLES[role], role, inventory[role])
        manifest = {
            "schema_version": 1, "target_site": "ez2-isolated-only",
            "source_sha": exact_sha,
            "files": {role: {"name": filename,
                             "sha256": _digest(destination / filename),
                             "size_bytes": (destination / filename).stat().st_size}
                      for role, filename in ROLES.items()},
        }
        manifest_path = destination / "backup-manifest.json"
        with manifest_path.open("x", encoding="utf-8") as output:
            json.dump(manifest, output, sort_keys=True, separators=(",", ":"))
        manifest_path.chmod(0o600)
        result = inspect(destination, exact_sha)
        if result["status"] != "BACKUP_ARCHIVE_STRUCTURE_VERIFIED_ONLY":
            raise ValueError("Generated rollback set failed structural inspection")
        return {
            "status": "BACKUP_ARCHIVES_CREATED_AND_VERIFIED_ONLY",
            "source_sha": exact_sha, "target_site": "ez2-isolated-only",
            "components": sorted(ROLES), "byte_integrity_verified": True,
            "archive_contents_inspected": True, "database_dump_generated": False,
            "sql_executed": False, "restore_rehearsed": False,
            "wordpress_touched": False, "deployment_authorized": False,
        }
    except BaseException:
        if created:
            shutil.rmtree(destination)
        raise


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4:
            raise ValueError("Usage: ez2_backup_snapshot_pack.py SNAPSHOT_DIR NEW_PRIVATE_BACKUP_DIR EXACT_SHA")
        print(json.dumps(pack(sys.argv[1], sys.argv[2], sys.argv[3]), sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("EZ2_BACKUP_PACK_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
