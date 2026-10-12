from __future__ import annotations

import json
import ssl
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from research_radar.collectors import http as http_module
from research_radar.collectors.base import SourceDescriptor
from research_radar.collectors.http import HttpClient, HttpResponse, HttpRetrievalError
from research_radar.collectors.official import (
    AnthropicGreenhouseAdapter,
    Ccn2027EventAdapter,
    CmuCognitiveNeuroscienceProgramAdapter,
    CosyneEventAdapter,
    NeuroelectricsCareersAdapter,
    UclGatsbyPhdAdapter,
)
from research_radar.collectors.service import collect_live
from research_radar.models import (
    DomainFitClassification,
    RetrievalMethod,
    SourceHealth,
    SourceVerificationStatus,
)
from research_radar.pipelines import run_events_pipeline

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
    assert result.records_considered == 1
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


def test_greenhouse_prioritizes_tracked_jobs_and_reserves_new_discovery_capacity() -> None:
    listing_url = AnthropicGreenhouseAdapter.source.retrieval_url
    jobs = [
        {
            "id": job_id,
            "title": f"Research Engineer {job_id}",
            "absolute_url": f"https://job-boards.greenhouse.io/anthropic/jobs/{job_id}",
            "location": {"name": "San Francisco, CA"},
            "content": "",
        }
        for job_id in range(1, 31)
    ]
    routes = {listing_url: response(listing_url, json.dumps({"jobs": jobs}))}
    for job in jobs:
        detail_url = f"https://boards-api.greenhouse.io/v1/boards/anthropic/jobs/{job['id']}"
        routes[detail_url] = response(detail_url, json.dumps(job))
    transport = RouteTransport(routes)
    adapter = AnthropicGreenhouseAdapter(
        HttpClient(transport=transport),
        tracked_job_ids={str(job_id) for job_id in range(1, 26)},
    )

    result = adapter.collect(observed_at=NOW)

    observed_ids = {record["official_job_id"] for record in result.records}
    assert result.records_fetched == 30
    assert result.records_matched == 30
    assert result.records_considered == 25
    assert {str(job_id) for job_id in range(1, 21)} <= observed_ids
    assert {str(job_id) for job_id in range(26, 31)} <= observed_ids
    assert not ({str(job_id) for job_id in range(21, 26)} & observed_ids)


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


