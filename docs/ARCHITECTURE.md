# Architecture

## Design goals

ResearchRadar uses deterministic, testable modules with small interfaces. Network and storage
details sit behind adapters at explicit seams. Core processing accepts data and returns data so it
can be tested without credentials or live services.

## Planned flow

```text
YAML configuration
       │
       ├── PhD discovery ────────┐
       ├── Job discovery ────────┼──► normalize ─► deduplicate ─► score
       └── Event discovery ──────┘                         │
                                                          ▼
                                              storage synchronization
                                               │        │        │
                                             current  history   runs
```

The three discovery pipelines are isolated failure domains. They share domain models and pure
processing modules but not run success state.

## Modules

- `config`: the public interface for loading and validating user-editable YAML.
- `models`: domain records and state enums; optional facts remain `None`.
- `identifiers`: deterministic identifiers based on canonical source-owned fields.
- `discovery`: category-specific pipeline coordination.
- `collectors`: future source adapters for official pages, feeds, and search providers.
- `normalization`: converts source records into domain models without network access.
- `deduplication`: resolves exact identities and flags uncertain matches.
- `scoring`: deterministic, explainable category scoring.
- `personalization`: applies preference feedback and visibility policy.
- `storage`: future Google Sheets adapter and in-memory test adapter.
- `scheduling`: run modes and independent category execution.

Only the first three modules contain behavior in Milestone 1. The remaining packages establish
the approved source layout without pretending their later behavior exists.

## Seams and adapters

Future collectors will satisfy a shared collector interface only after at least two concrete
source mechanisms exist. Storage will have a real seam because Google Sheets and an in-memory
test adapter have distinct implementations. Ranking and normalization remain pure modules rather
than adapters.

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
- Milestone 1 requires no API keys.
