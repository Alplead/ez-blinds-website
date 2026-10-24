"""End-to-end synthetic release-to-delivery bridge regression; no site or network."""
import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path

from ez2_content_candidate_bundle import package
from ez2_content_guard import digest
from ez2_release_delivery_bridge import plan

SHA = "a" * 40
CASES = 0


def archive(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            z.writestr(name, data)
    return output.getvalue()


def template():
    return {
        "title": "Synthetic home", "type": "page", "version": "4.3.4",
        "page_settings": {}, "content": [{
            "id": "deadbeef", "elType": "container",
            "settings": {"background_slideshow_gallery": [
                {"url": "ez2-media://home-hero-" + n}
                for n in ("one", "two", "three", "four")]},
            "elements": [],
        }],
    }


def fixture(root):
    release = root / "release"
    release.mkdir()
    theme = archive([("ezb-theme/style.css", b"Theme Name: EZB Theme"),
                     ("ezb-theme/theme.json", b"{}")])
    core = archive([("ezb-core/ezb-core.php", b"<?php // synthetic")])
    (release / "ezb-theme.zip").write_bytes(theme)
    (release / "ezb-core.zip").write_bytes(core)
    (release / "RELEASE_METADATA.txt").write_text("commit=" + SHA + "\nmedia_included=no\n")
    manifest = {
        "schema_version": 1, "commit": SHA, "delivery_scope": "theme-and-core-only",
        "archives": [
            {"name": "ezb-theme.zip", "install_path": "wp-content/themes/ezb-theme",
             "sha256": hashlib.sha256(theme).hexdigest()},
            {"name": "ezb-core.zip", "install_path": "wp-content/plugins/ezb-core",
             "sha256": hashlib.sha256(core).hexdigest()},
        ],
        "includes": {key: False for key in (
            "third_party_plugins", "elementor_templates", "wordpress_content", "media", "database")},
        "localwp_installed": False, "owner_visual_acceptance": False,
    }
    (release / "RELEASE_CONTENTS.json").write_text(json.dumps(manifest))
    names = ("ezb-theme.zip", "ezb-core.zip", "RELEASE_METADATA.txt", "RELEASE_CONTENTS.json")
    (release / "SHA256SUMS").write_text("".join(
        hashlib.sha256((release / n).read_bytes()).hexdigest() + "  " + n + "\n" for n in names))
    (release / "ez2-content-candidate.zip").write_bytes(
        package(SHA, json.dumps(template()).encode()))
    from ez2_release_set import run
    run("build", release, SHA)
    lock = root / "plugins.json"
    lock.write_text(json.dumps({
        "schema_version": 1, "target_site": "ez2-isolated-only",
        "plugins": [{
            "slug": "elementor", "version": "4.3.4", "entrypoint": "elementor/elementor.php",
            "source": "wordpress.org", "archive_sha256": "b" * 64, "activate": True,
        }],
    }))
    installed = root / "installed.json"
    installed.write_text(json.dumps({"schema_version": 1, "items": []}))
    return release, lock, installed


def reject(action):
    global CASES
    try:
        action()
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile):
        CASES += 1
        return
    raise AssertionError("Unsafe release-to-delivery input accepted")


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    release, lock, installed = fixture(root)
    baseline = {p.name: p.read_bytes() for p in release.iterdir()}
    good = plan(release, SHA, lock, installed)
    assert good["status"] == "READY_FOR_RUNTIME_TEST_ONLY"
    assert good["release_catalog_verified"] and good["candidate_archive_verified"]
    assert good["content"]["actions"][0]["action"] == "create"
    assert len(good["symbolic_media_slots"]) == 4
    assert not good["applied"] and not good["one_click_complete"]
    assert not good["plugin_archive_verified"] and not good["localwp_installed"]
    preview = good["transaction_preview"]
    assert preview["source_sha"] == SHA and preview["target_site"] == "ez2-isolated-only"
    assert len(preview["phases"]) == 8 and preview["phases"][2]["id"] == "backup_database_uploads_theme_and_plugins"
    assert preview["phases"][-1]["id"] == "commit_or_restore_full_backup"
    assert preview["can_apply"] is False and preview["one_click_complete"] is False
    assert preview["previous_baseline_trusted"] is False and not preview["localwp_touched"]
    assert len(preview["input_binding_sha256"]) == 64
    CASES += 1
    assert good["transaction_preview"] == plan(release, SHA, lock, installed)["transaction_preview"]
    CASES += 1
    assert baseline == {p.name: p.read_bytes() for p in release.iterdir()}
    CASES += 1

    previous = digest(template())
    installed.write_text(json.dumps({"schema_version": 1, "items": [
        {"key": "ez2-home-hero", "current_sha256": previous}]}))
    unchanged = plan(release, SHA, lock, installed)
    assert unchanged["content"]["actions"][0]["action"] == "unchanged"
    assert unchanged["transaction_preview"]["input_binding_sha256"] != preview["input_binding_sha256"]
    CASES += 1
    CASES += 1
    installed.write_text(json.dumps({"schema_version": 1, "items": [
        {"key": "ez2-home-hero", "current_sha256": "c" * 64}]}))
    blocked = plan(release, SHA, lock, installed)
    assert blocked["status"] == "BLOCKED_PREFLIGHT"
    assert blocked["content"]["actions"][0]["action"] == "conflict_owner_edit"
    assert "owner_modified_content_conflict" in blocked["transaction_preview"]["blocking_gates"]
    assert blocked["transaction_preview"]["can_apply"] is False
    CASES += 1
    CASES += 1
    updated = plan(release, SHA, lock, installed, "c" * 64)
    assert updated["status"] == "BLOCKED_PREFLIGHT"
    assert updated["content"]["actions"][0]["action"] == "update"
    assert "unattested_previous_content_baseline" in updated["transaction_preview"]["blocking_gates"]
    CASES += 1
    assert updated["transaction_preview"]["preflight_status"] == "BLOCKED_PREFLIGHT"
    assert updated["transaction_preview"]["can_apply"] is False
    CASES += 1
    assert updated["transaction_preview"]["input_binding_sha256"] != blocked["transaction_preview"]["input_binding_sha256"]
    assert updated["transaction_preview"]["previous_baseline_trusted"] is False
    CASES += 1
    CASES += 1

    # Verify the previous managed digest against a separate exact-head release.
    prior_sha = "d" * 40
    prior_root = root / "prior"
    prior_root.mkdir()
    prior_release, _, _ = fixture(prior_root)
    prior_candidate = template()
    prior_candidate["title"] = "Prior synthetic home"
    (prior_release / "ez2-content-candidate.zip").write_bytes(
        package(prior_sha, json.dumps(prior_candidate).encode()))
    (prior_release / "RELEASE_METADATA.txt").write_text(
        "commit=" + prior_sha + "\nmedia_included=no\n")
    old_manifest = json.loads((prior_release / "RELEASE_CONTENTS.json").read_text())
    old_manifest["commit"] = prior_sha
    (prior_release / "RELEASE_CONTENTS.json").write_text(json.dumps(old_manifest))
    names = ("ezb-theme.zip", "ezb-core.zip", "RELEASE_METADATA.txt", "RELEASE_CONTENTS.json")
    (prior_release / "SHA256SUMS").write_text("".join(
        hashlib.sha256((prior_release / n).read_bytes()).hexdigest() + "  " + n + "\n"
        for n in names))
    (prior_release / "EZ2_RELEASE_SET.json").unlink()
    from ez2_release_set import run as verify_release_set
    verify_release_set("build", prior_release, prior_sha)
    prior_digest = digest(prior_candidate)
    installed.write_text(json.dumps({"schema_version": 1, "items": [
        {"key": "ez2-home-hero", "current_sha256": prior_digest}]}))
    proven = plan(release, SHA, lock, installed,
                  prior_release_dir=prior_release, prior_release_sha=prior_sha)
    assert proven["status"] == "READY_FOR_RUNTIME_TEST_ONLY"
    assert proven["content"]["actions"][0]["action"] == "update"
    assert proven["prior_release_baseline"]["content_sha256"] == prior_digest
    assert proven["prior_release_baseline"]["source_sha"] == prior_sha
    CASES += 1
    assert proven["transaction_preview"]["prior_release_candidate_verified"] is True
    assert proven["transaction_preview"]["previous_baseline_trusted"] is False
    assert proven["installed_site_baseline_attested"] is False
    assert "prior_release_not_attested_as_installed_on_localwp" in proven["transaction_preview"]["blocking_gates"]
    assert "unattested_previous_content_baseline" not in proven["transaction_preview"]["blocking_gates"]
    assert proven["transaction_preview"]["can_apply"] is False
    CASES += 1
    assert proven["transaction_preview"] == plan(
        release, SHA, lock, installed, prior_release_dir=prior_release,
        prior_release_sha=prior_sha)["transaction_preview"]
    CASES += 1
    reject(lambda: plan(release, SHA, lock, installed, prior_release_dir=prior_release))
    reject(lambda: plan(release, SHA, lock, installed, prior_release_sha=prior_sha))
    reject(lambda: plan(release, SHA, lock, installed,
                        prior_release_dir=prior_release, prior_release_sha=SHA))
    reject(lambda: plan(release, SHA, lock, installed, previous_digest=prior_digest,
                        prior_release_dir=prior_release, prior_release_sha=prior_sha))
    reject(lambda: plan(release, SHA, lock, installed,
                        prior_release_dir=prior_release, prior_release_sha="e" * 40))
    installed.write_text(json.dumps({"schema_version": 1, "items": [
        {"key": "ez2-home-hero", "current_sha256": "c" * 64}]}))
    changed = plan(release, SHA, lock, installed,
                   prior_release_dir=prior_release, prior_release_sha=prior_sha)
    assert changed["status"] == "BLOCKED_PREFLIGHT"
    assert changed["content"]["actions"][0]["action"] == "conflict_owner_edit"
    CASES += 1
    prior_raw = (prior_release / "ez2-content-candidate.zip").read_bytes()
    (prior_release / "ez2-content-candidate.zip").write_bytes(b"tampered")
    reject(lambda: plan(release, SHA, lock, installed,
                        prior_release_dir=prior_release, prior_release_sha=prior_sha))
    (prior_release / "ez2-content-candidate.zip").write_bytes(prior_raw)
    CASES += 1
    assert baseline == {p.name: p.read_bytes() for p in release.iterdir()}
    CASES += 1

    reject(lambda: plan(release, SHA, lock, installed, "invalid"))
    reject(lambda: plan(release, "f" * 40, lock, installed))
    original_lock = lock.read_text()
    lock.write_text(original_lock.replace("4.3.4", "4.3.5"))
    reject(lambda: plan(release, SHA, lock, installed))
    lock.write_text(original_lock.replace('"b' + "b" * 63 + '"', "null"))
    blocked = plan(release, SHA, lock, installed)
    assert blocked["status"] == "BLOCKED_PREFLIGHT"
    assert blocked["missing_plugin_checksums"] == ["elementor"]
    assert "missing_official_plugin_checksum" in blocked["transaction_preview"]["blocking_gates"]
    CASES += 1
    CASES += 1
    lock.write_text(original_lock)
    installed.write_text('{"schema_version":1,"items":[],"items":[]}')
    reject(lambda: plan(release, SHA, lock, installed))
    installed.unlink()
    installed.symlink_to(lock)
    reject(lambda: plan(release, SHA, lock, installed))
    installed.unlink()
    installed.write_text(json.dumps({"schema_version": 1, "items": []}))
    (release / "ez2-content-candidate.zip").write_bytes(b"tampered")
    reject(lambda: plan(release, SHA, lock, installed))
    assert CASES == 31, CASES
print(f"EZ2_RELEASE_DELIVERY_BRIDGE_PASS cases={CASES}")
