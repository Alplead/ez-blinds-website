#!/usr/bin/env python3
"""Read-only link from an exact-head EZ2 release to a protected delivery plan.

NOT a WordPress installer, LocalWP sync tool or publication gate. No private
media, plugins or pages are installed, downloaded or uploaded by this script.
"""
import hashlib
import io
import json
import re
import stat
import sys
import zipfile
from pathlib import Path

from ez2_content_candidate_bundle import NAME, verify as verify_candidate
from ez2_content_guard import digest as content_digest, read as read_installed
from ez2_delivery_preflight import check as check_delivery
from ez2_elementor_export_check import check as check_elementor, unique, reject_nonfinite
from ez2_plugin_dependency_check import read as read_lock
from ez2_release_set import run as check_release, safe_read

COMMIT = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def regular_input(path, max_bytes):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Linked planning input refused")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= max_bytes:
        raise ValueError("Unsafe planning input")
    return path




def verify_prior_release(directory, previous_sha, incoming_sha):
    """Verify previous release bytes; never attest what LocalWP installed."""
    if (not isinstance(previous_sha, str) or not COMMIT.fullmatch(previous_sha)
            or previous_sha == incoming_sha):
        raise ValueError("Invalid or identical prior release SHA")
    root = Path(directory)
    catalog = check_release("verify", root, previous_sha)
    if (catalog.get("source_sha") != previous_sha
            or catalog.get("target_site") != "ez2-isolated-only"
            or catalog.get("scope") != "engineering-evidence-only"
            or catalog.get("deployment_authorized") is not False):
        raise ValueError("Prior release is not an isolated engineering candidate")
    raw = safe_read(root, "ez2-content-candidate.zip")
    manifest = verify_candidate(previous_sha, raw)
    if (manifest.get("source_sha") != previous_sha
            or manifest.get("scope") != "public-review-candidate-only"):
        raise ValueError("Prior candidate scope or SHA mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        candidate = json.loads(archive.read(NAME), object_pairs_hook=unique,
                               parse_constant=reject_nonfinite)
    check_elementor(candidate)
    return {
        "source_sha": previous_sha,
        "managed_key": "ez2-home-hero",
        "content_sha256": content_digest(candidate),
        "candidate_archive_sha256": hashlib.sha256(raw).hexdigest(),
        "release_catalog_sha256": hashlib.sha256(
            safe_read(root, "EZ2_RELEASE_SET.json")).hexdigest(),
        "installed_site_attested": False,
    }


