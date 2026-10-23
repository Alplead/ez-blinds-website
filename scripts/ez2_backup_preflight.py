#!/usr/bin/env python3
"""Read-only verification of an isolated EZ2 rollback backup set.

Run only against an operator-controlled local backup directory. This does not
create a backup, read WordPress credentials, restore data, or grant deployment.
Never commit a real backup, its manifest, or private media to public GitHub.
"""
import hashlib
import json
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


def verify(root, expected_sha):
    root = Path(root)
    if not isinstance(expected_sha, str) or not SHA.fullmatch(expected_sha):
        raise ValueError("Invalid exact source SHA")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Invalid backup directory")
    # A rollback set is a closed inventory. Undeclared files, directories and
    # symlinks must not ride along with the four verified backup components.
    expected_entries = {"backup-manifest.json", *ROLES.values()}
    if {entry.name for entry in root.iterdir()} != expected_entries:
        raise ValueError("Unexpected or missing rollback backup entries")
    manifest_path = root / "backup-manifest.json"
    manifest_stat = regular_file(manifest_path)
    if not 0 < manifest_stat.st_size <= MAX_MANIFEST_BYTES:
        raise ValueError("Invalid backup manifest size")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"),
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
        info = regular_file(path)
        if info.st_size != record["size_bytes"]:
            raise ValueError("Backup component size mismatch: " + role)
        inode = (info.st_dev, info.st_ino)
        if inode in seen_inodes:
            raise ValueError("Aliased backup components")
        seen_inodes.add(inode)
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != record["sha256"]:
            raise ValueError("Backup component checksum mismatch: " + role)
        total += info.st_size
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
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("EZ2_BACKUP_PREFLIGHT_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
