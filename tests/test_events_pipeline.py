from datetime import UTC, datetime
from pathlib import Path

from research_radar.models import AcademicEventType, PipelineStatus
from research_radar.pipelines import run_events_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def event_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "fictional": True,
        "title": "European Computational Neuroscience Forum 2027",
        "series_name": "European Computational Neuroscience Forum",
        "edition_year": 2027,
        "organization": "Fictional Neuroscience Society",
        "source_url": "https://events.neuro-forum.example/2027",
        "official_url": "https://events.neuro-forum.example/2027",
        "event_type": "Academic conference",
        "country": "Belgium",
        "region": "Europe",
        "location": "Brussels, Belgium",
        "research_areas": ["Computational Neuroscience", "Neural representations"],
        "starts_on": "2027-03-10",
        "ends_on": "2027-03-13",
        "submission_deadline": "2026-11-01",
        "registration_deadline": "2027-02-01",
        "source_verification_status": "VERIFIED_OFFICIAL",
    }
    record.update(overrides)
    return record


def test_event_pipeline_classifies_and_scores_with_fixed_reference_date() -> None:
    europe = event_record()
    north_america = event_record(
        title="North American AI Research Meeting 2027",
        series_name="North American AI Research Meeting",
        source_url="https://events.ai-meeting.example/2027",
        official_url="https://events.ai-meeting.example/2027",
        country="Canada",
        region="North America",
        location="Toronto, Canada",
        research_areas=["Artificial Intelligence", "Machine Learning"],
        event_type="Workshop",
    )
    report = run_events_pipeline(
        [europe, north_america],
        config_dir=PROJECT_ROOT / "config",
        observed_at=NOW,
        reference_date=NOW.date(),
    )

    assert report.status is PipelineStatus.SUCCESS
    assert report.records_accepted == 2
    first = next(item for item in report.records if "European" in item.opportunity.title)
    second = next(item for item in report.records if "North American" in item.opportunity.title)
    assert first.opportunity.academic_event_type is AcademicEventType.ACADEMIC_CONFERENCE
    assert second.opportunity.academic_event_type is AcademicEventType.WORKSHOP
    assert (
        first.score.components["geographic_priority"]
        > second.score.components["geographic_priority"]
    )
    assert first.score.components["deadline_relevance"] == 100


def test_recurring_event_editions_are_separate_while_same_edition_sources_merge() -> None:
    duplicate = event_record(source_url="https://society.neuro-forum.example/events/2027")
    prior_edition = event_record(
        title="European Computational Neuroscience Forum 2026",
        edition_year=2026,
        source_url="https://events.neuro-forum.example/2026",
        official_url="https://events.neuro-forum.example/2026",
        starts_on="2026-03-10",
        ends_on="2026-03-13",
        submission_deadline="2025-11-01",
        registration_deadline="2026-02-01",
    )
    report = run_events_pipeline(
        [event_record(), duplicate, prior_edition],
        config_dir=PROJECT_ROOT / "config",
        observed_at=NOW,
        reference_date=NOW.date(),
    )

    assert report.duplicates_found == 1
    assert len(report.records) == 2
    assert {item.opportunity.edition_year for item in report.records} == {2026, 2027}
    assert len({item.opportunity.opportunity_id for item in report.records}) == 2


def test_malformed_event_is_reported_as_partial_failure() -> None:
    malformed = event_record(starts_on="not-a-date")
    report = run_events_pipeline(
        [event_record(), malformed],
        config_dir=PROJECT_ROOT / "config",
        observed_at=NOW,
        reference_date=NOW.date(),
    )

    assert report.status is PipelineStatus.PARTIAL
    assert report.records_accepted == 1
    assert len(report.validation_errors) == 1
