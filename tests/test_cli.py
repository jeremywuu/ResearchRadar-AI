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
        watchlist_plan=SheetSyncPlan(sheet_name="Watchlist"),
        provenance=SimpleNamespace(valid_count=27, blocked_count=0),
        recommendations=SimpleNamespace(counts={}),
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
    assert "watchlist: insert=0" in output
    assert "no writes performed" in output


def test_cli_incremental_live_apply_remains_disabled_before_adapter_access(
    monkeypatch: pytest.MonkeyPatch, capsys: object
) -> None:
    monkeypatch.setattr(
        "research_radar.cli._required_live_pilot_adapter",
        lambda **_: pytest.fail("adapter must not load for a disabled apply"),
    )

    exit_code = main(
        [
            "sheets-sync",
            "--live",
            "--incremental",
            "--apply",
            "--reference-date",
            "2026-10-12",
        ]
    )

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert exit_code == 1
    assert "incremental live apply is disabled" in output


def test_cli_incremental_live_dry_run_reports_feedback_and_fingerprint(
    monkeypatch: pytest.MonkeyPatch, capsys: object, tmp_path: Path
) -> None:
    adapter = object()
    review_path = tmp_path / "review.md"
    preview = SimpleNamespace(
        offline=False,
        workbook=SimpleNamespace(
            plans={
                "jobs": SheetSyncPlan(sheet_name="Industry_Jobs", unchanged_record_ids=["job_1"])
            },
            failures={},
        ),
        watchlist_plan=SheetSyncPlan(sheet_name="Watchlist", unchanged_record_ids=["watch_1"]),
        provenance=SimpleNamespace(valid_count=1, blocked_count=0),
        recommendations=SimpleNamespace(counts={}),
        coverage={},
        review_report_path=review_path,
        feedback=SimpleNamespace(
            feedback_by_id={"job_1": object()},
            invalid_records=[],
            conflicts=[],
            template_rows_ignored=1998,
        ),
    )
    result = SimpleNamespace(
        preview=preview,
        plan_fingerprint="abc123",
        artifact_path=tmp_path / "incremental_plan_abc123.json",
    )
    monkeypatch.setattr(
        "research_radar.cli._required_live_pilot_adapter",
        lambda **_: adapter,
    )
    monkeypatch.setattr(
        "research_radar.cli.prepare_incremental_live_sync",
        lambda **_: result,
    )

    exit_code = main(["sheets-sync", "--live", "--incremental", "--dry-run"])

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert exit_code == 0
    assert "incremental" in output
    assert "feedback: loaded=1; invalid=0; conflicts=0; template_rows=1998" in output
    assert "plan fingerprint: abc123" in output
    assert "no writes performed" in output


def test_live_pilot_init_dry_run_uses_only_dedicated_adapter(
    monkeypatch: pytest.MonkeyPatch, capsys: object
) -> None:
    class PilotAdapter:
        settings = SimpleNamespace(environment="live-pilot")

        def get_spreadsheet_title(self) -> str:
            return "ResearchRadar AI — LIVE PILOT"

        def initialize_workbook(self, *, apply: bool) -> object:
            assert apply is False
            return SimpleNamespace(
                existing_sheets=(),
                missing_sheets=tuple(SHEET_SCHEMAS),
                incompatible_headers={},
            )

    monkeypatch.setattr("research_radar.cli.configured_live_pilot_adapter", lambda: PilotAdapter())
    monkeypatch.setattr(
        "research_radar.cli._live_adapter",
        lambda: pytest.fail("TEST spreadsheet adapter must not be loaded"),
    )

    exit_code = main(["sheets-init", "--live", "--dry-run"])

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert exit_code == 0
    assert "LIVE PILOT" in output
    assert "no writes performed" in output


