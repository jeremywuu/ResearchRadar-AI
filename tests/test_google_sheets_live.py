from __future__ import annotations

import os

import pytest

from research_radar.live_integration import (
    configured_live_pilot_adapter,
    validate_live_pilot_identity,
)
from research_radar.storage.google_sheets import GoogleSheetsAdapter


@pytest.mark.live_google_sheets
@pytest.mark.skipif(
    os.getenv("RUN_GOOGLE_SHEETS_LIVE_TEST") != "1",
    reason="set RUN_GOOGLE_SHEETS_LIVE_TEST=1 to run the authenticated read-only test",
)
def test_live_spreadsheet_status_is_read_only() -> None:
    if os.getenv("RESEARCH_RADAR_SHEETS_ENV") == "live-pilot":
        adapter = configured_live_pilot_adapter()
        assert adapter is not None
        validate_live_pilot_identity(adapter)
    else:
        adapter = GoogleSheetsAdapter.from_environment()

    status = adapter.get_status()

    assert set(status.worksheets) | set(status.missing_sheets)
