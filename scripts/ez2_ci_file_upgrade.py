#!/usr/bin/env python3
"""Rehearse theme/core ZIP replacement and rollback in auto-deleted CI scratch.

This NEVER accepts a target site path. It is not a LocalWP updater, a database
restore, an Elementor installer, or a deployment authorization.
"""
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

from ez2_release_set import run as verify_release

COMPONENTS = (("ezb-theme.zip", "themes", "ezb-theme", "style.css"),
              ("ezb-core.zip", "plugins", "ezb-core", "ezb-core.php"))


def snapshot(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Linked scratch file refused")
        if path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def unpack(archive, dest, folder):
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_nlink != 1:
        raise ValueError("Unsafe release ZIP")
    seen, directory_casing, total, count = set(), {}, 0, 0
    # The eventual LocalWP consumer is Windows: reject NTFS aliases even
    # though the isolated Linux CI filesystem would accept these members.
    reserved = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.I)
    with zipfile.ZipFile(archive) as z:
        members = z.infolist()
        if not 1 <= len(members) <= 3000 or z.testzip() is not None:
            raise ValueError("Invalid ZIP inventory or CRC")
        for entry in members:
            name = entry.filename
            parts = name.rstrip("/").split("/")
            if (not name or "\\" in name or name.startswith("/")
                    or parts[0] != folder or any(p in ("", ".", "..") for p in parts)
                    or any(not re.fullmatch(r"[A-Za-z0-9._-]+", p) for p in parts)
                    or (len(parts) < 2 and not (entry.is_dir() and name == folder + "/"))
                    or len(name) > 240):
                raise ValueError("Unsafe release ZIP member")
            # Windows strips trailing dots and treats device names as
            # special files, including names with an extension (CON.txt).
            # Reject inconsistent casing of shared parent directories:
            # Linux could stage both, but Windows would merge them.
            for part in parts:
                if part.endswith(".") or reserved.fullmatch(part):
                    raise ValueError("Windows-unsafe ZIP member")
            for depth in range(1, len(parts)):
                prefix = "/".join(parts[:depth])
                folded_prefix = prefix.casefold()
                prior = directory_casing.setdefault(folded_prefix, prefix)
                if prior != prefix:
                    raise ValueError("Case-conflicting ZIP parent directory")
            folded = name.rstrip("/").casefold()
            if folded in seen:
                raise ValueError("Duplicate case-insensitive ZIP member")
            seen.add(folded)
            kind = stat.S_IFMT(entry.external_attr >> 16)
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError("ZIP links and special files forbidden")
            if entry.flag_bits & 1 or entry.compress_type not in (0, 8):
                raise ValueError("Unsupported ZIP member")
            if entry.is_dir():
                if kind == stat.S_IFREG:
                    raise ValueError("Directory/file mode mismatch")
                continue
            if kind == stat.S_IFDIR or entry.file_size > 4 * 1024 * 1024:
                raise ValueError("Unsafe file size or mode")
            total += entry.file_size
            count += 1
            if total > 24 * 1024 * 1024:
                raise ValueError("Expanded release too large")
            target = dest.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise ValueError("ZIP path collision")
            with z.open(entry) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
    if not count:
        raise ValueError("Empty release archive")


