"""Reviewed Milestone 6 research-source adapters.

Paradromics and RLDM can be added to ``default_adapters`` only through its explicit feature flag.
CMU Neural Computation remains available only through preview or test configuration.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

from research_radar.collectors.base import SourceCollectionResult, SourceDescriptor
from research_radar.collectors.http import HttpClient, HttpRetrievalError
from research_radar.collectors.official import (
    _failure_result,
    _html_text,
    _research_areas,
    _robots_allowed,
)
from research_radar.models import (
    ExtractionStatus,
    RetrievalMethod,
    SourceHealth,
    SourceVerificationStatus,
)


class _RoleNotRelevant(ValueError):
    """A successfully retrieved role lacks the required domain evidence."""


class CmuNeuralComputationProgramAdapter:
    """Retain CMU PNC as a programme profile until a dated cycle is stated."""

    source = SourceDescriptor(
        source_id="cmu_neural_computation_profile",
        organization="Carnegie Mellon University",
        category="phd",
        official_source_url=(
            "https://www.cmu.edu/ni/academics/grad/programs/phd-neural-computation"
        ),
        retrieval_url=("https://www.cmu.edu/ni/academics/grad/programs/phd-neural-computation"),
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
            profile = self._extract_profile(response.text)
        except (HttpRetrievalError, ValueError) as exc:
            return _failure_result(self.source, observed_at, exc)
        return SourceCollectionResult(
            source=self.source,
            health=SourceHealth.SUCCESS_NO_MATCHES,
            extraction_status=ExtractionStatus.NO_MATCHES,
            retrieved_at=observed_at,
            informational_profiles=[profile],
            records_fetched=1,
            records_matched=1,
            records_considered=1,
            http_statuses=[response.status],
            last_successful_retrieval_at=observed_at,
        )

    def _extract_profile(self, html: str) -> dict[str, Any]:
        text, links = _html_text(html)
        if not re.search(r"Ph\.D\. (?:Program|in) Neural Computation", text, re.I):
            raise ValueError("CMU Neural Computation programme identity not found")
        application_url = next(
            (
                urljoin(self.source.official_source_url, href)
                for label, href in links
                if "apply" in label.casefold()
            ),
            None,
        )
        methods = [
            label
            for keyword, label in {
                "computational neuroscience": "Computational neuroscience",
                "machine learning": "Machine learning",
                "statistics": "Statistics",
                "experimental neuroscience": "Experimental neuroscience",
                "neural data": "Neural data analysis",
                "computational modeling": "Computational modeling",
            }.items()
            if keyword in text.casefold()
        ]
        return {
            "profile_type": "PHD_PROGRAM_PROFILE",
            "actionable_opportunity": False,
            "institution": "Carnegie Mellon University",
            "programme": "Ph.D. Program in Neural Computation",
            "laboratory": None,
            "potential_supervisor": None,
            "research_topics": [
                "Neural computation",
                "Computational neuroscience",
                "Cognition",
            ],
            "methods": methods,
            "admission_cycle": None,
            "confirmed_recruitment_status": "UNKNOWN",
            "official_deadline": None,
            "general_deadline_information": (
                "December 1 (programme page does not identify an admission cycle)"
                if re.search(r"Application Deadline\s+December 1", text, re.I)
                else None
            ),
            "funding_information": None,
            "official_url": self.source.official_source_url,
            "application_url": application_url,
            "verification_status": "VERIFIED_OFFICIAL",
            "source_evidence": [
                "Official CMU page identifies the Ph.D. Program in Neural Computation",
                "The monitored page does not announce Fall 2028 admission",
            ],
        }


class ParadromicsCareersAdapter:
    """Follow Paradromics' first-party careers links to its public JazzHR pages."""

    source = SourceDescriptor(
        source_id="paradromics_careers_pilot",
        organization="Paradromics",
        category="jobs",
        official_source_url="https://paradromics.com/careers/",
        retrieval_url="https://paradromics.com/careers/",
        retrieval_method=RetrievalMethod.OFFICIAL_HTML,
        verification_status=SourceVerificationStatus.VERIFIED_OFFICIAL,
    )
    _ATS_HOST = "paradromicsinc.applytojob.com"
    _CANDIDATE_TITLE = re.compile(
        r"neural|neuro|brain|signal|data|machine learning|software|clinical|research",
        re.I,
    )
    _MAX_DETAILS = 5

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
            careers = self.client.get(self.source.retrieval_url, accept="text/html")
            _, links = _html_text(careers.text)
            jobs = self._official_job_links(links)
            candidates = [job for job in jobs if self._CANDIDATE_TITLE.search(job[1])][
                : self._MAX_DETAILS
            ]
            if candidates and not _robots_allowed(self.client, candidates[0][0]):
                return SourceCollectionResult(
                    source=self.source,
                    health=SourceHealth.BLOCKED,
                    extraction_status=ExtractionStatus.FAILED,
                    retrieved_at=observed_at,
                    records_fetched=len(jobs),
                    records_matched=len(candidates),
                    errors=["JazzHR robots.txt does not permit retrieval"],
                    http_statuses=[careers.status],
                )
            records: list[dict[str, Any]] = []
            excluded_profiles: list[dict[str, Any]] = []
            errors: list[str] = []
            statuses = [careers.status]
            for url, title, location in candidates:
                try:
                    detail = self.client.get(url, accept="text/html")
                    statuses.append(detail.status)
                    records.append(self._extract_job(url, title, location, detail.text))
                except _RoleNotRelevant as exc:
                    excluded_profiles.append(
                        {
                            "profile_type": "LOW_DOMAIN_EVIDENCE_ROLE",
                            "title": title,
                            "official_url": url,
                            "reason": str(exc),
                        }
                    )
                except (HttpRetrievalError, ValueError) as exc:
                    errors.append(f"{url}: {exc}")
        except (HttpRetrievalError, ValueError) as exc:
            return _failure_result(self.source, observed_at, exc)

        if errors and records:
            health, extraction = SourceHealth.PARTIAL, ExtractionStatus.PARTIAL
        elif errors:
            health, extraction = SourceHealth.FAILED, ExtractionStatus.FAILED
        elif records:
            health, extraction = SourceHealth.SUCCESS, ExtractionStatus.SUCCESS
        else:
            health, extraction = SourceHealth.SUCCESS_NO_MATCHES, ExtractionStatus.NO_MATCHES
        return SourceCollectionResult(
            source=self.source,
            health=health,
            extraction_status=extraction,
            retrieved_at=observed_at,
            records=records,
            informational_profiles=excluded_profiles,
            records_fetched=len(jobs),
            records_matched=len(candidates),
            records_considered=len(candidates),
            errors=errors,
            http_statuses=statuses,
            last_successful_retrieval_at=observed_at,
        )

    def _official_job_links(
        self, links: list[tuple[str, str]]
    ) -> list[tuple[str, str, str | None]]:
        jobs: dict[str, tuple[str, str | None]] = {}
        for label, href in links:
            absolute = urljoin(self.source.official_source_url, href).split("?", 1)[0]
            parsed = urlsplit(absolute)
            if parsed.netloc != self._ATS_HOST or "/apply/" not in parsed.path:
                continue
            cleaned = " ".join(label.split())
            match = re.match(r"(.+?)\s+(Austin|Oakland),\s*(TX|CA)\s+Apply$", cleaned, re.I)
            if match:
                title = match.group(1).strip()
                location = f"{match.group(2).title()}, {match.group(3).upper()}"
            else:
                title = re.sub(r"\s+Apply$", "", cleaned, flags=re.I).strip()
                location = None
            if title:
                jobs.setdefault(absolute, (title, location))
        return [(url, title, location) for url, (title, location) in jobs.items()]

    def _extract_job(self, url: str, title: str, location: str | None, html: str) -> dict[str, Any]:
        text, _ = _html_text(html)
        if title.casefold() not in text.casefold():
            raise ValueError("JazzHR detail page does not confirm the listed title")
        domain_markers = (
            "brain-computer interface",
            "brain machine",
            "bci",
            "neural data",
            "neural signal",
            "neuroscience",
            "decoding algorithm",
        )
        role_evidence = _role_evidence(text, domain_markers)
        if not role_evidence:
            raise _RoleNotRelevant("detail page lacks role-specific BCI or neural-data evidence")

        research_areas = _research_areas(text)
        lowered = text.casefold()
        if ("brain machine" in lowered or "bci" in lowered) and (
            "Brain-computer interfaces" not in research_areas
        ):
            research_areas.append("Brain-computer interfaces")
        if ("neural data" in lowered or "decoding algorithm" in lowered) and (
            "Neural encoding and decoding" not in research_areas
        ):
            research_areas.append("Neural encoding and decoding")
        if "signal processing" in lowered and "Neural data science" not in research_areas:
            research_areas.append("Neural data science")

        salary_match = re.search(r"Salary:\s*\$([\d,]+)\s*[-–]\s*\$?([\d,]+)\s+base", text, re.I)
        salary: dict[str, Any] = {}
        if salary_match:
            salary = {
                "base_min": salary_match.group(1).replace(",", ""),
                "base_max": salary_match.group(2).replace(",", ""),
                "currency": "USD",
                "period": "annual",
                "original_text": salary_match.group(0),
                "source_url": url,
            }

        education_detail = None
        education_match = re.search(
            r"(?:Bachelor(?:'s|’s)|Master(?:'s|’s)|Ph\.?D\.?) degree[^.;]*", text, re.I
        )
        if education_match:
            education_detail = education_match.group(0).strip()
        skills = [
            label
            for keyword, label in {
                "python": "Python",
                "rust": "Rust",
                "c++": "C++",
                "machine learning": "Machine learning",
                "signal processing": "Neural data analysis",
                "time series": "Time-series analysis",
            }.items()
            if keyword in lowered
        ]
        job_id = urlsplit(url).path.split("/apply/", 1)[1].split("/", 1)[0]
        return {
            "fictional": False,
            "title": title,
            "organization": "Paradromics",
            "source_url": url,
            "official_source_url": self.source.official_source_url,
            "official_job_id": job_id,
            "location": location,
            "country": "United States" if location else None,
            "region": "United States" if location else None,
            "research_areas": research_areas,
            "research_orientation": "Applied research",
            "education_requirement": "Other" if education_detail else "Unknown",
            "education_requirement_detail": education_detail,
            "working_language": None,
            "skills": skills,
            "salary": salary,
            "source_verification_status": "VERIFIED_OFFICIAL",
            "opportunity_status": "confirmed open",
            "source_type": "official_html_linked_ats",
            "source_evidence": [
                "Paradromics official careers page links to this JazzHR posting",
                f"Role-specific source text connects {title} to BCI or neural-data work",
            ],
            "role_evidence": role_evidence,
            "research_responsibility_evidence": _sentences_with(
                text,
                (
                    "research",
                    "experiment",
                    "study",
                    "model",
                    "decoding",
                    "neural data",
                    "signal processing",
                ),
            ),
            "clinical_implementation_evidence": _sentences_with(
                text,
                ("clinical", "patient", "surgery", "hospital", "field support", "training"),
            ),
            "experience_requirement_detail": _experience_requirement(text),
            "work_authorization_detail": _work_authorization_evidence(text),
            "extraction_method": "deterministic_html_patterns",
            "adapter_source_id": self.source.source_id,
        }


