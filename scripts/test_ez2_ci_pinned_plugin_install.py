"""Offline regressions for checksum-pinned CI-only plugin installation."""
import copy
import hashlib
import io
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from ez2_ci_pinned_plugin_install import download_verified, main, validate_lock

CASES = 0
VERSION = "4.3.4"


def archive():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr("elementor/elementor.php",
                        "<?php\n/*\nPlugin Name: Elementor\nVersion: 4.3.4\n*/\n")
        zipped.writestr("elementor/readme.txt", "Synthetic CI test only")
    return output.getvalue()


class Response(io.BytesIO):
    def __init__(self, payload, *, url, status=200, length=None):
        super().__init__(payload)
        self.url = url
        self.status = status
        self.headers = {"Content-Length": str(len(payload)) if length is None else length}

    def geturl(self):
        return self.url


def blocked(action):
    global CASES
    try:
        action()
    except (ValueError, OSError):
        CASES += 1
    else:
        raise AssertionError("Unsafe pinned-plugin input accepted")


raw = archive()
lock = {"schema_version": 1, "target_site": "ez2-isolated-only",
        "plugins": [{"slug": "elementor", "version": VERSION,
                     "entrypoint": "elementor/elementor.php",
                     "source": "wordpress.org",
                     "archive_sha256": hashlib.sha256(raw).hexdigest(),
                     "activate": True}]}
url = "https://downloads.wordpress.org/plugin/elementor.4.3.4.zip"
assert validate_lock(lock)["version"] == VERSION
CASES += 1
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    def good(u):
        assert u == url
        return Response(raw, url=url)
    result = download_verified(lock, root, opener=good)
    assert result.name == "elementor.4.3.4.zip" and result.read_bytes() == raw
    CASES += 1
with tempfile.TemporaryDirectory() as temp:
    wrong = copy.deepcopy(lock)
    wrong["plugins"][0]["archive_sha256"] = "f" * 64
    blocked(lambda: download_verified(wrong, temp, opener=lambda u: Response(raw, url=u)))
with tempfile.TemporaryDirectory() as temp:
    blocked(lambda: download_verified(lock, temp, opener=lambda u: Response(raw, url=u + "?redirect")))
with tempfile.TemporaryDirectory() as temp:
    blocked(lambda: download_verified(lock, temp, opener=lambda u: Response(raw, url=u, status=206)))
with tempfile.TemporaryDirectory() as temp:
    blocked(lambda: download_verified(lock, temp, opener=lambda u: Response(raw, url=u, length="nope")))
with tempfile.TemporaryDirectory() as temp:
    blocked(lambda: download_verified(lock, temp, opener=lambda u: Response(raw, url=u, length="999999")))
with tempfile.TemporaryDirectory() as temp:
    broken = b"not a plugin ZIP"
    bad = copy.deepcopy(lock)
    bad["plugins"][0]["archive_sha256"] = hashlib.sha256(broken).hexdigest()
    blocked(lambda: download_verified(bad, temp, opener=lambda u: Response(broken, url=u)))
unpinned = copy.deepcopy(lock)
unpinned["plugins"][0]["archive_sha256"] = None
blocked(lambda: validate_lock(unpinned))
wrong_version = copy.deepcopy(lock)
wrong_version["plugins"][0]["version"] = "4.3.5"
blocked(lambda: validate_lock(wrong_version))
extra = copy.deepcopy(lock)
extra["plugins"].append(copy.deepcopy(extra["plugins"][0]))
blocked(lambda: validate_lock(extra))
with patch.dict(os.environ, {}, clear=True):
    blocked(lambda: main("a" * 40))
with patch.dict(os.environ, {"GITHUB_ACTIONS": "true",
                             "EZ2_CI_PINNED_PLUGIN_INSTALL": "YES_DISPOSABLE_RELEASE_ONLY"}):
    blocked(lambda: main("invalid"))
assert CASES == 13, CASES
print("EZ2_CI_PINNED_ELEMENTOR_INSTALL_GUARD_PASS cases=13")
