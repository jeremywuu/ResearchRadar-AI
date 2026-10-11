"""Local fixture collection; live adapters arrive in a later milestone."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_fixture_records(path: Path) -> list[dict[str, Any]]:
    """Load a JSON array of raw fixture records without performing network I/O."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load fixture file {path}: {exc}") from exc
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError(f"{path} must contain a JSON array of objects")
    return data
