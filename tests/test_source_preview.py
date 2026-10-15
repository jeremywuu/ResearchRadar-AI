from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from research_radar.collectors.base import SourceCollectionResult, SourceDescriptor
from research_radar.live_integration import RecommendationClassification
from research_radar.models import (
    ExtractionStatus,
    RetrievalMethod,
    SourceHealth,
    SourceVerificationStatus,
)
from research_radar.role_function import RoleDisplayGroup, RoleFunction
from research_radar.source_preview import (
    find_semantic_duplicate_conflicts,
    run_source_production_preview,
)
from research_radar.storage.durable_state import StateRestoreResult
from research_radar.storage.sheets import InMemorySheetsAdapter

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)


class PreviewSheetsAdapter(InMemorySheetsAdapter):
    settings = type(
        "Settings",
        (),
        {"environment": "live-pilot", "spreadsheet_id": "preview-only"},
    )()

    def get_spreadsheet_title(self) -> str:
        return "ResearchRadar AI — LIVE PILOT"


class CopyingStateReader:
    def __init__(self, source: Path) -> None:
        self.source = source
        self.commit_calls = 0

    def restore(self, target_dir: Path) -> StateRestoreResult:
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in ("jobs.json", "phd.json", "events.json", "source_metadata.json"):
            shutil.copy2(self.source / name, target_dir / name)
        return StateRestoreResult(
            available=True,
            snapshot_id="preview-baseline",
            current_generation=123,
            record_counts={"jobs": 0, "phd": 0, "events": 0},
        )

    def commit(self, *_args: object, **_kwargs: object) -> None:
        self.commit_calls += 1
        raise AssertionError("preview must never commit durable state")


class StaticPilotAdapter:
    def __init__(
        self,
        source_id: str,
        category: str,
        *,
        records: list[dict[str, object]] | None = None,
        profiles: list[dict[str, object]] | None = None,
    ) -> None:
        self.source = SourceDescriptor(
            source_id=source_id,
            organization=source_id,
            category=category,
            official_source_url=f"https://official.example/{source_id}",
            retrieval_url=f"https://official.example/{source_id}",
            retrieval_method=RetrievalMethod.OFFICIAL_HTML,
            verification_status=SourceVerificationStatus.VERIFIED_OFFICIAL,
        )
        self.records = records or []
        self.profiles = profiles or []

    def collect(self, *, observed_at: datetime) -> SourceCollectionResult:
        health = SourceHealth.SUCCESS if self.records else SourceHealth.SUCCESS_NO_MATCHES
        extraction = ExtractionStatus.SUCCESS if self.records else ExtractionStatus.NO_MATCHES
        return SourceCollectionResult(
            source=self.source,
            health=health,
            extraction_status=extraction,
            retrieved_at=observed_at,
            records=list(self.records),
            informational_profiles=list(self.profiles),
            records_fetched=max(1, len(self.records)),
            records_matched=max(1, len(self.records)),
            records_considered=max(1, len(self.records)),
            last_successful_retrieval_at=observed_at,
        )


def _empty_snapshot(path: Path) -> Path:
    path.mkdir(parents=True)
    for category in ("jobs", "phd", "events"):
        (path / f"{category}.json").write_text(
            json.dumps({"category": category, "summary": {}, "records": []}),
            encoding="utf-8",
        )
    (path / "source_metadata.json").write_text(
        json.dumps({"sources": {}, "pipelines": {}}), encoding="utf-8"
    )
    return path


def _job() -> dict[str, object]:
    return {
        "fictional": False,
        "title": "Software Engineer",
        "organization": "Paradromics",
        "official_job_id": "preview-job",
        "source_url": "https://paradromicsinc.applytojob.com/apply/preview-job",
        "official_source_url": "https://paradromics.com/careers/",
        "adapter_source_id": "paradromics_careers_pilot",
        "location": "Oakland, CA",
        "country": "United States",
        "region": "United States",
        "research_areas": ["Brain-computer interfaces", "Neural decoding"],
        "research_orientation": "Applied research",
        "education_requirement": "Other",
        "working_language": None,
        "skills": ["Python", "Neural data analysis"],
        "salary": {},
        "source_verification_status": "VERIFIED_OFFICIAL",
        "opportunity_status": "confirmed open",
        "source_type": "official_html_linked_ats",
        "source_evidence": ["Official company page links to posting"],
        "role_evidence": ["Develop BCI decoding algorithms with neural data."],
        "research_responsibility_evidence": ["Develop BCI decoding algorithms with neural data."],
        "extraction_method": "deterministic_html_patterns",
    }


