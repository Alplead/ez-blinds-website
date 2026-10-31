"""Power-loss regression cases; writes only inside auto-deleted synthetic fixtures."""
import os
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

# A crash during journal rewrite can leave a partial .ez2-journal-next.
# Recovery must use the last committed journal plus observed file state.
for fault, partial in ((1, b''), (2, b'{"schema":'), (6, b'{"schema":1}')):
    with tempfile.TemporaryDirectory(prefix='ez2-journal-partial-') as tmp:
        root = Path(tmp) / 'fixture'
        owner = fixture(root)
        initialise(root)
        try:
            apply(root, interrupt_after=fault)
        except RuntimeError as exc:
            assert str(exc) == 'SYNTHETIC_POWER_LOSS'
        else:
            raise AssertionError('Expected injected interruption')
        (root / '.ez2-journal-next').write_bytes(partial)
        assert recover(root)['status'] == 'SYNTHETIC_RECOVERY_VERIFIED'
        assert not (root / '.ez2-journal-next').exists()
        assert owner.read_bytes() == b'synthetic owner fixture unchanged'
        assert recover(root)['idempotent']
        CASES += 1

# Do not unlink an attacker-supplied symlink, hardlink or oversized journal.
for unsafe in ('symlink', 'hardlink', 'oversize'):
    with tempfile.TemporaryDirectory(prefix='ez2-journal-unsafe-') as tmp:
        root = Path(tmp) / 'fixture'
        fixture(root)
        initialise(root)
        try:
            apply(root, interrupt_after=1)
        except RuntimeError as exc:
            assert str(exc) == 'SYNTHETIC_POWER_LOSS'
        else:
            raise AssertionError('Expected injected interruption')
        scratch = root / '.ez2-journal-next'
        if unsafe == 'symlink':
            scratch.symlink_to(root / MARKER)
        elif unsafe == 'hardlink':
            os.link(root / MARKER, scratch)
        else:
            scratch.write_bytes(b'x' * 8193)
        rejected(lambda: recover(root))
        assert scratch.exists() or scratch.is_symlink()
        scratch.unlink()
        assert recover(root)['status'] == 'SYNTHETIC_RECOVERY_VERIFIED'

# Recovery itself can lose power after any of the three component restores.
# The next invocation must finish from observed original/rollback bytes rather
# than assuming the previous recover() call reached its final journal write.
for missing in (False, True):
    for apply_fault in (None, *range(1, 7)):
        for recovery_fault in range(1, len(COMPONENTS) + 1):
            with tempfile.TemporaryDirectory(prefix='ez2-journal-recover-crash-') as tmp:
                root = Path(tmp) / 'fixture'
                owner = fixture(root, missing)
                initialise(root)
                if apply_fault is None:
                    apply(root)
                else:
                    try:
                        apply(root, interrupt_after=apply_fault)
                    except RuntimeError as exc:
                        assert str(exc) == 'SYNTHETIC_POWER_LOSS'
                    else:
                        raise AssertionError('Expected synthetic apply interruption')
                try:
                    recover(root, interrupt_after=recovery_fault)
                except RuntimeError as exc:
                    assert str(exc) == 'SYNTHETIC_RECOVERY_POWER_LOSS'
                else:
                    raise AssertionError('Expected synthetic recovery interruption')
                assert owner.read_bytes() == b'synthetic owner fixture unchanged'
                assert recover(root)['status'] == 'SYNTHETIC_RECOVERY_VERIFIED'
                assert recover(root)['idempotent']
                assert owner.read_bytes() == b'synthetic owner fixture unchanged'
                for name in COMPONENTS:
                    old = root / 'live' / name / 'old.txt'
                    assert old.is_file() == (not missing or name != 'plugins/elementor')
                    assert not (root / 'live' / name / 'new.txt').exists()
                    assert not (root / 'rollback' / name).exists()
                CASES += 1

with tempfile.TemporaryDirectory(prefix='ez2-journal-recover-args-') as tmp:
    root = Path(tmp) / 'fixture'
    fixture(root)
    initialise(root)
    for invalid in (0, 4, -1, True, 1.0, '1'):
        rejected(lambda value=invalid: recover(root, interrupt_after=value))

print(f'EZ2_SYNTHETIC_DURABLE_JOURNAL_PASS scenarios={CASES} power_loss=54 localwp_touched=false can_apply=false')
