"""Synthetic no-network integration tests for isolated EZ2 delivery planning."""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from ez2_content_guard import digest
from ez2_delivery_preflight import check, run

SHA = "a" * 40

def fixture():
    page = {"title": "Synthetic home", "type": "page", "version": "3.31.1",
            "page_settings": {}, "content": [{"id": "deadbeef", "elType": "container",
                "settings": {"background_slideshow_gallery": [{"url": "ez2-media://hero-one"}]},
                "elements": [{"id": "ab12cd34", "elType": "widget", "widgetType": "heading",
                              "settings": {"title": "Demo"}, "elements": []}]}]}
    lock = {"schema_version": 1, "target_site": "ez2-isolated-only",
            "plugins": [{"slug": "elementor", "version": "4.3.4", "entrypoint": "elementor/elementor.php",
                         "source": "wordpress.org", "archive_sha256": "b" * 64, "activate": True}]}
    contract = {"schema_version": 1, "target_site": "ez2-isolated-only", "source_sha": SHA,
                "plugin_lock": "plugins.json", "templates": [
                    {"key": "ez2-home", "file": "home.json", "previous_sha256": None}],
                "media_slots": ["hero-one"]}
    installed = {"schema_version": 1, "items": []}
    return contract, installed, lock, {"home.json": page}

cases = 0
c, i, p, e = fixture()
r = check(c, i, p, e, SHA)
assert r["status"] == "READY_FOR_RUNTIME_TEST_ONLY" and not r["applied"]
assert not r["deployment_authorized"] and not r["localwp_verified"]
assert r["content"]["actions"][0]["action"] == "create"
assert r["content"]["unmanaged_existing_keys"] == []
cases += 1

def reject(mutate):
    global cases
    values = copy.deepcopy(fixture())
    mutate(*values)
    try:
        check(*values, SHA)
    except (ValueError, TypeError):
        cases += 1
        return
    raise AssertionError("Unsafe contract accepted")

reject(lambda c,i,p,e: c.update(target_site="ez-bns-new-dev.local"))
reject(lambda c,i,p,e: c.update(source_sha="f"*40))
reject(lambda c,i,p,e: c.update(schema_version=True))
reject(lambda c,i,p,e: c["templates"][0].update(file="../home.json"))
reject(lambda c,i,p,e: c["templates"][0].update(key="../home"))
reject(lambda c,i,p,e: c["templates"].append(copy.deepcopy(c["templates"][0])))
reject(lambda c,i,p,e: c["media_slots"].append("hero-one"))
reject(lambda c,i,p,e: c["media_slots"].append("../../secrets"))
reject(lambda c,i,p,e: p["plugins"][0].update(slug="elementor-pro"))
reject(lambda c,i,p,e: p["plugins"][0].update(version="4.3.5"))
reject(lambda c,i,p,e: e["home.json"].update(version="4.3.5"))
reject(lambda c,i,p,e: e["home.json"]["content"][0]["settings"].update(url="https://example.invalid/photo.jpg"))
reject(lambda c,i,p,e: c["templates"][0].update(previous_sha256="invalid"))

c,i,p,e = fixture()
c["media_slots"] = []
r = check(c,i,p,e,SHA)
assert r["status"] == "BLOCKED_PREFLIGHT" and r["unresolved_media_slots"] == ["hero-one"]
cases += 1
c,i,p,e = fixture()
p["plugins"][0]["archive_sha256"] = None
r = check(c,i,p,e,SHA)
assert r["status"] == "BLOCKED_PREFLIGHT" and r["missing_plugin_checksums"] == ["elementor"]
cases += 1
c,i,p,e = fixture()
i["items"] = [{"key": "ez2-home", "current_sha256": digest({"owner_edit": True})}]
r = check(c,i,p,e,SHA)
assert r["status"] == "BLOCKED_PREFLIGHT" and r["content"]["conflict_count"] == 1
cases += 1
c,i,p,e = fixture()
i["items"] = [{"key": "ez2-home", "current_sha256": digest(e["home.json"])}]
r = check(c,i,p,e,SHA)
assert r["status"] == "READY_FOR_RUNTIME_TEST_ONLY" and r["content"]["actions"][0]["action"] == "unchanged"
cases += 1
c,i,p,e = fixture()
c["media_slots"] = ["hero-one", "spare"]
r = check(c,i,p,e,SHA)
assert r["unused_media_slots"] == ["spare"]
cases += 1

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    c,i,p,e = fixture()
    for name,doc in {"delivery.json":c,"installed.json":i,"plugins.json":p,**e}.items():
        (root/name).write_text(json.dumps(doc), encoding="utf-8")
    assert run(root,SHA)["status"] == "READY_FOR_RUNTIME_TEST_ONLY"
    cases += 1
    script = Path(__file__).with_name("ez2_delivery_preflight.py")
    cmd = [sys.executable, str(script), str(root), SHA]
    output = subprocess.run(cmd, capture_output=True, text=True)
    assert output.returncode == 0 and json.loads(output.stdout)["installed"] is False
    cases += 1
    (root/"home.json").write_text('{"title":"a","title":"b"}')
    assert subprocess.run(cmd, capture_output=True).returncode == 1
    cases += 1
    (root/"home.json").unlink()
    (root/"home.json").symlink_to(root/"plugins.json")
    assert subprocess.run(cmd, capture_output=True).returncode == 1
    cases += 1
    (root/"home.json").unlink()
    (root/"home.json").write_text(json.dumps(e["home.json"]))
    (root/"delivery.json").write_text(json.dumps({**c,"media_slots":[]}))
    output = subprocess.run(cmd, capture_output=True, text=True)
    assert output.returncode == 2 and json.loads(output.stdout)["status"] == "BLOCKED_PREFLIGHT"
    cases += 1

assert cases == 24, cases
print(f"EZ2_DELIVERY_PREFLIGHT_PASS cases={cases}")
