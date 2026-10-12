"""Read-only weekly monitoring orchestration and report generation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from research_radar.collectors.base import OfficialSourceAdapter, SourceCollectionResult
from research_radar.collectors.service import collect_live
from research_radar.fresh_observation import (
    FreshObservationAnalysis,
    FreshObservationStatus,
    collect_fresh_observation,
)
from research_radar.live_integration import (
    IncrementalLiveSyncPlan,
    RecommendationClassification,
    prepare_incremental_live_sync,
)
from research_radar.models import AcademicEvent, IndustryJob, PhDOpportunity, SourceHealth

if TYPE_CHECKING:
    from research_radar.storage.sheets import SheetsAdapter


_SNAPSHOT_FILES = ("jobs.json", "phd.json", "events.json", "source_metadata.json")
_SUCCESS_HEALTH = {SourceHealth.SUCCESS, SourceHealth.SUCCESS_NO_MATCHES}


@dataclass(frozen=True)
class WeeklyRunResult:
    report_path: Path
    snapshot_dir: Path
    plan: IncrementalLiveSyncPlan
    durable_baseline_available: bool
    source_successes: int
    source_issues: int
    exit_code: int


def run_weekly_monitor(
    *,
    project_root: Path,
    output_dir: Path,
    state_dir: Path,
    observed_at: datetime,
    reference_date: date,
    adapter: SheetsAdapter,
    adapters: dict[str, OfficialSourceAdapter] | None = None,
) -> WeeklyRunResult:
    """Collect approved sources and build a read-only Sheets plan and weekly brief."""

    if observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    output_dir.mkdir(parents=True, exist_ok=True)
    durable_baseline = _has_complete_snapshot(state_dir)
    analysis: FreshObservationAnalysis | None = None
    if durable_baseline:
        fresh = collect_fresh_observation(
            project_root=project_root,
            live_dir=state_dir,
            history_root=output_dir / "history",
            observations_root=output_dir / "observations",
            observed_at=observed_at,
            reference_date=reference_date,
            adapters=adapters,
        )
        collection = fresh.collection
        analysis = fresh.analysis
        snapshot_dir = state_dir
    else:
        snapshot_dir = output_dir / "current"
        collection = collect_live(
            ("jobs", "phd", "events"),
            project_root=project_root,
            output_dir=snapshot_dir,
            observed_at=observed_at,
            reference_date=reference_date,
            adapters=adapters,
        )

    plan = prepare_incremental_live_sync(
        project_root=project_root,
        live_data_dir=snapshot_dir,
        review_dir=output_dir / "sheets-review",
        generated_at=observed_at,
        reference_date=reference_date,
        adapter=adapter,
    )
    report_path = output_dir / "researchradar_weekly_brief.md"
    _write_weekly_report(
        report_path,
        plan=plan,
        sources=collection.sources,
        analysis=analysis,
        observed_at=observed_at,
        reference_date=reference_date,
        durable_baseline=durable_baseline,
    )
    successes = sum(result.health in _SUCCESS_HEALTH for result in collection.sources.values())
    issues = len(collection.sources) - successes
    plans = (*plan.preview.workbook.plans.values(), plan.preview.watchlist_plan)
    unsafe_plan = bool(
        plan.preview.workbook.failures
        or any(item.invalid_records or item.conflicts for item in plans)
    )
    return WeeklyRunResult(
        report_path=report_path,
        snapshot_dir=snapshot_dir,
        plan=plan,
        durable_baseline_available=durable_baseline,
        source_successes=successes,
        source_issues=issues,
        exit_code=int(successes == 0 or unsafe_plan),
    )


def _has_complete_snapshot(path: Path) -> bool:
    return all((path / name).is_file() for name in _SNAPSHOT_FILES)


def _write_weekly_report(
    path: Path,
    *,
    plan: IncrementalLiveSyncPlan,
    sources: dict[str, SourceCollectionResult],
    analysis: FreshObservationAnalysis | None,
    observed_at: datetime,
    reference_date: date,
    durable_baseline: bool,
) -> None:
    preview = plan.preview
    successful = [item for item in sources.values() if item.health in _SUCCESS_HEALTH]
    unhealthy = [item for item in sources.values() if item.health not in _SUCCESS_HEALTH]
    if analysis is None:
        change_summary = "Unavailable: no durable previous snapshot was supplied."
        new_count = meaningful_count = 0
    else:
        new_count = analysis.counts[FreshObservationStatus.NEW]
        meaningful_count = analysis.counts[FreshObservationStatus.CONTENT_CHANGED]
        change_summary = f"NEW={new_count}; CONTENT_CHANGED={meaningful_count}"

    lines = [
        "# RESEARCHRADAR WEEKLY BRIEF",
        "",
        f"Generated: `{observed_at.isoformat()}`",
        "",
        "> Read-only run: no Google Sheets writes were permitted or performed.",
        "",
        "## A. Executive Summary",
        "",
        f"- Sources checked: {len(sources)}",
        f"- Successful or no-match sources: {len(successful)}",
        f"- Failed, blocked, partial, or unsupported sources: {len(unhealthy)}",
        f"- New opportunities: {new_count if analysis else 'unknown without durable state'}",
        "- Meaningful changes: "
        f"{meaningful_count if analysis else 'unknown without durable state'}",
        f"- Cross-run change detection: {change_summary}",
        f"- Durable baseline available: {'yes' if durable_baseline else 'no'}",
        "",
    ]
    deadlines = _approaching_deadlines(plan, reference_date)
    lines.append(f"- Deadlines approaching within 60 days: {len(deadlines)}")
    for title, deadline, url in deadlines:
        lines.append(f"  - [{title}]({url}) — `{deadline.isoformat()}`")

    _append_category(lines, "B. Industry Jobs", plan, "jobs")
    _append_category(lines, "C. PhD Opportunities", plan, "phd")
    _append_category(lines, "D. Events", plan, "events")
    _append_career_intelligence(lines, plan)

    lines.extend(["## F. Needs Review", ""])
    needs_review = [
        decision
        for decision in preview.recommendations.decisions
        if decision.classification is RecommendationClassification.NEEDS_REVIEW
    ]
    if not needs_review and not unhealthy:
        lines.append("None.")
    for decision in needs_review:
        processed = _processed_by_id(plan).get(decision.record_id)
        if processed is not None:
            opportunity = processed.opportunity
            lines.append(
                f"- `{decision.record_id}` [{opportunity.title}]({_official_url(opportunity)}): "
                f"{decision.explanation}"
            )
    for result in unhealthy:
        error = "; ".join(result.errors) if result.errors else "no extracted opportunity"
        lines.append(f"- Source `{result.source.source_id}`: {result.health.value}; {error}")
    if not durable_baseline:
        lines.append(
            "- Durable state is missing. Artifact snapshots support review only and are not "
            "authoritative long-term history."
        )

    lines.extend(["", "## G. Synchronization Preview", ""])
    for category, sheet_plan in preview.workbook.plans.items():
        lines.append(
            f"- {category}: insert={sheet_plan.insert_count}; update={sheet_plan.update_count}; "
            f"unchanged={sheet_plan.unchanged_count}; invalid={sheet_plan.invalid_count}; "
            f"conflicts={sheet_plan.conflict_count}"
        )
    watchlist = preview.watchlist_plan
    lines.append(
        f"- watchlist: insert={watchlist.insert_count}; update={watchlist.update_count}; "
        f"unchanged={watchlist.unchanged_count}; invalid={watchlist.invalid_count}; "
        f"conflicts={watchlist.conflict_count}"
    )
    lines.append(f"- Proposed plan fingerprint: `{plan.plan_fingerprint}`")

    lines.extend(["", "## H. Run Health", ""])
    for source_id, result in sorted(sources.items()):
        lines.append(
            f"- `{source_id}`: {result.health.value}; "
            f"retrieved=`{result.retrieved_at.isoformat()}`; "
            f"fetched={result.records_fetched}; extracted={len(result.records)}; "
            f"errors={len(result.errors)}"
        )
    lines.extend(
        [
            f"- Collection timestamp: `{observed_at.isoformat()}`",
            f"- Feedback records loaded: {len(preview.feedback.feedback_by_id)}",
            "- Personal feedback notes are intentionally omitted from this report.",
            "- Google Sheets writes: disabled",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_category(
    lines: list[str],
    heading: str,
    plan: IncrementalLiveSyncPlan,
    category: str,
) -> None:
    lines.extend([f"## {heading}", ""])
    decisions = plan.preview.recommendations.by_record_id
    records = sorted(
        plan.preview.execution.pipelines[category].records,
        key=lambda item: item.score.final_score,
        reverse=True,
    )
    if not records:
        lines.append("No extracted opportunities.")
        lines.append("")
        return
    for processed in records:
        opportunity = processed.opportunity
        decision = decisions[opportunity.opportunity_id]
        facts = _category_facts(opportunity)
        lines.append(
            f"- `{opportunity.opportunity_id}` [{opportunity.title}]({_official_url(opportunity)}) "
            f"— {opportunity.organization}; recommendation={decision.classification.value}; "
            f"domain_fit={decision.domain_fit.value}; score={processed.score.final_score:.1f}; "
            f"{facts}"
        )
    lines.append("")


def _category_facts(opportunity: object) -> str:
    if isinstance(opportunity, IndustryJob):
        salary = opportunity.original_salary_text or "salary unknown"
        return (
            f"education={opportunity.education_requirement.value}; {salary}; "
            f"career_stage={opportunity.classification.value}"
        )
    if isinstance(opportunity, PhDOpportunity):
        return (
            f"cycle={opportunity.target_cycle or 'unknown'}; "
            f"funding={opportunity.funding_status or 'unknown'}; "
            f"deadline={opportunity.deadline.isoformat() if opportunity.deadline else 'unknown'}"
        )
    if isinstance(opportunity, AcademicEvent):
        submission_deadline = (
            opportunity.submission_deadline.isoformat()
            if opportunity.submission_deadline
            else "unknown"
        )
        return (
            f"dates={opportunity.starts_on.isoformat() if opportunity.starts_on else 'unknown'}"
            f" to {opportunity.ends_on.isoformat() if opportunity.ends_on else 'unknown'}; "
            f"submission_deadline={submission_deadline}"
        )
    return "details unknown"


def _append_career_intelligence(lines: list[str], plan: IncrementalLiveSyncPlan) -> None:
    jobs = plan.preview.execution.pipelines["jobs"].records
    skills = Counter(skill for record in jobs for skill in record.opportunity.skills)
    future_targets = sum(
        record.opportunity.classification.value == "FUTURE_CAREER_TARGET" for record in jobs
    )
    lines.extend(["## E. Career Intelligence", ""])
    lines.append(f"- PhD-level future career targets retained: {future_targets}")
    if skills:
        rendered = ", ".join(f"{skill} ({count})" for skill, count in skills.most_common(8))
        lines.append(f"- Common explicitly extracted skills: {rendered}")
    else:
        lines.append("- Common explicitly extracted skills: insufficient evidence")
    lines.append(
        "- General AI/ML roles remain technical-transferability signals and do not automatically "
        "outrank cognition- or neuroscience-centered work."
    )
    lines.append("")


def _approaching_deadlines(
    plan: IncrementalLiveSyncPlan,
    reference_date: date,
) -> list[tuple[str, date, str]]:
    limit = reference_date + timedelta(days=60)
    result: list[tuple[str, date, str]] = []
    for report in plan.preview.execution.pipelines.values():
        for processed in report.records:
            opportunity = processed.opportunity
            candidates = [opportunity.deadline]
            if isinstance(opportunity, AcademicEvent):
                candidates.extend(
                    [opportunity.submission_deadline, opportunity.registration_deadline]
                )
            for deadline in candidates:
                if deadline is not None and reference_date <= deadline <= limit:
                    result.append((opportunity.title, deadline, _official_url(opportunity)))
    return sorted(result, key=lambda item: item[1])


def _official_url(opportunity: object) -> str:
    if isinstance(opportunity, (IndustryJob, PhDOpportunity, AcademicEvent)):
        return opportunity.official_source_url or opportunity.source_url
    raise TypeError("unsupported opportunity type")


def _processed_by_id(plan: IncrementalLiveSyncPlan) -> dict[str, object]:
    return {
        processed.opportunity.opportunity_id: processed
        for report in plan.preview.execution.pipelines.values()
        for processed in report.records
    }
