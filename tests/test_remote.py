"""Shared download plumbing: safe errors and an immutable request cache."""

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from quant_core.data.remote import RequestCache, fetch, publish_bytes, unique_object
from quant_core.provenance import canonical_json, content_hash

AT = datetime(2024, 1, 10, 23, 30, tzinfo=timezone.utc)
REQUEST = {"endpoint": "prices", "ticker": "SPY"}


class FetchTests(unittest.TestCase):
    def test_errors_use_supplied_messages_and_never_echo_secrets(self):
        url = "https://example.invalid/x?token=SECRET-1"
        cases = [(HTTPError(url, 404, "SECRET-1", {}, BytesIO(b"SECRET-1")), "unknown ticker"),
                 (HTTPError(url, 500, "SECRET-1", {}, BytesIO(b"SECRET-1")), r"Demo request failed \(HTTP 500\)"),
                 (URLError(url), "Demo transport failed")]
        for error, expected in cases:
            with self.subTest(expected=expected), patch("quant_core.data.remote.build_opener") as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaisesRegex(ValueError, expected) as caught:
                    fetch(url, {"Authorization": "Token SECRET-1"}, 30, "Demo", {404: "unknown ticker"})
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)

    def test_oversized_responses_are_refused(self):
        with patch("quant_core.data.remote.MAX_RESPONSE_BYTES", 3), \
                patch("quant_core.data.remote.build_opener") as opener:
            opener.return_value.open.return_value = BytesIO(b"1234")
            with self.assertRaisesRegex(ValueError, "exceeded"):
                fetch("https://example.invalid", {}, 30, "Demo")

    def test_duplicate_json_keys_are_refused(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            json.loads('{"a":1,"a":2}', object_pairs_hook=unique_object)


class RequestCacheTests(unittest.TestCase):
    def test_store_then_load_round_trips_bytes_and_time(self):
        with TemporaryDirectory() as directory:
            cache = RequestCache(Path(directory), "Demo", ".json")
            self.assertIsNone(cache.load(REQUEST))
            cache.store(REQUEST, b"[1]", AT)
            self.assertEqual(cache.load(REQUEST), (b"[1]", AT))
            self.assertTrue((Path(directory) / (sha256(b"[1]").hexdigest() + ".json")).exists())
            self.assertIsNone(cache.load(dict(REQUEST, ticker="IEF")))

    def test_corrupted_bodies_and_manifests_are_rejected_not_replaced(self):
        with TemporaryDirectory() as directory:
            cache = RequestCache(Path(directory), "Demo", ".json")
            cache.store(REQUEST, b"[1]", AT)
            body = Path(directory) / (sha256(b"[1]").hexdigest() + ".json")
            body.write_bytes(b"[2]")
            with self.assertRaisesRegex(ValueError, "Demo cache integrity"):
                cache.load(REQUEST)
            with self.assertRaisesRegex(ValueError, "Demo cache integrity mismatch"):
                cache.store(REQUEST, b"[1]", AT)
            self.assertEqual(body.read_bytes(), b"[2]")
            manifest = next(Path(directory).glob("*.request.json"))
            envelope = json.loads(manifest.read_text())
            for change in ({"retrieved_at": "2024-01-10T23:30:00"}, {"schema_version": 2},
                           {"request": dict(REQUEST, ticker="IEF")}):
                with self.subTest(change=change):
                    altered = dict(envelope["manifest"], **change)
                    manifest.write_text(canonical_json({"manifest": altered, "manifest_hash": content_hash(altered)}))
                    with self.assertRaisesRegex(ValueError, "Demo cache"):
                        cache.load(REQUEST)

    def test_failed_publication_leaves_no_partial_files(self):
        with TemporaryDirectory() as directory:
            with patch("quant_core.data.remote.os.link", side_effect=OSError("blocked")):
                with self.assertRaisesRegex(ValueError, "Cannot persist Demo cache"):
                    publish_bytes(b"x", Path(directory) / "x.json", "Demo")
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
