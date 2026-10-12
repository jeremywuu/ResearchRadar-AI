from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from research_radar.config import load_career_preferences
from research_radar.live_integration import (
    RecommendationClassification,
    audit_provenance,
    build_combined_live_snapshot,
    classify_recommendations,
    prepare_incremental_live_sync,
    prepare_live_sheets_preview,
)
from research_radar.models import (
    DomainFitClassification,
    ExecutionReport,
    PreferenceFeedback,
)
from research_radar.pipelines import run_events_pipeline, run_jobs_pipeline, run_phd_pipeline
from research_radar.storage.json_store import JsonOutputStore
from research_radar.storage.sheets import InMemorySheetsAdapter, sheet_rows_from_report

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def job_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "fictional": False,
        "title": "Research Engineer",
        "organization": "Official Research Company",
        "official_job_id": "JOB-1",
        "source_url": "https://jobs.official.example/JOB-1",
        "official_source_url": "https://official.example/careers",
        "adapter_source_id": "official_jobs",
        "location": "Brussels, Belgium",
        "country": "Belgium",
        "research_areas": ["Machine learning"],
        "skills": ["Python", "Machine learning"],
        "research_orientation": "Research-oriented",
        "education_requirement": "PhD Required",
        "working_language": None,
        "salary": {},
        "source_evidence": ["Official job ID JOB-1", "Title: Research Engineer"],
        "source_verification_status": "VERIFIED_OFFICIAL",
        "source_type": "official_fixture",
        "extraction_method": "deterministic_test_parser",
        "opportunity_status": "confirmed open",
    }
    record.update(overrides)
    return record


def _decision(raw: dict[str, object]):
    report = run_jobs_pipeline([raw], config_dir=ROOT / "config", observed_at=NOW)
    execution = ExecutionReport(pipelines={"jobs": report})
    provenance = audit_provenance(execution)
    rules = load_career_preferences(ROOT / "config" / "career_preferences.yaml")[
        "recommendation_rules"
    ]
    return report.records[0], classify_recommendations(execution, provenance, rules).decisions[0]


def test_cognitive_neuroscience_outranks_unrelated_ai_algorithm_role() -> None:
    cognitive, _ = _decision(
        job_record(
            title="Computational Cognitive Neuroscience Research Scientist",
            research_areas=[
                "Computational cognitive neuroscience",
                "Neural representations",
                "Cognitive modeling",
            ],
            skills=["fMRI", "Computational modeling", "RSA"],
        )
    )
    generic, _ = _decision(
        job_record(
            official_job_id="JOB-2",
            source_url="https://jobs.official.example/JOB-2",
            title="Research Engineer, Foundation Models",
            research_areas=["Machine learning", "Artificial intelligence"],
        )
    )

    assert cognitive.score.domain_fit is DomainFitClassification.CORE_DOMAIN_FIT
    assert cognitive.score.components["methodological_fit"] == 100
    assert cognitive.score.final_score > generic.score.final_score


def test_generic_research_engineer_and_cybersecurity_rl_are_not_core_fit() -> None:
    generic, generic_decision = _decision(job_record())
    cyber, cyber_decision = _decision(
        job_record(
            official_job_id="JOB-CYBER",
            source_url="https://jobs.official.example/JOB-CYBER",
            title="Research Engineer, Cybersecurity RL",
            research_areas=["Machine learning", "Reinforcement learning"],
        )
    )

    assert generic.score.domain_fit is DomainFitClassification.TECHNICAL_TRANSFERABLE
    assert generic_decision.classification is RecommendationClassification.NEEDS_REVIEW
    assert cyber.score.domain_fit is DomainFitClassification.LOW_DOMAIN_FIT
    assert cyber_decision.classification is RecommendationClassification.LOW_PRIORITY


def test_neuroai_and_neural_decoding_can_be_high_priority() -> None:
    processed, decision = _decision(
        job_record(
            title="Research Scientist, NeuroAI and Neural Decoding",
            research_areas=[
                "NeuroAI and brain-model alignment",
                "Neural encoding and decoding",
            ],
            skills=["Neural data analysis", "Machine learning"],
        )
    )

    assert processed.score.domain_fit is DomainFitClassification.CORE_DOMAIN_FIT
    assert decision.classification is RecommendationClassification.HIGH_PRIORITY


def test_transferable_phd_required_role_remains_discoverable_future_target() -> None:
    processed, decision = _decision(job_record())

    assert processed.opportunity.classification.value == "FUTURE_CAREER_TARGET"
    assert processed.excluded is False
    assert decision.classification is RecommendationClassification.NEEDS_REVIEW


