"""Command-line entry points for local development."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from research_radar.config import ConfigValidationError, load_all_configs
from research_radar.demo import run_demo


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
    return 2
