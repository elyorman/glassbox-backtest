"""Download plumbing shared by provider clients: one safe GET and an immutable local cache.

Original response bytes are published once under their SHA-256 and never replaced.
A request manifest maps a request (never a credential) to its response hash and
retrieval time, so a cached request is not sent again.
"""

from datetime import datetime
from hashlib import sha256
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from quant_core.provenance import canonical_json, content_hash

MAX_RESPONSE_BYTES = 64 * 1024 * 1024


def unique_object(pairs):
    """JSON object hook that refuses duplicate keys instead of keeping the last one."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None  # Never forward credential headers to another URL.


def fetch(url: str, headers: dict, timeout: int, label: str, messages=None) -> bytes:
    """One GET without redirects or retries; errors never echo the URL, headers or body."""
    try:
        with build_opener(_NoRedirect()).open(Request(url, headers=headers), timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            missing = getattr(response, "length", None)  # Bytes promised by Content-Length but not received.
    except HTTPError as exc:
        status = exc.code if type(exc.code) is int else 0
        raise ValueError((messages or {}).get(status, f"{label} request failed (HTTP {status})")) from None
    except (OSError, ValueError, HTTPException):
        # Invalid headers and URLs raise ValueError with their content; never echo it.
        raise ValueError(f"{label} transport failed; check connectivity") from None
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError(f"{label} response exceeded the supported size")
    if missing:
        raise ValueError(f"{label} response was cut off; try again")
    return raw


def publish_bytes(raw: bytes, destination: Path, label: str) -> None:
    """Publish complete bytes by hard link; an existing file is never replaced."""
    temporary = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink():
            raise ValueError(f"{label} cache integrity requires a regular file")
        if destination.exists():
            if destination.read_bytes() != raw:
                raise ValueError(f"{label} cache integrity mismatch")
            return
        with NamedTemporaryFile(mode="wb", dir=destination.parent, prefix=".download-",
                                suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.is_symlink() or destination.read_bytes() != raw:
                raise ValueError(f"{label} cache integrity mismatch") from None
    except OSError:
        raise ValueError(f"Cannot persist {label} cache") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass  # A leftover temporary file never affects the published one.


class RequestCache:
    """Request manifests and content-addressed response bodies in one directory."""

    def __init__(self, directory: Path, label: str, suffix: str):
        self.directory, self.label, self.suffix = Path(directory), label, suffix

    def _manifest_path(self, request):
        return self.directory / (content_hash(request) + ".request.json")

    def load(self, request: dict):
        """Return (raw bytes, retrieval time) for a cached request, or None if never stored."""
        path = self._manifest_path(request)
        if not (path.exists() or path.is_symlink()):
            return None
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError
            envelope = json.loads(path.read_bytes(), object_pairs_hook=unique_object)
            if not isinstance(envelope, dict) or set(envelope) != {"manifest", "manifest_hash"}:
                raise ValueError
            manifest = envelope["manifest"]
            if (not isinstance(manifest, dict)
                    or set(manifest) != {"schema_version", "request", "response_hash", "retrieved_at"}
                    or content_hash(manifest) != envelope["manifest_hash"]
                    or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
                    or manifest["request"] != request):
                raise ValueError
            digest = manifest["response_hash"]
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ValueError
            retrieved_at = datetime.fromisoformat(manifest["retrieved_at"])
            if retrieved_at.utcoffset() is None:
                raise ValueError
            body = self.directory / (digest + self.suffix)
            if body.is_symlink() or not body.is_file():
                raise ValueError
            raw = body.read_bytes()
            if sha256(raw).hexdigest() != digest:
                raise ValueError
            return raw, retrieved_at
        except (ValueError, TypeError, KeyError, OSError):
            raise ValueError(f"{self.label} cache integrity or schema validation failed; "
                             "original bytes were not overwritten") from None

    def store(self, request: dict, raw: bytes, retrieved_at: datetime) -> None:
        """Record a download; if the request is already recorded, the first record is kept."""
        if json.loads(canonical_json(request)) != request or retrieved_at.utcoffset() is None:
            raise ValueError(f"{self.label} cache needs plain JSON request fields and a timezone-aware time")
        digest = sha256(raw).hexdigest()
        publish_bytes(raw, self.directory / (digest + self.suffix), self.label)
        manifest = {"schema_version": 1, "request": request, "response_hash": digest,
                    "retrieved_at": retrieved_at.isoformat()}
        envelope = {"manifest_hash": content_hash(manifest), "manifest": manifest}
        try:
            publish_bytes((canonical_json(envelope) + "\n").encode("utf-8"), self._manifest_path(request), self.label)
        except ValueError:
            if self.load(request) is None:  # Raises if the existing record is corrupt.
                raise
