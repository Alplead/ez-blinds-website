#!/usr/bin/env python3
"""Read-only byte parity of first-party release ZIPs against a local wp-content tree.

Does not identify the WordPress site, attest its provenance, verify plugins,
install code, touch the database or authorize an update. Run only against a
separately approved, isolated disposable EZ2 WordPress fixture.
"""
import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import Path

from verify_release_scope import ARCHIVES, check as verify_release

MAX_FILE = 8 * 1024 * 1024
MAX_TREE = 32 * 1024 * 1024


def disk_inventory(directory):
    """Hash only regular single-link files; never follow symlinks or special files."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Missing or linked installed component directory")
    found = {}
    total = 0

    def visit(folder, relative):
        nonlocal total
        for child in folder.iterdir():
            info = child.lstat()
            name = relative + child.name
            if stat.S_ISDIR(info.st_mode):
                visit(child, name + "/")
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                if not 0 < info.st_size <= MAX_FILE or total + info.st_size > MAX_TREE:
                    raise ValueError("Unsafe installed file size")
                total += info.st_size
                found[name] = hashlib.sha256(child.read_bytes()).hexdigest()
                if len(found) > 512:
                    raise ValueError("Too many installed component files")
            else:
                raise ValueError("Linked or special installed component entry")
    visit(directory, "")
    return found


def archive_inventory(path, prefix):
    found = {}
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            if not entry.is_dir():
                relative = entry.filename.removeprefix(prefix + "/")
                if relative == entry.filename or not relative:
                    raise ValueError("Unexpected release archive root")
                found[relative] = hashlib.sha256(archive.read(entry)).hexdigest()
    return found


def check(release_dir, exact_sha, wp_content_dir):
    if not isinstance(exact_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", exact_sha):
        raise ValueError("Invalid exact SHA")
    release_dir, root = Path(release_dir), Path(wp_content_dir)
    if (root.name != "wp-content" or root.is_symlink() or not root.is_dir()
            or root.parent.is_symlink()):
        raise ValueError("Expected an ordinary isolated wp-content directory")
    verify_release(release_dir, exact_sha)
    mismatch_count = 0
    file_count = 0
    for archive, destination in ARCHIVES.items():
        target = root / Path(destination).relative_to("wp-content")
        expected = archive_inventory(release_dir / archive, archive.removesuffix(".zip"))
        actual = disk_inventory(target)
        file_count += len(expected)
        mismatch_count += sum(actual.get(name) != digest for name, digest in expected.items())
        mismatch_count += len(actual.keys() - expected.keys())
    return {
        "status": "CODE_BYTES_MATCH_RELEASE_ONLY" if mismatch_count == 0 else "BLOCKED_CODE_PARITY",
        "mode": "read-only", "source_sha": exact_sha,
        "checked_release_files": file_count, "mismatch_count": mismatch_count,
        "theme_core_byte_parity": mismatch_count == 0,
        "site_identity_verified": False, "installed_source_attested": False,
        "wordpress_runtime_verified": False, "third_party_plugins_verified": False,
        "elementor_content_verified": False, "private_media_verified": False,
        "localwp_installed": False, "deployment_authorized": False,
        "applied": False, "one_click_complete": False,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4:
            raise ValueError("Usage: ez2_installed_code_parity.py RELEASE_DIR EXACT_SHA WP_CONTENT_DIR")
        result = check(*sys.argv[1:])
        print(json.dumps(result, sort_keys=True))
        sys.exit(0 if result["theme_core_byte_parity"] else 2)
    except (ValueError, OSError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        print("EZ2_CODE_PARITY_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
