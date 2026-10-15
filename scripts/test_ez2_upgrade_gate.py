"""Synthetic no-network regression tests for the read-only EZ2 upgrade linkage."""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from ez2_upgrade_gate import evaluate

OLD = "a" * 40
NEW = "b" * 40
cases = 0


def good_backup():
    return {"status": "BACKUP_ARCHIVE_STRUCTURE_VERIFIED_ONLY",
            "target_site": "ez2-isolated-only", "byte_integrity_verified": True,
            "archive_contents_inspected": True}


def good_delivery():
    return {"status": "READY_FOR_RUNTIME_TEST_ONLY", "target_site": "ez2-isolated-only",
            "applied": False, "unresolved_media_slots": [], "missing_plugin_checksums": [],
            "content": {"conflict_count": 0}}


def invoke(backup=None, delivery=None, old=OLD, new=NEW):
    if backup is None:
        backup = good_backup()
    if delivery is None:
        delivery = good_delivery()
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp) / "contract", Path(tmp) / "backup"
        a.mkdir()
        b.mkdir()
        with patch("ez2_backup_archive_guard.inspect", return_value=backup) as inspect, \
             patch("ez2_delivery_preflight.run", return_value=delivery) as run:
            result = evaluate(a, b, old, new)
            inspect.assert_called_once_with(b, old)
            run.assert_called_once_with(a, new)
            return result


r = invoke()
assert r["status"] == "PREFLIGHT_PASS_RUNTIME_GATED"
assert r["installed_source_sha"] == OLD and r["candidate_source_sha"] == NEW
assert all(r[k] is False for k in ("site_identity_verified", "wordpress_runtime_verified",
        "elementor_free_visual_verified", "restore_rehearsed", "deployment_authorized", "applied"))
cases += 1

r = invoke(delivery={**good_delivery(), "status": "BLOCKED_PREFLIGHT",
                     "unresolved_media_slots": ["hero-one"], "missing_plugin_checksums": ["elementor"],
                     "content": {"conflict_count": 1}})
assert r["status"] == "BLOCKED_DELIVERY_PREFLIGHT"
assert r["unresolved_media_slots"] == ["hero-one"]
assert r["missing_plugin_checksums"] == ["elementor"] and r["content_conflicts"] == 1
cases += 1


def reject(backup=None, delivery=None, old=OLD, new=NEW, same_dir=False):
    global cases
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp) / "contract", Path(tmp) / "backup"
        a.mkdir()
        b.mkdir()
        with patch("ez2_backup_archive_guard.inspect", return_value=backup or good_backup()), \
             patch("ez2_delivery_preflight.run", return_value=delivery or good_delivery()):
            try:
                evaluate(a, a if same_dir else b, old, new)
            except (ValueError, TypeError, OSError):
                cases += 1
                return
            raise AssertionError("Unsafe upgrade linkage accepted")


reject(old="invalid")
reject(new="invalid")
reject(old="A" * 40)
reject(new="B" * 40)
reject(old=NEW, new=NEW)
reject(same_dir=True)
reject(backup={**good_backup(), "status": "UNKNOWN"})
reject(backup={**good_backup(), "byte_integrity_verified": False})
reject(backup={**good_backup(), "archive_contents_inspected": False})
reject(backup={**good_backup(), "target_site": "ezbns.com.au"})
reject(delivery={**good_delivery(), "target_site": "ez-bns-new-dev.local"})
reject(delivery={**good_delivery(), "applied": True})
reject(delivery={**good_delivery(), "status": "UNKNOWN"})

# Verify that a failing real preflight propagates rather than being interpreted as PASS.
with tempfile.TemporaryDirectory() as tmp:
    a, b = Path(tmp) / "contract", Path(tmp) / "backup"
    a.mkdir()
    b.mkdir()
    with patch("ez2_backup_archive_guard.inspect", side_effect=ValueError("tampered archive")):
        try:
            evaluate(a, b, OLD, NEW)
        except ValueError:
            cases += 1
        else:
            raise AssertionError("Tampered archive was not rejected")

assert cases == 16, cases
print(f"EZ2_UPGRADE_GATE_PASS cases={cases}")
