"""Canonical serialization and content hashes for reproducible runs."""

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from collections.abc import Mapping
from pathlib import Path


def primitive(value):
    if is_dataclass(value):
        return {field.name: primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {key: primitive(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [primitive(item) for item in value]
    return value


def canonical_json(value) -> str:
    return json.dumps(primitive(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def code_hash() -> str:
    """SHA-256 over every quant_core source file; run manifests record it as the engine hash."""
    root = Path(__file__).resolve().parents[1]
    return content_hash(tuple((path.relative_to(root).as_posix(), path.read_text(encoding="utf-8"))
                              for path in sorted(root.rglob("*.py"), key=lambda path: path.relative_to(root).parts)))
