#!/usr/bin/env python3
"""Verify pinned EZ2 plugin ZIP bytes offline; never extract, execute or install."""
import hashlib
import io
import json
import os
import re
import stat
import sys
import unicodedata
import zipfile
from pathlib import Path
from ez2_plugin_dependency_check import check, read

# Windows LocalWP extracts on a case-insensitive filesystem; reject device names,
# alternate data streams and paths that collapse during Windows extraction.
WINDOWS_DEVICE = re.compile(r'(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\..*)?\Z', re.I)


def file_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def verify(lock, archive_dir, repo_root=None):
    if check(lock)['missing_checksums']:
        raise ValueError('Missing pinned checksum')
    root = Path(archive_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Invalid private archive directory')
    resolved = root.resolve(strict=True)
    if resolved != root.absolute():
        raise ValueError('Linked ancestor in private archive directory')
    root = resolved
    repo = Path(repo_root or Path(__file__).resolve().parents[1]).resolve(strict=True)
    if root == repo or repo in root.parents:
        raise ValueError('Third-party archives cannot be inside public repository')
    results = []
    for plugin in lock['plugins']:
        slug, version = plugin['slug'], plugin['version']
        archive_path = root / f'{slug}.{version}.zip'
        if archive_path.is_symlink() or not archive_path.is_file():
            raise ValueError('Missing or unsafe plugin ZIP')
        before = archive_path.stat(follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 0 < before.st_size <= 50 * 1024 * 1024):
            raise ValueError('Missing, linked or oversized plugin ZIP')
        # Hash and inspect one immutable byte snapshot. Previously the ZIP was
        # reopened by path after hashing, so a replacement could pass a digest
        # for different bytes than the ones checked for safe installation.
        with archive_path.open('rb') as source:
            if file_identity(os.fstat(source.fileno())) != file_identity(before):
                raise ValueError('Plugin ZIP changed before reading')
            raw = source.read(50 * 1024 * 1024 + 1)
            if (len(raw) != before.st_size
                    or file_identity(os.fstat(source.fileno())) != file_identity(before)):
                raise ValueError('Plugin ZIP changed while reading')
        if (archive_path.is_symlink()
                or file_identity(archive_path.stat(follow_symlinks=False)) != file_identity(before)):
            raise ValueError('Plugin ZIP path changed after reading')
        if hashlib.sha256(raw).hexdigest() != plugin['archive_sha256']:
            raise ValueError('Pinned ZIP digest mismatch')
        seen, files, dirs, count, total, header = set(), set(), set(), 0, 0, None
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                entries = z.infolist()
                if not 1 <= len(entries) <= 5500:
                    raise ValueError('Unsafe ZIP entry count')
                for member in entries:
                    name = member.filename
                    if (not name or len(name.encode('utf-8')) > 255 or '\\' in name
                            or name.startswith('/') or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)):
                        raise ValueError('Unsafe ZIP member path')
                    parts = name.rstrip('/').split('/')
                    if (parts[0] != slug or any(p in ('', '.', '..') for p in parts)
                            or (len(parts) < 2 and not (name == slug + '/' and member.is_dir()))):
                        raise ValueError('ZIP member outside pinned plugin')
                    if any(
                        segment.endswith((' ', '.')) or
                        unicodedata.normalize('NFC', segment) != segment or
                        WINDOWS_DEVICE.fullmatch(segment) or
                        any(ch in '<>:"|?*' or unicodedata.category(ch) in ('Cc', 'Cf', 'Cs')
                            for ch in segment)
                        for segment in parts
                    ):
                        raise ValueError('Unsafe Windows plugin member path')
                    folded = unicodedata.normalize('NFC', '/'.join(parts)).casefold()
                    if folded in seen:
                        raise ValueError('Duplicate ZIP member')
                    seen.add(folded)
                    kind = stat.S_IFMT(member.external_attr >> 16)
                    if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                        raise ValueError('ZIP links and special files forbidden')
                    if (member.is_dir() and kind == stat.S_IFREG) or (not member.is_dir() and kind == stat.S_IFDIR):
                        raise ValueError('ZIP file type conflict')
                    if member.flag_bits & 1 or member.compress_type not in (0, 8):
                        raise ValueError('Encrypted or unsupported ZIP member')
                    if member.file_size > 25 * 1024 * 1024 or member.file_size < 0:
                        raise ValueError('Oversized ZIP member')
                    if member.is_dir():
                        dirs.add(folded)
                    else:
                        files.add(folded)
                        count += 1
                        total += member.file_size
                        if count > 5000 or total > 150 * 1024 * 1024:
                            raise ValueError('Excessive expanded ZIP size')
                        if member.file_size > 1024 * 1024 and member.file_size > max(1, member.compress_size) * 200:
                            raise ValueError('Excessive ZIP compression ratio')
                    if name == plugin['entrypoint']:
                        if member.is_dir() or member.file_size > 128 * 1024:
                            raise ValueError('Unsafe plugin entrypoint')
                        with z.open(member) as stream:
                            header = stream.read(128 * 1024).decode('utf-8-sig', errors='replace')
                # Reject empty directory entries nested beneath a file path.
                # A file-only walk cannot detect this collision without child files.
                for directory in dirs:
                    parts = directory.split('/')
                    if any('/'.join(parts[:i]) in files for i in range(1, len(parts) + 1)):
                        raise ValueError('ZIP file and directory collision')
                for filename in files:
                    parts = filename.split('/')
                    if filename in dirs or any('/'.join(parts[:i]) in files for i in range(1, len(parts))):
                        raise ValueError('ZIP file and directory collision')
                if not count or header is None:
                    raise ValueError('Plugin entrypoint missing')
                name = re.search(r'(?mi)^\s*\*?\s*Plugin Name:\s*([^\r\n]+)', header)
                pinned = re.search(r'(?mi)^\s*\*?\s*Version:\s*([^\r\n]+)', header)
                if not name or not name.group(1).strip() or not pinned or pinned.group(1).strip() != version:
                    raise ValueError('Plugin header mismatch')
                if z.testzip() is not None:
                    raise ValueError('ZIP CRC mismatch')
        except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, EOFError, UnicodeError) as exc:
            raise ValueError('Malformed plugin ZIP') from exc
        if (archive_path.is_symlink()
                or file_identity(archive_path.stat(follow_symlinks=False)) != file_identity(before)):
            raise ValueError('Plugin ZIP path changed during verification')
        results.append({'slug': slug, 'version': version, 'files_checked': count,
                        'uncompressed_bytes': total, 'checksum_verified': True})
    return {'status': 'LOCAL_PLUGIN_ARCHIVE_BYTES_VERIFIED_ONLY', 'target_site': 'ez2-isolated-only',
            'plugins': results, **{k: False for k in ('archive_extracted', 'archive_executed',
            'wordpress_org_provenance_verified', 'wordpress_runtime_verified',
            'elementor_feature_verified', 'plugin_installed', 'localwp_modified', 'deployment_authorized')}}


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Usage: ez2_plugin_archive_verify.py LOCK.json PRIVATE_ARCHIVE_DIRECTORY')
        print(json.dumps(verify(read(sys.argv[1]), sys.argv[2]), sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print('EZ2_PLUGIN_ARCHIVE_VERIFY_FAIL: ' + str(exc), file=sys.stderr)
        sys.exit(1)
