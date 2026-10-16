#!/usr/bin/env python3
"""Validate the unpublished EZ2 Elementor hero candidate; never import or deploy."""
import json
import sys
from pathlib import Path
from ez2_elementor_export_check import check as check_export, unique, reject_nonfinite

SLOTS = ("home-hero-one", "home-hero-two", "home-hero-three", "home-hero-four")
EXPECTED = {
    "content_width": "full",
    "min_height": {"unit": "vh", "size": 90},
    "background_background": "slideshow",
    "background_slideshow_loop": "yes",
    "background_slideshow_slide_duration": 5000,
    "background_slideshow_slide_transition": "fade",
    "background_slideshow_transition_duration": 1200,
    "background_slideshow_ken_burns": "yes",
    "background_slideshow_ken_burns_zoom_direction": "in",
    "background_slideshow_size": "cover",
    "background_overlay_background": "classic",
    "background_overlay_color": "#000000",
    "background_overlay_opacity": {"unit": "px", "size": 0.45},
}

def check(doc):
    summary = check_export(doc)
    if (doc["title"] != "EZ2 Home Hero - Unpublished Owner Review Candidate"
            or doc["version"] != "4.3.4" or doc["page_settings"] != {"hide_title": "yes"}
            or len(doc["content"]) != 1):
        raise ValueError("Candidate identity or scope changed")
    hero = doc["content"][0]
    if hero["id"] != "e2a10001" or hero["elType"] != "container":
        raise ValueError("Expected one hero container")
    settings = hero["settings"]
    if set(settings) != set(EXPECTED) | {"background_slideshow_gallery"}:
        raise ValueError("Unexpected hero settings")
    for name, expected in EXPECTED.items():
        if settings[name] != expected:
            raise ValueError("Unapproved visual or motion setting: " + name)
    expected_gallery = [{"id": "", "url": "ez2-media://" + slot} for slot in SLOTS]
    if settings["background_slideshow_gallery"] != expected_gallery:
        raise ValueError("Expected four symbolic media slots in order")
    if (summary["media_slots"] != sorted(SLOTS) or summary["nodes"] != 3
            or len(hero["elements"]) != 2):
        raise ValueError("Unexpected content or media")
    heading, button = hero["elements"]
    if (heading != {"id": "e2a10002", "elType": "widget", "widgetType": "heading",
                    "settings": {"title": "Blinds & Shutters", "header_size": "h1"},
                    "elements": []}
            or button != {"id": "e2a10003", "elType": "widget", "widgetType": "button",
                          "settings": {"text": "Request a Quote", "link": {"url": "/contact/"}},
                          "elements": []}):
        raise ValueError("Unapproved draft hero text or link")
    return {"status": "UNPUBLISHED_CANDIDATE_PREFLIGHT_ONLY",
            "media_slots": list(SLOTS), "nodes": summary["nodes"],
            "elementor_version_runtime_verified": False, "wordpress_imported": False,
            "localwp_visual_qa_verified": False, "owner_design_approved": False,
            "deployment_authorized": False}

def load(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256000:
        raise ValueError("Unsafe candidate JSON")
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=unique, parse_constant=reject_nonfinite)

if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("Usage: ez2_home_candidate_check.py CANDIDATE.json")
        print(json.dumps(check(load(sys.argv[1])), sort_keys=True))
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print("EZ2_HOME_CANDIDATE_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
