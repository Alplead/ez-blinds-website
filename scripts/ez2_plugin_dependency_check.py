#!/usr/bin/env python3
"""Read-only third-party plugin lock preflight for future isolated EZ2 site.

Does not fetch, install, activate, or verify official plugin provenance.
"""
import json
import re
import sys
from pathlib import Path

VERSION = re.compile(r"[1-9][0-9]{0,2}\.[0-9]{1,3}\.[0-9]{1,3}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
APPROVED_EVALUATION = {"elementor": "elementor/elementor.php"}


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("Non-finite JSON value")


def read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        raise ValueError("Unsafe manifest file")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=reject_constant)


def check(doc):
    if (not isinstance(doc, dict) or set(doc) != {"schema_version", "target_site", "plugins"}
            or type(doc["schema_version"]) is not int or doc["schema_version"] != 1
            or doc["target_site"] != "ez2-isolated-only"):
        raise ValueError("Invalid dependency manifest schema or target")
    plugins = doc["plugins"]
    if not isinstance(plugins, list) or not 1 <= len(plugins) <= 8:
        raise ValueError("Invalid plugin count")
    seen = set()
    missing = []
    listed = []
    for plugin in plugins:
        if not isinstance(plugin, dict) or set(plugin) != {
            "slug", "version", "entrypoint", "source", "archive_sha256", "activate"
        }:
            raise ValueError("Unexpected plugin fields")
        slug = plugin["slug"]
        if not isinstance(slug, str) or slug not in APPROVED_EVALUATION or slug in seen:
            raise ValueError("Duplicate or unapproved plugin")
        seen.add(slug)
        version = plugin["version"]
        if not isinstance(version, str) or not VERSION.fullmatch(version):
            raise ValueError("Exact numeric version required")
        if (plugin["entrypoint"] != APPROVED_EVALUATION[slug]
                or plugin["source"] != "wordpress.org"
                or plugin["activate"] is not True):
            raise ValueError("Unapproved source, entrypoint or activation")
        checksum = plugin["archive_sha256"]
        if checksum is None:
            missing.append(slug)
        elif (not isinstance(checksum, str) or not DIGEST.fullmatch(checksum)
              or checksum == "0" * 64):
            raise ValueError("Invalid archive SHA256")
        listed.append({"slug": slug, "version": version,
                       "checksum_recorded": checksum is not None})
    return {"status": "PENDING_CHECKSUM" if missing else "METADATA_ONLY",
            "plugins": listed, "missing_checksums": missing,
            "downloaded": False, "provenance_verified": False,
            "runtime_verified": False, "installed": False,
            "deployment_authorized": False}


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("Usage: ez2_plugin_dependency_check.py MANIFEST.json")
        result = check(read(sys.argv[1]))
        print(json.dumps(result, sort_keys=True))
        sys.exit(2 if result["missing_checksums"] else 0)
    except (OSError, ValueError, TypeError) as exc:
        print("EZ2_PLUGIN_DEPENDENCY_PREFLIGHT_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
