from datetime import UTC, datetime

import pytest

from research_radar.models import (
    CompensationDisclosureStatus,
    IndustryJob,
    PreferenceFeedback,
    SourceVerificationStatus,
    UserFeedback,
)

NOW = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)


def make_job(**overrides: object) -> IndustryJob:
    values: dict[str, object] = {
        "title": "Research Scientist",
        "organization": "Example Research",
        "source_url": "https://example.com/jobs/123",
        "first_seen_at": NOW,
        "last_seen_at": NOW,
        "source_verification_status": SourceVerificationStatus.VERIFIED_OFFICIAL,
    }
    values.update(overrides)
    return IndustryJob(**values)  # type: ignore[arg-type]


def test_required_model_fields_are_enforced() -> None:
    with pytest.raises(TypeError):
        IndustryJob()  # type: ignore[call-arg]


def test_missing_optional_information_is_preserved_as_none() -> None:
    job = make_job()

    assert job.base_salary_min is None
    assert job.total_compensation_min is None
    assert job.compensation_disclosure_status is CompensationDisclosureStatus.NOT_DISCLOSED
    assert job.working_language is None


def test_stable_identifier_is_repeatable_across_cosmetic_text_changes() -> None:
    first = make_job()
    second = make_job(
        title="  research scientist ",
        organization="EXAMPLE RESEARCH",
        source_url="https://example.com/jobs/123/",
    )

    assert first.opportunity_id == second.opportunity_id
    assert first.opportunity_id.startswith("job_")


def test_last_seen_cannot_precede_first_seen() -> None:
    with pytest.raises(ValueError, match="last_seen_at"):
        make_job(last_seen_at=datetime(2026, 10, 10, 9, 0, tzinfo=UTC))


def test_feedback_preference_bookmark_and_visibility_are_independent() -> None:
    feedback = UserFeedback(
        opportunity_id="job_123",
        preference=PreferenceFeedback.INTERESTED,
        saved=True,
        hidden=True,
        updated_at=NOW,
    )

    assert feedback.preference is PreferenceFeedback.INTERESTED
    assert feedback.saved is True
    assert feedback.hidden is True

    bookmark_only = UserFeedback(
        opportunity_id="job_456",
        preference=None,
        saved=True,
        hidden=False,
        updated_at=NOW,
    )
    assert bookmark_only.preference is None
    assert bookmark_only.saved is True
