"""Offline job-discovery policy and posting-state semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class PostingVerificationStatus(StrEnum):
    CONFIRMED_LISTED = "CONFIRMED_LISTED"
    DETAIL_PAGE_ACCESSIBLE_ONLY = "DETAIL_PAGE_ACCESSIBLE_ONLY"
    NOT_OBSERVED = "NOT_OBSERVED"
    CONFIRMED_CLOSED = "CONFIRMED_CLOSED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


@dataclass(frozen=True)
class CandidateSelection:
    selected_job_ids: tuple[str, ...]
    total_fetched: int
    relevant_candidates: int
    tracked_selected: int
    new_selected: int
    coverage_groups: tuple[str, ...]


def posting_status(
    *,
    index_available: bool,
    listed_on_current_index: bool,
    detail_accessible: bool,
    explicit_closed_evidence: bool,
) -> PostingVerificationStatus:
    """Classify posting evidence without treating absence or fetch failure as closure."""

    if explicit_closed_evidence:
        return PostingVerificationStatus.CONFIRMED_CLOSED
    if not index_available:
        return PostingVerificationStatus.SOURCE_UNAVAILABLE
    if listed_on_current_index and detail_accessible:
        return PostingVerificationStatus.CONFIRMED_LISTED
    if detail_accessible:
        return PostingVerificationStatus.DETAIL_PAGE_ACCESSIBLE_ONLY
    return PostingVerificationStatus.NOT_OBSERVED


def select_anthropic_candidates(
    jobs: list[dict[str, Any]],
    *,
    tracked_job_ids: set[str] | frozenset[str],
    max_details: int = 25,
    new_reserve: int = 5,
) -> CandidateSelection:
    """Propose bounded, deterministic, group-aware detail selection for offline review."""

    if max_details < 1 or new_reserve < 0 or new_reserve > max_details:
        raise ValueError("detail limits must satisfy 0 <= new_reserve <= max_details")
    prepared = [_candidate(job, tracked_job_ids) for job in jobs]
    relevant = [item for item in prepared if item is not None]
    tracked = sorted(
        (item for item in relevant if item[3]),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    new = sorted(
        (item for item in relevant if not item[3]),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    tracked_limit = max_details - min(new_reserve, len(new))
    selected = _round_robin(tracked, tracked_limit)
    selected_ids = {item[2] for item in selected}
    new_selection = _round_robin(new, min(new_reserve, max_details - len(selected)))
    selected.extend(new_selection)
    selected_ids.update(item[2] for item in new_selection)
    remaining = [item for item in [*tracked, *new] if item[2] not in selected_ids]
    selected.extend(_round_robin(remaining, max_details - len(selected)))
    return CandidateSelection(
        selected_job_ids=tuple(item[2] for item in selected),
        total_fetched=len(jobs),
        relevant_candidates=len(relevant),
        tracked_selected=sum(item[3] for item in selected),
        new_selected=sum(not item[3] for item in selected),
        coverage_groups=tuple(dict.fromkeys(item[1] for item in selected)),
    )


def _candidate(
    job: dict[str, Any],
    tracked_ids: set[str] | frozenset[str],
) -> tuple[int, str, str, bool] | None:
    job_id = str(job.get("id") or "").strip()
    title = str(job.get("title") or "").strip()
    if not job_id or not title:
        return None
    departments = job.get("departments")
    department_text = " ".join(
        str(item.get("name") or "") for item in departments or [] if isinstance(item, dict)
    )
    text = f"{title} {department_text}".casefold()
    group, score = _coverage_group(text)
    if score == 0 and job_id not in tracked_ids:
        return None
    return score, group, job_id, job_id in tracked_ids


def _coverage_group(text: str) -> tuple[str, int]:
    groups = (
        (
            "COGNITION_NEUROSCIENCE",
            4,
            ("neuro", "cognitive", "behavior", "human research", "brain"),
        ),
        (
            "INTERPRETABILITY_ALIGNMENT",
            3,
            ("interpretability", "alignment", "model behavior", "model evaluation"),
        ),
        (
            "RESEARCH_SCIENCE",
            2,
            ("research scientist", "research engineer", "machine learning research"),
        ),
        ("GENERAL_ML", 1, ("machine learning", "reinforcement learning", "data scientist")),
    )
    for group, score, markers in groups:
        if any(marker in text for marker in markers):
            return group, score
    return "OTHER", 0


def _round_robin(
    candidates: list[tuple[int, str, str, bool]],
    limit: int,
) -> list[tuple[int, str, str, bool]]:
    buckets: dict[str, list[tuple[int, str, str, bool]]] = {}
    for item in candidates:
        buckets.setdefault(item[1], []).append(item)
    selected: list[tuple[int, str, str, bool]] = []
    while len(selected) < limit and any(buckets.values()):
        groups = sorted(
            buckets,
            key=lambda value: -buckets[value][0][0] if buckets[value] else 0,
        )
        for group in groups:
            if buckets[group] and len(selected) < limit:
                selected.append(buckets[group].pop(0))
    return selected
