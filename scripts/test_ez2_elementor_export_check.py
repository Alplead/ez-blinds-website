"""Synthetic no-network tests for the EZ2 Elementor export preflight."""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from ez2_elementor_export_check import check, unique

def sample():
    return {"title": "Synthetic home", "type": "page", "version": "3.31.1",
            "page_settings": {},
            "content": [{"id": "a1b2c3d4", "elType": "container",
                         "settings": {"background_slideshow_gallery": [{"url": "ez2-media://hero-one"}],
                                      "background_slideshow_slide_duration": 5000},
                         "elements": [{"id": "deadbeef", "elType": "widget",
                                      "widgetType": "heading", "settings": {"title": "Demo"},
                                      "elements": []}]}]}

cases = 0
result = check(sample())
assert result["status"] == "PREFLIGHT_ONLY" and result["imported"] is False
assert result["nodes"] == 2 and result["media_slots"] == ["hero-one"]
cases += 1

def reject(change):
    global cases
    data = sample()
    change(data)
    try:
        check(data)
    except ValueError:
        cases += 1
        return
    raise AssertionError("Invalid export was accepted")

reject(lambda d: d.update(type="post"))
reject(lambda d: d.update(content=[]))
reject(lambda d: d.update(extra=True))
reject(lambda d: d["content"][0].update(id="../bad"))
reject(lambda d: d["content"][0]["elements"][0].update(id="a1b2c3d4"))
reject(lambda d: d["content"][0]["elements"][0].update(widgetType="unapproved-widget"))
reject(lambda d: d["content"][0]["settings"].update(custom_html="not permitted"))
reject(lambda d: d["content"][0]["settings"].update(image={"url": "https://example.invalid/media"}))
reject(lambda d: d["content"][0]["settings"].update(image={"url": "ez2-media://INVALID"}))
reject(lambda d: d.update(title="ez2-media://hero-one"))
reject(lambda d: d["content"][0]["elements"][0]["settings"].update(title="ez2-media://hero-one"))
reject(lambda d: d["content"][0]["settings"].update(custom_label="ez2-media://hero-one"))
reject(lambda d: d["content"][0]["settings"].update(x=[1] * 101))
reject(lambda d: d["content"][0]["elements"][0].update(elements=[{"id": "11223344"}]))
# A 'url' field is not necessarily an image. Never let a private
# attachment silently replace button destinations or unrelated settings.
reject(lambda d: d["content"][0]["elements"][0].update(
    widgetType="button", settings={"link": {"url": "ez2-media://hero-one"}}))
reject(lambda d: d["content"][0]["settings"].update(
    tracking={"url": "ez2-media://hero-one"}))
reject(lambda d: d["content"][0]["elements"][0]["settings"].update(
    image={"url": "ez2-media://hero-one"}))
reject(lambda d: d["content"][0]["settings"].update(
    image={"url": "ez2-media://hero-one"}))
reject(lambda d: d["content"][0]["elements"][0]["settings"].update(
    background_slideshow_gallery=[{"url": "ez2-media://hero-one"}]))
reject(lambda d: d["page_settings"].update(
    image={"url": "ez2-media://hero-one"}))

image = sample()
image["content"][0]["elements"][0].update(
    widgetType="image", settings={"image": {"url": "ez2-media://hero-one"}})
assert check(image)["media_slots"] == ["hero-one"]
cases += 1
carousel = sample()
carousel["content"][0]["elements"][0].update(
    widgetType="image-carousel", settings={"carousel": [{"url": "ez2-media://hero-one"}]})
assert check(carousel)["media_slots"] == ["hero-one"]
cases += 1

try:
    unique([("a", 1), ("a", 2)])
    raise AssertionError("Duplicate JSON key was accepted")
except ValueError:
    cases += 1

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "sample.json"
    path.write_text(json.dumps(sample()), encoding="utf-8")
    script = Path(__file__).with_name("ez2_elementor_export_check.py")
    run = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True)
    assert run.returncode == 0 and json.loads(run.stdout)["status"] == "PREFLIGHT_ONLY"
    cases += 1
    path.write_text('{"title":"a","title":"b"}', encoding="utf-8")
    run = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True)
    assert run.returncode == 1
    cases += 1

assert cases == 26, cases
print(f"EZ2_ELEMENTOR_EXPORT_PREFLIGHT_PASS cases={cases}")
