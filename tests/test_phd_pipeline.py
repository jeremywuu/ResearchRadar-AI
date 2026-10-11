from datetime import UTC, datetime
from pathlib import Path

from research_radar.models import OpportunityStatus, PhDOpportunityType, PipelineStatus
from research_radar.pipelines import run_phd_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def phd_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "fictional": True,
        "title": "PhD in Computational Decision Neuroscience",
        "organization": "Northbridge University",
        "official_opportunity_id": "NBU-CDN",
        "source_url": "https://graduate.northbridge.example/phd/cdn-2027",
        "country": "UK",
        "region": "Europe",
        "research_areas": ["Computational Neuroscience", "Decision-making"],
        "opportunity_type": "Advertised PhD position",
        "opportunity_status": "Confirmed Open",
        "target_cycle": "Fall 2027",
        "supervisor": "Dr. Rowan Vale",
        "laboratory": "Fictional Decision Lab",
        "funding_status": "Fully funded",
        "deadline": "2027-01-15",
        "source_verification_status": "VERIFIED_OFFICIAL",
    }
    record.update(overrides)
    return record


def test_phd_pipeline_preserves_status_type_cycle_and_unknown_funding() -> None:
    report = run_phd_pipeline(
        [
            phd_record(),
            phd_record(
                title="PI recruitment signal for reinforcement learning",
                official_opportunity_id=None,
                source_url="https://lab.northbridge.example/join",
                opportunity_type="Individual PI recruitment announcement",
                opportunity_status="Potential Signal",
                target_cycle="Fall 2028",
                funding_status=None,
            ),
            phd_record(
                title="Historical computational neuroscience recruitment",
                official_opportunity_id="NBU-HIST-2025",
                source_url="https://graduate.northbridge.example/archive/2025",
                opportunity_status="Historical Only",
                target_cycle="Fall 2025",
            ),
        ],
        config_dir=PROJECT_ROOT / "config",
        observed_at=NOW,
    )

    assert report.status is PipelineStatus.SUCCESS
    assert report.records_accepted == 3
    open_record = report.records[0].opportunity
    assert open_record.opportunity_status is OpportunityStatus.CONFIRMED_OPEN
    assert open_record.opportunity_type is PhDOpportunityType.ADVERTISED_POSITION
    assert open_record.target_cycle == "Fall 2027"

    signal = next(item.opportunity for item in report.records if "signal" in item.opportunity.title)
    assert signal.opportunity_status is OpportunityStatus.POTENTIAL_SIGNAL
    assert signal.funding_status is None
    assert "FUNDING_UNKNOWN" in signal.review_flags


def test_phd_deduplication_merges_sources_but_keeps_admission_cycles_separate() -> None:
    duplicate = phd_record(source_url="https://department.northbridge.example/cdn-2027")
    later_cycle = phd_record(
        source_url="https://graduate.northbridge.example/phd/cdn-2028",
        target_cycle="Fall 2028",
    )
    report = run_phd_pipeline(
        [phd_record(), duplicate, later_cycle],
        config_dir=PROJECT_ROOT / "config",
        observed_at=NOW,
    )

    assert report.duplicates_found == 1
    assert len(report.records) == 2
    assert len({item.opportunity.opportunity_id for item in report.records}) == 2
    cycle_2027 = next(
        item.opportunity for item in report.records if item.opportunity.target_cycle == "Fall 2027"
    )
    assert len(cycle_2027.source_urls) == 2


def test_malformed_phd_record_is_reported_without_fabricating_missing_fields() -> None:
    malformed = phd_record()
    malformed.pop("source_url")
    report = run_phd_pipeline(
        [phd_record(), malformed],
        config_dir=PROJECT_ROOT / "config",
        observed_at=NOW,
    )

    assert report.status is PipelineStatus.PARTIAL
    assert report.records_accepted == 1
    assert len(report.validation_errors) == 1
