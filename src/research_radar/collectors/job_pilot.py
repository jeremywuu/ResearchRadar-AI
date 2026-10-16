"""Disabled Milestone 6.3A industry-source pilots for offline validation."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

from research_radar.collectors.base import (
    OfficialSourceAdapter,
    SourceCollectionResult,
    SourceDescriptor,
)
from research_radar.collectors.http import HttpClient, HttpRetrievalError
from research_radar.collectors.official import _failure_result, _html_text, _robots_allowed
from research_radar.models import (
    ExtractionStatus,
    RetrievalMethod,
    SourceHealth,
    SourceVerificationStatus,
)


class NeuralinkCareersPilotAdapter:
    """Verify Neuralink ownership, then read a bounded Greenhouse shortlist."""

    source = SourceDescriptor(
        source_id="neuralink_careers_discovery",
        organization="Neuralink",
        category="jobs",
        official_source_url="https://neuralink.com/careers/",
        retrieval_url="https://boards-api.greenhouse.io/v1/boards/neuralink/jobs?content=false",
        retrieval_method=RetrievalMethod.PUBLIC_API,
        verification_status=SourceVerificationStatus.VERIFIED_OFFICIAL,
    )
    _BOARD_HOST = "job-boards.greenhouse.io"
    _DETAIL_ROOT = "https://boards-api.greenhouse.io/v1/boards/neuralink/jobs/"
    _RELEVANT = re.compile(
        r"neuro|neural|bci|brain|signal processing|machine learning|research|intern",
        re.I,
    )
    _MAX_DETAILS = 5

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    def collect(self, *, observed_at: datetime) -> SourceCollectionResult:
        try:
            if not _robots_allowed(self.client, self.source.official_source_url):
                return _blocked(self.source, observed_at)
            careers = self.client.get(self.source.official_source_url, accept="text/html")
            _, links = _html_text(careers.text)
            if not any(urlsplit(href).netloc == self._BOARD_HOST for _, href in links):
                raise ValueError(
                    "official careers page does not prove Neuralink Greenhouse ownership"
                )
            listing = self.client.get(self.source.retrieval_url, accept="application/json")
            jobs = json.loads(listing.text).get("jobs")
            if not isinstance(jobs, list):
                raise ValueError("Greenhouse response has no jobs list")
            candidates = [
                job
                for job in jobs
                if isinstance(job, dict)
                and isinstance(job.get("title"), str)
                and self._RELEVANT.search(job["title"])
            ][: self._MAX_DETAILS]
            records: list[dict[str, Any]] = []
            statuses = [careers.status, listing.status]
            errors: list[str] = []
            for candidate in candidates:
                job_id = candidate.get("id")
                try:
                    detail = self.client.get(
                        f"{self._DETAIL_ROOT}{job_id}", accept="application/json"
                    )
                    statuses.append(detail.status)
                    records.append(self._extract_job(json.loads(detail.text)))
                except (HttpRetrievalError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    errors.append(f"job {job_id}: {exc}")
            return _result(
                self.source,
                observed_at,
                records,
                fetched=len(jobs),
                matched=len(candidates),
                statuses=statuses,
                errors=errors,
            )
        except (HttpRetrievalError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return _failure_result(self.source, observed_at, exc)

    def _extract_job(self, detail: dict[str, Any]) -> dict[str, Any]:
        job_id = detail.get("id")
        title = detail.get("title")
        url = detail.get("absolute_url")
        if not isinstance(job_id, int | str) or not isinstance(title, str):
            raise ValueError("Neuralink detail is missing id or title")
        if not isinstance(url, str) or urlsplit(url).netloc != self._BOARD_HOST:
            raise ValueError("Neuralink detail has an invalid canonical URL")
        text, _ = _html_text(str(detail.get("content") or ""))
        location = _greenhouse_location(detail)
        return _raw_job(
            title=title,
            organization="Neuralink",
            official_job_id=str(job_id),
            source_url=url,
            official_source_url=self.source.official_source_url,
            adapter_source_id=self.source.source_id,
            location=location,
            description=text,
            evidence=[f"Current Greenhouse index job ID: {job_id}", f"Title: {title}"],
            extraction_method="official_careers_plus_greenhouse_api",
        )


class PrecisionNeuroscienceCareersPilotAdapter:
    """Follow Precision's first-party Kula relationship and current organization index."""

    source = SourceDescriptor(
        source_id="precision_neuroscience_careers_discovery",
        organization="Precision Neuroscience",
        category="jobs",
        official_source_url="https://www.precisionneuro.io/careers",
        retrieval_url="https://careers.kula.ai/precision-neuroscience",
        retrieval_method=RetrievalMethod.OFFICIAL_HTML,
        verification_status=SourceVerificationStatus.VERIFIED_OFFICIAL,
    )
    _ATS_HOST = "careers.kula.ai"
    _RELEVANT = re.compile(r"neural|neuro|signal|dsp|machine learning|data|research", re.I)
    _MAX_DETAILS = 3

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    def collect(self, *, observed_at: datetime) -> SourceCollectionResult:
        try:
            if not _robots_allowed(self.client, self.source.official_source_url):
                return _blocked(self.source, observed_at)
            careers = self.client.get(self.source.official_source_url, accept="text/html")
            if "careers.kula.ai/precision-neuroscience" not in careers.text:
                raise ValueError("official careers page does not prove Precision Kula ownership")
            if not _robots_allowed(self.client, self.source.retrieval_url):
                return _blocked(self.source, observed_at)
            index = self.client.get(self.source.retrieval_url, accept="text/html")
            _, links = _html_text(index.text)
            jobs = _kula_links(self.source.retrieval_url, links)
            candidates = [job for job in jobs if self._RELEVANT.search(job[1])][: self._MAX_DETAILS]
            records: list[dict[str, Any]] = []
            statuses = [careers.status, index.status]
            errors: list[str] = []
            for url, title in candidates:
                try:
                    detail = self.client.get(url, accept="text/html")
                    statuses.append(detail.status)
                    records.append(self._extract_job(url, title, detail.text))
                except (HttpRetrievalError, ValueError) as exc:
                    errors.append(f"job {url}: {exc}")
            return _result(
                self.source,
                observed_at,
                records,
                fetched=len(jobs),
                matched=len(candidates),
                statuses=statuses,
                errors=errors,
            )
        except (HttpRetrievalError, ValueError) as exc:
            return _failure_result(self.source, observed_at, exc)

    def _extract_job(self, url: str, title: str, html: str) -> dict[str, Any]:
        text, _ = _html_text(html)
        if title.casefold() not in text.casefold():
            raise ValueError("Kula detail does not confirm the indexed title")
        job_id = _kula_job_id(url)
        location_match = re.search(
            r"(?:Chicago|Framingham|New York|Santa Clara)(?:[^.]{0,80})",
            text,
            re.I,
        )
        return _raw_job(
            title=title,
            organization="Precision Neuroscience",
            official_job_id=job_id,
            source_url=url,
            official_source_url=self.source.official_source_url,
            adapter_source_id=self.source.source_id,
            location=location_match.group(0).strip() if location_match else None,
            description=text,
            evidence=[f"Current Kula index job ID: {job_id}", f"Title: {title}"],
            extraction_method="official_careers_plus_kula_html",
        )


