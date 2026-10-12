"""Initial deterministic collectors for verified official public sources."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from research_radar.collectors.base import SourceCollectionResult, SourceDescriptor
from research_radar.collectors.http import USER_AGENT, HttpClient, HttpRetrievalError
from research_radar.models import (
    ExtractionStatus,
    RetrievalMethod,
    SourceHealth,
    SourceVerificationStatus,
)


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._link_parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._link_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag == "a" and self._href:
            self.links.append((" ".join(self._link_parts).strip(), self._href))
            self._href = None
            self._link_parts = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text)
            if self._href:
                self._link_parts.append(text)

    @property
    def text(self) -> str:
        return " ".join(self.parts)


def _html_text(html: str) -> tuple[str, list[tuple[str, str]]]:
    parser = _TextParser()
    parser.feed(html)
    return parser.text, parser.links


def _robots_allowed(client: HttpClient, url: str) -> bool:
    parsed = urlsplit(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = client.get(robots_url, accept="text/plain")
    except HttpRetrievalError as exc:
        if exc.status == 404:
            return True
        raise
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    return parser.can_fetch(USER_AGENT, url)


def _failure_result(
    source: SourceDescriptor,
    observed_at: datetime,
    exc: Exception,
) -> SourceCollectionResult:
    status = exc.status if isinstance(exc, HttpRetrievalError) else None
    blocked = status in {401, 403}
    return SourceCollectionResult(
        source=source,
        health=SourceHealth.BLOCKED if blocked else SourceHealth.FAILED,
        extraction_status=ExtractionStatus.FAILED,
        retrieved_at=observed_at,
        errors=[str(exc)],
        http_statuses=[status] if status is not None else [],
    )


class AnthropicGreenhouseAdapter:
    """Read Anthropic roles through its official, publicly linked Greenhouse board."""

    source = SourceDescriptor(
        source_id="anthropic_greenhouse",
        organization="Anthropic",
        category="jobs",
        official_source_url="https://www.anthropic.com/careers/jobs",
        retrieval_url="https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=false",
        retrieval_method=RetrievalMethod.PUBLIC_API,
        verification_status=SourceVerificationStatus.VERIFIED_OFFICIAL,
    )
    _RELEVANT_TITLE = re.compile(
        r"research|scientist|machine learning|alignment|interpretability|research engineer",
        re.IGNORECASE,
    )
    _MAX_DETAILS = 25

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    def collect(self, *, observed_at: datetime) -> SourceCollectionResult:
        try:
            listing = self.client.get(self.source.retrieval_url, accept="application/json")
            payload = json.loads(listing.text)
            jobs = payload.get("jobs")
            if not isinstance(jobs, list):
                raise ValueError("Greenhouse response has no jobs list")
            candidates = [
                job
                for job in jobs
                if isinstance(job, dict)
                and isinstance(job.get("title"), str)
                and self._RELEVANT_TITLE.search(job["title"])
            ][: self._MAX_DETAILS]
            records: list[dict[str, Any]] = []
            errors: list[str] = []
            statuses = [listing.status]
            for candidate in candidates:
                job_id = candidate.get("id")
                if not isinstance(job_id, int | str):
                    errors.append("candidate missing official job id")
                    continue
                detail_url = "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs/" + str(
                    job_id
                )
                try:
                    response = self.client.get(detail_url, accept="application/json")
                    statuses.append(response.status)
                    detail = json.loads(response.text)
                    records.append(self._extract_job(detail, observed_at))
                except (HttpRetrievalError, json.JSONDecodeError, TypeError, ValueError) as exc:
                    errors.append(f"job {job_id}: {exc}")
            if not candidates:
                health = SourceHealth.SUCCESS_NO_MATCHES
                extraction = ExtractionStatus.NO_MATCHES
            elif errors and records:
                health = SourceHealth.PARTIAL
                extraction = ExtractionStatus.PARTIAL
            elif errors:
                health = SourceHealth.FAILED
                extraction = ExtractionStatus.FAILED
            else:
                health = SourceHealth.SUCCESS
                extraction = ExtractionStatus.SUCCESS
            return SourceCollectionResult(
                source=self.source,
                health=health,
                extraction_status=extraction,
                retrieved_at=observed_at,
                records=records,
                records_fetched=len(jobs),
                records_considered=len(candidates),
                errors=errors,
                http_statuses=statuses,
                last_successful_retrieval_at=observed_at,
            )
        except (HttpRetrievalError, json.JSONDecodeError, TypeError, ValueError) as exc:
            return _failure_result(self.source, observed_at, exc)

    def _extract_job(self, detail: dict[str, Any], observed_at: datetime) -> dict[str, Any]:
        job_id = detail.get("id")
        title = detail.get("title")
        absolute_url = detail.get("absolute_url")
        if not isinstance(job_id, int | str) or not isinstance(title, str):
            raise ValueError("job detail is missing id or title")
        if not isinstance(absolute_url, str):
            raise ValueError("job detail is missing canonical URL")
        location_data = detail.get("location")
        location = location_data.get("name") if isinstance(location_data, dict) else None
        content, _ = _html_text(str(detail.get("content") or ""))
        education = "Unknown"
        if re.search(r"Ph\.?D\.?[^.]{0,80}(required|must|have)", content, re.IGNORECASE):
            education = "PhD Required"
        elif re.search(r"Ph\.?D\.?[^.]{0,80}(preferred|preference)", content, re.IGNORECASE):
            education = "PhD Preferred"
        elif re.search(r"equivalent experience", content, re.IGNORECASE):
            education = "Equivalent Experience Accepted"
        areas = _research_areas(f"{title} {content}")
        orientation = "Research-oriented" if "research" in title.casefold() else "Applied research"
        evidence = [f"Official Greenhouse job ID: {job_id}", f"Title: {title}"]
        if location:
            evidence.append(f"Location: {location}")
        return {
            "fictional": False,
            "title": title,
            "organization": "Anthropic",
            "source_url": absolute_url,
            "official_source_url": self.source.official_source_url,
            "official_job_id": str(job_id),
            "location": location,
            "country": _country_from_location(location),
            "research_areas": areas,
            "research_orientation": orientation,
            "education_requirement": education,
            "working_language": None,
            "skills": [],
            "salary": {},
            "source_verification_status": "VERIFIED_OFFICIAL",
            "opportunity_status": "confirmed open",
            "source_type": "official_public_api",
            "source_evidence": evidence,
            "extraction_method": "greenhouse_job_board_api",
            "adapter_source_id": self.source.source_id,
        }


class UclGatsbyPhdAdapter:
    source = SourceDescriptor(
        source_id="ucl_gatsby_phd",
        organization="UCL Gatsby Computational Neuroscience Unit",
        category="phd",
        official_source_url=(
            "https://www.ucl.ac.uk/life-sciences/gatsby/study-and-work/gatsby-unit-phd-programme"
        ),
        retrieval_url=(
            "https://www.ucl.ac.uk/life-sciences/gatsby/study-and-work/gatsby-unit-phd-programme"
        ),
        retrieval_method=RetrievalMethod.OFFICIAL_HTML,
        verification_status=SourceVerificationStatus.VERIFIED_OFFICIAL,
    )

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    def collect(self, *, observed_at: datetime) -> SourceCollectionResult:
        try:
            if not _robots_allowed(self.client, self.source.retrieval_url):
                return SourceCollectionResult(
                    source=self.source,
                    health=SourceHealth.BLOCKED,
                    extraction_status=ExtractionStatus.FAILED,
                    retrieved_at=observed_at,
                    errors=["robots.txt does not permit retrieval"],
                )
            response = self.client.get(self.source.retrieval_url, accept="text/html")
            record = self._extract(response.text)
            return SourceCollectionResult(
                source=self.source,
                health=SourceHealth.SUCCESS,
                extraction_status=ExtractionStatus.SUCCESS,
                retrieved_at=observed_at,
                records=[record],
                records_fetched=1,
                records_considered=1,
                http_statuses=[response.status],
                last_successful_retrieval_at=observed_at,
            )
        except (HttpRetrievalError, ValueError) as exc:
            return _failure_result(self.source, observed_at, exc)

    def _extract(self, html: str) -> dict[str, Any]:
        text, links = _html_text(html)
        deadline_match = re.search(
            r"(?:deadline[^.]{0,100}?)?(\d{1,2})\s+(Nov(?:ember)?)\s+(20\d{2})",
            text,
            re.IGNORECASE,
        )
        cycle_match = re.search(r"PhD Programme\s+(20\d{2})", text, re.IGNORECASE)
        if not re.search(r"applications? (?:are )?(?:now )?open", text, re.IGNORECASE):
            raise ValueError("page does not explicitly confirm that applications are open")
        if not deadline_match:
            raise ValueError("confirmed application deadline not found")
        day, _, year = deadline_match.groups()
        deadline = date(int(year), 11, int(day))
        admission_link = next(
            (
                urljoin(self.source.official_source_url, href)
                for label, href in links
                if "portal" in label.casefold() or "apply" in label.casefold()
            ),
            self.source.official_source_url,
        )
        cycle = cycle_match.group(1) if cycle_match else None
        funding = None
        if re.search(
            r"fully funded|full funding|funding is available to all students",
            text,
            re.IGNORECASE,
        ):
            funding = "Fully funded (source stated)"
        evidence = ["Applications are open", f"Application deadline: {deadline.isoformat()}"]
        if cycle:
            evidence.append(f"Admission cycle: {cycle}")
        if funding:
            evidence.append("Full funding is explicitly stated")
        return {
            "fictional": False,
            "title": "Gatsby Unit PhD Programme",
            "organization": "University College London",
            "laboratory": "Gatsby Computational Neuroscience Unit",
            "source_url": self.source.official_source_url,
            "official_source_url": self.source.official_source_url,
            "admission_url": admission_link,
            "official_opportunity_id": f"ucl-gatsby-phd-{cycle}" if cycle else None,
            "target_cycle": cycle,
            "country": "United Kingdom",
            "location": "London",
            "research_areas": ["Machine learning", "Computational neuroscience"],
            "funding_status": funding,
            "deadline": deadline.isoformat(),
            "opportunity_status": "confirmed open",
            "opportunity_type": "centralized phd program admission",
            "source_verification_status": "VERIFIED_OFFICIAL",
            "source_type": "official_html",
            "source_evidence": evidence,
            "extraction_method": "deterministic_html_patterns",
            "adapter_source_id": self.source.source_id,
        }


class CosyneEventAdapter:
    source = SourceDescriptor(
        source_id="cosyne_official",
        organization="Computational and Systems Neuroscience (COSYNE)",
        category="events",
        official_source_url="https://www.cosyne.org/",
        retrieval_url="https://www.cosyne.org/",
        retrieval_method=RetrievalMethod.OFFICIAL_HTML,
        verification_status=SourceVerificationStatus.VERIFIED_OFFICIAL,
    )
    _PAGES = (
        "https://www.cosyne.org/",
        "https://www.cosyne.org/workshops-call",
        "https://www.cosyne.org/abstracts-submission",
    )

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    def collect(self, *, observed_at: datetime) -> SourceCollectionResult:
        pages: list[str] = []
        statuses: list[int] = []
        errors: list[str] = []
        robots_blocked = False
        for url in self._PAGES:
            try:
                if not _robots_allowed(self.client, url):
                    robots_blocked = True
                    errors.append(f"robots.txt does not permit {url}")
                    continue
                response = self.client.get(url, accept="text/html")
                pages.append(response.text)
                statuses.append(response.status)
            except HttpRetrievalError as exc:
                errors.append(str(exc))
        if not pages:
            return SourceCollectionResult(
                source=self.source,
                health=SourceHealth.BLOCKED if robots_blocked else SourceHealth.FAILED,
                extraction_status=ExtractionStatus.FAILED,
                retrieved_at=observed_at,
                errors=errors,
                http_statuses=statuses,
            )
        try:
            record = self._extract(pages)
        except ValueError as exc:
            return SourceCollectionResult(
                source=self.source,
                health=(
                    SourceHealth.PARTIAL if len(pages) < len(self._PAGES) else SourceHealth.FAILED
                ),
                extraction_status=ExtractionStatus.FAILED,
                retrieved_at=observed_at,
                records_fetched=1,
                errors=[*errors, str(exc)],
                http_statuses=statuses,
                last_successful_retrieval_at=observed_at,
            )
        return SourceCollectionResult(
            source=self.source,
            health=SourceHealth.PARTIAL if errors else SourceHealth.SUCCESS,
            extraction_status=ExtractionStatus.PARTIAL if errors else ExtractionStatus.SUCCESS,
            retrieved_at=observed_at,
            records=[record],
            records_fetched=1,
            records_considered=1,
            errors=errors,
            http_statuses=statuses,
            last_successful_retrieval_at=observed_at,
        )

    def _extract(self, pages: list[str]) -> dict[str, Any]:
        text = " ".join(_html_text(page)[0] for page in pages)
        main_dates = _main_meeting_dates(text)
        workshop_dates = _workshop_dates(text)
        abstract = _find_deadline(text, r"abstract[^.]{0,100}?(?:deadline|due)", "October", 10)
        workshop = _find_deadline(
            text,
            (
                r"workshop proposal(?: submission)?"
                r"(?: is now open\s*\.\s*Submission)?(?: deadline)?"
            ),
            "November",
            11,
        )
        registration = _find_deadline(
            text,
            (
                r"(?:presenter registration|presenting author[^.]{0,120}?"
                r"must register(?: for the meeting)? by)"
            ),
            "January",
            1,
        )
        if not main_dates or not workshop_dates:
            raise ValueError("COSYNE edition or main-meeting dates not found")
        start_day, end_day, date_year = main_dates
        workshop_start_day, workshop_end_day, workshop_year = workshop_dates
        if workshop_year != date_year:
            raise ValueError("COSYNE main meeting and workshop years do not match")
        year = date_year
        evidence = [
            f"COSYNE edition: {year}",
            f"Main meeting: {start_day}-{end_day} March {date_year}",
            f"Workshops: {workshop_start_day}-{workshop_end_day} March {workshop_year}",
        ]
        if abstract:
            evidence.append(f"Abstract deadline: {abstract.isoformat()}")
        if workshop:
            evidence.append(f"Workshop proposal deadline: {workshop.isoformat()}")
        if registration:
            evidence.append(
                f"Conditional presenter registration deadline: {registration.isoformat()}"
            )
        return {
            "fictional": False,
            "title": f"COSYNE {year}",
            "series_name": "COSYNE",
            "organization": "Computational and Systems Neuroscience (COSYNE)",
            "source_url": self.source.official_source_url,
            "official_source_url": self.source.official_source_url,
            "official_url": self.source.official_source_url,
            "edition_year": year,
            "country": "Canada",
            "location": "Montréal",
            "starts_on": date(date_year, 3, start_day).isoformat(),
            "ends_on": date(workshop_year, 3, workshop_end_day).isoformat(),
            "overall_starts_on": date(date_year, 3, start_day).isoformat(),
            "overall_ends_on": date(workshop_year, 3, workshop_end_day).isoformat(),
            "main_meeting_starts_on": date(date_year, 3, start_day).isoformat(),
            "main_meeting_ends_on": date(date_year, 3, end_day).isoformat(),
            "workshop_starts_on": date(workshop_year, 3, workshop_start_day).isoformat(),
            "workshop_ends_on": date(workshop_year, 3, workshop_end_day).isoformat(),
            "submission_deadline": abstract.isoformat() if abstract else None,
            "workshop_submission_deadline": workshop.isoformat() if workshop else None,
            "registration_deadline": None,
            "presenter_registration_deadline": registration.isoformat() if registration else None,
            "event_type": "academic conference",
            "research_areas": ["Computational neuroscience"],
            "opportunity_status": "confirmed upcoming",
            "source_verification_status": "VERIFIED_OFFICIAL",
            "source_type": "official_html",
            "source_evidence": evidence,
            "extraction_method": "deterministic_html_patterns",
            "adapter_source_id": self.source.source_id,
        }


def _main_meeting_dates(text: str) -> tuple[int, int, int] | None:
    day_first = re.search(
        r"Main Meeting\s+(\d{1,2})\s*[–-]\s*(\d{1,2})\s+March[,]?\s+(20\d{2})",
        text,
        re.IGNORECASE,
    )
    month_first = re.search(
        r"Main Meeting[^.]{0,30}?March\s+(\d{1,2})\s*[–-]\s*(\d{1,2})[,]?\s+(20\d{2})",
        text,
        re.IGNORECASE,
    )
    match = day_first or month_first
    return tuple(int(value) for value in match.groups()) if match else None


def _workshop_dates(text: str) -> tuple[int, int, int] | None:
    match = re.search(
        r"WORKSHOPS\s+(\d{1,2})\s*[–-]\s*(\d{1,2})\s+MARCH[,]?\s+(20\d{2})",
        text,
        re.IGNORECASE,
    )
    return tuple(int(value) for value in match.groups()) if match else None


def _find_deadline(text: str, prefix: str, month_name: str, month: int) -> date | None:
    day_first = re.search(
        rf"(?:{prefix})[^.]*?(\d{{1,2}})\s+{month_name}[,]?\s+(20\d{{2}})",
        text,
        re.IGNORECASE,
    )
    month_first = re.search(
        rf"(?:{prefix})[^.]*?{month_name}\s+(\d{{1,2}})[,]?\s+(20\d{{2}})",
        text,
        re.IGNORECASE,
    )
    match = day_first or month_first
    return date(int(match.group(2)), month, int(match.group(1))) if match else None


def _country_from_location(location: str | None) -> str | None:
    if not location:
        return None
    lowered = location.casefold()
    for marker, country in {
        "united states": "United States",
        "san francisco": "United States",
        "new york": "United States",
        "seattle": "United States",
        "london": "United Kingdom",
        "toronto": "Canada",
        "vancouver": "Canada",
        "sydney": "Australia",
        "melbourne": "Australia",
    }.items():
        if marker in lowered:
            return country
    return None


def _research_areas(text: str) -> list[str]:
    lowered = text.casefold()
    keywords = {
        "machine learning": "Machine learning",
        "artificial intelligence": "Artificial intelligence",
        "reinforcement learning": "Reinforcement learning",
        "human-ai": "Human-AI interaction",
        "neuroscience": "Computational neuroscience",
        "interpretability": "Artificial intelligence",
        "alignment": "Artificial intelligence",
    }
    return list(dict.fromkeys(label for keyword, label in keywords.items() if keyword in lowered))
