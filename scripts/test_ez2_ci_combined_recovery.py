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
                                      restore_files, scratch_upgrade, snapshot, verify_applied_transaction, verify_release_bytes, verify_elementor_source)
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


# The combined transaction must start from the real disposable WordPress
# database with Elementor Free already activated, not a theme/core-only fixture.
with patch('ez2_ci_combined_recovery.sql',
           return_value=b'a:1:{i:0;s:23:"elementor/elementor.php";}') as db:
    assert verify_elementor_source() is True
    assert 'wordpress.wp_options' in db.call_args.args[0][1]
    CASES += 1
for invalid in (
    b'a:0:{}',
    b'a:1:{i:0;s:22:"elementor/elementor.php";}',
    b'a:2:{i:0;s:23:"elementor/elementor.php";i:1;s:32:"elementor-pro/elementor-pro.php";}',
):
    with patch('ez2_ci_combined_recovery.sql', return_value=invalid):
        expect_blocked(verify_elementor_source)

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

    # Both components must match the exact release ZIP, not merely contain
    # their expected entrypoint names. Owner uploads are outside this scope.
    assert verify_release_bytes(live, release) >= 3
    CASES += 1
    theme_file = live / 'themes/ezb-theme/style.css'
    original_theme = theme_file.read_bytes()
    theme_file.write_bytes(b'corrupted but still a valid file')
    expect_blocked(lambda: verify_release_bytes(live, release))
    theme_file.write_bytes(original_theme)
    unexpected = live / 'plugins/ezb-core/extra.php'
    unexpected.write_bytes(b'<?php // unapproved file')
    expect_blocked(lambda: verify_release_bytes(live, release))
    unexpected.unlink()
    theme_file.unlink()
    expect_blocked(lambda: verify_release_bytes(live, release))
    theme_file.write_bytes(original_theme)
    theme_dir = theme_file.parent
    aside = theme_dir.with_name('ezb-theme-aside')
    theme_dir.rename(aside)
    theme_dir.symlink_to(aside, target_is_directory=True)
    expect_blocked(lambda: verify_release_bytes(live, release))
    theme_dir.unlink()
    aside.rename(theme_dir)
    assert verify_release_bytes(live, release) >= 3
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
assert CASES == 41, CASES
print('EZ2_CI_COMBINED_ROLLBACK_GUARD_PASS cases=41 file_fault_scenarios=4')
