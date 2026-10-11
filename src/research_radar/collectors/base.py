"""Contracts shared by read-only official-source collectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from urllib.parse import urlparse

from research_radar.models import (
    ExtractionStatus,
    RetrievalMethod,
    SourceHealth,
    SourceVerificationStatus,
)


@dataclass(frozen=True, kw_only=True)
class SourceDescriptor:
    source_id: str
    organization: str
    category: str
    official_source_url: str
    retrieval_url: str
    retrieval_method: RetrievalMethod
    verification_status: SourceVerificationStatus

    def __post_init__(self) -> None:
        for name, value in {
            "official_source_url": self.official_source_url,
            "retrieval_url": self.retrieval_url,
        }.items():
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"{name} must be an absolute HTTP(S) URL")


@dataclass(kw_only=True)
class SourceCollectionResult:
    source: SourceDescriptor
    health: SourceHealth
    extraction_status: ExtractionStatus
    retrieved_at: datetime
    records: list[dict[str, Any]] = field(default_factory=list)
    records_fetched: int = 0
    errors: list[str] = field(default_factory=list)
    http_statuses: list[int] = field(default_factory=list)
    last_successful_retrieval_at: datetime | None = None


class OfficialSourceAdapter(Protocol):
    source: SourceDescriptor

    def collect(self, *, observed_at: datetime) -> SourceCollectionResult:
        """Retrieve and extract source-stated records without classifying availability by guess."""
