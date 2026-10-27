"""Synthetic isolated EZ2 backup packaging tests; no private media or live WP."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import os
import gzip
import tarfile
from unittest.mock import patch

from ez2_backup_snapshot_pack import pack, _files, _write_tar, _write_sql
from ez2_backup_preflight import verify
from ez2_backup_archive_guard import inspect
from ez2_backup_scratch_replay import replay, _replay_archive

SHA = "a" * 40
cases = 0


def fixture(root):
    root.mkdir()
    (root / "database.sql").write_bytes(b"-- synthetic database only\nCREATE TABLE test (id INT);\n")
    for role in ("uploads", "plugins", "theme"):
        (root / role).mkdir()
        (root / role / "file.txt").write_bytes(("synthetic " + role + "\n").encode())


def reject(change):
    global cases
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        source = base / "snapshot"
        fixture(source)
        destination = base / "private-backup"
        change(source, destination)
        try:
            pack(source, destination, SHA)
        except (ValueError, OSError):
            assert not destination.exists() or (
                destination.is_dir() and not any(destination.iterdir())
            ), "Failure left an incomplete backup"
            cases += 1
            return
        raise AssertionError("Unsafe snapshot accepted")


with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    source = base / "snapshot"
    fixture(source)
    # Empty nested folders must survive a rollback archive and scratch replay.
    (source / "uploads" / "empty" / "nested").mkdir(parents=True)
    destination = base / "private-backup"
    result = pack(source, destination, SHA)
    assert result["status"] == "BACKUP_ARCHIVES_CREATED_AND_VERIFIED_ONLY"
    assert not any(result[key] for key in (
        "database_dump_generated", "sql_executed", "restore_rehearsed",
        "wordpress_touched", "deployment_authorized",
    ))
    assert verify(destination, SHA)["status"] == "BACKUP_BYTES_VERIFIED_ONLY"
    assert inspect(destination, SHA)["status"] == "BACKUP_ARCHIVE_STRUCTURE_VERIFIED_ONLY"
    assert replay(destination, SHA)["status"] == "SCRATCH_FILE_REPLAY_VERIFIED_ONLY"
    with tarfile.open(destination / "uploads.tar.gz", "r:gz") as archive:
        names = set(archive.getnames())
        assert {"uploads/empty", "uploads/empty/nested"} <= {
            name.rstrip("/") for name in names
        }, "Empty directories missing from backup"
    with tempfile.TemporaryDirectory() as scratch:
        replayed, _ = _replay_archive(
            destination / "uploads.tar.gz", "uploads", Path(scratch),
            {"files": 50000, "bytes": 1024 * 1024})
        assert replayed == 1
        assert (Path(scratch) / "uploads" / "empty" / "nested").is_dir()
    assert (source / "database.sql").exists()
    assert all((source / role / "file.txt").exists()
               for role in ("uploads", "plugins", "theme"))
    cases += 1
    try:
        pack(source, destination, SHA)
    except ValueError:
        cases += 1
    else:
        raise AssertionError("Existing backup overwritten")
    command = [
        sys.executable, str(Path(__file__).with_name("ez2_backup_snapshot_pack.py")),
        str(source), str(base / "cli-backup"), SHA,
    ]
    process = subprocess.run(command, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["byte_integrity_verified"]
    cases += 1

reject(lambda src, dst: (src / "uploads" / "file.txt").unlink())
reject(lambda src, dst: (
    (src / "uploads" / "file.txt").unlink(),
    (src / "uploads" / "file.txt").symlink_to(src / "database.sql"),
))
reject(lambda src, dst: (src / "plugins" / "file.txt").write_bytes(b""))
reject(lambda src, dst: (src / "theme" / "bad?.txt").write_bytes(b"x"))
reject(lambda src, dst: (src / "uploads" / "FILE.txt").write_bytes(b"x"))
reject(lambda src, dst: (src / "uploads" / "nested").symlink_to(
    src / "theme", target_is_directory=True))
reject(lambda src, dst: (src / "wp-config.php").write_bytes(b"not live"))
reject(lambda src, dst: (src / "unapproved").write_bytes(b"x"))
reject(lambda src, dst: dst.mkdir())
reject(lambda src, dst: (
    (src / "theme" / "file.txt").unlink(),
    (src / "theme" / "file.txt").hardlink_to(src / "plugins" / "file.txt"),
))
reject(lambda src, dst: (src / "database.sql").write_bytes(b""))
reject(lambda src, dst: (src / "database.sql").unlink())
reject(lambda src, dst: (src / "uploads" / "bad|file").write_bytes(b"x"))
reject(lambda src, dst: (src / "uploads" / "bad\\path").write_bytes(b"x"))

with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    fixture(base / "source")
    (base / "source" / "uploads" / "sub").mkdir()
    (base / "source" / "uploads" / "sub" / "photo.webp").write_bytes(b"synthetic image")
    assert pack(base / "source", base / "backup", SHA)["byte_integrity_verified"]
    assert replay(base / "backup", SHA)["replayed_files"] == 4
    cases += 1

# Windows LocalWP must not merge distinct Linux source directories.
def collide_directories(src, dst):
    for folder, filename in (("Photos", "one.webp"), ("photos", "two.webp")):
        path = src / "uploads" / folder
        path.mkdir()
        (path / filename).write_bytes(b"synthetic image")


def collide_file_directory(src, dst):
    (src / "uploads" / "Gallery").write_bytes(b"synthetic file")
    directory = src / "uploads" / "gallery"
    directory.mkdir()
    (directory / "photo.webp").write_bytes(b"synthetic image")


reject(collide_directories)
reject(collide_file_directory)

# Normal checkout and linked-worktree markers both forbid private backups.
reject(lambda src, dst: (src.parent / ".git").mkdir())
reject(lambda src, dst: (src.parent / ".git").write_text("gitdir: elsewhere", encoding="utf-8"))

# A clean snapshot must not be written into a different Git checkout.
with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    fixture(base / "snapshot")
    checkout = base / "public-repo"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    destination = checkout / "private-backup"
    try:
        pack(base / "snapshot", destination, SHA)
    except ValueError:
        assert not destination.exists()
        cases += 1
    else:
        raise AssertionError("Backup inside Git checkout accepted")

# Insufficient disk space must fail before a backup directory is created.
with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    fixture(base / "snapshot")
    destination = base / "private-backup"
    with patch("ez2_backup_snapshot_pack.shutil.disk_usage",
               return_value=SimpleNamespace(free=1)):
        try:
            pack(base / "snapshot", destination, SHA)
        except ValueError:
            assert not destination.exists()
            cases += 1
        else:
            raise AssertionError("Low-space backup accepted")

# os.walk normally ignores unreadable nested directories. A backup must not
# succeed with missing private files, even if other files were packaged.
with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    source = base / "snapshot"
    fixture(source)
    restricted = source / "uploads" / "restricted"
    restricted.mkdir()
    (restricted / "hidden.webp").write_bytes(b"synthetic private image")
    destination = base / "private-backup"
    import os
    real_scandir = os.scandir

    def deny_nested_scan(path):
        if Path(path) == restricted:
            raise PermissionError("synthetic unreadable nested directory")
        return real_scandir(path)

    with patch("ez2_backup_snapshot_pack.os.scandir", side_effect=deny_nested_scan):
        try:
            pack(source, destination, SHA)
        except ValueError as exc:
            assert "enumerate complete snapshot" in str(exc)
            assert not destination.exists(), "Incomplete backup created"
            cases += 1
        else:
            raise AssertionError("Unreadable nested snapshot was silently accepted")


# A same-length rewrite with the original mtime restored must still fail.
# Otherwise a stale snapshot can be accepted after an in-place file change.
def rewrite_preserving_size_and_mtime(path):
    before = path.stat()
    original = path.read_bytes()
    assert original and original[0] != ord("X")
    path.write_bytes(b"X" + original[1:])
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    assert path.stat().st_mtime_ns == before.st_mtime_ns


with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    fixture(base / "snapshot")
    uploads = base / "snapshot" / "uploads"
    entries = _files(uploads, "uploads")
    rewrite_preserving_size_and_mtime(uploads / "file.txt")
    try:
        _write_tar(base / "stale.tar.gz", "uploads", entries)
    except ValueError as exc:
        assert "changed during packaging" in str(exc)
        cases += 1
    else:
        raise AssertionError("Same-size pre-packaging rewrite was accepted")

with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    fixture(base / "snapshot")
    uploads = base / "snapshot" / "uploads"
    entries = _files(uploads, "uploads")
    original_addfile = tarfile.TarFile.addfile

    def tamper_after_tar_read(archive, member, fileobj=None):
        result = original_addfile(archive, member, fileobj)
        rewrite_preserving_size_and_mtime(uploads / "file.txt")
        return result

    with patch("ez2_backup_snapshot_pack.tarfile.TarFile.addfile",
               new=tamper_after_tar_read):
        try:
            _write_tar(base / "changed.tar.gz", "uploads", entries)
        except ValueError as exc:
            assert "changed while reading" in str(exc)
            cases += 1
        else:
            raise AssertionError("Same-size mid-tar rewrite was accepted")

with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    fixture(base / "snapshot")
    sql = base / "snapshot" / "database.sql"
    original_write = gzip.GzipFile.write

    def tamper_after_sql_read(writer, data):
        result = original_write(writer, data)
        rewrite_preserving_size_and_mtime(sql)
        return result

    with patch("ez2_backup_snapshot_pack.gzip.GzipFile.write",
               new=tamper_after_sql_read):
        try:
            _write_sql(sql, base / "changed.sql.gz")
        except ValueError as exc:
            assert "changed while reading" in str(exc)
            cases += 1
        else:
            raise AssertionError("Same-size mid-SQL rewrite was accepted")

# Packaging must reject a snapshot that changes *after* individual files
# have been read. Otherwise a valid-looking archive can omit newly added files.
from ez2_backup_snapshot_pack import _write_tar as real_write_tar
from ez2_backup_snapshot_pack import _write_sql as real_write_sql

with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    source = base / "snapshot"
    fixture(source)
    destination = base / "backup"

    def add_late_file(archive_path, role, entries):
        result = real_write_tar(archive_path, role, entries)
        if role == "uploads":
            (source / "uploads" / "late.webp").write_bytes(b"synthetic late photo")
        return result

    with patch("ez2_backup_snapshot_pack._write_tar", side_effect=add_late_file):
        try:
            pack(source, destination, SHA)
        except ValueError as exc:
            assert "inventory changed after packaging" in str(exc)
            assert not destination.exists(), "Stale archive was not cleaned up"
            cases += 1
        else:
            raise AssertionError("New file added after archiving was accepted")

with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    source = base / "snapshot"
    fixture(source)
    destination = base / "backup"

    def remove_late_file(archive_path, role, entries):
        result = real_write_tar(archive_path, role, entries)
        if role == "theme":
            (source / "theme" / "file.txt").unlink()
        return result

    with patch("ez2_backup_snapshot_pack._write_tar", side_effect=remove_late_file):
        try:
            pack(source, destination, SHA)
        except ValueError as exc:
            assert "inventory changed after packaging" in str(exc)
            assert not destination.exists(), "Stale archive was not cleaned up"
            cases += 1
        else:
            raise AssertionError("File removed after archiving was accepted")

with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    source = base / "snapshot"
    fixture(source)
    destination = base / "backup"

    def change_sql_after_compression(sql_path, archive_path):
        result = real_write_sql(sql_path, archive_path)
        rewrite_preserving_size_and_mtime(sql_path)
        return result

    with patch("ez2_backup_snapshot_pack._write_sql", side_effect=change_sql_after_compression):
        try:
            pack(source, destination, SHA)
        except ValueError as exc:
            assert "SQL changed after packaging" in str(exc)
            assert not destination.exists(), "Stale archive was not cleaned up"
            cases += 1
        else:
            raise AssertionError("SQL changed after compression was accepted")

# Empty directories are not archived by the current file-only packer, but
# additions, removals and same-name replacements during capture must not
# silently pass as a stable source snapshot.
def check_late_directory_drift(change):
    global cases
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        source = base / "snapshot"
        fixture(source)
        empty = source / "uploads" / "empty"
        empty.mkdir()
        destination = base / "backup"

        def mutate_after_archive(archive_path, role, entries):
            result = real_write_tar(archive_path, role, entries)
            if role == "theme":
                change(empty)
            return result

        with patch("ez2_backup_snapshot_pack._write_tar",
                   side_effect=mutate_after_archive):
            try:
                pack(source, destination, SHA)
            except ValueError as exc:
                assert "directory inventory changed" in str(exc), str(exc)
                assert not destination.exists(), "Unstable backup was not cleaned up"
                cases += 1
            else:
                raise AssertionError("Late directory drift was accepted")


def replace_empty_directory(path):
    path.rename(path.with_name("old-empty"))
    path.mkdir()


check_late_directory_drift(lambda path: (path / "new-empty").mkdir())
check_late_directory_drift(lambda path: path.rmdir())
check_late_directory_drift(replace_empty_directory)

assert cases == 34, cases
print(f"EZ2_BACKUP_SNAPSHOT_PACK_PASS cases={cases} backup_created=true wordpress_touched=false")
