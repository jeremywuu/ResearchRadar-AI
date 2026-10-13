from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from research_radar.collectors.base import SourceCollectionResult, SourceDescriptor
from research_radar.models import (
    ExtractionStatus,
    RetrievalMethod,
    SourceHealth,
    SourceVerificationStatus,
)
from research_radar.pipelines import run_jobs_pipeline
from research_radar.storage.durable_state import (
    LocalFilesystemStateBackend,
    StateCommitRequest,
)
from research_radar.storage.sheets import InMemorySheetsAdapter
from research_radar.weekly import run_weekly_monitor

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 12, 7, 0, tzinfo=UTC)


class PilotMemoryAdapter(InMemorySheetsAdapter):
    settings = type(
        "Settings",
        (),
        {"environment": "live-pilot", "spreadsheet_id": "pilot-id"},
    )()

    def get_spreadsheet_title(self) -> str:
        return "ResearchRadar AI — LIVE PILOT"


class StaticAdapter:
    def __init__(
        self,
        source_id: str,
        category: str,
        health: SourceHealth,
        records: list[dict[str, object]] | None = None,
    ) -> None:
        self.source = SourceDescriptor(
            source_id=source_id,
            organization=f"Official {category}",
            category=category,
            official_source_url=f"https://official.example/{source_id}",
            retrieval_url=f"https://official.example/{source_id}",
            retrieval_method=RetrievalMethod.PUBLIC_API,
            verification_status=SourceVerificationStatus.VERIFIED_OFFICIAL,
        )
        self.health = health
        self.records = records or []

    def collect(self, *, observed_at: datetime) -> SourceCollectionResult:
        extraction = (
            ExtractionStatus.SUCCESS
            if self.records
            else ExtractionStatus.NO_MATCHES
            if self.health is SourceHealth.SUCCESS_NO_MATCHES
            else ExtractionStatus.FAILED
        )
        return SourceCollectionResult(
            source=self.source,
            health=self.health,
            extraction_status=extraction,
            retrieved_at=observed_at,
            records=list(self.records),
            records_fetched=len(self.records),
            errors=[]
            if self.health in {SourceHealth.SUCCESS, SourceHealth.SUCCESS_NO_MATCHES}
            else ["blocked"],
        )


def _job_raw() -> dict[str, object]:
    return {
        "fictional": False,
        "title": "Research Scientist, Human Behavior",
        "organization": "Official Cognitive Research Company",
        "official_job_id": "WEEKLY-1",
        "source_url": "https://official.example/jobs/WEEKLY-1",
        "official_source_url": "https://official.example/jobs",
        "adapter_source_id": "official_jobs",
        "location": "London, United Kingdom",
        "country": "United Kingdom",
        "research_areas": [
            "Computational cognitive neuroscience",
            "Computational models of human behavior",
        ],
        "research_orientation": "Research-oriented",
        "education_requirement": "PhD Preferred",
        "working_language": None,
        "salary": {},
        "source_verification_status": "VERIFIED_OFFICIAL",
        "source_type": "official_api",
        "source_evidence": ["Official job ID WEEKLY-1"],
        "extraction_method": "structured_api",
        "opportunity_status": "confirmed open",
    }


def _adapters(*, all_failed: bool = False) -> dict[str, StaticAdapter]:
    failed = SourceHealth.FAILED if all_failed else SourceHealth.SUCCESS
    return {
        "official_jobs": StaticAdapter(
            "official_jobs", "jobs", failed, [] if all_failed else [_job_raw()]
        ),
        "official_phd": StaticAdapter(
            "official_phd",
            "phd",
            SourceHealth.FAILED if all_failed else SourceHealth.BLOCKED,
        ),
        "official_events": StaticAdapter(
            "official_events",
            "events",
            SourceHealth.FAILED if all_failed else SourceHealth.SUCCESS_NO_MATCHES,
        ),
    }


