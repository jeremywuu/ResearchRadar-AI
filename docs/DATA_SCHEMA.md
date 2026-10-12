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
content_updated_at
retrieved_at
source_retrieved_at
adapter_source_id
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
official_source_url?
source_type?
source_evidence
extraction_method?
is_fictional
```

`first_seen_at` is the earliest observation. `last_seen_at` is the most recent successful
observation of that record. `content_updated_at` changes only when material source content changes;
observation time alone is not a content change. `source_retrieved_at` identifies the official
source retrieval that produced the cached record, while `adapter_source_id` links it to the source
metadata entry. `retrieved_at` is retained for backward compatibility and aliases the source
retrieval time when no separate value is supplied. Loading cached JSON does not change any of
these timestamps.

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
overall_starts_on?
overall_ends_on?
main_meeting_starts_on?
main_meeting_ends_on?
workshop_starts_on?
workshop_ends_on?
submission_deadline?
registration_deadline?
workshop_submission_deadline?
presenter_registration_deadline?
event_url?
```

A conditional presenter-registration deadline is not stored as the general registration
deadline. Workshop-proposal and abstract-submission deadlines also remain separate.
For multi-part conferences, `starts_on`/`ends_on` describe the overall event. Optional segmented
fields preserve main-meeting and workshop ranges without changing the existing Sheets columns.

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
`updated_at` is optional because a person may enter feedback directly without adding a timestamp;
an empty cell remains `None` and no timestamp is fabricated. Empty preformatted checkbox rows with
false Saved/Hidden values are template rows, not feedback records.

## Incremental plan and observation state

An ignored local incremental-plan artifact contains:

```text
version
plan_fingerprint
generated_at
target_environment
sheet inserts
sheet updates with expected values
unchanged Record_IDs
invalid records and conflicts
deterministic Change_Log rows
pipeline failures
```

The fingerprint is calculated from the canonical plan body, excluding `generated_at`. Recovery
reconciles current worksheet values with the artifact by `Record_ID`; row numbers are never used as
identity.

Observation state is monitoring metadata distinct from `Opportunity_Status`:

```text
CONFIRMED_ACTIVE
CONFIRMED_CLOSED
NOT_OBSERVED_IN_LATEST_SUCCESSFUL_SCAN
SOURCE_TEMPORARILY_UNAVAILABLE
UNKNOWN
```

The last three states preserve the previous opportunity status. Absence from one scan and source
failure are never evidence of closure.

## Processed output

Each category JSON snapshot contains a pipeline summary and a list of processed records. Every
record contains the normalized opportunity, score components and weights, final score,
personalized score, rank, exclusion state, processing status, and optional feedback. On rewrite,
the JSON adapter preserves the earliest first-seen timestamp and existing feedback when the new
input has no feedback. Generated snapshots live under Git-ignored `data/`.

Unknown source facts remain `null`; review flags identify actionable unknowns. The complete
bounded extracted input is retained in `original_values`, while normalized values occupy typed
fields. `is_fictional` distinguishes demo fixtures from live official-source records.

## Official source collection result

Each source result contains a `SourceDescriptor` and retrieval outcome:

```text
source_id
organization
category
official_source_url
retrieval_url
retrieval_method          # PUBLIC_API or OFFICIAL_HTML
verification_status       # official-source identity only
health                    # SUCCESS, SUCCESS_NO_MATCHES, PARTIAL, FAILED, BLOCKED, UNSUPPORTED
extraction_status         # SUCCESS, PARTIAL, FAILED, NO_MATCHES
retrieved_at
last_successful_retrieval_at?
records_fetched
records_considered
http_statuses
errors
records
```

These fields deliberately do not conflate official verification, functioning extraction, and
confirmed opportunity availability.

`records_fetched` is the source response population. `records_considered` is the bounded subset
selected for detailed extraction, so accepted Anthropic research candidates are never described
as the entire employer job market.

## Live review provenance and timestamps

Every live record proposed for Sheets must contain a stable ID, title, organization, category,
valid official source URL, timezone-aware source retrieval time, verified-official source state,
adapter source ID, source evidence, and `is_fictional=false`. Missing required provenance blocks
the proposed write. Missing salary, working language, education, or other optional facts remains
unknown and triggers review rather than fabrication.

`Sheet_Synced_At` is an execution fact, not a source observation. It is absent for dry-runs and
must never advance `Last_Seen`. The four source/content timestamps remain distinct:

- `First_Seen`: earliest successful source observation.
- `Last_Seen`: latest successful source observation.
- `Content_Updated_At`: latest material source-content change.
- `Source_Retrieved_At`: retrieval that produced the cached record.

Preference recalibration does not update any of these timestamps. A plan may still carry a
previously collected, unsynchronized observation timestamp, but that field must be identified as
source-observation state rather than a preference change.

## Research-fit assessment

Each processed score retains the user-facing aggregate and three transparent research components:

