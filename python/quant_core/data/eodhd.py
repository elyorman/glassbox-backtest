"""Offline EODHD daily JSON normalization with immutable original-byte caching.

No network access occurs here. Provider tickers, stable identities, calendar and
reviewed actions are supplied independently; OHLC never uses adjusted_close.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from quant_core.data import Bar, DataMetadata, RAW_PRICES_SPLIT_ADJUSTED_VOLUME, SPLIT_ADJUSTED_VOLUME_LIMITATION, Security, Snapshot
from quant_core.provenance import canonical_json, content_hash


def _valid_ticker(ticker):
    return isinstance(ticker, str) and re.fullmatch(r"[A-Za-z0-9_^=-]+\.[A-Za-z0-9]+", ticker) is not None


def _normalized_bar(row, security_id, retrieved_day):
    required = {"date", "open", "high", "low", "close", "volume"}
    if not isinstance(row, dict) or not required <= set(row):
        raise ValueError("Missing daily bar fields")
    day_text = row["date"]
    if not isinstance(day_text, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day_text):
        raise ValueError("Invalid ISO session date")
    day = date.fromisoformat(day_text)
    if day > retrieved_day:
        raise ValueError("Bar session follows retrieval date")
    volume = row["volume"]
    if isinstance(volume, bool) or not isinstance(volume, (int, Decimal)):
        raise ValueError("Volume must be numeric")
    if not Decimal(volume).is_finite() or Decimal(volume) != Decimal(volume).to_integral_value():
        raise ValueError("Volume must be an integer")
    return Bar(security_id, day, row["open"], row["high"], row["low"], row["close"], volume)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate provider JSON field")
        result[key] = value
    return result


def _rows(raw):
    try:
        rows = json.loads(raw, parse_float=Decimal, object_pairs_hook=_unique_object)
        if not isinstance(rows, list):
            raise ValueError("Expected daily JSON array")
        if not rows:
            raise ValueError("Empty daily JSON array")
        return rows
    except (ValueError, TypeError, UnicodeError):
        # Provider bodies and parser messages can echo credential-bearing URLs.
        raise ValueError("EODHD response is not a valid daily JSON array") from None


def _validated_response(raw, start, end, retrieved_at):
    bars = [_normalized_bar(row, "validated-provider-row", retrieved_at.astimezone(timezone.utc).date())
            for row in _rows(raw)]
    if any(not start <= bar.session <= end for bar in bars):
        raise ValueError("Response outside requested bounds")
    if len({bar.session for bar in bars}) != len(bars):
        raise ValueError("Duplicate response sessions")


def _cache_bytes(raw: bytes, directory: Path) -> None:
    """Publish by content digest without replacing even a corrupted observation."""
    _publish_bytes(raw, directory / (sha256(raw).hexdigest() + ".json"))


def _publish_bytes(raw: bytes, destination: Path) -> None:
    temporary = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink():
            raise ValueError("EODHD raw cache integrity requires a regular file")
        if destination.exists():
            if destination.read_bytes() != raw:
                raise ValueError("EODHD raw cache integrity mismatch")
            return
        with NamedTemporaryFile(mode="wb", dir=destination.parent, prefix=".eodhd-",
                                suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.is_symlink() or destination.read_bytes() != raw:
                raise ValueError("EODHD raw cache integrity mismatch") from None
    except OSError:
        raise ValueError("Cannot persist EODHD raw cache") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class EodhdJsonSource:
    responses: Mapping[str, bytes] = field(repr=False)
    ticker_security_ids: Mapping[str, str]
    sessions: tuple[date, ...]
    securities: tuple[Security, ...]
    metadata: DataMetadata
    actions: tuple = ()
    actions_review_hash: str | None = None
    cache_dir: Path | None = None

    def load(self) -> Snapshot:
        if not isinstance(self.metadata, DataMetadata) or self.metadata.source != "eodhd":
            raise ValueError("EODHD source requires metadata.source='eodhd'")
        if not isinstance(self.responses, Mapping) or not self.responses:
            raise ValueError("EODHD source requires nonempty ticker/response mapping")
        if not isinstance(self.ticker_security_ids, Mapping):
            raise ValueError("Supply explicit EODHD ticker/security mapping")
        if set(self.responses) != set(self.ticker_security_ids):
            raise ValueError("Each response must have an explicit ticker/security mapping")
        if any(not _valid_ticker(t) for t in self.responses):
            raise ValueError("Invalid EODHD ticker; URLs and query strings are not accepted")
        actions = tuple(self.actions)
        reviewed = self.actions_review_hash is not None
        if reviewed and (not isinstance(self.actions_review_hash, str)
                         or not re.fullmatch(r"[0-9a-f]{64}", self.actions_review_hash)):
            raise ValueError("Action review requires a SHA-256 evidence hash")
        if (actions or self.metadata.actions_complete) and not reviewed:
            raise ValueError("Supplied or complete corporate actions require explicit review evidence")
        bars = []
        hashes = [("eodhd:calendar", content_hash(self.sessions)),
                  ("eodhd:securities", content_hash(self.securities)),
                  ("eodhd:ticker_mapping", content_hash(self.ticker_security_ids)),
                  ("eodhd:actions", content_hash(actions))]
        retrieved_day = self.metadata.retrieved_at.astimezone(timezone.utc).date()
        for ticker, raw in sorted(self.responses.items()):
            if not isinstance(raw, bytes):
                raise ValueError("EODHD response must contain original bytes")
            for index, row in enumerate(_rows(raw), 1):
                try:
                    bars.append(_normalized_bar(row, self.ticker_security_ids[ticker], retrieved_day))
                except (ValueError, TypeError, KeyError, ArithmeticError):
                    raise ValueError(f"Invalid EODHD daily bar at row {index}; check fields and retrieval date") from None
            hashes.append(("eodhd:response:" + ticker, sha256(raw).hexdigest()))
        if reviewed:
            hashes.append(("eodhd:reviewed_actions", self.actions_review_hash))
        limitations = list(self.metadata.limitations)
        limitations.append(SPLIT_ADJUSTED_VOLUME_LIMITATION)
        limitations.append("Supplied registry/calendar do not establish historical index membership or provider delisting coverage.")
        if not self.metadata.actions_complete:
            limitations.append("Corporate actions are incomplete: bars alone do not establish splits, dividends, payable dates or final delisting outcomes.")
        metadata = replace(self.metadata, adjustment_policy=RAW_PRICES_SPLIT_ADJUSTED_VOLUME,
                           limitations=tuple(dict.fromkeys(limitations)),
                           input_hashes=tuple(self.metadata.input_hashes) + tuple(hashes))
        try:
            snapshot = Snapshot(self.sessions, tuple(bars), metadata, self.securities, actions)
        except (ValueError, TypeError):
            raise ValueError("EODHD snapshot violates supplied calendar, security or corporate-action contract") from None
        if self.cache_dir is not None:
            for raw in self.responses.values():
                _cache_bytes(raw, Path(self.cache_dir))
        return snapshot


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None  # Do not forward a credential-bearing request to another URL.


@dataclass(frozen=True)
class EodhdResponse:
    raw: bytes = field(repr=False)
    retrieved_at: datetime


@dataclass(frozen=True)
class EodhdClient:
    """Explicit, single-symbol downloader. No credentials are discovered on disk.

    A successful request is reused forever within the chosen cache version. Use a
    new cache directory deliberately to retrieve revised observations. No retry,
    bulk request or corporate-action fetch occurs implicitly.
    """
    api_token: str = field(repr=False)
    cache_dir: Path
    timeout: int = 30

    def __post_init__(self):
        if not isinstance(self.api_token, str) or not self.api_token or any(c.isspace() for c in self.api_token):
            raise ValueError("EODHD token must be explicitly supplied and nonempty")
        if type(self.timeout) is not int or self.timeout <= 0:
            raise ValueError("EODHD timeout must be a positive number of seconds")
        object.__setattr__(self, "cache_dir", Path(self.cache_dir))

    def download(self, ticker: str, start: date, end: date) -> EodhdResponse:
        if not _valid_ticker(ticker) or type(start) is not date or type(end) is not date or end < start:
            raise ValueError("EODHD request requires a ticker and ascending date bounds")
        request_fields = {"ticker": ticker, "from": start.isoformat(), "to": end.isoformat(),
                          "fmt": "json", "period": "d", "order": "a"}
        request_path = self.cache_dir / (content_hash(request_fields) + ".request.json")
        if request_path.exists() or request_path.is_symlink():
            return self._cached(request_path, request_fields)
        query = urlencode({"api_token": self.api_token, "fmt": "json", "period": "d", "order": "a",
                           "from": start.isoformat(), "to": end.isoformat()})
        request = Request("https://eodhd.com/api/eod/" + ticker + "?" + query,
                          headers={"Accept": "application/json", "User-Agent": "quant-platform-core"})
        try:
            with build_opener(_NoRedirect()).open(request, timeout=self.timeout) as response:
                raw = response.read(64 * 1024 * 1024 + 1)
        except HTTPError as exc:
            status = exc.code if type(exc.code) is int else 0
            if status == 429:
                message = "EODHD rate limit reached (HTTP 429); no automatic retry"
            elif status in (401, 403):
                message = "EODHD authentication or entitlement rejected (HTTP " + str(status) + ")"
            else:
                message = "EODHD request failed (HTTP " + str(status) + ")"
            raise ValueError(message) from None
        except OSError:
            raise ValueError("EODHD transport failed; check connectivity and request settings") from None
        if not isinstance(raw, bytes) or len(raw) > 64 * 1024 * 1024:
            raise ValueError("EODHD response exceeded the supported size")
        retrieved_at = datetime.now(timezone.utc)
        try:
            _validated_response(raw, start, end, retrieved_at)
        except (ValueError, TypeError, ArithmeticError):
            raise ValueError("Invalid EODHD daily response or requested date bounds") from None
        _cache_bytes(raw, self.cache_dir)
        manifest = {"schema_version": 1, "request": request_fields,
                    "response_hash": sha256(raw).hexdigest(), "retrieved_at": retrieved_at.isoformat()}
        envelope = {"manifest_hash": content_hash(manifest), "manifest": manifest}
        _publish_bytes((canonical_json(envelope) + "\n").encode("utf-8"), request_path)
        return EodhdResponse(raw, retrieved_at)

    def _cached(self, path, request_fields):
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError("Invalid request cache file")
            envelope = json.loads(path.read_bytes(), object_pairs_hook=_unique_object)
            if not isinstance(envelope, dict) or set(envelope) != {"manifest", "manifest_hash"}:
                raise ValueError("Invalid request cache envelope")
            manifest = envelope["manifest"]
            if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "request", "response_hash", "retrieved_at"}:
                raise ValueError("Invalid request cache fields")
            if content_hash(manifest) != envelope["manifest_hash"]:
                raise ValueError("Request cache integrity mismatch")
            if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1 or manifest["request"] != request_fields:
                raise ValueError("Invalid request cache contract")
            digest = manifest["response_hash"]
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ValueError("Invalid response cache hash")
            retrieved_at = datetime.fromisoformat(manifest["retrieved_at"])
            if retrieved_at.utcoffset() is None:
                raise ValueError("Invalid cache retrieval timestamp")
            raw_path = self.cache_dir / (digest + ".json")
            if raw_path.is_symlink() or not raw_path.is_file():
                raise ValueError("Invalid raw cache file")
            raw = raw_path.read_bytes()
            if sha256(raw).hexdigest() != digest:
                raise ValueError("Raw cache integrity mismatch")
            _validated_response(raw, date.fromisoformat(request_fields["from"]),
                                date.fromisoformat(request_fields["to"]), retrieved_at)
            return EodhdResponse(raw, retrieved_at)
        except (ValueError, TypeError, KeyError, OSError, ArithmeticError):
            raise ValueError("EODHD cache integrity or schema validation failed; original bytes were not overwritten") from None
