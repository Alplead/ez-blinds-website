#!/usr/bin/env python3
"""Compile preflighted Elementor JSON with local-only private media references.
OFFLINE ONLY: no WordPress writes, media upload, plugin installation or deployment.
Resolved JSON and private mapping must never enter the public Git repository.
"""
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit
from ez2_elementor_export_check import check as check_export, unique, reject_nonfinite

HOST = re.compile(r"ez2(?:-[a-z0-9]+)*\.local\Z")
SLOT = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")
SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,200}\Z")
MIME = {"image/webp": ".webp", "image/jpeg": ".jpg", "image/png": ".png"}
SCHEME = "ez2-media://"

def read_json(path, limit):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Missing, linked or oversized JSON input")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=reject_nonfinite)

def validate_media_map(mapping, expected_host):
    if not isinstance(mapping, dict) or set(mapping) != {"schema_version", "target_site", "host", "slots"}:
        raise ValueError("Invalid media map schema")
    if type(mapping["schema_version"]) is not int or mapping["schema_version"] != 1:
        raise ValueError("Invalid media map version")
    if mapping["target_site"] != "ez2-isolated-only":
        raise ValueError("Non-isolated media map target")
    if not isinstance(expected_host, str) or not HOST.fullmatch(expected_host) or mapping["host"] != expected_host:
        raise ValueError("Unsafe or mismatched isolated host")
    slots = mapping["slots"]
    if not isinstance(slots, dict) or not 1 <= len(slots) <= 100:
        raise ValueError("Invalid media map size")
    seen_ids, seen_urls = {}, {}
    for slot, media in slots.items():
        if not isinstance(slot, str) or not SLOT.fullmatch(slot):
            raise ValueError("Invalid media slot key")
        if not isinstance(media, dict) or set(media) != {"id", "url", "mime"}:
            raise ValueError("Invalid media record")
        if type(media["id"]) is not int or not 1 <= media["id"] <= 2**31 - 1:
            raise ValueError("Invalid attachment ID")
        mime, url = media["mime"], media["url"]
        if not isinstance(mime, str) or mime not in MIME or not isinstance(url, str):
            raise ValueError("Unapproved image MIME or URL")
        if any(ord(c) < 33 or ord(c) > 126 for c in url) or "\\" in url or "%" in url:
            raise ValueError("Unsafe URL encoding")
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise ValueError("Invalid image URL") from exc
        if (parsed.scheme not in ("http", "https") or parsed.netloc != expected_host
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            raise ValueError("Image URL outside isolated site")
        parts = parsed.path.split("/")
        if (len(parts) < 6 or len(parts) > 10 or parts[:3] != ["", "wp-content", "uploads"]
                or not all(SEGMENT.fullmatch(p) and p not in (".", "..") for p in parts[3:])
                or not parts[-1].lower().endswith(MIME[mime])):
            raise ValueError("Invalid local WordPress media path")
        previous_url = seen_ids.setdefault(media["id"], url)
        previous_id = seen_urls.setdefault(url, media["id"])
        if previous_url != url or previous_id != media["id"]:
            raise ValueError("Conflicting attachment ID and URL mapping")
    return slots

def compile_export(doc, mapping, expected_host):
    summary = check_export(doc)
    slots = validate_media_map(mapping, expected_host)
    used = set(summary["media_slots"])
    if used != set(slots):
        raise ValueError("Unresolved or extra private media slots")
    def walk(value):
        if isinstance(value, dict):
            out = {k: walk(v) for k, v in value.items()}
            if isinstance(value.get("url"), str) and value["url"].startswith(SCHEME):
                media = slots[value["url"][len(SCHEME):]]
                if "id" in value and value["id"] not in (None, "", 0, "0", media["id"]):
                    raise ValueError("Conflicting Elementor attachment ID")
                out["id"] = media["id"]
            return out
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, str) and value.startswith(SCHEME):
            return slots[value[len(SCHEME):]]["url"]
        return value
    compiled = walk(doc)
    if SCHEME in json.dumps(compiled, ensure_ascii=False, allow_nan=False):
        raise ValueError("Unresolved symbolic media URL")
    return compiled, {"status": "COMPILED_OFFLINE_ONLY", "media_slots_resolved": len(used),
                      "elementor_nodes": summary["nodes"], "wordpress_imported": False,
                      "plugin_installed": False, "site_modified": False,
                      "visual_qa_verified": False, "deployment_authorized": False}

def write_private(path, doc):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.parent.is_dir():
        raise ValueError("Output must be a new absolute path in an existing private directory")
    root = Path(__file__).resolve().parents[1]
    parent = path.parent.resolve(strict=True)
    if parent == root or root in parent.parents:
        raise ValueError("Refusing private output inside public repository")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(doc, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")

def main(argv):
    if len(argv) != 5:
        raise ValueError("Usage: ez2_elementor_media_compile.py EXPORT.json PRIVATE_MEDIA_MAP.json EXPECTED_EZ2_HOST ABSOLUTE_PRIVATE_OUTPUT.json")
    compiled, result = compile_export(read_json(argv[1], 256000), read_json(argv[2], 65536), argv[3])
    write_private(argv[4], compiled)
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    try:
        main(sys.argv)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("EZ2_MEDIA_COMPILE_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
