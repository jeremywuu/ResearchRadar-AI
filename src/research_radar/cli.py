"""Command-line entry points for local development."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from pathlib import Path

from research_radar.config import ConfigValidationError, load_all_configs
from research_radar.demo import process_demo, run_demo
from research_radar.sheets_demo import build_demo_sheets_adapter
from research_radar.storage.sheets import sync_execution_report


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
    return parser


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
            print(
                f"{category}: insert={plan.insert_count}; update={plan.update_count}; "
                f"unchanged={plan.unchanged_count}; invalid={plan.invalid_count}; "
                f"conflicts={plan.conflict_count}; api_operations="
                f"{plan.estimated_api_operations}"
            )
        for category, failure in result.failures.items():
            print(f"{category}: FAILED; {failure}")
        return 1 if result.failures else 0
    return 2
