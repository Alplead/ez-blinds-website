#!/usr/bin/env python3
"""Read-only exact-head cross-artifact catalog; NOT an EZ2 installer."""
import hashlib
import json
import re
import sys
from pathlib import Path

from ez2_content_candidate_bundle import verify as verify_candidate
from ez2_elementor_export_check import unique, reject_nonfinite
from verify_release_scope import check as verify_release

COMPONENTS = (
    "ezb-theme.zip", "ezb-core.zip", "RELEASE_METADATA.txt",
    "RELEASE_CONTENTS.json", "SHA256SUMS", "ez2-content-candidate.zip",
)
CATALOG = "EZ2_RELEASE_SET.json"


def safe_read(root, name):
    path = root / name
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 32 * 1024 * 1024:
        raise ValueError("Missing, linked or oversized release component: " + name)
    return path.read_bytes()


def expected_catalog(root, sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid exact SHA")
    verify_release(root, sha)
    candidate = verify_candidate(sha, safe_read(root, "ez2-content-candidate.zip"))
    if candidate["source_sha"] != sha or candidate["scope"] != "public-review-candidate-only":
        raise ValueError("Candidate SHA or scope mismatch")
    return {
        "schema": 1,
        "source_sha": sha,
        "scope": "engineering-evidence-only",
        "target_site": "ez2-isolated-only",
        "files": [
            {"name": name, "sha256": hashlib.sha256(safe_read(root, name)).hexdigest()}
            for name in COMPONENTS
        ],
        "one_click_complete": False,
        "elementor_candidate_installable": False,
        "third_party_plugins_included": False,
        "private_media_included": False,
        "localwp_installed": False,
        "deployment_authorized": False,
    }


def canonical(doc):
    return (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")


def run(mode, directory, sha):
    if mode not in ("build", "verify"):
        raise ValueError("Invalid mode")
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Invalid release directory")
    root = root.resolve(strict=True)
    path = root / CATALOG
    if mode == "build":
        payload = canonical(expected_catalog(root, sha))
        # Never silently replace existing release evidence.
        with path.open("xb") as output:
            output.write(payload)
    raw = safe_read(root, CATALOG)
    doc = json.loads(raw, object_pairs_hook=unique, parse_constant=reject_nonfinite)
    if raw != canonical(doc) or doc != expected_catalog(root, sha):
        raise ValueError("Release-set catalog mismatch")
    return doc


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4:
            raise ValueError("Usage: ez2_release_set.py build|verify RELEASE_DIR EXACT_SHA")
        run(*sys.argv[1:])
        print("EZ2_RELEASE_SET_PASS one_click_complete=false")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print("EZ2_RELEASE_SET_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
