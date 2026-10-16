"""Synthetic-only regression tests; no site writes, downloads or private media."""
import copy
import json
import tempfile
import zipfile
from pathlib import Path
from ez2_hero_review_artifact import TEMPLATE, METADATA, pack, verify

SHA = "a" * 40
DOC = {
    "title": "EZ2 Home Hero - Unpublished Owner Review Candidate",
    "type": "page", "version": "4.3.4", "page_settings": {"hide_title": "yes"},
    "content": [{"id": "e2a10001", "elType": "container", "settings": {
        "content_width": "full", "min_height": {"unit": "vh", "size": 90},
        "background_background": "slideshow",
        "background_slideshow_gallery": [{"id": "", "url": "ez2-media://" + s}
            for s in ("home-hero-one", "home-hero-two", "home-hero-three", "home-hero-four")],
        "background_slideshow_loop": "yes", "background_slideshow_slide_duration": 5000,
        "background_slideshow_slide_transition": "fade",
        "background_slideshow_transition_duration": 1200,
        "background_slideshow_ken_burns": "yes",
        "background_slideshow_ken_burns_zoom_direction": "in",
        "background_slideshow_size": "cover", "background_overlay_background": "classic",
        "background_overlay_color": "#000000",
        "background_overlay_opacity": {"unit": "px", "size": 0.45},
    }, "elements": [
        {"id": "e2a10002", "elType": "widget", "widgetType": "heading",
         "settings": {"title": "Blinds & Shutters", "header_size": "h1"}, "elements": []},
        {"id": "e2a10003", "elType": "widget", "widgetType": "button",
         "settings": {"text": "Request a Quote", "link": {"url": "/contact/"}}, "elements": []}
    ]}]
}
RAW = (json.dumps(DOC, separators=(",", ":")) + "\n").encode()
cases = 0


def reject(fn):
    global cases
    try:
        fn()
    except (ValueError, TypeError, KeyError, UnicodeError):
        cases += 1
    else:
        raise AssertionError("Unsafe review artifact accepted")


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    output = root / "candidate.zip"
    record = pack(RAW, SHA, output)
    assert record["scope"] == "unpublished-elementor-hero-review-only"
    assert record["media_slots"] == sorted(("home-hero-one", "home-hero-two", "home-hero-three", "home-hero-four"))
    assert all(record[k] is False for k in ("media_bytes_included", "plugins_included",
        "database_included", "localwp_installed", "deployment_authorized"))
    cases += 1
    assert verify(output, SHA)["status"] == "UNPUBLISHED_REVIEW_ARTIFACT_VERIFIED"
    cases += 1
    reject(lambda: pack(RAW, SHA, output))
    reject(lambda: pack(RAW, "bad", root / "bad.zip"))
    reject(lambda: pack(b"", SHA, root / "empty.zip"))
    reject(lambda: pack(b"a" * 256001, SHA, root / "large.zip"))
    reject(lambda: pack(RAW.replace(b"ez2-media://home-hero-one", b"https://external.invalid/a"), SHA, root / "external.zip"))
    reject(lambda: pack(RAW.replace(b"4.3.4", b"4.3.5"), SHA, root / "version.zip"))
    reject(lambda: verify(output, "b" * 40))
    reject(lambda: verify(output, "bad"))
    def forged(filename, change=None, extra=None, template=None):
        source = copy.deepcopy(record)
        if change:
            change(source)
        with zipfile.ZipFile(root / filename, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(TEMPLATE, RAW if template is None else template)
            archive.writestr(METADATA, json.dumps(source))
            if extra:
                archive.writestr(extra, b"forbidden")
        return root / filename
    reject(lambda: verify(forged("fake-approval.zip", lambda r: r.update(deployment_authorized=True)), SHA))
    reject(lambda: verify(forged("fake-installed.zip", lambda r: r.update(localwp_installed=True)), SHA))
    reject(lambda: verify(forged("private.zip", extra="uploads/customer.webp"), SHA))
    reject(lambda: verify(forged("modified.zip", template=RAW.replace(b"Blinds & Shutters", b"Altered text")), SHA))
    reject(lambda: verify(forged("wrong-hash.zip", lambda r: r.update(template_sha256="0" * 64)), SHA))
    (root / "not-zip.zip").write_text("invalid")
    reject(lambda: verify(root / "not-zip.zip", SHA))
    (root / "symlink.zip").symlink_to(output)
    reject(lambda: verify(root / "symlink.zip", SHA))
    reject(lambda: verify(root / "missing.zip", SHA))
assert cases == 18, cases
print(f"EZ2_HERO_REVIEW_ARTIFACT_PASS cases={cases}")
