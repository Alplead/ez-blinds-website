#!/usr/bin/env python3
"""Read-only verification of an isolated EZ2 rollback backup set.

Run only against an operator-controlled local backup directory. This does not
create a backup, read WordPress credentials, restore data, or grant deployment.
Never commit a real backup, its manifest, or private media to public GitHub.
"""
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
ROLES = {
    "database": "database.sql.gz",
    "uploads": "uploads.tar.gz",
    "plugins": "plugins.tar.gz",
    "theme": "theme.tar.gz",
}
MAX_MANIFEST_BYTES = 16384


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate manifest key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("Non-finite manifest number")


def regular_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Backup input must be a single-link regular file")
    return info


def _identity(info):
    """Detect same-size rewrites and path replacement, not just byte counts."""
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_nlink)


def checked_read(path, *, max_bytes=None, collect=False):
    """Read verified bytes from the same regular-file descriptor we inspect.

    A path may be replaced after lstat but before open, or during hashing.
    Refuse those changes instead of trusting an unbound Path.open() read.
    """
    initial = regular_file(path)
    if max_bytes is not None and not 0 < initial.st_size <= max_bytes:
        raise ValueError("Invalid backup manifest size")
    # A regular file can be replaced with a FIFO between lstat and open.
    # O_NONBLOCK prevents that substitution from hanging the verifier; the
    # descriptor identity check below rejects the changed file type.
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        if _identity(before) != _identity(initial):
            raise ValueError("Backup input replaced before reading")
        digest = hashlib.sha256()
        chunks = [] if collect else None
        total = 0
        for block in iter(lambda: source.read(1024 * 1024), b""):
            total += len(block)
            if max_bytes is not None and total > max_bytes:
                raise ValueError("Backup manifest exceeds safe size")
            digest.update(block)
            if chunks is not None:
                chunks.append(block)
        after = os.fstat(source.fileno())
        if total != initial.st_size or _identity(after) != _identity(initial):
            raise ValueError("Backup input changed while reading")
    if _identity(regular_file(path)) != _identity(initial):
        raise ValueError("Backup input path changed during verification")
    return initial, digest.hexdigest(), b"".join(chunks) if chunks is not None else None


def verify(root, expected_sha):
    root = Path(root)
    if not isinstance(expected_sha, str) or not SHA.fullmatch(expected_sha):
        raise ValueError("Invalid exact source SHA")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Invalid backup directory")
    root_before = root.lstat()
    # A rollback set is a closed inventory. Undeclared files, directories and
    # symlinks must not ride along with the four verified backup components.
    expected_entries = {"backup-manifest.json", *ROLES.values()}
    if {entry.name for entry in root.iterdir()} != expected_entries:
        raise ValueError("Unexpected or missing rollback backup entries")
    manifest_path = root / "backup-manifest.json"
    manifest_stat, _, manifest_bytes = checked_read(
        manifest_path, max_bytes=MAX_MANIFEST_BYTES, collect=True)
    manifest = json.loads(manifest_bytes.decode("utf-8"),
                          object_pairs_hook=unique, parse_constant=reject_constant)
    if (not isinstance(manifest, dict)
            or set(manifest) != {"schema_version", "target_site", "source_sha", "files"}
            or type(manifest["schema_version"]) is not int
            or manifest["schema_version"] != 1
            or manifest["target_site"] != "ez2-isolated-only"
            or manifest["source_sha"] != expected_sha):
        raise ValueError("Wrong site, source or manifest schema")
    files = manifest["files"]
    if not isinstance(files, dict) or set(files) != set(ROLES):
        raise ValueError("All four rollback components are mandatory")
    seen_inodes = set()
    verified_files = {"backup-manifest.json": _identity(manifest_stat)}
    total = 0
    for role, filename in ROLES.items():
        record = files[role]
        if (not isinstance(record, dict) or set(record) != {"name", "sha256", "size_bytes"}
                or record["name"] != filename
                or not isinstance(record["sha256"], str)
                or not DIGEST.fullmatch(record["sha256"])
                or type(record["size_bytes"]) is not int
                or record["size_bytes"] <= 0):
            raise ValueError("Invalid backup component metadata: " + role)
        path = root / filename
        info, digest, _ = checked_read(path)
        if info.st_size != record["size_bytes"]:
            raise ValueError("Backup component size mismatch: " + role)
        inode = (info.st_dev, info.st_ino)
        if inode in seen_inodes:
            raise ValueError("Aliased backup components")
        seen_inodes.add(inode)
        if digest != record["sha256"]:
            raise ValueError("Backup component checksum mismatch: " + role)
        verified_files[filename] = _identity(info)
        total += info.st_size
    # Re-check the closed inventory after all reads. A component modified
    # after its individual digest must not be accepted as the same backup set.
    if (_identity(root.lstat()) != _identity(root_before)
            or root.is_symlink() or not root.is_dir()
            or {entry.name for entry in root.iterdir()} != expected_entries):
        raise ValueError("Backup directory changed during verification")
    for filename, identity in verified_files.items():
        if _identity(regular_file(root / filename)) != identity:
            raise ValueError("Backup component changed after hashing")
    return {
        "status": "BACKUP_BYTES_VERIFIED_ONLY",
        "source_sha": expected_sha,
        "target_site": "ez2-isolated-only",
        "verified_components": sorted(ROLES),
        "verified_bytes": total,
        "site_identity_verified": False,
        "archive_contents_inspected": False,
        "restore_rehearsed": False,
        "deployment_authorized": False,
        "applied": False,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("Usage: ez2_backup_preflight.py BACKUP_DIRECTORY EXACT_SHA")
        print(json.dumps(verify(sys.argv[1], sys.argv[2]), sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print("EZ2_BACKUP_PREFLIGHT_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
