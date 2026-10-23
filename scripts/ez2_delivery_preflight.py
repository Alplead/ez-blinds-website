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

from ez2_content_guard import plan as content_plan
from ez2_elementor_export_check import check as check_elementor, unique, reject_nonfinite
from ez2_plugin_dependency_check import check as check_plugins

COMMIT = re.compile(r"[0-9a-f]{40}\Z")
KEY = re.compile(r"ez2-[a-z0-9-]{1,80}\Z")
SLOT = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")
FILE = re.compile(r"[a-z0-9][a-z0-9_-]{0,70}\.json\Z")


def load(root, filename, limit):
    if not isinstance(filename, str) or not FILE.fullmatch(filename):
        raise ValueError("Unsafe JSON filename")
    path = root / filename
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Unsafe or oversized JSON file")
    return json.loads(path.read_text(encoding="utf-8"),
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
    if not isinstance(contract["plugin_lock"], str) or not FILE.fullmatch(contract["plugin_lock"]):
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
                or not isinstance(filename, str) or not FILE.fullmatch(filename)
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
    contract = load(root, "delivery.json", 32768)
    if not isinstance(contract, dict):
        raise ValueError("Invalid contract")
    lock = contract.get("plugin_lock")
    if not isinstance(lock, str) or not FILE.fullmatch(lock):
        raise ValueError("Invalid plugin lock filename")
    plugin_doc = load(root, lock, 32768)
    installed = load(root, "installed.json", 32768)
    templates = contract.get("templates")
    if not isinstance(templates, list) or len(templates) > 20:
        raise ValueError("Invalid templates")
    exports = {}
    for entry in templates:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise ValueError("Invalid template file")
        name = entry["file"]
        exports[name] = load(root, name, 256000)
    return check(contract, installed, plugin_doc, exports, expected_sha)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("Usage: ez2_delivery_preflight.py DIRECTORY EXPECTED_EXACT_SHA")
        result = run(sys.argv[1], sys.argv[2])
        print(json.dumps(result, sort_keys=True))
        sys.exit(2 if result["status"] == "BLOCKED_PREFLIGHT" else 0)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("EZ2_DELIVERY_PREFLIGHT_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