def exercise(archives, inject_failure=False, failure_phase=None):
    """Rehearse each file-swap interruption, then restore exact original bytes.

    Faults are synthetic and accepted only in an auto-deleted scratch site.
    The legacy inject_failure=True alias means after_first_install.
    """
    phases = ("after_first_backup", "after_first_install",
              "after_second_backup", "after_second_install")
    if failure_phase is None:
        failure_phase = "after_first_install" if inject_failure else None
    elif inject_failure or failure_phase not in phases:
        raise ValueError("Invalid or ambiguous scratch fault phase")
    with tempfile.TemporaryDirectory(prefix="ez2-ci-file-upgrade-") as temp:
        root = Path(temp)
        live, stage, backup = (root / name for name in ("live", "stage", "backup"))
        live.mkdir()
        stage.mkdir()
        backup.mkdir()
        for _, category, folder, _ in COMPONENTS:
            old = live / category / folder
            old.mkdir(parents=True)
            (old / "existing-owner-marker.txt").write_bytes(b"synthetic original, not owner data")
        uploads = live / "uploads" / "2026"
        uploads.mkdir(parents=True)
        (uploads / "synthetic-private-placeholder.txt").write_bytes(b"preserve unrelated files")
        original = snapshot(live)
        for (archive_name, category, folder, required), archive in zip(COMPONENTS, archives):
            destination = stage / category
            destination.mkdir(exist_ok=True)
            unpack(Path(archive), destination, folder)
            if not (destination / folder / required).is_file():
                raise ValueError("Missing required release entrypoint")
        # Verify every installed scratch byte, not only the two entrypoints.
        # Preserve unrelated existing files such as uploads without mutation.
        staged_files = snapshot(stage)
        expected_live = {
            name: digest for name, digest in original.items()
            if not any(name.startswith(f"{category}/{folder}/")
                       for _, category, folder, _ in COMPONENTS)
        }
        expected_live.update(staged_files)
        moved, fault_seen = [], False
        try:
            for index, (_, category, folder, _) in enumerate(COMPONENTS):
                current = live / category / folder
                saved = backup / category / folder
                saved.parent.mkdir(exist_ok=True)
                os.replace(current, saved)
                moved.append((current, saved))
                ordinal = ("first", "second")[index]
                if failure_phase == "after_" + ordinal + "_backup":
                    raise RuntimeError("INJECTED_SCRATCH_UPGRADE_FAILURE")
                os.replace(stage / category / folder, current)
                if failure_phase == "after_" + ordinal + "_install":
                    raise RuntimeError("INJECTED_SCRATCH_UPGRADE_FAILURE")
            for (_, category, folder, required), archive in zip(COMPONENTS, archives):
                if not (live / category / folder / required).is_file():
                    raise ValueError("Staged release not installed in scratch")
            if snapshot(live) != expected_live:
                raise ValueError("Installed scratch bytes differ from release or preserved files")
        except RuntimeError as exc:
            if str(exc) != "INJECTED_SCRATCH_UPGRADE_FAILURE":
                raise
            fault_seen = True
        finally:
            for current, saved in reversed(moved):
                if current.exists():
                    shutil.rmtree(current)
                os.replace(saved, current)
        if snapshot(live) != original:
            raise ValueError("Scratch rollback did not restore exact original file bytes")
        if fault_seen != (failure_phase is not None):
            raise ValueError("Fault rehearsal did not behave as requested")
        return {"status": "DISPOSABLE_FILE_ROLLBACK_VERIFIED",
                "fault_injected": fault_seen, "fault_phase": failure_phase or "none",
                "components": 2,
                "original_files_restored": True, "uploads_preserved": True,
                "localwp_touched": False, "database_restored": False,
                "deployment_authorized": False}


def main():
    if (len(sys.argv) != 3 or os.getenv("GITHUB_ACTIONS") != "true"
            or os.getenv("EZ2_CI_FILE_SWAP") != "YES_DISPOSABLE_RELEASE_ONLY"):
        raise ValueError("CI-only opt-in and RELEASE_DIR EXACT_SHA required")
    release = Path(sys.argv[1])
    sha = sys.argv[2]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid exact SHA")
    if release.resolve(strict=True) != (Path(__file__).resolve().parents[1] / ".release").resolve(strict=True):
        raise ValueError("Only exact-head CI release directory permitted")
    verify_release("verify", release, sha)
    archives = [release / entry[0] for entry in COMPONENTS]
    success = exercise(archives)
    phases = ("after_first_backup", "after_first_install",
              "after_second_backup", "after_second_install")
    failures = [exercise(archives, failure_phase=phase) for phase in phases]
    if (not success["original_files_restored"]
            or any(not result["fault_injected"]
                   or not result["original_files_restored"]
                   or not result["uploads_preserved"]
                   or result["fault_phase"] != phase
                   for phase, result in zip(phases, failures))):
        raise ValueError("Incomplete scratch upgrade rollback rehearsal")
    print("EZ2_CI_FILE_UPGRADE_ROLLBACK_PASS components=2 fault_recovered=true fault_scenarios=4 localwp_touched=false one_click_complete=false")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, zipfile.BadZipFile) as exc:
        print("EZ2_CI_FILE_UPGRADE_ROLLBACK_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
