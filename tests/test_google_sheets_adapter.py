from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from research_radar.storage.google_auth import (
    DefaultGoogleCredentialsProvider,
    SheetsAuthenticationError,
)
from research_radar.storage.google_sheets import (
    ConcurrentSheetChangeError,
    GoogleSheetsAdapter,
    GoogleSheetsError,
    GoogleSheetsPermissionError,
    GoogleSheetsSettings,
    MissingSpreadsheetError,
    SheetsConfigurationError,
)
from research_radar.storage.sheets import (
    CHANGE_LOG_SCHEMA,
    INDUSTRY_JOBS_SCHEMA,
    SHEET_SCHEMAS,
    WorksheetData,
    plan_sheet_sync,
)


class FakeHttpError(Exception):
    def __init__(self, status: int) -> None:
        self.resp = type("Response", (), {"status": status})()
        super().__init__(f"HTTP {status}")


class FakeRequest:
    def __init__(self, action: Callable[[], dict[str, Any]]) -> None:
        self.action = action

    def execute(self) -> dict[str, Any]:
        return self.action()


class FakeValuesResource:
    def __init__(self, service: FakeSheetsService) -> None:
        self.service = service

    def get(self, **kwargs: Any) -> FakeRequest:
        self.service.calls.append(("values.get", kwargs))
        return FakeRequest(lambda: self.service.next_response("values.get"))

    def append(self, **kwargs: Any) -> FakeRequest:
        self.service.calls.append(("values.append", kwargs))
        return FakeRequest(lambda: self.service.next_response("values.append"))

    def batchUpdate(self, **kwargs: Any) -> FakeRequest:  # noqa: N802 - Google client method
        self.service.calls.append(("values.batchUpdate", kwargs))
        return FakeRequest(lambda: self.service.next_response("values.batchUpdate"))


class FakeSpreadsheetsResource:
    def __init__(self, service: FakeSheetsService) -> None:
        self.service = service

    def values(self) -> FakeValuesResource:
        return FakeValuesResource(self.service)

    def get(self, **kwargs: Any) -> FakeRequest:
        self.service.calls.append(("spreadsheets.get", kwargs))
        return FakeRequest(lambda: self.service.next_response("spreadsheets.get"))

    def batchUpdate(self, **kwargs: Any) -> FakeRequest:  # noqa: N802
        self.service.calls.append(("spreadsheets.batchUpdate", kwargs))
        return FakeRequest(lambda: self.service.next_response("spreadsheets.batchUpdate"))


class FakeSheetsService:
    def __init__(self, responses: dict[str, list[object]]) -> None:
        self.responses = {name: list(items) for name, items in responses.items()}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def spreadsheets(self) -> FakeSpreadsheetsResource:
        return FakeSpreadsheetsResource(self)

    def next_response(self, method: str) -> dict[str, Any]:
        response = self.responses.get(method, [{}]).pop(0)
        if isinstance(response, Exception):
            raise response
        assert isinstance(response, dict)
        return response


def test_live_settings_require_spreadsheet_id_and_explicit_environment() -> None:
    with pytest.raises(SheetsConfigurationError, match="GOOGLE_SPREADSHEET_ID"):
        GoogleSheetsSettings.from_environment({})

    with pytest.raises(SheetsConfigurationError, match="RESEARCH_RADAR_SHEETS_ENV"):
        GoogleSheetsSettings.from_environment({"GOOGLE_SPREADSHEET_ID": "sheet-id"})

    settings = GoogleSheetsSettings.from_environment(
        {
            "GOOGLE_SPREADSHEET_ID": "sheet-id",
            "RESEARCH_RADAR_SHEETS_ENV": "test",
        }
    )
    assert settings.spreadsheet_id == "sheet-id"
    assert settings.environment == "test"


def test_authentication_failure_does_not_expose_credential_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret_path = tmp_path / "oauth-secret.json"
    provider = DefaultGoogleCredentialsProvider(
        environment={"GOOGLE_OAUTH_CLIENT_SECRET_FILE": str(secret_path)}
    )

    def fail_modules() -> object:
        raise ImportError("google auth dependency unavailable")

    monkeypatch.setattr(provider, "_load_official_libraries", fail_modules)

    with pytest.raises(SheetsAuthenticationError) as caught:
        provider.get_credentials()

    assert str(secret_path) not in str(caught.value)


