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
source_urls
identity_key
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
original_values
country?
region?
research_areas
```

## IndustryJob

```text
job_family?
official_job_id?
job_category?
research_orientation
education_requirement
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
compensation_source_url?
original_salary_text?
annualized_base_salary_min?
annualized_base_salary_max?
salary_flags
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
official_opportunity_id?
opportunity_type
```

## AcademicEvent

```text
event_type?
academic_event_type
series_name?
edition_year?
starts_on?
ends_on?
submission_deadline?
registration_deadline?
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

## Processed output

Each category JSON snapshot contains a pipeline summary and a list of processed records. Every
record contains the normalized opportunity, score components and weights, final score,
personalized score, rank, exclusion state, processing status, and optional feedback. On rewrite,
the JSON adapter preserves the earliest first-seen timestamp and existing feedback when the new
input has no feedback. Generated snapshots live under Git-ignored `data/`.

Unknown source facts remain `null`; review flags identify actionable unknowns. The complete raw
fictional input is retained in `original_values`, while normalized values occupy typed fields.

## Google Sheets ownership

Opportunity facts, classifications, scores, URLs, verification timestamps, and statuses are
agent-managed. Preference, saved, hidden, and personal notes are user-managed. Opportunity-sheet
plans never contain user-managed columns. `My_Feedback` is the canonical feedback source and is
joined to opportunities by `Record_ID`; its rows survive opportunity status changes or absence.

`config/watchlist.yaml` remains authoritative. `Watchlist` is an agent-managed, read-only mirror.
Bidirectional editing may be added later only with an explicit conflict-resolution policy and a
single declared authority per field.

All headers are validated exactly before writes. All untrusted values use RAW input semantics.
Blank cells represent unknown facts; no missing value is invented.

## Worksheet schemas

### Industry_Jobs

```text
Record_ID
Job_Title
Company
Location
Country
Research_Domain
Research_Orientation
Education_Requirement
Career_Stage
Working_Language
Required_Skills
Research_Relevance
PhD_Leverage
Skills_Career_Fit
Compensation_Score
Overall_Priority_Score
Original_Salary
Salary_Currency
Salary_Disclosure_Status
Source_URL
First_Seen
Last_Seen
Opportunity_Status
```

### PhD_Opportunities

```text
Record_ID
University
Program_or_Position
Research_Area
PI_Supervisor
Country
Admission_Cycle
Recruitment_Status
Funding_Status
Application_Deadline
Research_Fit_Score
Official_URL
First_Seen
Last_Seen
```

### Events

```text
Record_ID
Event_Name
Event_Type
Edition_Year
Country
City
Start_Date
End_Date
Submission_Deadline
Registration_Deadline
Research_Relevance
Priority_Score
Official_URL
First_Seen
Last_Seen
```

### Watchlist

```text
Record_ID
Organization
Category
Country_or_Region
Priority
Research_Focus
Official_Website
Monitoring_URL
Source_Type
Monitoring_Status
Adapter_Status
```

### My_Feedback

```text
Record_ID
Preference       # Very Interested, Interested, Not Relevant, or blank
Saved            # independent Boolean
Hidden           # independent Boolean
Personal_Notes
Updated_At       # timezone-aware ISO timestamp
```

Duplicate feedback IDs are conflicts. Invalid preference, Boolean, or timestamp values are
reported and not loaded. Automated synchronization never updates these user-managed fields.

### Run_Logs

```text
Record_ID        # deterministic from Run_ID and category
Run_ID
Timestamp
Pipeline_Category
Execution_Status
Processed_Count
Inserted_Count
Updated_Count
Unchanged_Count
Error_Count
Error_Summary
```

### Change_Log

```text
Record_ID        # same value as Event_ID
Event_ID
Run_ID
Timestamp
Pipeline_Category
Opportunity_Record_ID
Change_Type      # NEW_OPPORTUNITY, UPDATED_OPPORTUNITY, STATUS_CHANGE,
                 # DEADLINE_CHANGE, or SALARY_CHANGE
Field_Name
Previous_Value
New_Value
```

`Event_ID` is derived from category, opportunity ID, change type, field, old value, and new value.
The append adapter ignores an already-present event ID, making retries idempotent.

## Synchronization rules

- Rebuild `Record_ID` to row-number mappings from every current worksheet read.
- Duplicate current or desired IDs are conflicts; never choose a winner silently.
- Preserve the sheet's existing `First_Seen`; update only changed agent-managed cells.
- Do not rewrite unchanged rows, delete rows, or close records missing from one run.
- Batch inserts, targeted updates, and append-only logs separately.
- A dry-run returns the complete plan and performs no adapter writes.
- An affected-sheet schema/conflict failure does not prevent other categories from syncing.
