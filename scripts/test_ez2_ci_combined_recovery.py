"""Offline regressions for CI-only cross-domain recovery. No Docker needed."""
import os
import stat
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from ez2_ci_combined_recovery import CLONE, gate, inject_content_fault, restore_files, scratch_upgrade, snapshot

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

# Reject a fault directed at the installed WordPress database.
with patch('ez2_ci_combined_recovery.sql') as forbidden_sql:
    expect_blocked(lambda: inject_content_fault('wordpress'))
    forbidden_sql.assert_not_called()

# Prove the synthetic content mutation targets the clone exclusively.
with patch('ez2_ci_combined_recovery.sql',
           side_effect=[b'0', b'1', b'Home', b'0', b'', b'EZ2 synthetic content fault', b'EZ2 synthetic body fault', b'4']) as fake_sql:
    assert inject_content_fault(CLONE) == 1
    calls = [call.args[0][-1] for call in fake_sql.call_args_list]
    assert len(calls) == 8
    assert all('`ez2_ci_combined_disposable`' in query for query in calls)
    assert all('`wordpress`' not in query for query in calls)
    assert '_ez2_ci_transaction_fault' in calls[4]
    assert '_elementor_data' in calls[4] and '_elementor_page_settings' in calls[4]
    assert 'post_content=' in calls[4]
    CASES += 1

# Existing Elementor content on a synthetic page is a conflict, not update scope.
with patch('ez2_ci_combined_recovery.sql', side_effect=[b'0', b'1', b'Home', b'1']) as fake_sql:
    expect_blocked(lambda: inject_content_fault(CLONE))
    assert len(fake_sql.call_args_list) == 4

assert CLONE == 'ez2_ci_combined_disposable'
CASES += 1
assert CASES == 13, CASES
print('EZ2_CI_COMBINED_ROLLBACK_GUARD_PASS cases=13')