class Rldm2027EventAdapter:
    """Collect the official RLDM 2027 edition and its abstract deadline."""

    source = SourceDescriptor(
        source_id="rldm_2027_official_pilot",
        organization="RLDM",
        category="events",
        official_source_url="https://rldm.org/",
        retrieval_url="https://rldm.org/",
        retrieval_method=RetrievalMethod.OFFICIAL_HTML,
        verification_status=SourceVerificationStatus.VERIFIED_OFFICIAL,
    )
    _CALL_URL = "https://rldm.org/call-for-abstracts-2027/"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    def collect(self, *, observed_at: datetime) -> SourceCollectionResult:
        try:
            for url in (self.source.retrieval_url, self._CALL_URL):
                if not _robots_allowed(self.client, url):
                    return SourceCollectionResult(
                        source=self.source,
                        health=SourceHealth.BLOCKED,
                        extraction_status=ExtractionStatus.FAILED,
                        retrieved_at=observed_at,
                        errors=[f"robots.txt does not permit {url}"],
                    )
            home = self.client.get(self.source.retrieval_url, accept="text/html")
            call = self.client.get(self._CALL_URL, accept="text/html")
            record = self._extract(home.text, call.text)
        except (HttpRetrievalError, ValueError) as exc:
            return _failure_result(self.source, observed_at, exc)
        return SourceCollectionResult(
            source=self.source,
            health=SourceHealth.SUCCESS,
            extraction_status=ExtractionStatus.SUCCESS,
            retrieved_at=observed_at,
            records=[record],
            records_fetched=1,
            records_matched=1,
            records_considered=1,
            http_statuses=[home.status, call.status],
            last_successful_retrieval_at=observed_at,
        )

    def _extract(self, home_html: str, call_html: str) -> dict[str, Any]:
        home_text, _ = _html_text(home_html)
        call_text, _ = _html_text(call_html)
        combined = f"{home_text} {call_text}"
        if not re.search(
            r"Multi-disciplinary Conference on Reinforcement Learning and Decision Making",
            combined,
            re.I,
        ):
            raise ValueError("RLDM conference identity not found")
        if not re.search(r"July\s+6\s*[-–]\s*9,\s*2027", combined, re.I):
            raise ValueError("RLDM 2027 event dates not found")
        if not re.search(r"Paris,\s*France", home_text, re.I):
            raise ValueError("RLDM 2027 Paris location not found")
        deadline = None
        if re.search(
            r"Submissions due.{0,40}(?:20\s+January|January\s+20),?\s+2027",
            call_text,
            re.I,
        ):
            deadline = date(2027, 1, 20)
        return {
            "fictional": False,
            "title": "Reinforcement Learning and Decision Making 2027",
            "organization": "RLDM",
            "source_url": self._CALL_URL,
            "official_source_url": self.source.official_source_url,
            "event_url": self.source.official_source_url,
            "series_name": "RLDM",
            "edition_year": 2027,
            "location": "Paris",
            "country": "France",
            "region": "Europe",
            "starts_on": "2027-07-06",
            "ends_on": "2027-07-09",
            "submission_deadline": deadline.isoformat() if deadline else None,
            "submission_deadline_timezone": "AoE" if deadline else None,
            "registration_deadline": None,
            "event_type": "academic conference",
            "research_areas": [
                "Decision neuroscience",
                "Reinforcement learning models of cognition",
                "Computational models of human behavior",
            ],
            "opportunity_status": "confirmed upcoming",
            "source_verification_status": "VERIFIED_OFFICIAL",
            "source_type": "official_html",
            "source_evidence": [
                "Official RLDM page states July 6-9, 2027 in Paris, France",
                "Official call states abstract submissions due January 20, 2027 AoE",
            ],
            "extraction_method": "deterministic_html_patterns",
            "adapter_source_id": self.source.source_id,
        }


