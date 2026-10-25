"""Synthetic isolated EZ2 backup packaging tests; no private media or live WP."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from ez2_backup_snapshot_pack import pack
from ez2_backup_preflight import verify
from ez2_backup_archive_guard import inspect
from ez2_backup_scratch_replay import replay

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

assert cases == 18, cases
print(f"EZ2_BACKUP_SNAPSHOT_PACK_PASS cases={cases} backup_created=true wordpress_touched=false")
