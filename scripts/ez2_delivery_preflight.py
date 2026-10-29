#!/usr/bin/env python3
"""Read-only EZ2 A-scheme delivery contract validation and conflict planning.

This does not install WordPress plugins, import Elementor, resolve private media,
write to LocalWP, or grant publication authority. No private media bytes belong in
this public-repository contract.
"""
import json
import re
import sys
from pathlib import Path

from ez2_backup_preflight import checked_read, regular_file, _identity
from ez2_content_guard import plan as content_plan
from ez2_elementor_export_check import check as check_elementor, unique, reject_nonfinite
from ez2_plugin_dependency_check import check as check_plugins

COMMIT = re.compile(r"[0-9a-f]{40}\Z")
KEY = re.compile(r"ez2-[a-z0-9-]{1,80}\Z")
SLOT = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")
FILE = re.compile(r"[a-z0-9][a-z0-9_-]{0,70}\.json\Z")
# Windows reserves device names even with a .json extension. Linux CI can
# create these files, but an Owner Windows LocalWP VM cannot safely use them.
WINDOWS_DEVICE_JSON = re.compile(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])\.json\Z")


def safe_json_filename(value):
    return (isinstance(value, str) and FILE.fullmatch(value) is not None
            and WINDOWS_DEVICE_JSON.fullmatch(value) is None)


def load(root, filename, limit, pinned=None):
    if not safe_json_filename(filename):
        raise ValueError("Unsafe JSON filename")
    # Bind the JSON bytes to a verified regular-file descriptor. A plain
    # lstat() followed by read_text() can follow a replacement symlink or
    # silently consume another file after the initial validation.
    info, _, raw = checked_read(root / filename, max_bytes=limit, collect=True)
    if pinned is not None:
        pinned[filename] = _identity(info)
    return json.loads(raw.decode("utf-8"),
                      object_pairs_hook=unique, parse_constant=reject_nonfinite)


def check(contract, installed, plugin_doc, exports, expected_sha):
    if not isinstance(contract, dict) or set(contract) != {
        "schema_version", "target_site", "source_sha", "plugin_lock", "templates", "media_slots"
    } or type(contract["schema_version"]) is not int or contract["schema_version"] != 1:
        raise ValueError("Invalid delivery contract")
    if contract["target_site"] != "ez2-isolated-only":
        raise ValueError("Target site must be isolated EZ2; existing sites prohibited")
    if (not isinstance(expected_sha, str) or not COMMIT.fullmatch(expected_sha)
            or contract["source_sha"] != expected_sha):
        raise ValueError("Exact source SHA mismatch")
    if not safe_json_filename(contract["plugin_lock"]):
        raise ValueError("Unsafe plugin lock path")
    plugins = check_plugins(plugin_doc)
    # A syntactically valid Elementor export is not necessarily compatible with
    # the pinned runtime plugin. Fail closed before proposing any content write.
    pinned_versions = {item["slug"]: item["version"] for item in plugin_doc["plugins"]}
    elementor_version = pinned_versions.get("elementor")
    if elementor_version is None:
        raise ValueError("Elementor Free dependency is required")
    templates = contract["templates"]
    if not isinstance(templates, list) or not 1 <= len(templates) <= 20:
        raise ValueError("Invalid template count")
    approved_slots = contract["media_slots"]
    if (not isinstance(approved_slots, list) or len(approved_slots) > 100
            or any(not isinstance(s, str) or not SLOT.fullmatch(s) for s in approved_slots)
            or len(set(approved_slots)) != len(approved_slots)):
        raise ValueError("Invalid media-slot registry")
    desired = {"schema_version": 1, "items": []}
    used_slots, keys, paths = set(), set(), set()
    summaries = []
    for entry in templates:
        if not isinstance(entry, dict) or set(entry) != {"key", "file", "previous_sha256"}:
            raise ValueError("Invalid template declaration")
        key, filename = entry["key"], entry["file"]
        if (not isinstance(key, str) or not KEY.fullmatch(key) or key in keys
                or not safe_json_filename(filename)
                or filename in paths or filename == contract["plugin_lock"]):
            raise ValueError("Duplicate or unsafe template key/path")
        keys.add(key)
        paths.add(filename)
        if filename not in exports:
            raise ValueError("Missing validated Elementor export")
        exported = exports[filename]
        summary = check_elementor(exported)
        if exported["version"] != elementor_version:
            raise ValueError("Elementor template version differs from pinned plugin")
        used_slots.update(summary["media_slots"])
        summaries.append({"key": key, "nodes": summary["nodes"],
                          "media_slots": summary["media_slots"]})
        desired["items"].append({"key": key, "payload": exported,
                                 "previous_sha256": entry["previous_sha256"]})
    content = content_plan(desired, installed)
    unresolved = sorted(used_slots - set(approved_slots))
    unused = sorted(set(approved_slots) - used_slots)
    blocked = bool(content["conflict_count"] or unresolved or plugins["missing_checksums"])
    return {
        "status": "BLOCKED_PREFLIGHT" if blocked else "READY_FOR_RUNTIME_TEST_ONLY",
        "mode": "read-only", "source_sha": expected_sha,
        "target_site": "ez2-isolated-only", "applied": False,
        "installed": False, "localwp_verified": False,
        "deployment_authorized": False,
        "plugin_status": plugins["status"],
        "missing_plugin_checksums": plugins["missing_checksums"],
        "content": content, "templates": summaries,
        "unresolved_media_slots": unresolved, "unused_media_slots": unused,
        "media_bytes_included": False,
    }


def run(root, expected_sha):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Unsafe contract directory")
    root_identity = _identity(root.lstat())
    pinned = {}
    contract = load(root, "delivery.json", 32768, pinned)
    if not isinstance(contract, dict):
        raise ValueError("Invalid contract")
    lock = contract.get("plugin_lock")
    if not safe_json_filename(lock):
        raise ValueError("Invalid plugin lock filename")
    plugin_doc = load(root, lock, 32768, pinned)
    installed = load(root, "installed.json", 32768, pinned)
    templates = contract.get("templates")
    if not isinstance(templates, list) or len(templates) > 20:
        raise ValueError("Invalid templates")
    exports = {}
    declared = {"delivery.json", "installed.json", lock}
    for entry in templates:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise ValueError("Invalid template file")
        name = entry["file"]
        declared.add(name)
        exports[name] = load(root, name, 256000, pinned)
    # The delivery contract is a closed inventory. Never silently accept
    # undeclared private files, nested folders, or extra deployment inputs.
    if {entry.name for entry in root.iterdir()} != declared:
        raise ValueError("Unexpected or missing delivery contract entries")
    result = check(contract, installed, plugin_doc, exports, expected_sha)
    # A valid conflict plan must describe the SAME files that were parsed.
    # Re-check the complete inventory after validation, including same-byte
    # replacements and additions that occur while the plan is computed.
    if (root.is_symlink() or not root.is_dir()
            or _identity(root.lstat()) != root_identity
            or {entry.name for entry in root.iterdir()} != declared
            or any(_identity(regular_file(root / name)) != identity
                   for name, identity in pinned.items())):
        raise ValueError("Delivery contract inputs changed during preflight")
    return result


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("Usage: ez2_delivery_preflight.py DIRECTORY EXPECTED_EXACT_SHA")
        result = run(sys.argv[1], sys.argv[2])
        print(json.dumps(result, sort_keys=True))
        sys.exit(2 if result["status"] == "BLOCKED_PREFLIGHT" else 0)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print("EZ2_DELIVERY_PREFLIGHT_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
