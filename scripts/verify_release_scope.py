#!/usr/bin/env python3
"""Read-only exact-head verification for the theme/core-only EZB release.

Not an installer or evidence of EZ2 A-scheme full-site delivery.
"""
import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import Path

ARCHIVES = {
    "ezb-theme.zip": "wp-content/themes/ezb-theme",
    "ezb-core.zip": "wp-content/plugins/ezb-core",
}
EXCLUDED = {"third_party_plugins", "elementor_templates", "wordpress_content", "media", "database"}



def check_archive(file: Path, name: str) -> None:
    """Reject ZIP entries that could escape or corrupt a LocalWP installation.

    Checks are structural, not a signature or a claim of actual LP deployment.
    """
    root_name = name.removesuffix(".zip")
    required = {
        "ezb-theme.zip": {"ezb-theme/style.css", "ezb-theme/theme.json"},
        "ezb-core.zip": {"ezb-core/ezb-core.php"},
    }[name]
    try:
        with zipfile.ZipFile(file) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > 512:
                raise ValueError("Unsafe ZIP entry count")
            seen = set()
            regular_files = set()
            total_size = 0
            for entry in entries:
                raw = entry.filename
                is_dir = entry.is_dir()
                if (not raw or raw.startswith("/") or "\\" in raw
                        or any(ord(ch) < 32 for ch in raw)):
                    raise ValueError("Unsafe ZIP entry name")
                parts = raw.rstrip("/").split("/")
                if (parts[0] != root_name or any(p in ("", ".", "..") for p in parts)
                        or (not is_dir and len(parts) < 2)):
                    raise ValueError("ZIP entry outside expected plugin/theme root")
                folded = raw.rstrip("/").casefold()
                if folded in seen:
                    raise ValueError("Duplicate or case-colliding ZIP path")
                seen.add(folded)
                mode_type = stat.S_IFMT(entry.external_attr >> 16)
                if mode_type not in (0, stat.S_IFDIR if is_dir else stat.S_IFREG):
                    raise ValueError("ZIP symlink or special file")
                if entry.flag_bits & 1:
                    raise ValueError("Encrypted ZIP entry")
                total_size += entry.file_size
                if entry.file_size > 8 * 1024 * 1024 or total_size > 32 * 1024 * 1024:
                    raise ValueError("ZIP exceeds safe uncompressed size")
                if (any(p.casefold() in {".git", ".env", "uploads", "node_modules", "vendor"} for p in parts)
                        or parts[-1].casefold() == "wp-config.php"
                        or parts[-1].casefold().endswith((".sql", ".wpress"))):
                    raise ValueError("Private or forbidden ZIP path")
                if not is_dir:
                    regular_files.add(raw)
            if not required.issubset(regular_files):
                raise ValueError("Required plugin/theme files missing from ZIP")
            if archive.testzip() is not None:
                raise ValueError("ZIP member failed CRC verification")
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError("Unreadable or unsupported ZIP archive") from exc


def check(directory: Path, expected_sha: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("Invalid exact SHA")
    root = directory.resolve(strict=True)
    manifest = root / "RELEASE_CONTENTS.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Missing or symlinked release manifest")
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    fields = {"schema_version", "commit", "delivery_scope", "archives", "includes",
              "localwp_installed", "owner_visual_acceptance"}
    if not isinstance(doc, dict) or set(doc) != fields:
        raise ValueError("Unexpected manifest schema")
    if doc["schema_version"] != 1 or doc["commit"] != expected_sha:
        raise ValueError("Release SHA/schema mismatch")
    if doc["delivery_scope"] != "theme-and-core-only":
        raise ValueError("Unapproved full-site delivery claim")
    if doc["localwp_installed"] is not False or doc["owner_visual_acceptance"] is not False:
        raise ValueError("Unverified deployment or acceptance claim")
    includes = doc["includes"]
    if not isinstance(includes, dict) or set(includes) != EXCLUDED or any(v is not False for v in includes.values()):
        raise ValueError("Unverified content/plugin/media claim")
    archives = doc["archives"]
    if not isinstance(archives, list) or len(archives) != 2:
        raise ValueError("Expected exactly two first-party archives")
    seen = set()
    for item in archives:
        if not isinstance(item, dict) or set(item) != {"name", "install_path", "sha256"}:
            raise ValueError("Unexpected archive fields")
        name = item["name"]
        if name not in ARCHIVES or name in seen or item["install_path"] != ARCHIVES[name]:
            raise ValueError("Unexpected archive or installation destination")
        seen.add(name)
        file = root / name
        if file.is_symlink() or not file.is_file():
            raise ValueError("Missing or symlinked archive")
        if hashlib.sha256(file.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Archive digest mismatch")
        check_archive(file, name)
    if seen != set(ARCHIVES):
        raise ValueError("Incomplete archive inventory")
    metadata = root / "RELEASE_METADATA.txt"
    if metadata.is_symlink() or not metadata.is_file() or "commit=" + expected_sha not in metadata.read_text(encoding="utf-8").splitlines():
        raise ValueError("Release metadata SHA mismatch")
    sums = root / "SHA256SUMS"
    if sums.is_symlink() or not sums.is_file():
        raise ValueError("Missing checksum ledger")
    expected_files = set(ARCHIVES) | {"RELEASE_METADATA.txt", "RELEASE_CONTENTS.json"}
    lines = sums.read_text(encoding="utf-8").splitlines()
    if len(lines) != len(expected_files):
        raise ValueError("Unexpected checksum ledger entries")
    seen = set()
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if not match or match[2] not in expected_files or match[2] in seen:
            raise ValueError("Unsafe checksum ledger")
        seen.add(match[2])
        file = root / match[2]
        if file.is_symlink() or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != match[1]:
            raise ValueError("Checksum ledger mismatch")
    if seen != expected_files:
        raise ValueError("Incomplete checksum ledger")


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("Usage: verify_release_scope.py RELEASE_DIR EXACT_SHA")
        check(Path(sys.argv[1]), sys.argv[2])
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("EZB_RELEASE_SCOPE_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
    print("EZB_RELEASE_SCOPE_PASS")
