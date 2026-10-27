#!/usr/bin/env python3
"""Verify the Owner's PRIVATE EZ2 master WebP bundle before any WordPress import.

Read-only by design: does not extract files, access the network, contact GitHub,
or change WordPress. The 23 Owner photos and ZIP never enter the public repo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

MANIFEST = "EZB_WEB_DERIVATIVES_V2_MASTER_MANIFEST.json"
EXPECTED_PHOTOS = 23
EXPECTED_GROUPS = {"core": 8, "gallery_expansion": 15}


class BundleError(ValueError):
    pass


def verify_bundle(archive: Path) -> dict:
    if not archive.is_file() or archive.is_symlink():
        raise BundleError("An existing, non-symlink local ZIP is required.")
    if archive.stat().st_size > 30 * 1024 * 1024:
        raise BundleError("Private photo ZIP exceeds review size limit.")

    with zipfile.ZipFile(archive) as zf:
        entries = zf.infolist()
        if len(entries) != EXPECTED_PHOTOS + 1:
            raise BundleError("The package must contain exactly 23 WebP photos plus one manifest.")
        names = [info.filename for info in entries]
        if len(set(names)) != len(names) or len(set(n.casefold() for n in names)) != len(names):
            raise BundleError("Duplicate ZIP entry names are not permitted.")
        if MANIFEST not in names:
            raise BundleError("Expected private photo manifest is missing.")

        for info in entries:
            name = info.filename
            if (info.is_dir() or name.startswith(".") or "\\" in name or
                "/" in name or PurePosixPath(name).name != name or
                name in (".", "..") or len(name) > 160):
                raise BundleError("Path traversal, directory or unexpected ZIP member.")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise BundleError("ZIP contains a symbolic link.")
            if info.flag_bits & 0x1:
                raise BundleError("Encrypted ZIP entries cannot be checked.")
            if info.file_size > 4 * 1024 * 1024:
                raise BundleError("ZIP member is oversized.")
            if info.compress_size and info.file_size / info.compress_size > 150:
                raise BundleError("Suspicious ZIP expansion ratio.")

        raw_manifest = zf.read(MANIFEST)
        if len(raw_manifest) > 100 * 1024:
            raise BundleError("Private manifest is oversized.")
        manifest = json.loads(raw_manifest)
        if not isinstance(manifest, list) or len(manifest) != EXPECTED_PHOTOS:
            raise BundleError("Expected exactly 23 manifest records.")
        # Detect duplicate manifest filenames before any byte comparisons, so a
        # reused photo cannot hide behind a misleading first SHA mismatch.
        manifest_names = [record.get("file") for record in manifest
                          if isinstance(record, dict) and isinstance(record.get("file"), str)]
        if len(manifest_names) != len(set(manifest_names)):
            raise BundleError("Duplicate WebP inventory record.")
        groups = {name: 0 for name in EXPECTED_GROUPS}
        seen = set()
        for item in manifest:
            if (not isinstance(item, dict) or set(item) != {"group", "file", "bytes", "sha256"} or
                item["group"] not in groups or
                not isinstance(item["file"], str) or
                not item["file"].lower().endswith(".webp") or
                not isinstance(item["bytes"], int) or isinstance(item["bytes"], bool) or
                not 1000 <= item["bytes"] <= 4 * 1024 * 1024 or
                not isinstance(item["sha256"], str) or
                not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])):
                raise BundleError("Malformed private WebP inventory record.")
            filename = item["file"]
            if filename in seen or filename not in names:
                raise BundleError("Missing or duplicate WebP inventory record.")
            seen.add(filename)
            groups[item["group"]] += 1
            info = zf.getinfo(filename)
            if info.file_size != item["bytes"]:
                raise BundleError("Photo byte count differs from verified manifest.")
            digest = hashlib.sha256()
            header = b""
            with zf.open(info, "r") as file:
                while True:
                    block = file.read(64 * 1024)
                    if not block:
                        break
                    if len(header) < 12:
                        header = (header + block)[:12]
                    digest.update(block)
            if not (header[:4] == b"RIFF" and header[8:12] == b"WEBP"):
                raise BundleError("File does not have a WebP signature.")
            if digest.hexdigest() != item["sha256"]:
                raise BundleError("A genuine EZ WebP file differs from its recorded SHA-256.")

        if seen != (set(names) - {MANIFEST}) or groups != EXPECTED_GROUPS:
            raise BundleError("WebP package groups or file inventory do not match.")

    return {
        "status": "EZ2_PRIVATE_WEBP_BUNDLE_VERIFIED",
        "photos": EXPECTED_PHOTOS,
        "core": groups["core"],
        "gallery_expansion": groups["gallery_expansion"],
        "files_imported": 0,
        "public_upload_authorized": False,
        "no_media_contents_logged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only audit of Owner's private EZ2 WebP ZIP")
    parser.add_argument("--zip", type=Path, required=True, help="Local private ZIP path")
    args = parser.parse_args()
    try:
        print(json.dumps(verify_bundle(args.zip), sort_keys=True))
        return 0
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, BundleError) as exc:
        print("EZ2_PRIVATE_WEBP_BUNDLE_HOLD: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
