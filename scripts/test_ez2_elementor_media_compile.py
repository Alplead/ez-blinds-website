"""Synthetic offline regression coverage. No WordPress or network access."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from ez2_elementor_media_compile import compile_export, ensure_private_media_map, write_private, read_json

HOST = "ez2-review.local"
URL = f"http://{HOST}/wp-content/uploads/2026/10/synthetic-photo.webp"
def fixture():
    doc = {"title":"Synthetic","type":"page","version":"4.3.4","page_settings":{},
           "content":[{"id":"deadbeef","elType":"container",
                       "settings":{"background_slideshow_gallery":[{"url":"ez2-media://hero-one","id":""}]},
                       "elements":[{"id":"abcd1234","elType":"widget","widgetType":"image",
                                    "settings":{"image":{"url":"ez2-media://hero-one"}},"elements":[]}]}]}
    mapping = {"schema_version":2,"target_site":"ez2-isolated-only","host":HOST,
               "slots":{"hero-one":{"id":123,"url":URL,"mime":"image/webp","sha256":"a"*64}}}
    return doc,mapping

cases=0
d,m=fixture()
out,meta=compile_export(d,m,HOST)
assert meta["status"]=="COMPILED_OFFLINE_ONLY" and meta["media_slots_resolved"]==1
assert not any(meta[k] for k in ("wordpress_imported","site_modified","deployment_authorized","media_integrity_verified"))
assert "a"*64 not in json.dumps(meta)
assert out["content"][0]["settings"]["background_slideshow_gallery"][0]=={"url":URL,"id":123}
assert out["content"][0]["elements"][0]["settings"]["image"]=={"url":URL,"id":123}
cases+=1

def reject(change,host=HOST):
    global cases
    d,m=fixture()
    change(d,m)
    try:
        compile_export(d,m,host)
    except (ValueError,TypeError,KeyError):
        cases+=1
        return
    raise AssertionError("Unsafe mapping accepted")

reject(lambda d,m:m.update(target_site="ez-bns-new-dev.local"))
reject(lambda d,m:m.update(host="ezbns.com.au"))
reject(lambda d,m:m.update(schema_version=True))
reject(lambda d,m:m.update(schema_version=1))
reject(lambda d,m:m["slots"]["hero-one"].pop("sha256"))
reject(lambda d,m:m["slots"]["hero-one"].update(sha256="A"*64))
reject(lambda d,m:m["slots"]["hero-one"].update(sha256="a"*63))
reject(lambda d,m:m["slots"]["hero-one"].update(sha256=123))
reject(lambda d,m:m["slots"]["hero-one"].update(id=True))
reject(lambda d,m:m["slots"]["hero-one"].update(id=-1))
reject(lambda d,m:m["slots"]["hero-one"].update(url="https://ezbns.com.au/wp-content/uploads/2026/10/photo.webp"))
reject(lambda d,m:m["slots"]["hero-one"].update(url=f"http://{HOST}.evil.invalid/wp-content/uploads/2026/10/photo.webp"))
reject(lambda d,m:m["slots"]["hero-one"].update(url=f"http://{HOST}:8080/wp-content/uploads/2026/10/photo.webp"))
reject(lambda d,m:m["slots"]["hero-one"].update(url=f"http://{HOST}/wp-content/uploads/../private.webp"))
reject(lambda d,m:m["slots"]["hero-one"].update(url=f"http://{HOST}/wp-content/uploads/%2e%2e/private.webp"))
reject(lambda d,m:m["slots"]["hero-one"].update(url=f"http://{HOST}/wp-content/uploads/2026/10/photo.webp?token=1"))
reject(lambda d,m:m["slots"]["hero-one"].update(mime="application/pdf"))
reject(lambda d,m:m["slots"]["hero-one"].update(url=f"http://{HOST}/wp-content/uploads/2026/10/photo.jpg"))
reject(lambda d,m:m["slots"].update(extra={"id":321,"url":URL,"mime":"image/webp"}))
reject(lambda d,m:d["content"][0]["settings"]["background_slideshow_gallery"][0].update(id=999))
# A symbolic image token is never permitted to rewrite an Owner-facing page
# title, a heading widget, or unrelated text in an Elementor settings object.
reject(lambda d,m:d.update(title="ez2-media://hero-one"))
reject(lambda d,m:d["content"][0]["elements"][0]["settings"].update(title="ez2-media://hero-one"))
reject(lambda d,m:d["content"][0]["settings"].update(custom_label="ez2-media://hero-one"))
reject(lambda d,m:d["content"][0]["settings"].update(external="https://remote.invalid/pic"))
reject(lambda d,m:m.update(host="ez2-review.local"),host="ez-bns-new-dev.local")
reject(lambda d,m:m["slots"]["hero-one"].update(url=f"http://user@{HOST}/wp-content/uploads/2026/10/photo.webp"))
reject(lambda d,m:m["slots"]["hero-one"].update(url=f"http://{HOST}/wp-content/uploads/2026/10/photo.webp#frag"))
reject(lambda d,m:m["slots"]["hero-one"].update(url=f"http://{HOST}/wp-content/uploads/2026/10/\\photo.webp"))

# A symbolic URL in a button or unrelated setting must fail before
# compilation, even when its slot is present in the private media map.
reject(lambda d,m:d["content"][0]["elements"][0].update(
    widgetType="button", settings={"link": {"url": "ez2-media://hero-one"}}))
reject(lambda d,m:d["content"][0]["settings"].update(
    tracking={"url": "ez2-media://hero-one"}))
reject(lambda d,m:d["content"][0]["elements"][0]["settings"].update(
    caption={"url": "ez2-media://hero-one"}))

def add_second_slot(doc, media_map, attachment_id, url):
    media_map["slots"]["hero-two"] = {"id": attachment_id, "url": url, "mime": "image/webp", "sha256": "a"*64}
    doc["content"][0]["settings"]["background_slideshow_gallery"].append(
        {"url": "ez2-media://hero-two", "id": ""})

# Reusing the same attachment across slots is allowed; conflicting mappings are not.
reject(lambda d,m:add_second_slot(d,m,123,
       f"http://{HOST}/wp-content/uploads/2026/10/other-photo.webp"))
reject(lambda d,m:add_second_slot(d,m,124,URL))
reject(lambda d,m:(add_second_slot(d,m,123,URL),m["slots"]["hero-two"].update(sha256="b"*64)))
d_alias,m_alias=fixture()
add_second_slot(d_alias,m_alias,123,URL)
alias_export,alias_meta=compile_export(d_alias,m_alias,HOST)
assert alias_meta["media_slots_resolved"]==2
assert alias_export["content"][0]["settings"]["background_slideshow_gallery"][1]=={"url":URL,"id":123}
cases+=1

with tempfile.TemporaryDirectory() as tmp:
    tmp=Path(tmp)
    target=tmp/"resolved.json"
    write_private(target,out)
    assert json.loads(target.read_text())==out
    if os.name!="nt":assert target.stat().st_mode & 0o777==0o600
    cases+=1
    try:write_private(target,out)
    except FileExistsError:cases+=1
    else:raise AssertionError("Overwrote private output")
    link=tmp/"link.json"
    link.symlink_to(target)
    try:write_private(link,out)
    except ValueError:cases+=1
    else:raise AssertionError("Wrote to symlink")
    d,m=fixture()
    (tmp/"source.json").write_text(json.dumps(d))
    (tmp/"media.json").write_text(json.dumps(m))
    script=Path(__file__).with_name("ez2_elementor_media_compile.py")
    r=subprocess.run([sys.executable,str(script),str(tmp/"source.json"),str(tmp/"media.json"),HOST,str(tmp/"compiled.json")],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    assert json.loads(r.stdout)["wordpress_imported"] is False
    cases+=1
    private_guard_cases=0
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as checkout_tmp:
        inside=Path(checkout_tmp)/"synthetic-map.json"
        inside.write_text(json.dumps(m))
        try:ensure_private_media_map(str(inside))
        except ValueError:private_guard_cases+=1
        else:raise AssertionError("Accepted public-checkout media map")
        if os.name!="nt":
            alias=Path(checkout_tmp)/"linked-map.json"
            alias.symlink_to(tmp/"media.json")
            try:ensure_private_media_map(str(alias))
            except ValueError:private_guard_cases+=1
            else:raise AssertionError("Accepted in-checkout symlink to private media map")
            linked_dir=Path(checkout_tmp)/"linked-directory"
            linked_dir.symlink_to(tmp, target_is_directory=True)
            try:ensure_private_media_map(str(linked_dir/"media.json"))
            except ValueError:private_guard_cases+=1
            else:raise AssertionError("Accepted map through in-checkout linked directory")

# The private mapping must be bound to a single verified file descriptor.
# Linux CI permits hardlinks and path replacement that Windows LocalWP must
# not inherit as trusted media inputs.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    media_path = root / "media.json"
    media_path.write_text(json.dumps(fixture()[1]), encoding="utf-8")
    assert read_json(media_path, 65536)["host"] == HOST
    cases += 1

    linked = root / "linked.json"
    os.link(media_path, linked)
    try:
        read_json(linked, 65536)
    except ValueError:
        cases += 1
    else:
        raise AssertionError("Accepted a hardlinked private media map")
    linked.unlink()

    alias = root / "alias.json"
    alias.symlink_to(media_path)
    try:
        read_json(alias, 65536)
    except ValueError:
        cases += 1
    else:
        raise AssertionError("Accepted a symlinked private media map")
    alias.unlink()

    media_path.write_bytes(b"")
    try:
        read_json(media_path, 65536)
    except ValueError:
        cases += 1
    else:
        raise AssertionError("Accepted an empty private media map")

    media_path.write_text(json.dumps(fixture()[1]), encoding="utf-8")
    original_open = os.open
    swapped = [False]
    def swap_media_before_open(path, flags, *args, **kwargs):
        if Path(path) == media_path and not swapped[0]:
            replacement = root / "replacement.json"
            replacement.write_bytes(media_path.read_bytes())
            os.replace(replacement, media_path)
            swapped[0] = True
        return original_open(path, flags, *args, **kwargs)
    with patch("ez2_backup_preflight.os.open", side_effect=swap_media_before_open):
        try:
            read_json(media_path, 65536)
        except ValueError:
            assert swapped[0]
            cases += 1
        else:
            raise AssertionError("Accepted same-byte private map replacement")

assert cases==45,cases
assert private_guard_cases==(1 if os.name=="nt" else 3),private_guard_cases
print(f"EZ2_ELEMENTOR_MEDIA_COMPILE_PASS cases={cases}")
print(f"EZ2_PRIVATE_MEDIA_GUARD_PASS cases={private_guard_cases}")
