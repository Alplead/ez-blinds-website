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
    return {"status": "SCRATCH_FILE_REPLAY_VERIFIED_ONLY",
            "source_sha": OLD, "target_site": "ez2-isolated-only",
            "scratch_deleted": True, "replayed_files": 3, "replayed_bytes": 30,
            "database_sql_executed": False, "wordpress_restored": False,
            "restore_rehearsed": False, "localwp_touched": False,
            "deployment_authorized": False, "applied": False}


def good_delivery():
    return {"status": "READY_FOR_RUNTIME_TEST_ONLY", "target_site": "ez2-isolated-only",
            "source_sha": NEW, "mode": "read-only", "installed": False,
            "localwp_verified": False, "deployment_authorized": False,
            "media_bytes_included": False, "applied": False,
            "unresolved_media_slots": [], "missing_plugin_checksums": [],
            "plugin_status": "METADATA_ONLY",
            "content": {"mode": "dry-run-only", "applied": False,
                        "deployment_authorized": False, "unmanaged_existing_count": 0,
                        "actions": [], "conflict_count": 0}}


def invoke(backup=None, delivery=None, old=OLD, new=NEW):
    if backup is None:
        backup = good_backup()
    if delivery is None:
        delivery = good_delivery()
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp) / "contract", Path(tmp) / "backup"
        a.mkdir()
        b.mkdir()
        with patch("ez2_backup_scratch_replay.replay", return_value=backup) as replay, \
             patch("ez2_delivery_preflight.run", return_value=delivery) as run:
            result = evaluate(a, b, old, new)
            replay.assert_called_once_with(b, old)
            run.assert_called_once_with(a, new)
            return result


r = invoke()
assert r["status"] == "PREFLIGHT_PASS_RUNTIME_GATED"
assert r["installed_source_sha"] == OLD and r["candidate_source_sha"] == NEW
assert r["scratch_file_replay_verified"] and r["scratch_deleted"]
assert r["scratch_replayed_files"] == 3 and r["scratch_replayed_bytes"] == 30
assert r["database_sql_executed"] is False and r["wordpress_restored"] is False
assert all(r[k] is False for k in ("site_identity_verified", "wordpress_runtime_verified",
        "elementor_free_visual_verified", "restore_rehearsed", "deployment_authorized", "applied"))
cases += 1

r = invoke(delivery={**good_delivery(), "status": "BLOCKED_PREFLIGHT",
                     "unresolved_media_slots": ["hero-one"], "missing_plugin_checksums": ["elementor"],
                     "plugin_status": "PENDING_CHECKSUM",
                     "content": {**good_delivery()["content"], "conflict_count": 1,
                                 "actions": [{"key": "ez2-home", "action": "conflict_owner_edit",
                                              "desired_sha256": "c" * 64}]}})
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
        with patch("ez2_backup_scratch_replay.replay", return_value=backup or good_backup()), \
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
reject(backup={**good_backup(), "source_sha": NEW})
reject(backup={**good_backup(), "scratch_deleted": False})
reject(backup={**good_backup(), "replayed_files": 0})
reject(backup={**good_backup(), "replayed_files": True})
reject(backup={**good_backup(), "replayed_bytes": 0})
reject(backup={**good_backup(), "database_sql_executed": True})
reject(backup={**good_backup(), "wordpress_restored": True})
reject(backup={**good_backup(), "restore_rehearsed": True})
reject(backup={**good_backup(), "localwp_touched": True})
reject(backup={**good_backup(), "deployment_authorized": True})
reject(backup={**good_backup(), "applied": True})
reject(backup={**good_backup(), "target_site": "ezbns.com.au"})
reject(delivery={**good_delivery(), "target_site": "ez-bns-new-dev.local"})
reject(delivery={**good_delivery(), "applied": True})
reject(delivery={**good_delivery(), "status": "UNKNOWN"})
reject(delivery={**good_delivery(), "unresolved_media_slots": ["hero-one"]})
reject(delivery={**good_delivery(), "missing_plugin_checksums": ["elementor"]})
reject(delivery={**good_delivery(), "content": {"conflict_count": 1}})
reject(delivery={**good_delivery(), "status": "BLOCKED_PREFLIGHT"})
reject(delivery={**good_delivery(), "applied": 0})
reject(delivery={**good_delivery(), "unresolved_media_slots": "hero-one"})
reject(delivery={**good_delivery(), "content": {"conflict_count": -1}})
reject(delivery={**good_delivery(), "content": {"conflict_count": True}})
reject(delivery={**good_delivery(), "content": None})
reject(delivery={**good_delivery(), "source_sha": OLD})
reject(delivery={**good_delivery(), "source_sha": None})
reject(delivery={**good_delivery(), "mode": "write"})
reject(delivery={**good_delivery(), "installed": True})
reject(delivery={**good_delivery(), "localwp_verified": True})
reject(delivery={**good_delivery(), "deployment_authorized": True})
reject(delivery={**good_delivery(), "media_bytes_included": True})

