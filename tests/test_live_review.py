from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from research_radar.live_integration import (
    INCREMENTAL_APPLY_CONFIRMATION,
    DataMode,
    InitialLiveSyncApproval,
    LiveDataError,
    ObservationState,
    RecommendationClassification,
    TargetEnvironment,
    apply_initial_live_pilot_sync,
    configured_live_pilot_adapter,
    prepare_incremental_live_sync,
    prepare_live_sheets_preview,
    reconcile_incremental_plan,
    resolve_observation_state,
    validate_configured_data_mode,
    validate_incremental_apply_authorization,
    validate_target_compatibility,
)
from research_radar.models import SourceHealth
from research_radar.pipelines import run_events_pipeline, run_jobs_pipeline, run_phd_pipeline
from research_radar.storage.json_store import JsonOutputStore
from research_radar.storage.sheets import InMemorySheetsAdapter

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)


class PilotMemoryAdapter(InMemorySheetsAdapter):
    settings = type(
        "Settings",
        (),
        {"environment": "live-pilot", "spreadsheet_id": "pilot-id"},
    )()

    def get_spreadsheet_title(self) -> str:
        return "ResearchRadar AI — LIVE PILOT"


def _raw_records() -> dict[str, dict[str, object]]:
    common = {
        "fictional": False,
        "source_verification_status": "VERIFIED_OFFICIAL",
        "source_type": "official_fixture",
        "extraction_method": "deterministic_test_parser",
    }
    return {
        "jobs": common
        | {
            "title": "Research Scientist, Human Behavior",
            "organization": "Official Research Company",
            "official_job_id": "JOB-1",
            "source_url": "https://jobs.official.example/JOB-1",
            "official_source_url": "https://official.example/careers",
            "adapter_source_id": "official_jobs",
            "location": "New York, United States",
            "country": "United States",
            "research_areas": [
                "Computational cognitive neuroscience",
                "Computational models of human behavior",
            ],
            "research_orientation": "Research-oriented",
            "education_requirement": "Unknown",
            "working_language": None,
            "salary": {},
            "source_evidence": ["Official job ID JOB-1", "Title: Research Scientist"],
            "opportunity_status": "confirmed open",
        },
        "phd": common
        | {
            "title": "Gatsby Unit PhD Programme",
            "organization": "University College London",
            "official_opportunity_id": "ucl-gatsby-2027",
            "source_url": "https://www.ucl.ac.uk/gatsby/phd",
            "official_source_url": "https://www.ucl.ac.uk/gatsby/phd",
            "adapter_source_id": "ucl_gatsby_phd",
            "admission_url": "https://apply.gatsby.ucl.ac.uk/",
            "target_cycle": "2027",
            "deadline": "2026-11-09",
            "funding_status": "Fully funded (source stated)",
            "research_areas": ["Computational neuroscience"],
            "opportunity_status": "confirmed open",
            "opportunity_type": "centralized phd program admission",
            "source_evidence": ["Applications are open", "Admission cycle: 2027"],
        },
        "events": common
        | {
            "title": "COSYNE 2027",
            "series_name": "COSYNE",
            "organization": "COSYNE",
            "source_url": "https://www.cosyne.org/",
            "official_source_url": "https://www.cosyne.org/",
            "official_url": "https://www.cosyne.org/",
            "adapter_source_id": "cosyne_official",
            "edition_year": 2027,
            "event_type": "academic conference",
            "country": "Canada",
            "location": "Montréal",
            "research_areas": ["Computational neuroscience"],
            "starts_on": "2027-03-11",
            "ends_on": "2027-03-16",
            "overall_starts_on": "2027-03-11",
            "overall_ends_on": "2027-03-16",
            "main_meeting_starts_on": "2027-03-11",
            "main_meeting_ends_on": "2027-03-14",
            "workshop_starts_on": "2027-03-15",
            "workshop_ends_on": "2027-03-16",
            "submission_deadline": "2026-10-18",
            "workshop_submission_deadline": "2026-11-01",
            "presenter_registration_deadline": "2027-01-31",
            "opportunity_status": "confirmed upcoming",
            "source_evidence": [
                "Main meeting: 11-14 March 2027",
                "Workshops: 15-16 March 2027",
            ],
        },
    }


