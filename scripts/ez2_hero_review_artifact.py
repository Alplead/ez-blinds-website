#!/usr/bin/env python3
"""Build/verify an exact-head, NON-DEPLOYABLE Elementor hero review artifact.

No private media, mapping, plugins, database or WordPress writes are permitted.
"""
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from ez2_home_candidate_check import check as check_candidate
from ez2_elementor_export_check import unique, reject_nonfinite

SHA = re.compile(r"[0-9a-f]{40}\\Z")
TEMPLATE = "design/ez2-home-hero-candidate.json"
METADATA = "CANDIDATE_METADATA.json"
MAX_BYTES = 256000


def validate_candidate(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("Missing or oversized candidate")
    doc = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                     parse_constant=reject_nonfinite)
    result = check_candidate(doc)
    if result["status"] != "UNPUBLISHED_CANDIDATE_PREFLIGHT_ONLY":
        raise ValueError("Candidate is not review-only")
    return result


def metadata(raw, commit):
    if not isinstance(commit, str) or not SHA.fullmatch(commit):
        raise ValueError("Exact commit SHA required")
    result = validate_candidate(raw)
    return {
        "schema_version": 1, "source_sha": commit,
        "scope": "unpublished-elementor-hero-review-only",
        "template": TEMPLATE,
        "template_sha256": hashlib.sha256(raw).hexdigest(),
        "media_slots": result["media_slots"],
        "media_bytes_included": False,
        "private_media_map_included": False,
        "plugins_included": False,
        "wordpress_content_included": False,
        "database_included": False,
        "localwp_installed": False,
        "owner_design_approved": False,
        "deployment_authorized": False,
    }


def pack(raw, commit, target):
    meta = metadata(raw, commit)
    target = Path(target)
    if target.is_symlink() or target.exists() or not target.parent.is_dir():
        raise ValueError("Artifact destination must be a new file")
    payload = (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode()
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(TEMPLATE, raw)
        archive.writestr(METADATA, payload)
    return meta


def verify(path, expected_sha):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError("Unsafe artifact")
    if not isinstance(expected_sha, str) or not SHA.fullmatch(expected_sha):
        raise ValueError("Invalid expected SHA")
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.namelist() != [TEMPLATE, METADATA]:
                raise ValueError("Unexpected archive members or order")
            if any(info.is_dir() or info.flag_bits & 1 or info.file_size > MAX_BYTES
                   for info in archive.infolist()):
                raise ValueError("Unsafe archive entry")
            if archive.testzip() is not None:
                raise ValueError("Corrupt archive")
            raw = archive.read(TEMPLATE)
            record = json.loads(archive.read(METADATA).decode(),
                                object_pairs_hook=unique, parse_constant=reject_nonfinite)
    except (zipfile.BadZipFile, RuntimeError, UnicodeError) as exc:
        raise ValueError("Invalid ZIP archive") from exc
    expected = metadata(raw, expected_sha)
    if record != expected:
        raise ValueError("Artifact metadata mismatch")
    return {"status": "UNPUBLISHED_REVIEW_ARTIFACT_VERIFIED",
            "source_sha": expected_sha, "template_sha256": expected["template_sha256"],
            "media_bytes_included": False, "localwp_installed": False,
            "deployment_authorized": False}


def main(args):
    if len(args) != 4:
        raise ValueError("Usage: ez2_hero_review_artifact.py CANDIDATE.json EXACT_SHA NEW_OUTPUT.zip")
    source, commit, target = Path(args[1]), args[2], Path(args[3])
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_BYTES:
        raise ValueError("Unsafe candidate file")
    repo = Path(__file__).resolve().parents[1]
    if source.resolve() != repo / TEMPLATE:
        raise ValueError("Only the tracked public-safe candidate may be packaged")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    if actual != commit:
        raise ValueError("Git HEAD differs from expected SHA")
    committed = subprocess.check_output(["git", "show", f"HEAD:{TEMPLATE}"], cwd=repo)
    raw = source.read_bytes()
    if raw != committed:
        raise ValueError("Candidate differs from committed HEAD")
    pack(raw, commit, target)
    print(json.dumps(verify(target, commit), sort_keys=True))


if __name__ == "__main__":
    try:
        main(sys.argv)
    except (OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError) as exc:
        print("EZ2_HERO_REVIEW_ARTIFACT_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
