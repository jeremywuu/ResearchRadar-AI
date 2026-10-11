from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from research_radar.collectors.base import SourceDescriptor
from research_radar.collectors.http import HttpClient, HttpResponse, HttpRetrievalError
from research_radar.collectors.official import (
    AnthropicGreenhouseAdapter,
    CosyneEventAdapter,
    UclGatsbyPhdAdapter,
)
from research_radar.collectors.service import collect_live
from research_radar.models import (
    RetrievalMethod,
    SourceHealth,
    SourceVerificationStatus,
)

NOW = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "sources"


class RouteTransport:
    def __init__(self, routes: dict[str, HttpResponse | Exception]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        self.calls.append(url)
        assert headers["User-Agent"].startswith("ResearchRadarAI/")
        assert timeout > 0
        outcome = self.routes[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def response(url: str, body: str, status: int = 200) -> HttpResponse:
    return HttpResponse(url=url, status=status, body=body.encode(), headers={})


def greenhouse_transport(payload: dict | None = None) -> RouteTransport:
    payload = payload or json.loads((FIXTURES / "anthropic_jobs.json").read_text())
    listing_url = AnthropicGreenhouseAdapter.source.retrieval_url
    detail = payload["jobs"][0] if payload.get("jobs") else {}
    routes: dict[str, HttpResponse | Exception] = {
        listing_url: response(listing_url, json.dumps(payload))
    }
    if detail:
        detail_url = f"https://boards-api.greenhouse.io/v1/boards/anthropic/jobs/{detail['id']}"
        routes[detail_url] = response(detail_url, json.dumps(detail))
    return RouteTransport(routes)


def html_transport(page_url: str, body: str, *, error: Exception | None = None) -> RouteTransport:
    host = page_url.split("/", 3)[:3]
    robots = "/".join(host) + "/robots.txt"
    routes: dict[str, HttpResponse | Exception] = {
        robots: response(robots, "User-agent: *\nAllow: /\n"),
        page_url: error or response(page_url, body),
    }
    return RouteTransport(routes)


def test_greenhouse_success_preserves_official_identity_and_evidence() -> None:
    transport = greenhouse_transport()
    result = AnthropicGreenhouseAdapter(
        HttpClient(transport=transport, sleeper=lambda _: None)
    ).collect(observed_at=NOW)

    assert result.health is SourceHealth.SUCCESS
    assert result.records_fetched == 2
    assert len(result.records) == 1
    record = result.records[0]
    assert record["official_job_id"] == "12345"
    assert record["source_url"].startswith("https://job-boards.greenhouse.io/anthropic/")
    assert record["fictional"] is False
    assert record["source_evidence"]
    assert record["education_requirement"] == "PhD Preferred"


def test_greenhouse_empty_result_is_success_no_matches() -> None:
    transport = greenhouse_transport({"jobs": []})
    result = AnthropicGreenhouseAdapter(HttpClient(transport=transport)).collect(observed_at=NOW)
    assert result.health is SourceHealth.SUCCESS_NO_MATCHES
    assert result.records == []


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (HttpRetrievalError("forbidden", status=403), SourceHealth.BLOCKED),
        (HttpRetrievalError("missing", status=404), SourceHealth.FAILED),
    ],
)
def test_http_statuses_map_to_source_health(outcome: Exception, expected: SourceHealth) -> None:
    url = AnthropicGreenhouseAdapter.source.retrieval_url
    adapter = AnthropicGreenhouseAdapter(
        HttpClient(transport=RouteTransport({url: outcome}), max_attempts=1)
    )
    assert adapter.collect(observed_at=NOW).health is expected


def test_malformed_api_response_is_parser_failure() -> None:
    url = AnthropicGreenhouseAdapter.source.retrieval_url
    transport = RouteTransport({url: response(url, "not-json")})
    result = AnthropicGreenhouseAdapter(HttpClient(transport=transport)).collect(observed_at=NOW)
    assert result.health is SourceHealth.FAILED
    assert result.errors


