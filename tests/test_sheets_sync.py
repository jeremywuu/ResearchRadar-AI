from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research_radar.config import load_watchlist
from research_radar.models import (
    ExecutionReport,
    PipelineReport,
    PipelineStatus,
    PreferenceFeedback,
)
from research_radar.pipelines import run_jobs_pipeline, run_phd_pipeline
from research_radar.storage.sheets import (
    CHANGE_LOG_SCHEMA,
    INDUSTRY_JOBS_SCHEMA,
    MY_FEEDBACK_SCHEMA,
    PHD_OPPORTUNITIES_SCHEMA,
    WATCHLIST_SCHEMA,
    InMemorySheetsAdapter,
    SheetSchemaError,
    WorksheetData,
    load_feedback,
    plan_sheet_sync,
    sync_execution_report,
    watchlist_rows,
)

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def job_row(record_id: str, *, title: str = "AI Research Scientist") -> dict[str, object]:
    return {header: "" for header in INDUSTRY_JOBS_SCHEMA.headers} | {
        "Record_ID": record_id,
        "Job_Title": title,
        "Company": "Fictional AI Lab",
        "First_Seen": "2026-10-01T09:00:00+00:00",
        "Last_Seen": "2026-10-19T09:00:00+00:00",
        "Source_URL": "https://jobs.fictional-ai.example/role",
    }


def test_plan_separates_inserts_updates_and_unchanged_without_writing() -> None:
    unchanged = job_row("job_unchanged")
    existing_update = job_row("job_update", title="Old title")
    desired_update = job_row("job_update", title="New title")
    desired_insert = job_row("job_new")
    adapter = InMemorySheetsAdapter(
        {"Industry_Jobs": [unchanged, existing_update]},
        schemas={"Industry_Jobs": INDUSTRY_JOBS_SCHEMA},
    )
    before = deepcopy(adapter.read_worksheet("Industry_Jobs"))

    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        [unchanged, desired_update, desired_insert],
        adapter.read_worksheet("Industry_Jobs"),
        run_id="run_demo",
        timestamp=NOW,
    )

    assert plan.insert_count == 1
    assert plan.update_count == 1
    assert plan.unchanged_count == 1
    assert plan.invalid_count == 0
    assert plan.conflict_count == 0
    assert plan.estimated_api_operations == 2
    assert plan.updates[0].changed_fields == {"Job_Title": "New title"}
    assert adapter.read_worksheet("Industry_Jobs") == before
    assert not adapter.write_operations


def test_apply_is_idempotent_and_change_log_is_retry_safe() -> None:
    adapter = InMemorySheetsAdapter()
    desired = [job_row("job_new")]
    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        desired,
        adapter.read_worksheet("Industry_Jobs"),
        run_id="run_one",
        timestamp=NOW,
    )
    adapter.apply_plan(plan, dry_run=False)
    adapter.apply_plan(plan, dry_run=False)

    assert len(adapter.read_worksheet("Industry_Jobs").rows) == 1
    assert len(adapter.read_worksheet("Change_Log").rows) == 1

    repeated = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        desired,
        adapter.read_worksheet("Industry_Jobs"),
        run_id="run_two",
        timestamp=NOW,
    )
    assert repeated.insert_count == 0
    assert repeated.update_count == 0
    assert repeated.unchanged_count == 1


def test_manual_sorting_is_handled_by_rebuilding_record_id_row_map() -> None:
    sorted_rows = [job_row("job_b", title="Old B"), job_row("job_a", title="A")]
    adapter = InMemorySheetsAdapter({"Industry_Jobs": sorted_rows})
    desired = [job_row("job_a", title="A"), job_row("job_b", title="New B")]

    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        desired,
        adapter.read_worksheet("Industry_Jobs"),
        run_id="run_sort",
        timestamp=NOW,
    )

    assert plan.updates[0].record_id == "job_b"
    assert plan.updates[0].row_number == 2


