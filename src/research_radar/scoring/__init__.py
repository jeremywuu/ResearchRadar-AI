"""Deterministic, explainable scoring rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from research_radar.models import (
    AcademicEvent,
    CompensationDisclosureStatus,
    DomainFitClassification,
    EducationRequirement,
    IndustryJob,
    OpportunityStatus,
    PhDOpportunity,
    ResearchOrientation,
    ScoreBreakdown,
)


@dataclass(frozen=True)
class ResearchFitAssessment:
    overall: float
    domain_fit: float
    methodological_fit: float
    research_question_fit: float
    classification: DomainFitClassification
    explanation: tuple[str, ...]


def _canonical_term(value: str, aliases: dict[str, str]) -> str:
    normalized = value.strip().casefold()
    return aliases.get(normalized, value.strip()).casefold()


def _weighted_match(
    evidence: tuple[str, ...],
    configured: dict[str, Any],
    aliases: dict[str, str],
    *,
    neutral: float = 50.0,
) -> tuple[float, tuple[str, ...]]:
    weights = {
        _canonical_term(str(name), aliases): float(value) for name, value in configured.items()
    }
    matches = {
        _canonical_term(value, aliases): weights[_canonical_term(value, aliases)]
        for value in evidence
        if _canonical_term(value, aliases) in weights
    }
    if not matches:
        return neutral, ()
    return round(sum(matches.values()) / len(matches), 2), tuple(sorted(matches))


def assess_research_fit(
    research_areas: tuple[str, ...],
    interests: dict[str, Any],
    *,
    methods: tuple[str, ...] = (),
    role_title: str | None = None,
) -> ResearchFitAssessment:
    """Assess domain, method, and research-question fit without inventing missing evidence."""

    relevance = interests["research_relevance"]
    aliases = {
        str(name).casefold(): str(value) for name, value in relevance.get("aliases", {}).items()
    }
    canonical_areas = {_canonical_term(area, aliases) for area in research_areas}
    tiers = {
        name: {_canonical_term(value, aliases) for value in values}
        for name, values in interests["interest_tiers"].items()
    }
    title = (role_title or "").casefold()
    combined_evidence = " ".join((role_title or "", *research_areas)).casefold()
    lower_signal = next(
        (
            signal
            for signal in relevance["lower_priority_title_signals"]
            if signal.casefold() in title
        ),
        None,
    )
    interpretability_without_connection = "interpretability" in title and not any(
        signal.casefold() in combined_evidence
        for signal in relevance["interpretability_connection_signals"]
    )

    if lower_signal:
        classification = DomainFitClassification.LOW_DOMAIN_FIT
        tier_name = "lower_priority"
        domain_reason = f"Title evidence '{lower_signal}' indicates lower domain fit."
    elif interpretability_without_connection:
        classification = DomainFitClassification.INSUFFICIENT_EVIDENCE
        tier_name = "insufficient_evidence"
        domain_reason = (
            "Interpretability is not linked by available title evidence to cognition, brain, "
            "human behavior, or neural representations."
        )
    elif canonical_areas & tiers["core"]:
        classification = DomainFitClassification.CORE_DOMAIN_FIT
        tier_name = "core"
        domain_reason = "Structured research areas include a configured core domain."
    elif canonical_areas & tiers["adjacent"]:
        classification = DomainFitClassification.ADJACENT_DOMAIN_FIT
        tier_name = "adjacent"
        domain_reason = "Structured research areas include a configured adjacent domain."
    elif canonical_areas & tiers["technical_transferable"]:
        classification = DomainFitClassification.TECHNICAL_TRANSFERABLE
        tier_name = "technical_transferable"
        domain_reason = (
            "Available evidence supports transferable technical fit but not a cognition, brain, "
            "or behavior research question."
        )
    elif canonical_areas & tiers["lower_priority"]:
        classification = DomainFitClassification.LOW_DOMAIN_FIT
        tier_name = "lower_priority"
        domain_reason = "Structured research areas match a configured lower-priority domain."
    else:
        classification = DomainFitClassification.INSUFFICIENT_EVIDENCE
        tier_name = "insufficient_evidence"
        domain_reason = "Available structured evidence is insufficient to classify domain fit."

    domain_score = float(relevance["tier_scores"][tier_name])
    evidence = (*research_areas, *methods)
    method_score, method_matches = _weighted_match(
        evidence, relevance["methodology_weights"], aliases
    )
    question_score, question_matches = _weighted_match(
        research_areas, relevance["research_question_weights"], aliases
    )
    weights = relevance["component_weights"]
    overall = (
        domain_score * weights["domain_fit"]
        + method_score * weights["methodological_fit"]
        + question_score * weights["research_question_fit"]
    ) / 100
    method_reason = (
        f"Method evidence matched: {', '.join(method_matches)}."
        if method_matches
        else "Method evidence is unavailable or unmatched; neutral method fit applied."
    )
    question_reason = (
        f"Research-question evidence matched: {', '.join(question_matches)}."
        if question_matches
        else "Research-question evidence is unavailable or unmatched; neutral fit applied."
    )
    return ResearchFitAssessment(
        overall=round(overall, 2),
        domain_fit=domain_score,
        methodological_fit=method_score,
        research_question_fit=question_score,
        classification=classification,
        explanation=(domain_reason, method_reason, question_reason),
    )


def research_fit_score(
    research_areas: tuple[str, ...], interests: dict[str, Any]
) -> tuple[float, str]:
    assessment = assess_research_fit(research_areas, interests)
    return assessment.overall, " ".join(assessment.explanation)


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
    research = assess_research_fit(
        job.research_areas,
        interests,
        methods=job.skills,
        role_title=job.title,
    )
    phd_value, phd_reason = _phd_value(job)
    skills, skills_reason = _skills_score(job, preferences)
    compensation, compensation_reason = _compensation_score(job, salary_rules)
    components = {
        "research_relevance": research.overall,
        "research_domain_fit": research.domain_fit,
        "methodological_fit": research.methodological_fit,
        "research_question_fit": research.research_question_fit,
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
        explanation=(*research.explanation, phd_reason, skills_reason, compensation_reason),
        domain_fit=research.classification,
    )


def score_phd(
    opportunity: PhDOpportunity,
    *,
    interests: dict[str, Any],
    preferences: dict[str, Any],
) -> ScoreBreakdown:
    research = assess_research_fit(opportunity.research_areas, interests)
    cycle_scores = preferences.get("phd_cycle_scores", {})
    cycle_score = float(cycle_scores.get(opportunity.target_cycle or "unknown", 40.0))
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
        "research_fit": research.overall,
        "research_domain_fit": research.domain_fit,
        "methodological_fit": research.methodological_fit,
        "research_question_fit": research.research_question_fit,
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
            *research.explanation,
            f"Target cycle: {opportunity.target_cycle or 'unknown'}.",
            f"Recruitment evidence: {opportunity.opportunity_status.value}.",
        ),
        domain_fit=research.classification,
    )


def score_event(
    event: AcademicEvent,
    *,
    interests: dict[str, Any],
    reference_date: date,
) -> ScoreBreakdown:
    research = assess_research_fit(event.research_areas, interests)
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
        "research_fit": research.overall,
        "research_domain_fit": research.domain_fit,
        "methodological_fit": research.methodological_fit,
        "research_question_fit": research.research_question_fit,
        "geographic_priority": geography,
        "deadline_relevance": deadline_score,
    }
    weights = {"research_fit": 60, "geographic_priority": 25, "deadline_relevance": 15}
    final = sum(components[name] * weights[name] / 100 for name in weights)
    return ScoreBreakdown(
        components=components,
        weights=weights,
        final_score=round(final, 2),
        explanation=(
            *research.explanation,
            f"Region: {event.region or 'unknown'}.",
            deadline_reason,
        ),
        domain_fit=research.classification,
    )