def test_weekly_run_reports_partial_success_without_writes_or_private_notes(tmp_path: Path) -> None:
    job = run_jobs_pipeline([_job_raw()], config_dir=ROOT / "config", observed_at=NOW).records[0]
    adapter = PilotMemoryAdapter(
        {
            "My_Feedback": [
                {
                    "Record_ID": job.opportunity.opportunity_id,
                    "Preference": "Interested",
                    "Saved": True,
                    "Hidden": False,
                    "Personal_Notes": "private note must not appear",
                    "Feedback_Updated_At": "",
                }
            ]
        }
    )

    result = run_weekly_monitor(
        project_root=ROOT,
        output_dir=tmp_path / "run",
        state_dir=tmp_path / "missing-state",
        observed_at=NOW,
        reference_date=date(2026, 10, 12),
        adapter=adapter,
        adapters=_adapters(),
    )
    report = result.report_path.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert result.source_successes == 2
    assert result.source_issues == 1
    assert result.durable_baseline_available is False
    assert "Durable baseline available: no" in report
    assert "Official Cognitive Research Company" in report
    assert "https://official.example/jobs" in report
    assert "official_phd`: BLOCKED" in report
    assert "private note must not appear" not in report
    assert adapter.write_operations == []
    assert result.plan.preview.feedback.feedback_by_id[job.opportunity.opportunity_id].saved is True


def test_weekly_run_fails_only_when_no_source_succeeds(tmp_path: Path) -> None:
    result = run_weekly_monitor(
        project_root=ROOT,
        output_dir=tmp_path / "run",
        state_dir=tmp_path / "missing-state",
        observed_at=NOW,
        reference_date=date(2026, 10, 12),
        adapter=PilotMemoryAdapter(),
        adapters=_adapters(all_failed=True),
    )

    assert result.exit_code == 1
    assert result.source_successes == 0
    assert result.report_path.is_file()
    assert "Google Sheets writes: disabled" in result.report_path.read_text(encoding="utf-8")


def test_weekly_records_keep_stable_ids_without_durable_state(tmp_path: Path) -> None:
    first = run_weekly_monitor(
        project_root=ROOT,
        output_dir=tmp_path / "first",
        state_dir=tmp_path / "missing-one",
        observed_at=NOW,
        reference_date=date(2026, 10, 12),
        adapter=PilotMemoryAdapter(),
        adapters=_adapters(),
    )
    second = run_weekly_monitor(
        project_root=ROOT,
        output_dir=tmp_path / "second",
        state_dir=tmp_path / "missing-two",
        observed_at=NOW,
        reference_date=date(2026, 10, 12),
        adapter=PilotMemoryAdapter(),
        adapters=_adapters(),
    )

    first_id = first.plan.preview.execution.pipelines["jobs"].records[0].opportunity.opportunity_id
    second_id = (
        second.plan.preview.execution.pipelines["jobs"].records[0].opportunity.opportunity_id
    )
    assert first_id == second_id


def test_empty_durable_backend_enters_bootstrap_without_committing(tmp_path: Path) -> None:
    result = run_weekly_monitor(
        project_root=ROOT,
        output_dir=tmp_path / "run",
        state_dir=tmp_path / "legacy",
        observed_at=NOW,
        reference_date=date(2026, 10, 12),
        adapter=PilotMemoryAdapter(),
        adapters=_adapters(),
        state_backend=LocalFilesystemStateBackend(tmp_path / "durable"),
        run_id="cloud-run-1",
    )

    assert result.durable_baseline_available is False
    assert result.state_restore is not None and result.state_restore.available is False
    assert result.state_commit is None
    assert not (tmp_path / "durable" / "current.json").exists()


def test_existing_durable_state_is_restored_reconciled_and_committed(tmp_path: Path) -> None:
    initial = run_weekly_monitor(
        project_root=ROOT,
        output_dir=tmp_path / "initial",
        state_dir=tmp_path / "missing",
        observed_at=NOW,
        reference_date=date(2026, 10, 12),
        adapter=PilotMemoryAdapter(),
        adapters=_adapters(),
    )
    backend = LocalFilesystemStateBackend(tmp_path / "durable")
    backend.commit(
        initial.snapshot_dir,
        StateCommitRequest(
            run_id="bootstrap-1",
            committed_at=NOW,
            preference_configuration_hash=initial.plan.preview.preference_configuration_hash,
            source_health={"official_jobs": "SUCCESS"},
            bootstrap=True,
        ),
        expected_current_generation=None,
    )
    later = datetime(2026, 10, 19, 7, 0, tzinfo=UTC)

    result = run_weekly_monitor(
        project_root=ROOT,
        output_dir=tmp_path / "second",
        state_dir=tmp_path / "unused",
        observed_at=later,
        reference_date=date(2026, 10, 19),
        adapter=PilotMemoryAdapter(),
        adapters=_adapters(),
        state_backend=backend,
        run_id="cloud-run-2",
    )

    assert result.durable_baseline_available is True
    assert result.state_commit is not None
    assert result.state_commit.snapshot_id == "cloud-run-2"
    assert result.plan.preview.workbook.plans["jobs"].insert_count == 1


