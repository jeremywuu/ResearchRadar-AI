import json
from datetime import UTC, datetime
from pathlib import Path

from research_radar.career_stage import CareerStageFit, assess_career_stage
from research_radar.collectors.http import HttpClient, HttpResponse
from research_radar.collectors.job_pilot import (
    NeuralinkCareersPilotAdapter,
    PrecisionNeuroscienceCareersPilotAdapter,
    SynchronCareersPilotAdapter,
    milestone_6_3a_pilot_adapters,
)
from research_radar.collectors.service import default_adapters
from research_radar.models import SourceHealth
from research_radar.pipelines import run_jobs_pipeline
from research_radar.role_function import RoleFunction, assess_role_function

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


class RouteTransport:
    def __init__(self, routes: dict[str, HttpResponse]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        self.calls.append(url)
        return self.routes[url]


def _response(url: str, body: str) -> HttpResponse:
    return HttpResponse(url=url, status=200, body=body.encode(), headers={})


def test_job_pilots_are_not_registered_in_production() -> None:
    pilot_ids = set(milestone_6_3a_pilot_adapters())
    production_ids = set(default_adapters(environment={})) | set(
        default_adapters(environment={"RESEARCH_RADAR_RESEARCH_SOURCES_ENABLED": "true"})
    )

    assert pilot_ids == {
        "neuralink_careers_discovery",
        "precision_neuroscience_careers_discovery",
        "synchron_careers_discovery",
    }
    assert pilot_ids.isdisjoint(production_ids)


def test_neuralink_requires_official_board_ownership_and_extracts_bounded_role() -> None:
    careers = "https://neuralink.com/careers/"
    listing = NeuralinkCareersPilotAdapter.source.retrieval_url
    detail_url = "https://boards-api.greenhouse.io/v1/boards/neuralink/jobs/6594261003"
    detail = {
        "id": 6594261003,
        "title": "Machine Learning Engineer Intern, BCI Applications",
        "absolute_url": "https://job-boards.greenhouse.io/neuralink/jobs/6594261003",
        "location": {"name": "South San Francisco, California"},
        "content": (
            "<p>Develop neural decoders and analyze complex neural data.</p>"
            "<p>Prior machine learning model-building experience. "
            "Work authorization and sponsorship questions apply.</p>"
        ),
    }
    routes = {
        "https://neuralink.com/robots.txt": _response(
            "https://neuralink.com/robots.txt", "User-agent: *\nAllow: /\n"
        ),
        careers: _response(
            careers,
            '<a href="https://job-boards.greenhouse.io/neuralink">Open positions</a>',
        ),
        listing: _response(
            listing,
            json.dumps(
                {
                    "jobs": [
                        {"id": 6594261003, "title": detail["title"]},
                        {"id": 1, "title": "Account Executive"},
                    ]
                }
            ),
        ),
        detail_url: _response(detail_url, json.dumps(detail)),
    }

    result = NeuralinkCareersPilotAdapter(HttpClient(transport=RouteTransport(routes))).collect(
        observed_at=NOW
    )

    assert result.health is SourceHealth.SUCCESS
    assert result.records_fetched == 2
    assert result.records_considered == 1
    assert result.records[0]["official_job_id"] == "6594261003"
    assert result.records[0]["listing_status"] == "CONFIRMED_LISTED"


def test_neuralink_stable_id_uses_greenhouse_id() -> None:
    raw = {
        "fictional": False,
        "title": "Machine Learning Engineer Intern, BCI Applications",
        "organization": "Neuralink",
        "source_url": "https://job-boards.greenhouse.io/neuralink/jobs/6594261003",
        "official_source_url": "https://neuralink.com/careers/",
        "official_job_id": "6594261003",
        "location": "South San Francisco, California",
        "research_areas": ["Brain-computer interfaces"],
        "research_orientation": "Applied research",
        "education_requirement": "Unknown",
        "skills": [],
        "salary": {},
        "source_verification_status": "VERIFIED_OFFICIAL",
        "opportunity_status": "confirmed open",
        "source_type": "official_linked_ats",
        "source_evidence": ["Current official index"],
        "extraction_method": "official_careers_plus_greenhouse_api",
        "adapter_source_id": "neuralink_careers_discovery",
    }
    first = run_jobs_pipeline([raw], config_dir=ROOT / "config", observed_at=NOW)
    renamed = {**raw, "title": "BCI Machine Learning Engineer Intern"}
    second = run_jobs_pipeline([renamed], config_dir=ROOT / "config", observed_at=NOW)

    assert (
        first.records[0].opportunity.opportunity_id == second.records[0].opportunity.opportunity_id
    )


def test_precision_extracts_dsp_role_and_keeps_readiness_unconfirmed() -> None:
    careers = "https://www.precisionneuro.io/careers"
    index = "https://careers.kula.ai/precision-neuroscience"
    detail = "https://careers.kula.ai/precision-neuroscience/39009-dsp-algorithm-engineer"
    routes = {
        "https://www.precisionneuro.io/robots.txt": _response(
            "https://www.precisionneuro.io/robots.txt", "User-agent: *\nAllow: /\n"
        ),
        "https://careers.kula.ai/robots.txt": _response(
            "https://careers.kula.ai/robots.txt", "User-agent: *\nAllow: /\n"
        ),
        careers: _response(
            careers,
            '<a href="https://careers.kula.ai/precision-neuroscience">Open positions</a>',
        ),
        index: _response(index, f'<a href="{detail}">DSP Algorithm Engineer</a>'),
        detail: _response(
            detail,
            "<h1>DSP Algorithm Engineer</h1><p>Improve the BCI signal acquisition chain, "
            "develop signal processing algorithms and machine learning feature extraction. "
            "Candidates must be legally authorized to work in the US.</p>",
        ),
    }

    result = PrecisionNeuroscienceCareersPilotAdapter(
        HttpClient(transport=RouteTransport(routes))
    ).collect(observed_at=NOW)
    job = (
        run_jobs_pipeline(
            result.records,
            config_dir=ROOT / "config",
            observed_at=NOW,
        )
        .records[0]
        .opportunity
    )
    role = assess_role_function(job)
    stage = assess_career_stage(job, role.classification)

    assert result.health is SourceHealth.SUCCESS
    assert job.official_job_id == "39009"
    assert role.classification is RoleFunction.RESEARCH_ADJACENT_ENGINEERING
    assert stage.classification is CareerStageFit.PRE_PHD_RESEARCH_ENGINEERING
    assert stage.confirmed_eligibility is None
    assert stage.work_authorization_evidence is not None


def test_synchron_cognition_team_is_profile_with_no_current_job() -> None:
    careers = "https://synchron.com/careers"
    routes = {
        "https://synchron.com/robots.txt": _response(
            "https://synchron.com/robots.txt", "User-agent: *\nAllow: /\n"
        ),
        careers: _response(
            careers,
            "<h2>New York cognition lab</h2><p>Neural signals, models of human thought, "
            "closed-loop neurofeedback, and HCI.</p><p>No current openings here</p>"
            '<a href="https://workforcenow.adp.com/jobs/apply/posting.html?jobId=10">'
            "Principal Mechanical Engineer</a>",
        ),
    }

    result = SynchronCareersPilotAdapter(HttpClient(transport=RouteTransport(routes))).collect(
        observed_at=NOW
    )

    assert result.health is SourceHealth.SUCCESS_NO_MATCHES
    assert result.records == []
    assert result.informational_profiles[0]["profile_type"] == "RESEARCH_TEAM_PROFILE"
    assert result.informational_profiles[0]["actionable_opportunity"] is False
    assert result.informational_profiles[0]["current_opening_status"] == (
        "CONFIRMED_NO_CURRENT_OPENINGS"
    )
