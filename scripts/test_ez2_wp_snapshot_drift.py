"""Synthetic-only regression of EZ2 WordPress managed digest drift."""
import copy
from ez2_wp_snapshot_drift import compare

def snapshot():
    return {"schema_version": 1, "status": "MANAGED_CONTENT_DIGESTS_COLLECTED",
            "mode": "read-only", "target_site": "ez2-isolated-only",
            "runtime_gate_passed": True, "managed_count": 1,
            "entries": [{"key": "ez2-home-hero", "post_id": 12, "post_status": "draft",
                         "content_sha256": "a" * 64, "elementor_data_sha256": "b" * 64}],
            "private_content_emitted": False, "installed_release_attested": False,
            "localwp_verified": False, "owner_edit_baseline_trusted": False,
            "deployment_authorized": False, "applied": False}

def reject(a, b):
    global cases
    try:
        compare(a, b)
    except (ValueError, TypeError):
        cases += 1
        return
    raise AssertionError("Unsafe snapshot accepted")

cases = 0
original = snapshot()
assert compare(original, original)["status"] == "NO_CONTENT_DRIFT_UNTRUSTED_BASELINE"
assert compare(original, original)["can_apply"] is False
cases += 1
for patch, kind in [
    ({"content_sha256": "c" * 64}, "page_metadata_or_settings_changed"),
    ({"content_sha256": "c" * 64, "elementor_data_sha256": "d" * 64}, "elementor_and_page_changed"),
    ({"elementor_data_sha256": "d" * 64}, "elementor_digest_inconsistent"),
    ({"post_id": 14}, "managed_identity_changed"),
    ({"post_status": "publish"}, "post_status_inconsistent"),
]:
    changed = copy.deepcopy(original)
    changed["entries"][0].update(patch)
    report = compare(original, changed)
    assert report["status"] == "CONTENT_DRIFT_BLOCKED"
    assert report["changes"][0]["kind"] == kind
    assert report["change_count"] == 1 and not report["baseline_attested"]
    cases += 1
empty = copy.deepcopy(original)
empty.update(entries=[], managed_count=0, status="NO_MANAGED_PAGES")
assert compare(original, empty)["changes"][0]["kind"] == "missing_since_observation"
assert compare(empty, original)["changes"][0]["kind"] == "added_since_observation"
cases += 2
for field, value in [
    ("target_site", "ez-bns-new-dev.local"), ("mode", "write"),
    ("runtime_gate_passed", False), ("private_content_emitted", True),
    ("installed_release_attested", True), ("localwp_verified", True),
    ("owner_edit_baseline_trusted", True), ("deployment_authorized", True),
    ("applied", True), ("managed_count", True), ("status", "READY_FOR_INSTALL"),
    ("schema_version", True),
]:
    bad = copy.deepcopy(original)
    bad[field] = value
    reject(original, bad)
for patch in [
    {"key": "../../secret"}, {"key": "ez2-duplicate", "post_id": True},
    {"post_status": "inherit"}, {"content_sha256": "wrong"},
    {"elementor_data_sha256": "x" * 64}, {"post_id": 0},
]:
    bad = copy.deepcopy(original)
    bad["entries"][0].update(patch)
    reject(original, bad)
for mutation in [
    lambda s: s.update(unexpected="private"),
    lambda s: s["entries"][0].update(raw_content="secret"),
    lambda s: s["entries"].append(copy.deepcopy(s["entries"][0])),
    lambda s: s.update(managed_count=2),
]:
    bad = copy.deepcopy(original)
    mutation(bad)
    reject(original, bad)
assert cases == 30, cases
print(f"EZ2_WP_SNAPSHOT_DRIFT_PASS cases={cases} read_only=true baseline_attested=false")
