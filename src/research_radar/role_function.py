"""Evidence-based research-role suitability assessment for industry jobs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from research_radar.models import IndustryJob


class RoleFunction(StrEnum):
    RESEARCH_DIRECT = "RESEARCH_DIRECT"
    RESEARCH_ADJACENT_ENGINEERING = "RESEARCH_ADJACENT_ENGINEERING"
    CLINICAL_IMPLEMENTATION = "CLINICAL_IMPLEMENTATION"
    TECHNICAL_PLATFORM = "TECHNICAL_PLATFORM"
    NON_RESEARCH = "NON_RESEARCH"
    UNKNOWN = "UNKNOWN"


class RoleDisplayGroup(StrEnum):
    TOP_RESEARCH_MATCH = "TOP_RESEARCH_MATCH"
    RESEARCH_ADJACENT = "RESEARCH_ADJACENT"
    TRANSFERABLE_TECHNICAL = "TRANSFERABLE_TECHNICAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    LOW_PRIORITY = "LOW_PRIORITY"


@dataclass(frozen=True)
class RoleFunctionAssessment:
    classification: RoleFunction
    display_group: RoleDisplayGroup
    explanation: str
    evidence: tuple[str, ...]


_CLINICAL_MARKERS = (
    "clinical site",
    "clinical trial",
    "clinical study",
    "support clinical",
    "field support",
    "patient visit",
    "patient-facing",
    "surgical",
    "operating room",
    "technical presence",
    "train clinicians",
    "site activation",
)
_DIRECT_RESEARCH_MARKERS = (
    "conduct research",
    "design experiments",
    "develop computational models",
    "test hypotheses",
    "publish",
    "scientific study",
    "research program",
    "analyze neural data",
    "analyse neural data",
    "computational neuroscience research",
)
_NEURAL_COMPUTATIONAL_MARKERS = (
    "neural data",
    "neural signal",
    "neural decoding",
    "bci decoding",
    "decoding algorithm",
    "signal processing",
    "cognitive model",
    "computational model",
)
_ENGINEERING_ACTION_MARKERS = (
    "develop",
    "build",
    "implement",
    "realize",
    "evaluate software",
    "production software",
    "algorithm",
    "data curation",
)
_PLATFORM_MARKERS = (
    "embedded",
    "firmware",
    "device driver",
    "infrastructure",
    "platform engineering",
    "deployment pipeline",
    "low-latency",
    "hardware interface",
    "operating systems",
)
_NON_RESEARCH_MARKERS = (
    "sales quota",
    "account executive",
    "recruiting pipeline",
    "legal counsel",
    "marketing campaign",
    "business development",
    "customer acquisition",
    "office administration",
)


def assess_role_function(job: IndustryJob) -> RoleFunctionAssessment:
    """Classify job function from role-level evidence, never employer identity alone."""

    evidence = _role_evidence(job)
    text = " ".join(evidence).casefold()
    if not text:
        return RoleFunctionAssessment(
            classification=RoleFunction.UNKNOWN,
            display_group=RoleDisplayGroup.NEEDS_REVIEW,
            explanation=(
                "No role-level responsibility evidence was extracted; employer and title alone "
                "cannot establish research suitability."
            ),
            evidence=(),
        )
    if _contains(text, _NON_RESEARCH_MARKERS):
        return RoleFunctionAssessment(
            classification=RoleFunction.NON_RESEARCH,
            display_group=RoleDisplayGroup.LOW_PRIORITY,
            explanation="Role-level evidence describes a non-research business function.",
            evidence=evidence,
        )
    if _contains(text, _CLINICAL_MARKERS):
        return RoleFunctionAssessment(
            classification=RoleFunction.CLINICAL_IMPLEMENTATION,
            display_group=RoleDisplayGroup.NEEDS_REVIEW,
            explanation=(
                "Role-level evidence centers clinical or field implementation; exposure to "
                "neurotechnology does not by itself establish computational research ownership."
            ),
            evidence=evidence,
        )
    if _contains(text, _DIRECT_RESEARCH_MARKERS):
        return RoleFunctionAssessment(
            classification=RoleFunction.RESEARCH_DIRECT,
            display_group=RoleDisplayGroup.TOP_RESEARCH_MATCH,
            explanation=(
                "Official responsibilities explicitly describe scientific research, experiments, "
                "modeling, or neural-data analysis."
            ),
            evidence=evidence,
        )
    if _contains(text, _NEURAL_COMPUTATIONAL_MARKERS) and _contains(
        text, _ENGINEERING_ACTION_MARKERS
    ):
        return RoleFunctionAssessment(
            classification=RoleFunction.RESEARCH_ADJACENT_ENGINEERING,
            display_group=RoleDisplayGroup.RESEARCH_ADJACENT,
            explanation=(
                "Official responsibilities connect engineering work to neural data, decoding, "
                "signal processing, or computational modeling."
            ),
            evidence=evidence,
        )
    if _contains(text, _PLATFORM_MARKERS):
        return RoleFunctionAssessment(
            classification=RoleFunction.TECHNICAL_PLATFORM,
            display_group=RoleDisplayGroup.TRANSFERABLE_TECHNICAL,
            explanation=(
                "Official responsibilities emphasize technical platform, firmware, embedded, or "
                "infrastructure work without direct research ownership."
            ),
            evidence=evidence,
        )
    return RoleFunctionAssessment(
        classification=RoleFunction.UNKNOWN,
        display_group=RoleDisplayGroup.NEEDS_REVIEW,
        explanation=(
            "Available role-level evidence does not establish direct research, research-adjacent "
            "engineering, clinical implementation, platform work, or a non-research function."
        ),
        evidence=evidence,
    )


def _role_evidence(job: IndustryJob) -> tuple[str, ...]:
    raw = job.original_values
    values: list[str] = []
    for field in ("research_responsibility_evidence", "role_evidence"):
        candidate = raw.get(field)
        if isinstance(candidate, list):
            values.extend(str(item).strip() for item in candidate if str(item).strip())
        elif isinstance(candidate, str) and candidate.strip():
            values.append(candidate.strip())
    if job.description:
        values.append(job.description.strip())
    return tuple(dict.fromkeys(value for value in values if value))


def _contains(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)
