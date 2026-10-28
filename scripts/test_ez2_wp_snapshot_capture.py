"""No WordPress or private media: fake WP-CLI plus synthetic directory fixture."""
import json
import os
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch

from ez2_wp_snapshot_capture import capture, pack as real_pack

SHA = "a" * 40
HOST = "ez2-review.local"
VERSION = "4.3.5"
CASES = 0

FAKE_WP = '''#!/usr/bin/env python3
import json, os, pathlib, sys
mode = os.environ.get("FAKE_WP_MODE", "ok")
args = sys.argv[1:]
if "eval-file" in args:
    if mode == "gate_error": sys.exit(2)
    if mode.startswith("file_drift_"):
        root = pathlib.Path(args[0].split("=", 1)[1])
        marker = root / "wp-content" / ".gate-first-seen"
        upload = root / "wp-content" / "uploads" / "synthetic.txt"
        if marker.exists():
            if mode == "file_drift_modify": upload.write_text("changed synthetic upload")
            elif mode == "file_drift_add":
                (upload.parent / "late-synthetic.txt").write_text("new synthetic file")
            elif mode == "file_drift_delete": upload.unlink()
        else:
            marker.write_text("first synthetic gate")
    gate = {"status": "READY_FOR_BACKUP_REHEARSAL_ONLY",
            "target_site": "ez2-isolated-only",
            "expected_release_sha": os.environ["EZ2_EXPECTED_RELEASE_SHA"],
            "delivery_mode": "upgrade", "issues": [], "can_apply": False,
            "site_modified": False, "deployment_authorized": False}
    if mode == "gate_wrong_site": gate["target_site"] = "ez-bns-new-dev"
    if mode == "gate_wrong_sha": gate["expected_release_sha"] = "b" * 40
    if mode == "gate_apply": gate["can_apply"] = True
    if mode == "gate_missing_issues": del gate["issues"]
    if mode == "gate_drift_after_export" and (
            pathlib.Path(args[0].split("=", 1)[1]) / "wp-content" / ".exported").exists():
        gate["expected_release_sha"] = "b" * 40
    print(json.dumps(gate))
elif "db" in args and "query" in args:
    required = ("--skip-column-names", "--skip-plugins", "--skip-themes")
    if any(flag not in args for flag in required): sys.exit(4)
    root = pathlib.Path(args[0].split("=", 1)[1])
    if mode == "engine_query_error": sys.exit(5)
    if mode == "engine_empty": pass
    elif mode == "engine_nontransactional": print("wp_options\\tMyISAM")
    elif mode == "engine_malformed": print("wp_options InnoDB")
    elif mode == "engine_drift_after_export" and (
            root / "wp-content" / ".exported").exists():
        print("wp_options\\tInnoDB\\nwp_late\\tInnoDB")
    elif mode == "engine_drift_after_pack" and (
            root / "wp-content" / ".engine-drift").exists():
        print("wp_options\\tInnoDB\\nwp_late\\tInnoDB")
    else: print("wp_options\\tInnoDB\\nwp_posts\\tInnoDB")
elif "db" in args and "export" in args:
    # Assert the actual WP-CLI argv rather than only checking a helper.
    # The capture must fail closed when its InnoDB snapshot flags are missing
    # or unsupported by the installed mysqldump implementation.
    required = ("--add-drop-table", "--single-transaction", "--quick",
                "--skip-lock-tables", "--skip-plugins", "--skip-themes")
    if any(flag not in args for flag in required): sys.exit(4)
    if mode in ("db_error", "transaction_not_supported"): sys.exit(1)
    path = pathlib.Path(args[args.index("export") + 1])
    root = pathlib.Path(args[0].split("=", 1)[1])
    if mode in ("gate_drift_after_export", "engine_drift_after_export"):
        (root / "wp-content" / ".exported").write_text("synthetic")
    if mode == "config_modified":
        (root / "wp-config.php").write_text("<?php // changed synthetic configuration")
    if mode == "bootstrap_modified":
        (root / "wp-load.php").write_text("<?php // changed synthetic bootstrap")
    if mode == "empty_sql": path.write_bytes(b"")
    elif mode == "missing_sql": pass
    elif mode == "symlink_sql":
        path.symlink_to(pathlib.Path(args[0].split("=", 1)[1]) / "wp-load.php")
    elif mode == "hardlink_sql":
        os.link(pathlib.Path(args[0].split("=", 1)[1]) / "wp-load.php", path)
    else: path.write_bytes(b"-- synthetic only\\nCREATE TABLE dummy(id INT);\\n")
else: sys.exit(3)
'''