def test_default_http_transport_uses_verified_hostname_checking_context(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeHeaders:
        def items(self):
            return []

    class FakeResponse:
        status = 200
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def geturl(self) -> str:
            return "https://example.org/robots.txt"

        def read(self) -> bytes:
            return b"ok"

    def fake_urlopen(request, *, timeout, context):
        captured.update(timeout=timeout, context=context, request=request)
        return FakeResponse()

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.setattr(http_module, "urlopen", fake_urlopen)

    response_value = HttpClient(max_attempts=1).get(
        "https://example.org/robots.txt", accept="text/plain"
    )

    context = captured["context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert len(context.get_ca_certs()) > 0
    assert captured["timeout"] == 15.0
    assert response_value.status == 200


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
    assert record["starts_on"] == "2027-03-11"
    assert record["ends_on"] == "2027-03-16"
    assert record["main_meeting_starts_on"] == "2027-03-11"
    assert record["main_meeting_ends_on"] == "2027-03-14"
    assert record["workshop_starts_on"] == "2027-03-15"
    assert record["workshop_ends_on"] == "2027-03-16"
    assert record["submission_deadline"] == "2026-10-18"
    assert record["workshop_submission_deadline"] == "2026-11-01"
    assert record["registration_deadline"] is None
    assert record["presenter_registration_deadline"] == "2027-01-31"


def test_ccn_2027_extracts_edition_and_preserves_unknown_deadline() -> None:
    html = """
    <h1>10th Annual Conference Cognitive Computational Neuroscience</h1>
    <p>July 26-29, 2027</p><p>Edinburgh, UK</p>
    <p>Developing cognitive- or neural-level models of perception and cognition.</p>
    """
    transport = html_transport(Ccn2027EventAdapter.source.retrieval_url, html)

    result = Ccn2027EventAdapter(HttpClient(transport=transport)).collect(observed_at=NOW)

    assert result.health is SourceHealth.SUCCESS
    assert result.records[0]["edition_year"] == 2027
    assert result.records[0]["starts_on"] == "2027-07-26"
    assert result.records[0]["submission_deadline"] is None
    assert "Computational cognitive neuroscience" in result.records[0]["research_areas"]


def test_ccn_layout_variation_keeps_official_identity_and_dates() -> None:
    html = """
    <main><h1>Cognitive Computational Neuroscience</h1>
    <p>The conference meets Monday, July <span>26</span> through Thursday, July
    <strong>29</strong>, in the year 2027.</p>
    <p>Join us in Edinburgh — UK.</p></main>
    """
    transport = html_transport(Ccn2027EventAdapter.source.retrieval_url, html)

    result = Ccn2027EventAdapter(HttpClient(transport=transport)).collect(observed_at=NOW)

    assert result.health is SourceHealth.SUCCESS
    assert result.records[0]["title"] == "Cognitive Computational Neuroscience 2027"
    assert result.records[0]["starts_on"] == "2027-07-26"
    assert result.records[0]["ends_on"] == "2027-07-29"


def test_ccn_robots_block_is_reported_without_page_request() -> None:
    robots = "https://2027.ccneuro.org/robots.txt"
    transport = RouteTransport({robots: response(robots, "User-agent: *\nDisallow: /\n")})

    result = Ccn2027EventAdapter(HttpClient(transport=transport)).collect(observed_at=NOW)

    assert result.health is SourceHealth.BLOCKED
    assert result.records == []
    assert transport.calls == [robots]


def test_ccn_event_identity_is_stable_and_domain_first_scoring_is_core() -> None:
    raw = Ccn2027EventAdapter()._extract(
        "Cognitive Computational Neuroscience July 26-29, 2027 Edinburgh, UK"
    )
    first = run_events_pipeline(
        [raw], config_dir=ROOT / "config", observed_at=NOW, reference_date=NOW.date()
    ).records[0]
    repeated = run_events_pipeline(
        [raw], config_dir=ROOT / "config", observed_at=NOW, reference_date=NOW.date()
    ).records[0]
    next_edition = dict(raw)
    next_edition.update(
        {
            "title": "Cognitive Computational Neuroscience 2028",
            "edition_year": 2028,
            "starts_on": "2028-07-26",
            "ends_on": "2028-07-29",
        }
    )
    later = run_events_pipeline(
        [next_edition],
        config_dir=ROOT / "config",
        observed_at=NOW,
        reference_date=NOW.date(),
    ).records[0]

    assert first.opportunity.opportunity_id == repeated.opportunity.opportunity_id
    assert first.opportunity.opportunity_id != later.opportunity.opportunity_id
    assert first.score.domain_fit is DomainFitClassification.CORE_DOMAIN_FIT
    assert first.score.components["research_fit"] == 100.0


def test_cmu_programme_profile_is_not_open_admission_without_cycle_evidence() -> None:
    pages = {
        CmuCognitiveNeuroscienceProgramAdapter._PAGES[0]: (
            "<h1>Cognitive Neuroscience Graduate Program</h1>"
            "<p>Study mind, brain, behavior and computational science using fMRI and EEG.</p>"
        ),
        CmuCognitiveNeuroscienceProgramAdapter._PAGES[1]: (
            "<h1>Admissions</h1><p>The general deadline is December 1.</p>"
        ),
        CmuCognitiveNeuroscienceProgramAdapter._PAGES[2]: (
            "<p>All students receive full support including stipend and tuition.</p>"
        ),
    }
    routes: dict[str, HttpResponse | Exception] = {
        "https://www.cmu.edu/robots.txt": response(
            "https://www.cmu.edu/robots.txt", "User-agent: *\nAllow: /\n"
        )
    }
    routes.update({url: response(url, body) for url, body in pages.items()})

    result = CmuCognitiveNeuroscienceProgramAdapter(
        HttpClient(transport=RouteTransport(routes))
    ).collect(observed_at=NOW)

    assert result.health is SourceHealth.SUCCESS_NO_MATCHES
    assert result.records == []
    assert len(result.informational_profiles) == 1
    profile = result.informational_profiles[0]
    assert profile["actionable_opportunity"] is False
    assert profile["admission_cycle"] is None
    assert profile["application_deadline"] is None
    assert profile["recruitment_status"] == "FUTURE_CYCLE_NOT_ANNOUNCED"


def test_neuroelectrics_talent_pool_is_not_specific_open_vacancy() -> None:
    careers_url = NeuroelectricsCareersAdapter.source.retrieval_url
    board_url = "https://neuroelectrics.jobs.personio.com/?language=en"
    routes = {
        "https://www.neuroelectrics.com/robots.txt": response(
            "https://www.neuroelectrics.com/robots.txt", "User-agent: *\nAllow: /\n"
        ),
        careers_url: response(
            careers_url,
            '<a href="https://neuroelectrics.jobs.personio.com/">See open positions</a>',
        ),
        "https://neuroelectrics.jobs.personio.com/robots.txt": response(
            "https://neuroelectrics.jobs.personio.com/robots.txt",
            "User-agent: *\nAllow: /\n",
        ),
        board_url: response(
            board_url,
            '<a href="/job/814039">TALENT POOL (PERMANENT POSITION)</a>',
        ),
    }

    result = NeuroelectricsCareersAdapter(HttpClient(transport=RouteTransport(routes))).collect(
        observed_at=NOW
    )

    assert result.health is SourceHealth.SUCCESS_NO_MATCHES
    assert result.records == []
    assert result.informational_profiles[0]["profile_type"] == "TALENT_POOL"


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
