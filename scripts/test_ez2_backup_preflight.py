"""Synthetic, no-network regression tests for read-only EZ2 backup verification."""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ez2_backup_preflight import ROLES, verify

SHA = "a" * 40
cases = 0


def fixture(root):
    files = {}
    for role, name in ROLES.items():
        data = ("synthetic " + role + "\n").encode()
        (root / name).write_bytes(data)
        files[role] = {"name": name, "sha256": hashlib.sha256(data).hexdigest(),
                       "size_bytes": len(data)}
    manifest = {"schema_version": 1, "target_site": "ez2-isolated-only",
                "source_sha": SHA, "files": files}
    save(root, manifest)
    return manifest


def save(root, doc):
    (root / "backup-manifest.json").write_text(json.dumps(doc), encoding="utf-8")


def reject(mutator):
    global cases
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "backup"
        root.mkdir()
        manifest = fixture(root)
        mutator(root, manifest)
        try:
            verify(root, SHA)
        except (OSError, ValueError, TypeError):
            cases += 1
            return
        raise AssertionError("Unsafe backup was accepted")


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    fixture(root)
    result = verify(root, SHA)
    assert result["status"] == "BACKUP_BYTES_VERIFIED_ONLY"
    assert result["verified_components"] == sorted(ROLES)
    assert not result["restore_rehearsed"] and not result["deployment_authorized"]
    assert not result["site_identity_verified"] and not result["applied"]
    cases += 1
    cmd = [sys.executable, str(Path(__file__).with_name("ez2_backup_preflight.py")),
           str(root), SHA]
    run = subprocess.run(cmd, capture_output=True, text=True)
    assert run.returncode == 0 and json.loads(run.stdout)["verified_bytes"] > 0
    cases += 1
    assert subprocess.run(cmd[:-1] + ["not-a-sha"], capture_output=True).returncode == 1
    cases += 1

reject(lambda root, m: (m.update(target_site="ez-bns-new-dev.local"), save(root, m)))
reject(lambda root, m: (m.update(target_site="ezbns.com.au"), save(root, m)))
reject(lambda root, m: (m.update(source_sha="b" * 40), save(root, m)))
reject(lambda root, m: (m.update(schema_version=True), save(root, m)))
reject(lambda root, m: (m.update(unapproved=True), save(root, m)))
reject(lambda root, m: (m["files"].pop("database"), save(root, m)))
reject(lambda root, m: (m["files"].update(extra={}), save(root, m)))
reject(lambda root, m: (m["files"]["uploads"].update(name="../uploads.tar.gz"), save(root, m)))
reject(lambda root, m: (m["files"]["database"].update(sha256="f" * 64), save(root, m)))
reject(lambda root, m: (m["files"]["plugins"].update(size_bytes=0), save(root, m)))
reject(lambda root, m: (m["files"]["theme"].update(size_bytes=True), save(root, m)))
reject(lambda root, m: (m["files"]["uploads"].update(size_bytes=12345), save(root, m)))
reject(lambda root, m: (root / ROLES["theme"]).write_bytes(b"changed"))
reject(lambda root, m: (root / ROLES["database"]).unlink())
reject(lambda root, m: (root / "undeclared.txt").write_text("synthetic"))
reject(lambda root, m: (root / "undeclared-directory").mkdir())

def external_hardlink_component(root, m):
    os.link(root / ROLES["uploads"], root.parent / "outside-component")
reject(external_hardlink_component)

def external_hardlink_manifest(root, m):
    os.link(root / "backup-manifest.json", root.parent / "outside-manifest")
reject(external_hardlink_manifest)

def symlink_component(root, m):
    (root / ROLES["database"]).unlink()
    (root / ROLES["database"]).symlink_to(root / ROLES["uploads"])
reject(symlink_component)

def hardlink_component(root, m):
    (root / ROLES["database"]).unlink()
    os.link(root / ROLES["uploads"], root / ROLES["database"])
    m["files"]["database"] = copy.deepcopy(m["files"]["uploads"])
    m["files"]["database"]["name"] = ROLES["database"]
    save(root, m)
reject(hardlink_component)

def symlink_manifest(root, m):
    (root / "backup-manifest.json").rename(root / "real-manifest.json")
    (root / "backup-manifest.json").symlink_to(root / "real-manifest.json")
reject(symlink_manifest)

def duplicate_keys(root, m):
    (root / "backup-manifest.json").write_text('{"schema_version":1,"schema_version":1}')
reject(duplicate_keys)

def nonfinite(root, m):
    (root / "backup-manifest.json").write_text('{"schema_version":NaN}')
reject(nonfinite)

assert cases == 26, cases
print(f"EZ2_BACKUP_PREFLIGHT_PASS cases={cases}")
