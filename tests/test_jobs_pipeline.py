from datetime import UTC, datetime
from pathlib import Path

import pytest

from research_radar.models import (
    EnglishCompatibility,
    OpportunityClassification,
    PreferenceFeedback,
    UserFeedback,
)
from research_radar.pipelines import run_jobs_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def job_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "fictional": True,
        "title": "AI Research Scientist",
        "organization": "Helix AI Research, Inc.",
        "official_job_id": "HELIX-101",
        "source_url": "https://careers.helix-ai.example/jobs/HELIX-101?utm_source=test",
        "country": "USA",
        "region": "North America",
        "location": "Boston, MA",
        "research_areas": ["Artificial Intelligence", "Reinforcement Learning"],
        "skills": ["Python", "Machine Learning", "Computational Modeling"],
        "research_orientation": "Research-oriented",
        "education_requirement": "PhD Required",
        "working_language": "English",
        "job_category": "Research Scientist",
        "seniority": "Senior",
        "salary": {
            "original_text": "USD 160,000-190,000 annual base",
            "base_min": 160000,
            "base_max": 190000,
            "currency": "USD",
            "period": "annual",
            "source_url": "https://careers.helix-ai.example/jobs/HELIX-101",
        },
        "source_verification_status": "VERIFIED_OFFICIAL",
    }
    record.update(overrides)
    return record


def test_jobs_pipeline_classifies_filters_and_scores_without_fabrication() -> None:
    records = [
        job_record(),
        job_record(
            title="Relevant Research Scientist Without Salary",
            official_job_id="HELIX-102",
            source_url="https://careers.helix-ai.example/jobs/HELIX-102",
            salary=None,
            working_language=None,
        ),
        job_record(
            title="Lokalisierungsforscher",
            official_job_id="HELIX-103",
            source_url="https://careers.helix-ai.example/jobs/HELIX-103",
            working_language="German required",
        ),
    ]

    report = run_jobs_pipeline(records, config_dir=PROJECT_ROOT / "config", observed_at=NOW)

    assert report.records_processed == 3
    assert report.records_accepted == 2
    assert report.records_excluded == 1

    future = next(
        item for item in report.records if item.opportunity.title == "AI Research Scientist"
    )
    assert future.opportunity.classification is OpportunityClassification.FUTURE_CAREER_TARGET
    assert future.excluded is False
    assert future.score.weights == {
        "research_relevance": 45,
        "phd_level_research_value": 25,
        "skills_and_career_fit": 20,
        "compensation": 10,
    }
    expected = sum(
        future.score.components[name] * weight / 100
        for name, weight in future.score.weights.items()
    )
    assert future.score.final_score == pytest.approx(expected)

    unknown = next(item for item in report.records if "Without Salary" in item.opportunity.title)
    assert unknown.opportunity.base_salary_min is None
    assert unknown.score.components["compensation"] == 50
    assert unknown.opportunity.english_compatibility is EnglishCompatibility.UNKNOWN
    assert unknown.excluded is False
    assert "WORKING_LANGUAGE_NEEDS_REVIEW" in unknown.opportunity.review_flags

    incompatible = next(
        item for item in report.records if item.opportunity.title == "Lokalisierungsforscher"
    )
    assert incompatible.opportunity.english_compatibility is (
        EnglishCompatibility.EXPLICITLY_NON_ENGLISH_REQUIRED
    )
    assert incompatible.excluded is True


def test_saved_and_hidden_are_separate_from_research_scoring() -> None:
    raw = [job_record()]
    first = run_jobs_pipeline(raw, config_dir=PROJECT_ROOT / "config", observed_at=NOW)
    stable_id = first.records[0].opportunity.opportunity_id
    feedback = UserFeedback(
        opportunity_id=stable_id,
        preference=PreferenceFeedback.INTERESTED,
        saved=True,
        hidden=True,
        updated_at=NOW,
    )

    second = run_jobs_pipeline(
        raw,
        config_dir=PROJECT_ROOT / "config",
        observed_at=NOW,
        feedback_by_id={stable_id: feedback},
    )
    result = second.records[0]

    assert result.score.components == first.records[0].score.components
    assert result.feedback is feedback
    assert result.feedback.saved is True
    assert result.feedback.hidden is True
    assert result.rank is None


def test_salary_threshold_uses_annualized_base_not_total_compensation() -> None:
    report = run_jobs_pipeline(
        [
            job_record(
                salary={
                    "original_text": "USD 140,000 base; USD 300,000 total compensation",
                    "base_min": 140000,
                    "base_max": 140000,
                    "total_compensation_min": 300000,
                    "total_compensation_max": 300000,
                    "currency": "USD",
                    "period": "yearly",
                }
            )
        ],
        config_dir=PROJECT_ROOT / "config",
        observed_at=NOW,
    )

    result = report.records[0]
    assert result.opportunity.salary_period == "annual"
    assert result.opportunity.total_compensation_max == 300000
    assert result.score.components["compensation"] == 50
    assert "BELOW_ASPIRATIONAL_THRESHOLD" in result.opportunity.salary_flags


def test_similar_titles_without_a_strong_identity_are_not_merged() -> None:
    report = run_jobs_pipeline(
        [
            job_record(official_job_id=None, location="Boston, MA"),
            job_record(
                official_job_id=None,
                source_url="https://careers.helix-ai.example/jobs/another",
                location="Toronto, ON",
            ),
        ],
        config_dir=PROJECT_ROOT / "config",
        observed_at=NOW,
    )

    assert report.duplicates_found == 0
    assert len(report.records) == 2
