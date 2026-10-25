"""No WordPress or private media: fake WP-CLI plus synthetic directory fixture."""
import json
import os
import tempfile
from pathlib import Path

from ez2_wp_snapshot_capture import capture

SHA = "a" * 40
HOST = "ez2-review.local"
VERSION = "4.3.5"
CASES = 0

FAKE_WP = '''#!/usr/bin/env python3
import json, os, pathlib, sys
mode = os.environ.get("FAKE_WP_MODE", "ok")
args = sys.argv[1:]
if "eval-file" in args:
    if mode == "gate_error": sys.exit(2)
    gate = {"status": "READY_FOR_BACKUP_REHEARSAL_ONLY",
            "target_site": "ez2-isolated-only",
            "expected_release_sha": os.environ["EZ2_EXPECTED_RELEASE_SHA"],
            "delivery_mode": "upgrade", "issues": [], "can_apply": False,
            "site_modified": False, "deployment_authorized": False}
    if mode == "gate_wrong_site": gate["target_site"] = "ez-bns-new-dev"
    if mode == "gate_wrong_sha": gate["expected_release_sha"] = "b" * 40
    if mode == "gate_apply": gate["can_apply"] = True
    if mode == "gate_missing_issues": del gate["issues"]
    print(json.dumps(gate))
elif "db" in args and "export" in args:
    if mode == "db_error": sys.exit(1)
    path = pathlib.Path(args[args.index("export") + 1])
    if mode == "empty_sql": path.write_bytes(b"")
    elif mode == "missing_sql": pass
    else: path.write_bytes(b"-- synthetic only\\nCREATE TABLE dummy(id INT);\\n")
else: sys.exit(3)
'''


def fixture(base):
    root = base / "wp"
    root.mkdir()
    (root / "wp-load.php").write_text("<?php // synthetic")
    (root / "wp-admin").mkdir()
    content = root / "wp-content"
    content.mkdir()
    for name in ("uploads", "plugins", "themes"):
        folder = content / name
        folder.mkdir()
        (folder / "synthetic.txt").write_text("test " + name)
    parent = base / "private"
    parent.mkdir()
    fake = base / "fake-wp"
    fake.write_text(FAKE_WP)
    fake.chmod(0o700)
    return root, parent, fake


def run(root, parent, fake, *, host=HOST, version=VERSION, sha=SHA,
        name="ez2-backup-test", mode="ok"):
    original = os.environ.get("FAKE_WP_MODE")
    os.environ["FAKE_WP_MODE"] = mode
    try:
        return capture(root, parent, name, host, version, sha, wp_executable=fake)
    finally:
        if original is None: os.environ.pop("FAKE_WP_MODE", None)
        else: os.environ["FAKE_WP_MODE"] = original


def reject(mutate=lambda root, parent, fake: None, **kwargs):
    global CASES
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        root, parent, fake = fixture(base)
        mutate(root, parent, fake)
        existed_before = (parent / "ez2-backup-test").exists()
        try:
            run(root, parent, fake, **kwargs)
        except (ValueError, OSError):
            assert (parent / "ez2-backup-test").exists() == existed_before, "Unsafe backup persisted"
            assert not any(x.name.startswith("ez2-capture-") for x in parent.iterdir()), "Staging leaked"
            CASES += 1
            return
        raise AssertionError("Unsafe WordPress capture accepted")


with tempfile.TemporaryDirectory() as temp:
    root, parent, fake = fixture(Path(temp))
    result = run(root, parent, fake)
    assert result["status"] == "EZ2_PRIVATE_CAPTURE_ARCHIVED_AND_SCRATCH_FILE_REPLAYED_ONLY"
    assert result["backup_created"] and result["file_replay_verified"]
    assert result["database_export_generated"] and not result["database_restore_rehearsed"]
    assert not result["consistent_snapshot_verified"] and not result["deployment_authorized"]
    assert (parent / "ez2-backup-test" / "backup-manifest.json").is_file()
    assert (root / "wp-content" / "uploads" / "synthetic.txt").exists()
    assert not any(x.name.startswith("ez2-capture-") for x in parent.iterdir())
    CASES += 1
    try: run(root, parent, fake)
    except ValueError: CASES += 1
    else: raise AssertionError("Existing backup overwritten")

for mode in ("gate_error", "gate_wrong_site", "gate_wrong_sha", "gate_apply",
             "gate_missing_issues", "db_error", "empty_sql", "missing_sql"):
    reject(mode=mode)
for host in ("ezbns.com.au", "t2-ez-blinds-shutters.local", "ez-bns-new-dev.local",
             "ez2.local.evil", "ez2.local:8080", "EZ2-review.local", ""):
    reject(host=host)
for version in ("", "latest", "4.3", "4.3.5-beta", "0.0.0"):
    reject(version=version)
for sha in ("", "A" * 40, "a" * 39, "g" * 40):
    reject(sha=sha)
for name in ("", "backup", "../ez2-backup-test", "ez2-backup-..", "ez2-backup-TEST"):
    reject(name=name)
reject(lambda root, parent, fake: (root / "wp-load.php").unlink())
reject(lambda root, parent, fake: (root / "wp-content" / "uploads" / "synthetic.txt").unlink())
reject(lambda root, parent, fake: (
    (root / "wp-content" / "plugins" / "synthetic.txt").unlink(),
    (root / "wp-content" / "plugins" / "synthetic.txt").symlink_to(root / "wp-load.php"),
))
reject(lambda root, parent, fake: (
    (root / "wp-content" / "themes").rename(root / "theme-old"),
    (root / "wp-content" / "themes").symlink_to(root / "theme-old", target_is_directory=True),
))
reject(lambda root, parent, fake: (parent / "ez2-backup-test").mkdir())
reject(lambda root, parent, fake: (root / "wp-content" / "uploads" / "bad?.txt").write_text("x"))
reject(lambda root, parent, fake: (root / "wp-content" / "plugins" / "nested").symlink_to(
    root / "wp-content" / "uploads", target_is_directory=True))

assert CASES == 1 + 1 + 8 + 7 + 5 + 4 + 5 + 7, CASES
print(f"EZ2_WP_PRIVATE_CAPTURE_GUARD_PASS cases={CASES} fake_wp_cli=true live_wp_touched=false")
