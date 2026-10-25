"""Offline scratch-only tests for third-party pinned-plugin rollback."""
import copy
import hashlib
import io
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from ez2_ci_pinned_plugin_recovery import rehearse, main

CASES = 0


def blocked(fn):
    global CASES
    try:
        fn()
    except (OSError, ValueError):
        CASES += 1
    else:
        raise AssertionError('Unsafe plugin recovery input accepted')


def make_archive():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('elementor/elementor.php',
                   '<?php\n/*\nPlugin Name: Elementor\nVersion: 4.3.4\n*/\n')
        z.writestr('elementor/readme.txt', 'Synthetic CI fixture')
    return stream.getvalue()


with tempfile.TemporaryDirectory(prefix='ez2-plugin-recovery-tests-') as tmp:
    root = Path(tmp)
    data = make_archive()
    archive = root / 'elementor.4.3.4.zip'
    archive.write_bytes(data)
    lock = {'schema_version': 1, 'target_site': 'ez2-isolated-only',
            'plugins': [{'slug': 'elementor', 'version': '4.3.4',
                         'entrypoint': 'elementor/elementor.php',
                         'source': 'wordpress.org', 'activate': True,
                         'archive_sha256': hashlib.sha256(data).hexdigest()}]}
    for prior in (False, True):
        for phase in (None, 'after_backup', 'after_install'):
            result = rehearse(archive, lock, preexisting=prior, fault=phase)
            assert result['restored'] and result['uploads_preserved']
            assert result['files_verified'] == 2
            assert result['preexisting'] == prior
            CASES += 1
    blocked(lambda: rehearse(archive, lock, preexisting=1))
    blocked(lambda: rehearse(archive, lock, preexisting=True, fault='unknown'))
    wrong = copy.deepcopy(lock)
    wrong['plugins'][0]['archive_sha256'] = 'f' * 64
    blocked(lambda: rehearse(archive, wrong, preexisting=True))
    archive.write_bytes(b'not a ZIP')
    blocked(lambda: rehearse(archive, lock, preexisting=False))
    archive.write_bytes(data)
    link = root / 'other.zip'
    link.symlink_to(archive)
    blocked(lambda: rehearse(link, lock, preexisting=False))
    blocked(lambda: rehearse(root / 'missing.zip', lock, preexisting=False))

with patch.dict(os.environ, {}, clear=True):
    blocked(lambda: main('a' * 40))
with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true',
                             'EZ2_CI_PINNED_PLUGIN_RECOVERY': 'YES_DISPOSABLE_SCRATCH_ONLY'}):
    blocked(lambda: main('invalid'))

assert CASES == 14, CASES
print('EZ2_CI_PINNED_PLUGIN_RECOVERY_GUARD_PASS cases=14')
