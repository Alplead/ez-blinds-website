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

from ez2_ci_file_upgrade import COMPONENTS, snapshot, unpack
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



BUNDLE_FAULTS = tuple(
    f'after_{ordinal}_{step}'
    for ordinal in ('first', 'second', 'third')
    for step in ('backup', 'install')
)


def rehearse_bundle(archive, lock, release, *, preexisting, fault=None, repo_root=None,
                    on_installed=None, inject_callback_fault=False):
    """Rehearse a single three-component file transaction in disposable scratch.

    Theme, EZB Core and checksum-pinned Elementor are staged together. Every
    interruption must restore all original files, including an absent plugin.
    This is not a WordPress/LocalWP updater and never accepts a write target.
    """
    if (type(preexisting) is not bool or fault not in (None, *BUNDLE_FAULTS)
            or (on_installed is not None and not callable(on_installed))
            or type(inject_callback_fault) is not bool
            or (inject_callback_fault and (on_installed is None or fault is not None))):
        raise ValueError('Invalid three-component scratch scenario')
    plugin = validate_lock(lock)
    archive = Path(archive)
    release = Path(release)
    if (archive.is_symlink() or not archive.is_file()
            or archive.name != f"{plugin['slug']}.{plugin['version']}.zip"
            or release.is_symlink() or not release.is_dir()):
        raise ValueError('Unsafe three-component source')
    checked = verify_archive(lock, archive.parent, repo_root=repo_root)
    if (len(checked['plugins']) != 1
            or not checked['plugins'][0]['checksum_verified']):
        raise ValueError('Pinned third-party ZIP was not verified')
    entries = (*COMPONENTS, (archive.name, 'plugins', plugin['slug'],
                             Path(plugin['entrypoint']).name))
    with tempfile.TemporaryDirectory(prefix='ez2-ci-three-component-', dir='/tmp') as temp:
        root = Path(temp)
        live, stage, backup = (root / name for name in ('live', 'stage', 'backup'))
        for directory in (live, stage, backup):
            directory.mkdir()
        for _, category, name, _ in COMPONENTS:
            original = live / category / name / 'owner-original.txt'
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(SENTINEL)
        if preexisting:
            original = live / 'plugins' / plugin['slug'] / 'owner-original.txt'
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(SENTINEL)
        upload = live / 'uploads' / '2026' / 'owner-private-placeholder.webp'
        upload.parent.mkdir(parents=True)
        upload.write_bytes(SENTINEL)
        sql_upload = live / 'uploads' / '2026' / 'owner-media.txt'
        sql_upload.write_bytes(b'synthetic upload preserved')
        unrelated = live / 'plugins' / 'unrelated' / 'unrelated.php'
        unrelated.parent.mkdir(parents=True)
        unrelated.write_bytes(SENTINEL)
        before = snapshot(live)

        for archive_name, category, name, entrypoint in COMPONENTS:
            destination = stage / category
            destination.mkdir(exist_ok=True)
            unpack(release / archive_name, destination, name)
            if not (destination / name / entrypoint).is_file():
                raise ValueError('Release component entrypoint missing')
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(stage / 'plugins')
        staged_plugin = stage / 'plugins' / plugin['slug']
        if (staged_plugin.is_symlink() or not staged_plugin.is_dir()
                or not (staged_plugin / Path(plugin['entrypoint']).name).is_file()):
            raise ValueError('Pinned plugin entrypoint missing')
        expected = {(category, name): snapshot(stage / category / name)
                    for _, category, name, _ in entries}
        if any(not files for files in expected.values()):
            raise ValueError('Empty three-component stage')

        operations, fault_seen, callback_executed = [], False, False
        try:
            for index, (_, category, name, _) in enumerate(entries):
                current = live / category / name
                saved = backup / category / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                existed = current.is_dir() and not current.is_symlink()
                if current.exists() and not existed:
                    raise ValueError('Unsafe scratch component')
                if existed:
                    os.replace(current, saved)
                operations.append((current, saved, existed))
                ordinal = ('first', 'second', 'third')[index]
                if fault == f'after_{ordinal}_backup':
                    raise RuntimeError('INJECTED_THREE_COMPONENT_FAULT')
                os.replace(stage / category / name, current)
                if fault == f'after_{ordinal}_install':
                    raise RuntimeError('INJECTED_THREE_COMPONENT_FAULT')
            for _, category, name, _ in entries:
                if snapshot(live / category / name) != expected[(category, name)]:
                    raise ValueError('Installed component bytes differ from verified stage')
            if (upload.read_bytes() != SENTINEL or unrelated.read_bytes() != SENTINEL
                    or sql_upload.read_bytes() != b'synthetic upload preserved'):
                raise ValueError('Unrelated scratch content changed')
            if on_installed is not None:
                on_installed(live, before)
                callback_executed = True
                if inject_callback_fault:
                    raise RuntimeError('INJECTED_THREE_DOMAIN_FAULT')
        except RuntimeError as exc:
            if str(exc) not in ('INJECTED_THREE_COMPONENT_FAULT', 'INJECTED_THREE_DOMAIN_FAULT'):
                raise
            fault_seen = True
        finally:
            for current, saved, existed in reversed(operations):
                if current.is_dir() and not current.is_symlink():
                    shutil.rmtree(current)
                elif current.exists() or current.is_symlink():
                    raise ValueError('Unsafe scratch rollback destination')
                if existed:
                    os.replace(saved, current)
        if (snapshot(live) != before or upload.read_bytes() != SENTINEL
                or unrelated.read_bytes() != SENTINEL
                or sql_upload.read_bytes() != b'synthetic upload preserved'
                or fault_seen != (fault is not None or inject_callback_fault)
                or callback_executed != (on_installed is not None and fault is None)):
            raise ValueError('Three-component scratch rollback mismatch')
        return {'preexisting': preexisting,
                'fault': fault or ('after_content_apply' if inject_callback_fault else 'none'),
                'callback_executed': callback_executed,
                'components': 3, 'files_verified': sum(map(len, expected.values())),
                'restored': True, 'uploads_preserved': True,
                'localwp_touched': False, 'one_click_complete': False}


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
        bundle_cases = [(False, None), (False, 'after_third_install'),
                        *((True, phase) for phase in (None, *BUNDLE_FAULTS))]
        bundle_results = [rehearse_bundle(archive, lock, REPO / '.release',
                                         preexisting=prior, fault=phase)
                          for prior, phase in bundle_cases]
    if (len(bundle_results) != 9
            or any(not item['restored'] or not item['uploads_preserved']
                   or item['components'] != 3 for item in bundle_results)):
        raise ValueError('Incomplete three-component scratch rollback matrix')
    print('EZ2_CI_THREE_COMPONENT_RECOVERY_PASS scenarios=9 faults=7 components=3 '
          'source_archives_verified=true scratch_bytes_restored=true '
          'uploads_preserved=true localwp_touched=false one_click_complete=false')
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
