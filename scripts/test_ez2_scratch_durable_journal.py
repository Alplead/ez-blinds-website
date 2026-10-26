"""Power-loss regression cases; writes only inside auto-deleted synthetic fixtures."""
import tempfile
from pathlib import Path
from ez2_scratch_durable_journal import MARKER, MAGIC, COMPONENTS, initialise, apply, recover

CASES = 0


def fixture(root, missing_plugin=False):
    root.mkdir()
    (root / MARKER).write_text(MAGIC, encoding='ascii')
    for name in ('live', 'stage', 'rollback'):
        (root / name).mkdir()
    for component in COMPONENTS:
        if not (missing_plugin and component == 'plugins/elementor'):
            old = root / 'live' / component / 'old.txt'
            old.parent.mkdir(parents=True)
            old.write_text('original ' + component)
        new = root / 'stage' / component / 'new.txt'
        new.parent.mkdir(parents=True)
        new.write_text('candidate ' + component)
    owner = root / 'live' / 'uploads' / 'owner-photo.webp'
    owner.parent.mkdir()
    owner.write_bytes(b'synthetic owner fixture unchanged')
    return owner


def rejected(fn):
    global CASES
    try: fn()
    except (ValueError, RuntimeError): CASES += 1
    else: raise AssertionError('Unsafe operation accepted')


for missing in (False, True):
    for fault in (None, *range(1, 7)):
        with tempfile.TemporaryDirectory(prefix='ez2-journal-') as tmp:
            root = Path(tmp) / 'fixture'
            owner = fixture(root, missing)
            initialise(root)
            if fault is None:
                result = apply(root)
                assert result['status'] == 'SYNTHETIC_FILES_INSTALLED_RECOVERY_REQUIRED'
                assert all((root / 'live' / name / 'new.txt').is_file() for name in COMPONENTS)
            else:
                rejected(lambda: apply(root, interrupt_after=fault))
            assert owner.read_bytes() == b'synthetic owner fixture unchanged'
            assert recover(root)['status'] == 'SYNTHETIC_RECOVERY_VERIFIED'
            assert recover(root)['idempotent']
            assert owner.read_bytes() == b'synthetic owner fixture unchanged'
            for name in COMPONENTS:
                old = root / 'live' / name / 'old.txt'
                assert old.is_file() == (not missing or name != 'plugins/elementor')
                assert not (root / 'live' / name / 'new.txt').exists()
            CASES += 1

with tempfile.TemporaryDirectory(prefix='ez2-journal-reject-') as tmp:
    root = Path(tmp) / 'fixture'
    fixture(root)
    rejected(lambda: apply(root))  # no journal
    initialise(root)
    rejected(lambda: initialise(root))
    rejected(lambda: apply(root, interrupt_after=0))
    (root / 'stage' / COMPONENTS[0] / 'new.txt').write_text('tampered candidate')
    rejected(lambda: apply(root))
    assert recover(root)['status'] == 'SYNTHETIC_RECOVERY_VERIFIED'
    CASES += 1

with tempfile.TemporaryDirectory(prefix='ez2-journal-drift-') as tmp:
    root = Path(tmp) / 'fixture'
    fixture(root)
    initialise(root)
    rejected(lambda: apply(root, interrupt_after=2))
    (root / 'live' / COMPONENTS[0] / 'new.txt').write_text('unknown owner edit')
    rejected(lambda: recover(root))
    assert (root / 'rollback' / COMPONENTS[0] / 'old.txt').is_file()
    CASES += 1

with tempfile.TemporaryDirectory(prefix='ez2-journal-safety-') as tmp:
    root = Path(tmp) / 'fixture'
    fixture(root)
    (root / 'wp-config.php').write_text('<?php')
    rejected(lambda: initialise(root))
    (root / 'wp-config.php').unlink()
    (root / '.git').mkdir()
    rejected(lambda: initialise(root))
    (root / '.git').rmdir()
    (root / MARKER).write_text('not a valid synthetic marker')
    rejected(lambda: initialise(root))
    CASES += 1

print(f'EZ2_SYNTHETIC_DURABLE_JOURNAL_PASS scenarios={CASES} power_loss=12 localwp_touched=false can_apply=false')
