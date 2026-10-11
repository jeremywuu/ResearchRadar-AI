"""Domain models shared by collection, ranking, and storage modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar
from urllib.parse import urlparse

from research_radar.identifiers import generate_stable_identifier


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"


class TargetCategory(StrEnum):
    AI_BIG_TECH = "ai_big_tech"
    BCI_NEUROTECHNOLOGY = "bci_neurotechnology"
    BEHAVIORAL_DIGITAL_HEALTH = "behavioral_digital_health"
    ACADEMIC_LAB = "academic_lab"
    ACADEMIC_PROGRAM = "academic_program"
    CONFERENCE_EVENT = "conference_event"


class MonitoringStatus(StrEnum):
    VERIFIED_ACTIVE_SOURCE = "VERIFIED_ACTIVE_SOURCE"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    DISABLED = "DISABLED"


class AdapterStatus(StrEnum):
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    READY = "READY"
    FAILING = "FAILING"
    DISABLED = "DISABLED"


class SourceVerificationStatus(StrEnum):
    VERIFIED_OFFICIAL = "VERIFIED_OFFICIAL"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    UNVERIFIED = "UNVERIFIED"


class OpportunityStatus(StrEnum):
    CONFIRMED_OPEN = "CONFIRMED_OPEN"
    CONFIRMED_UPCOMING = "CONFIRMED_UPCOMING"
    POTENTIAL_SIGNAL = "POTENTIAL_SIGNAL"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class OpportunityClassification(StrEnum):
    CURRENT_OPPORTUNITY = "CURRENT_OPPORTUNITY"
    EARLY_PHD_OPPORTUNITY = "EARLY_PHD_OPPORTUNITY"
    FUTURE_CAREER_TARGET = "FUTURE_CAREER_TARGET"
    UNCLASSIFIED = "UNCLASSIFIED"


class EnglishCompatibility(StrEnum):
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class CompensationDisclosureStatus(StrEnum):
    DISCLOSED = "DISCLOSED"
    PARTIALLY_DISCLOSED = "PARTIALLY_DISCLOSED"
    NOT_DISCLOSED = "NOT_DISCLOSED"
    UNCLEAR = "UNCLEAR"


class PreferenceFeedback(StrEnum):
    VERY_INTERESTED = "VERY_INTERESTED"
    INTERESTED = "INTERESTED"
    NOT_RELEVANT = "NOT_RELEVANT"


def _validate_http_url(value: str, field_name: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute HTTP(S) URL")


@dataclass(kw_only=True)
class Opportunity:
    """Fields shared by all opportunity types.

    Missing optional facts remain ``None``. They are never inferred by this model.
    """

    ID_PREFIX: ClassVar[str] = "opportunity"

    title: str
    organization: str
    source_url: str
    first_seen_at: datetime
    last_seen_at: datetime
    source_verification_status: SourceVerificationStatus
    opportunity_id: str = ""
    opportunity_status: OpportunityStatus = OpportunityStatus.UNKNOWN
    classification: OpportunityClassification = OpportunityClassification.UNCLASSIFIED
    description: str | None = None
    location: str | None = None
    working_language: str | None = None
    english_compatibility: EnglishCompatibility = EnglishCompatibility.NEEDS_REVIEW
    deadline: date | None = None
    review_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.organization.strip():
            raise ValueError("title and organization must not be blank")
        _validate_http_url(self.source_url, "source_url")
        if self.last_seen_at < self.first_seen_at:
            raise ValueError("last_seen_at cannot precede first_seen_at")
        if not self.opportunity_id:
            self.opportunity_id = generate_stable_identifier(
                self.ID_PREFIX,
                self.organization,
                self.title,
                self.source_url,
            )


@dataclass(kw_only=True)
class IndustryJob(Opportunity):
    ID_PREFIX: ClassVar[str] = "job"

    job_family: str | None = None
    seniority: str | None = None
    degree_requirement: str | None = None
    skills: tuple[str, ...] = ()
    base_salary_min: Decimal | None = None
    base_salary_max: Decimal | None = None
    bonus_min: Decimal | None = None
    bonus_max: Decimal | None = None
    equity_min: Decimal | None = None
    equity_max: Decimal | None = None
    total_compensation_min: Decimal | None = None
    total_compensation_max: Decimal | None = None
    currency: str | None = None
    salary_period: str | None = None
    compensation_source: str | None = None
    compensation_disclosure_status: CompensationDisclosureStatus = (
        CompensationDisclosureStatus.NOT_DISCLOSED
    )


@dataclass(kw_only=True)
class PhDOpportunity(Opportunity):
    ID_PREFIX: ClassVar[str] = "phd"

    supervisor: str | None = None
    laboratory: str | None = None
    target_cycle: str | None = None
    funding_status: str | None = None
    admission_url: str | None = None


@dataclass(kw_only=True)
class AcademicEvent(Opportunity):
    ID_PREFIX: ClassVar[str] = "event"

    event_type: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    submission_deadline: date | None = None
    event_url: str | None = None


@dataclass(kw_only=True)
class WatchlistTarget:
    name: str
    category: TargetCategory
    country_or_region: str
    priority: Priority
    research_focus: str
    official_website: str
    monitoring_url: str
    source_type: str
    monitoring_status: MonitoringStatus
    adapter_status: AdapterStatus = AdapterStatus.NOT_IMPLEMENTED
    canonical_organization: str | None = None
    target_id: str = ""

    def __post_init__(self) -> None:
        _validate_http_url(self.official_website, "official_website")
        _validate_http_url(self.monitoring_url, "monitoring_url")
        if not self.target_id:
            self.target_id = generate_stable_identifier(
                "target", self.canonical_organization or self.name, self.category.value
            )


@dataclass(kw_only=True)
class UserFeedback:
    opportunity_id: str
    preference: PreferenceFeedback | None
    saved: bool
    hidden: bool
    updated_at: datetime
    notes: str | None = None
    feedback_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.opportunity_id.strip():
            raise ValueError("opportunity_id must not be blank")
        self.feedback_id = generate_stable_identifier(
            "feedback", self.opportunity_id, self.updated_at.isoformat()
        )
