from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
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
    DurableStateError,
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
        "role_evidence": ["Conduct research and design experiments to analyze human behavior."],
        "research_responsibility_evidence": [
            "Conduct research and design experiments to analyze human behavior."
        ],
        "extraction_method": "structured_api",
        "opportunity_status": "confirmed open",
    }


def _phd_raw(
    *,
    official_id: str,
    target_cycle: str | None,
    status: str,
) -> dict[str, object]:
    return {
        "fictional": False,
        "title": f"Cognitive Neuroscience PhD {official_id}",
        "organization": "Official University",
        "official_opportunity_id": official_id,
        "source_url": f"https://official.example/phd/{official_id}",
        "official_source_url": "https://official.example/phd",
        "adapter_source_id": "official_phd",
        "target_cycle": target_cycle,
        "opportunity_type": "centralized phd program admission",
        "research_areas": ["Computational cognitive neuroscience"],
        "source_verification_status": "VERIFIED_OFFICIAL",
        "source_type": "official_html",
        "source_evidence": [f"Official admission cycle: {target_cycle or 'unknown'}"],
        "extraction_method": "html",
        "opportunity_status": status,
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
    assert "New-to-Radar opportunities (first verified observation by ResearchRadar)" in report
    assert "New opportunities:" not in report
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


def test_weekly_role_gate_places_clinical_adjacent_and_platform_roles_separately(
    tmp_path: Path,
) -> None:
    direct = _job_raw()
    clinical = dict(_job_raw())
    clinical.update(
        {
            "official_job_id": "CLINICAL-1",
            "source_url": "https://official.example/jobs/CLINICAL-1",
            "title": "Field Clinical Specialist",
            "role_evidence": ["Support clinical sites during surgical patient visits."],
            "research_responsibility_evidence": [
                "Support clinical sites during surgical patient visits."
            ],
        }
    )
    adjacent = dict(_job_raw())
    adjacent.update(
        {
            "official_job_id": "DECODING-1",
            "source_url": "https://official.example/jobs/DECODING-1",
            "title": "Neural Decoding Engineer",
            "role_evidence": ["Develop decoding algorithms and evaluate neural data software."],
            "research_responsibility_evidence": [
                "Develop decoding algorithms and evaluate neural data software."
            ],
            "experience_requirement_detail": "3+ years of relevant professional experience",
        }
    )
    platform = dict(_job_raw())
    platform.update(
        {
            "official_job_id": "PLATFORM-1",
            "source_url": "https://official.example/jobs/PLATFORM-1",
            "title": "Embedded Firmware Engineer",
            "role_evidence": ["Build embedded firmware and low-latency hardware interfaces."],
            "research_responsibility_evidence": [
                "Build embedded firmware and low-latency hardware interfaces."
            ],
        }
    )
    adapters = _adapters()
    adapters["official_jobs"] = StaticAdapter(
        "official_jobs", "jobs", SourceHealth.SUCCESS, [direct, clinical, adjacent, platform]
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
    report = result.report_path.read_text(encoding="utf-8")

    top = report.split("## B. Top Research Matches", 1)[1].split("## C.", 1)[0]
    adjacent_section = report.split("## G. NeuroAI / BCI Research-Adjacent Roles", 1)[1].split(
        "## H.", 1
    )[0]
    platform_section = report.split("## I. Transferable Technical Roles", 1)[1].split("## J.", 1)[0]
    review_section = report.split("## J. Needs Review", 1)[1].split("## K.", 1)[0]
    assert "Research Scientist, Human Behavior" in top
    assert "Field Clinical Specialist" not in top
    assert "Neural Decoding Engineer" in adjacent_section
    assert "experience_requirement=3+ years of relevant professional experience" in adjacent_section
    assert "immediate_application_readiness=unknown" in adjacent_section
    assert "Embedded Firmware Engineer" in platform_section
    assert "Field Clinical Specialist" in review_section


def test_weekly_distinguishes_radar_discovery_from_official_posting_date(tmp_path: Path) -> None:
    baseline_adapters = _adapters()
    baseline_adapters["official_jobs"] = StaticAdapter(
        "official_jobs", "jobs", SourceHealth.SUCCESS_NO_MATCHES
    )
    baseline = run_weekly_monitor(
        project_root=ROOT,
        output_dir=tmp_path / "baseline-run",
        state_dir=tmp_path / "missing",
        observed_at=NOW,
        reference_date=date(2026, 10, 12),
        adapter=PilotMemoryAdapter(),
        adapters=baseline_adapters,
    )
    backend = LocalFilesystemStateBackend(tmp_path / "durable")
    backend.commit(
        baseline.snapshot_dir,
        StateCommitRequest(
            run_id="empty-baseline",
            committed_at=NOW,
            preference_configuration_hash=baseline.plan.preview.preference_configuration_hash,
            source_health={"official_jobs": "SUCCESS_NO_MATCHES"},
            bootstrap=True,
        ),
        expected_current_generation=None,
    )
    recent = _job_raw()
    recent["published_at"] = "2026-10-10T12:00:00Z"
    unknown = dict(_job_raw())
    unknown.update(
        {
            "official_job_id": "WEEKLY-UNKNOWN-DATE",
            "source_url": "https://official.example/jobs/WEEKLY-UNKNOWN-DATE",
            "title": "Research Scientist, Decision Neuroscience",
        }
    )
    older = dict(_job_raw())
    older.update(
        {
            "official_job_id": "WEEKLY-OLDER-POST",
            "source_url": "https://official.example/jobs/WEEKLY-OLDER-POST",
            "title": "Research Scientist, Cognitive Modeling",
            "posted_at": "2026-06-01",
        }
    )
    adapters = _adapters()
    adapters["official_jobs"] = StaticAdapter(
        "official_jobs", "jobs", SourceHealth.SUCCESS, [recent, unknown, older]
    )

    result = run_weekly_monitor(
        project_root=ROOT,
        output_dir=tmp_path / "current-run",
        state_dir=tmp_path / "unused",
        observed_at=NOW,
        reference_date=date(2026, 10, 12),
        adapter=PilotMemoryAdapter(),
        adapters=adapters,
        state_backend=backend,
        run_id="discovery-run",
    )
    report = result.report_path.read_text(encoding="utf-8")

    assert "New-to-Radar opportunities (first verified observation by ResearchRadar): 3" in report
    assert "Officially newly posted jobs: 1" in report
    assert "New-to-Radar jobs with unknown official posting date: 1" in report
    assert "radar_status=NEW_TO_RADAR; posting_status=NEWLY_POSTED (2026-10-10)" in report
    assert "radar_status=NEW_TO_RADAR; posting_status=UNKNOWN_POSTING_DATE" in report
    assert "radar_status=NEW_TO_RADAR; posting_status=OFFICIAL_POSTING_DATE (2026-06-01)" in report
    assert "first_seen_at" not in report.casefold()


def test_weekly_groups_phd_records_by_evidenced_admission_cycle(tmp_path: Path) -> None:
    adapters = _adapters()
    adapters["official_phd"] = StaticAdapter(
        "official_phd",
        "phd",
        SourceHealth.SUCCESS,
        [
            _phd_raw(
                official_id="FALL-2028",
                target_cycle="Fall 2028",
                status="confirmed open",
            ),
            _phd_raw(
                official_id="FALL-2027",
                target_cycle="Fall 2027",
                status="confirmed open",
            ),
            _phd_raw(
                official_id="UNKNOWN-CYCLE",
                target_cycle=None,
                status="potential signal",
            ),
            _phd_raw(
                official_id="FALL-2028-UNCONFIRMED",
                target_cycle="Fall 2028",
                status="potential signal",
            ),
        ],
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
    report = result.report_path.read_text(encoding="utf-8")
    confirmed_2028 = report.split("## C. Confirmed Fall 2028 Openings", 1)[1].split("## D.", 1)[0]
    watch = report.split("## D. Fall 2028 PhD Watch / Admission Cycle Unconfirmed", 1)[1].split(
        "## E.", 1
    )[0]
    other = report.split("## E. Other Confirmed Admission Cycles", 1)[1].split("## F.", 1)[0]
    profiles = report.split("## F. Informational Programme Profiles", 1)[1].split("## G.", 1)[0]

    assert "FALL-2028" in confirmed_2028
    assert "FALL-2028-UNCONFIRMED" not in confirmed_2028
    assert "FALL-2027" not in confirmed_2028
    assert "UNKNOWN-CYCLE" in watch
    assert "FALL-2028-UNCONFIRMED" in watch
    assert "FALL-2027" in other
    assert "Informational profiles are not ordinary PhD opportunities" in profiles


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


def test_explicit_cloud_state_fails_closed_before_collection(tmp_path: Path) -> None:
    class CollectionMustNotRun:
        def collect(self, *, observed_at: datetime) -> SourceCollectionResult:
            pytest.fail("collection must not run without the authoritative baseline")

    with pytest.raises(DurableStateError, match="authoritative durable baseline"):
        run_weekly_monitor(
            project_root=ROOT,
            output_dir=tmp_path / "run",
            state_dir=tmp_path / "legacy",
            observed_at=NOW,
            reference_date=date(2026, 10, 12),
            adapter=PilotMemoryAdapter(),
            adapters={"must_not_run": CollectionMustNotRun()},
            state_backend=LocalFilesystemStateBackend(tmp_path / "empty-durable"),
            require_durable_baseline=True,
            run_id="cloud-run-1",
        )


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
    report = result.report_path.read_text(encoding="utf-8")
    assert "Restored snapshot ID: `bootstrap-1`" in report
    assert "Restored records: jobs=1; phd=0; events=0; total=1" in report
    assert "GCS/durable-state commit: committed `cloud-run-2`" in report
    assert "Observation-only changes:" in report
    assert "Not observed opportunities:" in report


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


def test_weekly_workflow_has_approved_schedule_and_remains_read_only() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "weekly-monitoring.yml"
    workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    triggers = workflow["on"]
    monitor = workflow["jobs"]["monitor"]
    workflow_text = workflow_path.read_text(encoding="utf-8")

    assert triggers == {
        "workflow_dispatch": "",
        "schedule": [{"cron": "0 9 * * 1", "timezone": "Europe/Brussels"}],
    }
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    assert workflow["jobs"]["test"]["runs-on"] == "ubuntu-24.04"
    assert monitor["runs-on"] == "ubuntu-24.04"
    assert workflow["jobs"]["test"]["timeout-minutes"] == "15"
    assert monitor["timeout-minutes"] == "35"
    assert monitor["permissions"] == {"contents": "read", "id-token": "write"}
    assert "environment" not in monitor
    assert monitor["env"]["RESEARCH_RADAR_SHEETS_ENV"] == "live-pilot"
    assert monitor["env"]["RESEARCH_RADAR_DATA_MODE"] == "live"
    assert monitor["env"]["RESEARCH_RADAR_GOOGLE_READ_ONLY"] == "1"
    assert monitor["env"]["RESEARCH_RADAR_RESEARCH_SOURCES_ENABLED"] == (
        "${{ vars.RESEARCH_RADAR_RESEARCH_SOURCES_ENABLED }}"
    )
    assert monitor["env"]["RESEARCH_RADAR_GCS_BUCKET"] == ("${{ vars.RESEARCH_RADAR_GCS_BUCKET }}")
    assert monitor["env"]["RESEARCH_RADAR_GCS_PREFIX"] == ("${{ vars.RESEARCH_RADAR_GCS_PREFIX }}")
    assert 'python -m pip install -e ".[sheets,gcs]"' in workflow_text
    assert "--state-backend gcs" in workflow_text
    assert "--apply" not in workflow_text
    assert "GOOGLE_SPREADSHEET_ID" not in workflow_text
    assert "jeremywuu/ResearchRadar-AI" in workflow_text
    assert "refs/heads/main" in workflow_text
    assert "weekly-monitoring.yml@refs/heads/main" in workflow_text
    assert "actions/upload-artifact@v7" in workflow_text
    assert "actions/upload-artifact@v4" not in workflow_text
    assert monitor["steps"][-1]["with"]["retention-days"] == "14"


def test_active_weekly_schedule_is_documented() -> None:
    setup_guide = (ROOT / "docs" / "GITHUB_ACTIONS_SETUP.md").read_text(encoding="utf-8")

    assert 'cron: "0 9 * * 1"' in setup_guide
    assert 'timezone: "Europe/Brussels"' in setup_guide
    assert "scheduled production monitoring is active" in setup_guide


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
