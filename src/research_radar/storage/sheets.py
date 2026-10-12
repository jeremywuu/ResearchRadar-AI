"""Offline Google Sheets synchronization planning and in-memory adapter."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from research_radar.identifiers import generate_stable_identifier
from research_radar.models import (
    AcademicEvent,
    ExecutionReport,
    IndustryJob,
    PhDOpportunity,
    PipelineStatus,
    PreferenceFeedback,
    UserFeedback,
    WatchlistTarget,
)


class SheetSchemaError(ValueError):
    """Raised when worksheet headers do not match the declared schema."""


class SheetsOperationError(RuntimeError):
    """Base error for adapter I/O failures at the Sheets seam."""


class SheetsAdapter(Protocol):
    """Seam implemented by the offline adapter now and Google API adapter later."""

    def read_worksheet(self, name: str) -> WorksheetData: ...

    def read_record_ids(self, name: str) -> dict[str, int]: ...

    def apply_plan(self, plan: SheetSyncPlan, *, dry_run: bool) -> None: ...

    def append_unique(self, sheet_name: str, rows: list[dict[str, Any]]) -> None: ...


@dataclass(frozen=True)
class SheetSchema:
    name: str
    headers: tuple[str, ...]
    record_id_header: str
    agent_managed_headers: tuple[str, ...]
    user_managed_headers: tuple[str, ...] = ()


def _agent_schema(name: str, headers: tuple[str, ...]) -> SheetSchema:
    return SheetSchema(
        name=name,
        headers=headers,
        record_id_header="Record_ID",
        agent_managed_headers=headers,
    )


INDUSTRY_JOBS_SCHEMA = _agent_schema(
    "Industry_Jobs",
    (
        "Record_ID",
        "Job_Title",
        "Company",
        "Location",
        "Country",
        "Research_Domain",
        "Research_Orientation",
        "Education_Requirement",
        "Career_Stage",
        "Working_Language",
        "Required_Skills",
        "Research_Relevance",
        "PhD_Leverage",
        "Skills_Career_Fit",
        "Compensation_Score",
        "Overall_Priority_Score",
        "Original_Salary",
        "Salary_Currency",
        "Salary_Disclosure_Status",
        "Source_URL",
        "First_Seen",
        "Last_Seen",
        "Opportunity_Status",
    ),
)

PHD_OPPORTUNITIES_SCHEMA = _agent_schema(
    "PhD_Opportunities",
    (
        "Record_ID",
        "University",
        "Program_or_Position",
        "Research_Area",
        "PI_Supervisor",
        "Country",
        "Admission_Cycle",
        "Recruitment_Status",
        "Funding_Status",
        "Application_Deadline",
        "Research_Fit_Score",
        "Official_URL",
        "First_Seen",
        "Last_Seen",
    ),
)

EVENTS_SCHEMA = _agent_schema(
    "Events",
    (
        "Record_ID",
        "Event_Name",
        "Event_Type",
        "Edition_Year",
        "Country",
        "City",
        "Start_Date",
        "End_Date",
        "Submission_Deadline",
        "Registration_Deadline",
        "Research_Relevance",
        "Priority_Score",
        "Official_URL",
        "First_Seen",
        "Last_Seen",
    ),
)

WATCHLIST_SCHEMA = _agent_schema(
    "Watchlist",
    (
        "Record_ID",
        "Organization",
        "Category",
        "Country_or_Region",
        "Priority",
        "Research_Focus",
        "Official_Website",
        "Monitoring_URL",
        "Source_Type",
        "Monitoring_Status",
        "Adapter_Status",
    ),
)

MY_FEEDBACK_SCHEMA = SheetSchema(
    name="My_Feedback",
    headers=("Record_ID", "Preference", "Saved", "Hidden", "Personal_Notes", "Updated_At"),
    record_id_header="Record_ID",
    agent_managed_headers=("Record_ID",),
    user_managed_headers=("Preference", "Saved", "Hidden", "Personal_Notes", "Updated_At"),
)

RUN_LOGS_SCHEMA = _agent_schema(
    "Run_Logs",
    (
        "Record_ID",
        "Run_ID",
        "Timestamp",
        "Pipeline_Category",
        "Execution_Status",
        "Processed_Count",
        "Inserted_Count",
        "Updated_Count",
        "Unchanged_Count",
        "Error_Count",
        "Error_Summary",
    ),
)

CHANGE_LOG_SCHEMA = _agent_schema(
    "Change_Log",
    (
        "Record_ID",
        "Event_ID",
        "Run_ID",
        "Timestamp",
        "Pipeline_Category",
        "Opportunity_Record_ID",
        "Change_Type",
        "Field_Name",
        "Previous_Value",
        "New_Value",
    ),
)

SHEET_SCHEMAS = {
    schema.name: schema
    for schema in (
        INDUSTRY_JOBS_SCHEMA,
        PHD_OPPORTUNITIES_SCHEMA,
        EVENTS_SCHEMA,
        WATCHLIST_SCHEMA,
        MY_FEEDBACK_SCHEMA,
        RUN_LOGS_SCHEMA,
        CHANGE_LOG_SCHEMA,
    )
}


@dataclass
class WorksheetData:
    headers: tuple[str, ...]
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class InsertOperation:
    row: dict[str, Any]
    value_input_option: str = "RAW"


@dataclass(frozen=True)
class UpdateOperation:
    row_number: int
    record_id: str
    changed_fields: dict[str, Any]
    expected_values: dict[str, Any]
    value_input_option: str = "RAW"


@dataclass(frozen=True)
class SyncIssue:
    record_id: str | None
    message: str


@dataclass
class SheetSyncPlan:
    sheet_name: str
    inserts: list[InsertOperation] = field(default_factory=list)
    updates: list[UpdateOperation] = field(default_factory=list)
    unchanged_record_ids: list[str] = field(default_factory=list)
    invalid_records: list[SyncIssue] = field(default_factory=list)
    conflicts: list[SyncIssue] = field(default_factory=list)
    change_log_rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def insert_count(self) -> int:
        return len(self.inserts)

    @property
    def update_count(self) -> int:
        return len(self.updates)

    @property
    def unchanged_count(self) -> int:
        return len(self.unchanged_record_ids)

    @property
    def invalid_count(self) -> int:
        return len(self.invalid_records)

    @property
    def conflict_count(self) -> int:
        return len(self.conflicts)

    @property
    def estimated_api_operations(self) -> int:
        return int(bool(self.inserts)) + int(bool(self.updates))


@dataclass
class FeedbackLoadResult:
    feedback_by_id: dict[str, UserFeedback] = field(default_factory=dict)
    invalid_records: list[SyncIssue] = field(default_factory=list)
    conflicts: list[SyncIssue] = field(default_factory=list)


@dataclass
class WorkbookSyncReport:
    plans: dict[str, SheetSyncPlan] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)
    dry_run: bool = True


def _validate_headers(schema: SheetSchema, worksheet: WorksheetData) -> None:
    if worksheet.headers != schema.headers:
        raise SheetSchemaError(
            f"{schema.name} headers do not match the expected schema; refusing to plan writes"
        )


def _event_row(
    *,
    run_id: str,
    timestamp: datetime,
    category: str,
    record_id: str,
    change_type: str,
    field_name: str,
    previous_value: Any,
    new_value: Any,
) -> dict[str, Any]:
    event_id = generate_stable_identifier(
        "change",
        category,
        record_id,
        change_type,
        field_name,
        str(previous_value),
        str(new_value),
    )
    return {
        "Record_ID": event_id,
        "Event_ID": event_id,
        "Run_ID": run_id,
        "Timestamp": timestamp.isoformat(),
        "Pipeline_Category": category,
        "Opportunity_Record_ID": record_id,
        "Change_Type": change_type,
        "Field_Name": field_name,
        "Previous_Value": previous_value,
        "New_Value": new_value,
    }


def plan_sheet_sync(
    schema: SheetSchema,
    desired_rows: list[dict[str, Any]],
    worksheet: WorksheetData,
    *,
    run_id: str,
    timestamp: datetime,
    include_change_log: bool = True,
) -> SheetSyncPlan:
    """Build an idempotent, row-position-independent synchronization plan."""

    _validate_headers(schema, worksheet)
    plan = SheetSyncPlan(sheet_name=schema.name)
    existing_by_id: dict[str, tuple[int, dict[str, Any]]] = {}
    for row_number, row in enumerate(worksheet.rows, start=2):
        record_id = row.get(schema.record_id_header)
        if not isinstance(record_id, str) or not record_id.strip():
            plan.conflicts.append(SyncIssue(None, f"row {row_number} has no Record_ID"))
            continue
        if record_id in existing_by_id:
            plan.conflicts.append(SyncIssue(record_id, "duplicate Record_ID in worksheet"))
            continue
        existing_by_id[record_id] = (row_number, row)

    desired_ids: set[str] = set()
    for row in desired_rows:
        record_id = row.get(schema.record_id_header)
        if set(row) != set(schema.headers):
            plan.invalid_records.append(
                SyncIssue(
                    str(record_id) if record_id else None, "record fields do not match schema"
                )
            )
            continue
        if not isinstance(record_id, str) or not record_id.strip():
            plan.invalid_records.append(SyncIssue(None, "Record_ID is required"))
            continue
        if record_id in desired_ids:
            plan.conflicts.append(SyncIssue(record_id, "duplicate Record_ID in desired records"))
            continue
        desired_ids.add(record_id)
        existing_entry = existing_by_id.get(record_id)
        if existing_entry is None:
            plan.inserts.append(InsertOperation(deepcopy(row)))
            if include_change_log:
                plan.change_log_rows.append(
                    _event_row(
                        run_id=run_id,
                        timestamp=timestamp,
                        category=schema.name,
                        record_id=record_id,
                        change_type="NEW_OPPORTUNITY",
                        field_name="",
                        previous_value="",
                        new_value="",
                    )
                )
            continue

        row_number, existing = existing_entry
        changed: dict[str, Any] = {}
        for header in schema.agent_managed_headers:
            if header == "First_Seen":
                continue
            if row[header] != existing.get(header, ""):
                changed[header] = row[header]
        if not changed:
            plan.unchanged_record_ids.append(record_id)
            continue
        expected_values = {header: existing.get(header, "") for header in changed}
        plan.updates.append(UpdateOperation(row_number, record_id, changed, expected_values))
        for header, value in changed.items():
            if header == "Last_Seen":
                continue
            change_type = "UPDATED_OPPORTUNITY"
            if header in {
                "Opportunity_Status",
                "Recruitment_Status",
                "Application_Deadline",
                "Submission_Deadline",
                "Registration_Deadline",
                "Original_Salary",
                "Salary_Currency",
                "Salary_Disclosure_Status",
            }:
                change_type = (
                    "STATUS_CHANGE"
                    if header in {"Opportunity_Status", "Recruitment_Status"}
                    else "DEADLINE_CHANGE"
                    if "Deadline" in header
                    else "SALARY_CHANGE"
                )
            if include_change_log:
                plan.change_log_rows.append(
                    _event_row(
                        run_id=run_id,
                        timestamp=timestamp,
                        category=schema.name,
                        record_id=record_id,
                        change_type=change_type,
                        field_name=header,
                        previous_value=existing.get(header, ""),
                        new_value=value,
                    )
                )
    return plan


class InMemorySheetsAdapter:
    """Offline adapter with Google-Sheets-like row and RAW-write semantics."""

    def __init__(
        self,
        rows_by_sheet: dict[str, list[dict[str, Any]]] | None = None,
        *,
        schemas: dict[str, SheetSchema] | None = None,
        headers_by_sheet: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.schemas = schemas or SHEET_SCHEMAS
        self._worksheets: dict[str, WorksheetData] = {}
        rows_by_sheet = rows_by_sheet or {}
        headers_by_sheet = headers_by_sheet or {}
        for name, schema in self.schemas.items():
            self._worksheets[name] = WorksheetData(
                headers=headers_by_sheet.get(name, schema.headers),
                rows=deepcopy(rows_by_sheet.get(name, [])),
            )
        self.write_operations: list[tuple[str, str, str]] = []

    def read_worksheet(self, name: str) -> WorksheetData:
        return deepcopy(self._worksheets[name])

    def read_record_ids(self, name: str) -> dict[str, int]:
        worksheet = self.read_worksheet(name)
        schema = self.schemas[name]
        result: dict[str, int] = {}
        for row_number, row in enumerate(worksheet.rows, start=2):
            record_id = row.get(schema.record_id_header)
            if isinstance(record_id, str) and record_id:
                if record_id in result:
                    raise SheetsOperationError(f"duplicate Record_ID in {name}: {record_id}")
                result[record_id] = row_number
        return result

    def apply_plan(self, plan: SheetSyncPlan, *, dry_run: bool) -> None:
        if dry_run or plan.conflicts:
            return
        worksheet = self._worksheets[plan.sheet_name]
        if plan.inserts:
            schema = self.schemas[plan.sheet_name]
            existing_ids = {row.get(schema.record_id_header) for row in worksheet.rows}
            additions = [
                deepcopy(operation.row)
                for operation in plan.inserts
                if operation.row.get(schema.record_id_header) not in existing_ids
            ]
            if additions:
                worksheet.rows.extend(additions)
                self.write_operations.append((plan.sheet_name, "batch_insert", "RAW"))
        if plan.updates:
            schema = self.schemas[plan.sheet_name]
            for operation in plan.updates:
                row = worksheet.rows[operation.row_number - 2]
                if row.get(schema.record_id_header) != operation.record_id or any(
                    row.get(header, "") != expected
                    for header, expected in operation.expected_values.items()
                ):
                    raise SheetsOperationError(
                        f"{plan.sheet_name} changed after planning; update refused"
                    )
                row.update(deepcopy(operation.changed_fields))
            self.write_operations.append((plan.sheet_name, "batch_update", "RAW"))
        self.append_unique("Change_Log", plan.change_log_rows)

    def append_unique(self, sheet_name: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        worksheet = self._worksheets[sheet_name]
        schema = self.schemas[sheet_name]
        existing = {row.get(schema.record_id_header) for row in worksheet.rows}
        additions = [row for row in rows if row.get(schema.record_id_header) not in existing]
        if additions:
            worksheet.rows.extend(deepcopy(additions))
            self.write_operations.append((sheet_name, "batch_append", "RAW"))


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return value.value.replace("_", " ").title().replace("Phd", "PhD")
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        return " | ".join(str(_cell(item)) for item in value)
    return value


def sheet_rows_from_report(report: Any) -> tuple[SheetSchema, list[dict[str, Any]]]:
    """Map a pipeline report to its compact, user-facing worksheet schema."""

    schema_by_category = {
        "jobs": INDUSTRY_JOBS_SCHEMA,
        "phd": PHD_OPPORTUNITIES_SCHEMA,
        "events": EVENTS_SCHEMA,
    }
    try:
        schema = schema_by_category[report.category]
    except KeyError as exc:
        raise ValueError(f"unsupported pipeline category: {report.category}") from exc
    rows: list[dict[str, Any]] = []
    for processed in report.records:
        opportunity = processed.opportunity
        if isinstance(opportunity, IndustryJob):
            rows.append(
                {
                    "Record_ID": opportunity.opportunity_id,
                    "Job_Title": opportunity.title,
                    "Company": opportunity.organization,
                    "Location": _cell(opportunity.location),
                    "Country": _cell(opportunity.country),
                    "Research_Domain": _cell(opportunity.research_areas),
                    "Research_Orientation": _cell(opportunity.research_orientation),
                    "Education_Requirement": _cell(opportunity.education_requirement),
                    "Career_Stage": _cell(opportunity.classification),
                    "Working_Language": _cell(opportunity.working_language),
                    "Required_Skills": _cell(opportunity.skills),
                    "Research_Relevance": processed.score.components["research_relevance"],
                    "PhD_Leverage": processed.score.components["phd_level_research_value"],
                    "Skills_Career_Fit": processed.score.components["skills_and_career_fit"],
                    "Compensation_Score": processed.score.components["compensation"],
                    "Overall_Priority_Score": processed.score.final_score,
                    "Original_Salary": _cell(opportunity.original_salary_text),
                    "Salary_Currency": _cell(opportunity.currency),
                    "Salary_Disclosure_Status": _cell(opportunity.compensation_disclosure_status),
                    "Source_URL": opportunity.source_url,
                    "First_Seen": opportunity.first_seen_at.isoformat(),
                    "Last_Seen": opportunity.last_seen_at.isoformat(),
                    "Opportunity_Status": _cell(opportunity.opportunity_status),
                }
            )
        elif isinstance(opportunity, PhDOpportunity):
            rows.append(
                {
                    "Record_ID": opportunity.opportunity_id,
                    "University": opportunity.organization,
                    "Program_or_Position": opportunity.title,
                    "Research_Area": _cell(opportunity.research_areas),
                    "PI_Supervisor": _cell(opportunity.supervisor),
                    "Country": _cell(opportunity.country),
                    "Admission_Cycle": _cell(opportunity.target_cycle),
                    "Recruitment_Status": _cell(opportunity.opportunity_status),
                    "Funding_Status": _cell(opportunity.funding_status),
                    "Application_Deadline": _cell(opportunity.deadline),
                    "Research_Fit_Score": processed.score.components["research_fit"],
                    "Official_URL": opportunity.admission_url or opportunity.source_url,
                    "First_Seen": opportunity.first_seen_at.isoformat(),
                    "Last_Seen": opportunity.last_seen_at.isoformat(),
                }
            )
        elif isinstance(opportunity, AcademicEvent):
            rows.append(
                {
                    "Record_ID": opportunity.opportunity_id,
                    "Event_Name": opportunity.title,
                    "Event_Type": _cell(opportunity.academic_event_type),
                    "Edition_Year": _cell(opportunity.edition_year),
                    "Country": _cell(opportunity.country),
                    "City": _cell(opportunity.location),
                    "Start_Date": _cell(opportunity.starts_on),
                    "End_Date": _cell(opportunity.ends_on),
                    "Submission_Deadline": _cell(opportunity.submission_deadline),
                    "Registration_Deadline": _cell(opportunity.registration_deadline),
                    "Research_Relevance": processed.score.components["research_fit"],
                    "Priority_Score": processed.score.final_score,
                    "Official_URL": opportunity.event_url or opportunity.source_url,
                    "First_Seen": opportunity.first_seen_at.isoformat(),
                    "Last_Seen": opportunity.last_seen_at.isoformat(),
                }
            )
        else:
            raise ValueError(f"unsupported opportunity type: {type(opportunity).__name__}")
    return schema, rows


def watchlist_rows(targets: list[WatchlistTarget]) -> list[dict[str, Any]]:
    """Create the read-only worksheet mirror of YAML-owned watchlist records."""

    return [
        {
            "Record_ID": target.target_id,
            "Organization": target.name,
            "Category": target.category.value,
            "Country_or_Region": target.country_or_region,
            "Priority": target.priority.value,
            "Research_Focus": target.research_focus,
            "Official_Website": target.official_website,
            "Monitoring_URL": target.monitoring_url,
            "Source_Type": target.source_type,
            "Monitoring_Status": target.monitoring_status.value,
            "Adapter_Status": target.adapter_status.value,
        }
        for target in targets
    ]


def _feedback_preference(value: Any) -> PreferenceFeedback | None:
    if value in (None, "", "None"):
        return None
    mapping = {
        "Very Interested": PreferenceFeedback.VERY_INTERESTED,
        "Interested": PreferenceFeedback.INTERESTED,
        "Not Relevant": PreferenceFeedback.NOT_RELEVANT,
        "VERY_INTERESTED": PreferenceFeedback.VERY_INTERESTED,
        "INTERESTED": PreferenceFeedback.INTERESTED,
        "NOT_RELEVANT": PreferenceFeedback.NOT_RELEVANT,
    }
    if value not in mapping:
        raise ValueError("Preference must be Very Interested, Interested, Not Relevant, or None")
    return mapping[value]


def _feedback_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.casefold() in {"true", "false"}:
        return value.casefold() == "true"
    raise ValueError(f"{field_name} must be true or false")


def is_blank_feedback_template_row(row: dict[str, Any]) -> bool:
    """Return true for a preformatted feedback row containing only default values."""

    empty_text = (None, "")
    false_checkbox_values = (None, "", False, "FALSE", "false")
    return (
        row.get("Record_ID") in empty_text
        and row.get("Preference") in (*empty_text, "None")
        and row.get("Saved") in false_checkbox_values
        and row.get("Hidden") in false_checkbox_values
        and row.get("Personal_Notes") in empty_text
        and row.get("Updated_At") in empty_text
    )


def load_feedback(adapter: SheetsAdapter) -> FeedbackLoadResult:
    """Load canonical user-managed feedback without mutating the worksheet."""

    worksheet = adapter.read_worksheet("My_Feedback")
    _validate_headers(MY_FEEDBACK_SCHEMA, worksheet)
    result = FeedbackLoadResult()
    seen: set[str] = set()
    for row_number, row in enumerate(worksheet.rows, start=2):
        if is_blank_feedback_template_row(row):
            continue
        record_id = row.get("Record_ID")
        if not isinstance(record_id, str) or not record_id.strip():
            result.invalid_records.append(
                SyncIssue(None, f"row {row_number}: Record_ID is required")
            )
            continue
        if record_id in seen:
            result.conflicts.append(SyncIssue(record_id, "duplicate Record_ID in My_Feedback"))
            result.feedback_by_id.pop(record_id, None)
            continue
        seen.add(record_id)
        try:
            updated_at = datetime.fromisoformat(str(row.get("Updated_At", "")))
            if updated_at.tzinfo is None:
                raise ValueError("Updated_At must include a timezone")
            result.feedback_by_id[record_id] = UserFeedback(
                opportunity_id=record_id,
                preference=_feedback_preference(row.get("Preference")),
                saved=_feedback_bool(row.get("Saved"), "Saved"),
                hidden=_feedback_bool(row.get("Hidden"), "Hidden"),
                notes=str(row["Personal_Notes"]) if row.get("Personal_Notes") else None,
                updated_at=updated_at,
            )
        except (TypeError, ValueError) as exc:
            result.invalid_records.append(SyncIssue(record_id, f"row {row_number}: {exc}"))
    return result


def _run_log_row(
    run_id: str,
    timestamp: datetime,
    category: str,
    status: str,
    processed: int,
    plan: SheetSyncPlan | None,
    error: str | None,
    *,
    fetched: int | None = None,
    accepted: int = 0,
    rejected_errors: tuple[str, ...] = (),
    excluded: int = 0,
    extraction_errors: tuple[str, ...] = (),
    pipeline_errors: tuple[str, ...] = (),
) -> dict[str, Any]:
    record_id = generate_stable_identifier("runlog", run_id, category)
    plan_errors = [issue.message for issue in (plan.invalid_records if plan else [])]
    plan_errors.extend(issue.message for issue in (plan.conflicts if plan else []))
    synchronization_error_count = (plan.invalid_count + plan.conflict_count) if plan else 0
    if error:
        synchronization_error_count += 1
    error_count = (
        len(rejected_errors)
        + len(extraction_errors)
        + len(pipeline_errors)
        + synchronization_error_count
    )
    summary_parts = [
        f"fetched={fetched if fetched is not None else processed}",
        f"accepted={accepted}",
        f"rejected={len(rejected_errors)}",
        f"excluded={excluded}",
        f"source_extraction_errors={len(extraction_errors)}",
        f"pipeline_errors={len(pipeline_errors)}",
        f"synchronization_errors={synchronization_error_count}",
    ]
    details = [*rejected_errors, *extraction_errors, *pipeline_errors, *plan_errors]
    if error:
        details.append(error)
    return {
        "Record_ID": record_id,
        "Run_ID": run_id,
        "Timestamp": timestamp.isoformat(),
        "Pipeline_Category": category,
        "Execution_Status": status,
        "Processed_Count": processed,
        "Inserted_Count": plan.insert_count if plan else 0,
        "Updated_Count": plan.update_count if plan else 0,
        "Unchanged_Count": plan.unchanged_count if plan else 0,
        "Error_Count": error_count,
        "Error_Summary": "; ".join(summary_parts + details),
    }


def sync_execution_report(
    execution: ExecutionReport,
    adapter: SheetsAdapter,
    *,
    dry_run: bool,
    run_id: str,
    timestamp: datetime,
) -> WorkbookSyncReport:
    """Plan or apply all successful categories while isolating category failures."""

    result = WorkbookSyncReport(dry_run=dry_run)
    run_logs: list[dict[str, Any]] = []
    for category, pipeline_report in execution.pipelines.items():
        plan: SheetSyncPlan | None = None
        pipeline_failure = (
            pipeline_report.failure if pipeline_report.status is PipelineStatus.FAILED else None
        )
        synchronization_failure: str | None = None
        if pipeline_failure:
            result.failures[category] = pipeline_failure
        else:
            try:
                schema, rows = sheet_rows_from_report(pipeline_report)
                plan = plan_sheet_sync(
                    schema,
                    rows,
                    adapter.read_worksheet(schema.name),
                    run_id=run_id,
                    timestamp=timestamp,
                )
                result.plans[category] = plan
                adapter.apply_plan(plan, dry_run=dry_run)
            except (KeyError, SheetSchemaError, SheetsOperationError, ValueError) as exc:
                synchronization_failure = str(exc)
                result.failures[category] = synchronization_failure
        pipeline_errors = pipeline_report.pipeline_processing_errors
        if pipeline_failure and pipeline_failure not in pipeline_errors:
            pipeline_errors = (*pipeline_errors, pipeline_failure)
        run_logs.append(
            _run_log_row(
                run_id,
                timestamp,
                category,
                (
                    "PARTIAL"
                    if synchronization_failure is None
                    and plan
                    and (plan.invalid_records or plan.conflicts)
                    else pipeline_report.status.value
                    if synchronization_failure is None
                    else "FAILED"
                ),
                pipeline_report.records_processed,
                plan,
                synchronization_failure,
                fetched=pipeline_report.records_fetched,
                accepted=pipeline_report.records_accepted,
                rejected_errors=pipeline_report.validation_errors,
                excluded=pipeline_report.records_excluded,
                extraction_errors=pipeline_report.source_extraction_errors,
                pipeline_errors=pipeline_errors,
            )
        )
    if not dry_run:
        adapter.append_unique("Run_Logs", run_logs)
    return result


def build_success_run_log_rows(
    execution: ExecutionReport,
    plans: dict[str, SheetSyncPlan],
    *,
    run_id: str,
    timestamp: datetime,
) -> list[dict[str, Any]]:
    """Build success logs for already approved, preplanned category writes."""

    rows: list[dict[str, Any]] = []
    for category, pipeline_report in execution.pipelines.items():
        plan = plans.get(category)
        if plan is None or plan.invalid_records or plan.conflicts:
            raise SheetsOperationError(
                f"{category} has no safe approved plan for run-log generation"
            )
        rows.append(
            _run_log_row(
                run_id,
                timestamp,
                category,
                pipeline_report.status.value,
                pipeline_report.records_processed,
                plan,
                None,
                fetched=pipeline_report.records_fetched,
                accepted=pipeline_report.records_accepted,
                rejected_errors=pipeline_report.validation_errors,
                excluded=pipeline_report.records_excluded,
                extraction_errors=pipeline_report.source_extraction_errors,
                pipeline_errors=pipeline_report.pipeline_processing_errors,
            )
        )
    return rows