class SynchronCareersPilotAdapter:
    """Use Synchron's current first-party index and retain its cognition team as a profile."""

    source = SourceDescriptor(
        source_id="synchron_careers_discovery",
        organization="Synchron",
        category="jobs",
        official_source_url="https://synchron.com/careers",
        retrieval_url="https://synchron.com/careers",
        retrieval_method=RetrievalMethod.OFFICIAL_HTML,
        verification_status=SourceVerificationStatus.VERIFIED_OFFICIAL,
    )
    _RESEARCH_TITLE = re.compile(r"neural|neuro|signal|data scientist|research|cognition", re.I)

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    def collect(self, *, observed_at: datetime) -> SourceCollectionResult:
        try:
            if not _robots_allowed(self.client, self.source.retrieval_url):
                return _blocked(self.source, observed_at)
            response = self.client.get(self.source.retrieval_url, accept="text/html")
            text, links = _html_text(response.text)
            adp_jobs = [
                (href, label)
                for label, href in links
                if "workforcenow.adp.com" in urlsplit(href).netloc
            ]
            matches = [job for job in adp_jobs if self._RESEARCH_TITLE.search(job[1])]
            if matches:
                raise ValueError(
                    "research-titled Synchron roles require a separately reviewed ADP parser"
                )
            profile = {
                "profile_type": "RESEARCH_TEAM_PROFILE",
                "organization": "Synchron",
                "team": "New York cognition lab",
                "official_url": self.source.official_source_url,
                "current_opening_status": (
                    "CONFIRMED_NO_CURRENT_OPENINGS"
                    if re.search(r"no current openings here", text, re.I)
                    else "UNKNOWN"
                ),
                "actionable_opportunity": False,
                "research_topics": [
                    "Neural signals",
                    "Models of human thought",
                    "Closed-loop neurofeedback",
                    "Human-computer interaction",
                ],
            }
            return SourceCollectionResult(
                source=self.source,
                health=SourceHealth.SUCCESS_NO_MATCHES,
                extraction_status=ExtractionStatus.NO_MATCHES,
                retrieved_at=observed_at,
                informational_profiles=[profile],
                records_fetched=len(adp_jobs),
                records_matched=0,
                records_considered=0,
                http_statuses=[response.status],
                last_successful_retrieval_at=observed_at,
            )
        except (HttpRetrievalError, ValueError) as exc:
            return _failure_result(self.source, observed_at, exc)


