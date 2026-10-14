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
  skills/career fit, and compensation. Research relevance is itself 55% domain fit, 25%
  methodological fit, and 20% research-question fit. The domain component is intentionally larger
  than either technical component, so generic AI or RL keywords cannot outrank direct cognition,
  brain, or behavior evidence. Unknown structured facts receive a documented neutral score;
  undisclosed salary never changes the research components.
- PhD opportunities use 70% research fit, 20% target-cycle fit, and 10% recruitment-evidence
  confidence. Potential and historical signals remain distinct from confirmed openings.
- Events use 60% research fit, 25% geographic priority, and 15% deadline relevance. Europe gets
  priority while North America and Australia remain eligible. Deadline scoring accepts a
  reference date so tests are deterministic.

Preference feedback creates a separate personalized score. `saved` does not alter any score;
`hidden` removes a record from visible ranking without deleting it.

`ScoreBreakdown.domain_fit` carries the five-valued domain classification independently of its
numeric component. Recommendation rules use that classification before generic title signals:
core evidence may be high priority, adjacent evidence may be relevant, transferable evidence stays
reviewable, low-fit evidence stays archived, and insufficient evidence requires review. Title
signals may identify obvious business or ambiguous roles but cannot manufacture scientific scope.

## Preference-bound incremental plans

An incremental plan payload contains proposed sheet operations, source observations,
recommendation decisions, domain classifications, and a canonical SHA-256 hash of the validated
research-interest and career-preference configuration. The plan fingerprint hashes that complete
payload. Any relevant preference change therefore invalidates a previously approved plan even
when source rows are unchanged.

Recomputing preferences reads cached records and is not collection. It never mutates observation
timestamps. Score-only or recommendation-only sheet proposals generate no source-content change
events.

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

The default urllib transport constructs a verified TLS context from the reproducible certifi
dependency because Python.org installations may have no linked default CA file. Certificate and
hostname verification remain mandatory. `SSL_CERT_FILE` is the sole explicit override for an
operator-provided, organization-approved CA bundle; the client never disables validation.

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
The narrowly authorized pilot initializer additionally compares the adapter's spreadsheet ID with
`GOOGLE_LIVE_PILOT_SPREADSHEET_ID` and rechecks the exact title before creating only missing
approved worksheets. The separately authorized initial sync uses the same identity gates, rebuilds
the plan immediately before writing, and compares it with fixed approved insert, provenance, and
recommendation counts. It prevalidates every planned ID as unique, non-fictional, officially
verified, provenance-valid, and `HIGH_PRIORITY` or `RELEVANT`. Once rows exist, the plan contains
unchanged records instead of the approved inserts, so the one-time path fails before writing.
General recurring live and production writes remain disabled.

## Incremental live-pilot planning

`prepare_incremental_live_sync` is the incremental module interface. It reuses the cached-live
loader, provenance audit, recommendation filter, Sheets planner, and adapter seam, then returns a
dry-run plan with a SHA-256 fingerprint. The fingerprint covers inserts, targeted updates,
unchanged IDs, conflicts, invalid records, deterministic change events, and pipeline failures; it
does not include the wall-clock plan-generation time. The same cached data and worksheet state
therefore produce the same approval identity.

The ignored JSON plan artifact retains enough expected and desired values to audit a later partial
failure. `reconcile_incremental_plan` rereads current rows by `Record_ID`, separates completed and
pending actions, flags concurrent values, and identifies missing deterministic Change_Log event
IDs. It never retries writes. The narrowly scoped score-reconciliation apply rebuilds the plan,
matches the separately approved fingerprint, requires the exact deliberate confirmation phrase,
revalidates target identity and provenance, and refuses unresolved conflicts. It additionally
requires exactly 13 job, one PhD, and one event update, restricts changed cells to approved score
columns, and refuses inserts, watchlist writes, or Change Log events. General incremental and
production writes remain disabled.

