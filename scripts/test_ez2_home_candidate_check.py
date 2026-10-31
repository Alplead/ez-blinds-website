"""Offline regression tests for the unpublished Elementor hero candidate."""
import copy
import json
from pathlib import Path
from ez2_home_candidate_check import check, load, SLOTS
from ez2_elementor_media_compile import compile_export

path = Path(__file__).resolve().parents[1] / "design" / "ez2-home-hero-candidate.json"
base = load(path)
cases = 0
result = check(base)
assert result["status"] == "UNPUBLISHED_CANDIDATE_PREFLIGHT_ONLY"
assert result["media_slots"] == list(SLOTS) and result["nodes"] == 3
assert all(result[k] is False for k in ("elementor_version_runtime_verified",
    "wordpress_imported", "localwp_visual_qa_verified", "owner_design_approved",
    "deployment_authorized"))
cases += 1

mapping = {"schema_version": 2, "target_site": "ez2-isolated-only",
           "host": "ez2-review.local", "slots": {
               slot: {"id": n, "url": f"http://ez2-review.local/wp-content/uploads/2026/10/{slot}.webp",
                      "mime": "image/webp", "sha256": "a" * 64} for n, slot in enumerate(SLOTS, start=101)}}
compiled, report = compile_export(base, mapping, "ez2-review.local")
assert report["status"] == "COMPILED_OFFLINE_ONLY"
assert report["media_slots_resolved"] == 4 and report["site_modified"] is False
assert report["deployment_authorized"] is False
gallery = compiled["content"][0]["settings"]["background_slideshow_gallery"]
assert [item["id"] for item in gallery] == [101, 102, 103, 104]
assert all(item["url"].startswith("http://ez2-review.local/wp-content/uploads/") for item in gallery)
assert "ez2-media://" not in json.dumps(compiled)
cases += 1

def reject(change):
    global cases
    doc = copy.deepcopy(base)
    change(doc)
    try:
        check(doc)
    except (ValueError, TypeError, KeyError):
        cases += 1
        return
    raise AssertionError("Unsafe or unapproved candidate accepted")

def setting(name, value):
    return lambda doc: doc["content"][0]["settings"].__setitem__(name, value)

reject(setting("background_background", "classic"))
reject(setting("background_slideshow_loop", "no"))
reject(setting("background_slideshow_slide_duration", 1000))
reject(setting("background_slideshow_slide_transition", "slide_left"))
reject(setting("background_slideshow_transition_duration", 500))
reject(setting("background_slideshow_ken_burns", "no"))
reject(setting("background_slideshow_ken_burns_zoom_direction", "out"))
reject(setting("min_height", {"unit": "vh", "size": 50}))
reject(setting("background_overlay_opacity", {"unit": "px", "size": 0.1}))
reject(lambda doc: doc["content"][0]["settings"]["background_slideshow_gallery"].pop())
reject(lambda doc: doc["content"][0]["settings"]["background_slideshow_gallery"][0].update(url="https://example.invalid/image.webp"))
reject(lambda doc: doc["content"][0]["elements"][0].update(id="e2a10001"))
reject(lambda doc: doc["content"][0]["elements"][1].update(widgetType="slides"))
reject(lambda doc: doc["content"].append(copy.deepcopy(doc["content"][0])))
reject(lambda doc: doc["content"][0]["elements"][1]["settings"]["link"].update(url="https://external.invalid"))
reject(lambda doc: doc.update(version="4.3.5"))
reject(lambda doc: doc["content"][0]["settings"].update(custom_css="body{display:none}"))

for changed in (
    lambda m: m.update(host="ez-bns-new-dev.local"),
    lambda m: m["slots"].pop(SLOTS[0]),
    lambda m: m["slots"].update(extra={"id": 900, "url": "http://ez2-review.local/wp-content/uploads/2026/10/extra.webp", "mime": "image/webp", "sha256": "a" * 64}),
):
    other = copy.deepcopy(mapping)
    changed(other)
    try:
        compile_export(base, other, "ez2-review.local")
    except (ValueError, TypeError, KeyError):
        cases += 1
    else:
        raise AssertionError("Unsafe media map accepted")

assert cases == 22, cases
print(f"EZ2_HOME_HERO_CANDIDATE_PASS cases={cases}")
