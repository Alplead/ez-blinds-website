"""Synthetic end-to-end release + private rollback binding, no WordPress or network."""
import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path

from ez2_backup_release_binding import bind
from ez2_backup_snapshot_pack import pack
from ez2_content_candidate_bundle import package
from ez2_release_set import run as release_set

SHA = "a" * 40
CASES = 0


def zip_bytes(files):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files:
            archive.writestr(name, content)
    return data.getvalue()


def fixture(root):
    release = root / "release"
    release.mkdir()
    theme = zip_bytes([("ezb-theme/style.css", b"Theme Name: EZB Theme"),
                       ("ezb-theme/theme.json", b"{}")])
    core = zip_bytes([("ezb-core/ezb-core.php", b"<?php // synthetic")])
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
            "third_party_plugins", "elementor_templates", "wordpress_content",
            "media", "database")},
        "localwp_installed": False, "owner_visual_acceptance": False,
    }
    (release / "RELEASE_CONTENTS.json").write_text(json.dumps(manifest))
    names = ("ezb-theme.zip", "ezb-core.zip", "RELEASE_METADATA.txt", "RELEASE_CONTENTS.json")
    (release / "SHA256SUMS").write_text("".join(
        hashlib.sha256((release / name).read_bytes()).hexdigest() + "  " + name + "\n"
        for name in names))
    candidate = {
        "title": "Synthetic home", "type": "page", "version": "4.3.4",
        "page_settings": {}, "content": [{
            "id": "deadbeef", "elType": "container",
            "settings": {"background_slideshow_gallery": [
                {"url": "ez2-media://home-hero-" + n}
                for n in ("one", "two", "three", "four")]},
            "elements": [],
        }],
    }
    (release / "ez2-content-candidate.zip").write_bytes(
        package(SHA, json.dumps(candidate).encode()))
    release_set("build", release, SHA)

    source = root / "source"
    source.mkdir()
    (source / "database.sql").write_bytes(b"-- synthetic only\nCREATE TABLE dummy(id INT);\n")
    for role in ("uploads", "plugins", "theme"):
        (source / role).mkdir()
        (source / role / "synthetic.txt").write_text("synthetic " + role)
    backup = root / "private-backup"
    pack(source, backup, SHA)
    return release, backup


def reject(action):
    global CASES
    try:
        action()
    except (ValueError, OSError, TypeError, KeyError):
        CASES += 1
        return
    raise AssertionError("Unsafe binding accepted")


with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    release, backup = fixture(root)
    good = bind(release, backup, SHA)
    assert good["status"] == "EXACT_HEAD_RELEASE_AND_PRIVATE_BACKUP_VERIFIED_ONLY"
    assert good["private_backup_byte_integrity_verified"]
    assert good["private_scratch_file_replay_verified"]
    assert good["private_scratch_files_replayed"] == 3
    for flag in ("database_restore_rehearsed", "consistent_database_and_files_snapshot_verified",
                 "installed_site_identity_attested", "localwp_touched",
                 "deployment_authorized", "can_apply", "one_click_complete"):
        assert good[flag] is False, flag
    CASES += 1
    assert bind(release, backup, SHA) == good
    CASES += 1
    for sha in ("", "A" * 40, "b" * 40, "a" * 39, "g" * 40):
        reject(lambda sha=sha: bind(release, backup, sha))
    reject(lambda: bind(release, release, SHA))
    reject(lambda: bind(root, backup, SHA))
    reject(lambda: bind(release, root, SHA))
    reject(lambda: bind(release / "missing", backup, SHA))
    reject(lambda: bind(release, backup / "missing", SHA))
    (root / "release-link").symlink_to(release, target_is_directory=True)
    reject(lambda: bind(root / "release-link", backup, SHA))
    (root / "backup-link").symlink_to(backup, target_is_directory=True)
    reject(lambda: bind(release, root / "backup-link", SHA))
    sql = backup / "database.sql.gz"
    original_sql = sql.read_bytes()
    sql.write_bytes(original_sql + b"tampered")
    reject(lambda: bind(release, backup, SHA))
    sql.write_bytes(original_sql)
    original_theme = (release / "ezb-theme.zip").read_bytes()
    (release / "ezb-theme.zip").write_bytes(b"tampered")
    reject(lambda: bind(release, backup, SHA))
    (release / "ezb-theme.zip").write_bytes(original_theme)
    assert bind(release, backup, SHA) == good
    CASES += 1
    assert CASES == 17, CASES
    print(f"EZ2_BACKUP_RELEASE_BINDING_PASS cases={CASES} release_and_backup_verified=true localwp_touched=false can_apply=false")