def fixture(base):
    root = base / "wp"
    root.mkdir()
    (root / "wp-load.php").write_text("<?php // synthetic")
    (root / "wp-config.php").write_text("<?php // isolated synthetic configuration")
    (root / "wp-admin").mkdir()
    content = root / "wp-content"
    content.mkdir()
    for name in ("uploads", "plugins", "themes"):
        folder = content / name
        folder.mkdir()
        (folder / "synthetic.txt").write_text("test " + name)
    parent = base / "private"
    parent.mkdir()
    fake = base / "fake-wp"
    fake.write_text(FAKE_WP)
    fake.chmod(0o700)
    return root, parent, fake


def run(root, parent, fake, *, host=HOST, version=VERSION, sha=SHA,
        name="ez2-backup-test", mode="ok"):
    original = os.environ.get("FAKE_WP_MODE")
    os.environ["FAKE_WP_MODE"] = mode
    try:
        return capture(root, parent, name, host, version, sha, wp_executable=fake)
    finally:
        if original is None: os.environ.pop("FAKE_WP_MODE", None)
        else: os.environ["FAKE_WP_MODE"] = original


def reject(mutate=lambda root, parent, fake: None, **kwargs):
    global CASES
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        root, parent, fake = fixture(base)
        mutate(root, parent, fake)
        existed_before = (parent / "ez2-backup-test").exists()
        try:
            run(root, parent, fake, **kwargs)
        except (ValueError, OSError):
            assert (parent / "ez2-backup-test").exists() == existed_before, "Unsafe backup persisted"
            assert not any(x.name.startswith("ez2-capture-") for x in parent.iterdir()), "Staging leaked"
            CASES += 1
            return
        raise AssertionError("Unsafe WordPress capture accepted")


with tempfile.TemporaryDirectory() as temp:
    root, parent, fake = fixture(Path(temp))
    (root / "wp-content" / "uploads" / "empty" / "nested").mkdir(parents=True)
    result = run(root, parent, fake)
    assert result["status"] == "EZ2_PRIVATE_CAPTURE_ARCHIVED_AND_SCRATCH_FILE_REPLAYED_ONLY"
    assert result["backup_created"] and result["file_replay_verified"]
    assert result["source_file_inventory_stable"] is True
    assert result["database_export_generated"] and not result["database_restore_rehearsed"]
    assert not result["consistent_snapshot_verified"] and not result["deployment_authorized"]
    assert (parent / "ez2-backup-test" / "backup-manifest.json").is_file()
    with tarfile.open(parent / "ez2-backup-test" / "uploads.tar.gz", "r:gz") as archive:
        archived = {name.rstrip("/") for name in archive.getnames()}
        assert {"uploads/empty", "uploads/empty/nested"} <= archived
    assert (root / "wp-content" / "uploads" / "synthetic.txt").exists()
    assert not any(x.name.startswith("ez2-capture-") for x in parent.iterdir())
    CASES += 1
    try: run(root, parent, fake)
    except ValueError: CASES += 1
    else: raise AssertionError("Existing backup overwritten")

for mode in ("gate_error", "gate_wrong_site", "gate_wrong_sha", "gate_apply",
             "gate_missing_issues", "db_error", "transaction_not_supported", "empty_sql", "missing_sql",
             "symlink_sql", "hardlink_sql", "gate_drift_after_export",
             "engine_query_error", "engine_empty", "engine_nontransactional",
             "engine_malformed", "engine_drift_after_export",
             "config_modified", "bootstrap_modified", "file_drift_modify", "file_drift_add",
             "file_drift_delete"):
    reject(mode=mode)
for host in ("ezbns.com.au", "t2-ez-blinds-shutters.local", "ez-bns-new-dev.local",
             "ez2.local.evil", "ez2.local:8080", "EZ2-review.local", ""):
    reject(host=host)
for version in ("", "latest", "4.3", "4.3.5-beta", "0.0.0"):
    reject(version=version)
for sha in ("", "A" * 40, "a" * 39, "g" * 40):
    reject(sha=sha)
for name in ("", "backup", "../ez2-backup-test", "ez2-backup-..", "ez2-backup-TEST"):
    reject(name=name)
