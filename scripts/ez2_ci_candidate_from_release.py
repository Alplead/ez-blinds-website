#!/usr/bin/env python3
"""Stage the Elementor candidate from the verified delivery envelope for disposable CI only."""
import hashlib
import io
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from ez2_content_candidate_bundle import NAME, SOURCE, verify as verify_candidate
from ez2_release_set import run as verify_release_set

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = 'ez2-runtime-candidate.json'


def stage(release_dir, sha, expected_source):
    root = Path(release_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Unsafe release directory')
    if not isinstance(expected_source, bytes) or not expected_source:
        raise ValueError('Missing committed candidate bytes')
    output = root / OUTPUT
    if output.is_symlink() or output.exists():
        raise ValueError('Refusing to overwrite staged candidate')
    catalog = verify_release_set('verify', root, sha)
    for key, value in (
        ('source_sha', sha), ('target_site', 'ez2-isolated-only'),
        ('one_click_complete', False), ('elementor_candidate_installable', False),
        ('private_media_included', False), ('deployment_authorized', False),
        ('localwp_installed', False), ('third_party_plugins_included', False),
    ):
        if catalog.get(key) != value or (isinstance(value, bool) and catalog.get(key) is not value):
            raise ValueError('Unsafe or mismatched release catalog: ' + key)
    # A single envelope must supply theme, core, pinned dependency AND content.
    # The original release remains a separate exact-head parity witness.
    envelope_dir = root / 'ez2-envelope-install-input'
    if envelope_dir.is_symlink() or not envelope_dir.is_dir():
        raise ValueError('Verified envelope install inputs required')
    source_archive = root / 'ez2-content-candidate.zip'
    envelope_archive = envelope_dir / 'ez2-content-candidate.zip'
    for path in (source_archive, envelope_archive):
        if (path.is_symlink() or not path.is_file()
                or path.stat().st_nlink != 1
                or not 0 < path.stat().st_size <= 64 * 1024 * 1024):
            raise ValueError('Unsafe exact-head candidate archive')
    archive = envelope_archive.read_bytes()
    if archive != source_archive.read_bytes():
        raise ValueError('Envelope candidate differs from exact-head release')
    verify_candidate(sha, archive)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        payload = zipped.read(NAME)
    if payload != expected_source:
        raise ValueError('Candidate differs from committed exact-head source')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    fd = os.open(output, flags, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return {'status': 'DISPOSABLE_RUNTIME_INPUT_ONLY', 'source_sha': sha,
            'sha256': hashlib.sha256(payload).hexdigest(),
            'private_media_included': False, 'localwp_installed': False,
            'deployment_authorized': False}


def main(args):
    if len(args) != 3:
        raise ValueError('Usage: SCRIPT RELEASE_DIR EXACT_SHA')
    release_dir, sha = Path(args[1]), args[2]
    if release_dir.resolve(strict=True) != (ROOT / '.release').resolve(strict=True):
        raise ValueError('Only dedicated CI release directory permitted')
    current = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    if current != sha:
        raise ValueError('Checked-out HEAD differs from expected SHA')
    committed = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{sha}:{SOURCE}'])
    result = stage(release_dir, sha, committed)
    print('EZ2_RELEASE_CANDIDATE_RUNTIME_PASS source_sha=' + result['source_sha'])


if __name__ == '__main__':
    try:
        main(sys.argv)
    except (OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print('EZ2_RELEASE_CANDIDATE_RUNTIME_FAIL: ' + str(exc), file=sys.stderr)
        sys.exit(1)