# Reject nested preflight claims, malformed managed actions and plugin status lies.
reject(delivery={**good_delivery(), "content": {**good_delivery()["content"], "mode": "write"}})
reject(delivery={**good_delivery(), "content": {**good_delivery()["content"], "applied": True}})
reject(delivery={**good_delivery(), "content": {**good_delivery()["content"], "deployment_authorized": True}})
reject(delivery={**good_delivery(), "content": {**good_delivery()["content"], "unmanaged_existing_count": -1}})
reject(delivery={**good_delivery(), "content": {**good_delivery()["content"], "unmanaged_existing_count": True}})
reject(delivery={**good_delivery(), "content": {**good_delivery()["content"], "unmanaged_existing_count": "0"}})
reject(delivery={**good_delivery(), "content": {**good_delivery()["content"], "actions": "bad"}})
reject(delivery={**good_delivery(), "content": {**good_delivery()["content"], "actions": [
    {"key": "ez2-home", "action": "create", "desired_sha256": "bad"}]}})
reject(delivery={**good_delivery(), "content": {**good_delivery()["content"], "actions": [
    {"key": "ez2-home", "action": "conflict_owner_edit", "desired_sha256": "c" * 64}]}})
reject(delivery={**good_delivery(), "content": {**good_delivery()["content"], "actions": [
    {"key": "ez2-home", "action": "create", "desired_sha256": "c" * 64},
    {"key": "ez2-home", "action": "create", "desired_sha256": "c" * 64}]}})
reject(delivery={**good_delivery(), "content": {**good_delivery()["content"], "actions": [
    {"key": "bad", "action": "create", "desired_sha256": "c" * 64}]}})
reject(delivery={**good_delivery(), "content": {**good_delivery()["content"], "actions": [
    {"key": "ez2-home", "action": "delete", "desired_sha256": "c" * 64}]}})
reject(delivery={**good_delivery(), "content": {**good_delivery()["content"], "actions": [
    {"key": "ez2-home", "action": "create", "desired_sha256": "c" * 64, "extra": True}]}})
reject(delivery={**good_delivery(), "plugin_status": "UNKNOWN"})
reject(delivery={**good_delivery(), "plugin_status": "PENDING_CHECKSUM"})
reject(delivery={**good_delivery(), "missing_plugin_checksums": ["elementor"]})

# Blocker lists are canonical, sorted and unique; conflicting reports fail closed.
reject(delivery={**good_delivery(), "status": "BLOCKED_PREFLIGHT",
                 "unresolved_media_slots": ["hero-two", "hero-one"]})
reject(delivery={**good_delivery(), "status": "BLOCKED_PREFLIGHT",
                 "unresolved_media_slots": ["hero-one", "hero-one"]})
reject(delivery={**good_delivery(), "status": "BLOCKED_PREFLIGHT",
                 "missing_plugin_checksums": ["elementor", "elementor"],
                 "plugin_status": "PENDING_CHECKSUM"})
reject(delivery={**good_delivery(), "status": "BLOCKED_PREFLIGHT",
                 "missing_plugin_checksums": ["z-plugin", "a-plugin"],
                 "plugin_status": "PENDING_CHECKSUM"})

# Verify that a failing real preflight propagates rather than being interpreted as PASS.
with tempfile.TemporaryDirectory() as tmp:
    a, b = Path(tmp) / "contract", Path(tmp) / "backup"
    a.mkdir()
    b.mkdir()
    with patch("ez2_backup_scratch_replay.replay", side_effect=ValueError("tampered archive")):
        try:
            evaluate(a, b, OLD, NEW)
        except ValueError:
            cases += 1
        else:
            raise AssertionError("Tampered archive was not rejected")

assert cases == 61, cases
print(f"EZ2_UPGRADE_GATE_PASS cases={cases}")