def _paradromics_regression_jobs() -> list[dict[str, object]]:
    clinical = {
        **_job(),
        "title": "Field Clinical Specialist/Engineer",
        "official_job_id": "ujxQN2lhPz",
        "source_url": (
            "https://paradromicsinc.applytojob.com/apply/ujxQN2lhPz/"
            "Field-Clinical-Specialist-Engineer"
        ),
        "location": "Austin, TX",
        "role_evidence": [
            "Support implantable BCI use during surgical procedures and clinical study visits."
        ],
        "research_responsibility_evidence": [
            "Support implantable BCI use during surgical procedures and clinical study visits."
        ],
    }
    embedded = {
        **_job(),
        "title": "Embedded Software Engineer",
        "official_job_id": "u5hXN4N9ID",
        "source_url": (
            "https://paradromicsinc.applytojob.com/apply/u5hXN4N9ID/Embedded-Software-Engineer"
        ),
        "location": "Austin, TX",
        "research_areas": ["Computational neuroscience"],
        "role_evidence": [
            "Build low-latency embedded software for high-fidelity brain machine implants."
        ],
        "research_responsibility_evidence": [
            "Build low-latency embedded software for high-fidelity brain machine implants."
        ],
    }
    software = {
        **_job(),
        "official_job_id": "r7CgYCDBNk",
        "source_url": ("https://paradromicsinc.applytojob.com/apply/r7CgYCDBNk/Software-Engineer"),
        "role_evidence": [
            "Develop BCI data curation strategies and decoding algorithms; evaluate software "
            "with real neural data using Python, machine learning, and signal processing."
        ],
        "research_responsibility_evidence": [
            "Develop BCI data curation strategies and decoding algorithms; evaluate software "
            "with real neural data using Python, machine learning, and signal processing."
        ],
        "experience_requirement": "3+ years professional experience",
    }
    return [clinical, embedded, software]


def _event() -> dict[str, object]:
    return {
        "fictional": False,
        "title": "Reinforcement Learning and Decision Making 2027",
        "organization": "RLDM",
        "source_url": "https://rldm.org/call-for-abstracts-2027/",
        "official_source_url": "https://rldm.org/",
        "event_url": "https://rldm.org/",
        "adapter_source_id": "rldm_2027_official_pilot",
        "series_name": "RLDM",
        "edition_year": 2027,
        "location": "Paris",
        "country": "France",
        "region": "Europe",
        "starts_on": "2027-07-06",
        "ends_on": "2027-07-09",
        "submission_deadline": "2027-01-20",
        "submission_deadline_timezone": "AoE",
        "registration_deadline": None,
        "event_type": "academic conference",
        "research_areas": ["Decision neuroscience"],
        "opportunity_status": "confirmed upcoming",
        "source_verification_status": "VERIFIED_OFFICIAL",
        "source_type": "official_html",
        "source_evidence": ["Official RLDM 2027 page"],
        "extraction_method": "deterministic_html_patterns",
    }


def _adapters() -> dict[str, StaticPilotAdapter]:
    return {
        "paradromics_careers_pilot": StaticPilotAdapter(
            "paradromics_careers_pilot", "jobs", records=[_job()]
        ),
        "rldm_2027_official_pilot": StaticPilotAdapter(
            "rldm_2027_official_pilot", "events", records=[_event()]
        ),
        "cmu_neural_computation_profile": StaticPilotAdapter(
            "cmu_neural_computation_profile",
            "phd",
            profiles=[
                {
                    "profile_type": "PHD_PROGRAM_PROFILE",
                    "actionable_opportunity": False,
                    "admission_cycle": None,
                    "confirmed_recruitment_status": "UNKNOWN",
                    "official_deadline": None,
                    "general_deadline_information": "December 1",
                }
            ],
        ),
    }


