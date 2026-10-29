#!/usr/bin/env python3
"""Read-only validation of controlled, public-safe EZ2 Elementor page exports.

This does not install Elementor or import content into WordPress.
"""
import json
import math
import re
import sys
from html import unescape
from pathlib import Path

ID = re.compile(r"[0-9a-f]{6,16}\Z")
SLOT = re.compile(r"ez2-media://[a-z0-9][a-z0-9-]{0,79}\Z")
URI_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
ALLOWED = {"container", "section", "column", "widget"}
WIDGETS = {"heading", "text-editor", "image", "button", "divider", "spacer", "icon", "image-carousel"}
# Deliberately conservative: this preflight is not an HTML sanitizer.
# It accepts basic attribute-free formatting; links must use controlled button widgets.
SAFE_TAG = re.compile(r"<(/?)(p|br|strong|em|b|i|u|ul|ol|li)(\s*/?)>", re.IGNORECASE)
DANGEROUS_SCHEME = re.compile(r"(?:javascript|data|vbscript|file|blob)\s*:", re.IGNORECASE)

def validate_markup(value):
    decoded = unescape(value)
    if DANGEROUS_SCHEME.search(decoded):
        raise ValueError("Unsupported embedded URI scheme")
    if "<" not in decoded:
        return
    stack = []
    for token in re.split(r"(<[^>]*>)", decoded):
        if not token:
            continue
        if token.startswith("<"):
            match = SAFE_TAG.fullmatch(token)
            if not match:
                raise ValueError("Unsupported HTML markup")
            closing, tag, self_closing = match.groups()
            tag = tag.lower()
            if closing:
                if self_closing or not stack or stack.pop() != tag:
                    raise ValueError("Unbalanced HTML markup")
            elif tag == "br":
                continue
            elif self_closing:
                raise ValueError("Unsupported self-closing HTML markup")
            else:
                stack.append(tag)
        elif "<" in token:
            raise ValueError("Malformed HTML markup")
    if stack:
        raise ValueError("Unclosed HTML markup")

def unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON key")
        obj[key] = value
    return obj

def reject_nonfinite(value):
    raise ValueError("Non-finite JSON number")

def check(doc):
    if not isinstance(doc, dict) or set(doc) != {"title", "type", "version", "page_settings", "content"}:
        raise ValueError("Unexpected Elementor export fields")
    if doc["type"] != "page" or not isinstance(doc["title"], str) or not isinstance(doc["version"], str):
        raise ValueError("Unexpected Elementor page metadata")
    if "ez2-media://" in doc["title"]:
        raise ValueError("Symbolic media cannot appear in the page title")
    if not isinstance(doc["page_settings"], dict) or not isinstance(doc["content"], list) or not doc["content"]:
        raise ValueError("Missing Elementor page content")
    ids, slots = set(), set()
    count = 0

    def settings(value, depth=0, field=None):
        if depth > 12:
            raise ValueError("Settings nesting limit")
        if isinstance(value, dict):
            if len(value) > 80:
                raise ValueError("Settings count limit")
            for key, item in value.items():
                if not isinstance(key, str) or key.lower() in {"__dynamic__", "custom_html", "shortcode", "custom_css"}:
                    raise ValueError("Unsupported settings field")
                settings(item, depth + 1, key)
        elif isinstance(value, list):
            if len(value) > 100:
                raise ValueError("Settings list limit")
            for item in value:
                settings(item, depth + 1, field)
        elif isinstance(value, str):
            if len(value) > 6000:
                raise ValueError("Settings text limit")
            validate_markup(value)
            if value.startswith("ez2-media://"):
                # Media references belong to Elementor image URL fields,
                # never a heading, button label or other Owner-facing text.
                if field != "url" or not SLOT.fullmatch(value):
                    raise ValueError("Invalid media slot")
                slots.add(value[len("ez2-media://"):])
            elif ("://" in value or value.lstrip().startswith("//")
                  or URI_SCHEME.match(value.lstrip())):
                raise ValueError("External references are not allowed")
        elif type(value) is float and not math.isfinite(value):
            raise ValueError("Non-finite settings number")
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
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                          parse_constant=reject_nonfinite)
        print(json.dumps(check(data), sort_keys=True))
    except (OSError, ValueError, TypeError) as exc:
        print("EZ2_ELEMENTOR_PREFLIGHT_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
