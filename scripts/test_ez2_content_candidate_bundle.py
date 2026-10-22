"""Offline tests for exact-head public Elementor candidate artifact."""
import copy
import json
import zipfile
from ez2_content_candidate_bundle import candidate, package, verify

SHA = "a" * 40
SLOTS = ("one", "two", "three", "four")

def fixture():
    return {"title": "Synthetic candidate", "type": "page", "version": "4.3.4",
            "page_settings": {}, "content": [{"id": "deadbeef", "elType": "container",
            "settings": {"background_slideshow_gallery": [
                {"url": "ez2-media://home-hero-" + n} for n in SLOTS]}, "elements": []}]}

def encode(doc):
    return json.dumps(doc).encode()

data = encode(fixture())
assert candidate(data)["version"] == "4.3.4"
archive = package(SHA, data)
assert verify(SHA, archive)["localwp_installed"] is False
assert package(SHA, data) == archive
cases = 3

def reject(fn):
    global cases
    try:
        fn()
    except (ValueError, TypeError, zipfile.BadZipFile):
        cases += 1
        return
    raise AssertionError("Unsafe candidate accepted")

reject(lambda: package("bad", data))
reject(lambda: verify("b" * 40, archive))
reject(lambda: candidate(b""))
reject(lambda: candidate(b"x" * 256001))
reject(lambda: candidate(b'{"title":"a","title":"b"}'))
wrong = fixture()
wrong["version"] = "5.0.0"
reject(lambda: package(SHA, encode(wrong)))
wrong = fixture()
wrong["content"][0]["settings"]["background_slideshow_gallery"].pop()
reject(lambda: package(SHA, encode(wrong)))
wrong = fixture()
wrong["content"][0]["settings"]["background_slideshow_gallery"].append(
    {"url": "https://example.invalid/customer.jpg"})
reject(lambda: package(SHA, encode(wrong)))
wrong = fixture()
wrong["content"][0]["settings"]["custom_html"] = "<script>unsafe</script>"
reject(lambda: package(SHA, encode(wrong)))
reject(lambda: verify(SHA, archive[:-5]))
assert cases == 13, cases
print(f"EZ2_PUBLIC_CONTENT_CANDIDATE_TEST_PASS cases={cases}")
