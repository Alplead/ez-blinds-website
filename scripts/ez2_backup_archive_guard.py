#!/usr/bin/env python3
"""Read-only structural inspection of isolated EZ2 rollback backup archives.

Byte-integrity preflight runs first. No extraction, SQL execution, restore,
live-site identity check or deployment occurs. Never commit actual backups.
"""
import gzip
import json
import re
import unicodedata
import sys
import tarfile
from pathlib import Path

from ez2_backup_preflight import ROLES, verify

MAX_MEMBERS = 50000
MAX_MEMBER_BYTES = 2 * 1024 ** 3
MAX_ARCHIVE_BYTES = 16 * 1024 ** 3
MAX_SQL_BYTES = 16 * 1024 ** 3
CHUNK = 1024 * 1024
RESERVED = re.compile(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?\Z", re.I)


def safe_member(name, role, is_dir=False):
    if not isinstance(name, str) or not 0 < len(name) <= 512 or "\\" in name or "\x00" in name:
        raise ValueError("Unsafe archive member name")
    if name.endswith("/") and (not is_dir or name.endswith("//")):
        raise ValueError("Ambiguous archive member trailing separator")
    parts = name.rstrip("/").split("/")
    if (name.startswith("/") or any(not part or part in (".", "..") or
        part.endswith((" ", ".")) or ":" in part or
        any(ord(ch) < 32 or ord(ch) == 127 for ch in part) or
        RESERVED.fullmatch(part) for part in parts)):
        raise ValueError("Unsafe archive member path")
    if len(parts) == 1 and parts[0] == role and is_dir:
        return role.casefold()
    if len(parts) < 2 or parts[0] != role:
        raise ValueError("Backup member escapes its declared component")
    return unicodedata.normalize("NFC", "/".join(parts)).casefold()


def inspect_tar(path, role):
    seen = set()
    regular_paths = set()
    implied_directories = set()
    members = files = size = 0
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            for item in archive:
                members += 1
                if members > MAX_MEMBERS:
                    raise ValueError("Archive member count exceeds limit")
                key = safe_member(item.name, role, item.isdir())
                if key in seen:
                    raise ValueError("Duplicate or case-colliding archive member")
                seen.add(key)
                parts = key.split("/")
                for depth in range(1, len(parts)):
                    parent = "/".join(parts[:depth])
                    if parent in regular_paths:
                        raise ValueError("File cannot contain a nested archive entry")
                    implied_directories.add(parent)
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
        with gzip.open(path, "rb") as stream:
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
    summaries = {"database": inspect_sql(root / ROLES["database"])}
    for role in ("uploads", "plugins", "theme"):
        summaries[role] = inspect_tar(root / ROLES[role], role)
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
