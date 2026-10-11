"""Opportunity identity resolution and deterministic deduplication."""

from __future__ import annotations

from research_radar.models import Opportunity


def deduplicate(records: list[Opportunity]) -> tuple[list[Opportunity], int]:
    """Merge only records sharing a category-specific strong identity key."""

    unique: dict[str, Opportunity] = {}
    duplicates = 0
    for record in records:
        key = record.identity_key or record.opportunity_id
        existing = unique.get(key)
        if existing is None:
            unique[key] = record
            continue
        duplicates += 1
        existing.first_seen_at = min(existing.first_seen_at, record.first_seen_at)
        existing.last_seen_at = max(existing.last_seen_at, record.last_seen_at)
        existing.source_urls = tuple(dict.fromkeys((*existing.source_urls, *record.source_urls)))
        if existing.source_verification_status.value != "VERIFIED_OFFICIAL":
            existing.source_verification_status = record.source_verification_status
    return list(unique.values()), duplicates
