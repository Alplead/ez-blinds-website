#!/usr/bin/env python3
"""Read-only linkage of an installed EZ2 backup and a candidate delivery plan.

A backup and optional first-party byte-parity proof belong to the *installed*\nsource SHA, not the incoming candidate SHA.
Passing this gate is NOT permission to install: isolated WordPress/Elementor
runtime checks, real site identity, Owner approval and a real database restore
rehearsal remain separate mandatory gates. File replay occurs only inside an
auto-deleted private scratch directory; no WordPress site is touched. No WordPress credentials or private files are emitted.
"""
import json
import re
import sys
from pathlib import Path

COMMIT = re.compile(r"[0-9a-f]{40}\Z")


def evaluate(contract_dir, backup_dir, installed_sha, candidate_sha,
             installed_release_dir=None, wp_content_dir=None):
    if (not isinstance(installed_sha, str) or not COMMIT.fullmatch(installed_sha)
            or not isinstance(candidate_sha, str) or not COMMIT.fullmatch(candidate_sha)):
        raise ValueError("Both installed and candidate SHAs must be exact lowercase commits")
    if installed_sha == candidate_sha:
        raise ValueError("No version change: refusing to mislabel a no-op as an upgrade")
    contract_dir = Path(contract_dir)
    backup_dir = Path(backup_dir)
    if contract_dir.resolve() == backup_dir.resolve():
        raise ValueError("Backup and delivery contract directories must be separate")

    # Optional strict baseline path: compare actual first-party bytes against the
    # *installed* release, not the incoming candidate. This is still read-only;
    # byte parity cannot attest site identity or prove a prior installation.
    if (installed_release_dir is None) != (wp_content_dir is None):
        raise ValueError("Installed release and wp-content must be supplied together")
    parity_verified = False
    parity_files = 0
    if installed_release_dir is not None:
        from ez2_installed_code_parity import check as check_parity
        parity = check_parity(installed_release_dir, installed_sha, wp_content_dir)
        if (not isinstance(parity, dict)
                or parity.get("status") != "CODE_BYTES_MATCH_RELEASE_ONLY"
                or parity.get("source_sha") != installed_sha
                or parity.get("theme_core_byte_parity") is not True
                or type(parity.get("mismatch_count")) is not int
                or parity["mismatch_count"] != 0
                or type(parity.get("checked_release_files")) is not int
                or parity["checked_release_files"] < 1):
            raise ValueError("Installed code does not match the claimed baseline")
        for flag in ("site_identity_verified", "installed_source_attested",
                     "wordpress_runtime_verified", "third_party_plugins_verified",
                     "elementor_content_verified", "private_media_verified",
                     "localwp_installed", "deployment_authorized", "applied",
                     "one_click_complete"):
            if parity.get(flag) is not False:
                raise ValueError("Unsafe installed parity claim: " + flag)
        parity_verified = True
        parity_files = parity["checked_release_files"]

    # The scratch helper verifies archive bytes/paths, replays only file components
    # into a disposable private directory, and deletes it before returning.
    # The SQL dump is inspected but never executed.
    from ez2_backup_scratch_replay import replay
    from ez2_delivery_preflight import run

    scratch = replay(backup_dir, installed_sha)
    if (scratch["status"] != "SCRATCH_FILE_REPLAY_VERIFIED_ONLY"
            or scratch["source_sha"] != installed_sha
            or scratch["target_site"] != "ez2-isolated-only"
            or scratch["scratch_deleted"] is not True
            or type(scratch["replayed_files"]) is not int or scratch["replayed_files"] < 1
            or type(scratch["replayed_bytes"]) is not int or scratch["replayed_bytes"] < 1
            or any(scratch[key] is not False for key in (
                "database_sql_executed", "wordpress_restored", "restore_rehearsed",
                "localwp_touched", "deployment_authorized", "applied"))):
        raise ValueError("Backup scratch file replay did not pass safely")
    delivery = run(contract_dir, candidate_sha)
    # Upstream preflight must describe this exact candidate and remain strictly
    # read-only. Never accept a fabricated or stale READY response.
    if delivery.get("source_sha") != candidate_sha:
        raise ValueError("Delivery preflight source SHA mismatch")
    if delivery.get("mode") != "read-only":
        raise ValueError("Delivery preflight was not read-only")
    for field in ("installed", "localwp_verified", "deployment_authorized",
                  "media_bytes_included"):
        if delivery.get(field) is not False:
            raise ValueError("Unsafe delivery preflight claim: " + field)
    if delivery["target_site"] != "ez2-isolated-only" or delivery["applied"] is not False:
        raise ValueError("Delivery preflight returned an unsafe site or applied state")
    if delivery["status"] not in ("BLOCKED_PREFLIGHT", "READY_FOR_RUNTIME_TEST_ONLY"):
        raise ValueError("Unexpected delivery preflight result")
    for field in ("unresolved_media_slots", "missing_plugin_checksums"):
        if not isinstance(delivery.get(field), list) or any(
                not isinstance(value, str) or not value for value in delivery[field]):
            raise ValueError("Malformed delivery preflight blockers: " + field)
        if delivery[field] != sorted(set(delivery[field])):
            raise ValueError("Duplicate or unordered delivery preflight blockers: " + field)
    content = delivery.get("content")
    if not isinstance(content, dict) or type(content.get("conflict_count")) is not int \
            or content["conflict_count"] < 0:
        raise ValueError("Malformed delivery preflight content conflicts")
    # Nested reports must remain read-only and internally consistent. A
    # fabricated READY summary cannot override conflicting content evidence.
    if (content.get("mode") != "dry-run-only" or content.get("applied") is not False
            or content.get("deployment_authorized") is not False
            or type(content.get("unmanaged_existing_count")) is not int
            or content["unmanaged_existing_count"] < 0):
        raise ValueError("Unsafe nested content preflight")
    unmanaged = content.get("unmanaged_existing_keys")
    if (not isinstance(unmanaged, list)
            or len(unmanaged) != content["unmanaged_existing_count"]
            or any(not isinstance(key, str) or not re.fullmatch(
                r"ez2-[a-z0-9-]{1,80}", key) for key in unmanaged)
            or unmanaged != sorted(set(unmanaged))):
        raise ValueError("Malformed or inconsistent unmanaged Owner content keys")
    actions = content.get("actions")
    if not isinstance(actions, list) or len(actions) > 100:
        raise ValueError("Malformed content action list")
    keys, conflict_actions = set(), 0
    for action in actions:
        if not isinstance(action, dict) or set(action) != {
                "key", "action", "desired_sha256"}:
            raise ValueError("Malformed content action")
        key, state, digest = action["key"], action["action"], action["desired_sha256"]
        if (not isinstance(key, str) or not re.fullmatch(r"ez2-[a-z0-9-]{1,80}", key)
                or key in keys or state not in (
                    "create", "update", "unchanged", "conflict_missing",
                    "conflict_owner_edit")
                or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("Invalid or duplicate content action")
        keys.add(key)
        conflict_actions += state.startswith("conflict")
    if keys.intersection(unmanaged):
        raise ValueError("Unmanaged Owner content overlaps managed actions")
    if conflict_actions != content["conflict_count"]:
        raise ValueError("Content conflict count disagrees with actions")
    plugin_status = delivery.get("plugin_status")
    if (plugin_status not in ("PENDING_CHECKSUM", "METADATA_ONLY")
            or (plugin_status == "PENDING_CHECKSUM") !=
            bool(delivery["missing_plugin_checksums"])):
        raise ValueError("Plugin preflight status contradicts checksums")
    has_blockers = bool(delivery["unresolved_media_slots"] or
                        delivery["missing_plugin_checksums"] or content["conflict_count"])
    if (delivery["status"] == "BLOCKED_PREFLIGHT") != has_blockers:
        raise ValueError("Delivery preflight status contradicts its blockers")

    return {
        "status": ("BLOCKED_DELIVERY_PREFLIGHT" if delivery["status"] == "BLOCKED_PREFLIGHT"
                   else "PREFLIGHT_PASS_RUNTIME_GATED"),
        "installed_source_sha": installed_sha,
        "installed_code_byte_parity_verified": parity_verified,
        "installed_code_checked_files": parity_files,
        "installed_site_baseline_attested": False,
        "candidate_source_sha": candidate_sha,
        "target_site": "ez2-isolated-only",
        "backup_bytes_verified": True,
        "backup_archive_structure_verified": True,
        "scratch_file_replay_verified": True,
        "scratch_deleted": True,
        "scratch_replayed_files": scratch["replayed_files"],
        "scratch_replayed_bytes": scratch["replayed_bytes"],
        "database_sql_executed": False,
        "wordpress_restored": False,
        "delivery_status": delivery["status"],
        "unresolved_media_slots": delivery["unresolved_media_slots"],
        "missing_plugin_checksums": delivery["missing_plugin_checksums"],
        "content_conflicts": delivery["content"]["conflict_count"],
        "unmanaged_existing_keys": unmanaged,
        "site_identity_verified": False,
        "wordpress_runtime_verified": False,
        "elementor_free_visual_verified": False,
        "restore_rehearsed": False,
        "deployment_authorized": False,
        "applied": False,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) not in (5, 7):
            raise ValueError("Usage: ez2_upgrade_gate.py CONTRACT_DIR BACKUP_DIR INSTALLED_SHA CANDIDATE_SHA [INSTALLED_RELEASE_DIR WP_CONTENT_DIR]")
        result = evaluate(*sys.argv[1:])
        print(json.dumps(result, sort_keys=True))
        sys.exit(2 if result["status"] == "BLOCKED_DELIVERY_PREFLIGHT" else 0)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("EZ2_UPGRADE_GATE_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
