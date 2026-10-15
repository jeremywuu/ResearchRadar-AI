from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from research_radar.collectors.http import HttpClient, HttpResponse, HttpRetrievalError
from research_radar.collectors.pilot import (
    CmuNeuralComputationProgramAdapter,
    ParadromicsCareersAdapter,
    Rldm2027EventAdapter,
    milestone_6_pilot_adapters,
)
from research_radar.collectors.service import default_adapters
from research_radar.config import load_source_discovery
from research_radar.models import DomainFitClassification, SourceHealth
from research_radar.pipelines import run_events_pipeline, run_jobs_pipeline
from research_radar.source_preview import ResearchRoleFit, audit_paradromics_role

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


class RouteTransport:
    def __init__(self, routes: dict[str, HttpResponse | Exception]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        self.calls.append(url)
        outcome = self.routes[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def response(url: str, body: str) -> HttpResponse:
    return HttpResponse(url=url, status=200, body=body.encode(), headers={})


def robots_routes(host: str) -> dict[str, HttpResponse | Exception]:
    url = f"https://{host}/robots.txt"
    return {url: response(url, "User-agent: *\nAllow: /\n")}


def test_review_registry_is_disabled_and_has_expected_coverage() -> None:
    registry = load_source_discovery(ROOT / "config" / "source_discovery.yaml")

    assert len(registry["sources"]) == 15
    assert {source["category"] for source in registry["sources"]} == {
        "phd",
        "jobs",
        "events",
    }
    assert all(source["activate_in_production"] is False for source in registry["sources"])
    assert {source["review_status"] for source in registry["sources"]} <= {
        "READY_FOR_PILOT",
        "NEEDS_MANUAL_REVIEW",
        "INFORMATIONAL_ONLY",
        "BLOCKED",
        "UNSUITABLE",
    }


def test_pilot_adapters_are_not_registered_for_production() -> None:
    pilot_ids = set(milestone_6_pilot_adapters())

    assert pilot_ids == {
        "cmu_neural_computation_profile",
        "paradromics_careers_pilot",
        "rldm_2027_official_pilot",
    }
    assert pilot_ids.isdisjoint(default_adapters())


def test_cmu_neural_computation_is_profile_not_open_fall_2028_opportunity() -> None:
    url = CmuNeuralComputationProgramAdapter.source.retrieval_url
    routes = robots_routes("www.cmu.edu")
    routes[url] = response(
        url,
        """
        <h1>Ph.D. in Neural Computation (PNC)</h1>
        <a href="https://apply-dc-mcs.mcs.cmu.edu/">Apply Now</a>
        <h2>Application Deadline</h2><p>December 1</p>
        <p>Computational neuroscience uses machine learning, statistics, neural data,
        and experimental neuroscience to understand cognition.</p>
        """,
    )
    result = CmuNeuralComputationProgramAdapter(
        HttpClient(transport=RouteTransport(routes))
    ).collect(observed_at=NOW)

    assert result.health is SourceHealth.SUCCESS_NO_MATCHES
    assert result.records == []
    profile = result.informational_profiles[0]
    assert profile["profile_type"] == "PHD_PROGRAM_PROFILE"
    assert profile["admission_cycle"] is None
    assert profile["official_deadline"] is None
    assert profile["confirmed_recruitment_status"] == "UNKNOWN"
    assert "Fall 2028" in profile["source_evidence"][1]


def test_cmu_blocked_request_does_not_fabricate_profile() -> None:
    url = CmuNeuralComputationProgramAdapter.source.retrieval_url
    routes = robots_routes("www.cmu.edu")
    routes[url] = HttpRetrievalError("forbidden", status=403)

    result = CmuNeuralComputationProgramAdapter(
        HttpClient(transport=RouteTransport(routes), max_attempts=1)
    ).collect(observed_at=NOW)

    assert result.health is SourceHealth.BLOCKED
    assert result.records == []
    assert result.informational_profiles == []


def _paradromics_routes() -> dict[str, HttpResponse | Exception]:
    careers = ParadromicsCareersAdapter.source.retrieval_url
    software = "https://paradromicsinc.applytojob.com/apply/abc123/Software-Engineer"
    embedded = "https://paradromicsinc.applytojob.com/apply/def456/Embedded-Software-Engineer"
    mechanical = "https://paradromicsinc.applytojob.com/apply/ghi789/Mechanical-Design-Engineer"
    routes = {
        **robots_routes("paradromics.com"),
        **robots_routes("paradromicsinc.applytojob.com"),
        careers: response(
            careers,
            f"""
            <a href="{software}">Software Engineer Oakland, CA Apply</a>
            <a href="{embedded}">Embedded Software Engineer Austin, TX Apply</a>
            <a href="{mechanical}">Mechanical Design Engineer Austin, TX Apply</a>
            """,
        ),
        software: response(
            software,
            """
            <h1>Software Engineer</h1><p>Oakland, CA</p>
            <p>Develop BCI decoding algorithms and evaluate them with real neural data.</p>
            <p>Bachelor's degree in Computer Science or related field.</p>
            <p>Python, machine learning, signal processing and time series.</p>
            <p>Salary: $120,000-150,000 base</p>
            """,
        ),
        embedded: response(
            embedded,
            """
            <h1>Embedded Software Engineer</h1><p>Austin, TX</p>
            <p>Build low-latency software for brain machine implants and BCI hardware.</p>
            <p>Rust and C++ required.</p>
            """,
        ),
    }
    return routes


def test_paradromics_follows_only_officially_linked_relevant_jobs() -> None:
    transport = RouteTransport(_paradromics_routes())
    result = ParadromicsCareersAdapter(HttpClient(transport=transport)).collect(observed_at=NOW)

    assert result.health is SourceHealth.SUCCESS
    assert result.records_fetched == 3
    assert result.records_matched == 2
    assert len(result.records) == 2
    assert {record["official_job_id"] for record in result.records} == {"abc123", "def456"}
    assert all(record["working_language"] is None for record in result.records)
    assert result.records[0]["salary"]["base_min"] == "120000"
    assert "Neural encoding and decoding" in result.records[0]["research_areas"]
    assert "ghi789" not in " ".join(transport.calls)


def test_paradromics_records_keep_stable_ids_and_domain_first_scores() -> None:
    result = ParadromicsCareersAdapter(
        HttpClient(transport=RouteTransport(_paradromics_routes()))
    ).collect(observed_at=NOW)
    first = run_jobs_pipeline(result.records, config_dir=ROOT / "config", observed_at=NOW)
    repeated = run_jobs_pipeline(result.records, config_dir=ROOT / "config", observed_at=NOW)

    assert [record.opportunity.opportunity_id for record in first.records] == [
        record.opportunity.opportunity_id for record in repeated.records
    ]
    assert first.records[0].score.domain_fit is DomainFitClassification.CORE_DOMAIN_FIT
    assert first.records[1].score.domain_fit is DomainFitClassification.ADJACENT_DOMAIN_FIT


def test_paradromics_duplicate_official_job_id_is_deduplicated() -> None:
    result = ParadromicsCareersAdapter(
        HttpClient(transport=RouteTransport(_paradromics_routes()))
    ).collect(observed_at=NOW)

    report = run_jobs_pipeline(
        [result.records[0], dict(result.records[0])],
        config_dir=ROOT / "config",
        observed_at=NOW,
    )

    assert report.records_accepted == 1
    assert report.duplicates_found == 1


def test_paradromics_irrelevant_candidate_is_excluded_without_technical_error() -> None:
    careers = ParadromicsCareersAdapter.source.retrieval_url
    role = "https://paradromicsinc.applytojob.com/apply/abc123/Software-Engineer"
    routes = {
        **robots_routes("paradromics.com"),
        **robots_routes("paradromicsinc.applytojob.com"),
        careers: response(
            careers,
            f'<a href="{role}">Software Engineer Oakland, CA Apply</a>',
        ),
        role: response(
            role,
            "<h1>Software Engineer</h1><p>Build general internal business applications.</p>",
        ),
    }

    result = ParadromicsCareersAdapter(HttpClient(transport=RouteTransport(routes))).collect(
        observed_at=NOW
    )

    assert result.health is SourceHealth.SUCCESS_NO_MATCHES
    assert result.records == []
    assert result.errors == []
    assert result.informational_profiles[0]["profile_type"] == "LOW_DOMAIN_EVIDENCE_ROLE"


def test_bci_employer_boilerplate_is_not_role_level_evidence() -> None:
    careers = ParadromicsCareersAdapter.source.retrieval_url
    role = "https://paradromicsinc.applytojob.com/apply/abc123/Software-Engineer"
    routes = {
        **robots_routes("paradromics.com"),
        **robots_routes("paradromicsinc.applytojob.com"),
        careers: response(
            careers,
            f'<a href="{role}">Software Engineer Oakland, CA Apply</a>',
        ),
        role: response(
            role,
            """
            <h1>Software Engineer</h1>
            <p>Build internal billing tools.</p>
            <h2>About Paradromics</h2>
            <p>Paradromics is a brain-computer interface company.</p>
            """,
        ),
    }

    result = ParadromicsCareersAdapter(HttpClient(transport=RouteTransport(routes))).collect(
        observed_at=NOW
    )

    assert result.health is SourceHealth.SUCCESS_NO_MATCHES
    assert result.records == []
    assert result.errors == []


def test_clinical_bci_role_is_audited_separately_from_domain_score() -> None:
    raw = ParadromicsCareersAdapter()._extract_job(
        "https://paradromicsinc.applytojob.com/apply/clinical/Field-Clinical-Specialist-Engineer",
        "Field Clinical Specialist/Engineer",
        "Austin, TX",
        """
        <h1>Field Clinical Specialist/Engineer</h1>
        <p>Support clinical BCI procedures and train hospital teams working with neural data.</p>
        """,
    )
    processed = run_jobs_pipeline([raw], config_dir=ROOT / "config", observed_at=NOW).records[0]

    audit = audit_paradromics_role(processed)

    assert audit.role_fit is ResearchRoleFit.CLINICAL_IMPLEMENTATION
    assert "do not establish a research position" in audit.reason


def test_bci_decoding_software_role_remains_research_adjacent() -> None:
    raw = ParadromicsCareersAdapter()._extract_job(
        "https://paradromicsinc.applytojob.com/apply/software/Software-Engineer",
        "Software Engineer",
        "Oakland, CA",
        """
        <h1>Software Engineer</h1>
        <p>Develop clinical applications for a BCI system.</p>
        <p>Realize BCI decoding algorithms and evaluate them with real neural data.</p>
        """,
    )
    processed = run_jobs_pipeline([raw], config_dir=ROOT / "config", observed_at=NOW).records[0]

    audit = audit_paradromics_role(processed)

    assert audit.role_fit is ResearchRoleFit.RESEARCH_ADJACENT_ENGINEERING


def _rldm_routes() -> dict[str, HttpResponse | Exception]:
    home = Rldm2027EventAdapter.source.retrieval_url
    call = Rldm2027EventAdapter._CALL_URL
    return {
        **robots_routes("rldm.org"),
        home: response(
            home,
            """
            <h1>The Multi-disciplinary Conference on Reinforcement Learning and Decision Making</h1>
            <p>Save the dates: July 6-9, 2027</p>
            <p>Location: Maison de la Chimie, Paris, France</p>
            <p>Learning and decision making in humans, animals, and algorithms.</p>
            """,
        ),
        call: response(
            call,
            """
            <h1>Call for Abstracts</h1>
            <p>Submissions due: 20 January 2027 AOE (Anywhere on Earth)</p>
            <p>Conference: 6-9 July 2027</p>
            """,
        ),
    }


def test_rldm_extracts_distinct_event_and_submission_deadline() -> None:
    result = Rldm2027EventAdapter(HttpClient(transport=RouteTransport(_rldm_routes()))).collect(
        observed_at=NOW
    )

    assert result.health is SourceHealth.SUCCESS
    record = result.records[0]
    assert record["starts_on"] == "2027-07-06"
    assert record["ends_on"] == "2027-07-09"
    assert record["submission_deadline"] == "2027-01-20"
    assert record["submission_deadline_timezone"] == "AoE"
    assert record["registration_deadline"] is None
    assert record["location"] == "Paris"


def test_rldm_deadline_parser_tolerates_official_layout_text_between_label_and_date() -> None:
    raw = Rldm2027EventAdapter()._extract(
        """
        The Multi-disciplinary Conference on Reinforcement Learning and Decision Making
        July 6-9, 2027, Paris, France
        """,
        "Submissions due Key date January 20, 2027 (Anywhere on Earth)",
    )

    assert raw["submission_deadline"] == "2027-01-20"


def test_rldm_stable_event_id_and_core_research_fit() -> None:
    raw = Rldm2027EventAdapter()._extract(
        """
        The Multi-disciplinary Conference on Reinforcement Learning and Decision Making
        July 6-9, 2027 Paris, France
        """,
        "Submissions due: 20 January 2027 AOE",
    )
    first = run_events_pipeline(
        [raw], config_dir=ROOT / "config", observed_at=NOW, reference_date=date(2026, 10, 14)
    ).records[0]
    repeated = run_events_pipeline(
        [raw], config_dir=ROOT / "config", observed_at=NOW, reference_date=date(2026, 10, 14)
    ).records[0]

    assert first.opportunity.opportunity_id == repeated.opportunity.opportunity_id
    assert first.score.domain_fit is DomainFitClassification.CORE_DOMAIN_FIT