Meaningful source-change events are field-aware. Titles, locations, qualifications, salary,
deadlines, recruitment/funding status, research fields, and conference dates are meaningful.
`Last_Seen`, score changes, career-stage/ranking changes, Sheet timestamps, feedback, serialization,
and whitespace-only differences may update their owned fields but do not create source-content
Change_Log events. `First_Seen` remains immutable.

Source observation state remains separate from opportunity status. A successful scan that omits a
record yields `NOT_OBSERVED_IN_LATEST_SUCCESSFUL_SCAN`; a failed, blocked, unsupported, or partial
source yields `SOURCE_TEMPORARILY_UNAVAILABLE`. Neither state may close an opportunity. Only an
observed, explicit source status can confirm active or closed state.

Change event IDs are deterministic over category, record, change type, field, old value, and new
value. Retrying the same plan therefore does not duplicate `Change_Log` rows. Run log IDs combine
run ID and category. Category planning/apply failures are isolated from sibling categories.

## Fresh official-source observation

`collect --fresh-observation` is the bounded second-observation boundary. Before network access it
copies all four current live snapshot files into a timestamped `data/history/` directory. The new
raw results are written separately under `data/observations/`; only after collection finishes are
they reconciled into `data/live/`. All three locations are ignored by Git.

Reconciliation matches only stable `Record_ID` values and emits `NEW`, `UNCHANGED`,
`CONTENT_CHANGED`, `OBSERVATION_ONLY_CHANGED`, `NOT_OBSERVED`, `CONFIRMED_CLOSED`,
`SOURCE_UNAVAILABLE`, or `NEEDS_REVIEW`. Missing records are copied forward with their previous
facts and timestamps. A failed or partial source produces `SOURCE_UNAVAILABLE`; absence from a
successful bounded scan produces `NOT_OBSERVED`. Neither state changes opportunity status. Only a
fresh record carrying an explicit official closed status can produce `CONFIRMED_CLOSED`.

The Anthropic adapter keeps its 25-detail-request ceiling. It prioritizes up to 20 previously
tracked official job IDs and reserves up to five requests for new title-matched candidates. If
fewer new candidates exist, tracked records fill unused capacity. Metadata records the total board
population, title matches, selected detail requests, extracted records, and pipeline acceptances
separately. A tracked job omitted because of this cap is not closure evidence.

Meaningful comparison canonicalizes whitespace and excludes observation, sheet, ranking,
recommendation, and feedback metadata. A repeated observation advances `Last_Seen` and
`Source_Retrieved_At`, while `Content_Updated_At` is copied forward unless source content changes.
The local analysis includes deterministic prospective event IDs but a dry-run never appends them
to `Change_Log`.

## Configuration

Preferences and watchlist targets live in YAML. `research_radar.config` uses `yaml.safe_load` and
then validates the project schema. A configuration that merely looks correct is not accepted
until the parser and schema validation both succeed.

`source_expansion.yaml` separates implemented pilot adapters from verified future candidates. It
does not trigger collection by itself. Every entry has a stable source ID, category, official
HTTPS URL, and implementation state.

## Score reconciliation and informational source profiles

Live Sheets planning now forms its desired set from two independent sets: provenance-valid new
records approved for insertion, and provenance-valid IDs already present in the target worksheet.
The second set permits score refreshes after a preference revision without reopening the insertion
decision. Existing sheet `First_Seen` and `Last_Seen` values are copied into the planning model so
a cached recalculation cannot manufacture observation history.

`SourceCollectionResult.informational_profiles` carries verified, useful source entities that are
not actionable opportunities. The CMU adapter uses it for a programme profile when no admission
cycle is announced; the Neuroelectrics adapter uses it for general talent pools. These profiles are
stored in source metadata but never enter opportunity normalization, identity generation, ranking,
or Sheets insertion.