def test_targeted_update_preserves_first_seen_and_skips_unchanged_rows() -> None:
    existing = job_row("job_update", title="Old title")
    desired = job_row("job_update", title="New title")
    desired["First_Seen"] = "2026-10-19T09:00:00+00:00"
    adapter = InMemorySheetsAdapter({"Industry_Jobs": [existing]})
    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        [desired],
        adapter.read_worksheet("Industry_Jobs"),
        run_id="run_update",
        timestamp=NOW,
    )
    adapter.apply_plan(plan, dry_run=False)
    updated = adapter.read_worksheet("Industry_Jobs").rows[0]

    assert updated["Job_Title"] == "New title"
    assert updated["First_Seen"] == "2026-10-01T09:00:00+00:00"
    assert plan.updates[0].changed_fields == {"Job_Title": "New title"}
    assert adapter.write_operations[0] == ("Industry_Jobs", "batch_update", "RAW")

    repeated = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        [updated],
        adapter.read_worksheet("Industry_Jobs"),
        run_id="run_update_two",
        timestamp=NOW,
    )
    writes_before = list(adapter.write_operations)
    adapter.apply_plan(repeated, dry_run=False)
    assert repeated.unchanged_count == 1
    assert adapter.write_operations == writes_before


def test_duplicate_ids_and_invalid_records_are_reported_safely() -> None:
    duplicate_sheet = WorksheetData(
        headers=INDUSTRY_JOBS_SCHEMA.headers,
        rows=[job_row("job_dup"), job_row("job_dup")],
    )
    invalid = job_row("")
    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        [invalid],
        duplicate_sheet,
        run_id="run_conflict",
        timestamp=NOW,
    )

    assert plan.conflict_count == 1
    assert plan.invalid_count == 1
    assert not plan.inserts
    assert not plan.updates


def test_missing_sheet_records_are_not_closed_or_deleted() -> None:
    existing = job_row("job_absent")
    adapter = InMemorySheetsAdapter({"Industry_Jobs": [existing]})
    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        [],
        adapter.read_worksheet("Industry_Jobs"),
        run_id="run_missing",
        timestamp=NOW,
    )
    adapter.apply_plan(plan, dry_run=False)

    assert adapter.read_worksheet("Industry_Jobs").rows == [existing]
    assert not adapter.write_operations


def test_external_formula_text_is_written_with_raw_input_mode() -> None:
    malicious = job_row("job_literal", title='=HYPERLINK("https://bad.example","click")')
    adapter = InMemorySheetsAdapter()
    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        [malicious],
        adapter.read_worksheet("Industry_Jobs"),
        run_id="run_raw",
        timestamp=NOW,
    )
    adapter.apply_plan(plan, dry_run=False)

    assert plan.inserts[0].value_input_option == "RAW"
    assert adapter.write_operations[0] == ("Industry_Jobs", "batch_insert", "RAW")
    assert adapter.read_worksheet("Industry_Jobs").rows[0]["Job_Title"].startswith("=")


def test_invalid_headers_fail_before_any_write() -> None:
    invalid_sheet = WorksheetData(headers=("Wrong_Header",), rows=[])

    with pytest.raises(SheetSchemaError, match="refusing to plan writes"):
        plan_sheet_sync(
            INDUSTRY_JOBS_SCHEMA,
            [job_row("job_one")],
            invalid_sheet,
            run_id="run_headers",
            timestamp=NOW,
        )


def test_feedback_load_preserves_independent_user_fields_and_notes() -> None:
    feedback_row = {
        "Record_ID": "job_feedback",
        "Preference": "Very Interested",
        "Saved": True,
        "Hidden": False,
        "Personal_Notes": "Discuss with supervisor",
        "Updated_At": NOW.isoformat(),
    }
    adapter = InMemorySheetsAdapter({"My_Feedback": [feedback_row]})

    result = load_feedback(adapter)
    feedback = result.feedback_by_id["job_feedback"]

    assert feedback.preference is PreferenceFeedback.VERY_INTERESTED
    assert feedback.saved is True
    assert feedback.hidden is False
    assert feedback.notes == "Discuss with supervisor"
    assert not result.invalid_records
    assert adapter.read_worksheet("My_Feedback").rows == [feedback_row]


