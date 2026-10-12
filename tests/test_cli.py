from pathlib import Path
from types import SimpleNamespace

import pytest

from research_radar.cli import main
from research_radar.storage.google_sheets import SheetsConfigurationError
from research_radar.storage.sheets import SHEET_SCHEMAS, SheetSyncPlan

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cli_can_run_one_demo_pipeline(tmp_path: Path, capsys: object) -> None:
    exit_code = main(
        [
            "run-demo",
            "jobs",
            "--project-root",
            str(PROJECT_ROOT),
            "--output-dir",
            str(tmp_path),
            "--reference-date",
            "2026-10-12",
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "jobs.json").exists()
    assert "jobs:" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_cli_can_show_offline_sheets_dry_run(tmp_path: Path, capsys: object) -> None:
    output_dir = PROJECT_ROOT / "data" / "demo"
    mtimes_before = {path.name: path.stat().st_mtime_ns for path in output_dir.glob("*.json")}
    exit_code = main(
        [
            "sheets-plan",
            "--demo",
            "--project-root",
            str(PROJECT_ROOT),
            "--reference-date",
            "2026-10-12",
        ]
    )

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert exit_code == 0
    assert "dry-run; no worksheet writes" in output
    assert "jobs: insert=" in output
    assert "phd: insert=" in output
    assert "events: insert=" in output
    mtimes_after = {path.name: path.stat().st_mtime_ns for path in output_dir.glob("*.json")}
    assert mtimes_after == mtimes_before


def test_live_commands_require_explicit_write_mode() -> None:
    with pytest.raises(SystemExit):
        main(["sheets-init"])

    with pytest.raises(SystemExit):
        main(["sheets-sync", "--demo"])


def test_sheets_status_is_read_only_and_does_not_print_id(
    monkeypatch: pytest.MonkeyPatch, capsys: object
) -> None:
    class StubAdapter:
        settings = SimpleNamespace(environment="test")

        def get_status(self) -> object:
            return SimpleNamespace(
                worksheets={
                    name: SimpleNamespace(row_count=0, headers_valid=True) for name in SHEET_SCHEMAS
                },
                missing_sheets=(),
            )

    monkeypatch.setattr("research_radar.cli._live_adapter", lambda: StubAdapter())

    exit_code = main(["sheets-status"])

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert exit_code == 0
    assert "connected; environment=test" in output
    assert "spreadsheet-secret-id" not in output


def test_live_configuration_errors_are_human_readable(
    monkeypatch: pytest.MonkeyPatch, capsys: object
) -> None:
    def fail_adapter() -> object:
        raise SheetsConfigurationError("GOOGLE_SPREADSHEET_ID is required")

    monkeypatch.setattr("research_radar.cli._live_adapter", fail_adapter)

    assert main(["sheets-status"]) == 1
    assert "GOOGLE_SPREADSHEET_ID is required" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_cli_live_sheets_preview_is_offline_and_never_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: object
) -> None:
    review_path = tmp_path / "review.md"
    preview = SimpleNamespace(
        offline=True,
        workbook=SimpleNamespace(
            plans={"jobs": SheetSyncPlan(sheet_name="Industry_Jobs")}, failures={}
        ),
        provenance=SimpleNamespace(valid_count=27, blocked_count=0),
        coverage={},
        review_report_path=review_path,
    )
    monkeypatch.setattr("research_radar.cli.configured_live_pilot_adapter", lambda: None)
    monkeypatch.setattr("research_radar.cli.prepare_live_sheets_preview", lambda **_: preview)

    exit_code = main(
        [
            "sheets-sync",
            "--live",
            "--dry-run",
            "--project-root",
            str(PROJECT_ROOT),
            "--live-data-dir",
            str(tmp_path / "live"),
            "--review-dir",
            str(tmp_path / "review"),
        ]
    )

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert exit_code == 0
    assert "offline simulated empty workbook" in output
    assert "provenance: valid=27; blocked=0" in output
    assert "no writes performed" in output


def test_cli_refuses_live_apply_before_loading_any_adapter(capsys: object) -> None:
    exit_code = main(["sheets-sync", "--live", "--apply"])

    assert exit_code == 1
    assert "apply is disabled" in capsys.readouterr().out  # type: ignore[attr-defined]
