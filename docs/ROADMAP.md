# Roadmap

Only one milestone is implemented at a time. Completion requires its acceptance criteria and
explicit approval before the next milestone begins.

## Milestone 0 — Product design

Status: complete.

- Product scope, watchlist, priorities, salary policy, feedback model, and schedule approved.

## Milestone 1 — Repository foundation

Status: complete.

- Initialize the local Git repository without a remote.
- Add product, architecture, roadmap, and schema documentation.
- Add validated YAML configuration.
- Establish a Python 3.11+ `src` layout and domain models.
- Add pytest and Ruff.
- Use synthetic tests only; make no live service calls.

Acceptance criteria:

- All four configuration files parse with a real YAML parser and pass schema validation.
- Watchlist contains the 38 approved targets with only P0/P1 priorities.
- Models preserve missing optional data and generate repeatable identifiers.
- Preference, bookmark, and visibility states remain independent.
- Configuration validation, pytest, and Ruff pass locally.
- No credentials, remote repository, deployment, scraping, Sheets, or LLM integration exists.

## Milestone 2 — Local deterministic pipelines

Status: complete.

- Implement PhD, job, and event pipelines against synthetic fixtures.
- Add normalization, exact deduplication, classification, and explainable scoring.
- Verify one pipeline's failure cannot prevent the other two from completing.
- Keep all execution offline and write structured snapshots to ignored local JSON files.

Acceptance criteria:

- All categories run together or independently through the CLI.
- Malformed records are reported without fabricating missing facts.
- Strong category identities deduplicate sources while preserving annual editions and cycles.
- Salary handling preserves disclosures and uses neutral treatment when salary is unavailable.
- Feedback, saved, hidden, first-seen, last-seen, and source attribution survive local updates.
- Synthetic tests, configuration validation, pytest, and Ruff pass locally.

## Milestone 3A — Google Sheets synchronization: offline foundation

Status: complete.

- Define seven explicit worksheet schemas and field ownership.
- Add dry-run, idempotent upsert planning and an in-memory Sheets adapter.
- Protect canonical feedback, saved, hidden, and personal notes.
- Add stable run/change logs, RAW cell writes, conflict detection, and category isolation.

Acceptance criteria:

- Manually sorted rows are matched by stable Record ID, not row position.
- Inserts, targeted updates, unchanged records, invalid records, and conflicts are reported.
- Duplicate IDs and invalid headers stop writes to the affected sheet.
- Dry-run performs no writes; retrying a plan creates no duplicate records or change events.
- Missing opportunities are neither deleted nor automatically closed.
- Feedback round-trips without changing research scores or losing user notes.
- Synthetic tests, configuration validation, pytest, and Ruff pass locally.

## Milestone 3B — Live Google Sheets adapter

- Add Google authentication and the concrete API adapter after explicit approval.
- Create or validate a real workbook and issue targeted RAW batch operations.
- Verify quotas, retries, permission errors, and partial-write recovery against a test spreadsheet.

## Milestone 4 — Initial official-source adapters

- Review access terms before implementing each adapter.
- Connect a small number of official sources for every category.
- Track adapter health separately from source verification and opportunity status.

## Milestone 5 — Discovery and personalization

- Add a configurable open-web search adapter.
- Apply feedback without treating saved or hidden as relevance signals.
- Retain controlled exploratory results.
- Record paid-call usage and enforce budgets.

## Milestone 6 — Automation and reliability

- Add weekly, daily, and manual GitHub Actions modes.
- Run all three categories independently on scheduled scans.
- Add retry, timeout, run summary, cost, and failure reporting.

## Later phases

- Reliable salary benchmarking and trends
- Skill-demand and company-hiring trends
- PhD career intelligence and industry pathways
- Weekly email digests and deadline alerts