def milestone_6_pilot_adapters() -> dict[str, object]:
    """Return reviewed pilots without adding them to production collection."""

    adapters = [
        CmuNeuralComputationProgramAdapter(),
        ParadromicsCareersAdapter(),
        Rldm2027EventAdapter(),
    ]
    return {adapter.source.source_id: adapter for adapter in adapters}


def _sentences(text: str) -> list[str]:
    return [
        " ".join(sentence.split())
        for sentence in re.split(r"(?<=[.!?])\s+|\s*[•·]\s*", text)
        if sentence.strip()
    ]


def _sentences_with(text: str, markers: tuple[str, ...], *, limit: int = 4) -> list[str]:
    matching = [
        sentence
        for sentence in _sentences(text)
        if any(marker in sentence.casefold() for marker in markers)
    ]
    return matching[:limit]


def _role_evidence(text: str, domain_markers: tuple[str, ...]) -> list[str]:
    responsibility_markers = (
        "analy",
        "build",
        "collect",
        "decode",
        "deploy",
        "design",
        "develop",
        "evaluate",
        "implement",
        "process",
        "record",
        "research",
        "support",
        "train",
        "work with",
    )
    return [
        sentence
        for sentence in _sentences_with(text, domain_markers, limit=8)
        if any(marker in sentence.casefold() for marker in responsibility_markers)
    ][:4]


def _first_sentence_matching(text: str, pattern: str) -> str | None:
    expression = re.compile(pattern, re.I)
    return next((sentence for sentence in _sentences(text) if expression.search(sentence)), None)


def _experience_requirement(text: str) -> str | None:
    match = re.search(
        r"\b\d+\+?\s+years?\s+of\s+(?:professional\s+)?experience(?:\s+relevant\s+to\s+this\s+role)?",
        text,
        re.I,
    )
    return " ".join(match.group(0).split()) if match else None


def _work_authorization_evidence(text: str) -> str | None:
    match = re.search(
        r"Are you legally authorized to work in the United States\??",
        text,
        re.I,
    )
    if match:
        return "Are you legally authorized to work in the United States?"
    match = re.search(r"[^.]{0,100}(?:visa sponsorship|work authorization)[^.]{0,100}", text, re.I)
    return " ".join(match.group(0).split()) if match else None
