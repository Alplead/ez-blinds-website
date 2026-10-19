#!/usr/bin/env python3
"""Read-only linkage of an installed EZ2 backup and a candidate delivery plan.

A backup belongs to the *installed* source SHA, not the incoming candidate SHA.
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


def evaluate(contract_dir, backup_dir, installed_sha, candidate_sha):
    if (not isinstance(installed_sha, str) or not COMMIT.fullmatch(installed_sha)
            or not isinstance(candidate_sha, str) or not COMMIT.fullmatch(candidate_sha)):
        raise ValueError("Both installed and candidate SHAs must be exact lowercase commits")
    if installed_sha == candidate_sha:
        raise ValueError("No version change: refusing to mislabel a no-op as an upgrade")
    contract_dir = Path(contract_dir)
    backup_dir = Path(backup_dir)
    if contract_dir.resolve() == backup_dir.resolve():
        raise ValueError("Backup and delivery contract directories must be separate")

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
    content = delivery.get("content")
    if not isinstance(content, dict) or type(content.get("conflict_count")) is not int \
            or content["conflict_count"] < 0:
        raise ValueError("Malformed delivery preflight content conflicts")
    has_blockers = bool(delivery["unresolved_media_slots"] or
                        delivery["missing_plugin_checksums"] or content["conflict_count"])
    if (delivery["status"] == "BLOCKED_PREFLIGHT") != has_blockers:
        raise ValueError("Delivery preflight status contradicts its blockers")

    return {
        "status": ("BLOCKED_DELIVERY_PREFLIGHT" if delivery["status"] == "BLOCKED_PREFLIGHT"
                   else "PREFLIGHT_PASS_RUNTIME_GATED"),
        "installed_source_sha": installed_sha,
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
        "site_identity_verified": False,
        "wordpress_runtime_verified": False,
        "elementor_free_visual_verified": False,
        "restore_rehearsed": False,
        "deployment_authorized": False,
        "applied": False,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 5:
            raise ValueError("Usage: ez2_upgrade_gate.py CONTRACT_DIR BACKUP_DIR INSTALLED_SHA CANDIDATE_SHA")
        result = evaluate(*sys.argv[1:])
        print(json.dumps(result, sort_keys=True))
        sys.exit(2 if result["status"] == "BLOCKED_DELIVERY_PREFLIGHT" else 0)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("EZ2_UPGRADE_GATE_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
