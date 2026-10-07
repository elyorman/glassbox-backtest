"""Source preservation cannot include secrets, overwrite evidence or trust unsafe paths."""

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


class SourceArchiveTests(unittest.TestCase):
    def test_frozen_replay_cannot_import_unverified_cached_bytecode(self):
        import py_compile
        from research.source_archive import archive_sources, verify_stock_campaign
        package = self.root / "python" / "pkg"
        package.mkdir()
        module = package / "__init__.py"
        module.write_text("value = 1\n")
        research = self.root / "python" / "research"
        research.mkdir()
        (research / "stock_campaign.py").write_text(
            "import json, pkg\nprint(json.dumps({'value': pkg.value}))\n")
        manifest = archive_sources(self.root, self.output)
        archived_module = self.output / "pkg" / "__init__.py"
        archived_module.write_text("value = 2\n")
        py_compile.compile(str(archived_module), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        archived_module.write_text("value = 1\n")
        campaign = Path(self.temp.name) / "campaign"
        campaign.mkdir()
        (campaign / "EXPERIMENT_PLAN.json").write_text(json.dumps({"source_hashes": manifest["files"]}))
        self.assertEqual(verify_stock_campaign(self.output, campaign), {"value": 1})

    def test_archive_cannot_be_placed_inside_its_source_tree(self):
        from research.source_archive import archive_sources
        with self.assertRaisesRegex(ValueError, "inside"):
            archive_sources(self.root, self.root / "python" / "archive")

    def test_malformed_manifest_is_a_validation_error(self):
        from research.source_archive import verify_source_archive
        self.output.mkdir()
        (self.output / "SOURCE_ARCHIVE.json").write_text("[]")
        with self.assertRaises(ValueError):
            verify_source_archive(self.output)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        (self.root / "python" / "quant_core").mkdir(parents=True)
        (self.root / "python" / "quant_core" / "a.py").write_text("value = 1\n")
        (self.root / "python" / "quant_core" / "__pycache__").mkdir()
        (self.root / "python" / "quant_core" / "__pycache__" / "a.pyc").write_bytes(b"cache")
        (self.root / ".env").write_text("FAKE_KEY=not-for-backup\n")
        self.output = Path(self.temp.name) / "archive"

    def test_archive_exact_sources_excludes_secrets_and_preserves_originals(self):
        from research.source_archive import archive_sources, verify_source_archive
        manifest = archive_sources(self.root, self.output)
        self.assertEqual(set(manifest["files"]), {"quant_core/a.py"})
        self.assertEqual(manifest, verify_source_archive(self.output))
        self.assertEqual((self.root / "python/quant_core/a.py").read_text(), "value = 1\n")
        self.assertFalse((self.output / ".env").exists())

    def test_archive_refuses_existing_output_and_detects_tampering(self):
        from research.source_archive import archive_sources, verify_source_archive
        archive_sources(self.root, self.output)
        with self.assertRaises(FileExistsError):
            archive_sources(self.root, self.output)
        (self.output / "quant_core/a.py").write_text("value = 2\n")
        with self.assertRaisesRegex(ValueError, "hash|changed"):
            verify_source_archive(self.output)

    def test_verifier_rejects_added_python_sources(self):
        from research.source_archive import archive_sources, verify_source_archive
        archive_sources(self.root, self.output)
        (self.output / "quant_core/extra.py").write_text("pass\n")
        with self.assertRaisesRegex(ValueError, "source set"):
            verify_source_archive(self.output)

    def test_manifest_cannot_escape_archive(self):
        from research.source_archive import verify_source_archive
        self.output.mkdir()
        (self.output / "SOURCE_ARCHIVE.json").write_text(json.dumps({"files": {"../outside.py": "a"*64}}))
        with self.assertRaisesRegex(ValueError, "path"):
            verify_source_archive(self.output)

    def test_archive_refuses_symlink_sources(self):
        from research.source_archive import archive_sources
        external = Path(self.temp.name) / "private.py"
        external.write_text("private = 1\n")
        (self.root / "python/quant_core/link.py").symlink_to(external)
        with self.assertRaisesRegex(ValueError, "symlink"):
            archive_sources(self.root, self.output)


if __name__ == "__main__":
    unittest.main()