def test_production_preview_restores_and_plans_without_cloud_or_sheets_writes(
    tmp_path: Path,
) -> None:
    reader = CopyingStateReader(_empty_snapshot(tmp_path / "baseline"))
    sheets = PreviewSheetsAdapter()

    result = run_source_production_preview(
        project_root=ROOT,
        output_dir=tmp_path / "preview",
        observed_at=NOW,
        reference_date=date(2026, 10, 15),
        state_reader=reader,
        sheets_adapter=sheets,
        adapters=_adapters(),
    )

    assert result.restored.snapshot_id == "preview-baseline"
    assert reader.commit_calls == 0
    assert sheets.write_operations == []
    assert len(result.pilot_changes) == 2
    assert result.duplicate_conflicts == ()
    assert result.report_path.is_file()
    assert result.weekly_brief_path.is_file()
    assert "Personal_Notes" not in result.weekly_brief_path.read_text(encoding="utf-8")
    decision = result.sheets_plan.preview.recommendations.decisions[0]
    assert decision.role_function is RoleFunction.RESEARCH_ADJACENT_ENGINEERING
    assert decision.display_group is RoleDisplayGroup.RESEARCH_ADJACENT
    assert decision.effective_classification in {
        RecommendationClassification.HIGH_PRIORITY,
        RecommendationClassification.RELEVANT,
    }


def test_three_collected_paradromics_jobs_remain_canonical_while_two_are_insertable(
    tmp_path: Path,
) -> None:
    reader = CopyingStateReader(_empty_snapshot(tmp_path / "baseline"))
    sheets = PreviewSheetsAdapter()
    adapters = {
        "paradromics_careers_pilot": StaticPilotAdapter(
            "paradromics_careers_pilot",
            "jobs",
            records=_paradromics_regression_jobs(),
        )
    }

    result = run_source_production_preview(
        project_root=ROOT,
        output_dir=tmp_path / "preview",
        observed_at=NOW,
        reference_date=date(2026, 10, 15),
        state_reader=reader,
        sheets_adapter=sheets,
        adapters=adapters,
    )

    collected = result.collection.execution.pipelines["jobs"].records
    inserts = result.sheets_plan.preview.workbook.plans["jobs"].inserts
    decisions = result.sheets_plan.preview.recommendations.by_record_id

    assert len(collected) == 3
    assert len(inserts) == 2
    assert {processed.opportunity.opportunity_id for processed in collected} == set(decisions)
    clinical_id = next(
        processed.opportunity.opportunity_id
        for processed in collected
        if processed.opportunity.title == "Field Clinical Specialist/Engineer"
    )
    assert decisions[clinical_id].role_function is RoleFunction.CLINICAL_IMPLEMENTATION
    assert (
        decisions[clinical_id].effective_classification is RecommendationClassification.NEEDS_REVIEW
    )
    assert clinical_id not in {operation.row["Record_ID"] for operation in inserts}
    assert reader.commit_calls == 0
    assert sheets.write_operations == []


def test_rldm_semantic_duplicate_with_different_id_is_reported(tmp_path: Path) -> None:
    previous = _empty_snapshot(tmp_path / "previous")
    pilot = _empty_snapshot(tmp_path / "pilot")
    existing = {
        "opportunity": {
            "opportunity_id": "event_old",
            "title": "RLDM 2027",
            "series_name": "RLDM",
            "edition_year": 2027,
        }
    }
    current = {
        "opportunity": {
            "opportunity_id": "event_new",
            "title": "Reinforcement Learning and Decision Making 2027",
            "series_name": "RLDM",
            "edition_year": 2027,
        }
    }
    (previous / "events.json").write_text(
        json.dumps({"category": "events", "records": [existing]}), encoding="utf-8"
    )
    (pilot / "events.json").write_text(
        json.dumps({"category": "events", "records": [current]}), encoding="utf-8"
    )

    conflicts = find_semantic_duplicate_conflicts(previous, pilot)

    assert conflicts == ("events:event_new duplicates existing event_old",)


def test_source_preview_cli_has_no_apply_option() -> None:
    from research_radar.cli import build_parser

    args = build_parser().parse_args(["source-preview", "--live", "--state-backend", "gcs"])

    assert not hasattr(args, "apply")


def test_production_workflow_schedule_remains_unchanged() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "weekly-monitoring.yml").read_text()
    )
    triggers = workflow[True]

    assert triggers["schedule"] == [{"cron": "0 9 * * 1", "timezone": "Europe/Brussels"}]
    assert "push" not in triggers
