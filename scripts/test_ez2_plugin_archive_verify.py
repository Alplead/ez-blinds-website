"""Offline synthetic ZIP regressions; never downloads real plugin code."""
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch
from ez2_plugin_archive_verify import verify


def zip_bytes(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body, mode in entries:
            item = zipfile.ZipInfo(name)
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = mode << 16
            archive.writestr(item, body)
    return buf.getvalue()


GOOD = [('elementor/elementor.php', '<?php\n/*\nPlugin Name: Synthetic Elementor\nVersion: 4.3.4\n*/\n', stat.S_IFREG | 0o644),
        ('elementor/assets/style.css', 'body{}', stat.S_IFREG | 0o644)]


def lock(data):
    return {'schema_version': 1, 'target_site': 'ez2-isolated-only',
            'plugins': [{'slug': 'elementor', 'version': '4.3.4',
                         'entrypoint': 'elementor/elementor.php', 'source': 'wordpress.org',
                         'archive_sha256': hashlib.sha256(data).hexdigest(), 'activate': True}]}


cases = 0
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    archive_dir = root / 'private'
    archive_dir.mkdir()
    path = archive_dir / 'elementor.4.3.4.zip'

    def attempt(entries, *, expected_ok=False, wrong_digest=False):
        global cases
        data = zip_bytes(entries)
        path.write_bytes(data)
        manifest = lock(data)
        if wrong_digest:
            manifest['plugins'][0]['archive_sha256'] = 'f' * 64
        try:
            result = verify(manifest, archive_dir, repo_root=root / 'not-repo')
        except (ValueError, OSError):
            if expected_ok:
                raise
        else:
            if not expected_ok:
                raise AssertionError('Unsafe plugin archive accepted')
            assert result['status'] == 'LOCAL_PLUGIN_ARCHIVE_BYTES_VERIFIED_ONLY'
            assert result['plugins'][0]['files_checked'] == 2
            assert all(result[k] is False for k in ('archive_extracted', 'archive_executed',
                'wordpress_org_provenance_verified', 'wordpress_runtime_verified',
                'elementor_feature_verified', 'plugin_installed', 'localwp_modified',
                'deployment_authorized'))
        cases += 1

    (root / 'not-repo').mkdir()
    attempt(GOOD, expected_ok=True)
    attempt([('elementor/', '', stat.S_IFDIR | 0o755)] + GOOD, expected_ok=True)
    attempt(GOOD, wrong_digest=True)
    attempt(GOOD + [('elementor/../outside.php', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('../outside.php', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('/elementor/x.php', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('other/x.php', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor\\evil.php', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/STYLE.CSS', 'bad', stat.S_IFREG | 0o644),
                    ('elementor/style.css', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/clash', 'file', stat.S_IFREG | 0o644),
                    ('elementor/clash/nested.php', 'nested', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/dir/', '', stat.S_IFDIR | 0o755),
                    ('elementor/dir', 'file', stat.S_IFREG | 0o644)])
    # Empty directory entries must not appear below a regular file, regardless of order or case.
    attempt(GOOD + [('elementor/cache', 'file', stat.S_IFREG | 0o644),
                    ('elementor/cache/empty/', '', stat.S_IFDIR | 0o755)])
    attempt(GOOD + [('elementor/cache/empty/', '', stat.S_IFDIR | 0o755),
                    ('elementor/cache', 'file', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/Cache', 'file', stat.S_IFREG | 0o644),
                    ('elementor/cache/nested/', '', stat.S_IFDIR | 0o755)])
    attempt(GOOD + [('elementor/assets/empty/', '', stat.S_IFDIR | 0o755)], expected_ok=True)
    attempt(GOOD + [('elementor/link', 'elementor.php', stat.S_IFLNK | 0o777)])
    attempt(GOOD + [('elementor/./bad.php', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/sub//bad.php', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/x\x01.php', 'bad', stat.S_IFREG | 0o644)])
    # Windows LocalWP must not receive device names, ADS or ambiguous paths.
    attempt(GOOD + [('elementor/CON.txt', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/AUX', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/COM1.js', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/COM¹.log', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/LPT²', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/LPT9.txt', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/trailing.', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/trailing ', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/evil:ads.php', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/bad?.js', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/\u202ephp.txt', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/cafe\u0301.js', 'bad', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/caf\u00e9.js', 'a', stat.S_IFREG | 0o644),
                    ('elementor/cafe\u0301.js', 'b', stat.S_IFREG | 0o644)])
    attempt(GOOD + [('elementor/bomb.bin', 'A' * (26 * 1024 * 1024), stat.S_IFREG | 0o644)])
    attempt([('elementor/elementor.php', 'Version: 4.3.3', stat.S_IFREG | 0o644), GOOD[1]])
    attempt([GOOD[1]])
    attempt([('elementor/elementor.php', 'Plugin Name: Demo\nVersion: 4.3.4', stat.S_IFREG | 0o644), GOOD[1]], expected_ok=True)
    attempt([('elementor/elementor.php', 'Version: 4.3.4', stat.S_IFREG | 0o644), GOOD[1]])

    path.unlink()
    try:
        verify(lock(zip_bytes(GOOD)), archive_dir, repo_root=root / 'not-repo')
    except ValueError:
        cases += 1
    else:
        raise AssertionError('Missing archive accepted')

    data = zip_bytes(GOOD)
    path.symlink_to(root / 'not-repo' / 'outside.zip')
    (root / 'not-repo' / 'outside.zip').write_bytes(data)
    try:
        verify(lock(data), archive_dir, repo_root=root / 'not-repo')
    except ValueError:
        cases += 1
    else:
        raise AssertionError('Linked archive accepted')
    path.unlink()

    path.write_bytes(data)
    try:
        verify(lock(data), archive_dir, repo_root=root)
    except ValueError:
        cases += 1
    else:
        raise AssertionError('Archive inside repo accepted')

    # A second hardlink allows mutations through another filesystem path.
    other_link = root / 'outside-hardlink.zip'
    os.link(path, other_link)
    try:
        verify(lock(data), archive_dir, repo_root=root / 'not-repo')
    except ValueError:
        cases += 1
    else:
        raise AssertionError('Hardlinked archive accepted')
    other_link.unlink()

    # An ancestor symlink must not redirect private plugin inputs.
    alias = root / 'archive-alias'
    alias.symlink_to(archive_dir, target_is_directory=True)
    try:
        verify(lock(data), alias, repo_root=root / 'not-repo')
    except ValueError:
        cases += 1
    else:
        raise AssertionError('Linked archive ancestor accepted')
    alias.unlink()

    # Swap after checksum verification, before ZIP parsing. Both operations
    # must be bound to the SAME pinned bytes; the original code missed this.
    original_zip = zipfile.ZipFile
    replacement = archive_dir / 'replacement.zip'
    replacement.write_bytes(zip_bytes([
        ('elementor/elementor.php',
         '<?php\\n/*\\nPlugin Name: Synthetic Other\\nVersion: 4.3.4\\n*/\\n',
         stat.S_IFREG | 0o644),
        GOOD[1],
    ]))
    def swap_during_zip_open(*args, **kwargs):
        os.replace(replacement, path)
        return original_zip(*args, **kwargs)
    with patch('ez2_plugin_archive_verify.zipfile.ZipFile',
               side_effect=swap_during_zip_open):
        try:
            verify(lock(data), archive_dir, repo_root=root / 'not-repo')
        except ValueError:
            cases += 1
        else:
            raise AssertionError('Post-hash archive replacement accepted')
    path.write_bytes(data)

    manifest = lock(data)
    manifest['plugins'][0]['archive_sha256'] = None
    try:
        verify(manifest, archive_dir, repo_root=root / 'not-repo')
    except ValueError:
        cases += 1
    else:
        raise AssertionError('Unpinned archive accepted')

    manifest = lock(data)
    lock_path = root / 'lock.json'
    lock_path.write_text(json.dumps(manifest))
    cmd = [sys.executable, str(Path(__file__).with_name('ez2_plugin_archive_verify.py')),
           str(lock_path), str(archive_dir)]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)['plugin_installed'] is False
    cases += 1

assert cases == 45, cases
print(f'EZ2_PLUGIN_ARCHIVE_VERIFY_PASS cases={cases}')
