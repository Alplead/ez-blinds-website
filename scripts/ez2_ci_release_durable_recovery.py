#!/usr/bin/env python3
"""Bind real theme/core release ZIP bytes to crash-resumable scratch recovery.

CI-only transaction rehearsal, NOT a WordPress installer. Elementor is an
explicitly synthetic third component; this does not test plugin installation,
SQL, LocalWP, or Owner media. All writes use auto-deleted scratch.
"""
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

from ez2_ci_file_upgrade import COMPONENTS as FIRST_PARTY, snapshot, unpack
from ez2_release_set import run as verify_release
from ez2_scratch_durable_journal import (
    COMPONENTS, MAGIC, MARKER, _tree, apply, initialise, recover,
)

FAULTS = (None, 1, 2, 3, 4, 5, 6)


def exercise(archives, *, fault=None):
    """Test real first-party ZIP payloads through every journal crash point."""
    if not isinstance(archives, (list, tuple)) or len(archives) != 2:
        raise ValueError('Two first-party release ZIPs required')
    if fault not in FAULTS or (fault is not None and type(fault) is not int):
        raise ValueError('Invalid synthetic fault point')
    with tempfile.TemporaryDirectory(prefix='ez2-ci-release-durable-') as temp:
        root = Path(temp) / 'fixture'
        root.mkdir(mode=0o700)
        (root / MARKER).write_text(MAGIC, encoding='ascii')
        for name in ('live', 'stage', 'rollback'):
            (root / name).mkdir(mode=0o700)
        for archive, (_, category, folder, entrypoint) in zip(archives, FIRST_PARTY):
            old = root / 'live' / category / folder / 'original.txt'
            old.parent.mkdir(parents=True, exist_ok=True)
            old.write_bytes(('synthetic previous ' + folder).encode())
            unpack(Path(archive), root / 'stage' / category, folder)
            if not (root / 'stage' / category / folder / entrypoint).is_file():
                raise ValueError('Release entrypoint absent from scratch stage')
        # A synthetic sentinel tests the journal's third transition; the
        # real Elementor dependency is tested by separate CI runtime jobs.
        for section, body in (('live', b'synthetic previous plugin'),
                              ('stage', b'synthetic candidate plugin')):
            marker = root / section / 'plugins' / 'elementor' / 'fixture-only.txt'
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_bytes(body)
        owner = root / 'live' / 'uploads' / 'fixture-only.webp'
        owner.parent.mkdir(parents=True)
        owner.write_bytes(b'synthetic uploads must remain untouched')
        original = snapshot(root / 'live')
        candidate = {name: _tree(root / 'stage', name) for name in COMPONENTS}
        initialise(root)
        interrupted = False
        try:
            apply(root, interrupt_after=fault)
        except RuntimeError as exc:
            if str(exc) != 'SYNTHETIC_POWER_LOSS' or fault is None:
                raise
            interrupted = True
        if interrupted != (fault is not None):
            raise ValueError('Requested scratch interruption not observed')
        if fault is None and any(_tree(root / 'live', name) != candidate[name]
                                 for name in COMPONENTS):
            raise ValueError('Installed scratch payload differs from staged release')
        if owner.read_bytes() != b'synthetic uploads must remain untouched':
            raise ValueError('Synthetic uploads changed during scratch apply')
        receipt = recover(root)
        if receipt['status'] != 'SYNTHETIC_RECOVERY_VERIFIED' or not recover(root)['idempotent']:
            raise ValueError('Durable scratch recovery incomplete')
        if snapshot(root / 'live') != original:
            raise ValueError('Exact original scratch bytes not restored')
        if any((root / 'rollback' / name).exists() for name in COMPONENTS):
            raise ValueError('Uncleared scratch rollback slot')
        return {
            'status': 'EXACT_RELEASE_FIRST_PARTY_DURABLE_SCRATCH_ROLLBACK_PASS',
            'first_party_archives_staged': 2,
            'journal_components_rehearsed': 3,
            'power_loss_injected': interrupted,
            'original_bytes_restored': True,
            'synthetic_uploads_unchanged': True,
            'elementor_plugin_installed': False,
            'database_restored': False,
            'localwp_touched': False,
            'can_apply': False,
            'one_click_complete': False,
        }


def main():
    if (len(sys.argv) != 3 or os.getenv('GITHUB_ACTIONS') != 'true'
            or os.getenv('EZ2_CI_DURABLE_RELEASE') != 'YES_DISPOSABLE_RELEASE_ONLY'):
        raise ValueError('CI-only release rehearsal opt-in required')
    sha = sys.argv[2]
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Invalid exact-head SHA')
    release = Path(sys.argv[1])
    expected = Path(__file__).resolve().parents[1] / '.release'
    if release.is_symlink() or release.resolve(strict=True) != expected.resolve(strict=True):
        raise ValueError('Only CI release directory is allowed')
    catalog = verify_release('verify', release, sha)
    if (catalog['source_sha'] != sha or catalog['deployment_authorized'] is not False
            or catalog['localwp_installed'] is not False):
        raise ValueError('Release not safe for synthetic rehearsal')
    archives = [release / item[0] for item in FIRST_PARTY]
    receipts = [exercise(archives, fault=fault) for fault in FAULTS]
    if any(not r['original_bytes_restored'] or r['can_apply'] or r['localwp_touched']
           for r in receipts):
        raise ValueError('Incomplete durable release rehearsal')
    print('EZ2_CI_EXACT_RELEASE_DURABLE_ROLLBACK_PASS first_party=2 journal_components=3 '
          'fault_scenarios=6 elementor_installed=false localwp_touched=false can_apply=false')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, TypeError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
        print('EZ2_CI_EXACT_RELEASE_DURABLE_ROLLBACK_FAIL: ' + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
