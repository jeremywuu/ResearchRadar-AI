"""Command-line entry points for local development."""

from __future__ import annotations

import argparse
from pathlib import Path

from research_radar.config import ConfigValidationError, load_all_configs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-radar")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-config", help="validate all YAML configuration")
    validate.add_argument("--config-dir", type=Path, default=Path("config"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
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
    return 2