def test_adapter_reads_rows_with_the_declared_headers() -> None:
    service = FakeSheetsService(
        {
            "values.get": [
                {
                    "values": [
                        list(INDUSTRY_JOBS_SCHEMA.headers),
                        ["job_1", "AI Research Scientist", "Fictional AI Lab"],
                    ]
                }
            ]
        }
    )
    adapter = GoogleSheetsAdapter(GoogleSheetsSettings("sheet-id", "test"), service=service)

    worksheet = adapter.read_worksheet("Industry_Jobs")

    assert worksheet.headers == INDUSTRY_JOBS_SCHEMA.headers
    assert worksheet.rows[0]["Record_ID"] == "job_1"
    assert worksheet.rows[0]["Job_Title"] == "AI Research Scientist"
    assert worksheet.rows[0]["Opportunity_Status"] == ""
    assert service.calls[0][1]["spreadsheetId"] == "sheet-id"


def test_adapter_reads_spreadsheet_title_without_writing() -> None:
    service = FakeSheetsService(
        {"spreadsheets.get": [{"properties": {"title": "ResearchRadar AI — LIVE PILOT"}}]}
    )
    adapter = GoogleSheetsAdapter(GoogleSheetsSettings("pilot-id", "live-pilot"), service=service)

    assert adapter.get_spreadsheet_title() == "ResearchRadar AI — LIVE PILOT"
    assert [name for name, _ in service.calls] == ["spreadsheets.get"]


def test_missing_spreadsheet_has_a_clear_error() -> None:
    service = FakeSheetsService({"values.get": [FakeHttpError(404)]})
    adapter = GoogleSheetsAdapter(
        GoogleSheetsSettings("missing-id", "test"), service=service, max_attempts=1
    )

    with pytest.raises(MissingSpreadsheetError, match="not found"):
        adapter.read_worksheet("Industry_Jobs")


def test_permission_error_has_a_clear_error() -> None:
    service = FakeSheetsService({"values.get": [FakeHttpError(403)]})
    adapter = GoogleSheetsAdapter(
        GoogleSheetsSettings("sheet-id", "test"), service=service, max_attempts=1
    )

    with pytest.raises(GoogleSheetsPermissionError, match="permission denied"):
        adapter.read_worksheet("Industry_Jobs")


def test_rate_limits_and_network_failures_use_exponential_backoff() -> None:
    sleeps: list[float] = []
    service = FakeSheetsService(
        {
            "values.get": [
                FakeHttpError(429),
                OSError("temporary network failure"),
                {"values": [list(INDUSTRY_JOBS_SCHEMA.headers)]},
            ]
        }
    )
    adapter = GoogleSheetsAdapter(
        GoogleSheetsSettings("sheet-id", "test"),
        service=service,
        max_attempts=3,
        sleep=sleeps.append,
    )

    worksheet = adapter.read_worksheet("Industry_Jobs")

    assert worksheet.rows == []
    assert sleeps == [1.0, 2.0]
    assert [name for name, _ in service.calls] == ["values.get", "values.get", "values.get"]


def test_initialization_dry_run_preserves_existing_sheets_and_reports_missing() -> None:
    service = FakeSheetsService(
        {
            "spreadsheets.get": [
                {"sheets": [{"properties": {"sheetId": 10, "title": "Industry_Jobs"}}]}
            ],
            "values.get": [{"values": [list(INDUSTRY_JOBS_SCHEMA.headers)]}],
        }
    )
    adapter = GoogleSheetsAdapter(GoogleSheetsSettings("sheet-id", "test"), service=service)

    plan = adapter.initialize_workbook(apply=False)

    assert plan.existing_sheets == ("Industry_Jobs",)
    assert set(plan.missing_sheets) == set(SHEET_SCHEMAS) - {"Industry_Jobs"}
    assert not plan.incompatible_headers
    assert [name for name, _ in service.calls].count("spreadsheets.batchUpdate") == 0


def test_initialization_rejects_incompatible_existing_headers() -> None:
    service = FakeSheetsService(
        {
            "spreadsheets.get": [
                {"sheets": [{"properties": {"sheetId": 10, "title": "Industry_Jobs"}}]}
            ],
            "values.get": [{"values": [["Wrong_Header"]]}],
        }
    )
    adapter = GoogleSheetsAdapter(GoogleSheetsSettings("sheet-id", "test"), service=service)

    plan = adapter.initialize_workbook(apply=False)

    assert plan.incompatible_headers == {"Industry_Jobs": ("Wrong_Header",)}
    assert plan.safe_to_apply is False


