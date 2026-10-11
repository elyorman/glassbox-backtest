"""Shared download plumbing: safe errors and an immutable request cache."""

from contextlib import contextmanager
from datetime import date, datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from quant_core.data.remote import RequestCache, fetch, publish_bytes, unique_object
from quant_core.provenance import canonical_json, content_hash

AT = datetime(2024, 1, 10, 23, 30, tzinfo=timezone.utc)
REQUEST = {"endpoint": "prices", "ticker": "SPY"}


@contextmanager
def local_server(respond):
    """A real HTTP server on 127.0.0.1; `respond(handler)` answers each GET. Yields (port, paths)."""
    paths = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            respond(self)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        with patch.dict(os.environ, {"no_proxy": "*", "NO_PROXY": "*"}):
            yield server.server_port, paths
    finally:
        server.shutdown()
        server.server_close()


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

    def test_redirects_are_not_followed(self):
        def redirect(handler):
            handler.send_response(302)
            handler.send_header("Location", f"http://localhost:{handler.server.server_port}/elsewhere")
            handler.end_headers()

        with local_server(redirect) as (port, paths):
            with self.assertRaisesRegex(ValueError, r"Demo request failed \(HTTP 302\)"):
                fetch(f"http://127.0.0.1:{port}/start", {"Authorization": "Token SECRET-1"}, 5, "Demo")
        self.assertEqual(paths, ["/start"])

    def test_cut_off_responses_are_refused(self):
        def short(handler):
            handler.send_response(200)
            handler.send_header("Content-Length", "100")
            handler.end_headers()
            handler.wfile.write(b"x" * 50)
            handler.close_connection = True

        with local_server(short) as (port, _):
            with self.assertRaisesRegex(ValueError, "cut off"):
                fetch(f"http://127.0.0.1:{port}/", {}, 5, "Demo")

    def test_unsendable_requests_never_echo_secrets(self):
        for url, headers in (("https://example.invalid/", {"Authorization": "Token SECRET-1\n"}),
                             ("example.invalid/SECRET-1", {})):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "Demo transport failed") as caught:
                fetch(url, headers, 5, "Demo")
            self.assertNotIn("SECRET", str(caught.exception))

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

    def test_store_refuses_records_that_could_not_be_read_back(self):
        with TemporaryDirectory() as directory:
            cache = RequestCache(Path(directory), "Demo", ".json")
            for request, at in ((dict(REQUEST, day=date(2024, 1, 2)), AT), (REQUEST, datetime(2024, 1, 10))):
                with self.subTest(request=request), self.assertRaisesRegex(ValueError, "Demo cache needs"):
                    cache.store(request, b"[1]", at)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_a_repeated_download_keeps_the_first_record(self):
        with TemporaryDirectory() as directory:
            cache = RequestCache(Path(directory), "Demo", ".json")
            cache.store(REQUEST, b"[1]", AT)
            cache.store(REQUEST, b"[1]", datetime(2024, 1, 11, tzinfo=timezone.utc))
            cache.store(REQUEST, b"[2]", datetime(2024, 1, 12, tzinfo=timezone.utc))
            self.assertEqual(cache.load(REQUEST), (b"[1]", AT))

    def test_concurrent_publication_needs_identical_bytes(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / "x.json"

            def lose_race(content):
                def link(source, destination):
                    Path(destination).write_bytes(content)  # Another process published first.
                    raise FileExistsError
                return link

            with patch("quant_core.data.remote.os.link", side_effect=lose_race(b"x")):
                publish_bytes(b"x", target, "Demo")
            target.unlink()
            with patch("quant_core.data.remote.os.link", side_effect=lose_race(b"y")):
                with self.assertRaisesRegex(ValueError, "Demo cache integrity mismatch"):
                    publish_bytes(b"x", target, "Demo")
            self.assertEqual([p.name for p in Path(directory).iterdir()], ["x.json"])

    def test_failed_publication_leaves_no_partial_files(self):
        with TemporaryDirectory() as directory:
            with patch("quant_core.data.remote.os.link", side_effect=OSError("blocked")):
                with self.assertRaisesRegex(ValueError, "Cannot persist Demo cache"):
                    publish_bytes(b"x", Path(directory) / "x.json", "Demo")
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
