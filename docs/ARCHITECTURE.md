# Architecture

## Design goals

ResearchRadar uses deterministic, testable modules with small interfaces. Network and storage
details sit behind adapters at explicit seams. Core processing accepts data and returns data so it
can be tested without credentials or live services.

## Local processing flow

```text
fictional fixtures or verified official adapters + YAML configuration
       │
       ├── PhD pipeline ─────────┐
       ├── Job pipeline ─────────┼──► validate ─► normalize ─► classify
       └── Event pipeline ───────┘                         │
                                                          ▼
                                      deduplicate ─► score ─► rank ─► JSON
```

The three discovery pipelines are isolated failure domains. They share domain models and pure
processing modules but not run success state.

## Modules

- `config`: the public interface for loading and validating user-editable YAML.
- `models`: domain records and state enums; optional facts remain `None`.
- `identifiers`: deterministic identifiers based on canonical source-owned fields.
- `pipelines`: independently executable category processing and failure-isolated orchestration.
- `discovery`: reserved for later open-web and source discovery policy.
- `collectors`: bounded read-only HTTP retrieval, source contracts, deterministic extraction,
  and live collection orchestration.
- `normalization`: converts source records into domain models without network access.
- `deduplication`: resolves exact identities and flags uncertain matches.
- `scoring`: deterministic, explainable category scoring.
- `personalization`: applies preference feedback and visibility policy.
- `storage`: local JSON snapshots, offline Sheets planning, and the live Google API adapter.
- `scheduling`: run modes and independent category execution.

Each category follows the same public stages while retaining category-specific normalization,
classification, identity, and scoring rules. Record-level validation errors produce a `PARTIAL`
report; an unhandled category failure produces `FAILED` without stopping sibling pipelines.

## Identity and deduplication

- Jobs use canonical organization plus official job ID when present. Otherwise organization,
  title, and location form a conservative fallback; title alone never merges jobs.
- PhD records use canonical university, official ID (or the strongest PI/lab/title reference),
  and admission cycle. Different cycles remain separate.
- Events use series name plus edition year (or start date when the year is unknown). Annual
  editions remain separate.

Only records sharing these strong, category-specific identity keys merge. Merging preserves the
earliest `first_seen_at`, latest `last_seen_at`, and all source URLs.

## Deterministic scoring

- Jobs use the approved 45/25/20/10 weights for research relevance, PhD-level research value,
  skills/career fit, and compensation. Unknown structured facts receive a documented neutral
  score; undisclosed salary never changes the research components.
- PhD opportunities use 70% research fit, 20% target-cycle fit, and 10% recruitment-evidence
  confidence. Potential and historical signals remain distinct from confirmed openings.
- Events use 60% research fit, 25% geographic priority, and 15% deadline relevance. Europe gets
  priority while North America and Australia remain eligible. Deadline scoring accepts a
  reference date so tests are deterministic.

Preference feedback creates a separate personalized score. `saved` does not alter any score;
`hidden` removes a record from visible ranking without deleting it.

## Seams and adapters

Official collectors satisfy `OfficialSourceAdapter`. `SourceDescriptor` records the verified
organization/source relationship and retrieval method; `SourceCollectionResult` independently
records adapter health, extraction status, HTTP outcomes, and extracted source records. A
verified source may be blocked, a working adapter may return no matches, and a returned record
still needs explicit source evidence before it can be classified as an active opportunity.

The initial mechanisms are Anthropic's employer-linked Greenhouse Job Board API and deterministic
HTML extraction for UCL Gatsby and COSYNE. HTTP is GET-only, uses a descriptive User-Agent,
timeouts, bounded retries, robots checks for HTML, and injected transports for offline tests.
No HTML or JSON content is executed or treated as agent instructions.

Storage is separated from processing. `JsonOutputStore` handles local
snapshots, while the `SheetsAdapter` interface defines worksheet reads, planned writes, and
append-only logs. `InMemorySheetsAdapter` supplies the offline implementation.
`GoogleSheetsAdapter` implements the same seam with the official API client without changing
pipeline or planner behavior.

## Offline Sheets synchronization

```text
PipelineReport ─► user-facing row mapper ─► sync planner ─► SheetSyncPlan
                                                    │
current worksheet ─► validate headers + rebuild ID map
                                                    │
                      dry-run ◄─────────────────────┤
                                                    ▼
                                  SheetsAdapter.apply_plan
                                  ├── targeted batch inserts
                                  ├── targeted batch updates
                                  ├── unique Change_Log append
                                  └── unique Run_Logs append
```

The planner is pure: it reads current rows and returns inserts, updates, unchanged IDs, invalid
records, conflicts, change events, and an operation estimate. It never relies on row order.
Duplicate IDs or header drift prevent writes for that sheet. Missing input records cause no
deletion or status change. `First_Seen` is never overwritten; `Last_Seen` advances only after a
successful source observation. `Content_Updated_At` advances only when material opportunity
content changes. A `Last_Seen`-only update may be synchronized but does not create a Change_Log
event.

## Live collection flow

```text
verified official source ─► bounded GET ─► deterministic extraction
                                            │
                                            ▼
source health + evidence ─► existing category pipeline ─► data/live/*.json
                                            │
                                            └────────────► source_metadata.json
```

