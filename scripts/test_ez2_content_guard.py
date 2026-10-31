"""No-network synthetic regression tests for EZ2 dry-run content guard."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from ez2_content_guard import digest, plan, read

old, new, edited = ({"title": value} for value in ("Original", "New", "Owner edit"))
h_old, h_new, h_edited = map(digest, (old, new, edited))

def desired(previous=h_old, key="ez2-home"):
    return {"schema_version": 1, "items": [{"key": key, "payload": new, "previous_sha256": previous}]}

def installed(current=h_old):
    return {"schema_version": 1, "items": [{"key": "ez2-home", "current_sha256": current}]}

cases = 0
for want, have, action in [
    (desired(None), installed_empty := {"schema_version": 1, "items": []}, "create"),
    (desired(), installed(), "update"),
    (desired(), installed(h_new), "unchanged"),
    (desired(), installed(h_edited), "conflict_owner_edit"),
    (desired(None), installed(), "conflict_owner_edit"),
    (desired(), installed_empty, "conflict_missing"),
]:
    result = plan(want, have)
    assert result["actions"][0]["action"] == action
    assert result["applied"] is False and result["deployment_authorized"] is False
    cases += 1
unmanaged = plan(desired(), {"schema_version": 1, "items": installed()["items"] + [
    {"key": "ez2-z-extra", "current_sha256": h_old},
    {"key": "ez2-a-extra", "current_sha256": h_old}]})
assert unmanaged["unmanaged_existing_count"] == 2
assert unmanaged["unmanaged_existing_keys"] == ["ez2-a-extra", "ez2-z-extra"]
assert unmanaged["applied"] is False
cases += 1
assert digest({"b": 2, "a": 1}) == digest({"a": 1, "b": 2})
cases += 1
for want, have in [
    ({"schema_version": 1, "items": desired()["items"] * 2}, installed()),
    (desired(key="../unsafe"), installed()),
    (desired(previous="invalid"), installed()),
    (desired(), installed("invalid")),
    ({"schema_version": True, "items": []}, installed()),
]:
    try:
        plan(want, have)
        raise AssertionError("Unsafe input accepted")
    except ValueError:
        cases += 1
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / "input.json"
    path.write_text('{"schema_version":1,"schema_version":1,"items":[]}')
    try:
        read(path)
        raise AssertionError("Duplicate keys accepted")
    except ValueError:
        cases += 1
    # A valid-looking path must not be able to redirect or replace a
    # content-conflict input between validation and reading.
    path.write_text('{"schema_version":1,"items":[NaN]}')
    try:
        read(path)
        raise AssertionError("Non-finite JSON input accepted")
    except ValueError:
        cases += 1
    path.write_text('{"schema_version":1,"items":[]}')
    alias = Path(temp) / "hardlink.json"
    os.link(path, alias)
    try:
        read(path)
        raise AssertionError("Hardlinked input accepted")
    except ValueError:
        cases += 1
    alias.unlink()
    alias.symlink_to(path)
    try:
        read(alias)
        raise AssertionError("Symlinked input accepted")
    except ValueError:
        cases += 1
    alias.unlink()
    directory_alias = Path(temp) / "folder-alias"
    nested = Path(temp) / "nested"
    nested.mkdir()
    (nested / "input.json").write_text('{"schema_version":1,"items":[]}')
    directory_alias.symlink_to(nested, target_is_directory=True)
    try:
        read(directory_alias / "input.json")
        raise AssertionError("Linked ancestor accepted")
    except ValueError:
        cases += 1
    directory_alias.unlink()
    original_open = os.open
    def replace_before_open(path_arg, flags, *args, **kwargs):
        if Path(path_arg) == path:
            replacement = Path(temp) / "replacement.json"
            replacement.write_bytes(path.read_bytes())
            os.replace(replacement, path)
        return original_open(path_arg, flags, *args, **kwargs)
    with patch("ez2_backup_preflight.os.open", side_effect=replace_before_open):
        try:
            read(path)
            raise AssertionError("Same-byte replacement accepted")
        except ValueError:
            cases += 1
    path.write_bytes(b"")
    try:
        read(path)
        raise AssertionError("Empty input accepted")
    except ValueError:
        cases += 1
    d, i = Path(temp) / "desired.json", Path(temp) / "installed.json"
    d.write_text(json.dumps(desired()))
    i.write_text(json.dumps(installed(h_edited)))
    cmd = [sys.executable, str(Path(__file__).with_name("ez2_content_guard.py")), str(d), str(i)]
    run = subprocess.run(cmd, capture_output=True, text=True)
    assert run.returncode == 2 and json.loads(run.stdout)["conflict_count"] == 1
    cases += 1
    i.write_text(json.dumps(installed()))
    run = subprocess.run(cmd, capture_output=True, text=True)
    assert run.returncode == 0
    cases += 1
print(f"EZ2_CONTENT_GUARD_TEST_PASS cases={cases}")