reject(lambda root, parent, fake: (root / "wp-config.php").unlink())
reject(lambda root, parent, fake: (
    (root / "wp-config.php").unlink(),
    (root / "wp-config.php").symlink_to(root / "wp-load.php"),
))
reject(lambda root, parent, fake: (
    (root / "wp-config.php").unlink(),
    os.link(root / "wp-load.php", root / "wp-config.php"),
))
reject(lambda root, parent, fake: (
    (root / "wp-config.php").unlink(),
    (root / "wp-config.php").mkdir(),
))
reject(lambda root, parent, fake: (root / "wp-load.php").unlink())
reject(lambda root, parent, fake: (
    (root / "wp-load.php").unlink(),
    (root / "wp-load.php").symlink_to(fake),
))
reject(lambda root, parent, fake: (
    (root / "wp-admin").rename(root / "wp-admin-original"),
    (root / "wp-admin").symlink_to(root / "wp-admin-original", target_is_directory=True),
))
reject(lambda root, parent, fake: (root / "wp-content" / "uploads" / "synthetic.txt").unlink())
reject(lambda root, parent, fake: (
    (root / "wp-content" / "plugins" / "synthetic.txt").unlink(),
    (root / "wp-content" / "plugins" / "synthetic.txt").symlink_to(root / "wp-load.php"),
))
reject(lambda root, parent, fake: (
    (root / "wp-content" / "themes").rename(root / "theme-old"),
    (root / "wp-content" / "themes").symlink_to(root / "theme-old", target_is_directory=True),
))
reject(lambda root, parent, fake: (parent / "ez2-backup-test").mkdir())
reject(lambda root, parent, fake: (root / "wp-content" / "uploads" / "bad?.txt").write_text("x"))
reject(lambda root, parent, fake: (root / "wp-content" / "plugins" / "nested").symlink_to(
    root / "wp-content" / "uploads", target_is_directory=True))

# Never allow private SQL/media backups to be created under a Git checkout.
# Ordinary checkouts use a .git directory; linked worktrees use a .git file.
reject(lambda root, parent, fake: (parent / ".git").mkdir())
reject(lambda root, parent, fake: (parent.parent / ".git").mkdir())
reject(lambda root, parent, fake: (parent.parent / ".git").write_text("gitdir: /synthetic/worktree"))
reject(lambda root, parent, fake: (parent.parent / ".git").symlink_to("missing-gitdir"))

# A verified archive must not be accepted if live files change during
# the potentially lengthy packaging/replay phase. Only the newly created
# private backup is deleted; the WordPress source is never rolled back here.
for scenario in ("upload-drift", "plugin-drift", "theme-addition",
                 "config-drift", "bootstrap-drift", "config-same-mtime",
                 "empty-dir-added", "empty-dir-replaced"):
    with tempfile.TemporaryDirectory() as temp:
        root, parent, fake = fixture(Path(temp))
        if scenario == "empty-dir-replaced":
            (root / "wp-content/uploads/empty").mkdir()

        def pack_then_drift(*args, **kwargs):
            result = real_pack(*args, **kwargs)
            if scenario == "upload-drift":
                (root / "wp-content/uploads/synthetic.txt").write_text("late upload change")
            elif scenario == "plugin-drift":
                (root / "wp-content/plugins/synthetic.txt").write_text("late plugin change")
            elif scenario == "theme-addition":
                (root / "wp-content/themes/late.txt").write_text("late theme addition")
            elif scenario == "empty-dir-added":
                (root / "wp-content/uploads/late-empty").mkdir()
            elif scenario == "empty-dir-replaced":
                empty = root / "wp-content/uploads/empty"
                empty.rename(root / "wp-content/old-empty-stashed")
                empty.mkdir()
            elif scenario == "config-drift":
                (root / "wp-config.php").write_text("<?php // late config change")
            elif scenario == "bootstrap-drift":
                (root / "wp-load.php").write_text("<?php // late bootstrap change")
            else:
                config = root / "wp-config.php"
                original = config.read_bytes()
                before = config.stat()
                config.write_bytes(b"X" + original[1:])
                os.utime(config, ns=(before.st_atime_ns, before.st_mtime_ns))
            return result

        with patch("ez2_wp_snapshot_capture.pack", side_effect=pack_then_drift):
            try:
                run(root, parent, fake)
            except ValueError as exc:
                assert "after archive packaging" in str(exc), str(exc)
                assert not (parent / "ez2-backup-test").exists()
                assert not any(x.name.startswith("ez2-capture-") for x in parent.iterdir())
                CASES += 1
            else:
                raise AssertionError("Post-packaging WordPress drift was accepted")

# Detect a table created or converted after packaging, even if all captured
# WordPress files and the runtime identity remain unchanged.
with tempfile.TemporaryDirectory() as temp:
    root, parent, fake = fixture(Path(temp))

    def pack_then_engine_drift(*args, **kwargs):
        result = real_pack(*args, **kwargs)
        (root / "wp-content" / ".engine-drift").write_text("synthetic")
        return result

    with patch("ez2_wp_snapshot_capture.pack", side_effect=pack_then_engine_drift):
        try:
            run(root, parent, fake, mode="engine_drift_after_pack")
        except ValueError as exc:
            assert "Database table inventory changed after archive packaging" in str(exc)
            assert not (parent / "ez2-backup-test").exists()
            CASES += 1
        else:
            raise AssertionError("Post-packaging database engine drift accepted")


