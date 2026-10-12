"""Google credential discovery without embedding or logging secrets."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SHEETS_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)
SHEETS_READ_ONLY_SCOPES = ("https://www.googleapis.com/auth/spreadsheets.readonly",)


class SheetsAuthenticationError(RuntimeError):
    """Raised when Google credentials cannot be discovered or authorized."""


@dataclass(frozen=True)
class _OfficialAuthLibraries:
    adc: Any
    default_credentials_error: type[Exception]
    authorized_user_credentials: Any
    installed_app_flow: Any
    request_type: Any


class DefaultGoogleCredentialsProvider:
    """Discover ADC first, then optionally use an installed-app OAuth flow."""

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self.environment = environment if environment is not None else os.environ

    @staticmethod
    def _load_official_libraries() -> _OfficialAuthLibraries:
        try:
            import google.auth
            from google.auth.exceptions import DefaultCredentialsError
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise SheetsAuthenticationError(
                "Google Sheets dependencies are not installed; install the 'sheets' extra"
            ) from exc
        return _OfficialAuthLibraries(
            adc=google.auth.default,
            default_credentials_error=DefaultCredentialsError,
            authorized_user_credentials=Credentials,
            installed_app_flow=InstalledAppFlow,
            request_type=Request,
        )

    def get_credentials(self) -> Any:
        try:
            libraries = self._load_official_libraries()
        except (ImportError, SheetsAuthenticationError) as exc:
            raise SheetsAuthenticationError(
                "Google authentication support is unavailable; no credentials were loaded"
            ) from exc

        scopes = self._scopes()
        try:
            credentials, _ = libraries.adc(scopes=scopes)
            return credentials
        except libraries.default_credentials_error:
            pass

        token_path = Path(
            self.environment.get(
                "GOOGLE_OAUTH_TOKEN_FILE",
                str(Path.home() / ".config" / "research-radar" / "google-oauth-token.json"),
            )
        ).expanduser()
        client_file_value = self.environment.get("GOOGLE_OAUTH_CLIENT_SECRET_FILE")
        try:
            if token_path.is_file():
                credentials = libraries.authorized_user_credentials.from_authorized_user_file(
                    str(token_path), scopes
                )
                if credentials.expired and credentials.refresh_token:
                    credentials.refresh(libraries.request_type())
                    self._save_token(token_path, credentials.to_json())
                if credentials.valid:
                    return credentials
            if client_file_value:
                client_path = Path(client_file_value).expanduser()
                flow = libraries.installed_app_flow.from_client_secrets_file(
                    str(client_path), scopes
                )
                credentials = flow.run_local_server(port=0)
                self._save_token(token_path, credentials.to_json())
                return credentials
        except Exception as exc:
            raise SheetsAuthenticationError(
                "Google OAuth authorization failed; credential details were not logged"
            ) from exc

        raise SheetsAuthenticationError(
            "No Google credentials found. Configure Application Default Credentials or an "
            "installed-app OAuth client"
        )

    def _scopes(self) -> tuple[str, ...]:
        read_only = self.environment.get("RESEARCH_RADAR_GOOGLE_READ_ONLY", "").strip().casefold()
        return SHEETS_READ_ONLY_SCOPES if read_only in {"1", "true", "yes"} else SHEETS_SCOPES

    @staticmethod
    def _save_token(path: Path, token_json: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(token_json, encoding="utf-8")
        path.chmod(0o600)
