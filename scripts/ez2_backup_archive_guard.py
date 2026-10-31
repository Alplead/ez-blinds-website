#!/usr/bin/env python3
"""Read-only structural inspection of isolated EZ2 rollback backup archives.

Byte-integrity preflight runs first. No extraction, SQL execution, restore,
live-site identity check or deployment occurs. Never commit actual backups.
"""
import gzip
import json
import os
from contextlib import contextmanager
import re
import unicodedata
import sys
import tarfile
from pathlib import Path

from ez2_backup_preflight import ROLES, verify, regular_file, _identity

MAX_MEMBERS = 50000
MAX_MEMBER_BYTES = 2 * 1024 ** 3
MAX_ARCHIVE_BYTES = 16 * 1024 ** 3
MAX_SQL_BYTES = 16 * 1024 ** 3
CHUNK = 1024 * 1024
RESERVED = re.compile(r"(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\..*)?\Z", re.I)


def safe_member(name, role, is_dir=False):
    if not isinstance(name, str) or not 0 < len(name) <= 512 or "\\" in name or "\x00" in name:
        raise ValueError("Unsafe archive member name")
    if name.endswith("/") and (not is_dir or name.endswith("//")):
        raise ValueError("Ambiguous archive member trailing separator")
    parts = name.rstrip("/").split("/")
    if (name.startswith("/") or any(not part or part in (".", "..") or
        part.endswith((" ", ".")) or ":" in part or
        unicodedata.normalize("NFC", part) != part or
        any(ch in '<>"|?*' or unicodedata.category(ch) in ("Cc", "Cf", "Cs")
            for ch in part) or
        RESERVED.fullmatch(part) for part in parts)):
        raise ValueError("Unsafe archive member path")
    if len(parts) == 1 and parts[0] == role and is_dir:
        return role.casefold()
    if len(parts) < 2 or parts[0] != role:
        raise ValueError("Backup member escapes its declared component")
    return unicodedata.normalize("NFC", "/".join(parts)).casefold()


@contextmanager
def _safe_archive_input(path):
    """Pin the verified regular-file descriptor before gzip/tar decoding.

    An archive swapped for a FIFO after preflight must never block on open.
    This also refuses same-byte inode replacement during inspection.
    """
    initial = regular_file(path)
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(os.open(path, flags), "rb") as source:
        if _identity(os.fstat(source.fileno())) != _identity(initial):
            raise ValueError("Backup archive replaced before inspection")
        yield source
        if (_identity(os.fstat(source.fileno())) != _identity(initial)
                or _identity(regular_file(path)) != _identity(initial)):
            raise ValueError("Backup archive changed during inspection")


