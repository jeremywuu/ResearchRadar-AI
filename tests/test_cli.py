from pathlib import Path

from research_radar.cli import main

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
