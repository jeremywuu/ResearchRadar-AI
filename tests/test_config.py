from pathlib import Path

import pytest

from research_radar.config import (
    ConfigValidationError,
    load_all_configs,
    load_career_preferences,
    load_research_interests,
    load_source_discovery,
    load_source_expansion,
    load_watchlist,
    load_yaml,
)
from research_radar.models import Priority

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_all_project_yaml_configuration_loads_and_validates() -> None:
    result = load_all_configs(PROJECT_ROOT / "config")

    assert result["watchlist_targets"] == 38
    assert result["research_interests"] >= 10
    assert result["salary_weights_total"] == 100
    assert result["source_expansion_targets"] == 6
    assert result["source_discovery_targets"] == 15

    interests = load_research_interests(PROJECT_ROOT / "config" / "research_interests.yaml")
    assert interests["research_identity"]["primary_field"] == (
        "Computational Cognitive Neuroscience"
    )
    assert interests["research_relevance"]["component_weights"] == {
        "domain_fit": 55,
        "methodological_fit": 25,
        "research_question_fit": 20,
    }


def test_yaml_loader_uses_a_real_parser_and_rejects_invalid_escapes(tmp_path: Path) -> None:
    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text('url: "https\\://www\\.anthropic.com/"\n', encoding="utf-8")

    with pytest.raises(ConfigValidationError, match="valid YAML"):
        load_yaml(invalid_yaml)


def test_watchlist_rejects_invalid_urls(tmp_path: Path) -> None:
    watchlist = tmp_path / "watchlist.yaml"
    watchlist.write_text(
        """
version: 1
targets:
  - name: Example
    category: ai_big_tech
    country_or_region: Global
    priority: P0
    research_focus: AI
    official_website: "not-a-url"
    monitoring_url: "https://example.com/jobs"
    source_type: official_careers_page
    monitoring_status: VERIFIED_ACTIVE_SOURCE
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="official_website"):
        load_watchlist(watchlist)


def test_watchlist_priority_is_limited_to_p0_or_p1(tmp_path: Path) -> None:
    watchlist = tmp_path / "watchlist.yaml"
    watchlist.write_text(
        """
version: 1
targets:
  - name: Example
    category: ai_big_tech
    country_or_region: Global
    priority: P2
    research_focus: AI
    official_website: "https://example.com/"
    monitoring_url: "https://example.com/jobs"
    source_type: official_careers_page
    monitoring_status: VERIFIED_ACTIVE_SOURCE
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="priority"):
        load_watchlist(watchlist)


def test_project_watchlist_priorities_are_valid() -> None:
    targets = load_watchlist(PROJECT_ROOT / "config" / "watchlist.yaml")

    assert targets
    assert {target.priority for target in targets} <= {Priority.P0, Priority.P1}


def test_research_interest_weights_must_be_complete_and_bounded(tmp_path: Path) -> None:
    path = tmp_path / "research_interests.yaml"
    path.write_text(
        "version: 1\nprimary_interests: [AI, BCI]\ninterest_weights: {AI: 101}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="every primary interest"):
        load_research_interests(path)


def test_recommendation_rules_are_configured_and_valid() -> None:
    preferences = load_career_preferences(PROJECT_ROOT / "config" / "career_preferences.yaml")
    rules = preferences["recommendation_rules"]

    assert set(rules["title_signals"]) == {
        "high_priority",
        "relevant",
        "low_priority",
        "needs_review",
    }
    assert rules["score_thresholds"]["high_priority"] > rules["score_thresholds"]["relevant"]


def test_source_expansion_backlog_contains_only_verified_candidates() -> None:
    expansion = load_source_expansion(PROJECT_ROOT / "config" / "source_expansion.yaml")

    assert {item["source_id"] for item in expansion["backlog"]} == {
        "rldm_official",
        "synchron_careers",
        "ohbm_official",
    }
    assert {item["implementation_status"] for item in expansion["backlog"]} == {
        "VERIFIED_CANDIDATE"
    }


def test_source_discovery_registry_cannot_activate_production() -> None:
    discovery = load_source_discovery(PROJECT_ROOT / "config" / "source_discovery.yaml")

    assert len(discovery["sources"]) == 15
    assert all(item["activate_in_production"] is False for item in discovery["sources"])
    readiness = {
        item["source_id"]: item.get("activation_readiness") for item in discovery["sources"]
    }
    assert readiness["rldm_2027_official_pilot"] == ("APPROVED_FOR_PRODUCTION_PREPARATION")
    assert readiness["paradromics_careers_pilot"] == "CONDITIONAL_ROLE_FUNCTION_GATE"
    assert readiness["cmu_neural_computation_profile"] == "INFORMATIONAL_WATCH_ONLY"


def test_source_discovery_rejects_production_activation(tmp_path: Path) -> None:
    path = tmp_path / "source_discovery.yaml"
    source = (PROJECT_ROOT / "config" / "source_discovery.yaml").read_text()
    path.write_text(
        source.replace("activate_in_production: false", "activate_in_production: true", 1)
    )

    with pytest.raises(ConfigValidationError, match="disabled for production"):
        load_source_discovery(path)
