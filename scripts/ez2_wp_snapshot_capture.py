#!/usr/bin/env python3
"""Opt-in isolated EZ2 WordPress read-only capture + private rollback pack.

Requires a separately authorised EZ2-only WP-CLI runtime. Never run on
production, T2 or EZ BNS New Dev. This tool does not deploy or restore.
The SQL export and copied private files MUST remain outside public Git.
"""
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from ez2_backup_snapshot_pack import _directory_inventory, _files, _regular, pack
from ez2_backup_scratch_replay import replay

HOST = re.compile(r"ez2(?:-[a-z0-9]+)*\.local\Z")
VERSION = re.compile(r"[1-9][0-9]{0,2}\.[0-9]{1,3}\.[0-9]{1,3}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
NAME = re.compile(r"ez2-backup-[a-z0-9-]{3,64}\Z")
CHUNK = 1024 * 1024


def _inside(path, root):
    return path == root or root in path.parents


def _real_directory(path):
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("A required directory is missing or linked")
    real = path.resolve(strict=True)
    if real != path.absolute():
        raise ValueError("Linked ancestor in required directory")
    return real


def _private_parent_outside_git(parent):
    """Reject private backup destinations inside any Git worktree.

    A public repository must never contain SQL, media, or customer backups,
    even as untracked files. Worktrees use a .git *file*, not a directory.
    This guard is intentionally independent of gitignore configuration.
    """
    for directory in (parent, *parent.parents):
        marker = directory / ".git"
        if marker.exists() or marker.is_symlink():
            raise ValueError("Private backup destination is inside a Git worktree")


def _inventory(source, role):
    """Read-only inventory of source files, not a database-consistency proof.

    Detect additions, removals and metadata changes across WP-CLI export/copy.
    """
    files = tuple(
        (member, info.st_dev, info.st_ino, info.st_size,
         info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)
        for _, member, info in _files(source, role)
    )
    # Empty directories matter too: a file-only inventory cannot detect a
    # missing directory or a same-name replacement during SQL export/replay.
    return (_directory_inventory(source, role), files)


def _copy_component(source, destination, role):
    entries = _files(source, role)
    directories = _directory_inventory(source, role)
    destination.mkdir(mode=0o700)
    # Recreate every source directory, including empty nested directories,
    # before copying files. The packer can only archive directories that
    # survive this private staging copy.
    for _, member, device, inode in directories:
        relative = member.split("/", 1)[1] if "/" in member else ""
        original = source / relative
        info = original.lstat()
        if (not stat.S_ISDIR(info.st_mode) or original.is_symlink()
                or (info.st_dev, info.st_ino) != (device, inode)):
            raise ValueError("WordPress component directory changed before capture")
        if relative:
            (destination / relative).mkdir(parents=True, exist_ok=True, mode=0o700)
    for path, member, expected in entries:
        relative = member.split("/", 1)[1]
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as reader:
            current = os.fstat(reader.fileno())
            # A same-size rewrite with restored mtime must not silently
            # enter a private rollback copy. Mirror the archive pack guard.
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns,
                                  s.st_ctime_ns, s.st_nlink)
            if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1 or identity(current) != identity(expected):
                raise ValueError("WordPress component changed before capture")
            source_digest = hashlib.sha256()
            with target.open("xb") as writer:
                while True:
                    block = reader.read(CHUNK)
                    if not block:
                        break
                    source_digest.update(block)
                    writer.write(block)
                writer.flush()
                os.fsync(writer.fileno())
            after = os.fstat(reader.fileno())
            if identity(after) != identity(current):
                raise ValueError("WordPress component changed during capture")
            # A successful write is not proof that the private copy matches
            # the source. Detect truncated writes or same-size corruption
            # BEFORE the copy is packaged as a valid rollback archive.
            with os.fdopen(os.open(target, flags), "rb") as check:
                copied_before = os.fstat(check.fileno())
                if (not stat.S_ISREG(copied_before.st_mode)
                        or copied_before.st_nlink != 1
                        or copied_before.st_size != current.st_size):
                    raise ValueError("Copied WordPress component differs from source")
                copied_digest = hashlib.sha256()
                for block in iter(lambda: check.read(CHUNK), b""):
                    copied_digest.update(block)
                if (identity(os.fstat(check.fileno())) != identity(copied_before)
                        or copied_digest.digest() != source_digest.digest()):
                    raise ValueError("Copied WordPress component differs from source")
            target.chmod(0o600)
    if _directory_inventory(source, role) != directories:
        raise ValueError("WordPress component directories changed during capture")


