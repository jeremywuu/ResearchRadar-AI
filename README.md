# ResearchRadar AI

ResearchRadar AI is a personal academic and industry intelligence system for tracking:

- PhD programs, funded positions, supervisors, laboratories, and recruitment signals
- Research-oriented industry jobs and future career targets
- Academic conferences, workshops, exhibitions, and networking events

Milestone 4C.2 adds deterministic recommendation review and prepares a separate LIVE PILOT
workbook around the existing Google Sheets planner. Automated tests remain offline. Live records
cannot target the synthetic TEST workbook, and live-pilot writes remain disabled pending explicit
authorization.

## Requirements

- Python 3.11+
- Git

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,sheets]'
```

Google credentials are not required for the ordinary test suite. Follow
`docs/GOOGLE_SHEETS_SETUP.md` before using live commands; never commit `.env`, OAuth client files,
or cached tokens.

## Commands

Validate all YAML configuration with PyYAML and the project schema:

```bash
research-radar validate-config
```

The module form is equivalent:

```bash
python -m research_radar validate-config
```

Run all local demo pipelines, or one independently:

```bash
research-radar run-demo all --reference-date 2026-10-12
research-radar run-demo jobs
research-radar run-demo phd
research-radar run-demo events
```

Outputs are written to the Git-ignored `data/demo/` directory. Use `--output-dir` to change it
and `--project-root` when invoking the command outside the repository root.

Preview an offline synchronization against a mock, manually sorted workbook:

```bash
research-radar sheets-plan --demo --reference-date 2026-10-12
```

This is always a dry-run. It prints inserts, targeted updates, unchanged records, invalid rows,
conflicts, and estimated opportunity-sheet operations without writing any worksheet.

After configuring authentication, inspect the test spreadsheet without changing it:

```bash
research-radar sheets-status
research-radar sheets-init --dry-run
research-radar sheets-sync --demo --dry-run
```

Live writes always require `--apply`. Do not use it until the dry-run output has been reviewed.

Inspect the separately configured LIVE PILOT workbook without changing it:

```bash
export GOOGLE_LIVE_PILOT_SPREADSHEET_ID="<LIVE_PILOT_SPREADSHEET_ID>"
export RESEARCH_RADAR_SHEETS_ENV="live-pilot"
export RESEARCH_RADAR_DATA_MODE="live"

research-radar sheets-status --live
research-radar sheets-init --live --dry-run
research-radar sheets-sync --live --dry-run
```

`sheets-init --live --apply` is allowed only with the exact live data mode, live-pilot
environment, configured pilot ID, workbook title, and explicit flag. It creates only missing
approved worksheets. `sheets-sync --live --apply` remains disabled pending separate authorization.

Run tests:

```bash
pytest
```

Run lint checks and formatting verification:

```bash
ruff check .
ruff format --check .
```

Apply formatting when intentionally changing code:

```bash
ruff format .
```

## Configuration

- `config/watchlist.yaml`: organizations, laboratories, programs, and events
- `config/research_interests.yaml`: research interests and exploration policy
- `config/career_preferences.yaml`: geography, career stage, language, timing, and transparent
  recommendation rules
- `config/salary_rules.yaml`: job scoring weights and aspirational compensation flags

Watchlist membership is not evidence of a current opening. See `docs/PRD.md` for the
source-state distinctions that every future collector must preserve.

The committed `fixtures/demo/*.json` records use fictional organizations and reserved
`.example` domains. They are test inputs, never real opportunities.

## Documentation

- Product requirements: `docs/PRD.md`
- Architecture: `docs/ARCHITECTURE.md`
- Roadmap and acceptance criteria: `docs/ROADMAP.md`
- Domain and Google Sheets schema: `docs/DATA_SCHEMA.md`
- Google Cloud and Sheets setup: `docs/GOOGLE_SHEETS_SETUP.md`
