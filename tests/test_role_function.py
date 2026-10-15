from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research_radar.pipelines import run_jobs_pipeline
from research_radar.role_function import RoleDisplayGroup, RoleFunction, assess_role_function
from research_radar.storage.json_store import JsonOutputStore

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)


def _job(title: str, responsibilities: str | None):
    raw: dict[str, object] = {
        "fictional": False,
        "title": title,
        "organization": "Evidence-Based Employer",
        "official_job_id": title.casefold().replace(" ", "-"),
        "source_url": "https://official.example/jobs/role",
        "official_source_url": "https://official.example/jobs",
        "adapter_source_id": "official_role_source",
        "location": "Brussels, Belgium",
        "country": "Belgium",
        "research_areas": ["Computational neuroscience"],
        "research_orientation": "Applied research",
        "education_requirement": "Other",
        "skills": [],
        "salary": {},
        "source_verification_status": "VERIFIED_OFFICIAL",
        "opportunity_status": "confirmed open",
        "source_type": "official_html",
        "source_evidence": ["Official role page"],
        "extraction_method": "deterministic_html_patterns",
    }
    if responsibilities is not None:
        raw["role_evidence"] = [responsibilities]
        raw["research_responsibility_evidence"] = [responsibilities]
    return (
        run_jobs_pipeline([raw], config_dir=ROOT / "config", observed_at=NOW).records[0].opportunity
    )


@pytest.mark.parametrize(
    ("title", "responsibilities", "expected", "group"),
    (
        (
            "Computational Neuroscience Scientist",
            "Conduct research and design experiments to analyze neural data.",
            RoleFunction.RESEARCH_DIRECT,
            RoleDisplayGroup.TOP_RESEARCH_MATCH,
        ),
        (
            "Neural Decoding Research Engineer",
            "Develop neural decoding algorithms and evaluate software with neural data.",
            RoleFunction.RESEARCH_ADJACENT_ENGINEERING,
            RoleDisplayGroup.RESEARCH_ADJACENT,
        ),
        (
            "BCI Clinical Specialist",
            "Provide field support at clinical sites and train clinicians during patient visits.",
            RoleFunction.CLINICAL_IMPLEMENTATION,
            RoleDisplayGroup.NEEDS_REVIEW,
        ),
        (
            "Embedded Firmware Engineer",
            "Build embedded firmware and low-latency hardware interfaces.",
            RoleFunction.TECHNICAL_PLATFORM,
            RoleDisplayGroup.TRANSFERABLE_TECHNICAL,
        ),
        (
            "Neural Data Scientist",
            "Analyze neural data and develop computational models for a scientific study.",
            RoleFunction.RESEARCH_DIRECT,
            RoleDisplayGroup.TOP_RESEARCH_MATCH,
        ),
        (
            "ML Infrastructure Engineer",
            "Build infrastructure and deployment pipelines for model serving.",
            RoleFunction.TECHNICAL_PLATFORM,
            RoleDisplayGroup.TRANSFERABLE_TECHNICAL,
        ),
        (
            "Research Engineer",
            None,
            RoleFunction.UNKNOWN,
            RoleDisplayGroup.NEEDS_REVIEW,
        ),
    ),
)
def test_role_function_uses_responsibilities_not_employer_brand(
    title: str,
    responsibilities: str | None,
    expected: RoleFunction,
    group: RoleDisplayGroup,
) -> None:
    assessment = assess_role_function(_job(title, responsibilities))

    assert assessment.classification is expected
    assert assessment.display_group is group


def test_non_research_responsibilities_are_not_promoted_by_research_title() -> None:
    assessment = assess_role_function(
        _job("Research Partnerships Lead", "Own business development and customer acquisition.")
    )

    assert assessment.classification is RoleFunction.NON_RESEARCH
    assert assessment.display_group is RoleDisplayGroup.LOW_PRIORITY


def test_role_function_is_derived_without_changing_schema_v2_snapshot(tmp_path: Path) -> None:
    report = run_jobs_pipeline(
        [
            _job(
                "Neural Decoding Engineer",
                "Develop decoding algorithms and evaluate software with neural data.",
            ).original_values
        ],
        config_dir=ROOT / "config",
        observed_at=NOW,
    )
    JsonOutputStore(tmp_path).write(report)
    payload = json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))

    assert "role_function" not in payload["records"][0]["opportunity"]