def test_http_client_retries_rate_limit_and_timeout() -> None:
    calls = 0

    def flaky(url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HttpRetrievalError("rate limited", status=429)
        if calls == 2:
            raise HttpRetrievalError("timeout")
        return response(url, "{}")

    client = HttpClient(transport=flaky, sleeper=lambda _: None)
    assert client.get("https://example.org/data", accept="application/json").status == 200
    assert calls == 3


def test_ucl_html_extracts_only_explicit_cycle_deadline_and_funding() -> None:
    html = (FIXTURES / "ucl_gatsby.html").read_text()
    transport = html_transport(UclGatsbyPhdAdapter.source.retrieval_url, html)
    result = UclGatsbyPhdAdapter(HttpClient(transport=transport)).collect(observed_at=NOW)

    assert result.health is SourceHealth.SUCCESS
    record = result.records[0]
    assert record["target_cycle"] == "2027"
    assert record["deadline"] == "2026-11-09"
    assert record["funding_status"] == "Fully funded (source stated)"
    assert record.get("supervisor") is None


def test_ucl_403_is_blocked_and_does_not_fabricate_record() -> None:
    url = UclGatsbyPhdAdapter.source.retrieval_url
    transport = html_transport(url, "", error=HttpRetrievalError("challenge", status=403))
    result = UclGatsbyPhdAdapter(HttpClient(transport=transport, max_attempts=1)).collect(
        observed_at=NOW
    )
    assert result.health is SourceHealth.BLOCKED
    assert result.records == []


def test_html_robots_network_failure_is_failed_not_access_blocked() -> None:
    robots = "https://www.ucl.ac.uk/robots.txt"
    adapter = UclGatsbyPhdAdapter(
        HttpClient(
            transport=RouteTransport({robots: HttpRetrievalError("timeout")}),
            max_attempts=1,
        )
    )

    result = adapter.collect(observed_at=NOW)

    assert result.health is SourceHealth.FAILED
    assert result.records == []


def test_ucl_parser_rejects_historical_page_without_open_statement() -> None:
    html = "<p>Gatsby Unit PhD Programme 2027. Deadline 9 November 2026.</p>"
    transport = html_transport(UclGatsbyPhdAdapter.source.retrieval_url, html)
    result = UclGatsbyPhdAdapter(HttpClient(transport=transport)).collect(observed_at=NOW)
    assert result.health is SourceHealth.FAILED
    assert result.records == []


def test_cosyne_preserves_distinct_deadlines_and_edition() -> None:
    html = (FIXTURES / "cosyne.html").read_text()
    routes: dict[str, HttpResponse | Exception] = {
        "https://www.cosyne.org/robots.txt": response(
            "https://www.cosyne.org/robots.txt", "User-agent: *\nAllow: /\n"
        )
    }
    for url in CosyneEventAdapter._PAGES:
        routes[url] = response(url, html)
    result = CosyneEventAdapter(HttpClient(transport=RouteTransport(routes))).collect(
        observed_at=NOW
    )

    assert result.health is SourceHealth.SUCCESS
    record = result.records[0]
    assert record["edition_year"] == 2027
    assert record["submission_deadline"] == "2026-10-18"
    assert record["workshop_submission_deadline"] == "2026-11-01"
    assert record["registration_deadline"] is None
    assert record["presenter_registration_deadline"] == "2027-01-31"


def test_source_descriptor_rejects_invalid_urls() -> None:
    with pytest.raises(ValueError, match="absolute HTTP"):
        SourceDescriptor(
            source_id="bad",
            organization="Bad",
            category="jobs",
            official_source_url="not-a-url",
            retrieval_url="https://example.org/jobs",
            retrieval_method=RetrievalMethod.PUBLIC_API,
            verification_status=SourceVerificationStatus.UNVERIFIED,
        )


def test_live_orchestration_isolates_category_failure_and_writes_structured_output(
    tmp_path: Path,
) -> None:
    jobs_transport = greenhouse_transport()
    html = (FIXTURES / "cosyne.html").read_text()
    cosyne_routes: dict[str, HttpResponse | Exception] = {
        "https://www.cosyne.org/robots.txt": response(
            "https://www.cosyne.org/robots.txt", "User-agent: *\nAllow: /\n"
        )
    }
    for url in CosyneEventAdapter._PAGES:
        cosyne_routes[url] = response(url, html)
    ucl_url = UclGatsbyPhdAdapter.source.retrieval_url
    adapters = {
        "anthropic_greenhouse": AnthropicGreenhouseAdapter(HttpClient(transport=jobs_transport)),
        "ucl_gatsby_phd": UclGatsbyPhdAdapter(
            HttpClient(
                transport=html_transport(
                    ucl_url, "", error=HttpRetrievalError("challenge", status=403)
                ),
                max_attempts=1,
            )
        ),
        "cosyne_official": CosyneEventAdapter(HttpClient(transport=RouteTransport(cosyne_routes))),
    }

    result = collect_live(
        ("jobs", "phd", "events"),
        project_root=ROOT,
        output_dir=tmp_path,
        observed_at=NOW,
        reference_date=date(2026, 10, 11),
        adapters=adapters,
    )

    assert result.execution.pipelines["jobs"].records_accepted == 1
    assert result.execution.pipelines["events"].records_accepted == 1
    assert result.sources["ucl_gatsby_phd"].health is SourceHealth.BLOCKED
    assert (tmp_path / "jobs.json").exists()
    assert (tmp_path / "events.json").exists()
    metadata = json.loads(result.metadata_path.read_text())
    assert metadata["sources"]["anthropic_greenhouse"]["source"]["verification_status"] == (
        "VERIFIED_OFFICIAL"
    )