def test_event_scoring_uses_scientific_fit_not_general_ai_prestige() -> None:
    common = {
        "fictional": True,
        "organization": "Fictional Society",
        "event_type": "Academic conference",
        "country": "Belgium",
        "region": "Europe",
        "location": "Brussels",
        "starts_on": "2027-05-01",
        "ends_on": "2027-05-03",
        "submission_deadline": "2027-01-01",
        "source_verification_status": "VERIFIED_OFFICIAL",
    }
    records = [
        common
        | {
            "title": "Computational Cognitive Neuroscience Conference",
            "series_name": "CCN",
            "edition_year": 2027,
            "source_url": "https://ccn.example/2027",
            "official_url": "https://ccn.example/2027",
            "research_areas": ["Computational cognitive neuroscience", "Cognitive modeling"],
        },
        common
        | {
            "title": "General AI Conference",
            "series_name": "Prestigious General AI",
            "edition_year": 2027,
            "source_url": "https://ai.example/2027",
            "official_url": "https://ai.example/2027",
            "research_areas": ["Artificial intelligence", "Machine learning"],
        },
    ]
    report = run_events_pipeline(
        records,
        config_dir=ROOT / "config",
        observed_at=NOW,
        reference_date=NOW.date(),
    )

    scores = {item.opportunity.series_name: item.score.final_score for item in report.records}
    assert scores["CCN"] > scores["Prestigious General AI"]


def test_preference_revision_changes_plan_fingerprint_without_source_history_or_feedback_loss(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    shutil.copytree(ROOT / "config", project_root / "config")
    live_dir = tmp_path / "live"
    raw = job_record(
        title="Computational Cognitive Neuroscience Research Scientist",
        research_areas=["Computational cognitive neuroscience", "Neural representations"],
    )
    report = run_jobs_pipeline([raw], config_dir=project_root / "config", observed_at=NOW)
    record_id = report.records[0].opportunity.opportunity_id
    JsonOutputStore(live_dir).write(report)
    for category, pipeline in {
        "phd": run_phd_pipeline([], config_dir=project_root / "config", observed_at=NOW),
        "events": run_events_pipeline(
            [],
            config_dir=project_root / "config",
            observed_at=NOW,
            reference_date=NOW.date(),
        ),
    }.items():
        JsonOutputStore(live_dir).write(pipeline)
        assert pipeline.category == category
    metadata = {
        "sources": {
            "official_jobs": {
                "health": "SUCCESS",
                "retrieved_at": NOW.isoformat(),
                "records_fetched": 1,
                "records_considered": 1,
                "records": [raw],
            }
        },
        "pipelines": {"jobs": {"records_accepted": 1}},
    }
    (live_dir / "source_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    initial = prepare_live_sheets_preview(
        project_root=project_root,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 12),
    )
    feedback_row = {
        "Record_ID": record_id,
        "Preference": "Interested",
        "Saved": True,
        "Hidden": False,
        "Personal_Notes": "Preserve exactly",
        "Updated_At": "",
    }

    class PilotAdapter(InMemorySheetsAdapter):
        settings = type(
            "Settings", (), {"environment": "live-pilot", "spreadsheet_id": "pilot-id"}
        )()

        def get_spreadsheet_title(self) -> str:
            return "ResearchRadar AI — LIVE PILOT"

    adapter = PilotAdapter(
        {
            "Industry_Jobs": [initial.workbook.plans["jobs"].inserts[0].row],
            "My_Feedback": [feedback_row],
        }
    )
    first = prepare_incremental_live_sync(
        project_root=project_root,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 12),
        adapter=adapter,
    )
    interests_path = project_root / "config" / "research_interests.yaml"
    interests = yaml.safe_load(interests_path.read_text(encoding="utf-8"))
    interests["profile_revision"] = "test-recalibration-v2"
    interests["research_relevance"]["tier_scores"]["core"] = 95
    interests_path.write_text(yaml.safe_dump(interests, sort_keys=False), encoding="utf-8")
    second = prepare_incremental_live_sync(
        project_root=project_root,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=date(2026, 10, 12),
        adapter=adapter,
    )

    assert first.plan_fingerprint != second.plan_fingerprint
    assert report.records[0].opportunity.first_seen_at == NOW
    assert report.records[0].opportunity.last_seen_at == NOW
    assert report.records[0].opportunity.content_updated_at == NOW
    feedback = second.preview.feedback.feedback_by_id[record_id]
    assert feedback.preference is PreferenceFeedback.INTERESTED
    assert feedback.saved is True
    assert feedback.hidden is False
    assert feedback.notes == "Preserve exactly"
    assert second.preview.workbook.plans["jobs"].change_log_rows == []


