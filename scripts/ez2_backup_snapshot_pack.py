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
MIN_FREE_RESERVE = 128 * 1024 * 1024  # Do not consume the backup volume's last 128 MiB.
SOURCE_FILES = {"database": "database.sql", "uploads": "uploads",
                "plugins": "plugins", "theme": "theme"}


def _git_checkout_ancestor(path):
    """Refuse private backups in a normal Git checkout or linked worktree.

    Inspect resolved ancestors so a symlinked destination cannot hide a
    checkout. A .git *file* is also a worktree marker, not just a directory.
    """
    current = Path(path).resolve(strict=True)
    while True:
        marker = current / ".git"
        if marker.exists() or marker.is_symlink():
            return True
        if current.parent == current:
            return False
        current = current.parent


def _regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Snapshot contains a link or non-regular file")
    if info.st_size <= 0 or info.st_size > MAX_MEMBER_BYTES:
        raise ValueError("Snapshot file size outside safe bounds")
    return info


def _walk_error(exc):
    """Never silently omit an unreadable subtree from a private rollback set."""
    raise ValueError("Cannot enumerate complete snapshot directory") from exc


def _files(root, role, *, allow_empty=False):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Snapshot component must be a real directory")
    result = []
    seen = set()
    # A Linux fixture may contain Photos/ and photos/ as distinct folders,
    # but restoring both on Windows LocalWP would silently merge them.
    # Track directory spelling as well as file spelling before writing ZIPs.
    directory_spellings = {}
    total = 0
    for base, directories, files in os.walk(root, followlinks=False, onerror=_walk_error):
        for name in directories:
            directory = Path(base) / name
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError("Snapshot directory link or special entry")
            member = role + "/" + directory.relative_to(root).as_posix()
            folded = safe_member(member, role, is_dir=True)
            previous = directory_spellings.setdefault(folded, member)
            if previous != member or folded in seen:
                raise ValueError("Case-colliding snapshot directory or file")
        for name in files:
            path = Path(base) / name
            info = _regular(path)
            member = role + "/" + path.relative_to(root).as_posix()
            folded = safe_member(member, role)
            if folded in seen or folded in directory_spellings:
                raise ValueError("Case-colliding snapshot file or directory")
            seen.add(folded)
            result.append((path, member, info))
            total += info.st_size
            if len(result) > MAX_MEMBERS or total > MAX_ARCHIVE_BYTES:
                raise ValueError("Snapshot exceeds archive safety budget")
    if not result and not allow_empty:
        raise ValueError("Empty snapshot component")
    return sorted(result, key=lambda item: item[1])


def _directory_inventory(root, role):
    """Track even empty directories, which a file-only inventory misses.

    A directory replaced under the same name can change the source tree
    without changing the identity of any archived file. Refuse that drift.
    This is a consistency guard, not a claim that empty dirs are restored.
    """
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Snapshot component must be a real directory")
    result = []
    for base, directories, _files_in_dir in os.walk(
            root, followlinks=False, onerror=_walk_error):
        path = Path(base)
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or path.is_symlink():
            raise ValueError("Snapshot directory changed during packaging")
        relative = path.relative_to(root).as_posix()
        member = role if relative == "." else role + "/" + relative
        folded = safe_member(member, role, is_dir=True)
        result.append((folded, member, info.st_dev, info.st_ino))
        for name in directories:
            child = path / name
            if child.is_symlink() or not child.is_dir():
                raise ValueError("Snapshot directory link or special entry")
    return tuple(sorted(result))


def _file_identity(info):
    """Include ctime/link count: size and restored mtime can conceal a rewrite."""
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_nlink)