Each category remains a separate failure domain. Local collection summaries distinguish fetched,
extracted, accepted, validation-rejected, intentionally excluded, source-extraction-error, and
pipeline-error counts. Intentionally irrelevant or language-incompatible records are exclusions,
not technical errors.

## Live-data review flow

```text
data/live/*.json + source_metadata.json
             │
             ▼
restore cached identity and observation timestamps
             │
             ▼
existing category pipelines ─► provenance audit ─► safe records only
                                                   │
                                                   ▼
                 empty in-memory workbook or explicit LIVE PILOT workbook
                                                   │
                                                   ▼
                                 dry-run Sheets plan + Markdown review report
```

`research-radar sheets-sync --live --dry-run` is the only enabled live-data Sheets command in
Milestone 4C.1. It never falls back to `GOOGLE_SPREADSHEET_ID`. A configured pilot uses
`GOOGLE_LIVE_PILOT_SPREADSHEET_ID`, requires `RESEARCH_RADAR_SHEETS_ENV=live-pilot`, and must
have the exact workbook title `ResearchRadar AI — LIVE PILOT`. Otherwise the command plans
against an empty in-memory workbook without Google credentials or network access.

The loader reconstructs records through the existing pipelines but then restores their stored
stable IDs and observation timestamps. Consequently, reading a cached snapshot does not advance
`Last_Seen` or manufacture a new source observation. The audit distinguishes source-stated facts,
normalized values, rule-based interpretations, and unknown fields. Blocking provenance defects
prevent a proposed write; important unknowns remain visible as manual-review flags.

Milestone 4C.2 adds a deterministic recommendation layer after provenance validation. The rules
are YAML-owned and return a classification plus an explanation without mutating source state,
pipeline classification, score components, or feedback. The planner receives only verified
`HIGH_PRIORITY` and `RELEVANT` records. Held and low-priority records remain in the full execution
report and ignored local archive, so a future rule change can reconsider them.

Opportunity sheets contain only agent-managed columns. `My_Feedback` is the canonical source for
preference, saved, hidden, and personal notes. Feedback is loaded into `UserFeedback` for later
personalization but is never included in an opportunity-sheet write plan.

All untrusted cell values use Google Sheets `valueInputOption=RAW`, so strings beginning with
formula characters remain literal data. Writes are batched by insert, update, and append type;
whole-sheet replacement is forbidden.

## Live Sheets adapter

`GoogleSheetsAdapter` discovers credentials through a separate authentication provider, scopes
access to the Sheets API, and opens only the spreadsheet named by `GOOGLE_SPREADSHEET_ID`.
Application Default Credentials are preferred; installed-app OAuth is an explicit local fallback.
Credential objects and configured credential paths are never logged.

Initialization validates workbook metadata and exact headers before creating only missing
approved worksheets. One structural batch adds headers, frozen rows, filters, basic formats, and
feedback validation. Existing worksheets and rows are never replaced or deleted.

Before an update, the adapter rereads the worksheet and confirms every planned row still contains
the expected `Record_ID`. A sort or edit between plan and write fails safely. Inserts are rechecked
against current IDs, logs use deterministic IDs, and transient 429/5xx/network failures use
bounded exponential backoff. Multiple API requests are not transactional: a data write can
succeed before a later log append fails, so partial success is reported accurately.

`RESEARCH_RADAR_SHEETS_ENV=test` is required for synthetic demo writes. Production mode refuses
demo writes. The dedicated pilot instead requires `RESEARCH_RADAR_SHEETS_ENV=live-pilot`,
`RESEARCH_RADAR_DATA_MODE=live`, and `GOOGLE_LIVE_PILOT_SPREADSHEET_ID`; it never falls back to the
TEST ID. Modifying CLI commands also require explicit `--apply`; dry-run and status do not write.

Change event IDs are deterministic over category, record, change type, field, old value, and new
value. Retrying the same plan therefore does not duplicate `Change_Log` rows. Run log IDs combine
run ID and category. Category planning/apply failures are isolated from sibling categories.

## Configuration

Preferences and watchlist targets live in YAML. `research_radar.config` uses `yaml.safe_load` and
then validates the project schema. A configuration that merely looks correct is not accepted
until the parser and schema validation both succeed.

## Scheduling design

The future GitHub Actions workflow will define three independent jobs: `scan-phd`, `scan-jobs`,
and `scan-events`, followed by an always-run summary job. The proposed weekly trigger is:

```yaml
schedule:
  - cron: "0 9 * * 1"
    timezone: "Europe/Brussels"
```

`workflow_dispatch` will provide manual execution. A daily mode changes the cron expression to
`0 9 * * *`. The workflow file will be the schedule's single source of truth.

## Security

- Secrets are supplied through environment variables locally and GitHub Secrets later.
- `.env`, credentials, tokens, private keys, local data, and logs are ignored by Git.
- Logs must not include credentials or raw secret-bearing responses.
- Ordinary tests inject mock services and require no Google credentials or network access.
- Future GitHub Actions authentication will use Workload Identity Federation rather than
  committed service-account keys.
