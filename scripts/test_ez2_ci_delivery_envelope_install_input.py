#!/usr/bin/env python3
"""Offline regression for consuming verified EZ2 envelope bytes in CI only."""
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ez2_ci_delivery_envelope_install_input as consumer

SHA = "a" * 40
LOCK_BYTES = b'{"plugins":[{"slug":"elementor","version":"4.3.4"}]}'
CATALOG = {
    "source_sha": SHA, "target_site": "ez2-isolated-only",
    "scope": "engineering-evidence-only",
    "deployment_authorized": False, "one_click_complete": False,
}
RECEIPT = {
    "source_sha": SHA, "can_apply": False, "deployment_authorized": False,
}


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / ".release"
        self.root.mkdir()
        design = self.root.parent / "design"
        design.mkdir()
        self.source_lock = design / "ez2-elementor-pinned-plugin.json"
        self.source_lock.write_bytes(LOCK_BYTES)
        self.payloads = {}
        for name in consumer.RELEASE_NAMES:
            data = ("synthetic-" + name).encode()
            (self.root / name).write_bytes(data)
            self.payloads[name] = data
        self.make_envelope()
        self.verify = patch.object(consumer, "verify_bytes", return_value=RECEIPT)
        self.catalog = patch.object(consumer, "verify_release", return_value=CATALOG)
        self.verify.start()
        self.catalog.start()
        self.addCleanup(self.verify.stop)
        self.addCleanup(self.catalog.stop)

    def make_envelope(self):
        with zipfile.ZipFile(self.root / consumer.OUT_NAME, "w") as zipped:
            for name, data in self.payloads.items():
                zipped.writestr("release/" + name, data)
            zipped.writestr(consumer.DEPENDENCY, LOCK_BYTES)

    def test_staged_release_is_byte_identical(self):
        receipt = consumer.stage(self.root, SHA)
        self.assertEqual(receipt["status"], "DISPOSABLE_ENVELOPE_INSTALL_INPUT_VERIFIED")
        self.assertFalse(receipt["deployment_authorized"])
        self.assertFalse(receipt["localwp_installed"])
        self.assertEqual({p.name for p in (self.root / consumer.OUTPUT).iterdir()},
                         set(consumer.RELEASE_NAMES) | {"dependency"})
        self.assertTrue(receipt["pinned_plugin_manifest_from_envelope"])
        self.assertEqual((self.root / consumer.OUTPUT / consumer.DEPENDENCY).read_bytes(),
                         LOCK_BYTES)
        for name, data in self.payloads.items():
            self.assertEqual((self.root / consumer.OUTPUT / name).read_bytes(), data)

    def test_missing_pinned_dependency_refused(self):
        (self.root / consumer.OUT_NAME).unlink()
        with zipfile.ZipFile(self.root / consumer.OUT_NAME, "w") as zipped:
            for name, data in self.payloads.items():
                zipped.writestr("release/" + name, data)
        with self.assertRaises(ValueError):
            consumer.stage(self.root, SHA)
        self.assertFalse((self.root / consumer.OUTPUT).exists())

    def test_modified_pinned_dependency_refused(self):
        (self.root / consumer.OUT_NAME).unlink()
        with zipfile.ZipFile(self.root / consumer.OUT_NAME, "w") as zipped:
            for name, data in self.payloads.items():
                zipped.writestr("release/" + name, data)
            zipped.writestr(consumer.DEPENDENCY, b"changed lock")
        with self.assertRaises(ValueError):
            consumer.stage(self.root, SHA)
        self.assertFalse((self.root / consumer.OUTPUT).exists())

    def test_source_pinned_dependency_drift_refused(self):
        self.source_lock.write_bytes(b"changed source lock")
        with self.assertRaises(ValueError):
            consumer.stage(self.root, SHA)
        self.assertFalse((self.root / consumer.OUTPUT).exists())

    def test_source_pinned_dependency_symlink_refused(self):
        self.source_lock.unlink()
        self.source_lock.symlink_to(self.root / consumer.RELEASE_NAMES[0])
        with self.assertRaises(ValueError):
            consumer.stage(self.root, SHA)
        self.assertFalse((self.root / consumer.OUTPUT).exists())

    def test_repeat_refused(self):
        consumer.stage(self.root, SHA)
        with self.assertRaises(ValueError):
            consumer.stage(self.root, SHA)

    def test_wrong_exact_sha(self):
        with self.assertRaises(ValueError):
            consumer.stage(self.root, "invalid")

    def test_missing_original(self):
        (self.root / consumer.RELEASE_NAMES[0]).unlink()
        with self.assertRaises((ValueError, OSError)):
            consumer.stage(self.root, SHA)
        self.assertFalse((self.root / consumer.OUTPUT).exists())

    def test_original_release_tampered(self):
        (self.root / consumer.RELEASE_NAMES[0]).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            consumer.stage(self.root, SHA)
        self.assertFalse((self.root / consumer.OUTPUT).exists())

    def test_envelope_verification_failed(self):
        with patch.object(consumer, "verify_bytes", side_effect=ValueError("bad")):
            with self.assertRaises(ValueError):
                consumer.stage(self.root, SHA)
        self.assertFalse((self.root / consumer.OUTPUT).exists())

    def test_catalog_rejected(self):
        with patch.object(consumer, "verify_release", return_value={**CATALOG, "deployment_authorized": True}):
            with self.assertRaises(ValueError):
                consumer.stage(self.root, SHA)
        self.assertFalse((self.root / consumer.OUTPUT).exists())

    def test_archive_symlink_rejected(self):
        archive = self.root / consumer.OUT_NAME
        archive.unlink()
        archive.symlink_to(self.root / consumer.RELEASE_NAMES[0])
        with self.assertRaises(ValueError):
            consumer.stage(self.root, SHA)

    def test_destination_symlink_rejected(self):
        (self.root / consumer.OUTPUT).symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            consumer.stage(self.root, SHA)

    def test_receipt_cannot_authorize_apply(self):
        with patch.object(consumer, "verify_bytes", return_value={**RECEIPT, "can_apply": True}):
            with self.assertRaises(ValueError):
                consumer.stage(self.root, SHA)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ConsumerTests))
    if not result.wasSuccessful():
        sys.exit(1)
    print(f"EZ2_ENVELOPE_CONSUMER_GUARD_PASS cases={result.testsRun} disposable_only=true localwp_touched=false")
