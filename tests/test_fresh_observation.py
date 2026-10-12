from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_radar.fresh_observation import (
    FreshObservationStatus,
    archive_live_snapshot,
    reconcile_fresh_observations,
    write_fresh_collection_review,
)

OLD = datetime(2026, 10, 11, 21, 5, tzinfo=UTC)
NEW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def _record(
    record_id: str,
    *,
    title: str = "Research Scientist",
    last_seen: datetime = OLD,
    content_updated: datetime = OLD,
    status: str = "CONFIRMED_OPEN",
    salary: str | None = None,
    education: str = "PHD_REQUIRED",
    deadline: str | None = None,
    feedback: dict | None = None,
) -> dict:
    return {
        "opportunity": {
            "opportunity_id": record_id,
            "title": title,
            "organization": "Anthropic",
            "source_url": f"https://example.org/jobs/{record_id}",
            "official_source_url": "https://www.anthropic.com/careers/jobs",
            "adapter_source_id": "anthropic_greenhouse",
            "first_seen_at": OLD.isoformat(),
            "last_seen_at": last_seen.isoformat(),
            "content_updated_at": content_updated.isoformat(),
            "retrieved_at": last_seen.isoformat(),
            "source_retrieved_at": last_seen.isoformat(),
            "opportunity_status": status,
            "original_salary_text": salary,
            "education_requirement": education,
            "deadline": deadline,
            "source_evidence": [f"Title: {title}"],
            "original_values": {"fictional": False, "title": title},
        },
        "score": {"final_score": 90},
        "feedback": feedback,
    }


