"""Evidence-based career-stage assessment kept separate from role function."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from research_radar.models import IndustryJob
from research_radar.role_function import RoleFunction


class CareerStageFit(StrEnum):
    NEAR_TERM_INTERNSHIP_OR_RA = "NEAR_TERM_INTERNSHIP_OR_RA"
    PRE_PHD_RESEARCH_ENGINEERING = "PRE_PHD_RESEARCH_ENGINEERING"
    POST_PHD_RESEARCH_CAREER = "POST_PHD_RESEARCH_CAREER"
    TRANSFERABLE_TECHNICAL = "TRANSFERABLE_TECHNICAL"
    INFORMATIONAL_RESEARCH_TEAM = "INFORMATIONAL_RESEARCH_TEAM"
    UNKNOWN = "UNKNOWN"


class ApplicationReadiness(StrEnum):
    POSSIBLE_NEAR_TERM = "POSSIBLE_NEAR_TERM"
    REQUIREMENTS_NEED_REVIEW = "REQUIREMENTS_NEED_REVIEW"
    FUTURE_CAREER_TARGET = "FUTURE_CAREER_TARGET"
    INFORMATIONAL_ONLY = "INFORMATIONAL_ONLY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CareerStageAssessment:
    classification: CareerStageFit
    application_readiness: ApplicationReadiness
    long_term_career_relevance: str
    confirmed_eligibility: bool | None
    required_education: str | None
    required_experience: str | None
    work_authorization_evidence: str | None
    explanation: str
    unknown_information: tuple[str, ...]


def assess_career_stage(
    job: IndustryJob,
    role_function: RoleFunction,
) -> CareerStageAssessment:
    """Derive career timing from official role evidence without asserting eligibility."""

    raw = job.original_values
    education = _text(raw.get("education_requirement_detail")) or _education(job)
    experience = _text(raw.get("experience_requirement_detail"))
    work_authorization = _text(raw.get("work_authorization_detail"))
    evidence = " ".join(
        value
        for value in (
            job.title,
            job.description,
            education,
            experience,
            _joined(raw.get("role_evidence")),
            _joined(raw.get("research_responsibility_evidence")),
        )
        if value
    ).casefold()
    unknowns = []
    if not education:
        unknowns.append("required education")
    if not experience:
        unknowns.append("required experience")
    if not work_authorization:
        unknowns.append("work authorization")

    if any(marker in evidence for marker in ("internship", "intern ", "research assistant")):
        return CareerStageAssessment(
            classification=CareerStageFit.NEAR_TERM_INTERNSHIP_OR_RA,
            application_readiness=ApplicationReadiness.REQUIREMENTS_NEED_REVIEW,
            long_term_career_relevance="HIGH",
            confirmed_eligibility=None,
            required_education=education,
            required_experience=experience,
            work_authorization_evidence=work_authorization,
            explanation=(
                "The official role evidence identifies an internship or research-assistant "
                "path, but enrollment, graduation, and work-authorization requirements still "
                "need explicit review."
            ),
            unknown_information=tuple(unknowns),
        )
    if _post_phd_evidence(evidence, education, experience):
        return CareerStageAssessment(
            classification=CareerStageFit.POST_PHD_RESEARCH_CAREER,
            application_readiness=ApplicationReadiness.FUTURE_CAREER_TARGET,
            long_term_career_relevance=(
                "HIGH"
                if role_function
                in {RoleFunction.RESEARCH_DIRECT, RoleFunction.RESEARCH_ADJACENT_ENGINEERING}
                else "MODERATE"
            ),
            confirmed_eligibility=False if education and "phd" in education.casefold() else None,
            required_education=education,
            required_experience=experience,
            work_authorization_evidence=work_authorization,
            explanation=(
                "Official requirements indicate a post-PhD or senior research-career target; "
                "this preserves long-term value without implying current readiness."
            ),
            unknown_information=tuple(unknowns),
        )
    if role_function in {
        RoleFunction.RESEARCH_DIRECT,
        RoleFunction.RESEARCH_ADJACENT_ENGINEERING,
    }:
        return CareerStageAssessment(
            classification=CareerStageFit.PRE_PHD_RESEARCH_ENGINEERING,
            application_readiness=ApplicationReadiness.REQUIREMENTS_NEED_REVIEW,
            long_term_career_relevance="HIGH",
            confirmed_eligibility=None,
            required_education=education,
            required_experience=experience,
            work_authorization_evidence=work_authorization,
            explanation=(
                "The role function supports pre-PhD research experience, but the available "
                "evidence does not confirm that the user satisfies every requirement."
            ),
            unknown_information=tuple(unknowns),
        )
    if role_function is RoleFunction.TECHNICAL_PLATFORM:
        return CareerStageAssessment(
            classification=CareerStageFit.TRANSFERABLE_TECHNICAL,
            application_readiness=ApplicationReadiness.REQUIREMENTS_NEED_REVIEW,
            long_term_career_relevance="MODERATE",
            confirmed_eligibility=None,
            required_education=education,
            required_experience=experience,
            work_authorization_evidence=work_authorization,
            explanation=(
                "The role offers technical skill transfer but lacks direct research ownership."
            ),
            unknown_information=tuple(unknowns),
        )
    return CareerStageAssessment(
        classification=CareerStageFit.UNKNOWN,
        application_readiness=ApplicationReadiness.UNKNOWN,
        long_term_career_relevance="UNKNOWN",
        confirmed_eligibility=None,
        required_education=education,
        required_experience=experience,
        work_authorization_evidence=work_authorization,
        explanation="Available official evidence is insufficient for a career-stage decision.",
        unknown_information=tuple(unknowns),
    )


def informational_research_team_assessment() -> CareerStageAssessment:
    """Represent a research team without converting it into a job opening."""

    return CareerStageAssessment(
        classification=CareerStageFit.INFORMATIONAL_RESEARCH_TEAM,
        application_readiness=ApplicationReadiness.INFORMATIONAL_ONLY,
        long_term_career_relevance="HIGH",
        confirmed_eligibility=None,
        required_education=None,
        required_experience=None,
        work_authorization_evidence=None,
        explanation=(
            "The evidence describes a research team or publication, not a currently listed job."
        ),
        unknown_information=(
            "current opening",
            "required education",
            "required experience",
            "work authorization",
        ),
    )


def _post_phd_evidence(
    evidence: str,
    education: str | None,
    experience: str | None,
) -> bool:
    if education and "phd" in education.casefold():
        return True
    combined = " ".join(value for value in (evidence, experience) if value)
    return any(
        marker in combined
        for marker in (
            "postdoctoral",
            "principal scientist",
            "senior research scientist",
            "staff research scientist",
            "5+ years",
            "five or more years",
        )
    )


def _education(job: IndustryJob) -> str | None:
    value = job.education_requirement.value
    return None if value == "UNKNOWN" else value


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _joined(value: object) -> str | None:
    if isinstance(value, list):
        rendered = " ".join(str(item).strip() for item in value if str(item).strip())
        return rendered or None
    return _text(value)
