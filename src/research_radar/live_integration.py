"""Safe review and dry-run planning for cached verified live opportunity data."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from research_radar.models import (
    AcademicEvent,
    CompensationDisclosureStatus,
    EducationRequirement,
    EnglishCompatibility,
    ExecutionReport,
    IndustryJob,
    PhDOpportunity,
    PipelineReport,
    ProcessedOpportunity,
    SourceVerificationStatus,
    UserFeedback,
)
from research_radar.pipelines import run_events_pipeline, run_jobs_pipeline, run_phd_pipeline
from research_radar.storage.sheets import (
    InMemorySheetsAdapter,
    SheetsAdapter,
    WorkbookSyncReport,
    load_feedback,
    sync_execution_report,
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


LIVE_PILOT_WORKBOOK_TITLE = "ResearchRadar AI — LIVE PILOT"


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
class SourceCoverage:
    source_id: str
    records_returned: int
    records_considered: int
    records_extracted: int
    records_accepted: int


@dataclass(frozen=True)
class LiveSheetsPreview:
    execution: ExecutionReport
    provenance: ProvenanceReport
    workbook: WorkbookSyncReport
    coverage: dict[str, SourceCoverage]
    review_report_path: Path
    offline: bool
    target_environment: TargetEnvironment
    sheet_synced_at: datetime | None = None


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
        raise LiveDataError("live production synchronization is not enabled in Milestone 4C.1")
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
    provenance = audit_provenance(execution)
    safe_execution = _without_blocked_records(execution, provenance)
    workbook = sync_execution_report(
        safe_execution,
        adapter,
        dry_run=True,
        run_id=f"live_preview_{generated_at.strftime('%Y%m%dT%H%M%SZ')}",
        timestamp=generated_at,
    )
    coverage = _source_coverage(metadata, execution)
    review_path = _write_review_report(
        review_dir,
        execution=execution,
        provenance=provenance,
        workbook=workbook,
        coverage=coverage,
        generated_at=generated_at,
        offline=offline,
        target_environment=environment,
    )
    return LiveSheetsPreview(
        execution=execution,
        provenance=provenance,
        workbook=workbook,
        coverage=coverage,
        review_report_path=review_path,
        offline=offline,
        target_environment=environment,
    )


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
            if isinstance(opportunity, AcademicEvent) and not all(
                (
                    opportunity.overall_starts_on,
                    opportunity.overall_ends_on,
                    opportunity.main_meeting_starts_on,
                    opportunity.main_meeting_ends_on,
                    opportunity.workshop_starts_on,
                    opportunity.workshop_ends_on,
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
    ]
    if isinstance(opportunity, IndustryJob):
        values.extend(
            (
                f"research_orientation={opportunity.research_orientation.value}",
                f"education_requirement={opportunity.education_requirement.value}",
            )
        )
    return tuple(values)


def _without_blocked_records(
    execution: ExecutionReport,
    provenance: ProvenanceReport,
) -> ExecutionReport:
    valid_ids = {record.record_id for record in provenance.records if record.valid}
    reports: dict[str, PipelineReport] = {}
    for category, report in execution.pipelines.items():
        records = tuple(
            item for item in report.records if item.opportunity.opportunity_id in valid_ids
        )
        reports[category] = replace(report, records=records, records_accepted=len(records))
    return ExecutionReport(pipelines=reports)


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
        result[source_id] = SourceCoverage(
            source_id=source_id,
            records_returned=int(source.get("records_fetched", 0)),
            records_considered=int(source.get("records_considered", extracted)),
            records_extracted=extracted,
            records_accepted=accepted_by_source.get(source_id, 0),
        )
    return result


def _validate_existing_workbook(adapter: SheetsAdapter) -> None:
    read_title = getattr(adapter, "get_spreadsheet_title", None)
    if read_title is not None and read_title() != LIVE_PILOT_WORKBOOK_TITLE:
        raise LiveDataError(
            f"configured workbook title must be exactly {LIVE_PILOT_WORKBOOK_TITLE!r}"
        )
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
    workbook: WorkbookSyncReport,
    coverage: dict[str, SourceCoverage],
    generated_at: datetime,
    offline: bool,
    target_environment: TargetEnvironment,
) -> Path:
    review_dir.mkdir(parents=True, exist_ok=True)
    path = review_dir / "live_data_review.md"
    action_by_id = _planned_actions(workbook, provenance)
    audit_by_id = {record.record_id: record for record in provenance.records}
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
    lines.extend(
        [
            "",
            "## Opportunity review",
            "",
            "| Title | Organization | Category | Research | PhD | Education | Salary | Dates | "
            "Official URL | Verification | Missing | Action |",
            "|---|---|---|---:|---:|---|---|---|---|---|---|---|",
        ]
    )
    for category, report in execution.pipelines.items():
        for processed in report.records:
            opportunity = processed.opportunity
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
            verification = opportunity.source_verification_status.value
            if audit.review_required:
                verification += " · REVIEW"
            missing = (*audit.blocking_issues, *audit.missing_important_fields)
            lines.append(
                "| "
                + " | ".join(
                    (
                        _md(opportunity.title),
                        _md(opportunity.organization),
                        category,
                        research,
                        phd,
                        _md(education),
                        _md(salary),
                        _md(_important_dates(opportunity)),
                        _md(_opportunity_url(opportunity)),
                        _md(verification),
                        _md(", ".join(missing) or "None"),
                        _review_action(
                            action_by_id.get(opportunity.opportunity_id, "BLOCKED_REVIEW"),
                            audit,
                        ),
                    )
                )
                + " |"
            )
    lines.extend(["", "## Provenance details", ""])
    for category, report in execution.pipelines.items():
        for processed in report.records:
            opportunity = processed.opportunity
            audit = audit_by_id[opportunity.opportunity_id]
            lines.extend(
                [
                    f"### {_md(opportunity.title)} (`{opportunity.opportunity_id}`)",
                    "",
                    f"- Category: `{category}`",
                    f"- Adapter source: `{opportunity.adapter_source_id or 'missing'}`",
                    f"- Source retrieved: `{opportunity.source_retrieved_at}`",
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


def _review_action(action: str, audit: ProvenanceRecord) -> str:
    if action == "BLOCKED_REVIEW":
        return action
    return f"{action} · REVIEW" if audit.review_required else action


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
