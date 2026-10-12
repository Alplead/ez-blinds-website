"""Synthetic offline regression coverage. No WordPress or network access."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from ez2_elementor_media_compile import compile_export, write_private

HOST = "ez2-review.local"
URL = f"http://{HOST}/wp-content/uploads/2026/10/synthetic-photo.webp"
def fixture():
    doc = {"title":"Synthetic","type":"page","version":"4.3.4","page_settings":{},
           "content":[{"id":"deadbeef","elType":"container",
                       "settings":{"background_slideshow_gallery":[{"url":"ez2-media://hero-one","id":""}]},
                       "elements":[{"id":"abcd1234","elType":"widget","widgetType":"image",
                                    "settings":{"image":{"url":"ez2-media://hero-one"}},"elements":[]}]}]}
    mapping = {"schema_version":1,"target_site":"ez2-isolated-only","host":HOST,
               "slots":{"hero-one":{"id":123,"url":URL,"mime":"image/webp"}}}
    return doc,mapping

cases=0
d,m=fixture()
out,meta=compile_export(d,m,HOST)
assert meta["status"]=="COMPILED_OFFLINE_ONLY" and meta["media_slots_resolved"]==1
assert not any(meta[k] for k in ("wordpress_imported","site_modified","deployment_authorized"))
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
reject(lambda d,m:d["content"][0]["settings"].update(external="https://remote.invalid/pic"))
reject(lambda d,m:m.update(host="ez2-review.local"),host="ez-bns-new-dev.local")
reject(lambda d,m:m["slots"]["hero-one"].update(url=f"http://user@{HOST}/wp-content/uploads/2026/10/photo.webp"))
reject(lambda d,m:m["slots"]["hero-one"].update(url=f"http://{HOST}/wp-content/uploads/2026/10/photo.webp#frag"))
reject(lambda d,m:m["slots"]["hero-one"].update(url=f"http://{HOST}/wp-content/uploads/2026/10/\\photo.webp"))

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
assert cases==25,cases
print(f"EZ2_ELEMENTOR_MEDIA_COMPILE_PASS cases={cases}")