```text
research_relevance or research_fit
research_domain_fit
methodological_fit
research_question_fit
domain_fit  # CORE_DOMAIN_FIT, ADJACENT_DOMAIN_FIT, TECHNICAL_TRANSFERABLE,
            # LOW_DOMAIN_FIT, or INSUFFICIENT_EVIDENCE
```

The domain classification is rule-based personal metadata. It is not an official source fact and
is never stored as source evidence. Missing evidence remains `INSUFFICIENT_EVIDENCE`; it is not
converted into a negative qualification claim.

Incremental recovery artifacts additionally contain `preference_configuration_hash` and the
recommendation/domain decision for every reviewed record. These fields bind approval to the
validated preference configuration without altering stable Record IDs.

## Recommendation review

Recommendation is review metadata, not source evidence and not an opportunity status:

```text
record_id
category
classification  # HIGH_PRIORITY, RELEVANT, LOW_PRIORITY, NEEDS_REVIEW
explanation
```

The decision does not alter stable identity, source verification, pipeline career stage, score
components, or feedback. Only provenance-valid `HIGH_PRIORITY` and `RELEVANT` records enter the
live-pilot plan. `NEEDS_REVIEW` maps to `HOLD_FOR_REVIEW`; `LOW_PRIORITY` maps to `LOCAL_ARCHIVE`.
All four classes remain present in the local review report.

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

The live adapter rereads headers and the `Record_ID` row mapping immediately before applying a
plan. Existing agent-managed fields may be updated, but `First_Seen` is immutable and absent
incoming records are neither deleted nor marked closed. `Last_Seen` changes only when processing
input contains a newer observation. Google Sheets row positions are not identities.

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
Preformatted rows with no `Record_ID`, no preference, notes, or timestamp, and unchecked
`Saved`/`Hidden` boxes are blank templates: they are ignored rather than loaded or reported as
invalid. Any meaningful value on an ID-less row remains an error.

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

`Processed_Count` retains the Milestone 3 sheet meaning (records passed to the category pipeline).
To preserve the deployed worksheet schema without a destructive migration, `Error_Summary`
contains explicit labeled subcounts for `fetched`, `accepted`, validation `rejected`, intentional
`excluded`, `source_extraction_errors`, `pipeline_errors`, and `synchronization_errors`, followed
by bounded error details. `Error_Count` sums technical errors and validation rejections; it does
not count intentional relevance or language exclusions.

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
A `Last_Seen`-only observation update is not a meaningful content change and creates no event.
The append adapter ignores an already-present event ID, making retries idempotent.

## Synchronization rules

- Rebuild `Record_ID` to row-number mappings from every current worksheet read.
- Duplicate current or desired IDs are conflicts; never choose a winner silently.
- Preserve the sheet's existing `First_Seen`; update only changed agent-managed cells.
- Do not rewrite unchanged rows, delete rows, or close records missing from one run.
- Batch inserts, targeted updates, and append-only logs separately.
- A dry-run returns the complete plan and performs no adapter writes.
- An affected-sheet schema/conflict failure does not prevent other categories from syncing.

## Fresh observation comparison artifact

Each timestamped raw observation may include `observation_analysis.json` with one entry per stable
record:

```text
record_id
category
organization
title
status                 # NEW, UNCHANGED, CONTENT_CHANGED, OBSERVATION_ONLY_CHANGED,
                       # NOT_OBSERVED, CONFIRMED_CLOSED, SOURCE_UNAVAILABLE, NEEDS_REVIEW
changed_fields[]       # field name plus previous/current source values
official_url?
previous_observed_at?
current_observed_at?
source_id?
reason
event_id?              # deterministic prospective ID; not an appended Change_Log row
```

Fresh source metadata additionally distinguishes `records_fetched` (complete listing population),
`records_matched` (title-filter matches), `records_considered` (bounded detail requests), extracted
records, and accepted records. Reconciled snapshots copy forward unobserved records rather than
deleting them. Their previous `First_Seen`, `Last_Seen`, content, status, scores, and feedback remain
unchanged.

## Informational source profiles

`SourceCollectionResult.informational_profiles[]` stores verified source entities that must not be
normalized as active opportunities. Each profile is source-specific but must include a
`profile_type`, an official URL, verification state, and explicit actionable/non-actionable state
when applicable. Examples are a PhD programme profile with no announced cycle and a general talent
pool. Informational profiles contribute to source review but not opportunity or Sheets row counts.

## Recalibration update ownership

For records already present in opportunity worksheets, agent-managed score cells may be updated
regardless of current recommendation class. This exception does not admit new low-priority rows.
Score-only changes exclude `First_Seen`, `Last_Seen`, official source fields, and user feedback, and
produce no source-content change event.

Conference-wide `Start_Date` and `End_Date` are sufficient for ordinary conference provenance.
The additional overall/main-meeting/workshop date segments are required only for COSYNE because
that source explicitly distinguishes those intervals. A CCN edition is not provenance-blocked for
lacking COSYNE-specific workshop segmentation.
