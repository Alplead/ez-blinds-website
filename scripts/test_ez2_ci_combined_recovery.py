"""Offline regressions for CI-only cross-domain recovery. No Docker needed."""
import os
import stat
import json
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from ez2_ci_combined_recovery import (CLONE, SCRATCH_FAULT_PHASES, candidate_payload,
                                      exercise_swap_faults, gate, inject_content_fault,
                                      restore_files, scratch_upgrade, snapshot, verify_applied_transaction)
from ez2_content_candidate_bundle import package

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
    fault_root = root / 'fault-matrix'
    assert exercise_swap_faults(release, fault_root) == 4
    CASES += 1
    for phase in SCRATCH_FAULT_PHASES:
        recovered = fault_root / phase / 'live'
        assert (recovered / 'themes/ezb-theme/owner-original.txt').read_bytes() == b'synthetic owner fixture'
        assert (recovered / 'plugins/ezb-core/owner-original.txt').read_bytes() == b'synthetic owner fixture'
        assert (recovered / 'uploads/2026/owner-media.txt').read_bytes() == b'synthetic upload preserved'
        assert not (recovered / 'themes/ezb-theme/style.css').exists()
        CASES += 1
    expect_blocked(lambda: scratch_upgrade(release, root / 'invalid-fault',
                                           fault_phase='after_database_delete'))
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

# The actual committed public candidate, not a hand-written Elementor placeholder,
# must survive release archive verification before entering the disposable SQL clone.
with tempfile.TemporaryDirectory() as tmp:
    release = Path(tmp)
    sha = 'a' * 40
    source = (Path(__file__).resolve().parents[1] /
              'design/ez2-home-hero-candidate.json').read_bytes()
    candidate_zip = release / 'ez2-content-candidate.zip'
    candidate_zip.write_bytes(package(sha, source))
    payload = candidate_payload(release, sha)
    assert json.loads(payload) == json.loads(source)['content']
    CASES += 1
    expect_blocked(lambda: candidate_payload(release, 'b' * 40))
    candidate_zip.write_bytes(b'not a candidate zip')
    expect_blocked(lambda: candidate_payload(release, sha))

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

# Verify that the exact candidate bytes (including quotes) are stored intact,
# rather than accepting a manually invented Elementor-shaped SQL string.
with patch('ez2_ci_combined_recovery.sql',
           side_effect=[b'0', b'1', b'Home', b'0', b'',
                        b'EZ2 synthetic content fault', b'EZ2 synthetic body fault',
                        b'4', payload.hex().upper().encode()]) as fake_sql:
    assert inject_content_fault(CLONE, payload) == 1
    assert '0x' + payload.hex() in fake_sql.call_args_list[4].args[0][-1]
    assert 'HEX(meta_value)' in fake_sql.call_args_list[8].args[0][-1]
    CASES += 1
with patch('ez2_ci_combined_recovery.sql',
           side_effect=[b'0', b'1', b'Home', b'0', b'',
                        b'EZ2 synthetic content fault', b'EZ2 synthetic body fault',
                        b'4', b'00']):
    expect_blocked(lambda: inject_content_fault(CLONE, payload))

# Existing Elementor content on a synthetic page is a conflict, not update scope.
with patch('ez2_ci_combined_recovery.sql', side_effect=[b'0', b'1', b'Home', b'1']) as fake_sql:
    expect_blocked(lambda: inject_content_fault(CLONE))
    assert len(fake_sql.call_args_list) == 4



# A successful candidate must prove BOTH installed component bytes and the
# exact-head Elementor payload reached only the disposable database clone.
with tempfile.TemporaryDirectory() as tmp:
    live = Path(tmp)
    for category, name, entry in (('themes', 'ezb-theme', 'style.css'),
                                  ('plugins', 'ezb-core', 'ezb-core.php')):
        dest = live / category / name / entry
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b'synthetic release file')
    media = live / 'uploads/2026/owner-media.txt'
    media.parent.mkdir(parents=True)
    media.write_bytes(b'synthetic upload preserved')
    original = {'old/owner.txt': 'prior-snapshot'}
    source_digest = 'a' * 64
    observations = [
        b'http://ez2-ci-combined-fault.invalid',
        b'EZ2 synthetic content fault',
        b'EZ2 synthetic body fault',
        b'4',
        payload.hex().upper().encode('ascii'),
    ]
    with patch('ez2_ci_combined_recovery.digest', side_effect=['b' * 64, source_digest]), \
         patch('ez2_ci_combined_recovery.sql', side_effect=observations):
        assert verify_applied_transaction(live, original, source_digest, payload, 1)
    CASES += 1
    expect_blocked(lambda: verify_applied_transaction(live, original, source_digest, payload, 0))
    expect_blocked(lambda: verify_applied_transaction(live, original, source_digest, b'', 1))
    media.write_bytes(b'changed upload')
    expect_blocked(lambda: verify_applied_transaction(live, original, source_digest, payload, 1))
    media.write_bytes(b'synthetic upload preserved')
    (live / 'themes/ezb-theme/style.css').unlink()
    expect_blocked(lambda: verify_applied_transaction(live, original, source_digest, payload, 1))
    (live / 'themes/ezb-theme/style.css').write_bytes(b'synthetic release file')
    expect_blocked(lambda: verify_applied_transaction(live, snapshot(live), source_digest, payload, 1))
    with patch('ez2_ci_combined_recovery.digest', side_effect=['b' * 64, 'c' * 64]):
        expect_blocked(lambda: verify_applied_transaction(live, original, source_digest, payload, 1))
    with patch('ez2_ci_combined_recovery.digest', side_effect=['b' * 64, source_digest]), \
         patch('ez2_ci_combined_recovery.sql', side_effect=observations[:-1] + [b'00']):
        expect_blocked(lambda: verify_applied_transaction(live, original, source_digest, payload, 1))

assert CLONE == 'ez2_ci_combined_disposable'
CASES += 1
assert CASES == 32, CASES
print('EZ2_CI_COMBINED_ROLLBACK_GUARD_PASS cases=32 file_fault_scenarios=4')
