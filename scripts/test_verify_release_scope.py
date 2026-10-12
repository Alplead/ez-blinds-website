"""Self-contained, synthetic fixtures only. No private media or production access."""
import copy
import hashlib
import json
import tempfile
from pathlib import Path
from verify_release_scope import check

SHA = "a" * 40

def digest(data):
    return hashlib.sha256(data).hexdigest()

def update_ledger(root):
    names = ("ezb-theme.zip", "ezb-core.zip", "RELEASE_METADATA.txt", "RELEASE_CONTENTS.json")
    (root / "SHA256SUMS").write_text("".join(f"{digest((root / n).read_bytes())}  {n}\n" for n in names))

def fixture(root):
    (root / "ezb-theme.zip").write_bytes(b"theme fixture")
    (root / "ezb-core.zip").write_bytes(b"core fixture")
    (root / "RELEASE_METADATA.txt").write_text(f"commit={SHA}\nmedia_included=no\n")
    doc = {
        "schema_version": 1, "commit": SHA, "delivery_scope": "theme-and-core-only",
        "archives": [
            {"name": "ezb-theme.zip", "install_path": "wp-content/themes/ezb-theme", "sha256": digest(b"theme fixture")},
            {"name": "ezb-core.zip", "install_path": "wp-content/plugins/ezb-core", "sha256": digest(b"core fixture")},
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
print(f"EZB_RELEASE_SCOPE_REGRESSION_PASS cases={cases}")