def _write_tar(destination, role, entries):
    # Preserve empty directories as well as files. A rollback that omits an
    # empty uploads/plugin directory is not a complete filesystem replay.
    # Infer the component root from the first already-validated file entry.
    first_path, first_member, _ = entries[0]
    root = first_path
    for _ in first_member.split("/")[1:]:
        root = root.parent
    directories = _directory_inventory(root, role)
    if len(directories) + len(entries) > MAX_MEMBERS:
        raise ValueError("Snapshot directories exceed archive member budget")
    with destination.open("xb") as output:
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for _, member, device, inode in directories:
                path = root.joinpath(*member.split("/")[1:])
                info = path.lstat()
                if (not stat.S_ISDIR(info.st_mode) or path.is_symlink()
                        or (info.st_dev, info.st_ino) != (device, inode)):
                    raise ValueError("Snapshot directory changed during packaging")
                entry = tarfile.TarInfo(member + "/")
                entry.type = tarfile.DIRTYPE
                entry.mode = 0o700
                entry.mtime = 0
                archive.addfile(entry)
            for path, member, initial in entries:
                flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0))
                with os.fdopen(os.open(path, flags), "rb") as source:
                    before = os.fstat(source.fileno())
                    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                            or _file_identity(before) != _file_identity(initial)):
                        raise ValueError("Snapshot file changed during packaging")
                    entry = tarfile.TarInfo(member)
                    entry.size = before.st_size
                    entry.mode = 0o600
                    entry.mtime = 0
                    archive.addfile(entry, source)
                    after = os.fstat(source.fileno())
                    if _file_identity(after) != _file_identity(before):
                        raise ValueError("Snapshot file changed while reading")
    destination.chmod(0o600)


def _write_sql(source_path, destination):
    initial = _regular(source_path)
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(os.open(source_path, flags), "rb") as source:
        before = os.fstat(source.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or _file_identity(before) != _file_identity(initial)):
            raise ValueError("SQL source changed before packaging")
        with destination.open("xb") as output:
            with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as compressed:
                while True:
                    block = source.read(CHUNK)
                    if not block:
                        break
                    compressed.write(block)
        after = os.fstat(source.fileno())
        if _file_identity(after) != _file_identity(before):
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
    # The verifier rejects linked backup ancestors. Apply the same rule
    # before packaging, so a private snapshot or destination cannot be
    # redirected through an otherwise ordinary-looking parent directory.
    if source_real != source.absolute() or parent_real != parent.absolute():
        raise ValueError("Linked snapshot or backup parent ancestor")
    destination_real = parent_real / destination.name
    if (source_real == destination_real or source_real in destination_real.parents
            or destination_real in source_real.parents):
        raise ValueError("Backup must be outside the snapshot tree")
    if _git_checkout_ancestor(source_real) or _git_checkout_ancestor(parent_real):
        raise ValueError("Private snapshot and backup must stay outside Git checkouts")
    if (source_real / "wp-config.php").exists() or (source_real / "wp-admin").exists():
        raise ValueError("Live WordPress roots are not accepted as snapshots")
    if {p.name for p in source.iterdir()} != set(SOURCE_FILES.values()):
        raise ValueError("Snapshot must contain only database.sql, uploads, plugins and theme")
    inventory = {role: _files(source / role, role)
                 for role in ("uploads", "plugins", "theme")}
    directory_inventory = {
        role: _directory_inventory(source / role, role)
        for role in ("uploads", "plugins", "theme")
    }
    sql_info = _regular(source / "database.sql")
    # Conservative upper bound: compressed output should never need more than
    # raw input plus this reserve. Refuse before creating any private output.
    required = sql_info.st_size + sum(
        info.st_size for entries in inventory.values() for _, _, info in entries
    ) + MIN_FREE_RESERVE
    if shutil.disk_usage(parent_real).free < required:
        raise ValueError("Insufficient free space for isolated private backup")
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
        # A per-file read check is not enough: new files may appear, old files
        # may disappear, or SQL may change after its gzip stream has closed.
        # Re-enumerate the entire snapshot before accepting this rollback set.
        if _file_identity(_regular(source / "database.sql")) != _file_identity(sql_info):
            raise ValueError("Snapshot SQL changed after packaging")
        for role, initial_entries in inventory.items():
            final_entries = _files(source / role, role, allow_empty=True)
            initial_state = tuple((member, _file_identity(info))
                                  for _, member, info in initial_entries)
            final_state = tuple((member, _file_identity(info))
                                for _, member, info in final_entries)
            if final_state != initial_state:
                raise ValueError("Snapshot inventory changed after packaging")
            if _directory_inventory(source / role, role) != directory_inventory[role]:
                raise ValueError("Snapshot directory inventory changed after packaging")
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
