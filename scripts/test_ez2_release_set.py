"""Real-dependency synthetic tests: no mocks, site writes, private media or credentials."""
import hashlib
import io
import json
import zipfile
import tempfile
import zipfile
from pathlib import Path

from ez2_content_candidate_bundle import package as candidate_package
from ez2_release_set import CATALOG, run, safe_read

SHA = "a" * 40
CASES = 0


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, content in files:
            z.writestr(name, content)
    return output.getvalue()


def fixture(root):
    theme = archive([("ezb-theme/style.css", b"Theme Name: EZB Theme"),
                     ("ezb-theme/theme.json", b"{}")])
    core = archive([("ezb-core/ezb-core.php", b"<?php // synthetic")])
    (root / "ezb-theme.zip").write_bytes(theme)
    (root / "ezb-core.zip").write_bytes(core)
    (root / "RELEASE_METADATA.txt").write_text("commit=" + SHA + "\nmedia_included=no\n")
    manifest = {
        "schema_version": 1, "commit": SHA, "delivery_scope": "theme-and-core-only",
        "archives": [
            {"name": "ezb-theme.zip", "install_path": "wp-content/themes/ezb-theme",
             "sha256": digest(theme)},
            {"name": "ezb-core.zip", "install_path": "wp-content/plugins/ezb-core",
             "sha256": digest(core)},
        ],
        "includes": {k: False for k in (
            "third_party_plugins", "elementor_templates", "wordpress_content", "media", "database")},
        "localwp_installed": False, "owner_visual_acceptance": False,
    }
    (root / "RELEASE_CONTENTS.json").write_text(json.dumps(manifest))
    names = ("ezb-theme.zip", "ezb-core.zip", "RELEASE_METADATA.txt", "RELEASE_CONTENTS.json")
    (root / "SHA256SUMS").write_text("".join(
        digest((root / n).read_bytes()) + "  " + n + "\n" for n in names))
    template = {
        "title": "Synthetic candidate", "type": "page", "version": "4.3.4",
        "page_settings": {}, "content": [
            {"id": "deadbeef", "elType": "container",
             "settings": {"background_slideshow_gallery": [
                 {"url": "ez2-media://home-hero-" + n}
                 for n in ("one", "two", "three", "four")]},
             "elements": []}],
    }
    (root / "ez2-content-candidate.zip").write_bytes(
        candidate_package(SHA, json.dumps(template).encode("utf-8")))


def reject(change, label, sha=SHA, mode="verify"):
    global CASES
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fixture(root)
        run("build", root, SHA)
        change(root)
        try:
            run(mode, root, sha)
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
            CASES += 1
            return
        raise AssertionError("Accepted unsafe release-set state: " + label)


def alter(root, callback):
    path = root / CATALOG
    doc = json.loads(path.read_text())
    callback(doc)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    fixture(root)
    built = run("build", root, SHA)
    assert built["source_sha"] == SHA and len(built["files"]) == 6
    assert built["one_click_complete"] is False
    CASES += 1
    assert run("verify", root, SHA) == built
    CASES += 1
    try:
        run("build", root, SHA)
    except FileExistsError:
        CASES += 1
    else:
        raise AssertionError("Catalog unexpectedly overwritten")

reject(lambda r: None, "wrong exact SHA", "b" * 40)
reject(lambda r: (r / "ezb-theme.zip").write_bytes(b"tampered"), "theme tamper")
reject(lambda r: (r / "ez2-content-candidate.zip").write_bytes(b"tampered"), "candidate tamper")
reject(lambda r: (r / "SHA256SUMS").write_text("invalid"), "checksum ledger tamper")
reject(lambda r: (r / "ez2-content-candidate.zip").unlink(), "missing candidate")
reject(lambda r: alter(r, lambda d: d.update(one_click_complete=True)), "false one-click claim")
reject(lambda r: alter(r, lambda d: d.update(localwp_installed=True)), "false LP claim")
reject(lambda r: alter(r, lambda d: d.update(deployment_authorized=True)), "false authority")
reject(lambda r: alter(r, lambda d: d.update(target_site="ez-bns-new-dev.local")), "wrong site")
reject(lambda r: alter(r, lambda d: d["files"][0].update(sha256="0" * 64)), "false hash")
reject(lambda r: alter(r, lambda d: d["files"].append(d["files"][0])), "duplicate file")
reject(lambda r: alter(r, lambda d: d.update(unapproved=True)), "extra key")
reject(lambda r: (r / CATALOG).write_text('{"schema":1,"schema":1}'), "duplicate JSON key")
reject(lambda r: (r / CATALOG).write_text('{"schema":NaN}'), "nonfinite JSON")
reject(lambda r: (r / CATALOG).write_text(' {}\n'), "noncanonical JSON")
reject(lambda r: (r / CATALOG).unlink(), "missing catalog")
def linked_catalog(root):
    (root / CATALOG).unlink()
    (root / CATALOG).symlink_to(root / "RELEASE_CONTENTS.json")
reject(linked_catalog, "symlink catalog")
def linked_component(root):
    (root / "ez2-content-candidate.zip").unlink()
    (root / "ez2-content-candidate.zip").symlink_to(root / "RELEASE_CONTENTS.json")
reject(linked_component, "symlink component")
# A hard-linked component has two names for the same bytes and must not be
# trusted as an immutable release input, even when its checksum still matches.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    fixture(root)
    (root / "synthetic-alias").hardlink_to(root / "ezb-theme.zip")
    try:
        safe_read(root, "ezb-theme.zip")
    except ValueError:
        CASES += 1
    else:
        raise AssertionError("Hard-linked release component accepted")

reject(lambda r: None, "invalid mode", mode="install")
assert CASES == 23, CASES
print(f"EZ2_RELEASE_SET_TEST_PASS cases={CASES}")
