"""YAML configuration loading and schema validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
    }
    missing = sorted(required_keys - data.keys())
    if missing:
        raise ConfigValidationError(f"{path}: missing fields: {', '.join(missing)}")
    _load_non_empty_string_list(path, "geographic_scope")
    _load_non_empty_string_list(path, "phd_target_cycles")
    _load_non_empty_string_list(path, "target_skills")
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


def load_all_configs(config_dir: Path) -> dict[str, int]:
    watchlist = load_watchlist(config_dir / "watchlist.yaml")
    interests = load_research_interests(config_dir / "research_interests.yaml")
    load_career_preferences(config_dir / "career_preferences.yaml")
    salary = load_salary_rules(config_dir / "salary_rules.yaml")
    return {
        "watchlist_targets": len(watchlist),
        "research_interests": len(interests["primary_interests"]),
        "salary_weights_total": sum(salary["industry_job_scoring_weights"].values()),
    }
