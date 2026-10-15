"""Isolated Milestone 6 production-style preview without cloud or Sheets writes."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from research_radar.collectors.base import OfficialSourceAdapter
from research_radar.collectors.pilot import milestone_6_pilot_adapters
from research_radar.collectors.service import LiveCollectionReport, collect_live
from research_radar.fresh_observation import (
    FreshObservationAnalysis,
    FreshObservationStatus,
    OpportunityObservationChange,
    reconcile_fresh_observations,
)
from research_radar.live_integration import IncrementalLiveSyncPlan, prepare_incremental_live_sync
from research_radar.models import IndustryJob, ProcessedOpportunity
from research_radar.storage.durable_state import StateRestoreResult
from research_radar.storage.sheets import SheetsAdapter


class PreviewStateReader(Protocol):
    """Read-only durable-state seam; deliberately exposes no commit operation."""

    def restore(self, target_dir: Path) -> StateRestoreResult: ...


class ResearchRoleFit(StrEnum):
    RESEARCH_ADJACENT_ENGINEERING = "RESEARCH_ADJACENT_ENGINEERING"
    CLINICAL_IMPLEMENTATION = "CLINICAL_IMPLEMENTATION"
    TECHNICAL_PLATFORM = "TECHNICAL_PLATFORM"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class RoleFitAudit:
    record_id: str
    title: str
    official_url: str
    role_fit: ResearchRoleFit
    reason: str
    missing_information: tuple[str, ...]


@dataclass(frozen=True)
class SourceProductionPreview:
    output_dir: Path
    report_path: Path
    weekly_brief_path: Path
    restored: StateRestoreResult
    collection: LiveCollectionReport
    analysis: FreshObservationAnalysis
    pilot_changes: tuple[OpportunityObservationChange, ...]
    duplicate_conflicts: tuple[str, ...]
    sheets_plan: IncrementalLiveSyncPlan
    role_audits: tuple[RoleFitAudit, ...]


def run_source_production_preview(
    *,
    project_root: Path,
    output_dir: Path,
    observed_at: datetime,
    reference_date: date,
    state_reader: PreviewStateReader,
    sheets_adapter: SheetsAdapter,
    adapters: dict[str, OfficialSourceAdapter] | None = None,
) -> SourceProductionPreview:
    """Restore, collect, compare, and plan locally without exposing an apply/commit path."""

    if observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    output_dir.mkdir(parents=True, exist_ok=True)
    restored_dir = output_dir / "restored-state"
    restored = state_reader.restore(restored_dir)
    if not restored.available or not restored.snapshot_id:
        raise ValueError("an authoritative durable baseline is required for production preview")

    pilot_dir = output_dir / "pilot-observations"
    collection = collect_live(
        ("jobs", "phd", "events"),
        project_root=project_root,
        output_dir=pilot_dir,
        observed_at=observed_at,
        reference_date=reference_date,
        adapters=adapters or milestone_6_pilot_adapters(),
    )
    reconciled_dir = output_dir / "reconciled-preview"
    analysis = reconcile_fresh_observations(
        restored_dir,
        pilot_dir,
        reconciled_dir,
        analyzed_at=observed_at,
    )
    pilot_ids = {
        processed.opportunity.opportunity_id
        for report in collection.execution.pipelines.values()
        for processed in report.records
    }
    pilot_changes = tuple(change for change in analysis.changes if change.record_id in pilot_ids)
    duplicate_conflicts = find_semantic_duplicate_conflicts(restored_dir, pilot_dir)
    sheets_plan = prepare_incremental_live_sync(
        project_root=project_root,
        live_data_dir=pilot_dir,
        review_dir=output_dir / "sheets-review",
        generated_at=observed_at,
        reference_date=reference_date,
        adapter=sheets_adapter,
    )
    role_audits = tuple(
        audit_paradromics_role(processed)
        for processed in collection.execution.pipelines["jobs"].records
    )
    report_path = _write_preview_report(
        output_dir / "milestone_6_production_preview.md",
        restored=restored,
        collection=collection,
        analysis=analysis,
        pilot_changes=pilot_changes,
        duplicate_conflicts=duplicate_conflicts,
        sheets_plan=sheets_plan,
        role_audits=role_audits,
        observed_at=observed_at,
    )
    weekly_brief_path = _write_weekly_preview(
        output_dir / "weekly_brief_preview.md",
        restored=restored,
        collection=collection,
        pilot_changes=pilot_changes,
        duplicate_conflicts=duplicate_conflicts,
        sheets_plan=sheets_plan,
        role_audits=role_audits,
    )
    _write_machine_summary(
        output_dir / "production_preview.json",
        restored=restored,
        collection=collection,
        pilot_changes=pilot_changes,
        duplicate_conflicts=duplicate_conflicts,
        sheets_plan=sheets_plan,
        role_audits=role_audits,
        observed_at=observed_at,
    )
    return SourceProductionPreview(
        output_dir=output_dir,
        report_path=report_path,
        weekly_brief_path=weekly_brief_path,
        restored=restored,
        collection=collection,
        analysis=analysis,
        pilot_changes=pilot_changes,
        duplicate_conflicts=duplicate_conflicts,
        sheets_plan=sheets_plan,
        role_audits=role_audits,
    )


def audit_paradromics_role(processed: ProcessedOpportunity) -> RoleFitAudit:
    """Audit research-role fit separately from employer and domain-fit scoring."""

    opportunity = processed.opportunity
    if not isinstance(opportunity, IndustryJob):
        raise TypeError("role-fit audit requires an IndustryJob")
    raw = opportunity.original_values
    title = opportunity.title.casefold()
    research_evidence = tuple(raw.get("research_responsibility_evidence") or ())
    if "field clinical" in title or title.startswith("clinical "):
        role_fit = ResearchRoleFit.CLINICAL_IMPLEMENTATION
        reason = (
            "The verified role evidence centers clinical or field implementation; the BCI "
            "employer and domain exposure do not establish a research position."
        )
    elif "embedded" in title:
        role_fit = ResearchRoleFit.TECHNICAL_PLATFORM
        reason = (
            "The role supports BCI hardware/software infrastructure, but the available evidence "
            "does not establish neural analysis or cognitive research ownership."
        )
    elif research_evidence and any(
        marker in " ".join(research_evidence).casefold()
        for marker in ("decod", "neural data", "signal processing", "model")
    ):
        role_fit = ResearchRoleFit.RESEARCH_ADJACENT_ENGINEERING
        reason = (
            "The role has explicit neural-data, decoding, modeling, or signal-processing "
            "responsibilities, while remaining an engineering rather than scientist role."
        )
    else:
        role_fit = ResearchRoleFit.INSUFFICIENT_EVIDENCE
        reason = "The official posting does not provide enough role-level research evidence."

    missing = []
    if opportunity.education_requirement.value == "UNKNOWN":
        missing.append("education requirement")
    if opportunity.original_salary_text is None:
        missing.append("salary")
    if opportunity.working_language is None:
        missing.append("working language")
    work_authorization = str(raw.get("work_authorization_detail") or "")
    if not work_authorization or work_authorization.startswith("Are you legally authorized"):
        missing.append("sponsorship/work-authorization policy")
    return RoleFitAudit(
        record_id=opportunity.opportunity_id,
        title=opportunity.title,
        official_url=opportunity.source_url,
        role_fit=role_fit,
        reason=reason,
        missing_information=tuple(missing),
    )


def find_semantic_duplicate_conflicts(previous_dir: Path, pilot_dir: Path) -> tuple[str, ...]:
    """Find same real-world identities that were assigned different stable IDs."""

    previous = _snapshot_records(previous_dir)
    pilots = _snapshot_records(pilot_dir)
    previous_keys: dict[tuple[object, ...], str] = {}
    for category, record in previous:
        previous_keys[_semantic_key(category, record)] = _record_id(record)
    conflicts = []
    for category, record in pilots:
        key = _semantic_key(category, record)
        existing = previous_keys.get(key)
        current = _record_id(record)
        if existing is not None and existing != current:
            conflicts.append(f"{category}:{current} duplicates existing {existing}")
    return tuple(sorted(conflicts))


def _snapshot_records(path: Path) -> list[tuple[str, dict[str, object]]]:
    result = []
    for category in ("jobs", "phd", "events"):
        payload = json.loads((path / f"{category}.json").read_text(encoding="utf-8"))
        result.extend((category, record) for record in payload.get("records", []))
    return result


def _record_id(record: dict[str, object]) -> str:
    opportunity = record.get("opportunity")
    if not isinstance(opportunity, dict):
        return ""
    return str(opportunity.get("opportunity_id") or "")


def _semantic_key(category: str, record: dict[str, object]) -> tuple[object, ...]:
    opportunity = record.get("opportunity")
    if not isinstance(opportunity, dict):
        return (category, "malformed")
    if category == "jobs" and opportunity.get("official_job_id"):
        return (category, opportunity.get("organization"), opportunity.get("official_job_id"))
    if category == "events":
        return (
            category,
            opportunity.get("series_name") or opportunity.get("title"),
            opportunity.get("edition_year"),
        )
    return (category, opportunity.get("identity_key") or _record_id(record))


def _write_preview_report(
    path: Path,
    *,
    restored: StateRestoreResult,
    collection: LiveCollectionReport,
    analysis: FreshObservationAnalysis,
    pilot_changes: tuple[OpportunityObservationChange, ...],
    duplicate_conflicts: tuple[str, ...],
    sheets_plan: IncrementalLiveSyncPlan,
    role_audits: tuple[RoleFitAudit, ...],
    observed_at: datetime,
) -> Path:
    counts = _change_counts(pilot_changes)
    lines = [
        "# Milestone 6.1B Production Preview",
        "",
        f"Generated: `{observed_at.isoformat()}`",
        "",
        "> Read-only preview: GCS restore and Google Sheets reads only; no commit or apply path.",
        "",
        "## Restored baseline",
        "",
        f"- Snapshot: `{restored.snapshot_id}`",
        f"- Pointer generation: `{restored.current_generation}`",
        f"- Record counts: `{dict(restored.record_counts or {})}`",
        "",
        "## Source health",
        "",
    ]
    for source_id, result in sorted(collection.sources.items()):
        lines.append(
            f"- `{source_id}`: {result.health.value}; fetched={result.records_fetched}; "
            f"extracted={len(result.records)}; profiles={len(result.informational_profiles)}; "
            f"errors={len(result.errors)}"
        )
    lines.extend(["", "## Pilot comparison", ""])
    for status, count in sorted(counts.items()):
        lines.append(f"- {status}: {count}")
    lines.append(f"- Semantic duplicate conflicts: {len(duplicate_conflicts)}")
    for conflict in duplicate_conflicts:
        lines.append(f"  - {conflict}")

    lines.extend(["", "## Paradromics role-fit audit", ""])
    decisions = sheets_plan.preview.recommendations.by_record_id
    processed = {
        item.opportunity.opportunity_id: item
        for item in collection.execution.pipelines["jobs"].records
    }
    for audit in role_audits:
        item = processed[audit.record_id]
        opportunity = item.opportunity
        decision = decisions[audit.record_id]
        lines.extend(
            [
                f"### [{audit.title}]({audit.official_url})",
                "",
                f"- Record_ID: `{audit.record_id}`",
                f"- Score/domain: `{item.score.final_score:.2f}` / `{item.score.domain_fit.value}`",
                f"- Recommendation: `{decision.classification.value}`",
                f"- Research-role audit: `{audit.role_fit.value}`",
                f"- Career stage: `{opportunity.classification.value}`",
                f"- Location: {opportunity.location or 'UNKNOWN'}",
                f"- Education: {opportunity.degree_requirement or 'UNKNOWN'}",
                f"- Salary: {opportunity.original_salary_text or 'UNKNOWN'}",
                "- Work-authorization evidence: "
                + str(opportunity.original_values.get("work_authorization_detail") or "UNKNOWN"),
                f"- Audit: {audit.reason}",
                "- Missing: " + (", ".join(audit.missing_information) or "none identified"),
                "",
            ]
        )

    cmu = collection.sources.get("cmu_neural_computation_profile")
    profile = cmu.informational_profiles[0] if cmu and cmu.informational_profiles else None
    lines.extend(["## CMU Fall 2028 programme watch", ""])
    if profile:
        lines.extend(
            [
                f"- Type: `{profile['profile_type']}`",
                f"- Actionable opportunity: `{profile['actionable_opportunity']}`",
                f"- Admission cycle: `{profile['admission_cycle'] or 'UNKNOWN'}`",
                f"- Recruitment: `{profile['confirmed_recruitment_status']}`",
                f"- Cycle-specific deadline: `{profile['official_deadline'] or 'UNKNOWN'}`",
                f"- General deadline text: {profile['general_deadline_information'] or 'UNKNOWN'}",
                "- Sheets action: none; do not insert into PhD_Opportunities.",
            ]
        )
    else:
        lines.append("No verified profile was extracted.")

    event_records = collection.execution.pipelines["events"].records
    lines.extend(["", "## RLDM 2027", ""])
    for item in event_records:
        event = item.opportunity
        lines.extend(
            [
                f"- Record_ID: `{event.opportunity_id}`",
                f"- Dates: `{event.starts_on}` to `{event.ends_on}`",
                f"- Location: {event.location}, {event.country}",
                f"- Abstract deadline: `{event.submission_deadline}` "
                f"({event.original_values.get('submission_deadline_timezone') or 'UNKNOWN'})",
                f"- Registration deadline: `{event.registration_deadline or 'UNKNOWN'}`",
            ]
        )

    lines.extend(["", "## Hypothetical Sheets plan", ""])
    for category, plan in sheets_plan.preview.workbook.plans.items():
        lines.append(
            f"- {category}: insert={plan.insert_count}; update={plan.update_count}; "
            f"unchanged={plan.unchanged_count}; invalid={plan.invalid_count}; "
            f"conflicts={plan.conflict_count}"
        )
    lines.extend(
        [
            f"- Plan fingerprint: `{sheets_plan.plan_fingerprint}`",
            "- Google Sheets writes: 0",
            "- GCS writes: 0",
            "",
            "## Safety notes",
            "",
            f"- Full reconciliation contained {len(analysis.changes)} historical statuses; only "
            "pilot-observed IDs are counted above.",
            "- Missing records were not closed and the reconciled output is local preview data.",
            "- Personal feedback notes are not included.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_weekly_preview(
    path: Path,
    *,
    restored: StateRestoreResult,
    collection: LiveCollectionReport,
    pilot_changes: tuple[OpportunityObservationChange, ...],
    duplicate_conflicts: tuple[str, ...],
    sheets_plan: IncrementalLiveSyncPlan,
    role_audits: tuple[RoleFitAudit, ...],
) -> Path:
    lines = [
        "# TOP RESEARCH MATCHES — PREVIEW",
        "",
        "> Informational profiles and open opportunities are intentionally separated.",
        "",
        "## A. Fall 2028 PhD Watch",
        "",
        "- CMU Neural Computation — `INFORMATIONAL_PROFILE`; Fall 2028 opening `UNKNOWN`.",
        "",
        "## B. Potential Supervisors & Labs",
        "",
        "- No faculty recruitment statement was verified in this pilot.",
        "",
        "## C. NeuroAI / BCI Industry Research",
        "",
    ]
    for audit in role_audits:
        lines.append(
            f"- [{audit.title}]({audit.official_url}) — `{audit.role_fit.value}`; {audit.reason}"
        )
    lines.extend(
        [
            "",
            "## D. Conferences & Deadlines",
            "",
            "- [RLDM 2027](https://rldm.org/) — July 6–9, 2027, Paris; "
            "abstract deadline January 20, 2027 AoE; registration deadline unknown.",
            "",
            "## E. Transferable General AI Roles",
            "",
            "- No additional general-AI source was collected in this pilot.",
            "",
            "## F. Source Health",
            "",
        ]
    )
    for source_id, result in sorted(collection.sources.items()):
        lines.append(f"- `{source_id}`: `{result.health.value}`")
    counts = _change_counts(pilot_changes)
    lines.extend(
        [
            "",
            "## G. Historical Change Summary",
            "",
            f"- Restored snapshot: `{restored.snapshot_id}`",
            f"- Restored counts: `{dict(restored.record_counts or {})}`",
            f"- NEW_TO_RADAR: {counts.get(FreshObservationStatus.NEW.value, 0)}",
            f"- CONTENT_CHANGED: {counts.get(FreshObservationStatus.CONTENT_CHANGED.value, 0)}",
            "- Officially newly posted: UNKNOWN unless the source explicitly supplies a "
            "posting date.",
            f"- Duplicate conflicts: {len(duplicate_conflicts)}",
            f"- Sheets plan fingerprint: `{sheets_plan.plan_fingerprint}`",
            "- Google Sheets writes: 0; GCS writes: 0.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _change_counts(changes: tuple[OpportunityObservationChange, ...]) -> dict[str, int]:
    counts = {status.value: 0 for status in FreshObservationStatus}
    for change in changes:
        status = change.status
        counts[status.value] += 1
    return counts


def _write_machine_summary(
    path: Path,
    *,
    restored: StateRestoreResult,
    collection: LiveCollectionReport,
    pilot_changes: tuple[OpportunityObservationChange, ...],
    duplicate_conflicts: tuple[str, ...],
    sheets_plan: IncrementalLiveSyncPlan,
    role_audits: tuple[RoleFitAudit, ...],
    observed_at: datetime,
) -> None:
    payload = {
        "generated_at": observed_at.isoformat(),
        "read_only": True,
        "gcs_writes": 0,
        "sheets_writes": 0,
        "restored": {
            "snapshot_id": restored.snapshot_id,
            "current_generation": restored.current_generation,
            "record_counts": dict(restored.record_counts or {}),
        },
        "sources": {
            source_id: {
                "health": result.health.value,
                "fetched": result.records_fetched,
                "extracted": len(result.records),
                "profiles": len(result.informational_profiles),
                "errors": list(result.errors),
            }
            for source_id, result in sorted(collection.sources.items())
        },
        "change_counts": _change_counts(pilot_changes),
        "duplicate_conflicts": list(duplicate_conflicts),
        "sheets_plan_fingerprint": sheets_plan.plan_fingerprint,
        "role_audits": [asdict(audit) for audit in role_audits],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
