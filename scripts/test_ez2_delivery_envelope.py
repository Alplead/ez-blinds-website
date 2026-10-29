#!/usr/bin/env python3
"""Fail-closed tests for the public-safe exact-head EZ2 delivery envelope."""
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ez2_delivery_envelope as envelope

SHA = "a" * 40


def candidate():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr(envelope.NAME, '{"version":"4.3.4"}')
    return data.getvalue()


def fixture():
    files = {name: (name + "-synthetic").encode() for name in envelope.FILES}
    files["release/ez2-content-candidate.zip"] = candidate()
    files[envelope.DEPENDENCY] = json.dumps({
        "schema_version": 1, "target_site": "ez2-isolated-only",
        "plugins": [{"slug": "elementor", "version": "4.3.4",
                     "entrypoint": "elementor/elementor.php", "source": "wordpress.org",
                     "archive_sha256": "b" * 64, "activate": True}]
    }).encode()
    return files


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.files = fixture()
        self.patches = [
            patch.object(envelope, "verify_release", return_value={
                "source_sha": SHA, "target_site": "ez2-isolated-only",
                "scope": "engineering-evidence-only", "deployment_authorized": False}),
            patch.object(envelope, "verify_candidate", return_value={
                "source_sha": SHA, "scope": "public-review-candidate-only"}),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def make(self):
        return envelope.encode(self.files, envelope.validate_payload(self.files, SHA))

    def test_roundtrip(self):
        receipt = envelope.verify_bytes(self.make(), SHA)
        self.assertEqual(receipt["component_count"], 8)
        self.assertFalse(receipt["can_apply"])
        self.assertFalse(receipt["one_click_complete"])

    def test_deterministic(self):
        self.assertEqual(self.make(), self.make())

    def test_wrong_sha(self):
        with self.assertRaises(ValueError):
            envelope.verify_bytes(self.make(), "c" * 40)

    def test_invalid_sha(self):
        with self.assertRaises(ValueError):
            envelope.validate_payload(self.files, "not-a-sha")

    def test_missing_file(self):
        del self.files[envelope.FILES[0]]
        with self.assertRaises(ValueError):
            envelope.validate_payload(self.files, SHA)

    def test_unpinned_plugin(self):
        lock = json.loads(self.files[envelope.DEPENDENCY])
        lock["plugins"][0]["archive_sha256"] = None
        self.files[envelope.DEPENDENCY] = json.dumps(lock).encode()
        with self.assertRaises(ValueError):
            envelope.validate_payload(self.files, SHA)

    def test_plugin_version_mismatch(self):
        lock = json.loads(self.files[envelope.DEPENDENCY])
        lock["plugins"][0]["version"] = "4.3.5"
        self.files[envelope.DEPENDENCY] = json.dumps(lock).encode()
        with self.assertRaises(ValueError):
            envelope.validate_payload(self.files, SHA)

    def test_manifest_tamper(self):
        raw = self.make()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            values = {name: z.read(name) for name in z.namelist()}
        values[envelope.MANIFEST] = values[envelope.MANIFEST].replace(
            b'"can_apply":false', b'"can_apply":true')
        changed = io.BytesIO()
        with zipfile.ZipFile(changed, "w") as z:
            for name, data in values.items():
                z.writestr(name, data)
        with self.assertRaises(ValueError):
            envelope.verify_bytes(changed.getvalue(), SHA)

    def test_extra_member(self):
        raw = self.make()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            values = [(i.filename, z.read(i)) for i in z.infolist()]
        changed = io.BytesIO()
        with zipfile.ZipFile(changed, "w") as z:
            for name, data in values:
                z.writestr(name, data)
            z.writestr("../private.sql", "no")
        with self.assertRaises(ValueError):
            envelope.verify_bytes(changed.getvalue(), SHA)

    def test_noncanonical_zip(self):
        raw = self.make()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            values = [(i.filename, z.read(i)) for i in z.infolist()]
        changed = io.BytesIO()
        with zipfile.ZipFile(changed, "w") as z:
            for name, data in reversed(values):
                z.writestr(name, data)
        with self.assertRaises(ValueError):
            envelope.verify_bytes(changed.getvalue(), SHA)

    def test_invalid_json_lock(self):
        self.files[envelope.DEPENDENCY] = b'{"plugins":1,"plugins":2}'
        with self.assertRaises(ValueError):
            envelope.validate_payload(self.files, SHA)

    def test_lock_regular_file_read(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "elementor.json"
            lock.write_bytes(b'{"synthetic":true}')
            self.assertEqual(envelope.checked_dependency_lock(lock), b'{"synthetic":true}')

    def test_lock_hardlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "elementor.json"
            lock.write_bytes(b'{"synthetic":true}')
            os.link(lock, Path(temp) / "private-alias.json")
            with self.assertRaises(ValueError):
                envelope.checked_dependency_lock(lock)

    def test_lock_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "elementor.json"
            lock.write_bytes(b'{"synthetic":true}')
            alias = Path(temp) / "alias.json"
            alias.symlink_to(lock)
            with self.assertRaises(ValueError):
                envelope.checked_dependency_lock(alias)

    def test_lock_linked_parent_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp) / "real"
            parent.mkdir()
            (parent / "elementor.json").write_bytes(b'{"synthetic":true}')
            alias = Path(temp) / "linked"
            alias.symlink_to(parent, target_is_directory=True)
            with self.assertRaises(ValueError):
                envelope.checked_dependency_lock(alias / "elementor.json")

    def test_lock_oversized_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "elementor.json"
            lock.write_bytes(b"x" * 32769)
            with self.assertRaises(ValueError):
                envelope.checked_dependency_lock(lock)

    def test_lock_identical_bytes_replacement_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "elementor.json"
            lock.write_bytes(b'{"synthetic":true}')
            original_open = os.open
            swapped = False

            def swap_before_open(path, flags, *args, **kwargs):
                nonlocal swapped
                if Path(path) == lock and not swapped:
                    lock.unlink()
                    lock.write_bytes(b'{"synthetic":true}')
                    swapped = True
                return original_open(path, flags, *args, **kwargs)

            with patch.object(envelope.os, "open", side_effect=swap_before_open):
                with self.assertRaises(ValueError):
                    envelope.checked_dependency_lock(lock)
            self.assertTrue(swapped)

    def test_no_private_media(self):
        raw = self.make()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertFalse(any("uploads" in n or n.endswith(".sql") for n in z.namelist()))
            self.assertNotIn("elementor.zip", z.namelist())


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(EnvelopeTests)
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
    print(f"EZ2_DELIVERY_ENVELOPE_GUARD_PASS cases={result.testsRun} installable=false private_media=false")