def _write_live_snapshots(
    live_dir: Path,
    *,
    mutate: Callable[[dict[str, dict[str, object]]], None] | None = None,
) -> dict[str, str]:
    raws = _raw_records()
    if mutate:
        mutate(raws)
    reports = {
        "jobs": run_jobs_pipeline([raws["jobs"]], config_dir=ROOT / "config", observed_at=NOW),
        "phd": run_phd_pipeline([raws["phd"]], config_dir=ROOT / "config", observed_at=NOW),
        "events": run_events_pipeline(
            [raws["events"]],
            config_dir=ROOT / "config",
            observed_at=NOW,
            reference_date=date(2026, 10, 11),
        ),
    }
    store = JsonOutputStore(live_dir)
    ids: dict[str, str] = {}
    for category, report in reports.items():
        store.write(report)
        ids[category] = report.records[0].opportunity.opportunity_id
    metadata = {
        "sources": {
            raw["adapter_source_id"]: {
                "records_fetched": 10 if category == "jobs" else 1,
                "records_considered": 1,
                "records": [raw],
            }
            for category, raw in raws.items()
            if raw.get("adapter_source_id")
        },
        "pipelines": {
            category: {
                "records_extracted": 1,
                "records_accepted": 1,
            }
            for category in raws
        },
    }
    (live_dir / "source_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return ids


def test_live_data_rejects_test_and_production_targets() -> None:
    validate_target_compatibility(DataMode.SYNTHETIC, TargetEnvironment.TEST)
    validate_target_compatibility(DataMode.LIVE, TargetEnvironment.LIVE_PILOT)
    with pytest.raises(LiveDataError, match="live-pilot"):
        validate_target_compatibility(DataMode.LIVE, TargetEnvironment.TEST)
    with pytest.raises(LiveDataError, match="not enabled"):
        validate_target_compatibility(DataMode.LIVE, TargetEnvironment.PRODUCTION)


def test_configured_mode_and_pilot_environment_must_match() -> None:
    with pytest.raises(LiveDataError, match="incompatible"):
        validate_configured_data_mode(DataMode.LIVE, {"RESEARCH_RADAR_DATA_MODE": "synthetic"})
    with pytest.raises(LiveDataError, match="live-pilot"):
        configured_live_pilot_adapter(
            {
                "GOOGLE_LIVE_PILOT_SPREADSHEET_ID": "pilot-id",
                "RESEARCH_RADAR_SHEETS_ENV": "test",
            }
        )
    assert configured_live_pilot_adapter({"GOOGLE_SPREADSHEET_ID": "synthetic-test-id"}) is None


def test_live_loader_refuses_fictional_records(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    _write_live_snapshots(
        live_dir,
        mutate=lambda raws: raws["jobs"].__setitem__("fictional", True),
    )

    with pytest.raises(LiveDataError, match="fictional"):
        prepare_live_sheets_preview(
            project_root=ROOT,
            live_data_dir=live_dir,
            review_dir=tmp_path / "review",
            generated_at=NOW + timedelta(days=1),
            reference_date=date(2026, 10, 12),
        )


@pytest.mark.parametrize("missing_field", ["official_source_url", "adapter_source_id"])
def test_provenance_missing_required_metadata_blocks_sheet_action(
    tmp_path: Path, missing_field: str
) -> None:
    live_dir = tmp_path / "live"
    _write_live_snapshots(
        live_dir,
        mutate=lambda raws: raws["jobs"].pop(missing_field),
    )

    preview = prepare_live_sheets_preview(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW + timedelta(days=1),
        reference_date=date(2026, 10, 12),
    )

    job_audit = next(item for item in preview.provenance.records if item.category == "jobs")
    assert job_audit.valid is False
    assert any(missing_field in issue for issue in job_audit.blocking_issues)
    assert preview.workbook.plans["jobs"].insert_count == 0


def test_cached_preview_preserves_observation_timestamps_and_stable_ids(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    ids = _write_live_snapshots(live_dir)

    preview = prepare_live_sheets_preview(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW + timedelta(days=10),
        reference_date=date(2026, 10, 21),
    )

    job = preview.execution.pipelines["jobs"].records[0].opportunity
    assert job.opportunity_id == ids["jobs"]
    assert job.first_seen_at == NOW
    assert job.last_seen_at == NOW
    assert job.content_updated_at == NOW
    assert job.source_retrieved_at == NOW
    assert preview.sheet_synced_at is None


def test_offline_preview_is_dry_run_and_generates_human_review(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    _write_live_snapshots(live_dir)

    preview = prepare_live_sheets_preview(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 11),
    )

    assert preview.offline is True
    assert preview.workbook.dry_run is True
    assert {name: plan.insert_count for name, plan in preview.workbook.plans.items()} == {
        "jobs": 1,
        "phd": 1,
        "events": 1,
    }
    assert preview.watchlist_plan.insert_count == 38
    report = preview.review_report_path.read_text()
    assert "ResearchRadar Live Data Review" in report
    assert "Research Scientist" in report
    assert "https://jobs.official.example/JOB-1" in report
    assert "Gatsby Unit PhD Programme" in report
    assert "COSYNE 2027" in report
    assert "INSERT" in report


def test_configured_pilot_workbook_title_must_match_exactly(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    _write_live_snapshots(live_dir)

    class WrongWorkbookAdapter(InMemorySheetsAdapter):
        settings = type("Settings", (), {"environment": "live-pilot"})()

        def get_spreadsheet_title(self) -> str:
            return "ResearchRadar AI — TEST"

    with pytest.raises(LiveDataError, match="LIVE PILOT"):
        prepare_live_sheets_preview(
            project_root=ROOT,
            live_data_dir=live_dir,
            review_dir=tmp_path / "review",
            generated_at=NOW,
            reference_date=date(2026, 10, 11),
            adapter=WrongWorkbookAdapter(),
            target_environment=TargetEnvironment.LIVE_PILOT,
        )


def test_review_preserves_unknown_job_salary_and_language(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    _write_live_snapshots(live_dir)

    preview = prepare_live_sheets_preview(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 11),
    )

    job = preview.execution.pipelines["jobs"].records[0].opportunity
    assert job.working_language is None
    assert job.original_salary_text is None
    audit = next(item for item in preview.provenance.records if item.category == "jobs")
    assert "working_language" in audit.missing_important_fields
    assert "salary" in audit.missing_important_fields


def test_phd_cycle_and_conference_date_semantics_survive_preview(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    _write_live_snapshots(live_dir)

    preview = prepare_live_sheets_preview(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 11),
    )

    phd = preview.execution.pipelines["phd"].records[0].opportunity
    event = preview.execution.pipelines["events"].records[0].opportunity
    assert phd.target_cycle == "2027"
    assert "2028" not in phd.source_evidence
    assert event.overall_starts_on == date(2027, 3, 11)
    assert event.overall_ends_on == date(2027, 3, 16)
    assert event.main_meeting_ends_on == date(2027, 3, 14)
    assert event.workshop_starts_on == date(2027, 3, 15)
    assert event.workshop_submission_deadline == date(2026, 11, 1)
    assert event.presenter_registration_deadline == date(2027, 1, 31)


def test_source_coverage_and_feedback_are_preserved(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    ids = _write_live_snapshots(live_dir)
    feedback_row = {
        "Record_ID": ids["jobs"],
        "Preference": "Very Interested",
        "Saved": True,
        "Hidden": False,
        "Personal_Notes": "Pilot review",
        "Updated_At": NOW.isoformat(),
    }

    class PilotMemoryAdapter(InMemorySheetsAdapter):
        settings = type("Settings", (), {"environment": "live-pilot"})()

        def get_spreadsheet_title(self) -> str:
            return "ResearchRadar AI — LIVE PILOT"

    adapter = PilotMemoryAdapter({"My_Feedback": [feedback_row]})

    preview = prepare_live_sheets_preview(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 11),
        adapter=adapter,
        target_environment=TargetEnvironment.LIVE_PILOT,
    )

    coverage = preview.coverage["official_jobs"]
    assert coverage.records_returned == 10
    assert coverage.records_considered == 1
    assert coverage.records_extracted == 1
    assert coverage.records_accepted == 1
    job = preview.execution.pipelines["jobs"].records[0]
    assert job.feedback is not None
    assert job.feedback.saved is True
    assert job.feedback.hidden is False
    assert job.feedback.notes == "Pilot review"
    assert job.score.components["research_relevance"] == 87.5


def test_verified_source_and_low_career_relevance_are_independent(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    ids = _write_live_snapshots(
        live_dir,
        mutate=lambda raws: raws["jobs"].__setitem__("title", "Recruiter, AI Research"),
    )

    preview = prepare_live_sheets_preview(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 11),
    )

    job = preview.execution.pipelines["jobs"].records[0].opportunity
    decision = preview.recommendations.by_record_id[ids["jobs"]]
    assert job.source_verification_status.value == "VERIFIED_OFFICIAL"
    assert decision.classification is RecommendationClassification.LOW_PRIORITY
    assert "recruiter" in decision.explanation.casefold()
    assert preview.workbook.plans["jobs"].insert_count == 0
    assert len(preview.execution.pipelines["jobs"].records) == 1


def test_phd_required_research_role_remains_recommended_future_target(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"

    def future_role(raws: dict[str, dict[str, object]]) -> None:
        raws["jobs"]["title"] = "Research Scientist, Reinforcement Learning"
        raws["jobs"]["education_requirement"] = "PhD Required"
        raws["jobs"]["research_areas"] = ["Reinforcement learning"]

    ids = _write_live_snapshots(live_dir, mutate=future_role)
    preview = prepare_live_sheets_preview(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 11),
    )

    job = preview.execution.pipelines["jobs"].records[0].opportunity
    decision = preview.recommendations.by_record_id[ids["jobs"]]
    assert job.classification.value == "FUTURE_CAREER_TARGET"
    assert decision.classification is RecommendationClassification.NEEDS_REVIEW
    assert decision.domain_fit.value == "TECHNICAL_TRANSFERABLE"
    assert preview.workbook.plans["jobs"].insert_count == 0


def test_uncertain_recommendation_is_held_out_of_sheet_plan(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    ids = _write_live_snapshots(
        live_dir,
        mutate=lambda raws: raws["jobs"].__setitem__("title", "Product Manager, Research"),
    )

    preview = prepare_live_sheets_preview(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 11),
    )

    decision = preview.recommendations.by_record_id[ids["jobs"]]
    assert decision.classification is RecommendationClassification.NEEDS_REVIEW
    assert preview.workbook.plans["jobs"].insert_count == 0


def test_review_report_groups_records_and_preserves_required_fields(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    ids = _write_live_snapshots(
        live_dir,
        mutate=lambda raws: raws["jobs"].__setitem__("title", "Recruiter, AI Research"),
    )

    preview = prepare_live_sheets_preview(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 11),
    )
    report = preview.review_report_path.read_text(encoding="utf-8")

    assert "## A. Recommended for synchronization" in report
    assert "## B. Needs manual review" in report
    assert "## C. Low-priority archive" in report
    assert "Recommendation" in report
    assert "Career stage" in report
    assert ids["jobs"] in report
    assert "LOCAL_ARCHIVE" in report


def test_initial_live_sync_applies_only_the_exact_approved_plan_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_dir = tmp_path / "live"
    _write_live_snapshots(live_dir)

    class PilotMemoryAdapter(InMemorySheetsAdapter):
        settings = type(
            "Settings",
            (),
            {"environment": "live-pilot", "spreadsheet_id": "pilot-id"},
        )()

        def get_spreadsheet_title(self) -> str:
            return "ResearchRadar AI — LIVE PILOT"

    adapter = PilotMemoryAdapter()
    monkeypatch.setenv("GOOGLE_LIVE_PILOT_SPREADSHEET_ID", "pilot-id")
    monkeypatch.setenv("RESEARCH_RADAR_SHEETS_ENV", "live-pilot")
    monkeypatch.setenv("RESEARCH_RADAR_DATA_MODE", "live")
    approval = InitialLiveSyncApproval(
        opportunity_inserts={"jobs": 1, "phd": 1, "events": 1},
        watchlist_inserts=38,
        recommendation_counts={
            RecommendationClassification.HIGH_PRIORITY: 1,
            RecommendationClassification.RELEVANT: 2,
            RecommendationClassification.NEEDS_REVIEW: 0,
            RecommendationClassification.LOW_PRIORITY: 0,
        },
        provenance_valid=3,
    )

    result = apply_initial_live_pilot_sync(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW + timedelta(days=1),
        reference_date=date(2026, 10, 12),
        adapter=adapter,
        approval=approval,
    )

    assert result.applied_sheets == (
        "Industry_Jobs",
        "Change_Log",
        "PhD_Opportunities",
        "Events",
        "Watchlist",
        "Run_Logs",
    )
    assert len(adapter.read_worksheet("Industry_Jobs").rows) == 1
    assert len(adapter.read_worksheet("PhD_Opportunities").rows) == 1
    assert len(adapter.read_worksheet("Events").rows) == 1
    assert len(adapter.read_worksheet("Watchlist").rows) == 38
    assert len(adapter.read_worksheet("Run_Logs").rows) == 3
    assert len(adapter.read_worksheet("Change_Log").rows) == 3

    with pytest.raises(LiveDataError, match="approved initial plan"):
        apply_initial_live_pilot_sync(
            project_root=ROOT,
            live_data_dir=live_dir,
            review_dir=tmp_path / "review",
            generated_at=NOW + timedelta(days=1, minutes=1),
            reference_date=date(2026, 10, 12),
            adapter=adapter,
            approval=approval,
        )
    assert len(adapter.read_worksheet("Industry_Jobs").rows) == 1
    assert len(adapter.read_worksheet("PhD_Opportunities").rows) == 1
    assert len(adapter.read_worksheet("Events").rows) == 1
    assert len(adapter.read_worksheet("Watchlist").rows) == 38
    assert len(adapter.read_worksheet("Run_Logs").rows) == 3
    assert len(adapter.read_worksheet("Change_Log").rows) == 3


def test_incremental_cached_preview_has_stable_fingerprint_and_no_actions(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    _write_live_snapshots(live_dir)
    initial = prepare_live_sheets_preview(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 11),
    )
    adapter = PilotMemoryAdapter(
        {
            plan.sheet_name: [operation.row for operation in plan.inserts]
            for plan in initial.workbook.plans.values()
        }
        | {"Watchlist": [operation.row for operation in initial.watchlist_plan.inserts]}
    )

    first = prepare_incremental_live_sync(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW + timedelta(days=1),
        reference_date=date(2026, 10, 12),
        adapter=adapter,
    )
    second = prepare_incremental_live_sync(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW + timedelta(days=2),
        reference_date=date(2026, 10, 12),
        adapter=adapter,
    )

    assert first.plan_fingerprint == second.plan_fingerprint
    assert all(plan.insert_count == 0 for plan in first.preview.workbook.plans.values())
    assert all(plan.update_count == 0 for plan in first.preview.workbook.plans.values())
    assert first.preview.watchlist_plan.insert_count == 0
    assert first.preview.watchlist_plan.update_count == 0
    assert first.artifact_path.exists()


def test_incremental_insert_plan_fingerprint_excludes_generation_time(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    _write_live_snapshots(live_dir)
    adapter = PilotMemoryAdapter()

    first = prepare_incremental_live_sync(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 12),
        adapter=adapter,
    )
    second = prepare_incremental_live_sync(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW + timedelta(hours=1),
        reference_date=date(2026, 10, 12),
        adapter=adapter,
    )

    assert any(plan.insert_count for plan in first.preview.workbook.plans.values())
    assert first.plan_fingerprint == second.plan_fingerprint


def test_incremental_fingerprint_changes_with_fresh_source_observation(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    _write_live_snapshots(live_dir)
    initial = prepare_live_sheets_preview(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 11),
    )
    adapter = PilotMemoryAdapter(
        {
            plan.sheet_name: [operation.row for operation in plan.inserts]
            for plan in initial.workbook.plans.values()
        }
        | {"Watchlist": [operation.row for operation in initial.watchlist_plan.inserts]}
    )
    first = prepare_incremental_live_sync(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 12),
        adapter=adapter,
    )
    metadata_path = live_dir / "source_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["sources"]["official_jobs"]["health"] = "FAILED"
    metadata["sources"]["official_jobs"]["retrieved_at"] = "2026-10-12T09:00:00+00:00"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    second = prepare_incremental_live_sync(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 12),
        adapter=adapter,
    )

    assert first.plan_fingerprint != second.plan_fingerprint


def test_incremental_feedback_round_trip_preserves_user_owned_fields(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    ids = _write_live_snapshots(live_dir)
    feedback_row = {
        "Record_ID": ids["jobs"],
        "Preference": "Very Interested",
        "Saved": True,
        "Hidden": False,
        "Personal_Notes": "A personal research note",
        "Updated_At": "",
    }
    template = {
        "Record_ID": "",
        "Preference": "",
        "Saved": False,
        "Hidden": False,
        "Personal_Notes": "",
        "Updated_At": "",
    }
    adapter = PilotMemoryAdapter({"My_Feedback": [feedback_row, *([template] * 1998)]})

    result = prepare_incremental_live_sync(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 11),
        adapter=adapter,
    )

    feedback = result.preview.feedback.feedback_by_id[ids["jobs"]]
    assert feedback.preference.value == "VERY_INTERESTED"
    assert feedback.saved is True
    assert feedback.hidden is False
    assert feedback.notes == "A personal research note"
    assert feedback.updated_at is None
    assert result.preview.feedback.template_rows_ignored == 1998
    assert adapter.read_worksheet("My_Feedback").rows[0] == feedback_row


def test_incremental_feedback_with_title_instead_of_record_id_is_rejected(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    _write_live_snapshots(live_dir)
    feedback_row = {
        "Record_ID": "Research Scientist",
        "Preference": "Interested",
        "Saved": True,
        "Hidden": False,
        "Personal_Notes": "Keep for review",
        "Updated_At": "",
    }
    adapter = PilotMemoryAdapter({"My_Feedback": [feedback_row]})

    with pytest.raises(LiveDataError, match="not linked to known records"):
        prepare_incremental_live_sync(
            project_root=ROOT,
            live_data_dir=live_dir,
            review_dir=tmp_path / "review",
            generated_at=NOW,
            reference_date=date(2026, 10, 11),
            adapter=adapter,
        )

    assert adapter.read_worksheet("My_Feedback").rows == [feedback_row]


def test_partial_insert_recovery_does_not_repeat_completed_record(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    _write_live_snapshots(live_dir)
    original = prepare_incremental_live_sync(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 11),
        adapter=PilotMemoryAdapter(),
    )
    completed_job = original.preview.workbook.plans["jobs"].inserts[0].row
    partial_adapter = PilotMemoryAdapter({"Industry_Jobs": [completed_job]})

    recovery = reconcile_incremental_plan(original, partial_adapter)

    assert completed_job["Record_ID"] in recovery.sheets["Industry_Jobs"].completed_record_ids
    assert completed_job["Record_ID"] not in recovery.sheets["Industry_Jobs"].pending_record_ids
    assert recovery.missing_change_event_ids
    assert recovery.conflicts == ()


def test_incremental_authorization_requires_matching_fingerprint_and_confirmation(
    tmp_path: Path,
) -> None:
    live_dir = tmp_path / "live"
    _write_live_snapshots(live_dir)
    plan = prepare_incremental_live_sync(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 11),
        adapter=PilotMemoryAdapter(),
    )

    with pytest.raises(LiveDataError, match="fingerprint"):
        validate_incremental_apply_authorization(
            plan,
            approved_fingerprint="wrong",
            confirmation=INCREMENTAL_APPLY_CONFIRMATION,
        )
    with pytest.raises(LiveDataError, match="confirmation"):
        validate_incremental_apply_authorization(
            plan,
            approved_fingerprint=plan.plan_fingerprint,
            confirmation="",
        )
    validate_incremental_apply_authorization(
        plan,
        approved_fingerprint=plan.plan_fingerprint,
        confirmation=INCREMENTAL_APPLY_CONFIRMATION,
    )


@pytest.mark.parametrize(
    ("health", "observed", "explicit_status", "expected"),
    [
        (SourceHealth.SUCCESS, False, None, ObservationState.NOT_OBSERVED),
        (SourceHealth.FAILED, False, None, ObservationState.SOURCE_UNAVAILABLE),
        (SourceHealth.BLOCKED, False, None, ObservationState.SOURCE_UNAVAILABLE),
        (SourceHealth.SUCCESS, True, "CLOSED", ObservationState.CONFIRMED_CLOSED),
        (SourceHealth.SUCCESS, True, "CONFIRMED_OPEN", ObservationState.CONFIRMED_ACTIVE),
    ],
)
def test_observation_policy_is_conservative(
    health: SourceHealth,
    observed: bool,
    explicit_status: str | None,
    expected: ObservationState,
) -> None:
    decision = resolve_observation_state(
        source_health=health,
        observed=observed,
        explicit_status=explicit_status,
    )

    assert decision.state is expected
    if not observed:
        assert decision.may_change_opportunity_status is False


def test_existing_record_remains_updatable_after_recommendation_demotion(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    ids = _write_live_snapshots(live_dir)
    initial = prepare_live_sheets_preview(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 11),
    )
    existing_job = initial.workbook.plans["jobs"].inserts[0].row
    _write_live_snapshots(
        live_dir,
        mutate=lambda raws: raws["jobs"].__setitem__("title", "Recruiter, AI Research"),
    )
    adapter = PilotMemoryAdapter({"Industry_Jobs": [existing_job]})

    incremental = prepare_incremental_live_sync(
        project_root=ROOT,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW + timedelta(days=1),
        reference_date=date(2026, 10, 12),
        adapter=adapter,
    )

    assert incremental.preview.recommendations.by_record_id[ids["jobs"]].classification is (
        RecommendationClassification.LOW_PRIORITY
    )
    assert incremental.preview.workbook.plans["jobs"].insert_count == 0
    assert incremental.preview.workbook.plans["jobs"].update_count == 1
    update = incremental.preview.workbook.plans["jobs"].updates[0]
    assert update.record_id == ids["jobs"]
    assert update.changed_fields["Job_Title"] == "Recruiter, AI Research"
    assert adapter.read_worksheet("Industry_Jobs").rows == [existing_job]
