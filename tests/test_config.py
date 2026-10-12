from pathlib import Path

import pytest

from research_radar.config import (
    ConfigValidationError,
    load_all_configs,
    load_career_preferences,
    load_research_interests,
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
