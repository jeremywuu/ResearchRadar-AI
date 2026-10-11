"""Live spreadsheet orchestration over the existing Sheets adapter seam."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from research_radar.config import load_watchlist
from research_radar.demo import process_demo
from research_radar.storage.google_sheets import (
    GoogleSheetsAdapter,
    SheetsConfigurationError,
)
from research_radar.storage.sheets import (
    WATCHLIST_SCHEMA,
    FeedbackLoadResult,
    SheetSyncPlan,
    WorkbookSyncReport,
    load_feedback,
    plan_sheet_sync,
    sync_execution_report,
    watchlist_rows,
)


@dataclass(frozen=True)
class LiveDemoSyncResult:
    workbook: WorkbookSyncReport
    watchlist_plan: SheetSyncPlan
    feedback: FeedbackLoadResult


def run_live_demo_sync(
    adapter: GoogleSheetsAdapter,
    *,
    project_root: Path,
    apply: bool,
    run_id: str,
    timestamp: datetime,
    reference_date: date,
) -> LiveDemoSyncResult:
    """Plan or apply synthetic data only after validating the live workbook."""

    if apply:
        adapter.settings.require_demo_writes_allowed()
    initialization = adapter.initialize_workbook(apply=False)
    if initialization.missing_sheets:
        raise SheetsConfigurationError(
            "approved worksheets are missing; run sheets-init before synchronization"
        )
    if initialization.incompatible_headers:
        raise SheetsConfigurationError(
            "one or more worksheets have incompatible headers; no synchronization was attempted"
        )

    feedback = load_feedback(adapter)
    if apply and (feedback.invalid_records or feedback.conflicts):
        raise SheetsConfigurationError(
            "My_Feedback contains invalid rows or duplicate Record_ID values; apply refused"
        )
    execution = process_demo(
        ("jobs", "phd", "events"),
        project_root=project_root,
        observed_at=timestamp,
        reference_date=reference_date,
        feedback_by_id=feedback.feedback_by_id,
    )
    targets = load_watchlist(project_root / "config" / "watchlist.yaml")
    watchlist_plan = plan_sheet_sync(
        WATCHLIST_SCHEMA,
        watchlist_rows(targets),
        adapter.read_worksheet("Watchlist"),
        run_id=run_id,
        timestamp=timestamp,
        include_change_log=False,
    )
    if apply and (watchlist_plan.invalid_records or watchlist_plan.conflicts):
        raise SheetsConfigurationError("Watchlist synchronization plan is unsafe; apply refused")

    workbook = sync_execution_report(
        execution,
        adapter,
        dry_run=not apply,
        run_id=run_id,
        timestamp=timestamp,
    )
    adapter.apply_plan(watchlist_plan, dry_run=not apply)
    return LiveDemoSyncResult(
        workbook=workbook,
        watchlist_plan=watchlist_plan,
        feedback=feedback,
    )
