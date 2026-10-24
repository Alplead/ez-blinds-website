"""Offline scratch file-swap regression fixtures. No real site path is accepted."""
import io
import os
import stat
import tempfile
import zipfile
from pathlib import Path
from ez2_ci_file_upgrade import exercise

CASES = 0


def archive(root, name, members):
    path = root / name
    with zipfile.ZipFile(path, "w") as z:
        for filename, content, mode in members:
            entry = zipfile.ZipInfo(filename)
            entry.external_attr = mode << 16
            z.writestr(entry, content)
    return path


def fixtures(root):
    return (
        archive(root, "ezb-theme.zip", [
            ("ezb-theme/style.css", b"Theme Name: EZB Theme", stat.S_IFREG | 0o644),
            ("ezb-theme/theme.json", b"{}", stat.S_IFREG | 0o644)]),
        archive(root, "ezb-core.zip", [
            ("ezb-core/ezb-core.php", b"<?php // synthetic", stat.S_IFREG | 0o644)]),
    )


def reject(mutator, label):
    global CASES
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a, b = fixtures(root)
        mutator(root, a, b)
        try:
            exercise((a, b))
        except (ValueError, OSError, zipfile.BadZipFile):
            CASES += 1
            return
        raise AssertionError("Unsafe archive accepted: " + label)


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    a, b = fixtures(root)
    archive(root, a.name, [
        ("ezb-theme/", b"", stat.S_IFDIR | 0o755),
        ("ezb-theme/style.css", b"Theme Name: EZB Theme", stat.S_IFREG | 0o644),
        ("ezb-theme/theme.json", b"{}", stat.S_IFREG | 0o644)])
    assert exercise((a, b))["original_files_restored"]
    CASES += 1

with tempfile.TemporaryDirectory() as tmp:
    a, b = fixtures(Path(tmp))
    result = exercise((a, b))
    assert result["original_files_restored"] and result["uploads_preserved"]
    assert result["localwp_touched"] is False and result["database_restored"] is False
    CASES += 1
    for phase in ("after_first_backup", "after_first_install",
                  "after_second_backup", "after_second_install"):
        failed = exercise((a, b), failure_phase=phase)
        assert failed["fault_injected"] and failed["original_files_restored"]
        assert failed["uploads_preserved"] and failed["fault_phase"] == phase
        CASES += 1
    assert exercise((a, b), inject_failure=True)["fault_phase"] == "after_first_install"
    CASES += 1
    try:
        exercise((a, b), inject_failure=True, failure_phase="after_second_install")
    except ValueError:
        CASES += 1
    else:
        raise AssertionError("Ambiguous fault injection accepted")

reject(lambda r, a, b: a.write_bytes(b"invalid"), "corrupt ZIP")
reject(lambda r, a, b: a.unlink(), "missing ZIP")
reject(lambda r, a, b: archive(r, a.name, [("../escape", b"bad", stat.S_IFREG | 0o644)]), "traversal")
reject(lambda r, a, b: archive(r, a.name, [("wrong/style.css", b"bad", stat.S_IFREG | 0o644)]), "wrong root")
reject(lambda r, a, b: archive(r, a.name, [
    ("ezb-theme/style.css", b"one", stat.S_IFREG | 0o644),
    ("ezb-theme/STYLE.CSS", b"two", stat.S_IFREG | 0o644)]), "Windows collision")
reject(lambda r, a, b: archive(r, a.name, [
    ("ezb-theme/style.css", b"target", stat.S_IFLNK | 0o777)]), "symlink member")
reject(lambda r, a, b: archive(r, a.name, [
    ("ezb-theme/other.txt", b"no entrypoint", stat.S_IFREG | 0o644)]), "missing entrypoint")
reject(lambda r, a, b: archive(r, a.name, [
    ("ezb-theme/style.css", b"x" * (4 * 1024 * 1024 + 1), stat.S_IFREG | 0o644)]), "oversized entry")
reject(lambda r, a, b: archive(r, a.name, []), "empty ZIP")
def symlink_archive(root, a, b):
    a.unlink()
    a.symlink_to(b)
reject(symlink_archive, "linked ZIP")
assert CASES == 18, CASES
print("EZ2_CI_FILE_UPGRADE_REGRESSION_PASS cases=18")
