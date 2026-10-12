"""Orchestration for bounded live official-source collection."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from research_radar.collectors.base import OfficialSourceAdapter, SourceCollectionResult
from research_radar.collectors.official import (
    AnthropicGreenhouseAdapter,
    Ccn2027EventAdapter,
    CmuCognitiveNeuroscienceProgramAdapter,
    CosyneEventAdapter,
    NeuroelectricsCareersAdapter,
    UclGatsbyPhdAdapter,
)
from research_radar.models import (
    ExecutionReport,
    ExtractionStatus,
    PipelineReport,
    PipelineStatus,
    SourceHealth,
)
from research_radar.pipelines import run_events_pipeline, run_jobs_pipeline, run_phd_pipeline
from research_radar.storage.json_store import JsonOutputStore


@dataclass(kw_only=True)
class LiveCollectionReport:
    execution: ExecutionReport
    sources: dict[str, SourceCollectionResult]
    metadata_path: Path


def default_adapters() -> dict[str, OfficialSourceAdapter]:
    adapters: list[OfficialSourceAdapter] = [
        AnthropicGreenhouseAdapter(),
        UclGatsbyPhdAdapter(),
        CosyneEventAdapter(),
        Ccn2027EventAdapter(),
        CmuCognitiveNeuroscienceProgramAdapter(),
        NeuroelectricsCareersAdapter(),
    ]
    return {adapter.source.source_id: adapter for adapter in adapters}


def collect_live(
    categories: tuple[str, ...],
    *,
    project_root: Path,
    output_dir: Path,
    observed_at: datetime,
    reference_date: date,
    source_id: str | None = None,
    adapters: dict[str, OfficialSourceAdapter] | None = None,
) -> LiveCollectionReport:
    available = adapters or default_adapters()
    selected = [
        adapter
        for key, adapter in available.items()
        if adapter.source.category in categories and (source_id is None or key == source_id)
    ]
    if source_id and not selected:
        raise ValueError(f"unknown or category-incompatible source: {source_id}")

    source_results: dict[str, SourceCollectionResult] = {}
    reports: dict[str, PipelineReport] = {}
    store = JsonOutputStore(output_dir)
    for category in categories:
        category_adapters = [item for item in selected if item.source.category == category]
        raw_records: list[dict[str, Any]] = []
        source_errors: list[str] = []
        fetched = 0
        for adapter in category_adapters:
            try:
                result = adapter.collect(observed_at=observed_at)
            except Exception as exc:  # noqa: BLE001 - source isolation boundary
                result = SourceCollectionResult(
                    source=adapter.source,
                    health=SourceHealth.FAILED,
                    extraction_status=ExtractionStatus.FAILED,
                    retrieved_at=observed_at,
                    errors=[f"{type(exc).__name__}: {exc}"],
                )
            source_results[result.source.source_id] = result
            raw_records.extend(result.records)
            fetched += result.records_fetched
            source_errors.extend(f"{result.source.source_id}: {error}" for error in result.errors)
        try:
            report = _run_pipeline(
                category,
                raw_records,
                config_dir=project_root / "config",
                observed_at=observed_at,
                reference_date=reference_date,
            )
            report.records_fetched = fetched
            report.source_extraction_errors = tuple(source_errors)
            if source_errors and report.status is PipelineStatus.SUCCESS:
                report.status = PipelineStatus.PARTIAL
            store.write(report)
        except Exception as exc:  # noqa: BLE001 - category failure isolation boundary
            report = PipelineReport(
                category=category,
                status=PipelineStatus.FAILED,
                records_processed=len(raw_records),
                records_accepted=0,
                duplicates_found=0,
                records_excluded=0,
                validation_errors=(),
                records=(),
                failure=f"{type(exc).__name__}: {exc}",
                records_fetched=fetched,
                source_extraction_errors=tuple(source_errors),
                pipeline_processing_errors=(f"{type(exc).__name__}: {exc}",),
            )
        reports[category] = report
    metadata_path = _write_source_metadata(output_dir, source_results, reports)
    return LiveCollectionReport(
        execution=ExecutionReport(pipelines=reports),
        sources=source_results,
        metadata_path=metadata_path,
    )


def _run_pipeline(
    category: str,
    raw_records: list[dict[str, Any]],
    *,
    config_dir: Path,
    observed_at: datetime,
    reference_date: date,
) -> PipelineReport:
    if category == "jobs":
        return run_jobs_pipeline(raw_records, config_dir=config_dir, observed_at=observed_at)
    if category == "phd":
        return run_phd_pipeline(raw_records, config_dir=config_dir, observed_at=observed_at)
    if category == "events":
        return run_events_pipeline(
            raw_records,
            config_dir=config_dir,
            observed_at=observed_at,
            reference_date=reference_date,
        )
    raise ValueError(f"unsupported collection category: {category}")


def _write_source_metadata(
    output_dir: Path,
    sources: dict[str, SourceCollectionResult],
    reports: dict[str, PipelineReport],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "source_metadata.json"
    payload = {
        "sources": {key: _json_value(asdict(value)) for key, value in sources.items()},
        "pipelines": {
            key: {
                "status": value.status.value,
                "records_fetched": value.records_fetched,
                "records_extracted": value.records_processed,
                "records_accepted": value.records_accepted,
                "records_rejected": len(value.validation_errors),
                "records_excluded": value.records_excluded,
                "source_extraction_errors": list(value.source_extraction_errors),
                "pipeline_processing_errors": list(value.pipeline_processing_errors),
                "output_path": str(value.output_path) if value.output_path else None,
            }
            for key, value in reports.items()
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
