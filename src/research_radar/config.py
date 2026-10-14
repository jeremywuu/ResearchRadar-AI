"""YAML configuration loading and schema validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from research_radar.models import (
    AdapterStatus,
    MonitoringStatus,
    Priority,
    TargetCategory,
    WatchlistTarget,
)


class ConfigValidationError(ValueError):
    """Raised when configuration is syntactically invalid or violates its schema."""


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigValidationError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigValidationError(f"{path} must contain a YAML mapping")
    return data


def _require_version_one(data: dict[str, Any], path: Path) -> None:
    if data.get("version") != 1:
        raise ConfigValidationError(f"{path}: version must be 1")


def _required_string(item: dict[str, Any], field_name: str, index: int) -> str:
    value = item.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigValidationError(f"targets[{index}].{field_name} must be a non-empty string")
    return value


def load_watchlist(path: Path) -> list[WatchlistTarget]:
    data = load_yaml(path)
    _require_version_one(data, path)
    items = data.get("targets")
    if not isinstance(items, list) or not items:
        raise ConfigValidationError(f"{path}: targets must be a non-empty list")

    targets: list[WatchlistTarget] = []
    for index, raw_item in enumerate(items):
        if not isinstance(raw_item, dict):
            raise ConfigValidationError(f"targets[{index}] must be a mapping")
        priority_value = _required_string(raw_item, "priority", index)
        try:
            priority = Priority(priority_value)
        except ValueError as exc:
            raise ConfigValidationError(
                f"targets[{index}].priority must be one of: P0, P1"
            ) from exc
        try:
            target = WatchlistTarget(
                name=_required_string(raw_item, "name", index),
                canonical_organization=raw_item.get("canonical_organization"),
                category=TargetCategory(_required_string(raw_item, "category", index)),
                country_or_region=_required_string(raw_item, "country_or_region", index),
                priority=priority,
                research_focus=_required_string(raw_item, "research_focus", index),
                official_website=_required_string(raw_item, "official_website", index),
                monitoring_url=_required_string(raw_item, "monitoring_url", index),
                source_type=_required_string(raw_item, "source_type", index),
                monitoring_status=MonitoringStatus(
                    _required_string(raw_item, "monitoring_status", index)
                ),
                adapter_status=AdapterStatus(raw_item.get("adapter_status", "NOT_IMPLEMENTED")),
            )
        except (TypeError, ValueError) as exc:
            raise ConfigValidationError(f"targets[{index}]: {exc}") from exc
        targets.append(target)

    target_ids = [target.target_id for target in targets]
    if len(target_ids) != len(set(target_ids)):
        raise ConfigValidationError(f"{path}: duplicate watchlist target identities")
    return targets


def _load_non_empty_string_list(path: Path, key: str) -> list[str]:
    data = load_yaml(path)
    _require_version_one(data, path)
    values = data.get(key)
    if not isinstance(values, list) or not values or not all(isinstance(v, str) for v in values):
        raise ConfigValidationError(f"{path}: {key} must be a non-empty list of strings")
    return values


def load_research_interests(path: Path) -> dict[str, Any]:
    data = load_yaml(path)
    _require_version_one(data, path)
    interests = data.get("primary_interests")
    if (
        not isinstance(interests, list)
        or not interests
        or not all(isinstance(value, str) and value.strip() for value in interests)
    ):
        raise ConfigValidationError(f"{path}: primary_interests must be non-empty strings")
    weights = data.get("interest_weights")
    if not isinstance(weights, dict) or set(weights) != set(interests):
        raise ConfigValidationError(
            f"{path}: interest_weights must contain every primary interest exactly once"
        )
    if not all(isinstance(value, int) and 0 <= value <= 100 for value in weights.values()):
        raise ConfigValidationError(f"{path}: interest weights must be integers from 0 to 100")
    revision = data.get("profile_revision")
    if not isinstance(revision, str) or not revision.strip():
        raise ConfigValidationError(f"{path}: profile_revision must be a non-empty string")
    identity = data.get("research_identity")
    if not isinstance(identity, dict) or not all(
        isinstance(identity.get(field_name), str) and identity[field_name].strip()
        for field_name in ("primary_field", "primary_phd_cycle", "thesis")
    ):
        raise ConfigValidationError(f"{path}: research_identity is incomplete")
    tiers = data.get("interest_tiers")
    expected_tiers = {"core", "adjacent", "technical_transferable", "lower_priority"}
    if not isinstance(tiers, dict) or set(tiers) != expected_tiers:
        raise ConfigValidationError(
            f"{path}: interest_tiers must contain {', '.join(sorted(expected_tiers))}"
        )
    for name, values in tiers.items():
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            raise ConfigValidationError(
                f"{path}: interest_tiers.{name} must be a list of non-empty strings"
            )
    ranked_interests = {
        value for name in ("core", "adjacent", "technical_transferable") for value in tiers[name]
    }
    if ranked_interests != set(interests):
        raise ConfigValidationError(
            f"{path}: primary_interests must equal the ranked core, adjacent, and "
            "transferable tiers"
        )
    relevance = data.get("research_relevance")
    if not isinstance(relevance, dict):
        raise ConfigValidationError(f"{path}: research_relevance must be a mapping")
    component_weights = relevance.get("component_weights")
    expected_components = {"domain_fit", "methodological_fit", "research_question_fit"}
    if not isinstance(component_weights, dict) or set(component_weights) != expected_components:
        raise ConfigValidationError(f"{path}: invalid research_relevance.component_weights")
    if not all(
        isinstance(value, int) and 0 <= value <= 100 for value in component_weights.values()
    ):
        raise ConfigValidationError(f"{path}: research relevance weights must be 0-100 integers")
    if sum(component_weights.values()) != 100:
        raise ConfigValidationError(f"{path}: research relevance weights must total 100")
    if component_weights["domain_fit"] <= max(
        component_weights["methodological_fit"], component_weights["research_question_fit"]
    ):
        raise ConfigValidationError(f"{path}: domain_fit must be the largest component weight")
    tier_scores = relevance.get("tier_scores")
    expected_scores = {
        "core",
        "adjacent",
        "technical_transferable",
        "lower_priority",
        "insufficient_evidence",
    }
    if not isinstance(tier_scores, dict) or set(tier_scores) != expected_scores:
        raise ConfigValidationError(f"{path}: invalid research_relevance.tier_scores")
    if not all(isinstance(value, int) and 0 <= value <= 100 for value in tier_scores.values()):
        raise ConfigValidationError(f"{path}: research relevance tier scores must be 0-100")
    for field_name in ("methodology_weights", "research_question_weights"):
        values = relevance.get(field_name)
        if (
            not isinstance(values, dict)
            or not values
            or not all(
                isinstance(key, str)
                and key.strip()
                and isinstance(value, int)
                and 0 <= value <= 100
                for key, value in values.items()
            )
        ):
            raise ConfigValidationError(f"{path}: {field_name} must map terms to 0-100 integers")
    aliases = relevance.get("aliases", {})
    if not isinstance(aliases, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in aliases.items()
    ):
        raise ConfigValidationError(f"{path}: research_relevance.aliases must map strings")
    for field_name in ("lower_priority_title_signals", "interpretability_connection_signals"):
        values = relevance.get(field_name)
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(value, str) and value.strip() for value in values)
        ):
            raise ConfigValidationError(f"{path}: {field_name} must be non-empty strings")
    return data


def load_career_preferences(path: Path) -> dict[str, Any]:
    data = load_yaml(path)
    _require_version_one(data, path)
    required_keys = {
        "job_ranking_priorities",
        "geographic_scope",
        "english_work_environment",
        "phd_target_cycles",
        "career_stages",
        "recommendation_rules",
        "target_skills",
        "preferred_job_families",
        "phd_cycle_scores",
    }
    missing = sorted(required_keys - data.keys())
    if missing:
        raise ConfigValidationError(f"{path}: missing fields: {', '.join(missing)}")
    _load_non_empty_string_list(path, "geographic_scope")
    _load_non_empty_string_list(path, "phd_target_cycles")
    _load_non_empty_string_list(path, "target_skills")
    _load_non_empty_string_list(path, "preferred_job_families")
    cycle_scores = data["phd_cycle_scores"]
    if not isinstance(cycle_scores, dict) or not all(
        isinstance(name, str) and isinstance(value, int) and 0 <= value <= 100
        for name, value in cycle_scores.items()
    ):
        raise ConfigValidationError(f"{path}: phd_cycle_scores must map cycles to 0-100 integers")
    rules = data["recommendation_rules"]
    if not isinstance(rules, dict):
        raise ConfigValidationError(f"{path}: recommendation_rules must be a mapping")
    signals = rules.get("title_signals")
    expected_signals = {"high_priority", "relevant", "low_priority", "needs_review"}
    if not isinstance(signals, dict) or set(signals) != expected_signals:
        raise ConfigValidationError(
            f"{path}: recommendation title_signals must contain "
            + ", ".join(sorted(expected_signals))
        )
    for name, values in signals.items():
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(value, str) and value.strip() for value in values)
        ):
            raise ConfigValidationError(
                f"{path}: recommendation title_signals.{name} must be non-empty strings"
            )
    thresholds = rules.get("score_thresholds")
    if not isinstance(thresholds, dict) or set(thresholds) != {"high_priority", "relevant"}:
        raise ConfigValidationError(f"{path}: invalid recommendation score_thresholds")
    high = thresholds["high_priority"]
    relevant = thresholds["relevant"]
    if not all(isinstance(value, int) and 0 <= value <= 100 for value in (high, relevant)):
        raise ConfigValidationError(f"{path}: recommendation thresholds must be integers 0-100")
    if high <= relevant:
        raise ConfigValidationError(
            f"{path}: high_priority threshold must exceed relevant threshold"
        )
    return data


def load_salary_rules(path: Path) -> dict[str, Any]:
    data = load_yaml(path)
    _require_version_one(data, path)
    weights = data.get("industry_job_scoring_weights")
    if not isinstance(weights, dict) or not all(
        isinstance(value, int) for value in weights.values()
    ):
        raise ConfigValidationError(f"{path}: industry_job_scoring_weights must be integers")
    if sum(weights.values()) != 100:
        raise ConfigValidationError(f"{path}: industry job scoring weights must total 100")
    if data.get("percentile_benchmarking", {}).get("enabled_for_mvp") is not False:
        raise ConfigValidationError(f"{path}: percentile benchmarking must be disabled for MVP")
    thresholds = data.get("aspirational_base_salary_thresholds")
    if not isinstance(thresholds, dict) or not thresholds:
        raise ConfigValidationError(f"{path}: aspirational thresholds are required")
    for region, rule in thresholds.items():
        if not isinstance(rule, dict) or not isinstance(rule.get("annual_base"), int):
            raise ConfigValidationError(f"{path}: invalid threshold for {region}")
    return data


def load_source_expansion(path: Path) -> dict[str, Any]:
    data = load_yaml(path)
    _require_version_one(data, path)
    allowed_statuses = {"IMPLEMENTED", "VERIFIED_CANDIDATE"}
    source_ids: set[str] = set()
    for group_name in ("pilot_sources", "backlog"):
        entries = data.get(group_name)
        if not isinstance(entries, list):
            raise ConfigValidationError(f"{path}: {group_name} must be a list")
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ConfigValidationError(f"{path}: {group_name}[{index}] must be a mapping")
            required = ("source_id", "name", "category", "official_url", "implementation_status")
            if not all(
                isinstance(entry.get(field), str) and entry[field].strip() for field in required
            ):
                raise ConfigValidationError(
                    f"{path}: {group_name}[{index}] has missing string fields"
                )
            parsed = urlparse(entry["official_url"])
            if parsed.scheme != "https" or not parsed.netloc:
                raise ConfigValidationError(
                    f"{path}: {group_name}[{index}].official_url must be HTTPS"
                )
            if entry["implementation_status"] not in allowed_statuses:
                raise ConfigValidationError(
                    f"{path}: {group_name}[{index}] has invalid implementation_status"
                )
            if group_name == "pilot_sources" and entry["implementation_status"] != "IMPLEMENTED":
                raise ConfigValidationError(f"{path}: pilot_sources[{index}] must be IMPLEMENTED")
            if group_name == "backlog" and entry["implementation_status"] != "VERIFIED_CANDIDATE":
                raise ConfigValidationError(f"{path}: backlog[{index}] must be VERIFIED_CANDIDATE")
            source_id = entry["source_id"]
            if source_id in source_ids:
                raise ConfigValidationError(f"{path}: duplicate source_id {source_id}")
            source_ids.add(source_id)
    return data


def load_source_discovery(path: Path) -> dict[str, Any]:
    """Validate the review-only Milestone 6 source registry."""

    data = load_yaml(path)
    _require_version_one(data, path)
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ConfigValidationError(f"{path}: sources must be a non-empty list")
    allowed_categories = {"phd", "jobs", "events"}
    allowed_statuses = {
        "READY_FOR_PILOT",
        "NEEDS_MANUAL_REVIEW",
        "INFORMATIONAL_ONLY",
        "BLOCKED",
        "UNSUITABLE",
    }
    allowed_priorities = {"P0", "P1", "P2"}
    allowed_entity_types = {
        "PHD_PROGRAM_PROFILE",
        "LAB_PROFILE",
        "FACULTY_PROFILE",
        "CONFIRMED_PHD_OPENING",
        "APPLICATION_CYCLE_ANNOUNCEMENT",
        "FUNDING_OPPORTUNITY",
        "OFFICIAL_CAREERS_SOURCE",
        "EVENT_EDITION",
    }
    required = (
        "source_id",
        "organization",
        "url",
        "category",
        "source_entity_type",
        "research_relevance",
        "current_accessibility",
        "extraction_feasibility",
        "data_structure",
        "update_frequency",
        "provenance_quality",
        "expected_value",
        "main_limitations",
        "recommended_priority",
        "review_status",
    )
    source_ids: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise ConfigValidationError(f"{path}: sources[{index}] must be a mapping")
        if not all(
            isinstance(source.get(field), str) and source[field].strip() for field in required
        ):
            raise ConfigValidationError(f"{path}: sources[{index}] has missing string fields")
        parsed = urlparse(source["url"])
        if parsed.scheme != "https" or not parsed.netloc:
            raise ConfigValidationError(f"{path}: sources[{index}].url must be HTTPS")
        if source["category"] not in allowed_categories:
            raise ConfigValidationError(f"{path}: sources[{index}] has invalid category")
        if source["source_entity_type"] not in allowed_entity_types:
            raise ConfigValidationError(f"{path}: sources[{index}] has invalid source_entity_type")
        if source["review_status"] not in allowed_statuses:
            raise ConfigValidationError(f"{path}: sources[{index}] has invalid review_status")
        if source["recommended_priority"] not in allowed_priorities:
            raise ConfigValidationError(
                f"{path}: sources[{index}] has invalid recommended_priority"
            )
        if source.get("activate_in_production") is not False:
            raise ConfigValidationError(
                f"{path}: sources[{index}] must remain disabled for production"
            )
        source_id = source["source_id"]
        if source_id in source_ids:
            raise ConfigValidationError(f"{path}: duplicate source_id {source_id}")
        source_ids.add(source_id)
    return data


def load_all_configs(config_dir: Path) -> dict[str, int]:
    watchlist = load_watchlist(config_dir / "watchlist.yaml")
    interests = load_research_interests(config_dir / "research_interests.yaml")
    load_career_preferences(config_dir / "career_preferences.yaml")
    salary = load_salary_rules(config_dir / "salary_rules.yaml")
    source_expansion = load_source_expansion(config_dir / "source_expansion.yaml")
    source_discovery = load_source_discovery(config_dir / "source_discovery.yaml")
    return {
        "watchlist_targets": len(watchlist),
        "research_interests": len(interests["primary_interests"]),
        "salary_weights_total": sum(salary["industry_job_scoring_weights"].values()),
        "source_expansion_targets": sum(
            len(source_expansion[group]) for group in ("pilot_sources", "backlog")
        ),
        "source_discovery_targets": len(source_discovery["sources"]),
    }