def _result(
    source: SourceDescriptor,
    observed_at: datetime,
    records: list[dict[str, Any]],
    *,
    fetched: int,
    matched: int,
    statuses: list[int],
    errors: list[str],
) -> SourceCollectionResult:
    if records and errors:
        health, extraction = SourceHealth.PARTIAL, ExtractionStatus.PARTIAL
    elif records:
        health, extraction = SourceHealth.SUCCESS, ExtractionStatus.SUCCESS
    elif errors:
        health, extraction = SourceHealth.FAILED, ExtractionStatus.FAILED
    else:
        health, extraction = SourceHealth.SUCCESS_NO_MATCHES, ExtractionStatus.NO_MATCHES
    return SourceCollectionResult(
        source=source,
        health=health,
        extraction_status=extraction,
        retrieved_at=observed_at,
        records=records,
        records_fetched=fetched,
        records_matched=matched,
        records_considered=matched,
        errors=errors,
        http_statuses=statuses,
        last_successful_retrieval_at=observed_at,
    )


def _raw_job(
    *,
    title: str,
    organization: str,
    official_job_id: str,
    source_url: str,
    official_source_url: str,
    adapter_source_id: str,
    location: str | None,
    description: str,
    evidence: list[str],
    extraction_method: str,
) -> dict[str, Any]:
    education = _requirement(description, r"(?:Ph\.?D|doctorate)[^.]{0,120}")
    experience = _requirement(
        description,
        r"(?:at least\s+)?(?:\d+|two|three|four|five)\+?\s+years?[^.]{0,120}",
    )
    work_authorization = _requirement(
        description,
        r"(?:work authorization|authorized to work|sponsorship)[^.]{0,180}",
    )
    responsibilities = _sentences(
        description,
        ("neural", "brain", "bci", "signal", "decode", "research", "experiment"),
    )
    return {
        "fictional": False,
        "title": title,
        "organization": organization,
        "source_url": source_url,
        "official_source_url": official_source_url,
        "official_job_id": official_job_id,
        "location": location,
        "country": "United States" if location else None,
        "description": description,
        "research_areas": _research_areas(description),
        "research_orientation": "Applied research",
        "education_requirement": "PhD Required" if education else "Unknown",
        "education_requirement_detail": education,
        "experience_requirement_detail": experience,
        "work_authorization_detail": work_authorization,
        "role_evidence": responsibilities,
        "research_responsibility_evidence": responsibilities,
        "skills": [],
        "salary": {},
        "source_verification_status": "VERIFIED_OFFICIAL",
        "opportunity_status": "confirmed open",
        "listing_status": "CONFIRMED_LISTED",
        "source_type": "official_linked_ats",
        "source_evidence": evidence,
        "extraction_method": extraction_method,
        "adapter_source_id": adapter_source_id,
    }


def _blocked(source: SourceDescriptor, observed_at: datetime) -> SourceCollectionResult:
    return SourceCollectionResult(
        source=source,
        health=SourceHealth.BLOCKED,
        extraction_status=ExtractionStatus.FAILED,
        retrieved_at=observed_at,
        errors=["robots.txt does not permit retrieval"],
    )


def _greenhouse_location(detail: dict[str, Any]) -> str | None:
    location = detail.get("location")
    if isinstance(location, dict) and location.get("name"):
        return str(location["name"])
    return None


def _kula_links(base_url: str, links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for label, href in links:
        url = urljoin(base_url, href)
        if urlsplit(url).netloc != "careers.kula.ai" or not re.search(
            r"/precision-neuroscience/\d+-", urlsplit(url).path
        ):
            continue
        found.append((url, label.strip()))
    return list(dict.fromkeys(found))


def _kula_job_id(url: str) -> str:
    match = re.search(r"/precision-neuroscience/(\d+)-", urlsplit(url).path)
    if not match:
        raise ValueError("Kula detail URL lacks stable numeric job id")
    return match.group(1)


def _requirement(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.I)
    return match.group(0).strip() if match else None


def _sentences(text: str, markers: tuple[str, ...]) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if any(marker in sentence.casefold() for marker in markers)
    ][:8]


def _research_areas(text: str) -> list[str]:
    lowered = text.casefold()
    mapping = {
        "neural": "Neural data",
        "bci": "Brain-computer interfaces",
        "signal processing": "Neural signal processing",
        "machine learning": "Machine learning",
        "fMRI": "fMRI",
    }
    return [label for marker, label in mapping.items() if marker.casefold() in lowered]


def milestone_6_3a_pilot_adapters() -> dict[str, OfficialSourceAdapter]:
    """Return disabled Job Radar pilots for explicit offline injection only."""

    adapters = (
        NeuralinkCareersPilotAdapter(),
        PrecisionNeuroscienceCareersPilotAdapter(),
        SynchronCareersPilotAdapter(),
    )
    return {adapter.source.source_id: adapter for adapter in adapters}
