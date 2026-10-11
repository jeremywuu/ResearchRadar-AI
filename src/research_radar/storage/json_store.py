"""Structured local JSON output with history and feedback preservation."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from research_radar.models import PipelineReport


def _json_value(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


class JsonOutputStore:
    """Write one current snapshot per category in an ignored local directory."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def write(self, report: PipelineReport) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{report.category}.json"
        existing_by_id = self._existing_records(output_path)
        records = [_json_value(record) for record in report.records]
        for record in records:
            opportunity = record["opportunity"]
            existing = existing_by_id.get(opportunity["opportunity_id"])
            if existing is None:
                continue
            old_opportunity = existing.get("opportunity", {})
            opportunity["first_seen_at"] = min(
                opportunity["first_seen_at"],
                old_opportunity.get("first_seen_at", opportunity["first_seen_at"]),
            )
            opportunity["last_seen_at"] = max(
                opportunity["last_seen_at"],
                old_opportunity.get("last_seen_at", opportunity["last_seen_at"]),
            )
            if record.get("feedback") is None and existing.get("feedback") is not None:
                record["feedback"] = existing["feedback"]
                record["personalized_score"] = existing.get("personalized_score")
                record["rank"] = existing.get("rank")

        payload = {
            "category": report.category,
            "pipeline_status": report.status.value,
            "summary": {
                "records_processed": report.records_processed,
                "records_accepted": report.records_accepted,
                "duplicates_found": report.duplicates_found,
                "records_excluded": report.records_excluded,
                "validation_errors": list(report.validation_errors),
                "failure": report.failure,
            },
            "records": records,
        }
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report.output_path = output_path
        return output_path

    @staticmethod
    def _existing_records(path: Path) -> dict[str, dict[str, Any]]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        records = payload.get("records", []) if isinstance(payload, dict) else []
        return {
            record["opportunity"]["opportunity_id"]: record
            for record in records
            if isinstance(record, dict)
            and isinstance(record.get("opportunity"), dict)
            and isinstance(record["opportunity"].get("opportunity_id"), str)
        }