def transaction_preview(catalog, lock, installed, candidate, result, exact_sha, previous_digest, prior_proof):
    """Bind a reproducible, non-executable transaction preview to verified inputs.

    A future isolated-site agent must re-read the live site and verify every
    prerequisite; this evidence is deliberately NOT an installation permit.
    """
    import hashlib

    phases = [
        {"id": "verify_isolated_site_and_exact_head", "mode": "read-only"},
        {"id": "verify_official_plugin_archive", "mode": "required-before-write"},
        {"id": "backup_database_uploads_theme_and_plugins", "mode": "required-before-write"},
        {"id": "stage_verified_theme_core_and_elementor", "mode": "required-before-write"},
        {"id": "resolve_private_media_on_isolated_site", "mode": "required-before-write"},
        {"id": "apply_only_unmodified_managed_content", "mode": "requires-owner-confirmation"},
        {"id": "verify_wordpress_and_frontend", "mode": "required-after-write"},
        {"id": "commit_or_restore_full_backup", "mode": "rollback-on-any-failure"},
    ]
    blockers = [
        "isolated_localwp_site_identity_unverified",
        "official_elementor_archive_not_verified_for_localwp",
        "full_site_backup_and_restore_not_verified_on_localwp",
        "private_media_mapping_not_verified_on_localwp",
        "owner_delivery_and_publication_authorization_absent",
        "owner_content_baseline_not_independently_attested",
    ]
    if result["content"]["conflict_count"]:
        blockers.append("owner_modified_content_conflict")
    if any(action["action"] == "update" for action in result["content"]["actions"]) and prior_proof is None:
        blockers.append("unattested_previous_content_baseline")
    if prior_proof is not None:
        blockers.append("prior_release_not_attested_as_installed_on_localwp")
    if result["missing_plugin_checksums"]:
        blockers.append("missing_official_plugin_checksum")
    if result["unresolved_media_slots"]:
        blockers.append("unregistered_symbolic_media_slot")
    binding = {
        "source_sha": exact_sha,
        "target_site": "ez2-isolated-only",
        "release_catalog": catalog,
        "plugin_lock": lock,
        "installed_snapshot": installed,
        "candidate": candidate,
        "previous_digest_untrusted": previous_digest if prior_proof is None else None,
        "verified_prior_release_candidate": prior_proof,
        "content_actions": result["content"]["actions"],
        "phases": phases,
    }
    raw = json.dumps(binding, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return {
        "schema_version": 1,
        "kind": "exact-head-read-only-transaction-preview",
        "source_sha": exact_sha,
        "target_site": "ez2-isolated-only",
        "input_binding_sha256": hashlib.sha256(raw).hexdigest(),
        "phases": phases,
        "blocking_gates": blockers,
        "preflight_status": result["status"],
        "previous_baseline_trusted": False,
        "prior_release_candidate_verified": prior_proof is not None,
        "can_apply": False,
        "applied": False,
        "localwp_touched": False,
        "one_click_complete": False,
    }


def plan(release_dir, exact_sha, plugin_lock, installed_snapshot, previous_digest=None,
         prior_release_dir=None, prior_release_sha=None):
    if previous_digest is not None and (
            not isinstance(previous_digest, str) or not SHA256.fullmatch(previous_digest)):
        raise ValueError("Invalid previous managed-content digest")
    if (prior_release_dir is None) != (prior_release_sha is None):
        raise ValueError("Prior release directory and SHA must be supplied together")
    if prior_release_dir is not None and previous_digest is not None:
        raise ValueError("Do not mix untrusted digest with verified prior release")
    prior_proof = (verify_prior_release(prior_release_dir, prior_release_sha, exact_sha)
                   if prior_release_dir is not None else None)
    if prior_proof is not None:
        previous_digest = prior_proof["content_sha256"]
    release_dir = Path(release_dir)
    catalog = check_release("verify", release_dir, exact_sha)
    for key, expected in (
            ("source_sha", exact_sha),
            ("target_site", "ez2-isolated-only"),
            ("scope", "engineering-evidence-only"),
            ("one_click_complete", False),
            ("elementor_candidate_installable", False),
            ("third_party_plugins_included", False),
            ("private_media_included", False),
            ("localwp_installed", False),
            ("deployment_authorized", False)):
        if catalog.get(key) != expected or (isinstance(expected, bool)
                                             and catalog.get(key) is not expected):
            raise ValueError("Unsafe release catalog: " + key)
    raw = safe_read(release_dir, "ez2-content-candidate.zip")
    manifest = verify_candidate(exact_sha, raw)
    if manifest.get("source_sha") != exact_sha or manifest.get("scope") != "public-review-candidate-only":
        raise ValueError("Wrong candidate source or publication scope")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        candidate = json.loads(archive.read(NAME), object_pairs_hook=unique,
                               parse_constant=reject_nonfinite)
    summary = check_elementor(candidate)
    lock = read_lock(regular_input(plugin_lock, 32768))
    if len(lock.get("plugins", [])) != 1 or lock["plugins"][0].get("slug") != "elementor":
        raise ValueError("Only approved Elementor Free evaluation is supported")
    if lock["plugins"][0].get("version") != candidate["version"]:
        raise ValueError("Pinned Elementor version differs from release candidate")
    installed = read_installed(regular_input(installed_snapshot, 32768))
    contract = {
        "schema_version": 1,
        "target_site": "ez2-isolated-only",
        "source_sha": exact_sha,
        "plugin_lock": "plugins.json",
        "templates": [{
            "key": "ez2-home-hero",
            "file": "home-hero.json",
            "previous_sha256": previous_digest,
        }],
        "media_slots": summary["media_slots"],
    }
    result = check_delivery(contract, installed, lock, {"home-hero.json": candidate}, exact_sha)
    # A caller-provided previous digest is not proof of the prior trusted release.
    # Preserve the proposed update action for review, but do not call it ready
    # until a future isolated-site agent independently attests that baseline.
    if (prior_proof is None and any(action["action"] == "update"
                                    for action in result["content"]["actions"])):
        result = {**result, "status": "BLOCKED_PREFLIGHT"}
    return {
        "status": result["status"],
        "source_sha": exact_sha,
        "target_site": "ez2-isolated-only",
        "release_catalog_verified": True,
        "prior_release_baseline": prior_proof,
        "installed_site_baseline_attested": False,
        "candidate_archive_verified": True,
        "elementor_version_pinned": candidate["version"],
        "plugin_status": result["plugin_status"],
        "missing_plugin_checksums": result["missing_plugin_checksums"],
        "content": result["content"],
        "symbolic_media_slots": summary["media_slots"],
        "unresolved_media_slots": result["unresolved_media_slots"],
        "media_mapping_verified_on_localwp": False,
        "plugin_archive_verified": False,
        "wordpress_runtime_verified": False,
        "restore_rehearsed_on_localwp": False,
        "one_click_complete": False,
        "localwp_installed": False,
        "deployment_authorized": False,
        "applied": False,
        "transaction_preview": transaction_preview(catalog, lock, installed, candidate,
                                                    result, exact_sha, previous_digest, prior_proof),
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) not in (5, 6, 8):
            raise ValueError("Usage: ez2_release_delivery_bridge.py RELEASE_DIR EXACT_SHA PLUGIN_LOCK INSTALLED_SNAPSHOT [PREVIOUS_SHA256|- | --prior-release PRIOR_DIR PRIOR_SHA]")
        if len(sys.argv) == 8:
            if sys.argv[5] != "--prior-release":
                raise ValueError("Invalid prior-release option")
            result = plan(*sys.argv[1:5], prior_release_dir=sys.argv[6],
                          prior_release_sha=sys.argv[7])
        else:
            previous = None if len(sys.argv) == 5 or sys.argv[5] == "-" else sys.argv[5]
            result = plan(*sys.argv[1:5], previous)
        print(json.dumps(result, sort_keys=True))
        sys.exit(2 if result["status"] == "BLOCKED_PREFLIGHT" else 0)
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        print("EZ2_RELEASE_DELIVERY_BRIDGE_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
