"""Synthetic network tests; no real HTTP or WordPress installation in CI."""
import hashlib
import io
import stat
import tempfile
import zipfile
from pathlib import Path

from ez2_plugin_official_fetch import fetch, official_url


def make_zip():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in (
            ('elementor/elementor.php', b'<?php\n/*\nPlugin Name: Test\nVersion: 4.3.4\n*/'),
            ('elementor/assets/main.css', b'body{}'),
        ):
            entry = zipfile.ZipInfo(name)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(entry, data)
    return output.getvalue()


DATA = make_zip()
URL = official_url('elementor', '4.3.4')


def lock(digest=None):
    return {'schema_version': 1, 'target_site': 'ez2-isolated-only',
            'plugins': [{'slug': 'elementor', 'version': '4.3.4',
                         'entrypoint': 'elementor/elementor.php', 'source': 'wordpress.org',
                         'archive_sha256': digest if digest is not None else hashlib.sha256(DATA).hexdigest(),
                         'activate': True}]}


class Response(io.BytesIO):
    def __init__(self, body=DATA, url=URL, status=200, length=None):
        super().__init__(body)
        self.url = url
        self.status = status
        self.headers = {'Content-Length': str(len(body)) if length is None else length}

    def geturl(self):
        return self.url


cases = 0
with tempfile.TemporaryDirectory() as root:
    repo = Path(root)
    repo.mkdir(exist_ok=True)

    def attempt(doc, factory, ok=False):
        global cases
        calls = []

        def transport(url):
            calls.append(url)
            return factory()

        try:
            result = fetch(doc, open_url=transport, repo_root=repo)
        except (OSError, ValueError, TypeError):
            if ok:
                raise
        else:
            if not ok:
                raise AssertionError('Unsafe download accepted')
            assert calls == [URL]
            assert result['status'] == 'OFFICIAL_HTTPS_PINNED_ARCHIVE_VERIFIED_ONLY'
            assert result['private_temporary_files_deleted'] is True
            assert result['plugins'][0]['archive_sha256_verified'] is True
            assert result['plugins'][0]['zip_files_checked'] == 2
            for key in ('publisher_signature_verified', 'wordpress_runtime_verified',
                        'elementor_feature_verified', 'plugin_installed',
                        'localwp_modified', 'deployment_authorized'):
                assert result[key] is False
        cases += 1

    attempt(lock(), lambda: Response(), ok=True)
    attempt(lock('a' * 64), lambda: Response())
    attempt(lock(), lambda: Response(url='https://evil.invalid/plugin/elementor.4.3.4.zip'))
    attempt(lock(), lambda: Response(url=URL + '?download=1'))
    attempt(lock(), lambda: Response(status=206))
    attempt(lock(), lambda: Response(length='not-a-number'))
    attempt(lock(), lambda: Response(length='52428801'))
    attempt(lock(), lambda: Response(length='1'))
    attempt(lock(), lambda: Response(body=b''))
    attempt(lock(), lambda: Response(body=b'not a zip'))
    attempt(lock(), lambda: Response(length='0'))
    d = lock()
    d['plugins'][0]['archive_sha256'] = None
    attempt(d, lambda: Response())
    d = lock()
    d['plugins'][0]['source'] = 'evil.invalid'
    attempt(d, lambda: Response())
    assert official_url('elementor', '4.3.4') == URL
    cases += 1

assert cases == 14, cases
print(f'EZ2_OFFICIAL_PLUGIN_FETCH_PASS cases={cases}')
