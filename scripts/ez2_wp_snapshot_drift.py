#!/usr/bin/env python3
"""Read-only drift check for isolated EZ2 managed WordPress digest inventories.

Neither observation attests an installed release or grants content write authority.
No private WordPress page data, media URLs or credentials are accepted or emitted.
"""
import re

KEY = re.compile(r"ez2-[a-z0-9-]{1,80}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
FIELDS = {"schema_version", "status", "mode", "target_site", "runtime_gate_passed",
          "managed_count", "entries", "private_content_emitted",
          "installed_release_attested", "localwp_verified",
          "owner_edit_baseline_trusted", "deployment_authorized", "applied"}
ENTRY = {"key", "post_id", "post_status", "content_sha256", "elementor_data_sha256"}
STATUSES = {"publish", "future", "draft", "pending", "private", "trash"}


def validate(snapshot):
    if not isinstance(snapshot, dict) or set(snapshot) != FIELDS:
        raise ValueError("Invalid managed snapshot schema")
    if (type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1
            or snapshot["mode"] != "read-only"
            or snapshot["target_site"] != "ez2-isolated-only"
            or snapshot["runtime_gate_passed"] is not True):
        raise ValueError("Snapshot not from isolated read-only runtime gate")
    for flag in ("private_content_emitted", "installed_release_attested",
                 "localwp_verified", "owner_edit_baseline_trusted",
                 "deployment_authorized", "applied"):
        if snapshot[flag] is not False:
            raise ValueError("Unsafe snapshot claim: " + flag)
    count, rows = snapshot["managed_count"], snapshot["entries"]
    if (type(count) is not int or not 0 <= count <= 100 or not isinstance(rows, list)
            or len(rows) != count or snapshot["status"] != (
                "MANAGED_CONTENT_DIGESTS_COLLECTED" if count else "NO_MANAGED_PAGES")):
        raise ValueError("Inconsistent snapshot count or status")
    found, ids = {}, set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != ENTRY:
            raise ValueError("Invalid managed entry")
        key, post_id = row["key"], row["post_id"]
        if (not isinstance(key, str) or not KEY.fullmatch(key) or key in found
                or type(post_id) is not int or post_id < 1 or post_id in ids
                or row["post_status"] not in STATUSES
                or any(not isinstance(row[field], str) or not SHA256.fullmatch(row[field])
                       for field in ("content_sha256", "elementor_data_sha256"))):
            raise ValueError("Malformed or duplicate managed entry")
        found[key] = row
        ids.add(post_id)
    if list(found) != sorted(found):
        raise ValueError("Managed entries must be sorted")
    return found


def compare(baseline, current):
    before, after = validate(baseline), validate(current)
    changes = []
    for key in sorted(before.keys() | after.keys()):
        a, b = before.get(key), after.get(key)
        if a is None:
            kind = "added_since_observation"
        elif b is None:
            kind = "missing_since_observation"
        elif a["post_id"] != b["post_id"]:
            kind = "managed_identity_changed"
        elif a["content_sha256"] != b["content_sha256"]:
            kind = ("elementor_and_page_changed"
                    if a["elementor_data_sha256"] != b["elementor_data_sha256"]
                    else "page_metadata_or_settings_changed")
        elif a["elementor_data_sha256"] != b["elementor_data_sha256"]:
            kind = "elementor_digest_inconsistent"
        elif a["post_status"] != b["post_status"]:
            kind = "post_status_inconsistent"
        else:
            continue
        changes.append({"key": key, "kind": kind})
    return {"status": "CONTENT_DRIFT_BLOCKED" if changes else "NO_CONTENT_DRIFT_UNTRUSTED_BASELINE",
            "target_site": "ez2-isolated-only", "mode": "read-only",
            "baseline_attested": False, "same_site_attested": False,
            "change_count": len(changes), "changes": changes,
            "private_content_emitted": False, "deployment_authorized": False,
            "can_apply": False, "applied": False}
