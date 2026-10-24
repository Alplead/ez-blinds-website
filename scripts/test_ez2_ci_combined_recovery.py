"""Offline regressions for CI-only cross-domain recovery. No Docker needed."""
import os
import stat
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from ez2_ci_combined_recovery import CLONE, gate, restore_files, scratch_upgrade, snapshot

CASES = 0


def expect_blocked(action):
    global CASES
    try:
        action()
    except (ValueError, OSError, zipfile.BadZipFile):
        CASES += 1
    else:
        raise AssertionError('Unsafe recovery precondition accepted')


for env in ({}, {'GITHUB_ACTIONS': 'true'},
            {'EZ2_CI_COMBINED_ROLLBACK': 'YES_DISPOSABLE_STACK_ONLY'},
            {'GITHUB_ACTIONS': 'true', 'EZ2_CI_COMBINED_ROLLBACK': 'wrong'}):
    with patch.dict(os.environ, env, clear=True):
        expect_blocked(lambda: gate('/tmp/not-release', 'a' * 40))


def make_zip(path, entries):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, payload in entries:
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payload)


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    release = root / 'release'
    release.mkdir()
    make_zip(release / 'ezb-theme.zip', [('ezb-theme/style.css', b'Theme Name: EZB'),
                                         ('ezb-theme/theme.json', b'{}')])
    make_zip(release / 'ezb-core.zip', [('ezb-core/ezb-core.php', b'<?php // synthetic')])
    work = root / 'work'
    work.mkdir()
    live, before, moved = scratch_upgrade(release, work)
    assert snapshot(live) != before
    assert (live / 'uploads/2026/owner-media.txt').read_bytes() == b'synthetic upload preserved'
    CASES += 1
    restore_files(moved)
    assert snapshot(live) == before
    CASES += 1
    assert not any((work / 'backup').rglob('owner-original.txt'))
    CASES += 1
    try:
        restore_files(moved)
    except ValueError:
        CASES += 1
    else:
        raise AssertionError('Second rollback should refuse missing backup')
    (release / 'ezb-theme.zip').write_bytes(b'not a ZIP')
    bad = root / 'bad'
    bad.mkdir()
    expect_blocked(lambda: scratch_upgrade(release, bad))

assert CLONE == 'ez2_ci_combined_disposable'
CASES += 1
assert CASES == 10, CASES
print('EZ2_CI_COMBINED_ROLLBACK_GUARD_PASS cases=10')
