"""Public interfaces for local opportunity processing pipelines."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from research_radar.config import (
    load_career_preferences,
    load_research_interests,
    load_salary_rules,
)
from research_radar.deduplication import deduplicate
from research_radar.models import (
    EnglishCompatibility,
    ExecutionReport,
    PipelineReport,
    PipelineStatus,
    ProcessedOpportunity,
    UserFeedback,
)
from research_radar.normalization import RecordValidationError, normalize_job
from research_radar.personalization import apply_feedback, assign_ranks
from research_radar.scoring import score_event, score_job, score_phd


def _finalize_report(
    *,
    category: str,
    raw_count: int,
    normalized: list[Any],
    errors: list[str],
    score_record: Any,
    feedback_by_id: dict[str, UserFeedback] | None,
) -> PipelineReport:
    unique, duplicates = deduplicate(normalized)
    feedback_by_id = feedback_by_id or {}
    processed = []
    for opportunity in unique:
        record = ProcessedOpportunity(opportunity=opportunity, score=score_record(opportunity))
        processed.append(apply_feedback(record, feedback_by_id.get(opportunity.opportunity_id)))
    assign_ranks(processed)
    return PipelineReport(
        category=category,
        status=PipelineStatus.PARTIAL if errors else PipelineStatus.SUCCESS,
        records_processed=raw_count,
        records_accepted=len(processed),
        duplicates_found=duplicates,
        records_excluded=0,
        validation_errors=tuple(errors),
        records=tuple(processed),
    )


def run_jobs_pipeline(
    raw_records: list[dict[str, Any]],
    *,
    config_dir: Path,
    observed_at: datetime,
    feedback_by_id: dict[str, UserFeedback] | None = None,
) -> PipelineReport:
    interests = load_research_interests(config_dir / "research_interests.yaml")
    preferences = load_career_preferences(config_dir / "career_preferences.yaml")
    salary_rules = load_salary_rules(config_dir / "salary_rules.yaml")
    normalized = []
    errors = []
    for index, raw in enumerate(raw_records):
        try:
            normalized.append(normalize_job(raw, observed_at=observed_at))
        except (RecordValidationError, TypeError, ValueError) as exc:
            errors.append(f"record[{index}]: {exc}")
    unique, duplicates = deduplicate(normalized)
    feedback_by_id = feedback_by_id or {}
    processed: list[ProcessedOpportunity] = []
    for job in unique:
        excluded = job.english_compatibility is EnglishCompatibility.EXPLICITLY_NON_ENGLISH_REQUIRED
        record = ProcessedOpportunity(
            opportunity=job,
            score=score_job(
                job,
                interests=interests,
                preferences=preferences,
                salary_rules=salary_rules,
            ),
            excluded=excluded,
            exclusion_reason="EXPLICITLY_NON_ENGLISH_REQUIRED" if excluded else None,
            processing_status="EXCLUDED" if excluded else "ACCEPTED",
        )
        processed.append(apply_feedback(record, feedback_by_id.get(job.opportunity_id)))
    assign_ranks(processed)
    excluded_count = sum(record.excluded for record in processed)
    return PipelineReport(
        category="jobs",
        status=PipelineStatus.PARTIAL if errors else PipelineStatus.SUCCESS,
        records_processed=len(raw_records),
        records_accepted=len(processed) - excluded_count,
        duplicates_found=duplicates,
        records_excluded=excluded_count,
        validation_errors=tuple(errors),
        records=tuple(processed),
    )


def run_phd_pipeline(
    raw_records: list[dict[str, Any]],
    *,
    config_dir: Path,
    observed_at: datetime,
    feedback_by_id: dict[str, UserFeedback] | None = None,
) -> PipelineReport:
    from research_radar.normalization import normalize_phd

    interests = load_research_interests(config_dir / "research_interests.yaml")
    preferences = load_career_preferences(config_dir / "career_preferences.yaml")
    normalized = []
    errors = []
    for index, raw in enumerate(raw_records):
        try:
            normalized.append(normalize_phd(raw, observed_at=observed_at))
        except (RecordValidationError, TypeError, ValueError) as exc:
            errors.append(f"record[{index}]: {exc}")
    return _finalize_report(
        category="phd",
        raw_count=len(raw_records),
        normalized=normalized,
        errors=errors,
        score_record=lambda opportunity: score_phd(
            opportunity, interests=interests, preferences=preferences
        ),
        feedback_by_id=feedback_by_id,
    )


def run_events_pipeline(
    raw_records: list[dict[str, Any]],
    *,
    config_dir: Path,
    observed_at: datetime,
    reference_date: date,
    feedback_by_id: dict[str, UserFeedback] | None = None,
) -> PipelineReport:
    from research_radar.normalization import normalize_event

    interests = load_research_interests(config_dir / "research_interests.yaml")
    normalized = []
    errors = []
    for index, raw in enumerate(raw_records):
        try:
            normalized.append(normalize_event(raw, observed_at=observed_at))
        except (RecordValidationError, TypeError, ValueError) as exc:
            errors.append(f"record[{index}]: {exc}")
    return _finalize_report(
        category="events",
        raw_count=len(raw_records),
        normalized=normalized,
        errors=errors,
        score_record=lambda event: score_event(
            event, interests=interests, reference_date=reference_date
        ),
        feedback_by_id=feedback_by_id,
    )


def run_independent_pipelines(
    pipeline_tasks: Mapping[str, Callable[[], PipelineReport]],
) -> ExecutionReport:
    """Run every requested category and isolate failures to the failing category."""

    reports: dict[str, PipelineReport] = {}
    for category, task in pipeline_tasks.items():
        try:
            reports[category] = task()
        except Exception as exc:  # noqa: BLE001 - failure isolation is the boundary contract
            reports[category] = PipelineReport(
                category=category,
                status=PipelineStatus.FAILED,
                records_processed=0,
                records_accepted=0,
                duplicates_found=0,
                records_excluded=0,
                validation_errors=(),
                records=(),
                failure=f"{type(exc).__name__}: {exc}",
            )
    return ExecutionReport(pipelines=reports)
