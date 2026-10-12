"""Small bounded HTTP client for public read-only source retrieval."""

from __future__ import annotations

import os
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

USER_AGENT = "ResearchRadarAI/0.1 (+personal academic opportunity monitor; read-only)"


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status: int
    body: bytes
    headers: dict[str, str]

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class HttpRetrievalError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


Transport = Callable[[str, dict[str, str], float], HttpResponse]


def _verified_ssl_context() -> ssl.SSLContext:
    """Build a verified context from an explicit override or the packaged Mozilla CA set."""

    ca_file = os.environ.get("SSL_CERT_FILE") or certifi.where()
    return ssl.create_default_context(cafile=ca_file)


def _default_transport(url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
    request = Request(url, headers=headers, method="GET")
    try:
        context = _verified_ssl_context()
        with urlopen(  # noqa: S310 - validated official URLs
            request,
            timeout=timeout,
            context=context,
        ) as response:
            raw_headers: Message = response.headers
            return HttpResponse(
                url=response.geturl(),
                status=response.status,
                body=response.read(),
                headers={key.casefold(): value for key, value in raw_headers.items()},
            )
    except HTTPError as exc:
        raise HttpRetrievalError(f"HTTP {exc.code} for {url}", status=exc.code) from exc
    except (URLError, TimeoutError, OSError) as exc:
        reason = exc.reason if isinstance(exc, URLError) else exc
        raise HttpRetrievalError(f"network error for {url}: {reason}") from exc


class HttpClient:
    """GET-only client with bounded retry for transient failures."""

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        timeout_seconds: float = 15.0,
        max_attempts: int = 3,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport or _default_transport
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self._sleeper = sleeper

    def get(self, url: str, *, accept: str) -> HttpResponse:
        headers = {"User-Agent": USER_AGENT, "Accept": accept}
        last_error: HttpRetrievalError | None = None
        for attempt in range(self.max_attempts):
            try:
                return self._transport(url, headers, self.timeout_seconds)
            except HttpRetrievalError as exc:
                last_error = exc
                transient = exc.status in {408, 429, 500, 502, 503, 504} or exc.status is None
                if not transient or attempt == self.max_attempts - 1:
                    raise
                self._sleeper(float(2**attempt))
        raise last_error or HttpRetrievalError(f"retrieval failed for {url}")
