from datetime import UTC, datetime

import pytest

from research_radar.career_stage import (
    ApplicationReadiness,
    CareerStageFit,
    assess_career_stage,
    informational_research_team_assessment,
)
from research_radar.models import (
    EducationRequirement,
    IndustryJob,
    SourceVerificationStatus,
)
from research_radar.role_function import RoleFunction

NOW = datetime(2026, 10, 16, tzinfo=UTC)


def _job(
    title: str,
    *,
    education: str | None = None,
    experience: str | None = None,
    work_authorization: str | None = None,
    evidence: str = "",
) -> IndustryJob:
    original = {
        "research_responsibility_evidence": [evidence] if evidence else [],
        "education_requirement_detail": education,
        "experience_requirement_detail": experience,
        "work_authorization_detail": work_authorization,
    }
    return IndustryJob(
        title=title,
        organization="Official Employer",
        source_url="https://example.org/jobs/1",
        official_source_url="https://example.org/jobs",
        first_seen_at=NOW,
        last_seen_at=NOW,
        source_verification_status=SourceVerificationStatus.VERIFIED_OFFICIAL,
        education_requirement=(
            EducationRequirement.PHD_REQUIRED
            if education and "phd" in education.casefold()
            else EducationRequirement.UNKNOWN
        ),
        original_values=original,
    )


@pytest.mark.parametrize(
    ("job", "role", "expected", "readiness"),
    (
        (
            _job("Neural Data Research Internship", evidence="Analyze neural data."),
            RoleFunction.RESEARCH_DIRECT,
            CareerStageFit.NEAR_TERM_INTERNSHIP_OR_RA,
            ApplicationReadiness.REQUIREMENTS_NEED_REVIEW,
        ),
        (
            _job(
                "Neural Decoding Research Engineer",
                experience="2+ years of relevant professional experience",
                evidence="Develop neural decoding algorithms.",
            ),
            RoleFunction.RESEARCH_ADJACENT_ENGINEERING,
            CareerStageFit.PRE_PHD_RESEARCH_ENGINEERING,
            ApplicationReadiness.REQUIREMENTS_NEED_REVIEW,
        ),
        (
            _job(
                "Research Scientist, Brain Foundation Models",
                education="PhD in neuroscience, computer science, or a related field",
                evidence="Develop computational models of neural data.",
            ),
            RoleFunction.RESEARCH_DIRECT,
            CareerStageFit.POST_PHD_RESEARCH_CAREER,
            ApplicationReadiness.FUTURE_CAREER_TARGET,
        ),
        (
            _job("Embedded Firmware Engineer", evidence="Build embedded firmware."),
            RoleFunction.TECHNICAL_PLATFORM,
            CareerStageFit.TRANSFERABLE_TECHNICAL,
            ApplicationReadiness.REQUIREMENTS_NEED_REVIEW,
        ),
        (
            _job("Machine Learning Engineer"),
            RoleFunction.UNKNOWN,
            CareerStageFit.UNKNOWN,
            ApplicationReadiness.UNKNOWN,
        ),
    ),
)
def test_career_stage_is_independent_from_role_function(
    job: IndustryJob,
    role: RoleFunction,
    expected: CareerStageFit,
    readiness: ApplicationReadiness,
) -> None:
    assessment = assess_career_stage(job, role)

    assert assessment.classification is expected
    assert assessment.application_readiness is readiness


def test_phd_requirement_is_future_relevant_not_currently_eligible() -> None:
    assessment = assess_career_stage(
        _job(
            "Computational Neuroscience Scientist",
            education="PhD required",
            evidence="Conduct computational neuroscience research.",
        ),
        RoleFunction.RESEARCH_DIRECT,
    )

    assert assessment.long_term_career_relevance == "HIGH"
    assert assessment.confirmed_eligibility is False
    assert assessment.application_readiness is ApplicationReadiness.FUTURE_CAREER_TARGET


def test_academic_research_does_not_satisfy_professional_experience_automatically() -> None:
    assessment = assess_career_stage(
        _job(
            "BCI Machine Learning Engineer",
            experience="3+ years of professional software engineering experience",
            evidence="Develop BCI decoding algorithms.",
        ),
        RoleFunction.RESEARCH_ADJACENT_ENGINEERING,
    )

    assert assessment.confirmed_eligibility is None
    assert assessment.required_experience == (
        "3+ years of professional software engineering experience"
    )


def test_missing_work_authorization_stays_unknown() -> None:
    assessment = assess_career_stage(
        _job("Neural Signal Processing Researcher", evidence="Analyze neural signals."),
        RoleFunction.RESEARCH_DIRECT,
    )

    assert assessment.work_authorization_evidence is None
    assert "work authorization" in assessment.unknown_information


def test_multiple_degree_options_do_not_become_post_phd_only() -> None:
    assessment = assess_career_stage(
        _job(
            "Signal Processing Engineer",
            education="BS, MS, or PhD in electrical engineering",
            evidence="Develop neural signal-processing algorithms.",
        ),
        RoleFunction.RESEARCH_ADJACENT_ENGINEERING,
    )

    assert assessment.classification is CareerStageFit.PRE_PHD_RESEARCH_ENGINEERING
    assert assessment.confirmed_eligibility is None


def test_research_team_profile_is_not_a_job_opening() -> None:
    assessment = informational_research_team_assessment()

    assert assessment.classification is CareerStageFit.INFORMATIONAL_RESEARCH_TEAM
    assert assessment.application_readiness is ApplicationReadiness.INFORMATIONAL_ONLY
    assert assessment.confirmed_eligibility is None