def test_initialization_creates_only_missing_sheets_with_formatting_and_validation() -> None:
    service = FakeSheetsService(
        {
            "spreadsheets.get": [{"sheets": []}],
            "spreadsheets.batchUpdate": [{}],
        }
    )
    adapter = GoogleSheetsAdapter(GoogleSheetsSettings("sheet-id", "test"), service=service)

    plan = adapter.initialize_workbook(apply=True)

    assert set(plan.missing_sheets) == set(SHEET_SCHEMAS)
    batch_call = next(
        kwargs for name, kwargs in service.calls if name == "spreadsheets.batchUpdate"
    )
    requests = batch_call["body"]["requests"]
    assert sum("addSheet" in request for request in requests) == len(SHEET_SCHEMAS)
    assert any("setBasicFilter" in request for request in requests)
    assert any("autoResizeDimensions" in request for request in requests)
    validation_requests = [request for request in requests if "setDataValidation" in request]
    assert len(validation_requests) == 3
    preference_rule = validation_requests[0]["setDataValidation"]["rule"]
    assert {item["userEnteredValue"] for item in preference_rule["condition"]["values"]} == {
        "None",
        "Very Interested",
        "Interested",
        "Not Relevant",
    }
    assert all(call[1].get("spreadsheetId") == "sheet-id" for call in service.calls)


def test_production_environment_refuses_synthetic_demo_writes() -> None:
    settings = GoogleSheetsSettings("sheet-id", "production")

    with pytest.raises(SheetsConfigurationError, match="only when.*test"):
        settings.require_demo_writes_allowed()


def _job_row(record_id: str, title: str) -> dict[str, object]:
    return {header: "" for header in INDUSTRY_JOBS_SCHEMA.headers} | {
        "Record_ID": record_id,
        "Job_Title": title,
        "Company": "Fictional AI Lab",
        "Source_URL": "https://fictional-ai.example/jobs/1",
        "First_Seen": "2026-10-01T09:00:00+00:00",
        "Last_Seen": "2026-10-11T09:00:00+00:00",
    }


NOW = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)


def test_live_apply_inserts_with_raw_values_and_is_retry_safe() -> None:
    malicious = _job_row("job_1", '=HYPERLINK("https://bad.example","click")')
    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        [malicious],
        WorksheetData(headers=INDUSTRY_JOBS_SCHEMA.headers, rows=[]),
        run_id="run_insert",
        timestamp=NOW,
    )
    service = FakeSheetsService(
        {
            "values.get": [
                {"values": [list(INDUSTRY_JOBS_SCHEMA.headers)]},
                {"values": [list(CHANGE_LOG_SCHEMA.headers)]},
                {"values": [list(INDUSTRY_JOBS_SCHEMA.headers), list(malicious.values())]},
                {
                    "values": [
                        list(CHANGE_LOG_SCHEMA.headers),
                        list(plan.change_log_rows[0].values()),
                    ]
                },
            ],
            "values.append": [{}, {}],
        }
    )
    adapter = GoogleSheetsAdapter(GoogleSheetsSettings("sheet-id", "test"), service=service)

    adapter.apply_plan(plan, dry_run=False)
    adapter.apply_plan(plan, dry_run=False)

    append_calls = [kwargs for name, kwargs in service.calls if name == "values.append"]
    assert len(append_calls) == 2
    assert all(call["valueInputOption"] == "RAW" for call in append_calls)
    assert append_calls[0]["body"]["values"][0][1].startswith("=")


def test_live_apply_updates_only_changed_cells_and_detects_manual_resort() -> None:
    old = _job_row("job_1", "Old title")
    new = _job_row("job_1", "New title")
    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        [new],
        WorksheetData(headers=INDUSTRY_JOBS_SCHEMA.headers, rows=[old]),
        run_id="run_update",
        timestamp=NOW,
    )
    service = FakeSheetsService(
        {
            "values.get": [
                {"values": [list(INDUSTRY_JOBS_SCHEMA.headers), list(old.values())]},
                {"values": [list(CHANGE_LOG_SCHEMA.headers)]},
            ],
            "values.batchUpdate": [{}],
            "values.append": [{}],
        }
    )
    adapter = GoogleSheetsAdapter(GoogleSheetsSettings("sheet-id", "test"), service=service)

    adapter.apply_plan(plan, dry_run=False)

    update_call = next(kwargs for name, kwargs in service.calls if name == "values.batchUpdate")
    assert update_call["body"]["valueInputOption"] == "RAW"
    assert update_call["body"]["data"] == [
        {"range": "'Industry_Jobs'!B2", "values": [["New title"]]}
    ]

    sorted_service = FakeSheetsService(
        {
            "values.get": [
                {
                    "values": [
                        list(INDUSTRY_JOBS_SCHEMA.headers),
                        list(_job_row("job_other", "Other").values()),
                        list(old.values()),
                    ]
                }
            ]
        }
    )
    sorted_adapter = GoogleSheetsAdapter(
        GoogleSheetsSettings("sheet-id", "test"), service=sorted_service
    )

    with pytest.raises(ConcurrentSheetChangeError, match="changed after planning"):
        sorted_adapter.apply_plan(plan, dry_run=False)
    assert not any(name == "values.batchUpdate" for name, _ in sorted_service.calls)

    edited = _job_row("job_1", "Manually edited title")
    edited_service = FakeSheetsService(
        {"values.get": [{"values": [list(INDUSTRY_JOBS_SCHEMA.headers), list(edited.values())]}]}
    )
    edited_adapter = GoogleSheetsAdapter(
        GoogleSheetsSettings("sheet-id", "test"), service=edited_service
    )

    with pytest.raises(ConcurrentSheetChangeError, match="source values are stale"):
        edited_adapter.apply_plan(plan, dry_run=False)
    assert not any(name == "values.batchUpdate" for name, _ in edited_service.calls)


