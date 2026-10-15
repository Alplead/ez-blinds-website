#!/usr/bin/env python3
"""Read-only linkage of an installed EZ2 backup and a candidate delivery plan.

A backup belongs to the *installed* source SHA, not the incoming candidate SHA.
Passing this gate is NOT permission to install: isolated WordPress/Elementor
runtime checks, real site identity, Owner approval and a rehearsed restore remain
separate mandatory gates. No WordPress credentials or private files are emitted.
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

    # Imported only after identity checks, and both helpers are strictly read-only.
    from ez2_backup_archive_guard import inspect
    from ez2_delivery_preflight import run

    backup = inspect(backup_dir, installed_sha)
    if (backup["status"] != "BACKUP_ARCHIVE_STRUCTURE_VERIFIED_ONLY"
            or not backup["byte_integrity_verified"]
            or not backup["archive_contents_inspected"]
            or backup["target_site"] != "ez2-isolated-only"):
        raise ValueError("Backup preflight did not verify bytes and archive structure")
    delivery = run(contract_dir, candidate_sha)
    if delivery["target_site"] != "ez2-isolated-only" or delivery["applied"]:
        raise ValueError("Delivery preflight returned an unsafe site or applied state")
    if delivery["status"] not in ("BLOCKED_PREFLIGHT", "READY_FOR_RUNTIME_TEST_ONLY"):
        raise ValueError("Unexpected delivery preflight result")

    return {
        "status": ("BLOCKED_DELIVERY_PREFLIGHT" if delivery["status"] == "BLOCKED_PREFLIGHT"
                   else "PREFLIGHT_PASS_RUNTIME_GATED"),
        "installed_source_sha": installed_sha,
        "candidate_source_sha": candidate_sha,
        "target_site": "ez2-isolated-only",
        "backup_bytes_verified": True,
        "backup_archive_structure_verified": True,
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
