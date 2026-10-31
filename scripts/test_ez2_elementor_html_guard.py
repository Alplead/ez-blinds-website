"""Synthetic, read-only regression for Elementor HTML and encoded injection guards."""
import copy
from ez2_elementor_export_check import check

BASE = {"title": "Synthetic", "type": "page", "version": "3.31.1",
        "page_settings": {}, "content": [
            {"id": "abcdef12", "elType": "widget", "widgetType": "text-editor",
             "settings": {"editor": "Safe copy"}, "elements": []}]}

safe = ("<p>Safe <strong>copy</strong></p>", "<br/>",
        "Plain text &amp; details", "5 > 4")
blocked = ("<script>alert(1)</script>", "<img src=x onerror=alert(1)>",
           '<a href="javascript:alert(1)">click</a>', "&#x3c;script&#x3e;",
           "<p>broken", "<iframe src=x></iframe>",
           '<p onclick="alert(1)">x</p>', "<svg/onload=alert(1)>",
           "<p><script>bad</script></p>", "<p>unfinished<script",
           "<p/>", "data:text/html,<b>bad</b>")

cases = 0
for value in safe:
    doc = copy.deepcopy(BASE)
    doc["content"][0]["settings"]["editor"] = value
    assert check(doc)["status"] == "PREFLIGHT_ONLY"
    cases += 1
for value in blocked:
    doc = copy.deepcopy(BASE)
    doc["content"][0]["settings"]["editor"] = value
    try:
        check(doc)
    except ValueError:
        cases += 1
    else:
        raise AssertionError("Unsafe Elementor markup accepted: " + value)
assert cases == 16, cases
print(f"EZ2_ELEMENTOR_HTML_GUARD_PASS cases={cases}")
