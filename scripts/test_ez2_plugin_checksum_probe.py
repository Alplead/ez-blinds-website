"""Synthetic HTTPS responses only: no real downloads, plugins or site writes."""
import hashlib
import io
import stat
import tempfile
import zipfile
from pathlib import Path
from ez2_plugin_checksum_probe import capture
from ez2_plugin_official_fetch import NoRedirect, official_url

URL = official_url('elementor', '4.3.4')

def archive(version='4.3.4', entry=True):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
        members = [('elementor/assets/main.css', b'body{}')]
        if entry:
            members.insert(0, ('elementor/elementor.php',
                ('<?php\n/*\nPlugin Name: Synthetic Elementor\nVersion: ' + version + '\n*/').encode()))
        for name, data in members:
            item = zipfile.ZipInfo(name)
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = (stat.S_IFREG | 0o644) << 16
            z.writestr(item, data)
    return stream.getvalue()

DATA = archive()

def lock():
    return {'schema_version': 1, 'target_site': 'ez2-isolated-only',
            'plugins': [{'slug': 'elementor', 'version': '4.3.4',
            'entrypoint': 'elementor/elementor.php', 'source': 'wordpress.org',
            'archive_sha256': None, 'activate': True}]}

class Response(io.BytesIO):
    def __init__(self, data=DATA, url=URL, status=200, length='auto'):
        super().__init__(data)
        self.url, self.status = url, status
        self.headers = {} if length is None else {
            'Content-Length': str(len(data)) if length == 'auto' else length}
    def geturl(self):
        return self.url

cases = 0
with tempfile.TemporaryDirectory() as tmp:
    public = Path(tmp) / 'public'
    public.mkdir()
    def attempt(doc, response, success=False):
        global cases
        calls = []
        def opener(url):
            calls.append(url)
            return response
        try:
            result = capture(doc, open_url=opener, repo_root=public)
        except (OSError, ValueError, TypeError):
            if success:
                raise
        else:
            if not success:
                raise AssertionError('Unsafe checksum candidate accepted')
            assert calls == [URL]
            assert result['status'] == 'UNATTESTED_CHECKSUM_OBSERVATION'
            assert result['plugins'][0]['observed_sha256'] == hashlib.sha256(DATA).hexdigest()
            assert result['plugins'][0]['files_checked'] == 2
            assert result['temporary_files_deleted'] is True
            for field in ('independent_attestation', 'publisher_signature_verified',
                          'release_approved', 'installed', 'localwp_modified'):
                assert result[field] is False
        cases += 1

    attempt(lock(), Response(), True)
    attempt(lock(), Response(length=None), True)
    attempt(lock(), Response(url='https://other.invalid/plugin.zip'))
    attempt(lock(), Response(url=URL + '?modified=1'))
    attempt(lock(), Response(status=206))
    attempt(lock(), Response(length='bad'))
    attempt(lock(), Response(length='0'))
    attempt(lock(), Response(length='52428801'))
    attempt(lock(), Response(length='1'))
    attempt(lock(), Response(data=b''))
    attempt(lock(), Response(data=b'not-a-zip'))
    attempt(lock(), Response(data=archive(version='4.3.3')))
    attempt(lock(), Response(data=archive(entry=False)))
    doc = lock()
    doc['plugins'][0]['archive_sha256'] = 'a' * 64
    attempt(doc, Response())
    doc = lock()
    doc['target_site'] = 'ez-bns-new-dev.local'
    attempt(doc, Response())
    try:
        NoRedirect().redirect_request(None, None, 302, 'Found', {}, URL)
    except ValueError:
        cases += 1
    else:
        raise AssertionError('Redirect accepted')
assert cases == 16, cases
print(f'EZ2_PLUGIN_CHECKSUM_PROBE_PASS cases={cases}')
