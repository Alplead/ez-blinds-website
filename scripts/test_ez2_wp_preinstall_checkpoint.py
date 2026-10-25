"""Synthetic end-to-end checkpoint: verified public release + fake WP-CLI.

No live WordPress, credentials, network, private media or deployment.
"""
import hashlib
import io
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from ez2_content_candidate_bundle import package
from ez2_release_set import run as release_set
from ez2_wp_preinstall_checkpoint import prepare

SHA = "a" * 40
INSTALLED_SHA = "b" * 40
HOST = "ez2-checkpoint.local"
CASES = 0

FAKE_WP = """#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
if "eval-file" in args:
    if os.environ.get("FAKE_WP_FAIL") == "gate": sys.exit(2)
    print(json.dumps({
        "status": "READY_FOR_BACKUP_REHEARSAL_ONLY",
        "target_site": "ez2-isolated-only",
        "expected_release_sha": os.environ["EZ2_EXPECTED_RELEASE_SHA"],
        "delivery_mode": "upgrade", "issues": [],
        "can_apply": False, "site_modified": False,
        "deployment_authorized": False
    }))
elif "db" in args and "export" in args:
    if os.environ.get("FAKE_WP_FAIL") == "export": sys.exit(2)
    pathlib.Path(args[args.index("export") + 1]).write_bytes(
        b"-- synthetic only\\nCREATE TABLE dummy(id INT);\\n")
else:
    sys.exit(3)
"""


