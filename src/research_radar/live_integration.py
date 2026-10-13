"""Safe review and dry-run planning for cached verified live opportunity data."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from research_radar.config import load_career_preferences, load_research_interests, load_watchlist
from research_radar.models import (
    AcademicEvent,
    CompensationDisclosureStatus,
    DomainFitClassification,
    EducationRequirement,
    EnglishCompatibility,
    ExecutionReport,
    IndustryJob,
    PhDOpportunity,
    PipelineReport,
    ProcessedOpportunity,
    SourceHealth,
    SourceVerificationStatus,
    UserFeedback,
)
from research_radar.pipelines import run_events_pipeline, run_jobs_pipeline, run_phd_pipeline
from research_radar.storage.sheets import (
    WATCHLIST_SCHEMA,
    FeedbackLoadResult,
    InMemorySheetsAdapter,
    SheetsAdapter,
    SheetSyncPlan,
    WorkbookSyncReport,
    build_success_run_log_rows,
    load_feedback,
    plan_sheet_sync,
    sync_execution_report,
    watchlist_rows,
)


class LiveDataError(ValueError):
    """Raised when cached live data or its target environment is unsafe."""


class DataMode(StrEnum):
    SYNTHETIC = "synthetic"
    LIVE = "live"


class TargetEnvironment(StrEnum):
    TEST = "test"
    LIVE_PILOT = "live-pilot"
    PRODUCTION = "production"


class RecommendationClassification(StrEnum):
    HIGH_PRIORITY = "HIGH_PRIORITY"
    RELEVANT = "RELEVANT"
    LOW_PRIORITY = "LOW_PRIORITY"
    NEEDS_REVIEW = "NEEDS_REVIEW"


LIVE_PILOT_WORKBOOK_TITLE = "ResearchRadar AI — LIVE PILOT"
INCREMENTAL_APPLY_CONFIRMATION = "CONFIRM_LIVE_PILOT_INCREMENTAL"


class ObservationState(StrEnum):
    CONFIRMED_ACTIVE = "CONFIRMED_ACTIVE"
    CONFIRMED_CLOSED = "CONFIRMED_CLOSED"
    NOT_OBSERVED = "NOT_OBSERVED_IN_LATEST_SUCCESSFUL_SCAN"
    SOURCE_UNAVAILABLE = "SOURCE_TEMPORARILY_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ObservationDecision:
    state: ObservationState
    may_change_opportunity_status: bool


@dataclass(frozen=True)
class ProvenanceRecord:
    record_id: str
    category: str
    valid: bool
    blocking_issues: tuple[str, ...]
    missing_important_fields: tuple[str, ...]
    source_stated_facts: tuple[str, ...]
    normalized_information: tuple[str, ...]
    rule_based_interpretations: tuple[str, ...]

    @property
    def review_required(self) -> bool:
        return bool(self.blocking_issues or self.missing_important_fields)


@dataclass(frozen=True)
class ProvenanceReport:
    records: tuple[ProvenanceRecord, ...]

    @property
    def valid_count(self) -> int:
        return sum(record.valid for record in self.records)

    @property
    def blocked_count(self) -> int:
        return len(self.records) - self.valid_count


@dataclass(frozen=True)
class RecommendationDecision:
    record_id: str
    category: str
    classification: RecommendationClassification
    domain_fit: DomainFitClassification
    methodological_fit: float
    research_question_fit: float
    explanation: str


@dataclass(frozen=True)
class RecommendationReport:
    decisions: tuple[RecommendationDecision, ...]

    @property
    def by_record_id(self) -> dict[str, RecommendationDecision]:
        return {decision.record_id: decision for decision in self.decisions}

    @property
    def counts(self) -> dict[RecommendationClassification, int]:
        return {
            classification: sum(
                decision.classification is classification for decision in self.decisions
            )
            for classification in RecommendationClassification
        }


@dataclass(frozen=True)
class InitialLiveSyncApproval:
    opportunity_inserts: Mapping[str, int]
    watchlist_inserts: int
    recommendation_counts: Mapping[RecommendationClassification, int]
    provenance_valid: int


INITIAL_LIVE_PILOT_APPROVAL = InitialLiveSyncApproval(
    opportunity_inserts={"jobs": 13, "phd": 1, "events": 1},
    watchlist_inserts=38,
    recommendation_counts={
        RecommendationClassification.HIGH_PRIORITY: 8,
        RecommendationClassification.RELEVANT: 7,
        RecommendationClassification.NEEDS_REVIEW: 6,
        RecommendationClassification.LOW_PRIORITY: 6,
    },
    provenance_valid=27,
)


@dataclass(frozen=True)
class SourceCoverage:
    source_id: str
    health: str
    retrieved_at: str | None
    records_returned: int
    records_matched: int
    records_considered: int
    records_extracted: int
    records_accepted: int


@dataclass(frozen=True)
class LiveSheetsPreview:
    execution: ExecutionReport
    provenance: ProvenanceReport
    recommendations: RecommendationReport
    workbook: WorkbookSyncReport
    watchlist_plan: SheetSyncPlan
    coverage: dict[str, SourceCoverage]
    review_report_path: Path
    offline: bool
    target_environment: TargetEnvironment
    feedback: FeedbackLoadResult
    preference_configuration_hash: str
    sheet_synced_at: datetime | None = None


@dataclass(frozen=True)
class InitialLiveSyncResult:
    preview: LiveSheetsPreview
    applied_sheets: tuple[str, ...]


@dataclass(frozen=True)
class IncrementalLiveSyncPlan:
    preview: LiveSheetsPreview
    plan_fingerprint: str
    artifact_path: Path


@dataclass(frozen=True)
class ScoringOnlySyncApproval:
    update_counts: Mapping[str, int]
    watchlist_unchanged: int


APPROVED_SCORING_ONLY_SYNC = ScoringOnlySyncApproval(
    update_counts={"jobs": 13, "phd": 1, "events": 1},
    watchlist_unchanged=38,
)


@dataclass(frozen=True)
class IncrementalLiveSyncResult:
    plan: IncrementalLiveSyncPlan
    applied_sheets: tuple[str, ...]


@dataclass(frozen=True)
class RecoverySheetPlan:
    completed_record_ids: tuple[str, ...]
    pending_record_ids: tuple[str, ...]
    conflicts: tuple[str, ...]


@dataclass(frozen=True)
class IncrementalRecoveryPlan:
    sheets: dict[str, RecoverySheetPlan]
    missing_change_event_ids: tuple[str, ...]
    conflicts: tuple[str, ...]


def validate_target_compatibility(
    data_mode: DataMode,
    target_environment: TargetEnvironment,
) -> None:
    """Reject every data/target pairing except the two explicitly enabled pairs."""

    if data_mode is DataMode.SYNTHETIC and target_environment is TargetEnvironment.TEST:
        return
    if data_mode is DataMode.LIVE and target_environment is TargetEnvironment.LIVE_PILOT:
        return
    if data_mode is DataMode.LIVE and target_environment is TargetEnvironment.PRODUCTION:
        raise LiveDataError("live production synchronization is not enabled in Milestone 4C.2")
    if data_mode is DataMode.LIVE:
        raise LiveDataError("live data may target only the separate live-pilot environment")
    raise LiveDataError("synthetic data may target only the test environment")


def validate_configured_data_mode(
    requested: DataMode,
    environment: Mapping[str, str] | None = None,
) -> None:
    values = environment if environment is not None else os.environ
    configured = values.get("RESEARCH_RADAR_DATA_MODE", "").strip().casefold()
    if configured and configured != requested.value:
        raise LiveDataError(
            f"RESEARCH_RADAR_DATA_MODE={configured} is incompatible with {requested.value} input"
        )


def configured_live_pilot_adapter(
    environment: Mapping[str, str] | None = None,
) -> SheetsAdapter | None:
    """Use only the dedicated pilot ID; never fall back to the synthetic TEST workbook ID."""

    from research_radar.storage.google_sheets import GoogleSheetsAdapter, GoogleSheetsSettings

    values = environment if environment is not None else os.environ
    spreadsheet_id = values.get("GOOGLE_LIVE_PILOT_SPREADSHEET_ID", "").strip()
    if not spreadsheet_id:
        return None
    target = values.get("RESEARCH_RADAR_SHEETS_ENV", "").strip().casefold()
    if target != TargetEnvironment.LIVE_PILOT.value:
        raise LiveDataError(
            "GOOGLE_LIVE_PILOT_SPREADSHEET_ID requires RESEARCH_RADAR_SHEETS_ENV=live-pilot"
        )
    settings = GoogleSheetsSettings(spreadsheet_id, TargetEnvironment.LIVE_PILOT.value)
    return GoogleSheetsAdapter.from_settings(settings, environment=values)


def validate_live_pilot_write_environment(
    environment: Mapping[str, str] | None = None,
) -> str:
    """Require every explicit live-pilot write guard and return the configured ID."""

    values = environment if environment is not None else os.environ
    if values.get("RESEARCH_RADAR_DATA_MODE", "").strip().casefold() != DataMode.LIVE.value:
        raise LiveDataError("RESEARCH_RADAR_DATA_MODE=live is required for LIVE PILOT writes")
    if (
        values.get("RESEARCH_RADAR_SHEETS_ENV", "").strip().casefold()
        != TargetEnvironment.LIVE_PILOT.value
    ):
        raise LiveDataError(
            "RESEARCH_RADAR_SHEETS_ENV=live-pilot is required for LIVE PILOT writes"
        )
    spreadsheet_id = values.get("GOOGLE_LIVE_PILOT_SPREADSHEET_ID", "").strip()
    if not spreadsheet_id:
        raise LiveDataError("GOOGLE_LIVE_PILOT_SPREADSHEET_ID is required for LIVE PILOT writes")
    return spreadsheet_id


def validate_live_pilot_identity(
    adapter: SheetsAdapter,
    *,
    expected_spreadsheet_id: str | None = None,
) -> None:
    configured_environment = getattr(getattr(adapter, "settings", None), "environment", None)
    if configured_environment != TargetEnvironment.LIVE_PILOT.value:
        raise LiveDataError("configured spreadsheet environment must be live-pilot")
    configured_id = getattr(getattr(adapter, "settings", None), "spreadsheet_id", None)
    if expected_spreadsheet_id is not None and configured_id != expected_spreadsheet_id:
        raise LiveDataError("adapter spreadsheet ID does not match the configured LIVE PILOT ID")
    read_title = getattr(adapter, "get_spreadsheet_title", None)
    if read_title is None or read_title() != LIVE_PILOT_WORKBOOK_TITLE:
        raise LiveDataError(
            f"configured workbook title must be exactly {LIVE_PILOT_WORKBOOK_TITLE!r}"
        )


def prepare_live_sheets_preview(
    *,
    project_root: Path,
    live_data_dir: Path,
    review_dir: Path,
    generated_at: datetime,
    reference_date: date,
    adapter: SheetsAdapter | None = None,
    target_environment: TargetEnvironment | None = None,
) -> LiveSheetsPreview:
    """Load cached live records, audit them, and plan Sheets changes without writes."""

    if generated_at.tzinfo is None:
        raise LiveDataError("generated_at must be timezone-aware")
    offline = adapter is None
    environment = target_environment or TargetEnvironment.LIVE_PILOT
    validate_target_compatibility(DataMode.LIVE, environment)
    if adapter is None:
        adapter = InMemorySheetsAdapter()
    else:
        configured_environment = getattr(getattr(adapter, "settings", None), "environment", None)
        if configured_environment is not None and configured_environment != environment.value:
            raise LiveDataError(
                "configured spreadsheet environment does not match the live-pilot target"
            )
        _validate_existing_workbook(adapter)

    feedback = load_feedback(adapter)
    if feedback.invalid_records or feedback.conflicts:
        raise LiveDataError("target feedback contains invalid rows or duplicate Record_ID values")
    execution, metadata = load_live_execution(
        project_root=project_root,
        live_data_dir=live_data_dir,
        reference_date=reference_date,
        feedback_by_id=feedback.feedback_by_id,
    )
    known_feedback_ids = {
        processed.opportunity.opportunity_id
        for report in execution.pipelines.values()
        for processed in report.records
    }
    for sheet_name in ("Industry_Jobs", "PhD_Opportunities", "Events"):
        known_feedback_ids.update(
            str(row.get("Record_ID"))
            for row in adapter.read_worksheet(sheet_name).rows
            if row.get("Record_ID")
        )
    unlinked_feedback_ids = set(feedback.feedback_by_id) - known_feedback_ids
    if unlinked_feedback_ids:
        joined = ", ".join(sorted(unlinked_feedback_ids))
        raise LiveDataError(f"feedback Record_ID values are not linked to known records: {joined}")
    provenance = audit_provenance(execution)
    preferences = load_career_preferences(project_root / "config" / "career_preferences.yaml")
    interests = load_research_interests(project_root / "config" / "research_interests.yaml")
    preference_configuration_hash = _preference_configuration_hash(interests, preferences)
    recommendations = classify_recommendations(
        execution,
        provenance,
        preferences["recommendation_rules"],
    )
    safe_execution = _syncable_execution(
        execution,
        provenance,
        recommendations,
        adapter,
    )
    run_id = f"live_preview_{generated_at.strftime('%Y%m%dT%H%M%SZ')}"
    workbook = sync_execution_report(
        safe_execution,
        adapter,
        dry_run=True,
        run_id=run_id,
        timestamp=generated_at,
    )
    watchlist = load_watchlist(project_root / "config" / "watchlist.yaml")
    watchlist_plan = plan_sheet_sync(
        WATCHLIST_SCHEMA,
        watchlist_rows(watchlist),
        adapter.read_worksheet("Watchlist"),
        run_id=run_id,
        timestamp=generated_at,
        include_change_log=False,
    )
    coverage = _source_coverage(metadata, execution)
    review_path = _write_review_report(
        review_dir,
        execution=execution,
        provenance=provenance,
        recommendations=recommendations,
        workbook=workbook,
        watchlist_plan=watchlist_plan,
        coverage=coverage,
        generated_at=generated_at,
        offline=offline,
        target_environment=environment,
    )
    return LiveSheetsPreview(
        execution=execution,
        provenance=provenance,
        recommendations=recommendations,
        workbook=workbook,
        watchlist_plan=watchlist_plan,
        coverage=coverage,
        review_report_path=review_path,
        offline=offline,
        target_environment=environment,
        feedback=feedback,
        preference_configuration_hash=preference_configuration_hash,
    )


def prepare_incremental_live_sync(
    *,
    project_root: Path,
    live_data_dir: Path,
    review_dir: Path,
    generated_at: datetime,
    reference_date: date,
    adapter: SheetsAdapter,
) -> IncrementalLiveSyncPlan:
    """Build a repeatable, read-only live-pilot plan and persist its recovery artifact."""

    preview = prepare_live_sheets_preview(
        project_root=project_root,
        live_data_dir=live_data_dir,
        review_dir=review_dir,
        generated_at=generated_at,
        reference_date=reference_date,
        adapter=adapter,
        target_environment=TargetEnvironment.LIVE_PILOT,
    )
    payload = _incremental_plan_payload(preview)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    fingerprint = sha256(canonical.encode("utf-8")).hexdigest()
    review_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = review_dir / f"incremental_plan_{fingerprint}.json"
    artifact = {
        "version": 1,
        "plan_fingerprint": fingerprint,
        "generated_at": generated_at.isoformat(),
        "target_environment": preview.target_environment.value,
        "plan": payload,
    }
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return IncrementalLiveSyncPlan(
        preview=preview,
        plan_fingerprint=fingerprint,
        artifact_path=artifact_path,
    )


def validate_incremental_apply_authorization(
    plan: IncrementalLiveSyncPlan,
    *,
    approved_fingerprint: str,
    confirmation: str,
) -> None:
    """Validate the auditable approval inputs required by a future incremental apply."""

    if approved_fingerprint != plan.plan_fingerprint:
        raise LiveDataError("approved incremental plan fingerprint does not match the current plan")
    if confirmation != INCREMENTAL_APPLY_CONFIRMATION:
        raise LiveDataError("explicit incremental apply confirmation is required")
    plans = (*plan.preview.workbook.plans.values(), plan.preview.watchlist_plan)
    if plan.preview.workbook.failures:
        raise LiveDataError("incremental plan contains pipeline synchronization failures")
    if any(item.invalid_records or item.conflicts for item in plans):
        raise LiveDataError("incremental plan contains invalid records or unresolved conflicts")
    if plan.preview.provenance.blocked_count:
        raise LiveDataError("incremental plan contains provenance-blocked records")


def apply_incremental_live_score_sync(
    *,
    project_root: Path,
    live_data_dir: Path,
    review_dir: Path,
    generated_at: datetime,
    reference_date: date,
    adapter: SheetsAdapter,
    approved_fingerprint: str,
    confirmation: str,
    approval: ScoringOnlySyncApproval = APPROVED_SCORING_ONLY_SYNC,
) -> IncrementalLiveSyncResult:
    """Apply one fingerprint-bound score-only plan to the dedicated LIVE PILOT."""

    expected_id = validate_live_pilot_write_environment()
    validate_live_pilot_identity(adapter, expected_spreadsheet_id=expected_id)
    plan = prepare_incremental_live_sync(
        project_root=project_root,
        live_data_dir=live_data_dir,
        review_dir=review_dir,
        generated_at=generated_at,
        reference_date=reference_date,
        adapter=adapter,
    )
    validate_incremental_apply_authorization(
        plan,
        approved_fingerprint=approved_fingerprint,
        confirmation=confirmation,
    )
    _validate_scoring_only_incremental_plan(plan, approval)

    applied: list[str] = []
    try:
        for category in ("jobs", "phd", "events"):
            sheet_plan = plan.preview.workbook.plans[category]
            adapter.apply_plan(sheet_plan, dry_run=False)
            applied.append(sheet_plan.sheet_name)
    except Exception as exc:
        completed = ", ".join(applied) or "none"
        raise LiveDataError(
            f"score-only synchronization failed after completed sheets: {completed}; "
            "do not retry apply without inspecting the workbook"
        ) from exc
    return IncrementalLiveSyncResult(plan=plan, applied_sheets=tuple(applied))


def _validate_scoring_only_incremental_plan(
    plan: IncrementalLiveSyncPlan,
    approval: ScoringOnlySyncApproval,
) -> None:
    allowed_fields = {
        "jobs": {"Research_Relevance", "Overall_Priority_Score"},
        "phd": {"Research_Fit_Score"},
        "events": {"Research_Relevance", "Priority_Score"},
    }
    problems: list[str] = []
    for category, expected_count in approval.update_counts.items():
        sheet_plan = plan.preview.workbook.plans[category]
        if sheet_plan.update_count != expected_count:
            problems.append(
                f"{category} updates are {sheet_plan.update_count}, expected {expected_count}"
            )
        if sheet_plan.insert_count:
            problems.append(f"{category} contains inserts")
        if sheet_plan.change_log_rows:
            problems.append(f"{category} contains Change_Log events")
        for operation in sheet_plan.updates:
            changed = set(operation.changed_fields)
            if not changed or not changed <= allowed_fields[category]:
                problems.append(
                    f"{category} update {operation.record_id} contains non-scoring fields"
                )
    watchlist = plan.preview.watchlist_plan
    if watchlist.insert_count or watchlist.update_count:
        problems.append("watchlist contains writes")
    if len(watchlist.unchanged_record_ids) != approval.watchlist_unchanged:
        problems.append(
            f"watchlist unchanged count is {len(watchlist.unchanged_record_ids)}, "
            f"expected {approval.watchlist_unchanged}"
        )
    if watchlist.change_log_rows:
        problems.append("watchlist contains Change_Log events")
    if problems:
        raise LiveDataError("approved scoring-only plan mismatch: " + "; ".join(problems))


def resolve_observation_state(
    *,
    source_health: SourceHealth,
    observed: bool,
    explicit_status: str | None,
) -> ObservationDecision:
    """Keep source availability separate from source-stated opportunity status."""

    if (
        source_health
        in {
            SourceHealth.FAILED,
            SourceHealth.BLOCKED,
            SourceHealth.UNSUPPORTED,
            SourceHealth.PARTIAL,
        }
        and not observed
    ):
        return ObservationDecision(ObservationState.SOURCE_UNAVAILABLE, False)
    if not observed and source_health in {SourceHealth.SUCCESS, SourceHealth.SUCCESS_NO_MATCHES}:
        return ObservationDecision(ObservationState.NOT_OBSERVED, False)
    normalized_status = (explicit_status or "").strip().upper()
    if observed and normalized_status == "CLOSED":
        return ObservationDecision(ObservationState.CONFIRMED_CLOSED, True)
    if observed and normalized_status in {"CONFIRMED_OPEN", "CONFIRMED_UPCOMING"}:
        return ObservationDecision(ObservationState.CONFIRMED_ACTIVE, True)
    return ObservationDecision(ObservationState.UNKNOWN, False)


def reconcile_incremental_plan(
    original: IncrementalLiveSyncPlan,
    adapter: SheetsAdapter,
) -> IncrementalRecoveryPlan:
    """Reconcile a partially applied plan by Record_ID without repeating completed writes."""

    sheets: dict[str, RecoverySheetPlan] = {}
    global_conflicts: list[str] = []
    plans = {
        plan.sheet_name: plan
        for plan in (*original.preview.workbook.plans.values(), original.preview.watchlist_plan)
    }
    for sheet_name, plan in plans.items():
        worksheet = adapter.read_worksheet(sheet_name)
        rows_by_id: dict[str, dict[str, Any]] = {}
        sheet_conflicts = [issue.message for issue in (*plan.invalid_records, *plan.conflicts)]
        for row in worksheet.rows:
            record_id = row.get("Record_ID")
            if not isinstance(record_id, str) or not record_id:
                sheet_conflicts.append("current worksheet row has no Record_ID")
                continue
            if record_id in rows_by_id:
                sheet_conflicts.append(f"duplicate Record_ID in current worksheet: {record_id}")
                continue
            rows_by_id[record_id] = row

        completed: list[str] = []
        pending: list[str] = []
        for operation in plan.inserts:
            record_id = str(operation.row["Record_ID"])
            current = rows_by_id.get(record_id)
            if current is None:
                pending.append(record_id)
            elif _rows_match(operation.row, current):
                completed.append(record_id)
            else:
                sheet_conflicts.append(f"inserted Record_ID has unexpected values: {record_id}")
        for operation in plan.updates:
            current = rows_by_id.get(operation.record_id)
            if current is None:
                sheet_conflicts.append(f"updated Record_ID is missing: {operation.record_id}")
            elif _fields_match(current, operation.changed_fields):
                completed.append(operation.record_id)
            elif _fields_match(current, operation.expected_values):
                pending.append(operation.record_id)
            else:
                sheet_conflicts.append(
                    f"updated Record_ID has concurrent values: {operation.record_id}"
                )
        for record_id in plan.unchanged_record_ids:
            if record_id in rows_by_id:
                completed.append(record_id)
            else:
                sheet_conflicts.append(f"previously unchanged Record_ID is missing: {record_id}")
        sheets[sheet_name] = RecoverySheetPlan(
            completed_record_ids=tuple(sorted(set(completed))),
            pending_record_ids=tuple(sorted(set(pending))),
            conflicts=tuple(sheet_conflicts),
        )
        global_conflicts.extend(f"{sheet_name}: {message}" for message in sheet_conflicts)

    change_log = adapter.read_worksheet("Change_Log")
    existing_event_ids = {
        str(row.get("Event_ID")) for row in change_log.rows if row.get("Event_ID")
    }
    expected_event_ids = {
        str(row["Event_ID"]) for plan in plans.values() for row in plan.change_log_rows
    }
    return IncrementalRecoveryPlan(
        sheets=sheets,
        missing_change_event_ids=tuple(sorted(expected_event_ids - existing_event_ids)),
        conflicts=tuple(global_conflicts),
    )


def _incremental_plan_payload(preview: LiveSheetsPreview) -> dict[str, Any]:
    plans = (*preview.workbook.plans.values(), preview.watchlist_plan)
    return {
        "preference_configuration_hash": preview.preference_configuration_hash,
        "recommendations": {
            decision.record_id: {
                "classification": decision.classification.value,
                "domain_fit": decision.domain_fit.value,
                "methodological_fit": decision.methodological_fit,
                "research_question_fit": decision.research_question_fit,
            }
            for decision in sorted(
                preview.recommendations.decisions, key=lambda item: item.record_id
            )
        },
        "sheets": {
            plan.sheet_name: {
                "inserts": [operation.row for operation in plan.inserts],
                "updates": [
                    {
                        "record_id": operation.record_id,
                        "changed_fields": operation.changed_fields,
                        "expected_values": operation.expected_values,
                    }
                    for operation in plan.updates
                ],
                "unchanged_record_ids": sorted(plan.unchanged_record_ids),
                "invalid": [issue.message for issue in plan.invalid_records],
                "conflicts": [issue.message for issue in plan.conflicts],
                "change_log_rows": [
                    {key: value for key, value in row.items() if key not in {"Run_ID", "Timestamp"}}
                    for row in plan.change_log_rows
                ],
            }
            for plan in sorted(plans, key=lambda item: item.sheet_name)
        },
        "pipeline_failures": preview.workbook.failures,
        "provenance_blocked": preview.provenance.blocked_count,
        "source_observations": {
            source_id: {
                "health": source.health,
                "retrieved_at": source.retrieved_at,
                "records_returned": source.records_returned,
                "records_matched": source.records_matched,
                "records_considered": source.records_considered,
                "records_extracted": source.records_extracted,
                "records_accepted": source.records_accepted,
            }
            for source_id, source in sorted(preview.coverage.items())
        },
    }


def _preference_configuration_hash(
    interests: Mapping[str, Any], preferences: Mapping[str, Any]
) -> str:
    relevant = {
        "research_interests": interests,
        "career_preferences": preferences,
    }
    canonical = json.dumps(relevant, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def _comparison_value(value: Any) -> Any:
    return " ".join(value.split()) if isinstance(value, str) else value


def _fields_match(current: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(
        _comparison_value(current.get(field, "")) == _comparison_value(value)
        for field, value in expected.items()
    )


def _rows_match(expected: dict[str, Any], current: dict[str, Any]) -> bool:
    return _fields_match(current, expected)


def apply_initial_live_pilot_sync(
    *,
    project_root: Path,
    live_data_dir: Path,
    review_dir: Path,
    generated_at: datetime,
    reference_date: date,
    adapter: SheetsAdapter,
    approval: InitialLiveSyncApproval = INITIAL_LIVE_PILOT_APPROVAL,
) -> InitialLiveSyncResult:
    """Apply exactly one approved initial live-pilot plan; any plan drift stops the write."""

    expected_id = validate_live_pilot_write_environment()
    validate_live_pilot_identity(adapter, expected_spreadsheet_id=expected_id)
    preview = prepare_live_sheets_preview(
        project_root=project_root,
        live_data_dir=live_data_dir,
        review_dir=review_dir,
        generated_at=generated_at,
        reference_date=reference_date,
        adapter=adapter,
        target_environment=TargetEnvironment.LIVE_PILOT,
    )
    _validate_initial_live_pilot_plan(preview, approval)

    recommended_execution = _recommended_execution(
        preview.execution,
        preview.provenance,
        preview.recommendations,
    )
    run_id = f"live_initial_{generated_at.strftime('%Y%m%dT%H%M%SZ')}"
    run_logs = build_success_run_log_rows(
        recommended_execution,
        preview.workbook.plans,
        run_id=run_id,
        timestamp=generated_at,
    )
    applied: list[str] = []
    try:
        for category in ("jobs", "phd", "events"):
            plan = preview.workbook.plans[category]
            adapter.apply_plan(plan, dry_run=False)
            applied.append(plan.sheet_name)
            if plan.change_log_rows and "Change_Log" not in applied:
                applied.append("Change_Log")
        adapter.apply_plan(preview.watchlist_plan, dry_run=False)
        applied.append("Watchlist")
        adapter.append_unique("Run_Logs", run_logs)
        applied.append("Run_Logs")
    except Exception as exc:
        completed = ", ".join(applied) or "none"
        raise LiveDataError(
            f"LIVE PILOT synchronization failed after completed sheets: {completed}; "
            "do not retry apply without inspecting the workbook"
        ) from exc
    return InitialLiveSyncResult(preview=preview, applied_sheets=tuple(applied))


def _validate_initial_live_pilot_plan(
    preview: LiveSheetsPreview,
    approval: InitialLiveSyncApproval,
) -> None:
    problems: list[str] = []
    actual_inserts = {
        category: plan.insert_count for category, plan in preview.workbook.plans.items()
    }
    if actual_inserts != dict(approval.opportunity_inserts):
        expected_inserts = dict(approval.opportunity_inserts)
        problems.append(f"opportunity inserts are {actual_inserts}, expected {expected_inserts}")
    if preview.watchlist_plan.insert_count != approval.watchlist_inserts:
        problems.append(
            f"watchlist inserts are {preview.watchlist_plan.insert_count}, "
            f"expected {approval.watchlist_inserts}"
        )
    all_plans = (*preview.workbook.plans.values(), preview.watchlist_plan)
    if any(plan.update_count or plan.unchanged_count for plan in all_plans):
        problems.append("initial plan contains updates or unchanged records")
    if any(plan.invalid_records or plan.conflicts for plan in all_plans):
        problems.append("initial plan contains invalid records or conflicts")
    if preview.workbook.failures:
        problems.append(f"pipeline synchronization failures: {preview.workbook.failures}")
    if preview.provenance.valid_count != approval.provenance_valid:
        problems.append(
            f"valid provenance count is {preview.provenance.valid_count}, "
            f"expected {approval.provenance_valid}"
        )
    if preview.provenance.blocked_count:
        problems.append(f"blocked provenance records: {preview.provenance.blocked_count}")
    if preview.recommendations.counts != dict(approval.recommendation_counts):
        problems.append(
            f"recommendation counts are {preview.recommendations.counts}, "
            f"expected {dict(approval.recommendation_counts)}"
        )

    execution_by_id = {
        processed.opportunity.opportunity_id: processed
        for report in preview.execution.pipelines.values()
        for processed in report.records
    }
    audit_by_id = {record.record_id: record for record in preview.provenance.records}
    decision_by_id = preview.recommendations.by_record_id
    planned_ids = [
        str(operation.row["Record_ID"])
        for plan in preview.workbook.plans.values()
        for operation in plan.inserts
    ]
    if len(planned_ids) != len(set(planned_ids)):
        problems.append("planned opportunity Record_ID values are not unique")
    for record_id in planned_ids:
        processed = execution_by_id.get(record_id)
        audit = audit_by_id.get(record_id)
        decision = decision_by_id.get(record_id)
        if processed is None or audit is None or decision is None:
            problems.append(
                f"planned Record_ID is not linked to the reviewed execution: {record_id}"
            )
            continue
        opportunity = processed.opportunity
        if opportunity.is_fictional:
            problems.append(f"planned record is synthetic: {record_id}")
        if opportunity.source_verification_status is not SourceVerificationStatus.VERIFIED_OFFICIAL:
            problems.append(f"planned record source is not verified official: {record_id}")
        if not audit.valid:
            problems.append(f"planned record provenance is blocked: {record_id}")
        if decision.classification not in {
            RecommendationClassification.HIGH_PRIORITY,
            RecommendationClassification.RELEVANT,
        }:
            problems.append(f"planned record recommendation is not approved: {record_id}")
    if problems:
        raise LiveDataError("approved initial plan validation failed: " + "; ".join(problems))


def load_live_execution(
    *,
    project_root: Path,
    live_data_dir: Path,
    reference_date: date,
    feedback_by_id: dict[str, UserFeedback] | None = None,
) -> tuple[ExecutionReport, dict[str, Any]]:
    """Rebuild processed models from cached extracted inputs without a new observation."""

    metadata = _read_object(live_data_dir / "source_metadata.json")
    source_by_url = _source_ids_by_url(metadata)
    reports: dict[str, PipelineReport] = {}
    for category in ("jobs", "phd", "events"):
        payload = _read_object(live_data_dir / f"{category}.json")
        raw_records, stored_by_id = _cached_records(payload, category, source_by_url)
        observed_at = max(
            (
                _stored_timestamp(item["opportunity"], "source_retrieved_at")
                for item in stored_by_id.values()
            ),
            default=datetime.now(UTC),
        )
        if category == "jobs":
            report = run_jobs_pipeline(
                raw_records,
                config_dir=project_root / "config",
                observed_at=observed_at,
                feedback_by_id=feedback_by_id,
            )
        elif category == "phd":
            report = run_phd_pipeline(
                raw_records,
                config_dir=project_root / "config",
                observed_at=observed_at,
                feedback_by_id=feedback_by_id,
            )
        else:
            report = run_events_pipeline(
                raw_records,
                config_dir=project_root / "config",
                observed_at=observed_at,
                reference_date=reference_date,
                feedback_by_id=feedback_by_id,
            )
        _restore_cached_identity_and_observation(report, stored_by_id)
        reports[category] = report
    return ExecutionReport(pipelines=reports), metadata


def audit_provenance(execution: ExecutionReport) -> ProvenanceReport:
    audits: list[ProvenanceRecord] = []
    for category, report in execution.pipelines.items():
        for processed in report.records:
            opportunity = processed.opportunity
            original = opportunity.original_values
            blocking: list[str] = []
            if not opportunity.opportunity_id:
                blocking.append("Record_ID is missing")
            if not opportunity.title.strip():
                blocking.append("title is missing")
            if not opportunity.organization.strip():
                blocking.append("organization is missing")
            if not _is_http_url(original.get("official_source_url")):
                blocking.append("official_source_url is missing or invalid")
            if opportunity.source_retrieved_at is None:
                blocking.append("source_retrieved_at is missing")
            elif opportunity.source_retrieved_at.tzinfo is None:
                blocking.append("source_retrieved_at must be timezone-aware")
            if (
                opportunity.source_verification_status
                is not SourceVerificationStatus.VERIFIED_OFFICIAL
            ):
                blocking.append("source_verification_status is not VERIFIED_OFFICIAL")
            if not opportunity.adapter_source_id:
                blocking.append("adapter_source_id is missing")
            if opportunity.is_fictional:
                blocking.append("fictional must be false")
            if original.get("_stored_record_id_mismatch"):
                blocking.append("stored Record_ID does not match deterministic identity")
            if not opportunity.source_evidence:
                blocking.append("source_evidence is missing")

            missing = _missing_important_fields(opportunity)
            if (
                isinstance(opportunity, AcademicEvent)
                and (opportunity.series_name or "").casefold() == "cosyne"
                and not all(
                    (
                        opportunity.overall_starts_on,
                        opportunity.overall_ends_on,
                        opportunity.main_meeting_starts_on,
                        opportunity.main_meeting_ends_on,
                        opportunity.workshop_starts_on,
                        opportunity.workshop_ends_on,
                    )
                )
            ):
                blocking.append("conference date segments are incomplete")
            audits.append(
                ProvenanceRecord(
                    record_id=opportunity.opportunity_id,
                    category=category,
                    valid=not blocking,
                    blocking_issues=tuple(blocking),
                    missing_important_fields=missing,
                    source_stated_facts=opportunity.source_evidence,
                    normalized_information=_normalized_information(opportunity),
                    rule_based_interpretations=_rule_based_interpretations(processed),
                )
            )
    return ProvenanceReport(records=tuple(audits))


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LiveDataError(f"required live data file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LiveDataError(f"live data file is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise LiveDataError(f"live data file must contain an object: {path}")
    return value


def build_combined_live_snapshot(
    *,
    existing_dir: Path,
    additions_dir: Path,
    output_dir: Path,
) -> Path:
    """Build a local-only preview snapshot without mutating either input directory."""

    if output_dir.resolve() in {existing_dir.resolve(), additions_dir.resolve()}:
        raise LiveDataError("combined preview output must be separate from both input snapshots")
    output_dir.mkdir(parents=True, exist_ok=True)
    for category in ("jobs", "phd", "events"):
        current = _read_object(existing_dir / f"{category}.json")
        addition_path = additions_dir / f"{category}.json"
        addition = _read_object(addition_path) if addition_path.exists() else {"records": []}
        current_records = current.get("records")
        addition_records = addition.get("records")
        if not isinstance(current_records, list) or not isinstance(addition_records, list):
            raise LiveDataError(f"{category} snapshot records must be lists")
        current_ids = {_stored_record_id(record, category) for record in current_records}
        addition_ids = [_stored_record_id(record, category) for record in addition_records]
        duplicates = current_ids & set(addition_ids)
        if duplicates or len(addition_ids) != len(set(addition_ids)):
            joined = ", ".join(sorted(duplicates or set(addition_ids)))
            raise LiveDataError(f"combined preview contains duplicate {category} IDs: {joined}")
        combined = deepcopy(current)
        combined["records"] = [*current_records, *addition_records]
        summary = combined.get("summary")
        if isinstance(summary, dict):
            summary["records_processed"] = len(combined["records"])
            summary["records_accepted"] = sum(
                not bool(record.get("excluded"))
                for record in combined["records"]
                if isinstance(record, dict)
            )
        (output_dir / f"{category}.json").write_text(
            json.dumps(combined, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    current_metadata = _read_object(existing_dir / "source_metadata.json")
    addition_metadata = _read_object(additions_dir / "source_metadata.json")
    current_sources = current_metadata.get("sources")
    addition_sources = addition_metadata.get("sources")
    if not isinstance(current_sources, dict) or not isinstance(addition_sources, dict):
        raise LiveDataError("source metadata must contain source mappings")
    overlap = set(current_sources) & set(addition_sources)
    if overlap:
        raise LiveDataError(
            "combined preview source IDs already exist: " + ", ".join(sorted(overlap))
        )
    metadata = deepcopy(current_metadata)
    metadata["sources"] = {**current_sources, **addition_sources}
    metadata["pipelines"] = {}
    (output_dir / "source_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_dir


def _stored_record_id(record: Any, category: str) -> str:
    if not isinstance(record, dict) or not isinstance(record.get("opportunity"), dict):
        raise LiveDataError(f"{category} snapshot contains a malformed record")
    record_id = record["opportunity"].get("opportunity_id")
    if not isinstance(record_id, str) or not record_id:
        raise LiveDataError(f"{category} snapshot contains a record without Record_ID")
    return record_id


def _source_ids_by_url(metadata: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    sources = metadata.get("sources", {})
    if not isinstance(sources, dict):
        return result
    for source_id, source in sources.items():
        if not isinstance(source_id, str) or not isinstance(source, dict):
            continue
        records = source.get("records", [])
        if not isinstance(records, list):
            continue
        for raw in records:
            if isinstance(raw, dict) and isinstance(raw.get("source_url"), str):
                result[raw["source_url"]] = source_id
    return result


def _cached_records(
    payload: dict[str, Any],
    category: str,
    source_by_url: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if payload.get("category") != category:
        raise LiveDataError(f"{category}.json category does not match its filename")
    records = payload.get("records")
    if not isinstance(records, list):
        raise LiveDataError(f"{category}.json records must be a list")
    raws: list[dict[str, Any]] = []
    stored: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(records):
        if not isinstance(item, dict) or not isinstance(item.get("opportunity"), dict):
            raise LiveDataError(f"{category}.json record[{index}] is malformed")
        opportunity = item["opportunity"]
        record_id = opportunity.get("opportunity_id")
        raw = opportunity.get("original_values")
        if not isinstance(record_id, str) or not isinstance(raw, dict):
            raise LiveDataError(f"{category}.json record[{index}] lacks identity or source data")
        if raw.get("fictional") is not False:
            raise LiveDataError(
                f"{category}.json contains fictional or unmarked record {record_id}"
            )
        raw = dict(raw)
        if not raw.get("adapter_source_id"):
            source_id = source_by_url.get(str(raw.get("source_url", "")))
            if source_id:
                raw["adapter_source_id"] = source_id
        raws.append(raw)
        stored[record_id] = item
    return raws, stored


def _restore_cached_identity_and_observation(
    report: PipelineReport,
    stored_by_id: dict[str, dict[str, Any]],
) -> None:
    for processed in report.records:
        opportunity = processed.opportunity
        stored = stored_by_id.get(opportunity.opportunity_id)
        if stored is None:
            continue
        values = stored["opportunity"]
        stored_id = str(values["opportunity_id"])
        if stored_id != opportunity.opportunity_id:
            opportunity.original_values["_stored_record_id_mismatch"] = True
            opportunity.opportunity_id = stored_id
        opportunity.first_seen_at = _stored_timestamp(values, "first_seen_at")
        opportunity.last_seen_at = _stored_timestamp(values, "last_seen_at")
        opportunity.content_updated_at = _stored_timestamp(values, "content_updated_at")
        opportunity.retrieved_at = _stored_timestamp(values, "retrieved_at")
        opportunity.source_retrieved_at = _stored_timestamp(values, "source_retrieved_at")
        source_urls = values.get("source_urls")
        if isinstance(source_urls, list) and all(isinstance(value, str) for value in source_urls):
            opportunity.source_urls = tuple(source_urls)


def _stored_timestamp(values: dict[str, Any], field_name: str) -> datetime:
    fallback = {
        "source_retrieved_at": "retrieved_at",
        "retrieved_at": "last_seen_at",
        "content_updated_at": "first_seen_at",
    }.get(field_name)
    value = values.get(field_name)
    if value is None and fallback:
        value = values.get(fallback)
    if not isinstance(value, str):
        raise LiveDataError(f"{field_name} is missing from cached live data")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LiveDataError(f"{field_name} is not an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise LiveDataError(f"{field_name} must be timezone-aware")
    return parsed


def _is_http_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _missing_important_fields(opportunity: Any) -> tuple[str, ...]:
    missing: list[str] = []
    if isinstance(opportunity, IndustryJob):
        if opportunity.location is None:
            missing.append("location")
        if opportunity.education_requirement is EducationRequirement.UNKNOWN:
            missing.append("education_requirement")
        if opportunity.english_compatibility is EnglishCompatibility.UNKNOWN:
            missing.append("working_language")
        if opportunity.compensation_disclosure_status is CompensationDisclosureStatus.NOT_DISCLOSED:
            missing.append("salary")
    elif isinstance(opportunity, PhDOpportunity):
        for field_name in ("target_cycle", "funding_status", "deadline", "admission_url"):
            if getattr(opportunity, field_name) is None:
                missing.append(field_name)
    elif isinstance(opportunity, AcademicEvent):
        if opportunity.registration_deadline is None:
            missing.append("general_registration_deadline")
    return tuple(missing)


def _normalized_information(opportunity: Any) -> tuple[str, ...]:
    values = [
        f"country={opportunity.country or 'unknown'}",
        f"research_areas={', '.join(opportunity.research_areas) or 'unknown'}",
    ]
    if isinstance(opportunity, AcademicEvent):
        values.append(
            f"overall_dates={opportunity.overall_starts_on or 'unknown'} to "
            f"{opportunity.overall_ends_on or 'unknown'}"
        )
    return tuple(values)


def _rule_based_interpretations(processed: ProcessedOpportunity) -> tuple[str, ...]:
    opportunity = processed.opportunity
    values = [
        f"classification={opportunity.classification.value}",
        f"priority_score={processed.score.final_score}",
        f"domain_fit={processed.score.domain_fit.value}",
        f"methodological_fit={processed.score.components['methodological_fit']}",
        f"research_question_fit={processed.score.components['research_question_fit']}",
    ]
    if isinstance(opportunity, IndustryJob):
        values.extend(
            (
                f"research_orientation={opportunity.research_orientation.value}",
                f"education_requirement={opportunity.education_requirement.value}",
            )
        )
    return tuple(values)


def classify_recommendations(
    execution: ExecutionReport,
    provenance: ProvenanceReport,
    rules: Mapping[str, Any],
) -> RecommendationReport:
    """Classify personal relevance without changing source verification state."""

    provenance_by_id = {record.record_id: record for record in provenance.records}
    thresholds = rules["score_thresholds"]
    signals = rules["title_signals"]
    decisions: list[RecommendationDecision] = []
    for category, report in execution.pipelines.items():
        for processed in report.records:
            opportunity = processed.opportunity
            audit = provenance_by_id[opportunity.opportunity_id]
            if not audit.valid:
                classification = RecommendationClassification.NEEDS_REVIEW
                explanation = "Required provenance is incomplete; hold for manual review."
            elif isinstance(opportunity, IndustryJob):
                classification, explanation = _classify_job_recommendation(
                    processed,
                    signals=signals,
                    thresholds=thresholds,
                )
            elif (
                processed.score.domain_fit is DomainFitClassification.CORE_DOMAIN_FIT
                and processed.score.final_score >= thresholds["high_priority"]
            ):
                classification = RecommendationClassification.HIGH_PRIORITY
                explanation = (
                    f"Deterministic category score {processed.score.final_score:.1f} meets the "
                    "configured high-priority threshold."
                )
            elif (
                processed.score.domain_fit
                in {
                    DomainFitClassification.CORE_DOMAIN_FIT,
                    DomainFitClassification.ADJACENT_DOMAIN_FIT,
                }
                and processed.score.final_score >= thresholds["relevant"]
            ):
                classification = RecommendationClassification.RELEVANT
                explanation = (
                    f"Deterministic category score {processed.score.final_score:.1f} meets the "
                    "configured relevance threshold."
                )
            elif processed.score.domain_fit is DomainFitClassification.LOW_DOMAIN_FIT:
                classification = RecommendationClassification.LOW_PRIORITY
                explanation = (
                    "Available evidence indicates low fit with the configured research domain."
                )
            else:
                classification = RecommendationClassification.NEEDS_REVIEW
                explanation = (
                    f"Domain fit is {processed.score.domain_fit.value}; retain for review without "
                    "treating technical fit as core research relevance."
                )
            decisions.append(
                RecommendationDecision(
                    record_id=opportunity.opportunity_id,
                    category=category,
                    classification=classification,
                    domain_fit=processed.score.domain_fit,
                    methodological_fit=processed.score.components["methodological_fit"],
                    research_question_fit=processed.score.components["research_question_fit"],
                    explanation=explanation,
                )
            )
    return RecommendationReport(decisions=tuple(decisions))


def _classify_job_recommendation(
    processed: ProcessedOpportunity,
    *,
    signals: Mapping[str, Any],
    thresholds: Mapping[str, Any],
) -> tuple[RecommendationClassification, str]:
    title = processed.opportunity.title.casefold()
    research_score = processed.score.components["research_relevance"]
    matched = {
        name: next((phrase for phrase in phrases if phrase.casefold() in title), None)
        for name, phrases in signals.items()
    }
    if matched["low_priority"]:
        phrase = matched["low_priority"]
        return (
            RecommendationClassification.LOW_PRIORITY,
            f"Title signal '{phrase}' indicates recruiting, legal, sales, or unrelated "
            "business work.",
        )
    domain_fit = processed.score.domain_fit
    if domain_fit is DomainFitClassification.LOW_DOMAIN_FIT:
        return (
            RecommendationClassification.LOW_PRIORITY,
            "Available evidence indicates low domain fit despite any transferable techniques.",
        )
    if matched["needs_review"] and not (matched["high_priority"] or matched["relevant"]):
        phrase = matched["needs_review"]
        return (
            RecommendationClassification.NEEDS_REVIEW,
            f"Title signal '{phrase}' is ambiguous for career fit and requires manual review, "
            "independently of research-domain scoring.",
        )
    if (
        domain_fit is DomainFitClassification.CORE_DOMAIN_FIT
        and research_score >= thresholds["high_priority"]
    ):
        phrase = matched["high_priority"]
        return (
            RecommendationClassification.HIGH_PRIORITY,
            f"Core domain evidence and research relevance {research_score:.1f} meet the "
            "high-priority rule" + (f"; title signal '{phrase}' is supportive." if phrase else "."),
        )
    if (
        domain_fit is DomainFitClassification.ADJACENT_DOMAIN_FIT
        and research_score >= thresholds["relevant"]
    ):
        phrase = matched["relevant"]
        return (
            RecommendationClassification.RELEVANT,
            f"Adjacent domain evidence and research relevance {research_score:.1f} meet the "
            "relevance rule" + (f"; title signal '{phrase}' is supportive." if phrase else "."),
        )
    if domain_fit is DomainFitClassification.TECHNICAL_TRANSFERABLE:
        phrase = matched["needs_review"] or matched["high_priority"] or matched["relevant"]
        detail = f" Title signal '{phrase}' is not sufficient domain evidence." if phrase else ""
        return (
            RecommendationClassification.NEEDS_REVIEW,
            "Technical research skills are transferable, but available evidence does not show a "
            f"cognition, brain, or behavior research question.{detail}",
        )
    return (
        RecommendationClassification.NEEDS_REVIEW,
        "Available evidence is insufficient to determine computational cognitive neuroscience "
        "relevance.",
    )


def _recommended_execution(
    execution: ExecutionReport,
    provenance: ProvenanceReport,
    recommendations: RecommendationReport,
) -> ExecutionReport:
    valid_ids = {record.record_id for record in provenance.records if record.valid}
    recommended_ids = {
        decision.record_id
        for decision in recommendations.decisions
        if decision.classification
        in {RecommendationClassification.HIGH_PRIORITY, RecommendationClassification.RELEVANT}
    }
    allowed_ids = valid_ids & recommended_ids
    reports: dict[str, PipelineReport] = {}
    for category, report in execution.pipelines.items():
        records = tuple(
            item for item in report.records if item.opportunity.opportunity_id in allowed_ids
        )
        reports[category] = replace(report, records=records, records_accepted=len(records))
    return ExecutionReport(pipelines=reports)


def _syncable_execution(
    execution: ExecutionReport,
    provenance: ProvenanceReport,
    recommendations: RecommendationReport,
    adapter: SheetsAdapter,
) -> ExecutionReport:
    """Separate new-record admission from non-destructive existing-row score refreshes."""

    valid_ids = {record.record_id for record in provenance.records if record.valid}
    recommended_ids = {
        decision.record_id
        for decision in recommendations.decisions
        if decision.classification
        in {RecommendationClassification.HIGH_PRIORITY, RecommendationClassification.RELEVANT}
    }
    sheet_by_category = {
        "jobs": "Industry_Jobs",
        "phd": "PhD_Opportunities",
        "events": "Events",
    }
    reports: dict[str, PipelineReport] = {}
    for category, report in execution.pipelines.items():
        worksheet = adapter.read_worksheet(sheet_by_category[category])
        existing_by_id = {
            str(row["Record_ID"]): row
            for row in worksheet.rows
            if isinstance(row.get("Record_ID"), str) and row["Record_ID"]
        }
        selected: list[ProcessedOpportunity] = []
        for item in report.records:
            record_id = item.opportunity.opportunity_id
            is_existing = record_id in existing_by_id
            may_insert = record_id in recommended_ids and not item.excluded
            if record_id not in valid_ids or not (is_existing or may_insert):
                continue
            copied = deepcopy(item)
            if is_existing:
                existing = existing_by_id[record_id]
                copied.opportunity.first_seen_at = _sheet_datetime(
                    existing.get("First_Seen"), copied.opportunity.first_seen_at
                )
                copied.opportunity.last_seen_at = _sheet_datetime(
                    existing.get("Last_Seen"), copied.opportunity.last_seen_at
                )
            selected.append(copied)
        reports[category] = replace(
            report,
            records=tuple(selected),
            records_accepted=sum(not item.excluded for item in selected),
        )
    return ExecutionReport(pipelines=reports)


def _sheet_datetime(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return fallback
    else:
        return fallback
    return parsed if parsed.tzinfo is not None else fallback


def _source_coverage(
    metadata: dict[str, Any],
    execution: ExecutionReport,
) -> dict[str, SourceCoverage]:
    accepted_by_source: dict[str, int] = {}
    for report in execution.pipelines.values():
        for processed in report.records:
            source_id = processed.opportunity.adapter_source_id
            if source_id:
                accepted_by_source[source_id] = accepted_by_source.get(source_id, 0) + 1
    result: dict[str, SourceCoverage] = {}
    sources = metadata.get("sources", {})
    if not isinstance(sources, dict):
        return result
    for source_id, source in sources.items():
        if not isinstance(source_id, str) or not isinstance(source, dict):
            continue
        records = source.get("records", [])
        extracted = len(records) if isinstance(records, list) else 0
        accepted = accepted_by_source.get(source_id, 0)
        result[source_id] = SourceCoverage(
            source_id=source_id,
            health=str(source.get("health", "UNKNOWN")),
            retrieved_at=(
                str(source["retrieved_at"]) if source.get("retrieved_at") is not None else None
            ),
            records_returned=int(source.get("records_fetched", 0)),
            records_matched=int(source.get("records_matched", 0)),
            records_considered=int(source.get("records_considered", extracted)),
            records_extracted=extracted,
            records_accepted=accepted,
        )
    return result


def _validate_existing_workbook(adapter: SheetsAdapter) -> None:
    validate_live_pilot_identity(adapter)
    initialize = getattr(adapter, "initialize_workbook", None)
    if initialize is None:
        return
    plan = initialize(apply=False)
    if plan.missing_sheets:
        raise LiveDataError("LIVE PILOT workbook is missing approved worksheets")
    if plan.incompatible_headers:
        raise LiveDataError("LIVE PILOT workbook has incompatible worksheet headers")


def _write_review_report(
    review_dir: Path,
    *,
    execution: ExecutionReport,
    provenance: ProvenanceReport,
    recommendations: RecommendationReport,
    workbook: WorkbookSyncReport,
    watchlist_plan: SheetSyncPlan,
    coverage: dict[str, SourceCoverage],
    generated_at: datetime,
    offline: bool,
    target_environment: TargetEnvironment,
) -> Path:
    review_dir.mkdir(parents=True, exist_ok=True)
    path = review_dir / "live_data_review.md"
    action_by_id = _planned_actions(workbook, provenance)
    audit_by_id = {record.record_id: record for record in provenance.records}
    decision_by_id = recommendations.by_record_id
    counts = recommendations.counts
    lines = [
        "# ResearchRadar Live Data Review",
        "",
        f"Generated: {generated_at.isoformat()}",
        f"Data mode: `{DataMode.LIVE.value}`",
        f"Target environment: `{target_environment.value}`",
        "Target: `"
        + ("offline simulated empty workbook" if offline else "configured LIVE PILOT workbook")
        + "`",
        "Sheet_Synced_At: `None` (dry-run; no writes)",
        f"Watchlist plan: insert={watchlist_plan.insert_count}, "
        f"update={watchlist_plan.update_count}, unchanged={watchlist_plan.unchanged_count}",
        "",
        "## Recommendation summary",
        "",
        f"- HIGH_PRIORITY: {counts[RecommendationClassification.HIGH_PRIORITY]}",
        f"- RELEVANT: {counts[RecommendationClassification.RELEVANT]}",
        f"- NEEDS_REVIEW: {counts[RecommendationClassification.NEEDS_REVIEW]}",
        f"- LOW_PRIORITY: {counts[RecommendationClassification.LOW_PRIORITY]}",
        "",
        "## Source coverage",
        "",
        "| Source | Returned | Considered | Extracted | Accepted |",
        "|---|---:|---:|---:|---:|",
    ]
    for source in coverage.values():
        lines.append(
            f"| {_md(source.source_id)} | {source.records_returned} | "
            f"{source.records_considered} | {source.records_extracted} | "
            f"{source.records_accepted} |"
        )
    groups = (
        (
            "## A. Recommended for synchronization",
            {
                RecommendationClassification.HIGH_PRIORITY,
                RecommendationClassification.RELEVANT,
            },
        ),
        ("## B. Needs manual review", {RecommendationClassification.NEEDS_REVIEW}),
        ("## C. Low-priority archive", {RecommendationClassification.LOW_PRIORITY}),
    )
    for heading, classifications in groups:
        lines.extend(
            [
                "",
                heading,
                "",
                "| Record_ID | Title | Organization | Category | Research | PhD | Career stage | "
                "Domain fit | Method | Question | Recommendation | Education | Salary | "
                "Official URL | Verification | Missing | "
                "Proposed action | Explanation |",
                "|---|---|---|---|---:|---:|---|---|---:|---:|---|---|---|---|---|---|---|---|",
            ]
        )
        for category, report in execution.pipelines.items():
            for processed in report.records:
                opportunity = processed.opportunity
                decision = decision_by_id[opportunity.opportunity_id]
                if decision.classification not in classifications:
                    continue
                audit = audit_by_id[opportunity.opportunity_id]
                research, phd = _review_scores(processed)
                education = (
                    opportunity.education_requirement.value
                    if isinstance(opportunity, IndustryJob)
                    else "—"
                )
                salary = (
                    opportunity.original_salary_text or "Not Disclosed"
                    if isinstance(opportunity, IndustryJob)
                    else "—"
                )
                missing = (*audit.blocking_issues, *audit.missing_important_fields)
                lines.append(
                    "| "
                    + " | ".join(
                        (
                            opportunity.opportunity_id,
                            _md(opportunity.title),
                            _md(opportunity.organization),
                            category,
                            research,
                            phd,
                            opportunity.classification.value,
                            decision.domain_fit.value,
                            f"{decision.methodological_fit:.1f}",
                            f"{decision.research_question_fit:.1f}",
                            decision.classification.value,
                            _md(education),
                            _md(salary),
                            _md(_opportunity_url(opportunity)),
                            opportunity.source_verification_status.value,
                            _md(", ".join(missing) or "None"),
                            _proposed_action(
                                action_by_id.get(opportunity.opportunity_id),
                                audit,
                                decision,
                            ),
                            _md(decision.explanation),
                        )
                    )
                    + " |"
                )
    lines.extend(["", "## Provenance details", ""])
    for category, report in execution.pipelines.items():
        for processed in report.records:
            opportunity = processed.opportunity
            audit = audit_by_id[opportunity.opportunity_id]
            decision = decision_by_id[opportunity.opportunity_id]
            lines.extend(
                [
                    f"### {_md(opportunity.title)} (`{opportunity.opportunity_id}`)",
                    "",
                    f"- Category: `{category}`",
                    f"- Adapter source: `{opportunity.adapter_source_id or 'missing'}`",
                    f"- Source retrieved: `{opportunity.source_retrieved_at}`",
                    f"- Recommendation: `{decision.classification.value}`",
                    f"- Recommendation explanation: {_md(decision.explanation)}",
                    f"- Source-stated facts: {_md('; '.join(audit.source_stated_facts) or 'None')}",
                    f"- Normalized information: {_md('; '.join(audit.normalized_information))}",
                    "- Rule-based interpretations: "
                    + _md("; ".join(audit.rule_based_interpretations)),
                    "- Unknown/review fields: "
                    + _md(", ".join(audit.missing_important_fields) or "None"),
                    "",
                ]
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _planned_actions(
    workbook: WorkbookSyncReport,
    provenance: ProvenanceReport,
) -> dict[str, str]:
    actions = {
        record.record_id: "BLOCKED_REVIEW" for record in provenance.records if not record.valid
    }
    for plan in workbook.plans.values():
        actions.update({operation.row["Record_ID"]: "INSERT" for operation in plan.inserts})
        actions.update({operation.record_id: "UPDATE" for operation in plan.updates})
        actions.update({record_id: "UNCHANGED" for record_id in plan.unchanged_record_ids})
    return actions


def _proposed_action(
    planned_action: str | None,
    audit: ProvenanceRecord,
    decision: RecommendationDecision,
) -> str:
    if not audit.valid:
        return "BLOCKED_PROVENANCE"
    if decision.classification is RecommendationClassification.NEEDS_REVIEW:
        return "HOLD_FOR_REVIEW"
    if decision.classification is RecommendationClassification.LOW_PRIORITY:
        return "LOCAL_ARCHIVE"
    return planned_action or "PLAN_CONFLICT"


def _opportunity_url(opportunity: Any) -> str:
    if isinstance(opportunity, PhDOpportunity):
        return opportunity.admission_url or opportunity.source_url
    if isinstance(opportunity, AcademicEvent):
        return opportunity.event_url or opportunity.source_url
    return opportunity.source_url


def _review_scores(processed: ProcessedOpportunity) -> tuple[str, str]:
    components = processed.score.components
    research = components.get("research_relevance", components.get("research_fit"))
    phd = components.get("phd_level_research_value")
    return (
        f"{research:.1f}" if isinstance(research, int | float) else "—",
        f"{phd:.1f}" if isinstance(phd, int | float) else "—",
    )


def _important_dates(opportunity: Any) -> str:
    if isinstance(opportunity, IndustryJob):
        return f"Deadline: {opportunity.deadline}" if opportunity.deadline else "None disclosed"
    if isinstance(opportunity, PhDOpportunity):
        return (
            f"Application: {opportunity.deadline or 'unknown'}; "
            f"cycle: {opportunity.target_cycle or 'unknown'}"
        )
    if isinstance(opportunity, AcademicEvent):
        return (
            f"Overall {opportunity.overall_starts_on}–{opportunity.overall_ends_on}; "
            f"main {opportunity.main_meeting_starts_on}–{opportunity.main_meeting_ends_on}; "
            f"workshops {opportunity.workshop_starts_on}–{opportunity.workshop_ends_on}; "
            f"abstract {opportunity.submission_deadline}; workshop proposal "
            f"{opportunity.workshop_submission_deadline}; presenter registration "
            f"{opportunity.presenter_registration_deadline}"
        )
    return "Unknown"


def _md(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
