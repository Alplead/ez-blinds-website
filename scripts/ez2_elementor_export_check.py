#!/usr/bin/env python3
"""Read-only validation of controlled, public-safe EZ2 Elementor page exports.

This does not install Elementor or import content into WordPress.
"""
import json
import re
import sys
from pathlib import Path

ID = re.compile(r"[0-9a-f]{6,16}\Z")
SLOT = re.compile(r"ez2-media://[a-z0-9][a-z0-9-]{0,79}\Z")
ALLOWED = {"container", "section", "column", "widget"}
WIDGETS = {"heading", "text-editor", "image", "button", "divider", "spacer", "icon", "image-carousel"}

def unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON key")
        obj[key] = value
    return obj

def check(doc):
    if not isinstance(doc, dict) or set(doc) != {"title", "type", "version", "page_settings", "content"}:
        raise ValueError("Unexpected Elementor export fields")
    if doc["type"] != "page" or not isinstance(doc["title"], str) or not isinstance(doc["version"], str):
        raise ValueError("Unexpected Elementor page metadata")
    if not isinstance(doc["page_settings"], dict) or not isinstance(doc["content"], list) or not doc["content"]:
        raise ValueError("Missing Elementor page content")
    ids, slots = set(), set()
    count = 0

    def settings(value, depth=0):
        if depth > 12:
            raise ValueError("Settings nesting limit")
        if isinstance(value, dict):
            if len(value) > 80:
                raise ValueError("Settings count limit")
            for key, item in value.items():
                if not isinstance(key, str) or key.lower() in {"__dynamic__", "custom_html", "shortcode", "custom_css"}:
                    raise ValueError("Unsupported settings field")
                settings(item, depth + 1)
        elif isinstance(value, list):
            if len(value) > 100:
                raise ValueError("Settings list limit")
            for item in value:
                settings(item, depth + 1)
        elif isinstance(value, str):
            if len(value) > 6000:
                raise ValueError("Settings text limit")
            if value.startswith("ez2-media://"):
                if not SLOT.fullmatch(value):
                    raise ValueError("Invalid media slot")
                slots.add(value[len("ez2-media://"):])
            elif "://" in value or value.startswith("//"):
                raise ValueError("External references are not allowed")
        elif value is not None and type(value) not in (bool, int, float):
            raise ValueError("Unsupported settings type")

    def walk(node, depth=0):
        nonlocal count
        count += 1
        if count > 200 or depth > 12 or not isinstance(node, dict):
            raise ValueError("Node count/depth limit")
        if not {"id", "elType", "settings", "elements"}.issubset(node):
            raise ValueError("Missing Elementor node fields")
        if set(node) - {"id", "elType", "settings", "elements", "widgetType", "isInner"}:
            raise ValueError("Unexpected Elementor node fields")
        ident, kind = node["id"], node["elType"]
        if not isinstance(ident, str) or not ID.fullmatch(ident) or ident in ids:
            raise ValueError("Invalid or duplicate Elementor node ID")
        ids.add(ident)
        if kind not in ALLOWED or not isinstance(node["settings"], dict) or not isinstance(node["elements"], list):
            raise ValueError("Unsupported Elementor node")
        if kind == "widget":
            if node.get("widgetType") not in WIDGETS or node["elements"]:
                raise ValueError("Unsupported Elementor widget")
        elif "widgetType" in node:
            raise ValueError("Unexpected widget type")
        settings(node["settings"])
        for child in node["elements"]:
            walk(child, depth + 1)

    settings(doc["page_settings"])
    for node in doc["content"]:
        walk(node)
    return {"status": "PREFLIGHT_ONLY", "imported": False, "localwp_verified": False,
            "nodes": count, "media_slots": sorted(slots)}

if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("Expected one controlled Elementor JSON export")
        path = Path(sys.argv[1])
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 256000:
            raise ValueError("Invalid export file")
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
        print(json.dumps(check(data), sort_keys=True))
    except (OSError, ValueError, TypeError) as exc:
        print("EZ2_ELEMENTOR_PREFLIGHT_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
