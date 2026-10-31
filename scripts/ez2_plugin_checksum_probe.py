#!/usr/bin/env python3
"""Observe an exact WordPress.org ZIP SHA256; never approve or install it."""
import copy
import hashlib
import json
import sys
import tempfile
import urllib.error
from pathlib import Path
from ez2_plugin_archive_verify import verify
from ez2_plugin_dependency_check import check, read
from ez2_plugin_official_fetch import CHUNK, MAX_ARCHIVE, official_url, open_official

def capture(lock, open_url=open_official, repo_root=None):
    info = check(lock)
    if len(info['missing_checksums']) != len(lock['plugins']):
        raise ValueError('Only unpinned manifests can be observed')
    candidate = copy.deepcopy(lock)
    results = []
    with tempfile.TemporaryDirectory(prefix='ez2-observe-') as tmp:
        root = Path(tmp)
        for plugin, target in zip(lock['plugins'], candidate['plugins']):
            url = official_url(plugin['slug'], plugin['version'])
            digest, size = hashlib.sha256(), 0
            with open_url(url) as response:
                if response.geturl() != url or getattr(response, 'status', None) != 200:
                    raise ValueError('Unexpected download URL or status')
                length = response.headers.get('Content-Length')
                if length is not None and (not length.isdecimal() or not 0 < int(length) <= MAX_ARCHIVE):
                    raise ValueError('Invalid Content-Length')
                with (root / f"{plugin['slug']}.{plugin['version']}.zip").open('xb') as output:
                    while True:
                        block = response.read(CHUNK)
                        if not block:
                            break
                        size += len(block)
                        if size > MAX_ARCHIVE:
                            raise ValueError('Download size cap exceeded')
                        digest.update(block)
                        output.write(block)
                if not size or (length is not None and size != int(length)):
                    raise ValueError('Incomplete download')
            target['archive_sha256'] = digest.hexdigest()
            results.append({'slug': plugin['slug'], 'version': plugin['version'],
                            'observed_sha256': digest.hexdigest(), 'bytes': size})
        checked = verify(candidate, root, repo_root=repo_root)
        for result, archive in zip(results, checked['plugins']):
            if result['slug'] != archive['slug'] or result['version'] != archive['version']:
                raise ValueError('Archive order mismatch')
            result['files_checked'] = archive['files_checked']
    return {'status': 'UNATTESTED_CHECKSUM_OBSERVATION', 'plugins': results,
            'temporary_files_deleted': True, 'independent_attestation': False,
            'publisher_signature_verified': False, 'release_approved': False,
            'installed': False, 'localwp_modified': False}

if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('Usage: ez2_plugin_checksum_probe.py UNPINNED_LOCK.json')
        print(json.dumps(capture(read(sys.argv[1])), sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError, urllib.error.URLError, TimeoutError) as exc:
        print('EZ2_CHECKSUM_PROBE_FAIL: ' + str(exc), file=sys.stderr)
        sys.exit(1)
