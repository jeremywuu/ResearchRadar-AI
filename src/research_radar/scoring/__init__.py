"""Deterministic, explainable scoring rules."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from research_radar.models import (
    AcademicEvent,
    CompensationDisclosureStatus,
    EducationRequirement,
    IndustryJob,
    OpportunityStatus,
    PhDOpportunity,
    ResearchOrientation,
    ScoreBreakdown,
)


def _research_score(job: IndustryJob, interests: dict[str, Any]) -> tuple[float, str]:
    return research_fit_score(job.research_areas, interests)


def research_fit_score(
    research_areas: tuple[str, ...], interests: dict[str, Any]
) -> tuple[float, str]:
    configured = interests.get("interest_weights", {})
    weights = {str(name).casefold(): float(value) for name, value in configured.items()}
    matches = [weights[area.casefold()] for area in research_areas if area.casefold() in weights]
    if not research_areas:
        return 50.0, "Research areas were not disclosed; neutral relevance applied."
    if not matches:
        return 20.0, "No configured research-interest match."
    return round(
        sum(matches) / len(matches), 2
    ), f"Matched {len(matches)} configured research areas."


def _phd_value(job: IndustryJob) -> tuple[float, str]:
    orientation_scores = {
        ResearchOrientation.RESEARCH_ORIENTED: 90.0,
        ResearchOrientation.APPLIED_RESEARCH: 70.0,
        ResearchOrientation.COMMERCIAL_OPERATIONAL: 20.0,
        ResearchOrientation.UNKNOWN: 50.0,
    }
    score = orientation_scores[job.research_orientation]
    if job.education_requirement is EducationRequirement.PHD_REQUIRED:
        score = min(100.0, score + 10.0)
    elif job.education_requirement is EducationRequirement.PHD_PREFERRED:
        score = min(100.0, score + 5.0)
    return score, (
        f"{job.research_orientation.value}; education {job.education_requirement.value}."
    )


def _skills_score(job: IndustryJob, preferences: dict[str, Any]) -> tuple[float, str]:
    if not job.skills:
        return 50.0, "Skills were not disclosed; neutral career-fit applied."
    targets = {str(skill).casefold() for skill in preferences.get("target_skills", [])}
    matches = sum(skill.casefold() in targets for skill in job.skills)
    score = 100.0 * matches / len(job.skills)
    return round(score, 2), f"Matched {matches} of {len(job.skills)} configured target skills."


def _annualize(value: Decimal | None, period: str | None) -> Decimal | None:
    if value is None or period is None:
        return None
    factors = {"annual": Decimal("1"), "monthly": Decimal("12"), "hourly": Decimal("2080")}
    factor = factors.get(period)
    return value * factor if factor is not None else None


def _compensation_score(job: IndustryJob, salary_rules: dict[str, Any]) -> tuple[float, str]:
    job.annualized_base_salary_min = _annualize(job.base_salary_min, job.salary_period)
    job.annualized_base_salary_max = _annualize(job.base_salary_max, job.salary_period)
    if job.compensation_disclosure_status is CompensationDisclosureStatus.NOT_DISCLOSED:
        job.salary_flags = ("SALARY_NOT_DISCLOSED", "INSUFFICIENT_COMPARISON_DATA")
        return 50.0, "Salary not disclosed; neutral compensation score applied."

    region_key_by_country = {
        "United States": "US",
        "Canada": "CA",
        "United Kingdom": "UK",
        "Australia": "AU",
        "Belgium": "EURO_AREA",
    }
    key = region_key_by_country.get(job.country or "")
    threshold = salary_rules.get("aspirational_base_salary_thresholds", {}).get(key)
    comparable = (
        threshold
        and job.currency == threshold.get("currency")
        and job.annualized_base_salary_max is not None
    )
    if not comparable:
        job.salary_flags = ("THRESHOLD_NOT_COMPARABLE", "INSUFFICIENT_COMPARISON_DATA")
        return 50.0, "Compensation is not comparable to a configured base-salary threshold."
    annual_max = job.annualized_base_salary_max
    assert annual_max is not None
    if annual_max >= Decimal(str(threshold["annual_base"])):
        job.salary_flags = ("ABOVE_ASPIRATIONAL_THRESHOLD", "INSUFFICIENT_COMPARISON_DATA")
        return 75.0, "Annualized base salary reaches the configured attention threshold."
    job.salary_flags = ("BELOW_ASPIRATIONAL_THRESHOLD", "INSUFFICIENT_COMPARISON_DATA")
    return 50.0, "Annualized base salary is below the configured attention threshold."


def score_job(
    job: IndustryJob,
    *,
    interests: dict[str, Any],
    preferences: dict[str, Any],
    salary_rules: dict[str, Any],
) -> ScoreBreakdown:
    research, research_reason = _research_score(job, interests)
    phd_value, phd_reason = _phd_value(job)
    skills, skills_reason = _skills_score(job, preferences)
    compensation, compensation_reason = _compensation_score(job, salary_rules)
    components = {
        "research_relevance": research,
        "phd_level_research_value": phd_value,
        "skills_and_career_fit": skills,
        "compensation": compensation,
    }
    weights = dict(salary_rules["industry_job_scoring_weights"])
    final = sum(components[name] * weights[name] / 100 for name in weights)
    return ScoreBreakdown(
        components=components,
        weights=weights,
        final_score=round(final, 2),
        explanation=(research_reason, phd_reason, skills_reason, compensation_reason),
    )


def score_phd(
    opportunity: PhDOpportunity,
    *,
    interests: dict[str, Any],
    preferences: dict[str, Any],
) -> ScoreBreakdown:
    research, research_reason = research_fit_score(opportunity.research_areas, interests)
    target_cycles = set(preferences.get("phd_target_cycles", []))
    cycle_score = 100.0 if opportunity.target_cycle in target_cycles else 40.0
    if opportunity.target_cycle is None:
        cycle_score = 50.0
    confidence_scores = {
        OpportunityStatus.CONFIRMED_OPEN: 100.0,
        OpportunityStatus.CONFIRMED_UPCOMING: 90.0,
        OpportunityStatus.POTENTIAL_SIGNAL: 60.0,
        OpportunityStatus.HISTORICAL_ONLY: 20.0,
        OpportunityStatus.CLOSED: 10.0,
        OpportunityStatus.UNKNOWN: 50.0,
    }
    confidence = confidence_scores[opportunity.opportunity_status]
    components = {
        "research_fit": research,
        "target_cycle": cycle_score,
        "opportunity_confidence": confidence,
    }
    weights = {"research_fit": 70, "target_cycle": 20, "opportunity_confidence": 10}
    final = sum(components[name] * weights[name] / 100 for name in weights)
    return ScoreBreakdown(
        components=components,
        weights=weights,
        final_score=round(final, 2),
        explanation=(
            research_reason,
            f"Target cycle: {opportunity.target_cycle or 'unknown'}.",
            f"Recruitment evidence: {opportunity.opportunity_status.value}.",
        ),
    )


def score_event(
    event: AcademicEvent,
    *,
    interests: dict[str, Any],
    reference_date: date,
) -> ScoreBreakdown:
    research, research_reason = research_fit_score(event.research_areas, interests)
    if (event.region or "").casefold() == "europe":
        geography = 100.0
    elif (event.region or "").casefold() in {"north america", "australia"}:
        geography = 75.0
    else:
        geography = 50.0
    deadline = event.submission_deadline or event.registration_deadline
    if deadline is None:
        deadline_score = 50.0
        deadline_reason = "No deadline disclosed; neutral deadline score applied."
    else:
        days = (deadline - reference_date).days
        if days < 0:
            deadline_score = 20.0
        elif days <= 30:
            deadline_score = 100.0
        elif days <= 90:
            deadline_score = 80.0
        else:
            deadline_score = 60.0
        deadline_reason = f"Nearest tracked deadline is {days} days from the reference date."
    components = {
        "research_fit": research,
        "geographic_priority": geography,
        "deadline_relevance": deadline_score,
    }
    weights = {"research_fit": 60, "geographic_priority": 25, "deadline_relevance": 15}
    final = sum(components[name] * weights[name] / 100 for name in weights)
    return ScoreBreakdown(
        components=components,
        weights=weights,
        final_score=round(final, 2),
        explanation=(research_reason, f"Region: {event.region or 'unknown'}.", deadline_reason),
    )
