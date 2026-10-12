"""Live Google Sheets adapter built on the official Google API Python client."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from research_radar.storage.google_auth import DefaultGoogleCredentialsProvider
from research_radar.storage.sheets import (
    SHEET_SCHEMAS,
    SheetSchemaError,
    SheetsOperationError,
    SheetSyncPlan,
    WorksheetData,
    is_blank_feedback_template_row,
)


class SheetsConfigurationError(ValueError):
    """Raised when live spreadsheet configuration is missing or unsafe."""


class GoogleSheetsError(SheetsOperationError):
    """Base error for live Google Sheets operations."""


class GoogleSheetsPermissionError(GoogleSheetsError):
    """Raised when the authenticated identity lacks spreadsheet access."""


class MissingSpreadsheetError(GoogleSheetsError):
    """Raised when the configured spreadsheet does not exist or is inaccessible."""


class MissingWorksheetError(GoogleSheetsError):
    """Raised when an approved worksheet has not been initialized."""


class ConcurrentSheetChangeError(GoogleSheetsError):
    """Raised when a row moved or changed after synchronization planning."""


@dataclass(frozen=True)
class GoogleSheetsSettings:
    spreadsheet_id: str
    environment: str

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> GoogleSheetsSettings:
        values = environment if environment is not None else os.environ
        spreadsheet_id = values.get("GOOGLE_SPREADSHEET_ID", "").strip()
        if not spreadsheet_id:
            raise SheetsConfigurationError("GOOGLE_SPREADSHEET_ID is required")
        sheets_environment = values.get("RESEARCH_RADAR_SHEETS_ENV", "").strip().casefold()
        if sheets_environment not in {"test", "production"}:
            raise SheetsConfigurationError(
                "RESEARCH_RADAR_SHEETS_ENV must be 'test' or 'production'"
            )
        return cls(spreadsheet_id=spreadsheet_id, environment=sheets_environment)

    def require_demo_writes_allowed(self) -> None:
        if self.environment != "test":
            raise SheetsConfigurationError(
                "synthetic demo writes are allowed only when RESEARCH_RADAR_SHEETS_ENV=test"
            )


@dataclass(frozen=True)
class SheetsInitializationPlan:
    existing_sheets: tuple[str, ...]
    missing_sheets: tuple[str, ...]
    incompatible_headers: dict[str, tuple[str, ...]]
    sheet_ids: dict[str, int]

    @property
    def safe_to_apply(self) -> bool:
        return not self.incompatible_headers


@dataclass(frozen=True)
class WorksheetStatus:
    row_count: int
    headers_valid: bool
    template_row_count: int = 0


@dataclass(frozen=True)
class WorkbookStatus:
    worksheets: dict[str, WorksheetStatus]
    missing_sheets: tuple[str, ...]


def _http_status(exc: Exception) -> int | None:
    response = getattr(exc, "resp", None)
    status = getattr(response, "status", None)
    if isinstance(status, int):
        return status
    status_code = getattr(exc, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def _quote_sheet_name(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


class GoogleSheetsAdapter:
    """Concrete SheetsAdapter using the official Google Sheets API v4 client."""

    def __init__(
        self,
        settings: GoogleSheetsSettings,
        *,
        service: Any,
        max_attempts: int = 4,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.settings = settings
        self.service = service
        self.max_attempts = max_attempts
        self.sleep = sleep

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        *,
        credential_provider: DefaultGoogleCredentialsProvider | None = None,
    ) -> GoogleSheetsAdapter:
        settings = GoogleSheetsSettings.from_environment(environment)
        return cls.from_settings(
            settings,
            environment=environment,
            credential_provider=credential_provider,
        )

    @classmethod
    def from_settings(
        cls,
        settings: GoogleSheetsSettings,
        *,
        environment: Mapping[str, str] | None = None,
        credential_provider: DefaultGoogleCredentialsProvider | None = None,
    ) -> GoogleSheetsAdapter:
        """Build an adapter for already validated, explicitly scoped settings."""

        provider = credential_provider or DefaultGoogleCredentialsProvider(environment)
        credentials = provider.get_credentials()
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise GoogleSheetsError(
                "Google Sheets dependencies are not installed; install the 'sheets' extra"
            ) from exc
        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        return cls(settings, service=service)

    def _execute(self, request_factory: Callable[[], Any]) -> dict[str, Any]:
        for attempt in range(self.max_attempts):
            try:
                result = request_factory().execute()
                return result if isinstance(result, dict) else {}
            except Exception as exc:
                status = _http_status(exc)
                transient = status in {429, 500, 502, 503, 504} or (
                    status is None and isinstance(exc, OSError)
                )
                if transient and attempt + 1 < self.max_attempts:
                    self.sleep(float(2**attempt))
                    continue
                if status == 401:
                    raise GoogleSheetsError("Google authentication was rejected") from exc
                if status == 403:
                    raise GoogleSheetsPermissionError(
                        "permission denied for the configured spreadsheet"
                    ) from exc
                if status == 404:
                    raise MissingSpreadsheetError(
                        "configured Google spreadsheet was not found"
                    ) from exc
                if transient:
                    raise GoogleSheetsError(
                        "Google Sheets request failed after exponential-backoff retries"
                    ) from exc
                raise GoogleSheetsError("Google Sheets request failed") from exc
        raise AssertionError("retry loop must return or raise")

    def read_worksheet(self, name: str) -> WorksheetData:
        schema = SHEET_SCHEMAS.get(name)
        if schema is None:
            raise MissingWorksheetError(f"unsupported worksheet: {name}")
        end_column = _column_letter(len(schema.headers))
        range_name = f"{_quote_sheet_name(name)}!A:{end_column}"
        response = self._execute(
            lambda: (
                self.service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self.settings.spreadsheet_id,
                    range=range_name,
                    valueRenderOption="UNFORMATTED_VALUE",
                    dateTimeRenderOption="FORMATTED_STRING",
                )
            )
        )
        values = response.get("values", [])
        if not values:
            return WorksheetData(headers=(), rows=[])
        raw_headers = values[0]
        headers = tuple(str(value) for value in raw_headers)
        rows: list[dict[str, Any]] = []
        for raw_row in values[1:]:
            padded = list(raw_row) + [""] * max(0, len(headers) - len(raw_row))
            rows.append(dict(zip(headers, padded, strict=False)))
        return WorksheetData(headers=headers, rows=rows)

    def get_spreadsheet_title(self) -> str:
        """Read the configured workbook title without modifying Drive or Sheets state."""

        response = self._execute(
            lambda: self.service.spreadsheets().get(
                spreadsheetId=self.settings.spreadsheet_id,
                fields="properties(title)",
            )
        )
        title = response.get("properties", {}).get("title")
        if not isinstance(title, str) or not title:
            raise GoogleSheetsError("configured spreadsheet did not return a title")
        return title

    def read_record_ids(self, name: str) -> dict[str, int]:
        worksheet = self.read_worksheet(name)
        schema = SHEET_SCHEMAS[name]
        if worksheet.headers != schema.headers:
            raise SheetSchemaError(f"{name} headers do not match the expected schema")
        result: dict[str, int] = {}
        for row_number, row in enumerate(worksheet.rows, start=2):
            record_id = row.get(schema.record_id_header)
            if not isinstance(record_id, str) or not record_id.strip():
                raise GoogleSheetsError(f"{name} row {row_number} has no Record_ID")
            if record_id in result:
                raise GoogleSheetsError(f"duplicate Record_ID in {name}: {record_id}")
            result[record_id] = row_number
        return result

    def initialize_workbook(self, *, apply: bool) -> SheetsInitializationPlan:
        """Inspect approved worksheets and optionally create only missing structures."""

        metadata = self._execute(
            lambda: self.service.spreadsheets().get(
                spreadsheetId=self.settings.spreadsheet_id,
                fields="sheets(properties(sheetId,title))",
            )
        )
        existing_properties = {
            str(sheet.get("properties", {}).get("title")): sheet.get("properties", {})
            for sheet in metadata.get("sheets", [])
        }
        existing_names = tuple(name for name in SHEET_SCHEMAS if name in existing_properties)
        missing_names = tuple(name for name in SHEET_SCHEMAS if name not in existing_properties)
        incompatible: dict[str, tuple[str, ...]] = {}
        sheet_ids = {
            name: int(properties["sheetId"])
            for name, properties in existing_properties.items()
            if name in SHEET_SCHEMAS and isinstance(properties.get("sheetId"), int)
        }
        for name in existing_names:
            worksheet = self.read_worksheet(name)
            if worksheet.headers != SHEET_SCHEMAS[name].headers:
                incompatible[name] = worksheet.headers

        used_ids = {
            int(properties["sheetId"])
            for properties in existing_properties.values()
            if isinstance(properties.get("sheetId"), int)
        }
        for name in missing_names:
            sheet_ids[name] = _stable_sheet_id(name, used_ids)
            used_ids.add(sheet_ids[name])

        plan = SheetsInitializationPlan(
            existing_sheets=existing_names,
            missing_sheets=missing_names,
            incompatible_headers=incompatible,
            sheet_ids=sheet_ids,
        )
        if apply:
            if not plan.safe_to_apply:
                raise SheetSchemaError(
                    "existing worksheet headers are incompatible; initialization was not applied"
                )
            if plan.missing_sheets:
                requests: list[dict[str, Any]] = []
                for name in plan.missing_sheets:
                    requests.extend(_initialization_requests(name, plan.sheet_ids[name]))
                self._execute(
                    lambda: self.service.spreadsheets().batchUpdate(
                        spreadsheetId=self.settings.spreadsheet_id,
                        body={"requests": requests},
                    )
                )
        return plan

    def get_status(self) -> WorkbookStatus:
        """Check connectivity, approved worksheets, headers, and row counts without writes."""

        metadata = self._execute(
            lambda: self.service.spreadsheets().get(
                spreadsheetId=self.settings.spreadsheet_id,
                fields="sheets(properties(sheetId,title))",
            )
        )
        existing = {
            str(sheet.get("properties", {}).get("title")) for sheet in metadata.get("sheets", [])
        }
        worksheets: dict[str, WorksheetStatus] = {}
        missing: list[str] = []
        for name, schema in SHEET_SCHEMAS.items():
            if name not in existing:
                missing.append(name)
                continue
            worksheet = self.read_worksheet(name)
            template_row_count = (
                sum(is_blank_feedback_template_row(row) for row in worksheet.rows)
                if name == "My_Feedback"
                else 0
            )
            worksheets[name] = WorksheetStatus(
                row_count=len(worksheet.rows) - template_row_count,
                headers_valid=worksheet.headers == schema.headers,
                template_row_count=template_row_count,
            )
        return WorkbookStatus(worksheets=worksheets, missing_sheets=tuple(missing))

    def apply_plan(self, plan: SheetSyncPlan, *, dry_run: bool) -> None:
        """Apply a validated plan with fresh row-ID checks and RAW value writes."""

        if dry_run:
            return
        if plan.conflicts:
            raise GoogleSheetsError(
                f"{plan.sheet_name} has synchronization conflicts; no writes were applied"
            )
        schema = SHEET_SCHEMAS[plan.sheet_name]
        current = self.read_worksheet(plan.sheet_name)
        if current.headers != schema.headers:
            raise SheetSchemaError(
                f"{plan.sheet_name} headers changed after planning; no writes were applied"
            )
        current_ids: dict[str, int] = {}
        for row_number, row in enumerate(current.rows, start=2):
            record_id = row.get(schema.record_id_header)
            if not isinstance(record_id, str) or not record_id:
                raise GoogleSheetsError(f"{plan.sheet_name} row {row_number} has no Record_ID")
            if record_id in current_ids:
                raise GoogleSheetsError(f"duplicate Record_ID in {plan.sheet_name}: {record_id}")
            current_ids[record_id] = row_number

        update_data: list[dict[str, Any]] = []
        for operation in plan.updates:
            current_row = current_ids.get(operation.record_id)
            if current_row != operation.row_number:
                raise ConcurrentSheetChangeError(
                    f"{plan.sheet_name} changed after planning; Record_ID row mapping is stale"
                )
            current_record = current.rows[current_row - 2]
            if any(
                current_record.get(header, "") != expected
                for header, expected in operation.expected_values.items()
            ):
                raise ConcurrentSheetChangeError(
                    f"{plan.sheet_name} changed after planning; source values are stale"
                )
            for header, value in operation.changed_fields.items():
                column = _column_letter(schema.headers.index(header) + 1)
                update_data.append(
                    {
                        "range": f"{_quote_sheet_name(plan.sheet_name)}!{column}{current_row}",
                        "values": [[value]],
                    }
                )
        if update_data:
            self._execute(
                lambda: (
                    self.service.spreadsheets()
                    .values()
                    .batchUpdate(
                        spreadsheetId=self.settings.spreadsheet_id,
                        body={"valueInputOption": "RAW", "data": update_data},
                    )
                )
            )

        inserts = [
            operation.row
            for operation in plan.inserts
            if operation.row.get(schema.record_id_header) not in current_ids
        ]
        if inserts:
            self._append_rows(plan.sheet_name, inserts)
        self.append_unique("Change_Log", plan.change_log_rows)

    def append_unique(self, sheet_name: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        schema = SHEET_SCHEMAS[sheet_name]
        current = self.read_worksheet(sheet_name)
        if current.headers != schema.headers:
            raise SheetSchemaError(
                f"{sheet_name} headers do not match the expected schema; append refused"
            )
        existing_ids: set[str] = set()
        for row_number, row in enumerate(current.rows, start=2):
            record_id = row.get(schema.record_id_header)
            if not isinstance(record_id, str) or not record_id:
                raise GoogleSheetsError(f"{sheet_name} row {row_number} has no Record_ID")
            if record_id in existing_ids:
                raise GoogleSheetsError(f"duplicate Record_ID in {sheet_name}: {record_id}")
            existing_ids.add(record_id)
        additions = [row for row in rows if row.get(schema.record_id_header) not in existing_ids]
        if additions:
            self._append_rows(sheet_name, additions)

    def _append_rows(self, sheet_name: str, rows: list[dict[str, Any]]) -> None:
        schema = SHEET_SCHEMAS[sheet_name]
        values = [[row.get(header, "") for header in schema.headers] for row in rows]
        self._execute(
            lambda: (
                self.service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=self.settings.spreadsheet_id,
                    range=f"{_quote_sheet_name(sheet_name)}!A:{_column_letter(len(schema.headers))}",
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body={"majorDimension": "ROWS", "values": values},
                )
            )
        )


def _column_letter(index: int) -> str:
    if index < 1:
        raise ValueError("column index must be positive")
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _stable_sheet_id(name: str, used_ids: set[int]) -> int:
    candidate = int.from_bytes(sha256(name.encode("utf-8")).digest()[:4], "big") & 0x7FFFFFFF
    while candidate in used_ids:
        candidate = (candidate + 1) & 0x7FFFFFFF
    return candidate


def _grid_range(sheet_id: int, start_column: int, end_column: int) -> dict[str, int]:
    return {
        "sheetId": sheet_id,
        "startRowIndex": 1,
        "endRowIndex": 2000,
        "startColumnIndex": start_column,
        "endColumnIndex": end_column,
    }


def _format_columns(name: str, headers: tuple[str, ...], sheet_id: int) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    date_headers = {
        "First_Seen",
        "Last_Seen",
        "Application_Deadline",
        "Start_Date",
        "End_Date",
        "Submission_Deadline",
        "Registration_Deadline",
        "Timestamp",
        "Updated_At",
    }
    score_headers = {
        "Research_Relevance",
        "PhD_Leverage",
        "Skills_Career_Fit",
        "Compensation_Score",
        "Overall_Priority_Score",
        "Research_Fit_Score",
        "Priority_Score",
    }
    for index, header in enumerate(headers):
        if header in date_headers:
            requests.append(
                {
                    "repeatCell": {
                        "range": _grid_range(sheet_id, index, index + 1),
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "DATE_TIME"
                                    if header
                                    in {"First_Seen", "Last_Seen", "Timestamp", "Updated_At"}
                                    else "DATE",
                                    "pattern": "yyyy-mm-dd hh:mm"
                                    if header
                                    in {"First_Seen", "Last_Seen", "Timestamp", "Updated_At"}
                                    else "yyyy-mm-dd",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                }
            )
        if header in score_headers:
            requests.append(
                {
                    "repeatCell": {
                        "range": _grid_range(sheet_id, index, index + 1),
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {"type": "NUMBER", "pattern": "0.00"}
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                }
            )
    if name == "My_Feedback":
        preference_index = headers.index("Preference")
        requests.append(
            {
                "setDataValidation": {
                    "range": _grid_range(sheet_id, preference_index, preference_index + 1),
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [
                                {"userEnteredValue": value}
                                for value in (
                                    "None",
                                    "Very Interested",
                                    "Interested",
                                    "Not Relevant",
                                )
                            ],
                        },
                        "strict": True,
                        "showCustomUi": True,
                    },
                }
            }
        )
        for header in ("Saved", "Hidden"):
            index = headers.index(header)
            requests.append(
                {
                    "setDataValidation": {
                        "range": _grid_range(sheet_id, index, index + 1),
                        "rule": {"condition": {"type": "BOOLEAN"}, "strict": True},
                    }
                }
            )
    return requests


def _initialization_requests(name: str, sheet_id: int) -> list[dict[str, Any]]:
    schema = SHEET_SCHEMAS[name]
    column_count = len(schema.headers)
    header_values = [{"userEnteredValue": {"stringValue": header}} for header in schema.headers]
    requests: list[dict[str, Any]] = [
        {
            "addSheet": {
                "properties": {
                    "sheetId": sheet_id,
                    "title": name,
                    "gridProperties": {
                        "rowCount": 2000,
                        "columnCount": column_count,
                        "frozenRowCount": 1,
                    },
                }
            }
        },
        {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": column_count,
                },
                "rows": [{"values": header_values}],
                "fields": "userEnteredValue",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": column_count,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                        "backgroundColor": {"red": 0.9, "green": 0.93, "blue": 0.97},
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        },
        {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 2000,
                        "startColumnIndex": 0,
                        "endColumnIndex": column_count,
                    }
                }
            }
        },
        {
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": column_count,
                }
            }
        },
    ]
    requests.extend(_format_columns(name, schema.headers, sheet_id))
    return requests
