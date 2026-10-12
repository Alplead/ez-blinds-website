"""No-network synthetic tests for the read-only EZ2 plugin lockfile guard."""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from ez2_plugin_dependency_check import check, read, unique


def sample(checksum=None):
    return {"schema_version": 1, "target_site": "ez2-isolated-only",
            "plugins": [{"slug": "elementor", "version": "4.3.4",
                         "entrypoint": "elementor/elementor.php", "source": "wordpress.org",
                         "archive_sha256": checksum, "activate": True}]}


cases = 0
r = check(sample())
assert r["status"] == "PENDING_CHECKSUM" and r["missing_checksums"] == ["elementor"]
assert not any(r[k] for k in ("downloaded", "provenance_verified", "runtime_verified",
                              "installed", "deployment_authorized"))
cases += 1
r = check(sample("a" * 64))
assert r["status"] == "METADATA_ONLY" and r["plugins"][0]["checksum_recorded"]
assert not r["deployment_authorized"]
cases += 1


def reject(change):
    global cases
    d = sample()
    change(d)
    try:
        check(d)
    except (ValueError, TypeError):
        cases += 1
        return
    raise AssertionError("Unsafe manifest accepted")


reject(lambda d: d.update(target_site="ez-bns-new-dev.local"))
reject(lambda d: d["plugins"][0].update(source="https://untrusted.invalid"))
reject(lambda d: d["plugins"][0].update(slug="elementor-pro"))
reject(lambda d: d["plugins"][0].update(entrypoint="../elementor.php"))
reject(lambda d: d["plugins"].append({"slug": "other", "version": "1.2.3",
    "entrypoint": "other/other.php", "source": "wordpress.org", "archive_sha256": None,
    "activate": True}))
reject(lambda d: d["plugins"][0].update(version="latest"))
reject(lambda d: d["plugins"][0].update(version="4.3.4-beta"))
reject(lambda d: d["plugins"][0].update(archive_sha256="invalid"))
reject(lambda d: d["plugins"][0].update(archive_sha256="0" * 64))
reject(lambda d: d["plugins"][0].update(activate=False))
reject(lambda d: d["plugins"].append(copy.deepcopy(d["plugins"][0])))
reject(lambda d: d["plugins"][0].update(download_url="https://example.invalid"))
reject(lambda d: d.update(schema_version=True))
reject(lambda d: d.update(plugins=[]))
reject(lambda d: d.update(extra="unapproved"))
try:
    unique([("a", 1), ("a", 2)])
    raise AssertionError("Duplicate JSON keys accepted")
except ValueError:
    cases += 1

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    path = root / "manifest.json"
    script = Path(__file__).with_name("ez2_plugin_dependency_check.py")
    path.write_text(json.dumps(sample()), encoding="utf-8")
    run = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True)
    assert run.returncode == 2 and json.loads(run.stdout)["status"] == "PENDING_CHECKSUM"
    cases += 1
    path.write_text(json.dumps(sample("a" * 64)), encoding="utf-8")
    run = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True)
    assert run.returncode == 0 and not json.loads(run.stdout)["installed"]
    cases += 1
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    run = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True)
    assert run.returncode == 1
    cases += 1
    link = root / "linked.json"
    link.symlink_to(path)
    try:
        read(link)
        raise AssertionError("Symlink accepted")
    except ValueError:
        cases += 1
assert cases == 22, cases
print(f"EZ2_PLUGIN_DEPENDENCY_PREFLIGHT_PASS cases={cases}")