def test_feedback_load_ignores_1999_blank_checkbox_template_rows() -> None:
    template_row = {
        "Record_ID": "",
        "Preference": "",
        "Saved": False,
        "Hidden": False,
        "Personal_Notes": "",
        "Updated_At": "",
    }
    adapter = InMemorySheetsAdapter({"My_Feedback": [template_row] * 1999})

    result = load_feedback(adapter)

    assert result.feedback_by_id == {}
    assert result.invalid_records == []
    assert result.conflicts == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Preference", "Interested"),
        ("Saved", True),
        ("Hidden", True),
        ("Personal_Notes", "Needs an ID"),
        ("Updated_At", NOW.isoformat()),
    ],
)
def test_feedback_without_record_id_but_with_meaningful_input_is_invalid(
    field: str, value: object
) -> None:
    row = {
        "Record_ID": "",
        "Preference": "",
        "Saved": False,
        "Hidden": False,
        "Personal_Notes": "",
        "Updated_At": "",
    }
    row[field] = value

    result = load_feedback(InMemorySheetsAdapter({"My_Feedback": [row]}))

    assert result.feedback_by_id == {}
    assert len(result.invalid_records) == 1
    assert "Record_ID is required" in result.invalid_records[0].message


def test_duplicate_feedback_ids_are_conflicts_not_silent_overwrites() -> None:
    row = {
        "Record_ID": "job_feedback",
        "Preference": "Interested",
        "Saved": False,
        "Hidden": True,
        "Personal_Notes": "Keep hidden",
        "Updated_At": NOW.isoformat(),
    }
    adapter = InMemorySheetsAdapter({"My_Feedback": [row, row]})

    result = load_feedback(adapter)

    assert len(result.conflicts) == 1
    assert "job_feedback" not in result.feedback_by_id


def _job_fixture() -> dict[str, object]:
    return {
        "fictional": True,
        "title": "AI Research Scientist",
        "organization": "Fictional AI Lab",
        "official_job_id": "FAI-1",
        "source_url": "https://jobs.fictional-ai.example/FAI-1",
        "research_areas": ["Artificial Intelligence"],
        "research_orientation": "Research-oriented",
        "education_requirement": "PhD Required",
        "working_language": "English",
    }


def _phd_fixture() -> dict[str, object]:
    return {
        "fictional": True,
        "title": "PhD in Computational Neuroscience",
        "organization": "Fictional University",
        "official_opportunity_id": "FU-1",
        "source_url": "https://graduate.fictional.example/FU-1",
        "research_areas": ["Computational Neuroscience"],
        "opportunity_type": "Advertised PhD position",
        "opportunity_status": "Confirmed Open",
        "target_cycle": "Fall 2027",
    }


def test_one_sheet_failure_does_not_corrupt_other_categories() -> None:
    jobs = run_jobs_pipeline([_job_fixture()], config_dir=PROJECT_ROOT / "config", observed_at=NOW)
    phd = run_phd_pipeline([_phd_fixture()], config_dir=PROJECT_ROOT / "config", observed_at=NOW)
    adapter = InMemorySheetsAdapter(headers_by_sheet={"PhD_Opportunities": ("Invalid",)})

    result = sync_execution_report(
        ExecutionReport(pipelines={"jobs": jobs, "phd": phd}),
        adapter,
        dry_run=False,
        run_id="run_isolated",
        timestamp=NOW,
    )

    assert len(adapter.read_worksheet("Industry_Jobs").rows) == 1
    assert adapter.read_worksheet("PhD_Opportunities").rows == []
    assert "phd" in result.failures
    assert "jobs" in result.plans
    assert len(adapter.read_worksheet("Run_Logs").rows) == 2

    sync_execution_report(
        ExecutionReport(pipelines={"jobs": jobs, "phd": phd}),
        adapter,
        dry_run=False,
        run_id="run_isolated",
        timestamp=NOW,
    )
    assert len(adapter.read_worksheet("Run_Logs").rows) == 2


