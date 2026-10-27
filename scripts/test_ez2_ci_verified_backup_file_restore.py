#!/usr/bin/env python3
"""Synthetic verified backup rollback test; no Owner photos, SQL or LocalWP."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
from unittest.mock import patch

from ez2_backup_preflight import ROLES
import ez2_ci_verified_backup_file_restore as engine
from ez2_ci_verified_backup_file_restore import rehearse

SHA = "a" * 40
cases = 0


def write_tar(path: Path, role: str, name="synthetic.txt", body=None, kind="file"):
    body = ("SYNTHETIC " + role + "\n").encode() if body is None else body
    with tarfile.open(path, "w:gz") as archive:
        entry = tarfile.TarInfo(role + "/" + name)
        if kind == "symlink":
            entry.type = tarfile.SYMTYPE
            entry.linkname = "../../secret"
        else:
            entry.size = len(body)
        archive.addfile(entry, io.BytesIO(body) if kind == "file" else None)


def rewrite_manifest(root: Path, sha=SHA):
    manifest = {
        "schema_version": 1,
        "target_site": "ez2-isolated-only",
        "source_sha": sha,
        "files": {
            role: {
                "name": filename,
                "sha256": hashlib.sha256((root / filename).read_bytes()).hexdigest(),
                "size_bytes": (root / filename).stat().st_size,
            } for role, filename in ROLES.items()
        },
    }
    (root / "backup-manifest.json").write_text(json.dumps(manifest))


def fixture(root):
    with gzip.open(root / ROLES["database"], "wb") as db:
        db.write(b"-- synthetic CI SQL, never executed\n")
    for role in ("uploads", "plugins", "theme"):
        write_tar(root / ROLES[role], role)
    rewrite_manifest(root)


def reject(change, expected_phrase, *, update=True):
    global cases
    with tempfile.TemporaryDirectory(prefix="ez2-ci-recovery-tests-") as temp:
        root = Path(temp)
        fixture(root)
        change(root)
        if update:
            rewrite_manifest(root)
        try:
            rehearse(root, SHA)
        except (ValueError, OSError) as error:
            assert expected_phrase in str(error), (expected_phrase, str(error))
        else:
            raise AssertionError("Unsafe backup accepted: " + expected_phrase)
        cases += 1


os.environ["GITHUB_ACTIONS"] = "true"
os.environ["EZ2_CI_VERIFIED_FILE_RESTORE"] = "YES_DISPOSABLE_RELEASE_STACK"
with tempfile.TemporaryDirectory(prefix="ez2-ci-backup-fixture-") as temp:
    root = Path(temp)
    fixture(root)
    report = rehearse(root, SHA)
    assert report["status"] == "EZ2_CI_VERIFIED_BACKUP_FILE_RESTORE_PASS"
    assert report["components"] == 3 and report["files_rehearsed"] == 3
    assert report["injected_faults_restored"] == 6
    assert report["successful_swap_and_explicit_restore"] is True
    assert report["tampered_backup_refused"] is True
    assert report["private_scratch_deleted"] is True
    assert not any(report[k] for k in (
        "database_restore_rehearsed_here", "owner_localwp_touched",
        "one_click_ready", "can_apply",
    ))
    assert set(p.name for p in root.iterdir()) == set(ROLES.values()) | {"backup-manifest.json"}
    cases += 1
    with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
        try:
            rehearse(root, SHA)
        except ValueError as e:
            assert "only allowed in disposable CI" in str(e)
        else:
            raise AssertionError("Non-CI was allowed to perform filesystem writes")
        cases += 1
    with patch.dict(os.environ, {"EZ2_CI_VERIFIED_FILE_RESTORE": "NO"}):
        try:
            rehearse(root, SHA)
        except ValueError as e:
            assert "only allowed in disposable CI" in str(e)
        else:
            raise AssertionError("Missing opt-in was allowed")
        cases += 1
    try:
        rehearse(root, "wrong")
    except ValueError as e:
        assert "Exact source SHA required" in str(e)
    else:
        raise AssertionError("Unpinned source was accepted")
    cases += 1
    try:
        rehearse(root, "b" * 40)
    except ValueError as e:
        assert "Wrong site, source or manifest schema" in str(e)
    else:
        raise AssertionError("Mismatched SHA was accepted")
    cases += 1

# An actual failed rename, not just a labelled test exception, must recover
# every component already moved and MUST propagate its error to the caller.
with tempfile.TemporaryDirectory(prefix="ez2-ci-io-failure-") as tmp:
    parent = Path(tmp)
    source = parent / "master"
    attempt_root = parent / "attempts"
    source.mkdir()
    attempt_root.mkdir()
    for role in engine.ROLES_TO_RESTORE:
        (source / role).mkdir()
        (source / role / "new.txt").write_text("SYNTHETIC-NEW-" + role)
    expected = {role: engine.fingerprint(source / role)
                for role in engine.ROLES_TO_RESTORE}
    original_move = engine.safe_move
    move_count = [0]

    def fail_fourth_move(a, b):
        move_count[0] += 1
        if move_count[0] == 4:
            raise OSError("SYNTHETIC_DISK_RENAME_FAILURE")
        original_move(a, b)

    with patch("ez2_ci_verified_backup_file_restore.safe_move", side_effect=fail_fourth_move):
        try:
            engine.run_one(source, expected, None, attempt_root)
        except OSError as exc:
            assert str(exc) == "SYNTHETIC_DISK_RENAME_FAILURE"
        else:
            raise AssertionError("Real I/O error was hidden as success")
    attempt = attempt_root / "case-success"
    for role in engine.ROLES_TO_RESTORE:
        assert (attempt / "installed" / role / "original-ci-marker.txt").read_text() == (
            "SYNTHETIC-OLD-ONLY:" + role + "\n")
    engine.verify_role_set(attempt / "incoming", expected)
    assert not list((attempt / "backup").iterdir())
    cases += 1

reject(lambda r: (r / ROLES["uploads"]).write_bytes(b"damaged"),
       "Invalid compressed tar archive")
# Preserve byte count so the checksum (not merely the size guard) catches it.
reject(lambda r: (r / ROLES["uploads"]).write_bytes(
           b"X" * (r / ROLES["uploads"]).stat().st_size),
       "checksum mismatch", update=False)
reject(lambda r: write_tar(r / ROLES["plugins"], "plugins",
                           name="../escape.txt", body=b"escape"),
       "Unsafe archive member path")
reject(lambda r: write_tar(r / ROLES["theme"], "theme",
                           name="link.txt", kind="symlink"),
       "Unsupported archive entry type")
reject(lambda r: (r / "unexpected.zip").write_bytes(b"outside"),
       "Unexpected or missing rollback backup entries")
reject(lambda r: (r / ROLES["database"]).write_bytes(b"not a gzip"),
       "Invalid compressed SQL dump")
with patch("ez2_ci_verified_backup_file_restore.MAX_BYTES", 1):
    reject(lambda r: None, "Synthetic backup too large")
with patch("ez2_ci_verified_backup_file_restore.MAX_FILES", 1):
    reject(lambda r: None, "Synthetic backup too large")
print("EZ2_CI_VERIFIED_FILE_ROLLBACK_TEST_PASS cases=" + str(cases))