def test_weekly_deadlines_are_semantically_labeled_without_alias_duplicates(
    tmp_path: Path,
) -> None:
    event = {
        "fictional": False,
        "title": "Cognitive Conference 2026",
        "organization": "Official Event",
        "source_url": "https://official.example/event",
        "official_source_url": "https://official.example/event",
        "adapter_source_id": "official_events",
        "series_name": "Cognitive Conference",
        "edition_year": 2026,
        "event_type": "academic conference",
        "starts_on": "2026-11-01",
        "ends_on": "2026-11-03",
        "submission_deadline": "2026-10-18",
        "workshop_submission_deadline": "2026-10-18",
        "research_areas": ["Computational cognitive neuroscience"],
        "source_verification_status": "VERIFIED_OFFICIAL",
        "source_type": "official_html",
        "source_evidence": ["Official dates"],
        "extraction_method": "html",
        "opportunity_status": "confirmed upcoming",
        "country": "Belgium",
    }
    adapters = _adapters()
    adapters["official_events"] = StaticAdapter(
        "official_events", "events", SourceHealth.SUCCESS, [event]
    )
    result = run_weekly_monitor(
        project_root=ROOT,
        output_dir=tmp_path / "run",
        state_dir=tmp_path / "missing",
        observed_at=NOW,
        reference_date=date(2026, 10, 12),
        adapter=PilotMemoryAdapter(),
        adapters=adapters,
    )
    report = result.report_path.read_text()

    assert report.count("Abstract submission deadline: `2026-10-18`") == 1
    assert report.count("Workshop proposal deadline: `2026-10-18`") == 1
    assert "Conference start: `2026-11-01`" in report
    assert "Conference end: `2026-11-03`" in report


def test_weekly_workflow_is_manual_only_free_compatible_and_read_only() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "weekly-monitoring.yml"
    workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    triggers = workflow["on"]
    monitor = workflow["jobs"]["monitor"]
    workflow_text = workflow_path.read_text(encoding="utf-8")

    assert triggers == {"workflow_dispatch": ""}
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    assert workflow["jobs"]["test"]["timeout-minutes"] == "15"
    assert monitor["timeout-minutes"] == "35"
    assert monitor["permissions"] == {"contents": "read", "id-token": "write"}
    assert "environment" not in monitor
    assert monitor["env"]["RESEARCH_RADAR_SHEETS_ENV"] == "live-pilot"
    assert monitor["env"]["RESEARCH_RADAR_DATA_MODE"] == "live"
    assert monitor["env"]["RESEARCH_RADAR_GOOGLE_READ_ONLY"] == "1"
    assert "--apply" not in workflow_text
    assert "GOOGLE_SPREADSHEET_ID" not in workflow_text
    assert "jeremywuu/ResearchRadar-AI" in workflow_text
    assert "refs/heads/main" in workflow_text
    assert "weekly-monitoring.yml@refs/heads/main" in workflow_text
    assert monitor["steps"][-1]["with"]["retention-days"] == "14"


def test_deferred_weekly_schedule_remains_documented() -> None:
    setup_guide = (ROOT / "docs" / "GITHUB_ACTIONS_SETUP.md").read_text(encoding="utf-8")

    assert 'cron: "0 9 * * 1"' in setup_guide
    assert 'timezone: "Europe/Brussels"' in setup_guide
    assert "first deployment is deliberately manual-only" in setup_guide


def test_wif_plan_uses_numeric_ids_and_exact_workflow_claim() -> None:
    plan = (ROOT / "docs" / "GOOGLE_WIF_SETUP.md").read_text(encoding="utf-8")

    assert "attribute.repository_id=='1416626708'" in plan
    assert "attribute.repository_owner_id=='213313923'" in plan
    assert "attribute.ref=='refs/heads/main'" in plan
    assert "attribute.workflow_ref=='jeremywuu/ResearchRadar-AI/.github/workflows/" in plan
    assert "attribute.job_workflow_ref=" not in plan
    assert "roles/iam.workloadIdentityUser" in plan
    assert "researchradar-pool/*" in plan
    assert "Do not bind" in plan
