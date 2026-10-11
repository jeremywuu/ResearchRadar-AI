# Data Schema

## General rules

- IDs are deterministic and prefixed by record type.
- Timestamps are timezone-aware.
- Missing optional facts are `None`, not guessed strings.
- Source text and URLs are preserved alongside normalized values.
- New optional fields should have defaults to avoid unnecessary breaking changes.

## Source and opportunity states

| Concern | Field | Meaning |
|---|---|---|
| Official-source identity | `monitoring_status` | Whether a watchlist URL is verified, pending, or disabled |
| Collector operation | `adapter_status` | Whether collection is not implemented, ready, failing, or disabled |
| Observed availability | `opportunity_status` | Whether evidence confirms open, upcoming, potential, historical, closed, or unknown |

These fields are intentionally independent.

## WatchlistTarget

Required fields:

```text
target_id
name
category
country_or_region
priority
research_focus
official_website
monitoring_url
source_type
monitoring_status
adapter_status
```

`canonical_organization` is optional and prevents internal research teams such as FAIR from being
treated as separate employers.

## Shared opportunity fields

`IndustryJob`, `PhDOpportunity`, and `AcademicEvent` share:

```text
opportunity_id
title
organization
source_url
first_seen_at
last_seen_at
source_verification_status
opportunity_status
classification
description?
location?
working_language?
english_compatibility
deadline?
review_flags
```

## IndustryJob

```text
job_family?
seniority?
degree_requirement?
skills
base_salary_min?
base_salary_max?
bonus_min?
bonus_max?
equity_min?
equity_max?
total_compensation_min?
total_compensation_max?
currency?
salary_period?
compensation_source?
compensation_disclosure_status
```

Base, bonus, equity, and total compensation are separate facts. Percentile fields are omitted
from the MVP model until a reliable dataset exists.

## PhDOpportunity

```text
supervisor?
laboratory?
target_cycle?
funding_status?
admission_url?
```

## AcademicEvent

```text
event_type?
starts_on?
ends_on?
submission_deadline?
event_url?
```

## UserFeedback

```text
feedback_id
opportunity_id
preference?  # VERY_INTERESTED, INTERESTED, NOT_RELEVANT
saved        # independent bookmark
hidden       # independent visibility control
updated_at
notes?
```

`saved` does not change relevance. `hidden` never deletes the opportunity or its history.

## Planned Google Sheets tabs

- `Opportunities`: canonical current records and protected user fields
- `Organizations`: normalized watchlist organizations
- `Sources`: source verification and adapter health
- `OpportunityHistory`: append-only changed snapshots
- `FeedbackLog`: preference, bookmark, and visibility changes
- `Runs`: per-category and aggregate execution outcomes and cost
- `Errors`: structured recoverable and terminal failures
- `Dashboard`: formulas and pivots only

The exact column mapping is finalized in Milestone 3 before the Sheets adapter is implemented.
