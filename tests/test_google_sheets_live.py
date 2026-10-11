from __future__ import annotations

import os

import pytest

from research_radar.storage.google_sheets import GoogleSheetsAdapter


@pytest.mark.live_google_sheets
@pytest.mark.skipif(
    os.getenv("RUN_GOOGLE_SHEETS_LIVE_TEST") != "1",
    reason="set RUN_GOOGLE_SHEETS_LIVE_TEST=1 to run the authenticated read-only test",
)
def test_live_spreadsheet_status_is_read_only() -> None:
    adapter = GoogleSheetsAdapter.from_environment()

    status = adapter.get_status()

    assert set(status.worksheets) | set(status.missing_sheets)