def test_opportunity_sync_never_overwrites_feedback_on_second_run() -> None:
    feedback_row = {
        "Record_ID": "job_feedback",
        "Preference": "Not Relevant",
        "Saved": False,
        "Hidden": True,
        "Personal_Notes": "User-owned note",
        "Updated_At": NOW.isoformat(),
    }
    adapter = InMemorySheetsAdapter({"My_Feedback": [feedback_row]})
    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        [job_row("job_feedback")],
        adapter.read_worksheet("Industry_Jobs"),
        run_id="run_feedback",
        timestamp=NOW,
    )
    adapter.apply_plan(plan, dry_run=False)
    adapter.apply_plan(plan, dry_run=False)

    assert adapter.read_worksheet("My_Feedback").rows == [feedback_row]
    loaded = load_feedback(adapter).feedback_by_id["job_feedback"]
    assert loaded.hidden is True
    assert loaded.saved is False
    assert loaded.notes == "User-owned note"


def test_loaded_feedback_can_be_applied_without_changing_base_relevance() -> None:
    first = run_jobs_pipeline([_job_fixture()], config_dir=PROJECT_ROOT / "config", observed_at=NOW)
    record_id = first.records[0].opportunity.opportunity_id
    feedback_row = {
        "Record_ID": record_id,
        "Preference": "Interested",
        "Saved": True,
        "Hidden": True,
        "Personal_Notes": "Canonical sheet feedback",
        "Updated_At": NOW.isoformat(),
    }
    feedback = load_feedback(InMemorySheetsAdapter({"My_Feedback": [feedback_row]})).feedback_by_id
    second = run_jobs_pipeline(
        [_job_fixture()],
        config_dir=PROJECT_ROOT / "config",
        observed_at=NOW,
        feedback_by_id=feedback,
    )

    assert second.records[0].score.components == first.records[0].score.components
    assert second.records[0].feedback is feedback[record_id]
    assert second.records[0].feedback.saved is True
    assert second.records[0].feedback.hidden is True
    assert second.records[0].rank is None


def test_salary_and_status_updates_create_specific_change_events() -> None:
    existing = job_row("job_change")
    existing["Original_Salary"] = "USD 140,000"
    existing["Opportunity_Status"] = "Open"
    desired = deepcopy(existing)
    desired["Original_Salary"] = "USD 155,000"
    desired["Opportunity_Status"] = "Closed"

    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        [desired],
        WorksheetData(headers=INDUSTRY_JOBS_SCHEMA.headers, rows=[existing]),
        run_id="run_changes",
        timestamp=NOW,
    )

    assert {(row["Change_Type"], row["Field_Name"]) for row in plan.change_log_rows} == {
        ("SALARY_CHANGE", "Original_Salary"),
        ("STATUS_CHANGE", "Opportunity_Status"),
    }


def test_last_seen_only_update_does_not_create_meaningful_change_event() -> None:
    existing = job_row("job_observed")
    desired = deepcopy(existing)
    desired["Last_Seen"] = "2026-10-20T09:00:00+00:00"

    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        [desired],
        WorksheetData(headers=INDUSTRY_JOBS_SCHEMA.headers, rows=[existing]),
        run_id="run_observed",
        timestamp=NOW,
    )

    assert plan.update_count == 1
    assert plan.updates[0].changed_fields == {"Last_Seen": "2026-10-20T09:00:00+00:00"}
    assert plan.change_log_rows == []


