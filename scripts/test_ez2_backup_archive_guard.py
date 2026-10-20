"""Synthetic no-network, no-extraction EZ2 backup archive structure tests."""
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from ez2_backup_archive_guard import inspect
from ez2_backup_preflight import ROLES

SHA = "a" * 40
cases = 0


def archive(path, role, entries=None):
    if entries is None:
        entries = [(role + "/file.txt", b"synthetic\n", "file")]
    with tarfile.open(path, "w:gz") as out:
        for name, data, kind in entries:
            item = tarfile.TarInfo(name)
            if kind == "dir":
                item.type = tarfile.DIRTYPE
                item.size = 0
            elif kind == "link":
                item.type = tarfile.SYMTYPE
                item.linkname = "../../escape"
            else:
                item.size = len(data)
            out.addfile(item, io.BytesIO(data) if kind == "file" else None)


def fixture(root):
    with gzip.open(root / ROLES["database"], "wb") as stream:
        stream.write(b"-- synthetic SQL only\n")
    for role in ("uploads", "plugins", "theme"):
        archive(root / ROLES[role], role)
    manifest = {"schema_version": 1, "target_site": "ez2-isolated-only", "source_sha": SHA,
                "files": {role: {"name": name,
                                 "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                                 "size_bytes": (root / name).stat().st_size}
                          for role, name in ROLES.items()}}
    (root / "backup-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def fixture_manifest_only(root):
    manifest = json.loads((root / "backup-manifest.json").read_text())
    for role, name in ROLES.items():
        content = (root / name).read_bytes()
        manifest["files"][role]["sha256"] = hashlib.sha256(content).hexdigest()
        manifest["files"][role]["size_bytes"] = len(content)
    (root / "backup-manifest.json").write_text(json.dumps(manifest))


def reject(change):
    global cases
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fixture(root)
        change(root)
        fixture_manifest_only(root)
        try:
            inspect(root, SHA)
        except (OSError, ValueError, TypeError):
            cases += 1
            return
        raise AssertionError("Unsafe archive accepted")


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    fixture(root)
    result = inspect(root, SHA)
    assert result["status"] == "BACKUP_ARCHIVE_STRUCTURE_VERIFIED_ONLY"
    assert result["archive_contents_inspected"] and result["byte_integrity_verified"]
    assert not any(result[key] for key in ("extracted", "sql_executed", "restore_rehearsed",
                                         "site_identity_verified", "deployment_authorized", "applied"))
    assert all(result["components"][r]["files"] == 1 for r in ("uploads", "plugins", "theme"))
    archive(root / ROLES["uploads"], "uploads",
            [("uploads/", b"", "dir"), ("uploads/photo.webp", b"test", "file")])
    fixture_manifest_only(root)
    assert inspect(root, SHA)["components"]["uploads"]["members"] == 2
    cases += 1
    cmd = [sys.executable, str(Path(__file__).with_name("ez2_backup_archive_guard.py")),
           str(root), SHA]
    run = subprocess.run(cmd, capture_output=True, text=True)
    assert run.returncode == 0 and json.loads(run.stdout)["archive_contents_inspected"]
    cases += 1
    assert subprocess.run(cmd[:-1] + ["wrong"], capture_output=True).returncode == 1
    cases += 1

reject(lambda r: archive(r / ROLES["uploads"], "uploads", [("uploads/../escape", b"x", "file")]))
reject(lambda r: archive(r / ROLES["uploads"], "uploads", [("/uploads/absolute", b"x", "file")]))
reject(lambda r: archive(r / ROLES["uploads"], "uploads", [("plugins/other", b"x", "file")]))
reject(lambda r: archive(r / ROLES["plugins"], "plugins", [("plugins/link", b"", "link")]))
reject(lambda r: archive(r / ROLES["theme"], "theme", [("theme/file", b"", "dir")]))
reject(lambda r: archive(r / ROLES["theme"], "theme",
                         [("theme/file", b"a", "file"), ("theme/FILE", b"b", "file")]))
reject(lambda r: archive(r / ROLES["uploads"], "uploads", [("uploads/CON.txt", b"x", "file")]))
reject(lambda r: archive(r / ROLES["uploads"], "uploads", [("uploads/evil\\path", b"x", "file")]))
reject(lambda r: archive(r / ROLES["uploads"], "uploads", [("uploads/evil:name", b"x", "file")]))
reject(lambda r: archive(r / ROLES["uploads"], "uploads", [("uploads/trailing. ", b"x", "file")]))
reject(lambda r: archive(r / ROLES["theme"], "theme", []))
reject(lambda r: (r / ROLES["database"]).write_bytes(b"not a gzip file"))
reject(lambda r: (r / ROLES["database"]).write_bytes(gzip.compress(b"")))
reject(lambda r: (r / ROLES["plugins"]).write_bytes(b"not tar gzip"))
# Unicode-normalisation aliases must not overwrite one another on restore.
reject(lambda r: archive(r / ROLES["uploads"], "uploads", [
    ("uploads/caf\u00e9.txt", b"x", "file"), ("uploads/cafe\u0301.txt", b"y", "file")]))
reject(lambda r: archive(r / ROLES["uploads"], "uploads", [
    ("uploads/parent", b"x", "file"), ("uploads/parent/child", b"y", "file")]))
reject(lambda r: archive(r / ROLES["uploads"], "uploads", [
    ("uploads/Parent/child", b"x", "file"), ("uploads/parent", b"y", "file")]))
assert cases == 20, cases
print(f"EZ2_BACKUP_ARCHIVE_GUARD_PASS cases={cases}")