def test_status_is_read_only_and_reports_missing_sheets_and_row_counts() -> None:
    service = FakeSheetsService(
        {
            "spreadsheets.get": [
                {"sheets": [{"properties": {"sheetId": 10, "title": "Industry_Jobs"}}]}
            ],
            "values.get": [
                {
                    "values": [
                        list(INDUSTRY_JOBS_SCHEMA.headers),
                        list(_job_row("job_1", "One").values()),
                        list(_job_row("job_2", "Two").values()),
                    ]
                }
            ],
        }
    )
    adapter = GoogleSheetsAdapter(GoogleSheetsSettings("sheet-id", "test"), service=service)

    status = adapter.get_status()

    assert status.worksheets["Industry_Jobs"].row_count == 2
    assert status.worksheets["Industry_Jobs"].headers_valid is True
    assert set(status.missing_sheets) == set(SHEET_SCHEMAS) - {"Industry_Jobs"}
    assert not any("Update" in name or "append" in name for name, _ in service.calls)


def test_status_distinguishes_feedback_records_from_blank_template_rows() -> None:
    blank_template = ["", "", False, False, "", ""]
    valid_feedback = [
        "job_1",
        "Interested",
        True,
        False,
        "Keep",
        "2026-10-11T09:00:00+00:00",
    ]
    service = FakeSheetsService(
        {
            "spreadsheets.get": [
                {"sheets": [{"properties": {"sheetId": 50, "title": "My_Feedback"}}]}
            ],
            "values.get": [
                {
                    "values": [
                        list(SHEET_SCHEMAS["My_Feedback"].headers),
                        valid_feedback,
                        *([blank_template] * 1999),
                    ]
                }
            ],
        }
    )
    adapter = GoogleSheetsAdapter(GoogleSheetsSettings("sheet-id", "test"), service=service)

    status = adapter.get_status()

    assert status.worksheets["My_Feedback"].row_count == 1
    assert status.worksheets["My_Feedback"].template_row_count == 1999


def test_duplicate_record_ids_are_rejected() -> None:
    duplicate = _job_row("job_1", "Duplicate")
    service = FakeSheetsService(
        {
            "values.get": [
                {
                    "values": [
                        list(INDUSTRY_JOBS_SCHEMA.headers),
                        list(duplicate.values()),
                        list(duplicate.values()),
                    ]
                }
            ]
        }
    )
    adapter = GoogleSheetsAdapter(GoogleSheetsSettings("sheet-id", "test"), service=service)

    with pytest.raises(GoogleSheetsError, match="duplicate Record_ID"):
        adapter.read_record_ids("Industry_Jobs")


def test_apply_dry_run_performs_no_api_calls() -> None:
    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        [_job_row("job_1", "Dry run")],
        WorksheetData(headers=INDUSTRY_JOBS_SCHEMA.headers, rows=[]),
        run_id="dry_run",
        timestamp=NOW,
    )
    service = FakeSheetsService({})
    adapter = GoogleSheetsAdapter(GoogleSheetsSettings("sheet-id", "test"), service=service)

    adapter.apply_plan(plan, dry_run=True)

    assert service.calls == []


def test_partial_api_failure_is_reported_without_claiming_atomicity() -> None:
    old = _job_row("job_1", "Old title")
    new = _job_row("job_1", "New title")
    plan = plan_sheet_sync(
        INDUSTRY_JOBS_SCHEMA,
        [new],
        WorksheetData(headers=INDUSTRY_JOBS_SCHEMA.headers, rows=[old]),
        run_id="partial",
        timestamp=NOW,
    )
    service = FakeSheetsService(
        {
            "values.get": [
                {"values": [list(INDUSTRY_JOBS_SCHEMA.headers), list(old.values())]},
                {"values": [list(CHANGE_LOG_SCHEMA.headers)]},
            ],
            "values.batchUpdate": [{}],
            "values.append": [FakeHttpError(503)],
        }
    )
    adapter = GoogleSheetsAdapter(
        GoogleSheetsSettings("sheet-id", "test"),
        service=service,
        max_attempts=1,
    )

    with pytest.raises(GoogleSheetsError, match="after exponential-backoff retries"):
        adapter.apply_plan(plan, dry_run=False)

    methods = [name for name, _ in service.calls]
    assert "values.batchUpdate" in methods
    assert "values.append" in methods
