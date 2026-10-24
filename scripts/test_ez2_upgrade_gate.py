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
                        "unmanaged_existing_keys": [], "actions": [], "conflict_count": 0}}


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
assert r["unmanaged_existing_keys"] == []
assert r["installed_code_byte_parity_verified"] is False
assert r["installed_code_checked_files"] == 0
assert r["installed_site_baseline_attested"] is False
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

# The Owner's unmanaged records are disclosed without being changed or deleted.
r = invoke(delivery={**good_delivery(), "content": {
    **good_delivery()["content"], "unmanaged_existing_count": 1,
    "unmanaged_existing_keys": ["ez2-owner-note"]}})
assert r["unmanaged_existing_keys"] == ["ez2-owner-note"]
cases += 1
reject(delivery={**good_delivery(), "content": {
    **good_delivery()["content"], "unmanaged_existing_count": 1,
    "unmanaged_existing_keys": []}})
reject(delivery={**good_delivery(), "content": {
    **good_delivery()["content"], "unmanaged_existing_count": 2,
    "unmanaged_existing_keys": ["ez2-z", "ez2-a"]}})
reject(delivery={**good_delivery(), "content": {
    **good_delivery()["content"], "unmanaged_existing_count": 1,
    "unmanaged_existing_keys": ["ez2-home"], "actions": [
        {"key": "ez2-home", "action": "create", "desired_sha256": "c" * 64}]}})

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


# Strict read-only integration: installed release ZIP bytes must match the
# isolated fixture's wp-content before a candidate can reach the runtime gate.
def good_parity():
    return {"status": "CODE_BYTES_MATCH_RELEASE_ONLY", "source_sha": OLD,
            "theme_core_byte_parity": True, "mismatch_count": 0,
            "checked_release_files": 3,
            **{key: False for key in (
                "site_identity_verified", "installed_source_attested",
                "wordpress_runtime_verified", "third_party_plugins_verified",
                "elementor_content_verified", "private_media_verified",
                "localwp_installed", "deployment_authorized", "applied",
                "one_click_complete")}}


def strict(parity, should_reject=False):
    global cases
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a, b = root / "contract", root / "backup"
        release, content = root / "installed-release", root / "site" / "wp-content"
        for folder in (a, b, release, content):
            folder.mkdir(parents=True)
        with patch("ez2_installed_code_parity.check", return_value=parity) as parity_check, \
             patch("ez2_backup_scratch_replay.replay", return_value=good_backup()), \
             patch("ez2_delivery_preflight.run", return_value=good_delivery()):
            if should_reject:
                try:
                    evaluate(a, b, OLD, NEW, release, content)
                except (ValueError, TypeError):
                    cases += 1
                    return
                raise AssertionError("Unsafe installed baseline was accepted")
            result = evaluate(a, b, OLD, NEW, release, content)
            parity_check.assert_called_once_with(release, OLD, content)
            assert result["installed_code_byte_parity_verified"] is True
            assert result["installed_code_checked_files"] == 3
            assert result["installed_site_baseline_attested"] is False
            assert result["site_identity_verified"] is False
            assert result["deployment_authorized"] is False
            cases += 1


strict(good_parity())
strict({**good_parity(), "status": "BLOCKED_CODE_PARITY"}, True)
strict({**good_parity(), "source_sha": NEW}, True)
strict({**good_parity(), "mismatch_count": 1}, True)
strict({**good_parity(), "checked_release_files": 0}, True)
strict({**good_parity(), "theme_core_byte_parity": False}, True)
strict({**good_parity(), "localwp_installed": True}, True)
strict({**good_parity(), "deployment_authorized": True}, True)
strict({**good_parity(), "applied": True}, True)
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    a, b = root / "contract", root / "backup"
    a.mkdir()
    b.mkdir()
    try:
        evaluate(a, b, OLD, NEW, root / "release")
    except ValueError:
        cases += 1
    else:
        raise AssertionError("Partial parity input was accepted")

assert cases == 75, cases
print(f"EZ2_UPGRADE_GATE_PASS cases=57 additional=18 total={cases}")
