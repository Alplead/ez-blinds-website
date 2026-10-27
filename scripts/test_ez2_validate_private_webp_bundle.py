#!/usr/bin/env python3
"""Synthetic validation regression: never stores or reads real Owner photos."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ez2_validate_private_webp_bundle import verify_bundle, BundleError, MANIFEST

CASES = 0


def make_zip(path: Path, issue: str = ""):
    records = []
    payloads = {}
    for i in range(23):
        name = f"synthetic-ez-photo-{i:02d}.webp"
        data = b"RIFF" + (2040).to_bytes(4, "little") + b"WEBP" + os.urandom(2032)
        payloads[name] = data
        records.append({
            "group": "core" if i < 8 else "gallery_expansion",
            "file": name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    if issue == "hash":
        records[0]["sha256"] = "0" * 64
    if issue == "group":
        records[0]["group"] = "gallery_expansion"
    if issue == "wrong_format":
        payloads[records[0]["file"]] = b"NOT!" + payloads[records[0]["file"]][4:]
        records[0]["sha256"] = hashlib.sha256(payloads[records[0]["file"]]).hexdigest()
    if issue == "traversal":
        old = records[0]["file"]
        records[0]["file"] = "../private.webp"
        payloads[records[0]["file"]] = payloads.pop(old)
    if issue == "duplicate":
        records[0]["file"] = records[1]["file"]
    if issue == "missing":
        payloads.pop(records[0]["file"])
    if issue == "unexpected":
        payloads["secret.sql"] = b"x"
    if issue == "symlink":
        records[0]["file"] = "symlink.webp"
        old = "synthetic-ez-photo-00.webp"
        payloads["symlink.webp"] = payloads.pop(old)

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, payload in payloads.items():
            if issue == "symlink" and name == "symlink.webp":
                member = zipfile.ZipInfo(name)
                member.create_system = 3
                member.external_attr = (0o120777 << 16)
                z.writestr(member, payload)
            else:
                z.writestr(name, payload)
        z.writestr(MANIFEST, json.dumps(records))


def check(issue, expected_code):
    global CASES
    with tempfile.TemporaryDirectory(prefix="ez2-webp-qa-") as tmp:
        path = Path(tmp) / "review.zip"
        make_zip(path, issue)
        try:
            result = verify_bundle(path)
        except BundleError as exc:
            if issue == "":
                raise
            if expected_code not in str(exc):
                raise AssertionError(f"{issue}: wrong blocker: {exc}") from exc
        else:
            if issue:
                raise AssertionError(f"{issue} unexpectedly accepted")
            if (result["photos"] != 23 or result["core"] != 8
                or result["gallery_expansion"] != 15
                or result["files_imported"] != 0
                or result["public_upload_authorized"]):
                raise AssertionError("Verified report makes an ungrounded install claim")
        CASES += 1


check("", "")
check("hash", "SHA-256")
check("group", "groups")
check("wrong_format", "WebP signature")
check("traversal", "Path traversal")
check("duplicate", "inventory record")
check("missing", "file inventory")
check("unexpected", "exactly 23")
check("symlink", "symbolic link")
print(f"EZ2_PRIVATE_WEBP_MANIFEST_TEST_PASS cases={CASES}")