def _bootstrap_fingerprint(path):
    """Check bootstrap bytes and identity without following a swapped symlink.

    WordPress configuration may contain secrets; only a digest is retained in
    memory. Matching file size/mtime alone is not a sufficient drift check.
    """
    before = _regular(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        current = os.fstat(source.fileno())
        identity = lambda info: (
            info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_nlink
        )
        if not stat.S_ISREG(current.st_mode) or identity(current) != identity(before):
            raise ValueError("WordPress bootstrap changed before fingerprint")
        digest = hashlib.sha256()
        for block in iter(lambda: source.read(CHUNK), b""):
            digest.update(block)
        if identity(os.fstat(source.fileno())) != identity(before):
            raise ValueError("WordPress bootstrap changed while fingerprinting")
    return identity(before), digest.hexdigest()


def _wp(wp_executable, root, args, env):
    try:
        process = subprocess.run(
            [str(wp_executable), "--path=" + str(root), *args],
            capture_output=True, text=True, timeout=180, check=False, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("WP-CLI unavailable or timed out") from exc
    if process.returncode != 0:
        # WP-CLI diagnostics can include secrets; never echo stdout/stderr.
        raise ValueError("WP-CLI gate/export failed (diagnostics suppressed)")
    return process.stdout


def capture(wp_root, backup_parent, backup_name, host, version, exact_sha, *, wp_executable="wp"):
    if not isinstance(host, str) or not HOST.fullmatch(host):
        raise ValueError("Only isolated EZ2 .local hostnames are allowed")
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError("Exact Elementor version required")
    if not isinstance(exact_sha, str) or not SHA.fullmatch(exact_sha):
        raise ValueError("Exact 40-character source SHA required")
    if not isinstance(backup_name, str) or not NAME.fullmatch(backup_name):
        raise ValueError("Unsafe private backup name")
    root = _real_directory(wp_root)
    parent = _real_directory(backup_parent)
    if _inside(root, parent) or _inside(parent, root):
        raise ValueError("Private backup parent must be outside WordPress root")
    _private_parent_outside_git(parent)
    destination = parent / backup_name
    if destination.exists() or destination.is_symlink():
        raise ValueError("Backup destination already exists")
    # Never follow linked WordPress bootstrap files or administration roots.
    # A linked entrypoint can redirect WP-CLI outside the authorised site.
    try:
        bootstrap_before = {
            name: _bootstrap_fingerprint(root / name)
            for name in ("wp-load.php", "wp-config.php")
        }
        _real_directory(root / "wp-admin")
    except (ValueError, OSError) as exc:
        raise ValueError("Expected regular WordPress bootstrap files not found") from exc
    content = _real_directory(root / "wp-content")
    components = {
        "uploads": _real_directory(content / "uploads"),
        "plugins": _real_directory(content / "plugins"),
        "theme": _real_directory(content / "themes"),
    }
    if any(not _inside(path, content) for path in components.values()):
        raise ValueError("WordPress component outside content root")
    gate_file = Path(__file__).with_name("ez2_wp_delivery_runtime_gate.php")
    if not gate_file.is_file():
        raise ValueError("Pinned runtime gate missing")
    env = dict(os.environ)
    env.update(EZ2_EXPECTED_HOST=host, EZ2_EXPECTED_ELEMENTOR_VERSION=version,
               EZ2_EXPECTED_RELEASE_SHA=exact_sha, EZ2_DELIVERY_MODE="upgrade")
    gate = json.loads(_wp(wp_executable, root, ["eval-file", str(gate_file)], env))
    if (not isinstance(gate, dict)
            or gate.get("status") != "READY_FOR_BACKUP_REHEARSAL_ONLY"
            or gate.get("target_site") != "ez2-isolated-only"
            or gate.get("expected_release_sha") != exact_sha
            or gate.get("delivery_mode") != "upgrade"
            or gate.get("issues") != []
            or gate.get("can_apply") is not False
            or gate.get("site_modified") is not False
            or gate.get("deployment_authorized") is not False):
        raise ValueError("Isolated EZ2 runtime identity gate rejected capture")
    # Observe all component files before exporting SQL. A second inventory
    # after the post-capture runtime gate prevents silent file-set drift.
    initial_inventory = {role: _inventory(source, role)
                         for role, source in components.items()}
    # All writes remain in a private directory outside the WordPress root.
    with tempfile.TemporaryDirectory(prefix="ez2-capture-", dir=parent) as scratch:
        staged = Path(scratch) / "snapshot"
        staged.mkdir(mode=0o700)
        # InnoDB tables must be exported from one transactional read view,
        # without blocking the isolated test site with table locks. WP-CLI
        # forwards these documented mysqldump flags. Non-transactional tables
        # and simultaneous file changes are NOT covered by this guarantee.
        # If the local mysqldump cannot honour the flags, fail closed.
        _wp(wp_executable, root, ["db", "export", str(staged / "database.sql"),
                                    "--add-drop-table", "--single-transaction",
                                    "--quick", "--skip-lock-tables",
                                    "--skip-plugins", "--skip-themes"], env)
        sql = staged / "database.sql"
        # WP-CLI output is untrusted until its file type, link count and
        # bounded size are checked. Never package a linked SQL export.
        try:
            _regular(sql)
        except (ValueError, OSError) as exc:
            raise ValueError("WP-CLI SQL export missing or unsafe") from exc
        for role, source in components.items():
            _copy_component(source, staged / role, role)
        # Recheck config and runtime identity after WP-CLI export and file copy.
        if any(_bootstrap_fingerprint(root / name) != fingerprint
               for name, fingerprint in bootstrap_before.items()):
            raise ValueError("WordPress bootstrap files changed during capture")
        _real_directory(root / "wp-admin")
        post_gate = json.loads(_wp(wp_executable, root, ["eval-file", str(gate_file)], env))
        if post_gate != gate:
            raise ValueError("WordPress runtime identity changed during capture")
        if any(_inventory(source, role) != initial_inventory[role]
               for role, source in components.items()):
            raise ValueError("WordPress source file inventory changed during capture")
        result = pack(staged, destination, exact_sha)
        try:
            replay_result = replay(destination, exact_sha)
            if replay_result["status"] != "SCRATCH_FILE_REPLAY_VERIFIED_ONLY":
                raise ValueError("Private backup scratch replay failed")
            # Packaging and scratch replay can take time. A live WordPress site
            # may change after the pre-pack inventory, leaving a stale rollback.
            # Recheck the source *after* packaging and remove the new archive
            # on drift; this is still not a database consistency guarantee.
            if any(_bootstrap_fingerprint(root / name) != fingerprint
                   for name, fingerprint in bootstrap_before.items()):
                raise ValueError("WordPress bootstrap files changed after archive packaging")
            _real_directory(root / "wp-admin")
            final_gate = json.loads(_wp(wp_executable, root,
                                      ["eval-file", str(gate_file)], env))
            if final_gate != gate:
                raise ValueError("WordPress runtime identity changed after archive packaging")
            if any(_inventory(source, role) != initial_inventory[role]
                   for role, source in components.items()):
                raise ValueError("WordPress source file inventory changed after archive packaging")
        except BaseException:
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            raise
    return {
        "status": "EZ2_PRIVATE_CAPTURE_ARCHIVED_AND_SCRATCH_FILE_REPLAYED_ONLY",
        "source_sha": exact_sha,
        "target_site": "ez2-isolated-only",
        "backup_created": result["byte_integrity_verified"],
        "database_export_generated": True,
        "file_replay_verified": True,
        "source_file_inventory_stable": True,
        "database_restore_rehearsed": False,
        "consistent_snapshot_verified": False,
        "wordpress_files_modified": False,
        "site_identity_gate_passed": True,
        "deployment_authorized": False,
        "one_click_complete": False,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 7:
            raise ValueError("Usage: ez2_wp_snapshot_capture.py WP_ROOT PRIVATE_PARENT NEW_BACKUP_NAME EZ2_HOST ELEMENTOR_VERSION EXACT_SHA")
        print(json.dumps(capture(*sys.argv[1:]), sort_keys=True))
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("EZ2_PRIVATE_CAPTURE_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