`build_combined_live_snapshot` creates a separate ignored preview directory from the immutable
current live snapshot plus one bounded source result. It rejects duplicate record or source IDs
and never mutates either input. This lets a failed source-health observation participate in an
incremental plan fingerprint without fabricating an opportunity or advancing unrelated source
timestamps.

## Scheduling design

`.github/workflows/weekly-monitoring.yml` separates offline validation from the authenticated
read-only monitoring job. The collection service still isolates the jobs, PhD, and events
pipelines so one source or category failure does not stop sibling processing. The intended weekly
trigger is:

```yaml
schedule:
  - cron: "0 9 * * 1"
    timezone: "Europe/Brussels"
```

The deployed workflow also retains `workflow_dispatch`. Scheduled starts are best-effort and may
be delayed. A future daily mode changes the cron expression to `0 9 * * *`. The workflow file is
the schedule's single source of truth. Concurrency prevents two runs for the same ref, job
timeouts bound cost, and no workflow command contains `--apply`.
The jobs are pinned to `ubuntu-24.04` during initial production operation. The concurrency group
uses `cancel-in-progress: false`, so a queued manual or scheduled run cannot terminate an active
GCS commit; the storage generation CAS remains the authoritative race safeguard.

Private-repository GitHub Free compatibility avoids GitHub Environment dependencies. The workflow
reads non-secret repository variables and checks the exact repository, `main` ref, and workflow
path before OIDC authentication. Google WIF must enforce the same repository, ref, and
`job_workflow_ref` claims; this preserves least privilege without environment claims or long-lived
keys.

`run_weekly_monitor` collects all six implemented adapters, builds an incremental Sheets dry-run,
and renders a private Markdown brief without feedback notes. It treats `SUCCESS_NO_MATCHES` as a
healthy source outcome and reports blocked or failed sources without converting them into closed
opportunities.

GitHub-hosted runners do not retain ignored local snapshots. Fourteen-day Actions artifacts are
review outputs, not durable state. `DurableStateBackend` now provides one restore/commit contract
implemented by a local filesystem adapter and an optional GCS adapter. Both use the existing four
snapshot files and the existing fresh-observation reconciler; no parallel opportunity database or
scoring path exists.

Snapshots and commit manifests are append-only. A commit writes and validates every immutable
object before replacing `current.json`. The local adapter uses an exclusive lock plus atomic
replace; GCS uses create-only object preconditions and a generation-matched pointer update. A stale
writer therefore leaves only non-authoritative orphan objects. Restore validates schema, stable-ID
uniqueness, per-file checksums, whole-state checksum, and pointer-to-manifest integrity, with a
reported fallback through a bounded 32-snapshot recovery history when newer commits are corrupt.
A subsequent commit records the snapshot actually restored as its base and rejects any base that
is absent from the generation-matched recovery history.

An empty backend is explicit bootstrap mode and is never auto-committed by a routine weekly run.
Partial source runs may advance state only when at least one source succeeds and reconciliation is
safe; unavailable-source records are copied forward with their previous facts and timestamps. The
hosted workflow explicitly selects GCS, verifies the authoritative schema-v2 baseline before
collection, and fails closed rather than using an empty runner directory. A validated successor is
committed with the restored pointer generation as a CAS precondition. Sheets and GCS use separately
scoped ADC credentials: `spreadsheets.readonly` and `devstorage.read_write`. See
`DURABLE_STATE_DESIGN.md` and `GCS_SETUP_PLAN.md`.

## Security

- Secrets are supplied through environment variables locally. GitHub uses OIDC and WIF rather
  than a stored Google credential.
- `.env`, credentials, tokens, private keys, local data, and logs are ignored by Git.
- Logs must not include credentials or raw secret-bearing responses.
- Ordinary tests inject mock services and require no Google credentials or network access.
- GitHub Actions authentication uses Workload Identity Federation through a dedicated service
  account shared on LIVE PILOT as Viewer. The workflow requests the Sheets read-only OAuth scope;
  local Mac OAuth behavior remains unchanged.
