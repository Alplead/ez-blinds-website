"""Synthetic ZIP regressions for the first-party release/durable journal bridge."""
import tempfile
import zipfile
from pathlib import Path

from ez2_ci_release_durable_recovery import FAULTS, RECOVERY_FAULTS, exercise

CASES = 0


def archive(path, folder, entrypoint):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(folder + '/' + entrypoint, 'synthetic candidate code')
        z.writestr(folder + '/assets/fixture.txt', 'synthetic candidate asset')
    return path


def reject(call):
    global CASES
    try:
        call()
    except (ValueError, OSError, zipfile.BadZipFile):
        CASES += 1
    else:
        raise AssertionError('Unsafe release bridge input accepted')


with tempfile.TemporaryDirectory(prefix='ez2-ci-release-durable-tests-') as tmp:
    base = Path(tmp)
    theme = archive(base / 'ezb-theme.zip', 'ezb-theme', 'style.css')
    core = archive(base / 'ezb-core.zip', 'ezb-core', 'ezb-core.php')
    for fault in FAULTS:
        for recovery_fault in RECOVERY_FAULTS:
            result = exercise([theme, core], fault=fault, recovery_fault=recovery_fault)
            assert result['status'] == 'EXACT_RELEASE_FIRST_PARTY_DURABLE_SCRATCH_ROLLBACK_PASS'
            assert result['first_party_archives_staged'] == 2
            assert result['journal_components_rehearsed'] == 3
            assert result['power_loss_injected'] == (fault is not None)
            assert result['recovery_power_loss_injected'] == (recovery_fault is not None)
            assert result['original_bytes_restored'] and result['synthetic_uploads_unchanged']
            assert not any(result[key] for key in ('elementor_plugin_installed',
                'database_restored', 'localwp_touched', 'can_apply', 'one_click_complete'))
            CASES += 1
    reject(lambda: exercise([theme]))
    for bad in (0, 7, True, '1', 1.0):
        reject(lambda value=bad: exercise([theme, core], fault=value))
    for bad in (0, 4, -1, True, '1', 1.0):
        reject(lambda value=bad: exercise([theme, core], recovery_fault=value))
    wrong = archive(base / 'wrong.zip', 'not-theme', 'style.css')
    reject(lambda: exercise([wrong, core]))
    malformed = base / 'malformed.zip'
    malformed.write_bytes(b'not a zip')
    reject(lambda: exercise([malformed, core]))
    linked = base / 'linked.zip'
    linked.symlink_to(theme)
    reject(lambda: exercise([linked, core]))
    missing = archive(base / 'missing.zip', 'ezb-core', 'not-entrypoint.php')
    reject(lambda: exercise([theme, missing]))
    assert theme.is_file() and core.is_file()

assert CASES == 44, CASES
print('EZ2_CI_RELEASE_DURABLE_BRIDGE_TEST_PASS cases=44 synthetic_only=true localwp_touched=false can_apply=false')
