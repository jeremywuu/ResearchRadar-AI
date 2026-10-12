"""Versioned source observations and conservative cross-snapshot reconciliation."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any

from research_radar.collectors.base import OfficialSourceAdapter
from research_radar.collectors.official import AnthropicGreenhouseAdapter
from research_radar.collectors.service import LiveCollectionReport, collect_live, default_adapters

if TYPE_CHECKING:
    from research_radar.live_integration import IncrementalLiveSyncPlan


class FreshObservationError(ValueError):
    """Raised when source snapshots cannot be reconciled safely."""


class FreshObservationStatus(StrEnum):
    NEW = "NEW"
    UNCHANGED = "UNCHANGED"
    CONTENT_CHANGED = "CONTENT_CHANGED"
    OBSERVATION_ONLY_CHANGED = "OBSERVATION_ONLY_CHANGED"
    NOT_OBSERVED = "NOT_OBSERVED"
    CONFIRMED_CLOSED = "CONFIRMED_CLOSED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass(frozen=True)
class FieldChange:
    field_name: str
    previous_value: Any
    current_value: Any


@dataclass(frozen=True)
class OpportunityObservationChange:
    record_id: str
    category: str
    organization: str
    title: str
    status: FreshObservationStatus
    changed_fields: tuple[FieldChange, ...]
    official_url: str | None
    previous_observed_at: str | None
    current_observed_at: str | None
    source_id: str | None
    reason: str
    event_id: str | None = None


@dataclass(frozen=True)
class FreshObservationAnalysis:
    analyzed_at: datetime
    changes: tuple[OpportunityObservationChange, ...]
    source_metadata: dict[str, Any]

    @property
    def by_record_id(self) -> dict[str, OpportunityObservationChange]:
        return {change.record_id: change for change in self.changes}

    @property
    def counts(self) -> dict[FreshObservationStatus, int]:
        return {
            status: sum(change.status is status for change in self.changes)
            for status in FreshObservationStatus
        }


@dataclass(frozen=True)
class FreshCollectionRun:
    archive_dir: Path
    fresh_dir: Path
    analysis_path: Path
    collection: LiveCollectionReport
    analysis: FreshObservationAnalysis


_SNAPSHOT_FILES = ("jobs.json", "phd.json", "events.json", "source_metadata.json")
_OBSERVATION_FIELDS = {
    "first_seen_at",
    "last_seen_at",
    "content_updated_at",
    "retrieved_at",
    "source_retrieved_at",
}
_NON_SOURCE_FIELDS = {
    "classification",
    "english_compatibility",
    "review_flags",
    "source_verification_status",
    "original_values",
}
_UNAVAILABLE_HEALTH = {"FAILED", "BLOCKED", "UNSUPPORTED", "PARTIAL"}


def collect_fresh_observation(
    *,
    project_root: Path,
    live_dir: Path,
    history_root: Path,
    observations_root: Path,
    observed_at: datetime,
    reference_date: date,
    adapters: dict[str, OfficialSourceAdapter] | None = None,
) -> FreshCollectionRun:
    """Archive the current state, collect each existing source once, and reconcile locally."""

    archive_dir = archive_live_snapshot(live_dir, history_root, archived_at=observed_at)
    version = observed_at.strftime("%Y%m%dT%H%M%S.%fZ")
    fresh_dir = observations_root / version
    if fresh_dir.exists():
        raise FileExistsError(f"fresh observation directory already exists: {fresh_dir}")
    selected_adapters = adapters
    if selected_adapters is None:
        selected_adapters = default_adapters()
        selected_adapters[AnthropicGreenhouseAdapter.source.source_id] = AnthropicGreenhouseAdapter(
            tracked_job_ids=_tracked_job_ids(live_dir)
        )
    collection = collect_live(
        ("jobs", "phd", "events"),
        project_root=project_root,
        output_dir=fresh_dir,
        observed_at=observed_at,
        reference_date=reference_date,
        adapters=selected_adapters,
    )
    analysis = reconcile_fresh_observations(
        archive_dir,
        fresh_dir,
        live_dir,
        analyzed_at=observed_at,
    )
    analysis_path = fresh_dir / "observation_analysis.json"
    _write_analysis(analysis_path, analysis)
    return FreshCollectionRun(
        archive_dir=archive_dir,
        fresh_dir=fresh_dir,
        analysis_path=analysis_path,
        collection=collection,
        analysis=analysis,
    )


def archive_live_snapshot(
    source_dir: Path,
    archive_root: Path,
    *,
    archived_at: datetime,
) -> Path:
    """Copy the complete current snapshot into a non-overwriting version directory."""

    if archived_at.tzinfo is None:
        raise FreshObservationError("archived_at must be timezone-aware")
    missing = [name for name in _SNAPSHOT_FILES if not (source_dir / name).is_file()]
    if missing:
        raise FreshObservationError("snapshot is incomplete: " + ", ".join(missing))
    version = archived_at.strftime("%Y%m%dT%H%M%S.%fZ")
    destination = archive_root / version
    destination.mkdir(parents=True, exist_ok=False)
    for name in _SNAPSHOT_FILES:
        shutil.copy2(source_dir / name, destination / name)
    return destination


def reconcile_fresh_observations(
    previous_dir: Path,
    fresh_dir: Path,
    output_dir: Path,
    *,
    analyzed_at: datetime,
) -> FreshObservationAnalysis:
    """Compare a fresh bounded observation and write a conservative current snapshot."""

    if analyzed_at.tzinfo is None:
        raise FreshObservationError("analyzed_at must be timezone-aware")
    previous_metadata = _read_object(previous_dir / "source_metadata.json")
    fresh_metadata = _read_object(fresh_dir / "source_metadata.json")
    changes: list[OpportunityObservationChange] = []
    output_dir.mkdir(parents=True, exist_ok=True)

    for category in ("jobs", "phd", "events"):
        previous_payload = _read_category(previous_dir / f"{category}.json", category)
        fresh_payload = _read_category(fresh_dir / f"{category}.json", category)
        previous_records, previous_duplicates = _index_records(previous_payload["records"])
        fresh_records, fresh_duplicates = _index_records(fresh_payload["records"])
        duplicate_ids = previous_duplicates | fresh_duplicates
        reconciled: list[dict[str, Any]] = []

        for record_id, current in fresh_records.items():
            prior = previous_records.get(record_id)
            if record_id in duplicate_ids:
                selected = prior or current
                reconciled.append(selected)
                changes.append(
                    _change(
                        selected,
                        category,
                        FreshObservationStatus.NEEDS_REVIEW,
                        reason="duplicate Record_ID in an observation snapshot",
                    )
                )
                continue
            if prior is None:
                reconciled.append(current)
                changes.append(
                    _change(
                        current,
                        category,
                        FreshObservationStatus.NEW,
                        reason="stable Record_ID was not present in the previous snapshot",
                        event_kind="NEW_OPPORTUNITY",
                    )
                )
                continue
            reconciled_record, observation_change = _reconcile_matching(
                prior,
                current,
                category,
            )
            reconciled.append(reconciled_record)
            changes.append(observation_change)

        for record_id, prior in previous_records.items():
            if record_id in fresh_records or record_id in duplicate_ids:
                continue
            source_id = _opportunity(prior).get("adapter_source_id")
            health = _source_health(fresh_metadata, source_id)
            status = (
                FreshObservationStatus.SOURCE_UNAVAILABLE
                if health in _UNAVAILABLE_HEALTH or health is None
                else FreshObservationStatus.NOT_OBSERVED
            )
            reason = (
                f"source health was {health or 'UNKNOWN'}; previous facts were retained"
                if status is FreshObservationStatus.SOURCE_UNAVAILABLE
                else "record was outside or absent from this bounded successful observation"
            )
            reconciled.append(prior)
            changes.append(
                _change(
                    prior,
                    category,
                    status,
                    reason=reason,
                    previous=prior,
                    current_observed=False,
                )
            )

        fresh_payload["records"] = reconciled
        fresh_payload["summary"] = {
            **fresh_payload.get("summary", {}),
            "records_reconciled": len(reconciled),
            "previous_records_preserved": sum(
                item.status
                in {FreshObservationStatus.NOT_OBSERVED, FreshObservationStatus.SOURCE_UNAVAILABLE}
                and item.category == category
                for item in changes
            ),
        }
        _write_object(output_dir / f"{category}.json", fresh_payload)

    metadata = {
        **fresh_metadata,
        "observation_reconciliation": {
            "analyzed_at": analyzed_at.isoformat(),
            "previous_source_retrievals": _source_retrievals(previous_metadata),
            "statuses": {
                status.value: sum(change.status is status for change in changes)
                for status in FreshObservationStatus
            },
        },
    }
    _write_object(output_dir / "source_metadata.json", metadata)
    return FreshObservationAnalysis(analyzed_at, tuple(changes), metadata)


def load_fresh_observation_analysis(path: Path) -> FreshObservationAnalysis:
    """Load the ignored machine-readable comparison artifact for review generation."""

    payload = _read_object(path)
    try:
        changes = tuple(
            OpportunityObservationChange(
                record_id=item["record_id"],
                category=item["category"],
                organization=item["organization"],
                title=item["title"],
                status=FreshObservationStatus(item["status"]),
                changed_fields=tuple(FieldChange(**field) for field in item["changed_fields"]),
                official_url=item.get("official_url"),
                previous_observed_at=item.get("previous_observed_at"),
                current_observed_at=item.get("current_observed_at"),
                source_id=item.get("source_id"),
                reason=item["reason"],
                event_id=item.get("event_id"),
            )
            for item in payload["changes"]
        )
        analyzed_at = datetime.fromisoformat(payload["analyzed_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FreshObservationError(f"invalid observation analysis: {path}") from exc
    return FreshObservationAnalysis(analyzed_at, changes, {})


def write_fresh_collection_review(
    analysis: FreshObservationAnalysis,
    plan: IncrementalLiveSyncPlan,
    output_path: Path,
) -> Path:
    """Render collection, source-change, Sheets-plan, and feedback evidence for human review."""

    preview = plan.preview
    lines = [
        "# Fresh Official Source Collection Review",
        "",
        f"Generated: `{analysis.analyzed_at.isoformat()}`",
        "",
        "No Google Sheets writes were performed. This report describes a read-only plan.",
        "",
        "## A. Collection Summary",
        "",
        "| Source | Health | Fetched | Title matched | Detail selected | Extracted | "
        "Accepted | Rejected | Retrieved |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    sources = analysis.source_metadata.get("sources", {})
    pipelines = analysis.source_metadata.get("pipelines", {})
    for source_id, source in sorted(sources.items()):
        descriptor = source.get("source", {})
        category = descriptor.get("category", "")
        pipeline = pipelines.get(category, {})
        lines.append(
            "| "
            + " | ".join(
                (
                    str(source_id),
                    str(source.get("health", "UNKNOWN")),
                    str(source.get("records_fetched", 0)),
                    str(source.get("records_matched", 0)),
                    str(source.get("records_considered", 0)),
                    str(len(source.get("records", []))),
                    str(pipeline.get("records_accepted", 0)),
                    str(pipeline.get("records_rejected", 0)),
                    str(source.get("retrieved_at", "")),
                )
            )
            + " |"
        )

    lines.extend(["", "## B. Opportunity Changes", ""])
    for status in FreshObservationStatus:
        matching = [item for item in analysis.changes if item.status is status]
        lines.append(f"### {status.value} ({len(matching)})")
        lines.append("")
        if not matching:
            lines.append("None.")
            lines.append("")
            continue
        for item in matching:
            lines.append(f"- `{item.record_id}` — {item.organization}: {item.title}. {item.reason}")
            for field in item.changed_fields:
                lines.append(
                    f"  - `{field.field_name}`: `{field.previous_value}` → `{field.current_value}`"
                )
        lines.append("")

    lines.extend(["## C. Proposed Sheets Operations", ""])
    for category, sheet_plan in preview.workbook.plans.items():
        lines.append(
            f"- {category}: insert={sheet_plan.insert_count}, update={sheet_plan.update_count}, "
            f"unchanged={sheet_plan.unchanged_count}, invalid={sheet_plan.invalid_count}, "
            f"conflicts={sheet_plan.conflict_count}"
        )
    lines.extend(
        [
            f"- watchlist: insert={preview.watchlist_plan.insert_count}, "
            f"update={preview.watchlist_plan.update_count}, "
            f"unchanged={preview.watchlist_plan.unchanged_count}",
            f"- feedback: loaded={len(preview.feedback.feedback_by_id)}, "
            f"invalid={len(preview.feedback.invalid_records)}, "
            f"conflicts={len(preview.feedback.conflicts)}, "
            f"template_rows={preview.feedback.template_rows_ignored}",
            f"- plan fingerprint: `{plan.plan_fingerprint}`",
            "",
            "## D. Evidence for New or Meaningfully Changed Records",
            "",
        ]
    )
    evidence_changes = [
        item
        for item in analysis.changes
        if item.status
        in {
            FreshObservationStatus.NEW,
            FreshObservationStatus.CONTENT_CHANGED,
            FreshObservationStatus.CONFIRMED_CLOSED,
        }
    ]
    if not evidence_changes:
        lines.append("No new or meaningfully changed official-source records were detected.")
    for item in evidence_changes:
        url = item.official_url or "unknown"
        lines.append(
            f"- `{item.record_id}` [{item.title}]({url}): {item.status.value}; {item.reason}"
        )

    unsafe = [
        item
        for item in analysis.changes
        if item.status
        in {
            FreshObservationStatus.NEEDS_REVIEW,
            FreshObservationStatus.SOURCE_UNAVAILABLE,
            FreshObservationStatus.NOT_OBSERVED,
        }
    ]
    lines.extend(["", "## E. Recommendations", ""])
    if preview.workbook.failures or unsafe:
        lines.append(
            "Only inserts or updates already present in the fingerprinted plan are candidates for "
            "a separately authorized synchronization. NOT_OBSERVED, SOURCE_UNAVAILABLE, and "
            "NEEDS_REVIEW states must not cause closure or deletion."
        )
    else:
        lines.append(
            "The read-only plan has no unresolved source-observation safety state. Any write still "
            "requires separate fingerprint-bound authorization."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _reconcile_matching(
    previous: dict[str, Any],
    current: dict[str, Any],
    category: str,
) -> tuple[dict[str, Any], OpportunityObservationChange]:
    old = _opportunity(previous)
    new = _opportunity(current)
    new["first_seen_at"] = old.get("first_seen_at", new.get("first_seen_at"))
    if current.get("feedback") is None and previous.get("feedback") is not None:
        current["feedback"] = previous["feedback"]
        current["personalized_score"] = previous.get("personalized_score")

    field_changes = _meaningful_changes(old, new)
    explicit_status = str(new.get("opportunity_status") or "").strip().upper()
    if explicit_status in {"CLOSED", "CONFIRMED_CLOSED"}:
        status = FreshObservationStatus.CONFIRMED_CLOSED
        reason = "fresh official record explicitly states a closed status"
        event_kind = "STATUS_CHANGE"
    elif field_changes:
        status = FreshObservationStatus.CONTENT_CHANGED
        reason = "one or more meaningful source fields changed"
        event_kind = "UPDATED_OPPORTUNITY"
    else:
        new["content_updated_at"] = old.get("content_updated_at")
        if _canonical(new.get("last_seen_at")) != _canonical(old.get("last_seen_at")):
            status = FreshObservationStatus.OBSERVATION_ONLY_CHANGED
            reason = "the opportunity was observed again without meaningful content changes"
        else:
            status = FreshObservationStatus.UNCHANGED
            reason = "no source content or observation timestamp changed"
        event_kind = None
    return current, _change(
        current,
        category,
        status,
        changed_fields=field_changes,
        previous=previous,
        reason=reason,
        event_kind=event_kind,
    )


def _meaningful_changes(old: dict[str, Any], new: dict[str, Any]) -> tuple[FieldChange, ...]:
    keys = sorted((set(old) | set(new)) - _OBSERVATION_FIELDS - _NON_SOURCE_FIELDS)
    return tuple(
        FieldChange(key, old.get(key), new.get(key))
        for key in keys
        if _canonical(old.get(key)) != _canonical(new.get(key))
    )


def _change(
    record: dict[str, Any],
    category: str,
    status: FreshObservationStatus,
    *,
    reason: str,
    changed_fields: tuple[FieldChange, ...] = (),
    previous: dict[str, Any] | None = None,
    event_kind: str | None = None,
    current_observed: bool = True,
) -> OpportunityObservationChange:
    opportunity = _opportunity(record)
    prior = _opportunity(previous) if previous is not None else {}
    record_id = str(opportunity.get("opportunity_id") or "")
    event_id = None
    if event_kind:
        body = json.dumps(
            {
                "record_id": record_id,
                "event_kind": event_kind,
                "changes": [
                    [
                        item.field_name,
                        _canonical(item.previous_value),
                        _canonical(item.current_value),
                    ]
                    for item in changed_fields
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        event_id = "change_" + sha256(body.encode()).hexdigest()[:16]
    return OpportunityObservationChange(
        record_id=record_id,
        category=category,
        organization=str(opportunity.get("organization") or ""),
        title=str(opportunity.get("title") or ""),
        status=status,
        changed_fields=changed_fields,
        official_url=opportunity.get("source_url") or opportunity.get("official_source_url"),
        previous_observed_at=prior.get("last_seen_at"),
        current_observed_at=(opportunity.get("last_seen_at") if current_observed else None),
        source_id=opportunity.get("adapter_source_id"),
        reason=reason,
        event_id=event_id,
    )


def _index_records(
    records: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    indexed: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for record in records:
        record_id = _opportunity(record).get("opportunity_id")
        if not isinstance(record_id, str) or not record_id:
            raise FreshObservationError("snapshot record is missing a stable opportunity_id")
        if record_id in indexed:
            duplicates.add(record_id)
            continue
        indexed[record_id] = record
    return indexed, duplicates


def _opportunity(record: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(record, dict) or not isinstance(record.get("opportunity"), dict):
        raise FreshObservationError("snapshot contains a malformed processed record")
    return record["opportunity"]


def _source_health(metadata: dict[str, Any], source_id: Any) -> str | None:
    sources = metadata.get("sources", {})
    source = sources.get(source_id) if isinstance(sources, dict) else None
    health = source.get("health") if isinstance(source, dict) else None
    return str(health).upper() if health else None


def _source_retrievals(metadata: dict[str, Any]) -> dict[str, Any]:
    sources = metadata.get("sources", {})
    if not isinstance(sources, dict):
        return {}
    return {
        source_id: source.get("retrieved_at")
        for source_id, source in sources.items()
        if isinstance(source, dict)
    }


def _tracked_job_ids(live_dir: Path) -> set[str]:
    payload = _read_category(live_dir / "jobs.json", "jobs")
    return {
        str(_opportunity(record)["official_job_id"])
        for record in payload["records"]
        if _opportunity(record).get("official_job_id")
    }


def _canonical(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def _read_category(path: Path, category: str) -> dict[str, Any]:
    payload = _read_object(path)
    if payload.get("category") != category or not isinstance(payload.get("records"), list):
        raise FreshObservationError(f"invalid {category} snapshot: {path}")
    return payload


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FreshObservationError(f"required snapshot file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise FreshObservationError(f"snapshot is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise FreshObservationError(f"snapshot root must be an object: {path}")
    return payload


def _write_object(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_analysis(path: Path, analysis: FreshObservationAnalysis) -> None:
    payload = {
        "analyzed_at": analysis.analyzed_at.isoformat(),
        "counts": {status.value: count for status, count in analysis.counts.items()},
        "changes": [
            {
                **asdict(change),
                "status": change.status.value,
            }
            for change in analysis.changes
        ],
    }
    _write_object(path, payload)