def inspect_tar(path, role):
    seen = set()
    regular_paths = set()
    implied_directories = set()
    directory_spellings = {}
    members = files = size = 0
    try:
        with _safe_archive_input(path) as source, tarfile.open(fileobj=source, mode="r:gz") as archive:
            for item in archive:
                members += 1
                if members > MAX_MEMBERS:
                    raise ValueError("Archive member count exceeds limit")
                key = safe_member(item.name, role, item.isdir())
                # The private snapshot packer writes restrictive, deterministic
                # restore metadata. A foreign tar can pass path/hash checks yet
                # restore privileged permissions, ownership or PAX xattrs.
                # Accept only the metadata our own rollback packer emits.
                expected_mode = 0o700 if item.isdir() else 0o600
                if (item.mode != expected_mode or item.uid != 0 or item.gid != 0
                        or item.mtime != 0 or item.uname or item.gname
                        or item.linkname or item.devmajor or item.devminor
                        or set(item.pax_headers) - {"path"}):
                    raise ValueError("Unsafe archive restore metadata")
                if key in seen:
                    raise ValueError("Duplicate or case-colliding archive member")
                seen.add(key)
                parts = key.split("/")
                original_parts = item.name.rstrip("/").split("/")
                for depth in range(1, len(parts)):
                    parent = "/".join(parts[:depth])
                    spelling = "/".join(original_parts[:depth])
                    previous = directory_spellings.setdefault(parent, spelling)
                    if previous != spelling:
                        raise ValueError("Case-colliding implicit archive directories")
                    if parent in regular_paths:
                        raise ValueError("File cannot contain a nested archive entry")
                    implied_directories.add(parent)
                if item.isdir():
                    spelling = "/".join(original_parts)
                    previous = directory_spellings.setdefault(key, spelling)
                    if previous != spelling:
                        raise ValueError("Case-colliding explicit archive directory")
                if item.isfile():
                    if key in implied_directories:
                        raise ValueError("File conflicts with an archive directory")
                    regular_paths.add(key)
                if item.isdir():
                    continue
                if not item.isfile() or item.size < 0 or item.size > MAX_MEMBER_BYTES:
                    raise ValueError("Unsupported archive entry type or size")
                size += item.size
                if size > MAX_ARCHIVE_BYTES:
                    raise ValueError("Archive expanded size exceeds limit")
                stream = archive.extractfile(item)
                if stream is None:
                    raise ValueError("Archive file content missing")
                actual = 0
                with stream:
                    while True:
                        chunk = stream.read(CHUNK)
                        if not chunk:
                            break
                        actual += len(chunk)
                if actual != item.size:
                    raise ValueError("Archive member truncated")
                files += 1
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise ValueError("Invalid compressed tar archive") from exc
    if files == 0:
        raise ValueError("Empty backup component archive")
    return {"members": members, "files": files, "uncompressed_bytes": size}


def inspect_sql(path):
    total = 0
    try:
        with _safe_archive_input(path) as source, gzip.GzipFile(fileobj=source, mode="rb") as stream:
            while True:
                chunk = stream.read(CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_SQL_BYTES:
                    raise ValueError("SQL dump expanded size exceeds limit")
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise ValueError("Invalid compressed SQL dump") from exc
    if total == 0:
        raise ValueError("Empty SQL dump")
    return {"uncompressed_bytes": total}


def inspect(root, exact_sha):
    integrity = verify(root, exact_sha)
    root = Path(root)
    # The first hash pass must describe the SAME file objects subsequently
    # inspected. Rechecking only archive structure is insufficient if a backup
    # changes after byte verification (including same-byte inode replacement).
    pinned = {"backup-manifest.json": _identity(regular_file(root / "backup-manifest.json"))}
    pinned.update({name: _identity(regular_file(root / name)) for name in ROLES.values()})
    directory_identity = _identity(root.lstat())
    summaries = {"database": inspect_sql(root / ROLES["database"])}
    for role in ("uploads", "plugins", "theme"):
        summaries[role] = inspect_tar(root / ROLES[role], role)
    # Verify again AFTER structural inspection. Otherwise the report could
    # certify archive bytes that were never covered by the first digest pass.
    verify(root, exact_sha)
    if (_identity(root.lstat()) != directory_identity or
            any(_identity(regular_file(root / name)) != identity
                for name, identity in pinned.items())):
        raise ValueError("Backup inputs changed during archive inspection")
    return {
        "status": "BACKUP_ARCHIVE_STRUCTURE_VERIFIED_ONLY",
        "source_sha": exact_sha,
        "target_site": "ez2-isolated-only",
        "components": summaries,
        "byte_integrity_verified": integrity["status"] == "BACKUP_BYTES_VERIFIED_ONLY",
        "archive_contents_inspected": True,
        "sql_executed": False,
        "extracted": False,
        "site_identity_verified": False,
        "restore_rehearsed": False,
        "deployment_authorized": False,
        "applied": False,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("Usage: ez2_backup_archive_guard.py BACKUP_DIRECTORY EXACT_SHA")
        print(json.dumps(inspect(sys.argv[1], sys.argv[2]), sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("EZ2_BACKUP_ARCHIVE_GUARD_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