def test_material_change_logs_only_material_fields_when_last_seen_also_advances() -> None:
    existing = job_row("job_material", title="Old title")
    desired = job_row("job_material", title="New title")
    desired["Last_Seen"] = "2026-10-20T09:00:00+00:00"

    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        [desired],
        WorksheetData(headers=INDUSTRY_JOBS_SCHEMA.headers, rows=[existing]),
        run_id="run_material",
        timestamp=NOW,
    )

    assert {row["Field_Name"] for row in plan.change_log_rows} == {"Job_Title"}


def test_run_log_counts_validation_errors_but_not_intentional_exclusions() -> None:
    explicit_non_english = _job_fixture() | {"working_language": "German required"}
    report = run_jobs_pipeline(
        [explicit_non_english, {"fictional": True}],
        config_dir=PROJECT_ROOT / "config",
        observed_at=NOW,
    )
    adapter = InMemorySheetsAdapter()

    sync_execution_report(
        ExecutionReport(pipelines={"jobs": report}),
        adapter,
        dry_run=False,
        run_id="run_log_accuracy",
        timestamp=NOW,
    )

    log = adapter.read_worksheet("Run_Logs").rows[0]
    assert log["Error_Count"] == 1
    assert "rejected=1" in log["Error_Summary"]
    assert "excluded=1" in log["Error_Summary"]
    assert "pipeline_errors=0" in log["Error_Summary"]


def test_run_log_distinguishes_pipeline_failure_from_synchronization_error() -> None:
    report = PipelineReport(
        category="jobs",
        status=PipelineStatus.FAILED,
        records_processed=0,
        records_accepted=0,
        duplicates_found=0,
        records_excluded=0,
        validation_errors=(),
        records=(),
        failure="source parser crashed",
    )
    adapter = InMemorySheetsAdapter()

    sync_execution_report(
        ExecutionReport(pipelines={"jobs": report}),
        adapter,
        dry_run=False,
        run_id="run_pipeline_failure",
        timestamp=NOW,
    )

    log = adapter.read_worksheet("Run_Logs").rows[0]
    assert log["Error_Count"] == 1
    assert "pipeline_errors=1" in log["Error_Summary"]
    assert "synchronization_errors=0" in log["Error_Summary"]


def test_run_log_aggregates_source_pipeline_and_sync_errors_separately() -> None:
    report = run_jobs_pipeline(
        [_job_fixture()], config_dir=PROJECT_ROOT / "config", observed_at=NOW
    )
    report.records_fetched = 12
    report.source_extraction_errors = ("one source record could not be extracted",)
    report.pipeline_processing_errors = ("one scoring error",)
    adapter = InMemorySheetsAdapter(headers_by_sheet={"Industry_Jobs": ("Invalid",)})

    sync_execution_report(
        ExecutionReport(pipelines={"jobs": report}),
        adapter,
        dry_run=False,
        run_id="run_aggregate_errors",
        timestamp=NOW,
    )

    log = adapter.read_worksheet("Run_Logs").rows[0]
    assert log["Error_Count"] == 3
    assert "fetched=12" in log["Error_Summary"]
    assert "source_extraction_errors=1" in log["Error_Summary"]
    assert "pipeline_errors=1" in log["Error_Summary"]
    assert "synchronization_errors=1" in log["Error_Summary"]


def test_declared_feedback_and_log_schemas_are_explicit() -> None:
    assert MY_FEEDBACK_SCHEMA.user_managed_headers == (
        "Preference",
        "Saved",
        "Hidden",
        "Personal_Notes",
        "Updated_At",
    )
    assert CHANGE_LOG_SCHEMA.record_id_header == "Record_ID"
    assert PHD_OPPORTUNITIES_SCHEMA.headers[0] == "Record_ID"


def test_watchlist_sheet_is_a_read_only_mirror_of_yaml_configuration() -> None:
    targets = load_watchlist(PROJECT_ROOT / "config" / "watchlist.yaml")
    rows = watchlist_rows(targets)

    assert len(rows) == 38
    assert {row["Record_ID"] for row in rows} == {target.target_id for target in targets}
    assert all(set(row) == set(WATCHLIST_SCHEMA.headers) for row in rows)
