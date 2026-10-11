"""Raw-record normalization into domain models."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from research_radar.identifiers import generate_stable_identifier
from research_radar.models import (
    AcademicEvent,
    AcademicEventType,
    CompensationDisclosureStatus,
    EducationRequirement,
    EnglishCompatibility,
    IndustryJob,
    OpportunityClassification,
    OpportunityStatus,
    PhDOpportunity,
    PhDOpportunityType,
    ResearchOrientation,
    SourceVerificationStatus,
)


class RecordValidationError(ValueError):
    """Raised when a raw record cannot be safely normalized."""


ORGANIZATION_SUFFIXES = (", inc.", " inc.", " ltd.", " corporation")
COUNTRY_ALIASES = {
    "usa": "United States",
    "us": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "belgium": "Belgium",
    "canada": "Canada",
    "australia": "Australia",
}
RESEARCH_AREA_ALIASES = {
    "ai": "Artificial intelligence",
    "artificial intelligence": "Artificial intelligence",
    "ml": "Machine learning",
    "machine learning": "Machine learning",
    "reinforcement learning": "Reinforcement learning",
    "computational neuroscience": "Computational neuroscience",
    "cognitive neuroscience": "Cognitive neuroscience",
    "computational modeling": "Computational modeling",
    "brain-computer interfaces": "Brain-computer interfaces",
    "bci": "Brain-computer interfaces",
    "neural decoding": "Neural decoding",
    "data science": "Data science",
    "behavioral science": "Behavioral science",
    "human-ai interaction": "Human-AI interaction",
    "neural representations": "Neural representations",
    "decision-making": "Decision-making",
}


def normalize_organization(value: str) -> str:
    normalized = " ".join(value.split()).strip()
    lowered = normalized.casefold()
    for suffix in ORGANIZATION_SUFFIXES:
        if lowered.endswith(suffix):
            return normalized[: -len(suffix)].rstrip(" ,")
    return normalized


def normalize_country(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip()
    return COUNTRY_ALIASES.get(cleaned.casefold(), cleaned)


def normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RecordValidationError("source_url must be an absolute HTTP(S) URL")
    query = urlencode(
        [(key, item) for key, item in parse_qsl(parsed.query) if not key.startswith("utm_")]
    )
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), path, query, ""))


def normalize_research_areas(values: object) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise RecordValidationError("research_areas must be a list of strings")
    result = [
        RESEARCH_AREA_ALIASES.get(value.strip().casefold(), value.strip()) for value in values
    ]
    return tuple(dict.fromkeys(value for value in result if value))


def parse_date(value: object, field_name: str) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise RecordValidationError(f"{field_name} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RecordValidationError(f"{field_name} must be an ISO date string") from exc


def _required_text(raw: dict[str, Any], field_name: str) -> str:
    value = raw.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise RecordValidationError(f"{field_name} is required")
    return value.strip()


def _research_orientation(value: object) -> ResearchOrientation:
    mapping = {
        "research-oriented": ResearchOrientation.RESEARCH_ORIENTED,
        "applied research": ResearchOrientation.APPLIED_RESEARCH,
        "commercial / operational": ResearchOrientation.COMMERCIAL_OPERATIONAL,
        "commercial/operational": ResearchOrientation.COMMERCIAL_OPERATIONAL,
    }
    return mapping.get(str(value).strip().casefold(), ResearchOrientation.UNKNOWN)


def _education_requirement(value: object) -> EducationRequirement:
    mapping = {
        "phd required": EducationRequirement.PHD_REQUIRED,
        "phd preferred": EducationRequirement.PHD_PREFERRED,
        "master's accepted": EducationRequirement.MASTERS_ACCEPTED,
        "masters accepted": EducationRequirement.MASTERS_ACCEPTED,
        "equivalent experience accepted": EducationRequirement.EQUIVALENT_EXPERIENCE_ACCEPTED,
        "other": EducationRequirement.OTHER,
    }
    return mapping.get(str(value).strip().casefold(), EducationRequirement.UNKNOWN)


def _language(value: object) -> tuple[str | None, EnglishCompatibility, tuple[str, ...]]:
    if value is None or not str(value).strip():
        return None, EnglishCompatibility.UNKNOWN, ("WORKING_LANGUAGE_NEEDS_REVIEW",)
    text = str(value).strip()
    lowered = text.casefold()
    if "english" in lowered:
        return text, EnglishCompatibility.ENGLISH_COMPATIBLE, ()
    if "required" in lowered:
        return text, EnglishCompatibility.EXPLICITLY_NON_ENGLISH_REQUIRED, ()
    return text, EnglishCompatibility.UNKNOWN, ("WORKING_LANGUAGE_NEEDS_REVIEW",)


def _job_classification(
    title: str,
    education: EducationRequirement,
) -> OpportunityClassification:
    lowered = title.casefold()
    if "intern" in lowered:
        if education in {EducationRequirement.PHD_REQUIRED, EducationRequirement.PHD_PREFERRED}:
            return OpportunityClassification.EARLY_PHD_OPPORTUNITY
        return OpportunityClassification.CURRENT_OPPORTUNITY
    if education in {EducationRequirement.PHD_REQUIRED, EducationRequirement.PHD_PREFERRED}:
        return OpportunityClassification.FUTURE_CAREER_TARGET
    if education in {
        EducationRequirement.MASTERS_ACCEPTED,
        EducationRequirement.EQUIVALENT_EXPERIENCE_ACCEPTED,
    }:
        return OpportunityClassification.CURRENT_OPPORTUNITY
    return OpportunityClassification.NEEDS_REVIEW


def _decimal(value: object, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise RecordValidationError(f"{field_name} must be numeric")
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise RecordValidationError(f"{field_name} must be numeric") from exc


def _salary_period(value: object) -> str | None:
    if value in (None, ""):
        return None
    mapping = {
        "annual": "annual",
        "annually": "annual",
        "year": "annual",
        "yearly": "annual",
        "monthly": "monthly",
        "month": "monthly",
        "hourly": "hourly",
        "hour": "hourly",
    }
    return mapping.get(str(value).strip().casefold())


def normalize_job(raw: dict[str, Any], *, observed_at: datetime) -> IndustryJob:
    if raw.get("fictional") is not True:
        raise RecordValidationError("demo records must be explicitly marked fictional")
    title = _required_text(raw, "title")
    organization = normalize_organization(_required_text(raw, "organization"))
    source_url = normalize_url(_required_text(raw, "source_url"))
    official_job_id = raw.get("official_job_id")
    if official_job_id is not None and not isinstance(official_job_id, str):
        raise RecordValidationError("official_job_id must be a string")
    education = _education_requirement(raw.get("education_requirement"))
    language, compatibility, review_flags = _language(raw.get("working_language"))
    location = str(raw["location"]).strip() if raw.get("location") else None
    identity_parts = (
        (organization, official_job_id)
        if official_job_id
        else (organization, title, location or "unknown-location")
    )
    identity_key = "|".join(part.casefold() for part in identity_parts)
    salary = raw.get("salary")
    salary_data = salary if isinstance(salary, dict) else {}
    has_any_compensation = any(
        salary_data.get(field) is not None
        for field in (
            "base_min",
            "base_max",
            "bonus_min",
            "bonus_max",
            "equity_min",
            "equity_max",
            "total_compensation_min",
            "total_compensation_max",
        )
    )
    if has_any_compensation:
        disclosure = CompensationDisclosureStatus.DISCLOSED
    elif salary_data.get("original_text"):
        disclosure = CompensationDisclosureStatus.PARTIALLY_DISCLOSED
    else:
        disclosure = CompensationDisclosureStatus.NOT_DISCLOSED
    source_status_value = raw.get("source_verification_status", "UNVERIFIED")
    try:
        source_status = SourceVerificationStatus(str(source_status_value))
    except ValueError as exc:
        raise RecordValidationError("invalid source_verification_status") from exc

    return IndustryJob(
        title=title,
        organization=organization,
        source_url=source_url,
        source_urls=(source_url,),
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        source_verification_status=source_status,
        opportunity_status=OpportunityStatus.UNKNOWN,
        classification=_job_classification(title, education),
        opportunity_id=generate_stable_identifier("job", *identity_parts),
        identity_key=identity_key,
        original_values=deepcopy(raw),
        country=normalize_country(
            raw.get("country") if isinstance(raw.get("country"), str) else None
        ),
        region=str(raw["region"]).strip() if raw.get("region") else None,
        location=location,
        research_areas=normalize_research_areas(raw.get("research_areas")),
        working_language=language,
        english_compatibility=compatibility,
        review_flags=review_flags,
        official_job_id=official_job_id,
        job_category=str(raw["job_category"]).strip() if raw.get("job_category") else None,
        job_family=str(raw["job_category"]).strip() if raw.get("job_category") else None,
        seniority=str(raw["seniority"]).strip() if raw.get("seniority") else None,
        research_orientation=_research_orientation(raw.get("research_orientation")),
        education_requirement=education,
        degree_requirement=str(raw["education_requirement"]).strip()
        if raw.get("education_requirement")
        else None,
        skills=tuple(str(value).strip() for value in raw.get("skills", []) if str(value).strip()),
        base_salary_min=_decimal(salary_data.get("base_min"), "salary.base_min"),
        base_salary_max=_decimal(salary_data.get("base_max"), "salary.base_max"),
        bonus_min=_decimal(salary_data.get("bonus_min"), "salary.bonus_min"),
        bonus_max=_decimal(salary_data.get("bonus_max"), "salary.bonus_max"),
        equity_min=_decimal(salary_data.get("equity_min"), "salary.equity_min"),
        equity_max=_decimal(salary_data.get("equity_max"), "salary.equity_max"),
        total_compensation_min=_decimal(
            salary_data.get("total_compensation_min"), "salary.total_compensation_min"
        ),
        total_compensation_max=_decimal(
            salary_data.get("total_compensation_max"), "salary.total_compensation_max"
        ),
        currency=str(salary_data["currency"]).upper() if salary_data.get("currency") else None,
        salary_period=_salary_period(salary_data.get("period")),
        compensation_source=str(salary_data["original_text"])
        if salary_data.get("original_text")
        else None,
        compensation_source_url=normalize_url(str(salary_data["source_url"]))
        if salary_data.get("source_url")
        else None,
        original_salary_text=str(salary_data["original_text"])
        if salary_data.get("original_text")
        else None,
        compensation_disclosure_status=disclosure,
    )


def _source_status(raw: dict[str, Any]) -> SourceVerificationStatus:
    value = raw.get("source_verification_status", "UNVERIFIED")
    try:
        return SourceVerificationStatus(str(value))
    except ValueError as exc:
        raise RecordValidationError("invalid source_verification_status") from exc


def _opportunity_status(value: object) -> OpportunityStatus:
    mapping = {
        "confirmed open": OpportunityStatus.CONFIRMED_OPEN,
        "confirmed upcoming": OpportunityStatus.CONFIRMED_UPCOMING,
        "potential signal": OpportunityStatus.POTENTIAL_SIGNAL,
        "historical only": OpportunityStatus.HISTORICAL_ONLY,
        "closed": OpportunityStatus.CLOSED,
        "unknown": OpportunityStatus.UNKNOWN,
    }
    return mapping.get(str(value).strip().casefold(), OpportunityStatus.UNKNOWN)


def _phd_type(value: object) -> PhDOpportunityType:
    mapping = {
        "advertised phd position": PhDOpportunityType.ADVERTISED_POSITION,
        "centralized phd program admission": PhDOpportunityType.CENTRALIZED_PROGRAM,
        "individual pi recruitment announcement": PhDOpportunityType.PI_RECRUITMENT_ANNOUNCEMENT,
    }
    return mapping.get(str(value).strip().casefold(), PhDOpportunityType.UNKNOWN)


def normalize_phd(raw: dict[str, Any], *, observed_at: datetime) -> PhDOpportunity:
    if raw.get("fictional") is not True:
        raise RecordValidationError("demo records must be explicitly marked fictional")
    title = _required_text(raw, "title")
    organization = normalize_organization(_required_text(raw, "organization"))
    source_url = normalize_url(_required_text(raw, "source_url"))
    target_cycle = str(raw["target_cycle"]).strip() if raw.get("target_cycle") else None
    official_id = raw.get("official_opportunity_id")
    if official_id is not None and not isinstance(official_id, str):
        raise RecordValidationError("official_opportunity_id must be a string")
    supervisor = str(raw["supervisor"]).strip() if raw.get("supervisor") else None
    laboratory = str(raw["laboratory"]).strip() if raw.get("laboratory") else None
    strong_reference = official_id or "|".join(
        value for value in (title, supervisor, laboratory) if value
    )
    identity_parts = (organization, strong_reference, target_cycle or "unknown-cycle")
    identity_key = "|".join(part.casefold() for part in identity_parts)
    funding_status = str(raw["funding_status"]).strip() if raw.get("funding_status") else None
    flags = () if funding_status else ("FUNDING_UNKNOWN",)
    return PhDOpportunity(
        title=title,
        organization=organization,
        source_url=source_url,
        source_urls=(source_url,),
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        source_verification_status=_source_status(raw),
        opportunity_status=_opportunity_status(raw.get("opportunity_status")),
        classification=OpportunityClassification.CURRENT_OPPORTUNITY,
        opportunity_id=generate_stable_identifier("phd", *identity_parts),
        identity_key=identity_key,
        original_values=deepcopy(raw),
        country=normalize_country(
            raw.get("country") if isinstance(raw.get("country"), str) else None
        ),
        region=str(raw["region"]).strip() if raw.get("region") else None,
        location=str(raw["location"]).strip() if raw.get("location") else None,
        research_areas=normalize_research_areas(raw.get("research_areas")),
        deadline=parse_date(raw.get("deadline"), "deadline"),
        review_flags=flags,
        supervisor=supervisor,
        laboratory=laboratory,
        target_cycle=target_cycle,
        funding_status=funding_status,
        admission_url=normalize_url(str(raw["admission_url"]))
        if raw.get("admission_url")
        else None,
        official_opportunity_id=official_id,
        opportunity_type=_phd_type(raw.get("opportunity_type")),
    )


def _event_type(value: object) -> AcademicEventType:
    mapping = {
        "academic conference": AcademicEventType.ACADEMIC_CONFERENCE,
        "workshop": AcademicEventType.WORKSHOP,
        "symposium": AcademicEventType.SYMPOSIUM,
        "summer school": AcademicEventType.SUMMER_SCHOOL,
        "industry exhibition": AcademicEventType.INDUSTRY_EXHIBITION,
        "networking event": AcademicEventType.NETWORKING_EVENT,
    }
    return mapping.get(str(value).strip().casefold(), AcademicEventType.UNKNOWN)


def normalize_event(raw: dict[str, Any], *, observed_at: datetime) -> AcademicEvent:
    if raw.get("fictional") is not True:
        raise RecordValidationError("demo records must be explicitly marked fictional")
    title = _required_text(raw, "title")
    series_name = _required_text(raw, "series_name")
    organization = normalize_organization(_required_text(raw, "organization"))
    source_url = normalize_url(_required_text(raw, "source_url"))
    official_url = normalize_url(str(raw.get("official_url") or source_url))
    edition_year_value = raw.get("edition_year")
    if edition_year_value is not None and (
        isinstance(edition_year_value, bool) or not isinstance(edition_year_value, int)
    ):
        raise RecordValidationError("edition_year must be an integer")
    starts_on = parse_date(raw.get("starts_on"), "starts_on")
    ends_on = parse_date(raw.get("ends_on"), "ends_on")
    if starts_on and ends_on and ends_on < starts_on:
        raise RecordValidationError("ends_on cannot precede starts_on")
    edition_identity = str(edition_year_value) if edition_year_value is not None else str(starts_on)
    identity_parts = (series_name, edition_identity)
    identity_key = "|".join(part.casefold() for part in identity_parts)
    flags = () if edition_year_value is not None else ("EDITION_YEAR_UNKNOWN",)
    return AcademicEvent(
        title=title,
        organization=organization,
        source_url=source_url,
        source_urls=(source_url,),
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        source_verification_status=_source_status(raw),
        opportunity_status=_opportunity_status(raw.get("opportunity_status")),
        opportunity_id=generate_stable_identifier("event", *identity_parts),
        identity_key=identity_key,
        original_values=deepcopy(raw),
        country=normalize_country(
            raw.get("country") if isinstance(raw.get("country"), str) else None
        ),
        region=str(raw["region"]).strip() if raw.get("region") else None,
        location=str(raw["location"]).strip() if raw.get("location") else None,
        research_areas=normalize_research_areas(raw.get("research_areas")),
        review_flags=flags,
        event_type=str(raw["event_type"]).strip() if raw.get("event_type") else None,
        academic_event_type=_event_type(raw.get("event_type")),
        starts_on=starts_on,
        ends_on=ends_on,
        submission_deadline=parse_date(raw.get("submission_deadline"), "submission_deadline"),
        registration_deadline=parse_date(raw.get("registration_deadline"), "registration_deadline"),
        deadline=parse_date(raw.get("submission_deadline"), "submission_deadline"),
        event_url=official_url,
        series_name=series_name,
        edition_year=edition_year_value,
    )
