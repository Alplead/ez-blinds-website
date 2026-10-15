"""Synthetic scratch-only filesystem replay regressions; no private media."""
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch

from ez2_backup_preflight import ROLES
from ez2_backup_scratch_replay import replay

SHA = "a" * 40
cases = 0


def archive(path, role, entries=None):
    if entries is None:
        entries = [(role + "/file.txt", b"synthetic\n", "file")]
    with tarfile.open(path, "w:gz") as output:
        for name, data, kind in entries:
            item = tarfile.TarInfo(name)
            if kind == "dir":
                item.type = tarfile.DIRTYPE
                item.size = 0
            elif kind == "symlink":
                item.type = tarfile.SYMTYPE
                item.linkname = "../../outside"
            else:
                item.size = len(data)
            output.addfile(item, io.BytesIO(data) if kind == "file" else None)


def fixture(root):
    with gzip.open(root / ROLES["database"], "wb") as stream:
        stream.write(b"-- synthetic, never executed\n")
    for role in ("uploads", "plugins", "theme"):
        archive(root / ROLES[role], role)
    refresh_manifest(root)


def refresh_manifest(root):
    manifest = {"schema_version": 1, "target_site": "ez2-isolated-only", "source_sha": SHA,
                "files": {role: {"name": name,
                                 "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                                 "size_bytes": (root / name).stat().st_size}
                          for role, name in ROLES.items()}}
    (root / "backup-manifest.json").write_text(json.dumps(manifest))


def reject(change, update_manifest=True):
    global cases
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        fixture(root)
        change(root)
        if update_manifest:
            refresh_manifest(root)
        try:
            replay(root, SHA)
        except (ValueError, OSError, TypeError, KeyError):
            cases += 1
            return
        raise AssertionError("Unsafe backup replay succeeded")


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    fixture(root)
    result = replay(root, SHA)
    assert result["status"] == "SCRATCH_FILE_REPLAY_VERIFIED_ONLY"
    assert result["replayed_files"] == 3 and result["replayed_bytes"] == 30
    assert result["scratch_deleted"] and not any(result[k] for k in (
        "database_sql_executed", "wordpress_restored", "restore_rehearsed",
        "localwp_touched", "deployment_authorized", "applied"))
    cases += 1
    archive(root / ROLES["uploads"], "uploads", [
        ("uploads/", b"", "dir"),
        ("uploads/sub/", b"", "dir"),
        ("uploads/sub/photo.webp", b"image fixture", "file")])
    refresh_manifest(root)
    assert replay(root, SHA)["replayed_files"] == 3
    cases += 1
    cmd = [sys.executable, str(Path(__file__).with_name("ez2_backup_scratch_replay.py")), str(root), SHA]
    p = subprocess.run(cmd, capture_output=True, text=True)
    assert p.returncode == 0 and json.loads(p.stdout)["scratch_deleted"]
    cases += 1
    assert subprocess.run(cmd[:-1] + ["wrong"], capture_output=True).returncode == 1
    cases += 1
    with patch("ez2_backup_scratch_replay.MAX_SCRATCH_BYTES", 1):
        try:
            replay(root, SHA)
        except ValueError:
            cases += 1
        else:
            raise AssertionError("Replay accepted over-budget data")

reject(lambda r: (r / ROLES["database"]).write_bytes(b"bad"))
reject(lambda r: archive(r / ROLES["uploads"], "uploads", [("uploads/../escape", b"x", "file")]))
reject(lambda r: archive(r / ROLES["uploads"], "uploads", [("uploads/evil", b"", "symlink")]))
reject(lambda r: archive(r / ROLES["uploads"], "uploads", [("uploads/File", b"a", "file"), ("uploads/file", b"b", "file")]))
reject(lambda r: (r / ROLES["plugins"]).write_bytes(b"tampered"), update_manifest=False)
reject(lambda r: archive(r / ROLES["theme"], "theme", [("theme/file", b"a", "file"), ("theme/file/sub", b"b", "file")]))
reject(lambda r: archive(r / ROLES["uploads"], "uploads", [("plugins/file", b"x", "file")]))
reject(lambda r: (r / "backup-manifest.json").write_text(json.dumps({"bad": True})), update_manifest=False)

assert cases == 13, cases
print(f"EZ2_BACKUP_SCRATCH_REPLAY_PASS cases={cases}")