def test_live_pilot_init_apply_is_narrowly_authorized(
    monkeypatch: pytest.MonkeyPatch, capsys: object
) -> None:
    apply_calls: list[bool] = []

    class PilotAdapter:
        settings = SimpleNamespace(environment="live-pilot", spreadsheet_id="pilot-id")

        def get_spreadsheet_title(self) -> str:
            return "ResearchRadar AI — LIVE PILOT"

        def initialize_workbook(self, *, apply: bool) -> object:
            apply_calls.append(apply)
            return SimpleNamespace(
                existing_sheets=(),
                missing_sheets=tuple(SHEET_SCHEMAS),
                incompatible_headers={},
            )

    monkeypatch.setenv("GOOGLE_LIVE_PILOT_SPREADSHEET_ID", "pilot-id")
    monkeypatch.setenv("RESEARCH_RADAR_SHEETS_ENV", "live-pilot")
    monkeypatch.setenv("RESEARCH_RADAR_DATA_MODE", "live")
    monkeypatch.setattr(
        "research_radar.cli.configured_live_pilot_adapter",
        lambda: PilotAdapter(),
    )
    monkeypatch.setattr(
        "research_radar.cli._live_adapter",
        lambda: pytest.fail("TEST spreadsheet adapter must not be loaded"),
    )

    assert main(["sheets-init", "--live", "--apply"]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "LIVE PILOT initialization (apply)" in output
    assert "created: 7 worksheet(s)" in output
    assert apply_calls == [True]


@pytest.mark.parametrize(
    ("variable", "value", "message"),
    [
        ("RESEARCH_RADAR_DATA_MODE", "synthetic", "DATA_MODE"),
        ("RESEARCH_RADAR_SHEETS_ENV", "test", "live-pilot"),
    ],
)
def test_live_pilot_init_apply_rejects_wrong_write_environment_before_initialization(
    monkeypatch: pytest.MonkeyPatch,
    capsys: object,
    variable: str,
    value: str,
    message: str,
) -> None:
    monkeypatch.setenv("GOOGLE_LIVE_PILOT_SPREADSHEET_ID", "pilot-id")
    monkeypatch.setenv("RESEARCH_RADAR_SHEETS_ENV", "live-pilot")
    monkeypatch.setenv("RESEARCH_RADAR_DATA_MODE", "live")
    monkeypatch.setenv(variable, value)
    monkeypatch.setattr(
        "research_radar.cli.configured_live_pilot_adapter",
        lambda: pytest.fail("adapter must not load for an invalid write environment"),
    )

    assert main(["sheets-init", "--live", "--apply"]) == 1
    assert message in capsys.readouterr().out  # type: ignore[attr-defined]


def test_live_pilot_init_apply_rejects_adapter_id_mismatch(
    monkeypatch: pytest.MonkeyPatch, capsys: object
) -> None:
    class WrongPilotAdapter:
        settings = SimpleNamespace(environment="live-pilot", spreadsheet_id="wrong-id")

        def get_spreadsheet_title(self) -> str:
            return "ResearchRadar AI — LIVE PILOT"

        def initialize_workbook(self, *, apply: bool) -> object:
            pytest.fail("initialization must not run for an ID mismatch")

    monkeypatch.setenv("GOOGLE_LIVE_PILOT_SPREADSHEET_ID", "approved-id")
    monkeypatch.setenv("RESEARCH_RADAR_SHEETS_ENV", "live-pilot")
    monkeypatch.setenv("RESEARCH_RADAR_DATA_MODE", "live")
    monkeypatch.setattr(
        "research_radar.cli.configured_live_pilot_adapter", lambda: WrongPilotAdapter()
    )

    assert main(["sheets-init", "--live", "--apply"]) == 1
    assert "does not match" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_live_pilot_init_apply_rejects_wrong_workbook_title(
    monkeypatch: pytest.MonkeyPatch, capsys: object
) -> None:
    class WrongTitleAdapter:
        settings = SimpleNamespace(environment="live-pilot", spreadsheet_id="approved-id")

        def get_spreadsheet_title(self) -> str:
            return "ResearchRadar AI — TEST"

        def initialize_workbook(self, *, apply: bool) -> object:
            pytest.fail("initialization must not run for a title mismatch")

    monkeypatch.setenv("GOOGLE_LIVE_PILOT_SPREADSHEET_ID", "approved-id")
    monkeypatch.setenv("RESEARCH_RADAR_SHEETS_ENV", "live-pilot")
    monkeypatch.setenv("RESEARCH_RADAR_DATA_MODE", "live")
    monkeypatch.setattr(
        "research_radar.cli.configured_live_pilot_adapter", lambda: WrongTitleAdapter()
    )

    assert main(["sheets-init", "--live", "--apply"]) == 1
    assert "LIVE PILOT" in capsys.readouterr().out  # type: ignore[attr-defined]