def archive(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipped:
        for name, content in files:
            zipped.writestr(name, content)
    return buffer.getvalue()


def build_release(release, sha):
    release.mkdir()
    theme = archive([("ezb-theme/style.css", b"Theme Name: EZB Theme"),
                     ("ezb-theme/theme.json", b"{}")])
    core = archive([("ezb-core/ezb-core.php", b"<?php // synthetic")])
    (release / "ezb-theme.zip").write_bytes(theme)
    (release / "ezb-core.zip").write_bytes(core)
    (release / "RELEASE_METADATA.txt").write_text("commit=" + sha + "\nmedia_included=no\n")
    contents = {
        "schema_version": 1, "commit": sha, "delivery_scope": "theme-and-core-only",
        "archives": [
            {"name": "ezb-theme.zip", "install_path": "wp-content/themes/ezb-theme",
             "sha256": hashlib.sha256(theme).hexdigest()},
            {"name": "ezb-core.zip", "install_path": "wp-content/plugins/ezb-core",
             "sha256": hashlib.sha256(core).hexdigest()},
        ],
        "includes": {k: False for k in ("third_party_plugins", "elementor_templates",
                    "wordpress_content", "media", "database")},
        "localwp_installed": False, "owner_visual_acceptance": False,
    }
    (release / "RELEASE_CONTENTS.json").write_text(json.dumps(contents))
    names = ("ezb-theme.zip", "ezb-core.zip", "RELEASE_METADATA.txt", "RELEASE_CONTENTS.json")
    (release / "SHA256SUMS").write_text("".join(
        hashlib.sha256((release / name).read_bytes()).hexdigest() + "  " + name + "\n"
        for name in names))
    candidate = {
        "title": "Synthetic home", "type": "page", "version": "4.3.4",
        "page_settings": {},
        "content": [{"id": "deadbeef", "elType": "container",
                     "settings": {"background_slideshow_gallery": [
                         {"url": "ez2-media://home-hero-" + n}
                         for n in ("one", "two", "three", "four")]},
                     "elements": []}],
    }
    (release / "ez2-content-candidate.zip").write_bytes(
        package(sha, json.dumps(candidate).encode()))
    release_set("build", release, sha)

    return release


def fixture(root):
    release = build_release(root / "release", SHA)
    installed_release = build_release(root / "installed-release", INSTALLED_SHA)
    wp = root / "wp"
    wp.mkdir()
    (wp / "wp-load.php").write_text("<?php // synthetic")
    (wp / "wp-config.php").write_text("<?php // synthetic")
    (wp / "wp-admin").mkdir()
    for role in ("uploads", "plugins", "themes"):
        folder = wp / "wp-content" / role
        folder.mkdir(parents=True, exist_ok=True)
        if role == "uploads":
            (folder / "synthetic.txt").write_text("synthetic uploads")
    for filename, role in (("ezb-theme.zip", "themes"), ("ezb-core.zip", "plugins")):
        with zipfile.ZipFile(installed_release / filename) as zipped:
            zipped.extractall(wp / "wp-content" / role)
    private = root / "private"
    private.mkdir()
    fake = root / "fake-wp"
    fake.write_text(FAKE_WP)
    fake.chmod(0o700)
    return release, installed_release, wp, private, fake


def run(release, installed_release, wp, private, fake, *, sha=SHA,
        installed_sha=INSTALLED_SHA, host=HOST, version="4.3.4",
        name="ez2-backup-checkpoint"):
    return prepare(release, installed_release, wp, private, name, host, version,
                   installed_sha, sha, wp_executable=fake)


def reject(action, destination=None):
    global CASES
    try:
        action()
    except (ValueError, OSError, TypeError, KeyError):
        if destination is not None:
            assert not destination.exists(), "Failed checkpoint retained unverified archive"
        CASES += 1
        return
    raise AssertionError("Unsafe checkpoint accepted")


with tempfile.TemporaryDirectory() as temp:
    release, installed_release, wp, private, fake = fixture(Path(temp))
    result = run(release, installed_release, wp, private, fake)
    assert result["status"] == "PRIVATE_PREINSTALL_CHECKPOINT_VERIFIED_ONLY"
    assert result["installed_source_sha"] == INSTALLED_SHA
    assert result["candidate_source_sha"] == SHA
    assert result["installed_code_byte_parity_verified"] is True
    assert result["installed_source_attested"] is False
    assert result["candidate_release_verified"] is True
    assert json.loads((private / "ez2-backup-checkpoint" / "backup-manifest.json").read_text())["source_sha"] == INSTALLED_SHA
    for key in ("public_release_verified", "private_backup_created",
                "private_backup_byte_integrity_verified", "private_file_replay_verified",
                "database_export_generated"):
        assert result[key] is True
    for key in ("database_restore_rehearsed",
                "consistent_database_and_files_snapshot_verified",
                "localwp_installed", "deployment_authorized", "can_apply",
                "one_click_complete"):
        assert result[key] is False
    assert (private / "ez2-backup-checkpoint" / "backup-manifest.json").exists()
    CASES += 1
    reject(lambda: run(release, installed_release, wp, private, fake))  # Never overwrite.
    assert CASES == 2

for scenario in ("wrong-sha", "same-sha", "wrong-installed-sha",
                 "invalid-release", "tampered-installed-release", "installed-code-drift",
                 "candidate-inside-wp",
                 "wrong-host", "gate-failure", "export-failure", "overlap",
                 "binding-failure"):
    with tempfile.TemporaryDirectory() as temp:
        release, installed_release, wp, private, fake = fixture(Path(temp))
        destination = private / "ez2-backup-checkpoint"
        if scenario == "wrong-sha":
            action = lambda: run(release, installed_release, wp, private, fake, sha="c" * 40)
        elif scenario == "same-sha":
            action = lambda: run(release, installed_release, wp, private, fake, sha=INSTALLED_SHA)
        elif scenario == "wrong-installed-sha":
            action = lambda: run(release, installed_release, wp, private, fake, installed_sha="c" * 40)
        elif scenario == "tampered-installed-release":
            (installed_release / "ezb-theme.zip").write_bytes(b"tampered")
            action = lambda: run(release, installed_release, wp, private, fake)
        elif scenario == "candidate-inside-wp":
            nested = wp / "candidate-release"
            shutil.copytree(release, nested)
            action = lambda: run(nested, installed_release, wp, private, fake)
        elif scenario == "installed-code-drift":
            (wp / "wp-content/themes/ezb-theme/style.css").write_text("owner changed")
            action = lambda: run(release, installed_release, wp, private, fake)
        elif scenario == "invalid-release":
            (release / "ezb-theme.zip").write_bytes(b"tampered")
            action = lambda: run(release, installed_release, wp, private, fake)
        elif scenario == "wrong-host":
            action = lambda: run(release, installed_release, wp, private, fake, host="ez-bns-new-dev.local")
        elif scenario in ("gate-failure", "export-failure"):
            os.environ["FAKE_WP_FAIL"] = "gate" if scenario == "gate-failure" else "export"
            action = lambda: run(release, installed_release, wp, private, fake)
        elif scenario == "overlap":
            action = lambda: run(release, installed_release, wp, release, fake)
        else:
            action = lambda: run(release, installed_release, wp, private, fake)
        try:
            if scenario == "binding-failure":
                with patch("ez2_wp_preinstall_checkpoint.bind_release",
                           side_effect=ValueError("synthetic bind failure")):
                    reject(action, destination)
            else:
                reject(action, destination)
        finally:
            os.environ.pop("FAKE_WP_FAIL", None)
        assert not any(p.name.startswith("ez2-capture-") for p in private.iterdir())

assert CASES == 14, CASES
print(f"EZ2_PRIVATE_PREINSTALL_CHECKPOINT_PASS cases={CASES} private_backup_verified=true localwp_touched=false can_apply=false")
