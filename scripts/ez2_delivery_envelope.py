#!/usr/bin/env python3
"""Deterministic public-safe EZ2 delivery envelope for a future isolated updater.

Combines first-party ZIPs, an unpublished Elementor review candidate and a
checksum-pinned official plugin dependency manifest. It NEVER installs content,
bundles third-party code or private media, or grants LocalWP publication rights.
"""
import hashlib
import io
import json
import re
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

from ez2_content_candidate_bundle import NAME, verify as verify_candidate
from ez2_elementor_export_check import unique, reject_nonfinite
from ez2_plugin_dependency_check import check as check_plugins
from ez2_release_set import CATALOG, COMPONENTS, run as verify_release, safe_read

OUT_NAME = "EZ2_DELIVERY_ENVELOPE.zip"
DEPENDENCY = "dependency/elementor-pinned.json"
MANIFEST = "EZ2_ENVELOPE_MANIFEST.json"
FILES = tuple("release/" + name for name in (*COMPONENTS, CATALOG)) + (DEPENDENCY,)
MAX_BYTES = 64 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{40}\Z")


def json_read(raw):
    return json.loads(raw, object_pairs_hook=unique, parse_constant=reject_nonfinite)


def validate_payload(files, sha):
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise ValueError("Invalid exact source SHA")
    if set(files) != set(FILES):
        raise ValueError("Incomplete or unexpected delivery components")
    lock = json_read(files[DEPENDENCY])
    checked = check_plugins(lock)
    plugins = lock["plugins"]
    if (len(plugins) != 1 or plugins[0]["slug"] != "elementor"
            or checked["missing_checksums"] or checked["status"] != "METADATA_ONLY"):
        raise ValueError("Pinned Elementor Free dependency required")
    candidate = files["release/ez2-content-candidate.zip"]
    verified = verify_candidate(sha, candidate)
    if verified.get("source_sha") != sha or verified.get("scope") != "public-review-candidate-only":
        raise ValueError("Unapproved Elementor content candidate")
    with zipfile.ZipFile(io.BytesIO(candidate)) as z:
        content = json_read(z.read(NAME))
    if content.get("version") != plugins[0]["version"]:
        raise ValueError("Elementor candidate version differs from pinned dependency")
    with tempfile.TemporaryDirectory(prefix="ez2-public-envelope-") as temp:
        root = Path(temp)
        for name in (*COMPONENTS, CATALOG):
            (root / name).write_bytes(files["release/" + name])
        catalog = verify_release("verify", root, sha)
        if (catalog.get("source_sha") != sha
                or catalog.get("target_site") != "ez2-isolated-only"
                or catalog.get("scope") != "engineering-evidence-only"
                or catalog.get("deployment_authorized") is not False):
            raise ValueError("Unsafe release catalog")
    return {
        "schema_version": 1,
        "source_sha": sha,
        "target_site": "ez2-isolated-only",
        "scope": "engineering-evidence-only",
        "files": [{"name": name, "sha256": hashlib.sha256(files[name]).hexdigest(),
                   "size": len(files[name])} for name in FILES],
        "elementor_version": plugins[0]["version"],
        "third_party_plugin_bytes_included": False,
        "private_media_included": False,
        "content_published": False,
        "localwp_installed": False,
        "one_click_complete": False,
        "can_apply": False,
        "deployment_authorized": False,
    }


def encode(files, manifest):
    output = io.BytesIO()
    entries = [(name, files[name]) for name in FILES]
    entries.append((MANIFEST, (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()))
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in entries:
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output.getvalue()


def verify_bytes(raw, sha):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("Unsafe envelope size")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) != len(FILES) + 1 or {i.filename for i in infos} != set(FILES) | {MANIFEST}:
                raise ValueError("Unexpected or duplicate envelope members")
            if (any(i.is_dir() or i.flag_bits & 1
                    or stat.S_IFMT(i.external_attr >> 16) not in (0, stat.S_IFREG)
                    or i.file_size > MAX_BYTES for i in infos)
                    or sum(i.file_size for i in infos) > MAX_BYTES
                    or archive.testzip() is not None):
                raise ValueError("Unsafe envelope member")
            files = {name: archive.read(name) for name in FILES}
            declared = json_read(archive.read(MANIFEST))
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError("Unreadable envelope") from exc
    expected = validate_payload(files, sha)
    if declared != expected or encode(files, expected) != raw:
        raise ValueError("Non-canonical, mismatched or tampered envelope")
    return {"status": "EZ2_PUBLIC_DELIVERY_ENVELOPE_VERIFIED_ONLY",
            "source_sha": sha, "component_count": len(FILES),
            "one_click_complete": False, "can_apply": False,
            "localwp_installed": False, "deployment_authorized": False}


def build(release_dir, sha, plugin_lock, output):
    root = Path(release_dir)
    lock = Path(plugin_lock)
    destination = Path(output)
    if (root.is_symlink() or not root.is_dir() or lock.is_symlink()
            or not lock.is_file() or lock.stat().st_size > 32768
            or destination.name != OUT_NAME or destination.parent.resolve() != root.resolve()
            or destination.exists() or destination.is_symlink()):
        raise ValueError("Unsafe envelope build paths")
    files = {"release/" + name: safe_read(root, name) for name in (*COMPONENTS, CATALOG)}
    files[DEPENDENCY] = lock.read_bytes()
    manifest = validate_payload(files, sha)
    raw = encode(files, manifest)
    verify_bytes(raw, sha)
    with destination.open("xb") as output_file:
        output_file.write(raw)
    return verify_bytes(destination.read_bytes(), sha)


def main(argv):
    if len(argv) == 5 and argv[0] == "build":
        return build(*argv[1:])
    if len(argv) == 3 and argv[0] == "verify":
        file = Path(argv[1])
        if file.is_symlink() or not file.is_file():
            raise ValueError("Unsafe envelope file")
        return verify_bytes(file.read_bytes(), argv[2])
    raise ValueError("Usage: build RELEASE_DIR SHA PLUGIN_LOCK OUTPUT | verify ZIP SHA")


if __name__ == "__main__":
    try:
        result = main(sys.argv[1:])
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("EZ2_DELIVERY_ENVELOPE_FAIL: " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
