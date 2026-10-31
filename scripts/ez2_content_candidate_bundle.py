#!/usr/bin/env python3
"""Package public-safe Elementor review JSON; never install or publish it."""
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from ez2_elementor_export_check import check, unique, reject_nonfinite

SOURCE = "design/ez2-home-hero-candidate.json"
NAME = "elementor/home-hero.json"
SLOTS = {"home-hero-one", "home-hero-two", "home-hero-three", "home-hero-four"}

def candidate(data):
    if not 0 < len(data) <= 256000:
        raise ValueError("Invalid template size")
    doc = json.loads(data, object_pairs_hook=unique, parse_constant=reject_nonfinite)
    result = check(doc)
    if set(result["media_slots"]) != SLOTS or doc["version"] not in ("4.3.4", "4.3.5"):
        raise ValueError("Unexpected template or media slots")
    return doc

def package(sha, data):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid source SHA")
    candidate(data)
    manifest = {"schema": 1, "source_sha": sha, "template_sha256": hashlib.sha256(data).hexdigest(),
                "scope": "public-review-candidate-only", "localwp_installed": False,
                "plugin_installed": False, "private_media_included": False,
                "deployment_authorized": False}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path, payload in ((NAME, data), ("MANIFEST.json", json.dumps(manifest, sort_keys=True))):
            info = zipfile.ZipInfo(path, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, payload)
    return output.getvalue()

def verify(sha, data):
    if len(data) > 300000:
        raise ValueError("Oversized ZIP")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sorted(z.namelist()) != ["MANIFEST.json", NAME] or z.testzip() is not None:
            raise ValueError("Unexpected ZIP members")
        raw = z.read(NAME)
        manifest = json.loads(z.read("MANIFEST.json"), object_pairs_hook=unique)
    if package(sha, raw) != data:
        raise ValueError("Tampered or non-canonical candidate")
    return manifest

def main(argv):
    if len(argv) != 5 or argv[1] not in ("build", "verify"):
        raise ValueError("Usage: SCRIPT build|verify ROOT SHA ZIP")
    mode, root, sha, output = argv[1], Path(argv[2]).resolve(), argv[3], Path(argv[4])
    if mode == "build":
        head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        if head != sha or output.parent.resolve() != (root / ".release").resolve() or output.exists() or output.parent.is_symlink():
            raise ValueError("Wrong source or unsafe output")
        raw = subprocess.check_output(["git", "-C", str(root), "show", f"{sha}:{SOURCE}"])
        output.write_bytes(package(sha, raw))
    else:
        if output.is_symlink():
            raise ValueError("Linked ZIP")
        verify(sha, output.read_bytes())
    print("EZ2_PUBLIC_CONTENT_CANDIDATE_PASS installable=false")

if __name__ == "__main__":
    try:
        main(sys.argv)
    except (OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError, zipfile.BadZipFile) as e:
        print("EZ2_CONTENT_CANDIDATE_FAIL: " + str(e), file=sys.stderr)
        sys.exit(1)