def _write_snapshot(
    root: Path,
    records: list[dict],
    *,
    health: str = "SUCCESS",
    fetched: int = 100,
    considered: int = 25,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for category in ("jobs", "phd", "events"):
        category_records = records if category == "jobs" else []
        (root / f"{category}.json").write_text(
            json.dumps(
                {
                    "category": category,
                    "pipeline_status": "SUCCESS",
                    "summary": {},
                    "records": category_records,
                }
            ),
            encoding="utf-8",
        )
    metadata = {
        "sources": {
            "anthropic_greenhouse": {
                "source": {"source_id": "anthropic_greenhouse", "category": "jobs"},
                "health": health,
                "retrieved_at": NEW.isoformat(),
                "records_fetched": fetched,
                "records_considered": considered,
                "records": [],
                "errors": [],
            }
        },
        "pipelines": {
            "jobs": {
                "status": "SUCCESS",
                "records_fetched": fetched,
                "records_extracted": len(records),
                "records_accepted": len(records),
                "records_rejected": 0,
                "records_excluded": 0,
            }
        },
    }
    (root / "source_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


def test_archive_preserves_previous_snapshot_without_overwrite(tmp_path: Path) -> None:
    live = tmp_path / "live"
    _write_snapshot(live, [_record("job_1")])

    archived = archive_live_snapshot(live, tmp_path / "history", archived_at=NEW)

    assert (archived / "jobs.json").read_text() == (live / "jobs.json").read_text()
    with pytest.raises(FileExistsError):
        archive_live_snapshot(live, tmp_path / "history", archived_at=NEW)


def test_fresh_observation_preserves_first_seen_and_advances_last_seen(tmp_path: Path) -> None:
    previous, fresh, live = tmp_path / "previous", tmp_path / "fresh", tmp_path / "live"
    _write_snapshot(previous, [_record("job_1")])
    _write_snapshot(fresh, [_record("job_1", last_seen=NEW, content_updated=NEW)])

    analysis = reconcile_fresh_observations(previous, fresh, live, analyzed_at=NEW)

    change = analysis.by_record_id["job_1"]
    assert change.status is FreshObservationStatus.OBSERVATION_ONLY_CHANGED
    saved = json.loads((live / "jobs.json").read_text())["records"][0]["opportunity"]
    assert saved["first_seen_at"] == OLD.isoformat()
    assert saved["last_seen_at"] == NEW.isoformat()
    assert saved["content_updated_at"] == OLD.isoformat()


@pytest.mark.parametrize(
    ("field", "old_value", "new_value"),
    [
        ("salary", "$150,000", "$175,000"),
        ("education", "PHD_PREFERRED", "PHD_REQUIRED"),
        ("deadline", "2026-11-01", "2026-11-15"),
    ],
)
def test_material_field_changes_are_reported(
    tmp_path: Path, field: str, old_value: str, new_value: str
) -> None:
    previous, fresh, live = tmp_path / "previous", tmp_path / "fresh", tmp_path / "live"
    old_kwargs = {field: old_value}
    new_kwargs = {field: new_value, "last_seen": NEW, "content_updated": NEW}
    _write_snapshot(previous, [_record("job_1", **old_kwargs)])
    _write_snapshot(fresh, [_record("job_1", **new_kwargs)])

    analysis = reconcile_fresh_observations(previous, fresh, live, analyzed_at=NEW)

    change = analysis.by_record_id["job_1"]
    assert change.status is FreshObservationStatus.CONTENT_CHANGED
    assert any(item.field_name for item in change.changed_fields)


def test_whitespace_only_change_is_observation_only(tmp_path: Path) -> None:
    previous, fresh, live = tmp_path / "previous", tmp_path / "fresh", tmp_path / "live"
    _write_snapshot(previous, [_record("job_1", title="Research Scientist")])
    _write_snapshot(
        fresh,
        [_record("job_1", title=" Research   Scientist ", last_seen=NEW, content_updated=NEW)],
    )

    analysis = reconcile_fresh_observations(previous, fresh, live, analyzed_at=NEW)

    assert analysis.by_record_id["job_1"].status is (
        FreshObservationStatus.OBSERVATION_ONLY_CHANGED
    )


def test_new_opportunity_is_detected_without_duplicate_ids(tmp_path: Path) -> None:
    previous, fresh, live = tmp_path / "previous", tmp_path / "fresh", tmp_path / "live"
    _write_snapshot(previous, [_record("job_1")])
    _write_snapshot(fresh, [_record("job_1", last_seen=NEW), _record("job_2", last_seen=NEW)])

    analysis = reconcile_fresh_observations(previous, fresh, live, analyzed_at=NEW)

    assert analysis.by_record_id["job_2"].status is FreshObservationStatus.NEW
    saved = json.loads((live / "jobs.json").read_text())["records"]
    assert [item["opportunity"]["opportunity_id"] for item in saved] == ["job_1", "job_2"]


def test_candidate_cap_missing_job_is_preserved_as_not_observed(tmp_path: Path) -> None:
    previous, fresh, live = tmp_path / "previous", tmp_path / "fresh", tmp_path / "live"
    feedback = {"preference": "INTERESTED", "saved": True, "hidden": False, "notes": "keep"}
    _write_snapshot(previous, [_record("job_1", feedback=feedback)])
    _write_snapshot(fresh, [], fetched=700, considered=25)

    analysis = reconcile_fresh_observations(previous, fresh, live, analyzed_at=NEW)

    change = analysis.by_record_id["job_1"]
    assert change.status is FreshObservationStatus.NOT_OBSERVED
    assert change.previous_observed_at == OLD.isoformat()
    assert change.current_observed_at is None
    saved = json.loads((live / "jobs.json").read_text())["records"][0]
    assert saved["feedback"] == feedback
    assert saved["opportunity"]["last_seen_at"] == OLD.isoformat()
    assert saved["opportunity"]["opportunity_status"] == "CONFIRMED_OPEN"


@pytest.mark.parametrize("health", ["FAILED", "BLOCKED", "PARTIAL"])
def test_unavailable_source_preserves_record_and_status(tmp_path: Path, health: str) -> None:
    previous, fresh, live = tmp_path / "previous", tmp_path / "fresh", tmp_path / "live"
    _write_snapshot(previous, [_record("job_1")])
    _write_snapshot(fresh, [], health=health)

    analysis = reconcile_fresh_observations(previous, fresh, live, analyzed_at=NEW)

    assert analysis.by_record_id["job_1"].status is FreshObservationStatus.SOURCE_UNAVAILABLE
    assert analysis.by_record_id["job_1"].previous_observed_at == OLD.isoformat()
    assert analysis.by_record_id["job_1"].current_observed_at is None
    saved = json.loads((live / "jobs.json").read_text())["records"][0]["opportunity"]
    assert saved["opportunity_status"] == "CONFIRMED_OPEN"


def test_explicit_official_closure_is_distinct_from_missing(tmp_path: Path) -> None:
    previous, fresh, live = tmp_path / "previous", tmp_path / "fresh", tmp_path / "live"
    _write_snapshot(previous, [_record("job_1")])
    _write_snapshot(fresh, [_record("job_1", status="CLOSED", last_seen=NEW)])

    analysis = reconcile_fresh_observations(previous, fresh, live, analyzed_at=NEW)

    assert analysis.by_record_id["job_1"].status is FreshObservationStatus.CONFIRMED_CLOSED


def test_duplicate_record_id_becomes_review_issue_without_overwrite(tmp_path: Path) -> None:
    previous, fresh, live = tmp_path / "previous", tmp_path / "fresh", tmp_path / "live"
    _write_snapshot(previous, [_record("job_1")])
    _write_snapshot(fresh, [_record("job_1"), _record("job_1", title="Different")])

    analysis = reconcile_fresh_observations(previous, fresh, live, analyzed_at=NEW)

    assert analysis.by_record_id["job_1"].status is FreshObservationStatus.NEEDS_REVIEW
    assert len(json.loads((live / "jobs.json").read_text())["records"]) == 1


def test_change_event_id_is_deterministic_across_retry(tmp_path: Path) -> None:
    previous, fresh = tmp_path / "previous", tmp_path / "fresh"
    _write_snapshot(previous, [_record("job_1", salary="$150,000")])
    _write_snapshot(
        fresh,
        [_record("job_1", salary="$175,000", last_seen=NEW, content_updated=NEW)],
    )

    first = reconcile_fresh_observations(previous, fresh, tmp_path / "live1", analyzed_at=NEW)
    second = reconcile_fresh_observations(previous, fresh, tmp_path / "live2", analyzed_at=NEW)

    assert first.by_record_id["job_1"].event_id == second.by_record_id["job_1"].event_id


def test_human_review_report_contains_plan_and_evidence(tmp_path: Path) -> None:
    previous, fresh, live = tmp_path / "previous", tmp_path / "fresh", tmp_path / "live"
    _write_snapshot(previous, [])
    _write_snapshot(fresh, [_record("job_2", last_seen=NEW)])
    analysis = reconcile_fresh_observations(previous, fresh, live, analyzed_at=NEW)
    sheet_plan = SimpleNamespace(
        insert_count=1,
        update_count=0,
        unchanged_count=0,
        invalid_count=0,
        conflict_count=0,
    )
    watchlist_plan = SimpleNamespace(insert_count=0, update_count=0, unchanged_count=38)
    feedback = SimpleNamespace(
        feedback_by_id={}, invalid_records=[], conflicts=[], template_rows_ignored=1999
    )
    preview = SimpleNamespace(
        workbook=SimpleNamespace(plans={"jobs": sheet_plan}, failures={}),
        watchlist_plan=watchlist_plan,
        feedback=feedback,
    )
    plan = SimpleNamespace(preview=preview, plan_fingerprint="fresh-fingerprint")

    path = write_fresh_collection_review(analysis, plan, tmp_path / "review.md")
    text = path.read_text()

    assert "Fresh Official Source Collection Review" in text
    assert "job_2" in text
    assert "fresh-fingerprint" in text
    assert "No Google Sheets writes" in text
