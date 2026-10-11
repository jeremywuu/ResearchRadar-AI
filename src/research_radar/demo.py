"""Orchestration for the local fictional-data demonstration."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from research_radar.collectors import load_fixture_records
from research_radar.models import ExecutionReport
from research_radar.pipelines import (
    run_events_pipeline,
    run_independent_pipelines,
    run_jobs_pipeline,
    run_phd_pipeline,
)
from research_radar.storage import JsonOutputStore


def run_demo(
    categories: tuple[str, ...],
    *,
    project_root: Path,
    output_dir: Path,
    observed_at: datetime | None = None,
    reference_date: date | None = None,
) -> ExecutionReport:
    execution = process_demo(
        categories,
        project_root=project_root,
        observed_at=observed_at,
        reference_date=reference_date,
    )
    store = JsonOutputStore(output_dir)
    for report in execution.pipelines.values():
        if report.failure is None:
            store.write(report)
    return execution


def process_demo(
    categories: tuple[str, ...],
    *,
    project_root: Path,
    observed_at: datetime | None = None,
    reference_date: date | None = None,
) -> ExecutionReport:
    """Process fictional fixtures without writing local or external storage."""

    observed_at = observed_at or datetime.now(UTC)
    reference_date = reference_date or observed_at.date()
    config_dir = project_root / "config"
    fixture_dir = project_root / "fixtures" / "demo"
    tasks = {
        "jobs": lambda: run_jobs_pipeline(
            load_fixture_records(fixture_dir / "jobs.json"),
            config_dir=config_dir,
            observed_at=observed_at,
        ),
        "phd": lambda: run_phd_pipeline(
            load_fixture_records(fixture_dir / "phd.json"),
            config_dir=config_dir,
            observed_at=observed_at,
        ),
        "events": lambda: run_events_pipeline(
            load_fixture_records(fixture_dir / "events.json"),
            config_dir=config_dir,
            observed_at=observed_at,
            reference_date=reference_date,
        ),
    }
    return run_independent_pipelines({name: tasks[name] for name in categories})
