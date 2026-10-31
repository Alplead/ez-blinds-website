#!/usr/bin/env python3
"""Read-only conflict detection for future EZ2 managed Elementor content.

Never installs plugins, changes WordPress, or authorizes deployment. A trusted
installer must independently verify the prior-release baseline before use.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

from ez2_backup_preflight import checked_read, reject_constant

KEY = re.compile(r"ez2-[a-z0-9-]{1,80}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON key")
        obj[key] = value
    return obj


def read(path):
    """Read one immutable, single-link JSON input without following links.

    Binding the bytes to a verified descriptor prevents an attacker from
    replacing an Owner-content conflict input after the path check. Reject
    symlinked parent directories as well as symlinked files.
    """
    path = Path(path)
    if path.resolve(strict=True) != path.absolute():
        raise ValueError("Linked input file or ancestor")
    _, _, raw = checked_read(path, max_bytes=2_000_000, collect=True)
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=reject_constant)


def index(doc, kind):
    if not isinstance(doc, dict) or set(doc) != {"schema_version", "items"} or type(doc["schema_version"]) is not int or doc["schema_version"] != 1:
        raise ValueError("Invalid document schema")
    if not isinstance(doc["items"], list) or len(doc["items"]) > 100:
        raise ValueError("Invalid item count")
    found = {}
    for item in doc["items"]:
        fields = {"key", "payload", "previous_sha256"} if kind == "desired" else {"key", "current_sha256"}
        if not isinstance(item, dict) or set(item) != fields:
            raise ValueError("Invalid item schema")
        key = item["key"]
        if not isinstance(key, str) or not KEY.fullmatch(key) or key in found:
            raise ValueError("Invalid or duplicate managed key")
        if kind == "desired":
            if not isinstance(item["payload"], dict):
                raise ValueError("Invalid managed payload")
            digest(item["payload"])
            previous = item["previous_sha256"]
            if previous is not None and (not isinstance(previous, str) or not SHA.fullmatch(previous)):
                raise ValueError("Invalid baseline digest")
        elif not isinstance(item["current_sha256"], str) or not SHA.fullmatch(item["current_sha256"]):
            raise ValueError("Invalid installed digest")
        found[key] = item
    return found


def plan(desired, installed):
    want, have = index(desired, "desired"), index(installed, "installed")
    actions = []
    for key, item in sorted(want.items()):
        target = digest(item["payload"])
        previous = item["previous_sha256"]
        current = have.get(key, {}).get("current_sha256")
        if current is None:
            action = "create" if previous is None else "conflict_missing"
        elif current == target:
            action = "unchanged"
        elif previous is not None and current == previous:
            action = "update"
        else:
            action = "conflict_owner_edit"
        actions.append({"key": key, "action": action, "desired_sha256": target})
    count = sum(row["action"].startswith("conflict") for row in actions)
    # Surface Owner-managed records that the candidate release will leave intact.
    # Never silently delete or overwrite content omitted from the new template set.
    unmanaged = sorted(set(have) - set(want))
    return {"mode": "dry-run-only", "applied": False, "deployment_authorized": False,
            "conflict_count": count, "unmanaged_existing_count": len(unmanaged),
            "unmanaged_existing_keys": unmanaged, "actions": actions}


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("Usage: ez2_content_guard.py DESIRED_JSON INSTALLED_JSON")
        result = plan(read(sys.argv[1]), read(sys.argv[2]))
        print(json.dumps(result, sort_keys=True))
        sys.exit(2 if result["conflict_count"] else 0)
    except (ValueError, OSError, TypeError) as exc:
        print("EZ2_CONTENT_GUARD_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
