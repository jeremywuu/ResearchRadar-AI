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
