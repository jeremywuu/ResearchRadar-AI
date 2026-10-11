"""Stable identifier generation for records observed across multiple runs."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), path, parsed.query, ""))


def generate_stable_identifier(prefix: str, *identity_parts: str) -> str:
    """Return a deterministic identifier from stable, source-owned identity fields."""

    normalized = []
    for part in identity_parts:
        value = _normalize_url(part) if "://" in part else _normalize_text(part)
        normalized.append(value)
    digest = hashlib.sha256("\x1f".join(normalized).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
