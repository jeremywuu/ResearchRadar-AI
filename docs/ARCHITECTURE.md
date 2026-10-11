# Architecture

## Design goals

ResearchRadar uses deterministic, testable modules with small interfaces. Network and storage
details sit behind adapters at explicit seams. Core processing accepts data and returns data so it
can be tested without credentials or live services.

## Local processing flow

```text
fictional JSON fixtures + YAML configuration
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
- `collectors`: local fixture loading now; live adapters arrive later.
- `normalization`: converts source records into domain models without network access.
- `deduplication`: resolves exact identities and flags uncertain matches.
- `scoring`: deterministic, explainable category scoring.
- `personalization`: applies preference feedback and visibility policy.
- `storage`: local JSON snapshots now; a Google Sheets adapter arrives later.
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

Future collectors will satisfy a shared collector interface only after at least two concrete
source mechanisms exist. `JsonOutputStore` is separate from processing, so a later Google Sheets
adapter does not change the pipelines. Ranking and normalization remain deterministic modules.

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
- Milestone 2 requires no API keys.
