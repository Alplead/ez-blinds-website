"""Offline checkpoint-to-candidate file-swap and exact rollback tests.

All fixtures are synthetic; no LocalWP, real WordPress, network, or private data.
"""
import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path

from ez2_backup_snapshot_pack import pack
from ez2_checkpoint_upgrade_rehearsal import PHASES, rehearse
from ez2_content_candidate_bundle import package
from ez2_release_set import run as release_set

INSTALLED = "b" * 40
CANDIDATE = "a" * 40
CASES = 0


def zip_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return stream.getvalue()


def release(root, sha, marker):
    root.mkdir()
    archives = {
        "ezb-theme.zip": zip_bytes([
            ("ezb-theme/style.css", ("Theme Name: EZB " + marker).encode()),
            ("ezb-theme/theme.json", b"{}")]),
        "ezb-core.zip": zip_bytes([
            ("ezb-core/ezb-core.php", ("<?php // " + marker).encode())]),
    }
    for name, data in archives.items():
        (root / name).write_bytes(data)
    (root / "RELEASE_METADATA.txt").write_text("commit=" + sha + "\nmedia_included=no\n")
    (root / "RELEASE_CONTENTS.json").write_text(json.dumps({
        "schema_version": 1, "commit": sha, "delivery_scope": "theme-and-core-only",
        "archives": [
            {"name": name, "install_path": ("wp-content/themes/ezb-theme" if name == "ezb-theme.zip"
                                          else "wp-content/plugins/ezb-core"),
             "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in archives.items()],
        "includes": {key: False for key in (
            "third_party_plugins", "elementor_templates",
            "wordpress_content", "media", "database")},
        "localwp_installed": False, "owner_visual_acceptance": False,
    }))
    names = ("ezb-theme.zip", "ezb-core.zip", "RELEASE_METADATA.txt", "RELEASE_CONTENTS.json")
    (root / "SHA256SUMS").write_text("".join(
        hashlib.sha256((root / name).read_bytes()).hexdigest() + "  " + name + "\n"
        for name in names))
    content = {
        "title": "Synthetic home", "type": "page", "version": "4.3.4",
        "page_settings": {}, "content": [
            {"id": "deadbeef", "elType": "container",
             "settings": {"background_slideshow_gallery": [
                 {"url": "ez2-media://home-hero-" + n}
                 for n in ("one", "two", "three", "four")]},
             "elements": []}],
    }
    (root / "ez2-content-candidate.zip").write_bytes(
        package(sha, json.dumps(content).encode()))
    release_set("build", root, sha)
    return root


def fixture(base):
    installed = release(base / "installed", INSTALLED, "old")
    candidate = release(base / "candidate", CANDIDATE, "new")
    source = base / "snapshot"
    source.mkdir()
    (source / "database.sql").write_bytes(b"-- synthetic SQL only\nCREATE TABLE test(id INT);\n")
    for name in ("theme", "plugins", "uploads"):
        (source / name).mkdir()
    for filename, category in (("ezb-theme.zip", "theme"), ("ezb-core.zip", "plugins")):
        with zipfile.ZipFile(installed / filename) as archive:
            archive.extractall(source / category)
    (source / "plugins" / "third-party").mkdir()
    (source / "plugins" / "third-party" / "fixture.txt").write_bytes(b"synthetic unrelated plugin")
    (source / "uploads" / "synthetic.webp").write_bytes(b"synthetic private-media placeholder")
    backup = base / "private-backup"
    pack(source, backup, INSTALLED)
    return candidate, installed, backup


def reject(action):
    global CASES
    try:
        action()
    except (ValueError, OSError):
        CASES += 1
        return
    raise AssertionError("Unsafe scratch rehearsal accepted")


with tempfile.TemporaryDirectory() as temp:
    candidate, installed, backup = fixture(Path(temp))
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in backup.iterdir() if p.is_file()}
    result = rehearse(candidate, installed, backup, INSTALLED, CANDIDATE)
    assert result["status"] == "PRIVATE_BACKUP_CANDIDATE_SCRATCH_UPGRADE_ROLLBACK_VERIFIED_ONLY"
    assert result["scratch_candidate_swap_rehearsed"] and result["scratch_original_bytes_restored"]
    assert result["private_backup_unchanged"] and result["restored_private_files"] >= 5
    assert not any(result[key] for key in ("database_sql_executed",
        "database_restore_rehearsed", "wordpress_installed", "localwp_touched",
        "deployment_authorized", "can_apply", "one_click_complete"))
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in backup.iterdir() if p.is_file()}
    CASES += 1
    for phase in PHASES:
        fault = rehearse(candidate, installed, backup, INSTALLED, CANDIDATE,
                         fault_phase=phase)
        assert fault["fault_injected"] and fault["fault_phase"] == phase
        assert fault["scratch_original_bytes_restored"]
        CASES += 1

with tempfile.TemporaryDirectory() as temp:
    candidate, installed, backup = fixture(Path(temp))
    reject(lambda: rehearse(candidate, installed, backup, CANDIDATE, CANDIDATE))
    reject(lambda: rehearse(candidate, installed, backup, "wrong", CANDIDATE))
    reject(lambda: rehearse(candidate, installed, backup, INSTALLED, CANDIDATE,
                             fault_phase="not-a-fault"))
    (backup / "uploads.tar.gz").write_bytes(b"corrupt")
    reject(lambda: rehearse(candidate, installed, backup, INSTALLED, CANDIDATE))

with tempfile.TemporaryDirectory() as temp:
    candidate, installed, backup = fixture(Path(temp))
    (candidate / "ezb-theme.zip").write_bytes(b"corrupt")
    reject(lambda: rehearse(candidate, installed, backup, INSTALLED, CANDIDATE))

with tempfile.TemporaryDirectory() as temp:
    candidate, installed, backup = fixture(Path(temp))
    (installed / "ezb-core.zip").write_bytes(b"corrupt")
    reject(lambda: rehearse(candidate, installed, backup, INSTALLED, CANDIDATE))

with tempfile.TemporaryDirectory() as temp:
    candidate, installed, backup = fixture(Path(temp))
    bad = Path(temp) / "linked-backup"
    bad.symlink_to(backup, target_is_directory=True)
    reject(lambda: rehearse(candidate, installed, bad, INSTALLED, CANDIDATE))

assert CASES == 13, CASES
print(f"EZ2_CHECKPOINT_CANDIDATE_SCRATCH_ROLLBACK_PASS cases={CASES} "
      "private_backup_unchanged=true localwp_touched=false can_apply=false")
