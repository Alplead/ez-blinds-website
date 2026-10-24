"""Synthetic fail-closed tests for exact-head release candidate CI staging."""
import io
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch
from ez2_ci_candidate_from_release import stage, OUTPUT
import ez2_ci_candidate_from_release as target

SHA = 'a' * 40
PAYLOAD = b'{"title":"Synthetic public candidate"}'
CASES = 0


def candidate_zip(payload=PAYLOAD):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as zipped:
        zipped.writestr('elementor/home-hero.json', payload)
    return stream.getvalue()


def catalog(**changes):
    doc = {'source_sha': SHA, 'target_site': 'ez2-isolated-only',
           'one_click_complete': False, 'elementor_candidate_installable': False,
           'private_media_included': False, 'deployment_authorized': False,
           'localwp_installed': False, 'third_party_plugins_included': False}
    doc.update(changes)
    return doc


def setup(root):
    (root / 'ez2-content-candidate.zip').write_bytes(candidate_zip())


def run(root, expected=PAYLOAD, metadata=None):
    with patch.object(target, 'verify_release_set', return_value=catalog() if metadata is None else metadata), \
         patch.object(target, 'verify_candidate', return_value={'source_sha': SHA}):
        return stage(root, SHA, expected)


def reject(action):
    global CASES
    try:
        action()
    except (ValueError, OSError, KeyError, zipfile.BadZipFile):
        CASES += 1
        return
    raise AssertionError('Unsafe candidate input accepted')


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    setup(root)
    info = run(root)
    assert info['source_sha'] == SHA and info['localwp_installed'] is False
    assert (root / OUTPUT).read_bytes() == PAYLOAD
    assert os.stat(root / OUTPUT).st_mode & 0o077 == 0
    CASES += 1
    reject(lambda: run(root))

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    setup(root)
    reject(lambda: run(root, b'changed'))
    reject(lambda: run(root, b''))
    reject(lambda: run(root, metadata=catalog(source_sha='b' * 40)))
    reject(lambda: run(root, metadata=catalog(target_site='ez-bns-new-dev.local')))
    reject(lambda: run(root, metadata=catalog(one_click_complete=True)))
    reject(lambda: run(root, metadata=catalog(private_media_included=True)))
    reject(lambda: run(root, metadata=catalog(deployment_authorized=True)))
    reject(lambda: run(root, metadata=catalog(elementor_candidate_installable=True)))
    reject(lambda: run(root, metadata=catalog(localwp_installed=True)))
    reject(lambda: run(root, metadata=catalog(third_party_plugins_included=True)))
    (root / OUTPUT).symlink_to(root / 'ez2-content-candidate.zip')
    reject(lambda: run(root))

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    setup(root)
    (root / 'ez2-content-candidate.zip').write_bytes(b'not a zip')
    reject(lambda: run(root))

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    setup(root)
    (root / 'ez2-content-candidate.zip').unlink()
    (root / 'ez2-content-candidate.zip').symlink_to(root / 'missing.zip')
    reject(lambda: run(root))

assert CASES == 15, CASES
print(f'EZ2_RELEASE_RUNTIME_INPUT_REGRESSION_PASS cases={CASES}')
