"""Synthetic read-only first-party installed-code parity regressions."""
import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path

from ez2_installed_code_parity import check

SHA = "a" * 40
CASES = 0


def zipped(files):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return data.getvalue()


def fixture(root):
    release = root / "release"
    release.mkdir()
    content = root / "site" / "wp-content"
    (content / "themes" / "ezb-theme").mkdir(parents=True)
    (content / "plugins" / "ezb-core").mkdir(parents=True)
    files = {
        "ezb-theme.zip": {
            "ezb-theme/style.css": b"Theme Name: EZB Theme\n",
            "ezb-theme/theme.json": b"{}",
        },
        "ezb-core.zip": {"ezb-core/ezb-core.php": b"<?php // synthetic"},
    }
    archives = []
    for name, entries in files.items():
        raw = zipped(entries)
        (release / name).write_bytes(raw)
        archives.append({"name": name, "install_path": "wp-content/" +
                         ("themes/ezb-theme" if name == "ezb-theme.zip" else "plugins/ezb-core"),
                         "sha256": hashlib.sha256(raw).hexdigest()})
        for member, data in entries.items():
            path = content / ("themes" if name == "ezb-theme.zip" else "plugins") / member
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    manifest = {
        "schema_version": 1, "commit": SHA, "delivery_scope": "theme-and-core-only",
        "archives": archives,
        "includes": {name: False for name in (
            "third_party_plugins", "elementor_templates", "wordpress_content", "media", "database")},
        "localwp_installed": False, "owner_visual_acceptance": False,
    }
    (release / "RELEASE_CONTENTS.json").write_text(json.dumps(manifest))
    (release / "RELEASE_METADATA.txt").write_text("commit=" + SHA + "\n")
    names = ("ezb-theme.zip", "ezb-core.zip", "RELEASE_CONTENTS.json", "RELEASE_METADATA.txt")
    (release / "SHA256SUMS").write_text("".join(
        hashlib.sha256((release / n).read_bytes()).hexdigest() + "  " + n + "\n" for n in names))
    return release, content


def rejected(action):
    global CASES
    try:
        action()
    except (ValueError, OSError, TypeError, KeyError, zipfile.BadZipFile):
        CASES += 1
        return
    raise AssertionError("Unsafe parity input was accepted")


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    release, content = fixture(root)
    original = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = check(release, SHA, content)
    assert result["status"] == "CODE_BYTES_MATCH_RELEASE_ONLY"
    assert result["checked_release_files"] == 3 and result["mismatch_count"] == 0
    assert result["theme_core_byte_parity"] is True
    assert all(result[key] is False for key in (
        "site_identity_verified", "installed_source_attested", "wordpress_runtime_verified",
        "third_party_plugins_verified", "elementor_content_verified", "private_media_verified",
        "localwp_installed", "deployment_authorized", "applied", "one_click_complete"))
    CASES += 1
    assert result == check(release, SHA, content)
    CASES += 1
    assert original == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    CASES += 1
    target = content / "themes/ezb-theme/style.css"
    target.write_text("Owner changed this file")
    mismatch = check(release, SHA, content)
    assert mismatch["status"] == "BLOCKED_CODE_PARITY" and mismatch["mismatch_count"] == 1
    CASES += 1
    target.unlink()
    assert check(release, SHA, content)["mismatch_count"] == 1
    CASES += 1
    target.write_bytes(b"Theme Name: EZB Theme\n")
    extra = content / "plugins/ezb-core/extra.php"
    extra.write_text("unexpected")
    assert check(release, SHA, content)["mismatch_count"] == 1
    CASES += 1
    extra.unlink()
    target.unlink()
    target.symlink_to(content / "themes/ezb-theme/theme.json")
    rejected(lambda: check(release, SHA, content))
    target.unlink()
    target.write_bytes(b"Theme Name: EZB Theme\n")
    extra.hardlink_to(target)
    rejected(lambda: check(release, SHA, content))
    extra.unlink()
    link = content / "themes/ezb-theme/subdir"
    link.symlink_to(content / "plugins", target_is_directory=True)
    rejected(lambda: check(release, SHA, content))
    link.unlink()
    rejected(lambda: check(release, "b" * 40, content))
    rejected(lambda: check(release, "invalid", content))
    rejected(lambda: check(release, SHA, content.parent))
    (release / "ezb-theme.zip").write_bytes(b"tampered")
    rejected(lambda: check(release, SHA, content))
    assert CASES == 13, CASES
print(f"EZ2_INSTALLED_CODE_PARITY_PASS cases={CASES}")
