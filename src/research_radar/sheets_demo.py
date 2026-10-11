"""Synthetic workbook state for the offline Sheets planning demonstration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from research_radar.models import ExecutionReport
from research_radar.storage.sheets import InMemorySheetsAdapter, sheet_rows_from_report


def build_demo_sheets_adapter(execution: ExecutionReport) -> InMemorySheetsAdapter:
    """Create sorted mock sheets containing one unchanged and one stale row per category."""

    rows_by_sheet: dict[str, list[dict[str, Any]]] = {}
    changed_header = {
        "jobs": "Job_Title",
        "phd": "Program_or_Position",
        "events": "Event_Name",
    }
    for category, report in execution.pipelines.items():
        if report.failure is not None:
            continue
        schema, desired = sheet_rows_from_report(report)
        existing: list[dict[str, Any]] = []
        if desired:
            existing.append(deepcopy(desired[0]))
        if len(desired) > 1:
            stale = deepcopy(desired[1])
            stale[changed_header[category]] = "Outdated synthetic value"
            existing.insert(0, stale)
        rows_by_sheet[schema.name] = existing
    return InMemorySheetsAdapter(rows_by_sheet)
