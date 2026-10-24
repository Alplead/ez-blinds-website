"""Self-contained, synthetic fixtures only. No private media or production access."""
import copy
import hashlib
import io
import json
import stat
import zipfile
import tempfile
from pathlib import Path
from verify_release_scope import check

SHA = "a" * 40

def digest(data):
    return hashlib.sha256(data).hexdigest()


def archive_bytes(name, entries=None):
    root = name.removesuffix(".zip")
    if entries is None:
        entries = (
            [("ezb-theme/style.css", b"Theme Name: EZB Theme"), ("ezb-theme/theme.json", b"{}")]
            if root == "ezb-theme" else [("ezb-core/ezb-core.php", b"<?php // fixture")]
        )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in entries:
            archive.writestr(path, content)
    return stream.getvalue()


def changed_archive(root, name, entries=None, raw_bytes=None):
    (root / name).write_bytes(raw_bytes if raw_bytes is not None else archive_bytes(name, entries))
    doc = json.loads((root / "RELEASE_CONTENTS.json").read_text())
    for item in doc["archives"]:
        if item["name"] == name:
            item["sha256"] = digest((root / name).read_bytes())
    (root / "RELEASE_CONTENTS.json").write_text(json.dumps(doc))
    update_ledger(root)


def update_ledger(root):
    names = ("ezb-theme.zip", "ezb-core.zip", "RELEASE_METADATA.txt", "RELEASE_CONTENTS.json")
    (root / "SHA256SUMS").write_text("".join(f"{digest((root / n).read_bytes())}  {n}\n" for n in names))

def fixture(root):
    (root / "ezb-theme.zip").write_bytes(archive_bytes("ezb-theme.zip"))
    (root / "ezb-core.zip").write_bytes(archive_bytes("ezb-core.zip"))
    (root / "RELEASE_METADATA.txt").write_text(f"commit={SHA}\nmedia_included=no\n")
    doc = {
        "schema_version": 1, "commit": SHA, "delivery_scope": "theme-and-core-only",
        "archives": [
            {"name": "ezb-theme.zip", "install_path": "wp-content/themes/ezb-theme", "sha256": digest((root / "ezb-theme.zip").read_bytes())},
            {"name": "ezb-core.zip", "install_path": "wp-content/plugins/ezb-core", "sha256": digest((root / "ezb-core.zip").read_bytes())},
        ],
        "includes": {key: False for key in ("third_party_plugins", "elementor_templates", "wordpress_content", "media", "database")},
        "localwp_installed": False, "owner_visual_acceptance": False,
    }
    (root / "RELEASE_CONTENTS.json").write_text(json.dumps(doc))
    update_ledger(root)
    return doc

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    baseline = fixture(root)
    check(root, SHA)
    cases = 1
    def reject(modifier, name):
        global cases
        fixture(root)
        modifier(root)
        try:
            check(root, SHA)
        except (ValueError, OSError, KeyError, TypeError):
            cases += 1
            return
        raise AssertionError("Accepted invalid release: " + name)
    reject(lambda r: (r / "ezb-core.zip").write_bytes(b"tampered"), "archive tamper")
    reject(lambda r: (r / "SHA256SUMS").write_text(""), "ledger missing entries")
    reject(lambda r: (r / "RELEASE_METADATA.txt").write_text("commit=" + "b"*40 + "\n"), "metadata mismatch")
    def changed_doc(r, change):
        doc = copy.deepcopy(baseline)
        change(doc)
        (r / "RELEASE_CONTENTS.json").write_text(json.dumps(doc))
        update_ledger(r)
    reject(lambda r: changed_doc(r, lambda d: d.update({"commit": "b"*40})), "wrong SHA")
    reject(lambda r: changed_doc(r, lambda d: d.update({"delivery_scope": "full-site-one-click"})), "unapproved scope")
    reject(lambda r: changed_doc(r, lambda d: d["includes"].update({"media": True})), "false media inclusion")
    reject(lambda r: changed_doc(r, lambda d: d.update({"localwp_installed": True})), "false install claim")
    reject(lambda r: changed_doc(r, lambda d: d["archives"][0].update({"install_path": "../production"})), "path traversal")
    reject(lambda r: changed_doc(r, lambda d: d["archives"].append(d["archives"][0])), "duplicate archive")
    reject(lambda r: (r / "RELEASE_CONTENTS.json").unlink(), "missing manifest")

    valid_theme = [("ezb-theme/style.css", b"ok"), ("ezb-theme/theme.json", b"{}")]
    reject(lambda r: changed_archive(r, "ezb-theme.zip",
           valid_theme + [("ezb-theme/../escape.php", b"x")]), "ZIP traversal")
    reject(lambda r: changed_archive(r, "ezb-theme.zip",
           valid_theme + [("/tmp/escape.php", b"x")]), "absolute ZIP path")
    reject(lambda r: changed_archive(r, "ezb-theme.zip",
           valid_theme + [("ezb-theme/STYLE.CSS", b"x")]), "case-colliding ZIP entry")
    reject(lambda r: changed_archive(r, "ezb-theme.zip",
           valid_theme + [("ezb-core/foreign.php", b"x")]), "foreign ZIP root")
    reject(lambda r: changed_archive(r, "ezb-theme.zip",
           [("ezb-theme/style.css", b"ok")]), "missing required theme JSON")
    reject(lambda r: changed_archive(r, "ezb-theme.zip",
           valid_theme + [("ezb-theme/uploads/customer.jpg", b"private")]), "forbidden uploads")
    reject(lambda r: changed_archive(r, "ezb-theme.zip",
           raw_bytes=b"not a zip"), "invalid ZIP bytes")
    symlink = zipfile.ZipInfo("ezb-theme/shortcut")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    reject(lambda r: changed_archive(r, "ezb-theme.zip",
           valid_theme + [(symlink, "../../outside")]), "ZIP symlink")
    # Synthetic Windows extraction hazards: reserved names, trailing dots/spaces,
    # forbidden punctuation and device-name superscripts. No customer media.
    for invalid_path in (
        "ezb-theme/CON.txt",
        "ezb-theme/lpt1.log",
        "ezb-theme/LPT¹.log",
        "ezb-theme/nested./photo.webp",
        "ezb-theme/trailing ",
        "ezb-theme/name?.txt",
        'ezb-theme/name".txt',
    ):
        reject(lambda r, path=invalid_path: changed_archive(
            r, "ezb-theme.zip", valid_theme + [(path, b"synthetic")]),
            "Windows-incompatible ZIP path: " + invalid_path)
    fixture(root)
    changed_archive(root, "ezb-theme.zip",
                    valid_theme + [("ezb-theme/normal-name.webp", b"synthetic")])
    check(root, SHA)
    cases += 1
print(f"EZB_RELEASE_SCOPE_REGRESSION_PASS cases={cases}")
