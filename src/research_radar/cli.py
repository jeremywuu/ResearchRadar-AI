"""Command-line entry points for local development."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from pathlib import Path

from research_radar.collectors.service import collect_live
from research_radar.config import ConfigValidationError, load_all_configs
from research_radar.demo import process_demo, run_demo
from research_radar.live_integration import (
    DataMode,
    LiveDataError,
    TargetEnvironment,
    apply_initial_live_pilot_sync,
    configured_live_pilot_adapter,
    prepare_live_sheets_preview,
    validate_configured_data_mode,
    validate_live_pilot_identity,
    validate_live_pilot_write_environment,
)
from research_radar.sheets_demo import build_demo_sheets_adapter
from research_radar.sheets_live import run_live_demo_sync
from research_radar.storage.google_auth import SheetsAuthenticationError
from research_radar.storage.google_sheets import (
    GoogleSheetsAdapter,
    GoogleSheetsError,
    SheetsConfigurationError,
)
from research_radar.storage.sheets import (
    SheetsAdapter,
    SheetSchemaError,
    SheetSyncPlan,
    sync_execution_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-radar")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-config", help="validate all YAML configuration")
    validate.add_argument("--config-dir", type=Path, default=Path("config"))
    demo = subparsers.add_parser("run-demo", help="run fictional local processing pipelines")
    demo.add_argument(
        "category", choices=("all", "jobs", "phd", "events"), nargs="?", default="all"
    )
    demo.add_argument("--project-root", type=Path, default=Path.cwd())
    demo.add_argument("--output-dir", type=Path, default=Path("data/demo"))
    demo.add_argument("--reference-date", type=date.fromisoformat)
    sheets = subparsers.add_parser("sheets-plan", help="plan offline worksheet synchronization")
    sheets.add_argument("--demo", action="store_true", required=True)
    sheets.add_argument("--project-root", type=Path, default=Path.cwd())
    sheets.add_argument("--reference-date", type=date.fromisoformat, default=date(2026, 10, 12))

    sheets_init = subparsers.add_parser(
        "sheets-init", help="inspect or initialize the configured Google spreadsheet"
    )
    sheets_init.add_argument(
        "--live", action="store_true", help="target only the dedicated LIVE PILOT workbook"
    )
    _add_write_mode(sheets_init)

    sheets_sync = subparsers.add_parser(
        "sheets-sync", help="preview or synchronize selected data with Google Sheets"
    )
    data_mode = sheets_sync.add_mutually_exclusive_group(required=True)
    data_mode.add_argument("--demo", action="store_true", help="use fictional demo records")
    data_mode.add_argument("--live", action="store_true", help="use cached verified live records")
    _add_write_mode(sheets_sync)
    sheets_sync.add_argument("--project-root", type=Path, default=Path.cwd())
    sheets_sync.add_argument("--reference-date", type=date.fromisoformat, default=date.today())
    sheets_sync.add_argument("--live-data-dir", type=Path, default=Path("data/live"))
    sheets_sync.add_argument("--review-dir", type=Path, default=Path("data/review"))

    sheets_status = subparsers.add_parser(
        "sheets-status", help="check Google Sheets connectivity and schema without writes"
    )
    sheets_status.add_argument(
        "--live", action="store_true", help="check only the dedicated LIVE PILOT workbook"
    )
    collect = subparsers.add_parser(
        "collect", help="collect from explicitly selected verified official sources"
    )
    collect.add_argument("category", choices=("all", "jobs", "phd", "events"))
    collect.add_argument(
        "--live",
        action="store_true",
        required=True,
        help="explicitly authorize read-only network access",
    )
    collect.add_argument("--source", help="optional exact source identifier")
    collect.add_argument("--project-root", type=Path, default=Path.cwd())
    collect.add_argument("--output-dir", type=Path, default=Path("data/live"))
    collect.add_argument("--reference-date", type=date.fromisoformat, default=date.today())
    return parser


def _add_write_mode(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="inspect only; perform no writes")
    mode.add_argument("--apply", action="store_true", help="explicitly authorize writes")


def _print_sync_plan(category: str, plan: SheetSyncPlan) -> None:
    print(
        f"{category}: insert={plan.insert_count}; update={plan.update_count}; "
        f"unchanged={plan.unchanged_count}; invalid={plan.invalid_count}; "
        f"conflicts={plan.conflict_count}; api_operations={plan.estimated_api_operations}"
    )


def _live_adapter() -> GoogleSheetsAdapter:
    return GoogleSheetsAdapter.from_environment()


def _required_live_pilot_adapter(*, for_write: bool = False) -> SheetsAdapter:
    expected_id = validate_live_pilot_write_environment() if for_write else None
    if not for_write:
        validate_configured_data_mode(DataMode.LIVE)
    adapter = configured_live_pilot_adapter()
    if adapter is None:
        raise LiveDataError("GOOGLE_LIVE_PILOT_SPREADSHEET_ID is required")
    validate_live_pilot_identity(adapter, expected_spreadsheet_id=expected_id)
    return adapter


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-config":
        try:
            summary = load_all_configs(args.config_dir)
        except ConfigValidationError as exc:
            print(f"Configuration invalid: {exc}")
            return 1
        print(
            "Configuration valid: "
            f"{summary['watchlist_targets']} watchlist targets, "
            f"{summary['research_interests']} research interests, "
            f"salary weights total {summary['salary_weights_total']}%."
        )
        return 0
    if args.command == "run-demo":
        categories = ("jobs", "phd", "events") if args.category == "all" else (args.category,)
        report = run_demo(
            categories,
            project_root=args.project_root,
            output_dir=args.output_dir,
            reference_date=args.reference_date,
        )
        for name, pipeline in report.pipelines.items():
            print(
                f"{name}: {pipeline.status.value}; processed={pipeline.records_processed}; "
                f"accepted={pipeline.records_accepted}; duplicates={pipeline.duplicates_found}; "
                f"excluded={pipeline.records_excluded}; "
                f"validation_errors={len(pipeline.validation_errors)}"
            )
            if pipeline.output_path:
                print(f"  output: {pipeline.output_path}")
            if pipeline.failure:
                print(f"  failure: {pipeline.failure}")
        return 1 if report.failed_pipelines else 0
    if args.command == "sheets-plan":
        observed_at = datetime.combine(args.reference_date, datetime.min.time(), tzinfo=UTC)
        execution = process_demo(
            ("jobs", "phd", "events"),
            project_root=args.project_root,
            observed_at=observed_at,
            reference_date=args.reference_date,
        )
        adapter = build_demo_sheets_adapter(execution)
        result = sync_execution_report(
            execution,
            adapter,
            dry_run=True,
            run_id=f"demo_{args.reference_date.isoformat()}",
            timestamp=observed_at,
        )
        print("Google Sheets synchronization plan (dry-run; no worksheet writes)")
        for category, plan in result.plans.items():
            _print_sync_plan(category, plan)
        for category, failure in result.failures.items():
            print(f"{category}: FAILED; {failure}")
        return 1 if result.failures else 0
    if args.command == "collect":
        observed_at = datetime.now(UTC)
        categories = ("jobs", "phd", "events") if args.category == "all" else (args.category,)
        try:
            result = collect_live(
                categories,
                project_root=args.project_root,
                output_dir=args.output_dir,
                observed_at=observed_at,
                reference_date=args.reference_date,
                source_id=args.source,
            )
        except ValueError as exc:
            print(f"Collection failed: {exc}")
            return 1
        print("Official-source collection (read-only network; local JSON only)")
        for source in result.sources.values():
            print(
                f"{source.source.source_id}: {source.health.value}; "
                f"fetched={source.records_fetched}; extracted={len(source.records)}; "
                f"extraction_errors={len(source.errors)}"
            )
            for error in source.errors:
                print(f"  error: {error}")
        for category, report in result.execution.pipelines.items():
            print(
                f"{category}: {report.status.value}; fetched={report.records_fetched or 0}; "
                f"extracted={report.records_processed}; accepted={report.records_accepted}; "
                f"rejected={len(report.validation_errors)}; excluded={report.records_excluded}"
            )
            if report.output_path:
                print(f"  output: {report.output_path}")
        print(f"source metadata: {result.metadata_path}")
        failed_health = {"FAILED", "BLOCKED", "UNSUPPORTED"}
        return int(
            bool(result.execution.failed_pipelines)
            or any(source.health.value in failed_health for source in result.sources.values())
        )
    try:
        if args.command == "sheets-init":
            adapter = (
                _required_live_pilot_adapter(for_write=args.apply) if args.live else _live_adapter()
            )
            plan = adapter.initialize_workbook(apply=args.apply)
            target = "LIVE PILOT" if args.live else "configured workbook"
            print(f"Google Sheets {target} initialization ({'apply' if args.apply else 'dry-run'})")
            print(f"existing: {', '.join(plan.existing_sheets) or 'none'}")
            print(f"missing: {', '.join(plan.missing_sheets) or 'none'}")
            if plan.incompatible_headers:
                print("incompatible headers: " + ", ".join(plan.incompatible_headers))
                return 1
            if args.apply:
                print(f"created: {len(plan.missing_sheets)} worksheet(s)")
            else:
                print("no writes performed")
            return 0
        if args.command == "sheets-sync":
            observed_at = datetime.now(UTC)
            if args.live:
                if args.apply:
                    pilot_adapter = _required_live_pilot_adapter(for_write=True)
                    result = apply_initial_live_pilot_sync(
                        project_root=args.project_root,
                        live_data_dir=args.live_data_dir,
                        review_dir=args.review_dir,
                        generated_at=observed_at,
                        reference_date=args.reference_date,
                        adapter=pilot_adapter,
                    )
                    print("Google Sheets initial LIVE PILOT synchronization (apply)")
                    for category, plan in result.preview.workbook.plans.items():
                        _print_sync_plan(category, plan)
                    _print_sync_plan("watchlist", result.preview.watchlist_plan)
                    print("applied sheets: " + ", ".join(result.applied_sheets))
                    print("approved initial synchronization applied once")
                    return 0
                validate_configured_data_mode(DataMode.LIVE)
                pilot_adapter = configured_live_pilot_adapter()
                preview = prepare_live_sheets_preview(
                    project_root=args.project_root,
                    live_data_dir=args.live_data_dir,
                    review_dir=args.review_dir,
                    generated_at=observed_at,
                    reference_date=args.reference_date,
                    adapter=pilot_adapter,
                    target_environment=TargetEnvironment.LIVE_PILOT,
                )
                target = (
                    "offline simulated empty workbook"
                    if preview.offline
                    else "configured LIVE PILOT workbook"
                )
                print(f"Google Sheets live-data preview (dry-run; target={target})")
                for category, plan in preview.workbook.plans.items():
                    _print_sync_plan(category, plan)
                _print_sync_plan("watchlist", preview.watchlist_plan)
                print(
                    f"provenance: valid={preview.provenance.valid_count}; "
                    f"blocked={preview.provenance.blocked_count}"
                )
                for classification, count in preview.recommendations.counts.items():
                    print(f"recommendation {classification.value}: {count}")
                for source in preview.coverage.values():
                    print(
                        f"coverage {source.source_id}: returned={source.records_returned}; "
                        f"considered={source.records_considered}; "
                        f"extracted={source.records_extracted}; "
                        f"accepted={source.records_accepted}"
                    )
                print(f"review report: {preview.review_report_path}")
                print("no writes performed")
                return (
                    1
                    if preview.workbook.failures
                    or preview.provenance.blocked_count
                    or preview.watchlist_plan.invalid_records
                    or preview.watchlist_plan.conflicts
                    else 0
                )
            result = run_live_demo_sync(
                _live_adapter(),
                project_root=args.project_root,
                apply=args.apply,
                run_id=f"demo_{observed_at.strftime('%Y%m%dT%H%M%SZ')}",
                timestamp=observed_at,
                reference_date=args.reference_date,
            )
            print(f"Google Sheets demo synchronization ({'apply' if args.apply else 'dry-run'})")
            for category, plan in result.workbook.plans.items():
                _print_sync_plan(category, plan)
            _print_sync_plan("watchlist", result.watchlist_plan)
            print(
                "feedback: "
                f"loaded={len(result.feedback.feedback_by_id)}; "
                f"invalid={len(result.feedback.invalid_records)}; "
                f"conflicts={len(result.feedback.conflicts)}"
            )
            for category, failure in result.workbook.failures.items():
                print(f"{category}: FAILED; {failure}")
            if not args.apply:
                print("no writes performed")
            return 1 if result.workbook.failures else 0
        if args.command == "sheets-status":
            adapter = _required_live_pilot_adapter() if args.live else _live_adapter()
            status = adapter.get_status()
            print(f"Google Sheets status: connected; environment={adapter.settings.environment}")
            for name, worksheet in status.worksheets.items():
                template_rows = getattr(worksheet, "template_row_count", 0)
                template_suffix = f"; template_rows={template_rows}" if template_rows else ""
                print(
                    f"{name}: rows={worksheet.row_count}; "
                    f"headers={'valid' if worksheet.headers_valid else 'INVALID'}"
                    f"{template_suffix}"
                )
            for name in status.missing_sheets:
                print(f"{name}: MISSING")
            return (
                1
                if status.missing_sheets
                or any(not sheet.headers_valid for sheet in status.worksheets.values())
                else 0
            )
    except (
        GoogleSheetsError,
        SheetSchemaError,
        SheetsAuthenticationError,
        SheetsConfigurationError,
        LiveDataError,
    ) as exc:
        print(f"Google Sheets operation failed: {exc}")
        return 1
    return 2
