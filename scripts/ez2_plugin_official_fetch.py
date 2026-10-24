#!/usr/bin/env python3
"""Read-only, opt-in HTTPS retrieval of pinned WordPress.org plugin ZIPs.

Only a private temporary directory is used. No ZIP is installed, extracted,
committed, published, or persisted. This does not prove Elementor functionality.
"""
import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from ez2_plugin_archive_verify import verify
from ez2_plugin_dependency_check import check, read

MAX_ARCHIVE = 50 * 1024 * 1024
CHUNK = 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Plugin download redirect refused')


def official_url(slug, version):
    return f'https://downloads.wordpress.org/plugin/{slug}.{version}.zip'


def open_official(url):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'EZ2-isolated-plugin-provenance-check/1.0',
        'Accept': 'application/zip',
    })
    return urllib.request.build_opener(NoRedirect).open(request, timeout=30)


def fetch(lock, open_url=open_official, repo_root=None):
    checked = check(lock)
    if checked['missing_checksums']:
        raise ValueError('Pinned plugin SHA256 required before network fetch')
    results = []
    with tempfile.TemporaryDirectory(prefix='ez2-official-plugin-') as temp:
        private_dir = Path(temp)
        for plugin in lock['plugins']:
            url = official_url(plugin['slug'], plugin['version'])
            path = private_dir / f"{plugin['slug']}.{plugin['version']}.zip"
            with open_url(url) as response:
                if response.geturl() != url:
                    raise ValueError('Unexpected plugin download origin or path')
                if getattr(response, 'status', 200) != 200:
                    raise ValueError('Official plugin download did not return HTTP 200')
                size_header = response.headers.get('Content-Length')
                if size_header is not None:
                    if not size_header.isdecimal() or not 0 < int(size_header) <= MAX_ARCHIVE:
                        raise ValueError('Unsafe plugin Content-Length')
                count = 0
                with path.open('xb') as dest:
                    while True:
                        data = response.read(CHUNK)
                        if not data:
                            break
                        count += len(data)
                        if count > MAX_ARCHIVE:
                            raise ValueError('Plugin download exceeds private size cap')
                        dest.write(data)
                if not count or (size_header is not None and count != int(size_header)):
                    raise ValueError('Incomplete plugin download')
            results.append({'slug': plugin['slug'], 'version': plugin['version'],
                            'official_https_url': url, 'download_bytes': count})
        verified = verify(lock, private_dir, repo_root=repo_root)
        for result, archive in zip(results, verified['plugins']):
            if result['slug'] != archive['slug'] or result['version'] != archive['version']:
                raise ValueError('Verified plugin order mismatch')
            result['archive_sha256_verified'] = archive['checksum_verified']
            result['zip_files_checked'] = archive['files_checked']
    return {'status': 'OFFICIAL_HTTPS_PINNED_ARCHIVE_VERIFIED_ONLY',
            'target_site': 'ez2-isolated-only', 'plugins': results,
            'private_temporary_files_deleted': True,
            'official_https_transport_checked': True,
            'publisher_signature_verified': False,
            'wordpress_runtime_verified': False,
            'elementor_feature_verified': False,
            'plugin_installed': False, 'localwp_modified': False,
            'deployment_authorized': False}


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('Usage: ez2_plugin_official_fetch.py PINNED_PLUGIN_LOCK.json')
        print(json.dumps(fetch(read(sys.argv[1])), sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError, urllib.error.URLError, TimeoutError) as exc:
        print('EZ2_OFFICIAL_PLUGIN_FETCH_FAIL: ' + str(exc), file=sys.stderr)
        sys.exit(1)
