"""Offline tests for a single three-component theme/core/Elementor transaction."""
import copy
import hashlib
import io
import tempfile
import zipfile
from pathlib import Path

from ez2_ci_pinned_plugin_recovery import BUNDLE_FAULTS, rehearse_bundle

CASES = 0


def zipped(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return output.getvalue()


def blocked(action):
    global CASES
    try:
        action()
    except (ValueError, OSError, zipfile.BadZipFile):
        CASES += 1
    else:
        raise AssertionError('Unsafe three-component transaction was accepted')


with tempfile.TemporaryDirectory(prefix='ez2-three-component-tests-') as temp:
    root = Path(temp)
    release = root / 'release'
    release.mkdir()
    (release / 'ezb-theme.zip').write_bytes(zipped([
        ('ezb-theme/style.css', b'Theme Name: EZB'),
        ('ezb-theme/theme.json', b'{}')]))
    (release / 'ezb-core.zip').write_bytes(zipped([
        ('ezb-core/ezb-core.php', b'<?php // synthetic')]))
    plugin_raw = zipped([
        ('elementor/elementor.php',
         b'<?php\n/*\nPlugin Name: Elementor\nVersion: 4.3.4\n*/\n'),
        ('elementor/readme.txt', b'Synthetic offline fixture')])
    plugin = root / 'elementor.4.3.4.zip'
    plugin.write_bytes(plugin_raw)
    lock = {'schema_version': 1, 'target_site': 'ez2-isolated-only',
            'plugins': [{'slug': 'elementor', 'version': '4.3.4',
                         'entrypoint': 'elementor/elementor.php',
                         'source': 'wordpress.org', 'activate': True,
                         'archive_sha256': hashlib.sha256(plugin_raw).hexdigest()}]}
    for preexisting in (False, True):
        for phase in (None, *BUNDLE_FAULTS):
            result = rehearse_bundle(plugin, lock, release,
                                     preexisting=preexisting, fault=phase)
            assert result['restored'] and result['uploads_preserved']
            assert result['components'] == 3 and result['files_verified'] == 5
            assert not result['localwp_touched'] and not result['one_click_complete']
            assert result['fault'] == (phase or 'none')
            CASES += 1
    blocked(lambda: rehearse_bundle(plugin, lock, release, preexisting=1))
    blocked(lambda: rehearse_bundle(plugin, lock, release, preexisting=True,
                                   fault='after_fourth_install'))
    wrong = copy.deepcopy(lock)
    wrong['plugins'][0]['archive_sha256'] = 'f' * 64
    blocked(lambda: rehearse_bundle(plugin, wrong, release, preexisting=True))
    plugin_link = root / 'elementor.4.3.4.zip.link'
    plugin_link.symlink_to(plugin)
    blocked(lambda: rehearse_bundle(plugin_link, lock, release, preexisting=False))
    observations = []
    def inspect(live, before):
        assert (live / 'themes/ezb-theme/style.css').is_file()
        assert (live / 'plugins/ezb-core/ezb-core.php').is_file()
        assert (live / 'plugins/elementor/elementor.php').is_file()
        assert (live / 'uploads/2026/owner-media.txt').read_bytes() == b'synthetic upload preserved'
        assert before['uploads/2026/owner-media.txt']
        observations.append(True)
    for injected in (False, True):
        result = rehearse_bundle(plugin, lock, release, preexisting=True,
                                 on_installed=inspect, inject_callback_fault=injected)
        assert result['restored'] and result['callback_executed']
        assert result['fault'] == ('after_content_apply' if injected else 'none')
        CASES += 1
    assert len(observations) == 2
    blocked(lambda: rehearse_bundle(plugin, lock, release, preexisting=True,
                                   on_installed='invalid'))
    blocked(lambda: rehearse_bundle(plugin, lock, release, preexisting=True,
                                   inject_callback_fault=True))
    (release / 'ezb-theme.zip').write_bytes(b'not a release ZIP')
    blocked(lambda: rehearse_bundle(plugin, lock, release, preexisting=False))

assert CASES == 23, CASES
print('EZ2_CI_THREE_COMPONENT_GUARD_PASS cases=23 scenarios=16 faults=13')
