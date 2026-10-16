import pytest

from research_radar.job_discovery import (
    PostingVerificationStatus,
    posting_status,
    select_anthropic_candidates,
)


@pytest.mark.parametrize(
    ("index", "listed", "detail", "closed", "expected"),
    (
        (True, True, True, False, PostingVerificationStatus.CONFIRMED_LISTED),
        (True, False, True, False, PostingVerificationStatus.DETAIL_PAGE_ACCESSIBLE_ONLY),
        (True, False, False, False, PostingVerificationStatus.NOT_OBSERVED),
        (False, False, False, False, PostingVerificationStatus.SOURCE_UNAVAILABLE),
        (True, False, True, True, PostingVerificationStatus.CONFIRMED_CLOSED),
    ),
)
def test_posting_status_requires_current_index_or_explicit_closure(
    index: bool,
    listed: bool,
    detail: bool,
    closed: bool,
    expected: PostingVerificationStatus,
) -> None:
    assert (
        posting_status(
            index_available=index,
            listed_on_current_index=listed,
            detail_accessible=detail,
            explicit_closed_evidence=closed,
        )
        is expected
    )


def test_anthropic_policy_prioritizes_domain_fit_and_preserves_group_coverage() -> None:
    jobs = [
        {"id": 1, "title": "Research Scientist, Brain and Model Alignment"},
        {"id": 2, "title": "Research Engineer, Interpretability"},
        {"id": 3, "title": "Research Scientist, Machine Learning"},
        {"id": 4, "title": "Machine Learning Engineer"},
        {"id": 5, "title": "Infrastructure Engineer"},
        {"id": 6, "title": "Research Scientist, Human Behavior"},
    ]

    result = select_anthropic_candidates(
        jobs,
        tracked_job_ids=frozenset({"4"}),
        max_details=4,
        new_reserve=2,
    )

    assert "1" in result.selected_job_ids
    assert "4" in result.selected_job_ids
    assert "5" not in result.selected_job_ids
    assert result.tracked_selected == 1
    assert "COGNITION_NEUROSCIENCE" in result.coverage_groups
    assert len(result.selected_job_ids) == 4


def test_anthropic_policy_is_stable_across_listing_order() -> None:
    jobs = [
        {"id": "b", "title": "Research Engineer, Interpretability"},
        {"id": "a", "title": "Research Scientist, Brain Models"},
        {"id": "c", "title": "Machine Learning Engineer"},
    ]

    first = select_anthropic_candidates(jobs, tracked_job_ids=set(), max_details=3, new_reserve=3)
    second = select_anthropic_candidates(
        list(reversed(jobs)), tracked_job_ids=set(), max_details=3, new_reserve=3
    )

    assert first.selected_job_ids == second.selected_job_ids


def test_anthropic_policy_keeps_bounded_detail_budget() -> None:
    jobs = [
        {"id": index, "title": f"Research Scientist, Neural Models {index}"} for index in range(100)
    ]

    result = select_anthropic_candidates(jobs, tracked_job_ids=set())

    assert result.total_fetched == 100
    assert len(result.selected_job_ids) == 25


def test_anthropic_policy_rejects_invalid_detail_limits() -> None:
    with pytest.raises(ValueError, match="detail limits"):
        select_anthropic_candidates([], tracked_job_ids=set(), max_details=3, new_reserve=4)