# A private file copy must reject same-length source rewrites even when
# mtime is restored. These two races previously evaded size/mtime checks.
def rewrite_same_size_preserving_mtime(path):
    before = path.stat()
    data = path.read_bytes()
    assert data and data[0] != ord("X")
    path.write_bytes(b"X" + data[1:])
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    assert path.stat().st_mtime_ns == before.st_mtime_ns


from ez2_wp_snapshot_capture import _copy_component
import ez2_wp_snapshot_capture as capture_module

with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    source = base / "uploads"
    source.mkdir()
    file = source / "synthetic.txt"
    file.write_bytes(b"synthetic private image")
    original_files = capture_module._files

    def rewrite_after_enumeration(root, role):
        entries = original_files(root, role)
        rewrite_same_size_preserving_mtime(file)
        return entries

    with patch("ez2_wp_snapshot_capture._files", side_effect=rewrite_after_enumeration):
        try:
            _copy_component(source, base / "copy", "uploads")
        except ValueError as exc:
            assert "changed before capture" in str(exc)
            CASES += 1
        else:
            raise AssertionError("Timestamp-restored rewrite before copy accepted")

with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    source = base / "uploads"
    source.mkdir()
    file = source / "synthetic.txt"
    file.write_bytes(b"synthetic private image")
    original_open = Path.open

    def rewrite_during_copy(path, mode="r", *args, **kwargs):
        if mode == "xb" and path == base / "copy" / "synthetic.txt":
            rewrite_same_size_preserving_mtime(file)
        return original_open(path, mode, *args, **kwargs)

    with patch.object(Path, "open", new=rewrite_during_copy):
        try:
            _copy_component(source, base / "copy", "uploads")
        except ValueError as exc:
            assert "changed during capture" in str(exc)
            CASES += 1
        else:
            raise AssertionError("Timestamp-restored rewrite during copy accepted")


# The private copy must match the original bytes, not merely report
# that both file handles were successfully opened. Exercise both a short
# write and a same-length corrupt write without touching any WordPress site.
for scenario in ("short-write", "same-length-corruption"):
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        source = base / "uploads"
        source.mkdir()
        (source / "synthetic.txt").write_bytes(b"synthetic private image")
        destination = base / "copy"
        original_open = Path.open

        class AlteredCopyWriter:
            def __init__(self, wrapped):
                self.wrapped = wrapped
            def __enter__(self):
                self.wrapped.__enter__()
                return self
            def __exit__(self, *args):
                return self.wrapped.__exit__(*args)
            def __getattr__(self, name):
                return getattr(self.wrapped, name)
            def write(self, data):
                if scenario == "short-write":
                    return self.wrapped.write(data[:max(1, len(data) // 2)])
                return self.wrapped.write(bytes([data[0] ^ 1]) + data[1:])

        def corrupt_copy(path, mode="r", *args, **kwargs):
            opened = original_open(path, mode, *args, **kwargs)
            if path == destination / "synthetic.txt" and mode == "xb":
                return AlteredCopyWriter(opened)
            return opened

        with patch.object(Path, "open", new=corrupt_copy):
            try:
                _copy_component(source, destination, "uploads")
            except ValueError as exc:
                assert "Copied WordPress component differs from source" in str(exc), str(exc)
                CASES += 1
            else:
                raise AssertionError("Corrupt or truncated private copy accepted")


# A directory added while a private component is being copied must fail,
# even when every archived file remains unchanged.
with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    source = base / "uploads"
    source.mkdir()
    (source / "synthetic.txt").write_bytes(b"synthetic private image")
    destination = base / "copy"
    original_open = Path.open

    def add_empty_during_copy(path, mode="r", *args, **kwargs):
        if path == destination / "synthetic.txt" and mode == "xb":
            (source / "late-empty").mkdir()
        return original_open(path, mode, *args, **kwargs)

    with patch.object(Path, "open", new=add_empty_during_copy):
        try:
            _copy_component(source, destination, "uploads")
        except ValueError as exc:
            assert "directories changed during capture" in str(exc), str(exc)
            CASES += 1
        else:
            raise AssertionError("Directory drift during private copy was accepted")

assert CASES == 1 + 1 + 22 + 7 + 5 + 4 + 11 + 7 + 4 + 8 + 1 + 2 + 2 + 1, CASES
print(f"EZ2_WP_PRIVATE_CAPTURE_GUARD_PASS cases={CASES} fake_wp_cli=true live_wp_touched=false")
