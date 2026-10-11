import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from research_radar.models import (
    PipelineReport,
    PipelineStatus,
    PreferenceFeedback,
    UserFeedback,
)
from research_radar.pipelines import run_independent_pipelines, run_jobs_pipeline
from research_radar.storage import JsonOutputStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def job_record() -> dict[str, object]:
    return {
        "fictional": True,
        "title": "AI Research Scientist",
        "organization": "Helix AI Research",
        "official_job_id": "HELIX-101",
        "source_url": "https://careers.helix-ai.example/jobs/HELIX-101",
        "country": "United States",
        "region": "North America",
        "research_areas": ["Artificial Intelligence"],
        "skills": ["Python", "Machine Learning"],
        "research_orientation": "Research-oriented",
        "education_requirement": "PhD Required",
        "working_language": "English",
    }


def empty_report(category: str) -> PipelineReport:
    return PipelineReport(
        category=category,
        status=PipelineStatus.SUCCESS,
        records_processed=0,
        records_accepted=0,
        duplicates_found=0,
        records_excluded=0,
        validation_errors=(),
        records=(),
    )


def test_pipeline_failure_does_not_stop_other_categories() -> None:
    def fail() -> PipelineReport:
        raise RuntimeError("synthetic pipeline failure")

    execution = run_independent_pipelines(
        {
            "jobs": lambda: empty_report("jobs"),
            "phd": fail,
            "events": lambda: empty_report("events"),
        }
    )

    assert execution.pipelines["jobs"].status is PipelineStatus.SUCCESS
    assert execution.pipelines["phd"].status is PipelineStatus.FAILED
    assert execution.pipelines["events"].status is PipelineStatus.SUCCESS
    assert execution.failed_pipelines == ("phd",)


def test_json_store_is_idempotent_and_preserves_feedback_and_history(tmp_path: Path) -> None:
    first = run_jobs_pipeline([job_record()], config_dir=PROJECT_ROOT / "config", observed_at=NOW)
    opportunity_id = first.records[0].opportunity.opportunity_id
    feedback = UserFeedback(
        opportunity_id=opportunity_id,
        preference=PreferenceFeedback.VERY_INTERESTED,
        saved=True,
        hidden=True,
        updated_at=NOW,
    )
    first = run_jobs_pipeline(
        [job_record()],
        config_dir=PROJECT_ROOT / "config",
        observed_at=NOW,
        feedback_by_id={opportunity_id: feedback},
    )
    store = JsonOutputStore(tmp_path)
    path = store.write(first)

    later = run_jobs_pipeline(
        [job_record()],
        config_dir=PROJECT_ROOT / "config",
        observed_at=NOW + timedelta(days=7),
    )
    store.write(later)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert len(payload["records"]) == 1
    saved = payload["records"][0]
    assert saved["opportunity"]["opportunity_id"] == opportunity_id
    assert saved["opportunity"]["first_seen_at"] == NOW.isoformat()
    assert saved["opportunity"]["last_seen_at"] == (NOW + timedelta(days=7)).isoformat()
    assert saved["feedback"]["saved"] is True
    assert saved["feedback"]["hidden"] is True
    assert saved["feedback"]["preference"] == "VERY_INTERESTED"
    assert saved["rank"] is None


def test_storage_outputs_valid_structured_json_for_each_category(tmp_path: Path) -> None:
    from research_radar.demo import run_demo

    execution = run_demo(
        ("jobs", "phd", "events"),
        project_root=PROJECT_ROOT,
        output_dir=tmp_path,
        observed_at=NOW,
        reference_date=date(2026, 10, 12),
    )

    assert not execution.failed_pipelines
    for category in ("jobs", "phd", "events"):
        payload = json.loads((tmp_path / f"{category}.json").read_text(encoding="utf-8"))
        assert payload["category"] == category
        assert payload["pipeline_status"] in {"SUCCESS", "PARTIAL"}
        assert payload["records"]
        assert all("score" in item and "opportunity" in item for item in payload["records"])
