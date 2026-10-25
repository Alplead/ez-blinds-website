#!/usr/bin/env python3
"""CI-only Elementor ZIP file-swap/rollback rehearsal on disposable scratch.

This does not update an installed WordPress site or the Owner's LocalWP. A
separate disposable WordPress smoke proves runtime activation; this rehearsal
covers pinned third-party plugin *files* and failure recovery only.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from ez2_ci_file_upgrade import snapshot
from ez2_ci_pinned_plugin_install import REPO, LOCK_PATH, download_verified, validate_lock, wp
from ez2_plugin_archive_verify import verify as verify_archive
from ez2_plugin_dependency_check import read as read_lock
from ez2_release_set import run as verify_release

FAULTS = ('after_backup', 'after_install')
SENTINEL = b'synthetic owner-owned fixture, not real content'


def rehearse(archive, lock, *, preexisting, fault=None, repo_root=None):
    """Install verified plugin bytes into scratch, then restore previous state.

    Both an existing plugin and a fresh install are rehearsed. No site path is
    accepted: the only writable target is an auto-deleted temporary directory.
    """
    if type(preexisting) is not bool or fault not in (None, *FAULTS):
        raise ValueError('Invalid scratch recovery scenario')
    plugin = validate_lock(lock)
    archive = Path(archive)
    root = archive.parent.resolve(strict=True)
    expected_name = f"{plugin['slug']}.{plugin['version']}.zip"
    if archive.name != expected_name or archive.is_symlink() or not archive.is_file():
        raise ValueError('Unsafe pinned plugin archive')
    verified = verify_archive(lock, root, repo_root=repo_root)
    if len(verified['plugins']) != 1 or not verified['plugins'][0]['checksum_verified']:
        raise ValueError('Unverified pinned plugin ZIP')
    with tempfile.TemporaryDirectory(prefix='ez2-ci-plugin-recovery-', dir='/tmp') as temp:
        scratch = Path(temp)
        live = scratch / 'live'
        stage = scratch / 'stage'
        backup = scratch / 'backup'
        for parent in (live / 'plugins', stage / 'plugins', backup / 'plugins'):
            parent.mkdir(parents=True)
        plugin_dir = live / 'plugins' / plugin['slug']
        if preexisting:
            plugin_dir.mkdir()
            (plugin_dir / 'old-version.txt').write_bytes(SENTINEL)
        unrelated = live / 'plugins' / 'ezb-core' / 'ezb-core.php'
        unrelated.parent.mkdir()
        unrelated.write_bytes(SENTINEL)
        upload = live / 'uploads' / '2026' / 'private-placeholder.webp'
        upload.parent.mkdir(parents=True)
        upload.write_bytes(SENTINEL)
        before = snapshot(live)
        # The archive has already passed a full ZIP member/path/CRC check.
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(stage / 'plugins')
        staged = stage / 'plugins' / plugin['slug']
        entry = staged / Path(plugin['entrypoint']).name
        if not entry.is_file() or staged.is_symlink():
            raise ValueError('Verified plugin entrypoint missing from scratch stage')
        expected = snapshot(staged)
        if not expected:
            raise ValueError('Empty staged plugin')
        saved = backup / 'plugins' / plugin['slug']
        moved, installed, fault_seen = False, False, False
        try:
            if preexisting:
                os.replace(plugin_dir, saved)
                moved = True
            if fault == 'after_backup':
                raise RuntimeError('INJECTED_PLUGIN_SCRATCH_FAULT')
            os.replace(staged, plugin_dir)
            installed = True
            if fault == 'after_install':
                raise RuntimeError('INJECTED_PLUGIN_SCRATCH_FAULT')
            if snapshot(plugin_dir) != expected:
                raise ValueError('Staged pinned plugin differs from installed scratch bytes')
            if upload.read_bytes() != SENTINEL or unrelated.read_bytes() != SENTINEL:
                raise ValueError('Unrelated scratch data changed')
        except RuntimeError as exc:
            if str(exc) != 'INJECTED_PLUGIN_SCRATCH_FAULT':
                raise
            fault_seen = True
        finally:
            if installed and plugin_dir.exists():
                shutil.rmtree(plugin_dir)
            if moved:
                os.replace(saved, plugin_dir)
        if snapshot(live) != before or upload.read_bytes() != SENTINEL:
            raise ValueError('Plugin scratch rollback did not restore exact bytes')
        if fault_seen != (fault is not None):
            raise ValueError('Plugin scratch fault injection was not observed')
        return {'preexisting': preexisting, 'fault': fault or 'none',
                'files_verified': len(expected), 'restored': True,
                'uploads_preserved': True, 'localwp_touched': False}


def main(exact_sha):
    if (os.getenv('GITHUB_ACTIONS') != 'true'
            or os.getenv('EZ2_CI_PINNED_PLUGIN_RECOVERY') != 'YES_DISPOSABLE_SCRATCH_ONLY'
            or not re.fullmatch(r'[0-9a-f]{40}', exact_sha)):
        raise ValueError('Explicit CI-only exact-SHA plugin recovery opt-in required')
    if subprocess.check_output(('git', 'rev-parse', 'HEAD'), cwd=REPO, text=True).strip() != exact_sha:
        raise ValueError('CI checkout is not the exact requested SHA')
    verify_release('verify', REPO / '.release', exact_sha)
    if (wp('option', 'get', 'home').stdout.strip() != 'http://localhost:8081'
            or wp('eval', 'echo wp_get_environment_type();').stdout.strip() != 'staging'
            or wp('plugin', 'get', 'elementor', '--field=version').stdout.strip() != '4.3.4'
            or wp('plugin', 'is-active', 'elementor').returncode != 0):
        raise ValueError('Disposable Elementor release fixture not active')
    lock = read_lock(LOCK_PATH)
    with tempfile.TemporaryDirectory(prefix='ez2-ci-pinned-recovery-zip-', dir='/tmp') as temp:
        archive = download_verified(lock, temp)
        results = [rehearse(archive, lock, preexisting=prior, fault=phase)
                   for prior in (False, True) for phase in (None, *FAULTS)]
    if len(results) != 6 or not all(x['restored'] and x['uploads_preserved'] for x in results):
        raise ValueError('Incomplete pinned plugin rollback matrix')
    print('EZ2_CI_PINNED_PLUGIN_RECOVERY_PASS scenarios=6 faults=4 '
          'pinned_archive_verified=true scratch_bytes_restored=true '
          'uploads_preserved=true localwp_touched=false one_click_complete=false')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('Usage: ez2_ci_pinned_plugin_recovery.py EXACT_HEAD_SHA')
        main(sys.argv[1])
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, zipfile.BadZipFile,
            subprocess.CalledProcessError) as exc:
        print('EZ2_CI_PINNED_PLUGIN_RECOVERY_FAIL: ' + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