def test_existing_low_priority_row_receives_score_refresh_without_source_history_change(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    shutil.copytree(ROOT / "config", project_root / "config")
    live_dir = tmp_path / "live"
    raw = job_record(
        title="Sales Lead",
        research_areas=["Artificial intelligence"],
        research_orientation="Commercial / operational",
        education_requirement="Unknown",
    )
    report = run_jobs_pipeline([raw], config_dir=project_root / "config", observed_at=NOW)
    record_id = report.records[0].opportunity.opportunity_id
    _, rows = sheet_rows_from_report(report)
    existing = dict(rows[0])
    existing.update(
        {
            "Research_Relevance": 90.0,
            "PhD_Leverage": 90.0,
            "Skills_Career_Fit": 90.0,
            "Overall_Priority_Score": 90.0,
            "First_Seen": "2026-09-01T09:00:00+00:00",
            "Last_Seen": "2026-09-02T09:00:00+00:00",
        }
    )
    JsonOutputStore(live_dir).write(report)
    JsonOutputStore(live_dir).write(
        run_phd_pipeline([], config_dir=project_root / "config", observed_at=NOW)
    )
    JsonOutputStore(live_dir).write(
        run_events_pipeline(
            [],
            config_dir=project_root / "config",
            observed_at=NOW,
            reference_date=NOW.date(),
        )
    )
    metadata = {
        "sources": {
            "official_jobs": {
                "health": "SUCCESS",
                "retrieved_at": NOW.isoformat(),
                "records_fetched": 1,
                "records_considered": 1,
                "records": [raw],
            }
        },
        "pipelines": {"jobs": {"records_accepted": 1}},
    }
    (live_dir / "source_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    class PilotAdapter(InMemorySheetsAdapter):
        settings = type(
            "Settings", (), {"environment": "live-pilot", "spreadsheet_id": "pilot-id"}
        )()

        def get_spreadsheet_title(self) -> str:
            return "ResearchRadar AI — LIVE PILOT"

    feedback_row = {
        "Record_ID": record_id,
        "Preference": "Interested",
        "Saved": True,
        "Hidden": False,
        "Personal_Notes": "Preserve exactly",
        "Updated_At": "",
    }
    adapter = PilotAdapter({"Industry_Jobs": [existing], "My_Feedback": [feedback_row]})

    preview = prepare_live_sheets_preview(
        project_root=project_root,
        live_data_dir=live_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=NOW.date(),
        adapter=adapter,
    )

    decision = next(
        item for item in preview.recommendations.decisions if item.record_id == record_id
    )
    assert decision.classification is RecommendationClassification.LOW_PRIORITY
    plan = preview.workbook.plans["jobs"]
    assert plan.insert_count == 0
    assert plan.update_count == 1
    changed = plan.updates[0].changed_fields
    assert "Research_Relevance" in changed
    assert "Overall_Priority_Score" in changed
    assert "First_Seen" not in changed
    assert "Last_Seen" not in changed
    assert "Opportunity_Status" not in changed
    assert plan.change_log_rows == []
    feedback = preview.feedback.feedback_by_id[record_id]
    assert feedback.preference is PreferenceFeedback.INTERESTED
    assert feedback.saved is True
    assert feedback.notes == "Preserve exactly"


def test_combined_ccn_insert_and_existing_score_refresh_are_stable_and_read_only(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    shutil.copytree(ROOT / "config", project_root / "config")
    existing_dir = tmp_path / "existing"
    addition_dir = tmp_path / "addition"
    combined_dir = tmp_path / "combined"
    job_raw = job_record(
        title="Sales Lead",
        research_areas=["Artificial intelligence"],
        research_orientation="Commercial / operational",
        education_requirement="Unknown",
    )
    job_report = run_jobs_pipeline([job_raw], config_dir=project_root / "config", observed_at=NOW)
    record_id = job_report.records[0].opportunity.opportunity_id
    _, job_rows = sheet_rows_from_report(job_report)
    existing_job = dict(job_rows[0])
    existing_job.update(
        {
            "Research_Relevance": 90.0,
            "Overall_Priority_Score": 90.0,
            "First_Seen": "2026-09-01T09:00:00+00:00",
            "Last_Seen": "2026-09-02T09:00:00+00:00",
        }
    )
    JsonOutputStore(existing_dir).write(job_report)
    JsonOutputStore(existing_dir).write(
        run_phd_pipeline([], config_dir=project_root / "config", observed_at=NOW)
    )
    JsonOutputStore(existing_dir).write(
        run_events_pipeline(
            [],
            config_dir=project_root / "config",
            observed_at=NOW,
            reference_date=NOW.date(),
        )
    )
    (existing_dir / "source_metadata.json").write_text(
        json.dumps(
            {
                "sources": {
                    "official_jobs": {
                        "health": "SUCCESS",
                        "retrieved_at": NOW.isoformat(),
                        "records_fetched": 1,
                        "records": [job_raw],
                    }
                },
                "pipelines": {},
            }
        ),
        encoding="utf-8",
    )
    ccn_raw = {
        "fictional": False,
        "title": "Cognitive Computational Neuroscience 2027",
        "series_name": "CCN",
        "organization": "Cognitive Computational Neuroscience",
        "source_url": "https://2027.ccneuro.org/",
        "official_source_url": "https://2027.ccneuro.org/",
        "official_url": "https://2027.ccneuro.org/",
        "adapter_source_id": "ccn_2027_official",
        "edition_year": 2027,
        "country": "United Kingdom",
        "region": "Europe",
        "location": "Edinburgh",
        "starts_on": "2027-07-26",
        "ends_on": "2027-07-29",
        "submission_deadline": None,
        "registration_deadline": None,
        "event_type": "academic conference",
        "research_areas": [
            "Computational cognitive neuroscience",
            "Cognitive modeling",
            "Neural representations",
        ],
        "opportunity_status": "confirmed upcoming",
        "source_verification_status": "VERIFIED_OFFICIAL",
        "source_type": "official_html",
        "source_evidence": [
            "Conference dates: 2027-07-26 through 2027-07-29",
            "Location: Edinburgh, United Kingdom",
        ],
        "extraction_method": "deterministic_html_patterns",
    }
    ccn_report = run_events_pipeline(
        [ccn_raw],
        config_dir=project_root / "config",
        observed_at=NOW,
        reference_date=NOW.date(),
    )
    JsonOutputStore(addition_dir).write(ccn_report)
    (addition_dir / "source_metadata.json").write_text(
        json.dumps(
            {
                "sources": {
                    "ccn_2027_official": {
                        "source": {"category": "events"},
                        "health": "SUCCESS",
                        "retrieved_at": NOW.isoformat(),
                        "records_fetched": 1,
                        "records_considered": 1,
                        "records": [ccn_raw],
                    }
                },
                "pipelines": {},
            }
        ),
        encoding="utf-8",
    )
    build_combined_live_snapshot(
        existing_dir=existing_dir,
        additions_dir=addition_dir,
        output_dir=combined_dir,
    )

    class PilotAdapter(InMemorySheetsAdapter):
        settings = type(
            "Settings", (), {"environment": "live-pilot", "spreadsheet_id": "pilot-id"}
        )()

        def get_spreadsheet_title(self) -> str:
            return "ResearchRadar AI — LIVE PILOT"

    adapter = PilotAdapter(
        {
            "Industry_Jobs": [existing_job],
            "My_Feedback": [
                {
                    "Record_ID": record_id,
                    "Preference": "Interested",
                    "Saved": True,
                    "Hidden": False,
                    "Personal_Notes": "Preserve exactly",
                    "Updated_At": "",
                }
            ],
        }
    )
    first = prepare_incremental_live_sync(
        project_root=project_root,
        live_data_dir=combined_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW,
        reference_date=NOW.date(),
        adapter=adapter,
    )
    second = prepare_incremental_live_sync(
        project_root=project_root,
        live_data_dir=combined_dir,
        review_dir=tmp_path / "review",
        generated_at=NOW.replace(hour=10),
        reference_date=NOW.date(),
        adapter=adapter,
    )

    assert first.preview.workbook.plans["jobs"].update_count == 1
    assert first.preview.workbook.plans["jobs"].change_log_rows == []
    assert first.preview.workbook.plans["events"].insert_count == 1
    assert len(first.preview.workbook.plans["events"].change_log_rows) == 1
    assert first.plan_fingerprint == second.plan_fingerprint
    assert adapter.write_operations == []
    job_update = first.preview.workbook.plans["jobs"].updates[0].changed_fields
    assert "First_Seen" not in job_update
    assert "Last_Seen" not in job_update
    feedback = first.preview.feedback.feedback_by_id[record_id]
    assert feedback.preference is PreferenceFeedback.INTERESTED
    assert feedback.saved is True
    assert feedback.hidden is False
    assert feedback.notes == "Preserve exactly"
