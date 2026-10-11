# ResearchRadar AI agent instructions

## Objective

Build an evidence-based personal system for monitoring PhD opportunities, research-oriented
industry jobs, and academic or industry events. Work only within the currently approved
milestone.

## Non-negotiable rules

- Preserve source URLs, original evidence, and observation timestamps.
- Represent unknown facts as missing or review-needed; never invent vacancies, salary,
  funding, deadlines, eligibility, language requirements, or recruitment status.
- Keep official-source verification, adapter health, and opportunity availability as separate
  states.
- Keep preference feedback separate from `saved` and `hidden`; hiding retains history.
- Keep credentials in environment variables or GitHub secrets and out of Git, logs, fixtures,
  and Google Sheets.
- Prefer deterministic processing. Paid calls and new dependencies require explicit approval.

## Engineering workflow

1. Read `docs/PRD.md` when changing product behavior, ranking, source policy, or MVP scope.
2. Read `docs/ARCHITECTURE.md` when adding a module, interface, adapter, or external dependency.
3. Read `docs/DATA_SCHEMA.md` when changing models, YAML fields, identifiers, Sheets columns,
   feedback, or history behavior.
4. Read `docs/ROADMAP.md` before starting work and stop at the active milestone.
5. Add or update behavior-focused tests, make the smallest implementation change, then run
   configuration validation, pytest, and Ruff.

## Coding conventions

- Target Python 3.11+ with a `src` layout and type hints on public interfaces.
- Use small interfaces around meaningful seams; add an adapter only when behavior actually
  varies.
- Keep network access outside normalization, identity, scoring, and personalization modules.
- Keep user preferences in YAML rather than Python constants.
- Use timezone-aware timestamps and `None` for missing optional facts.
- Match existing names and avoid unrelated refactors.

## Completion criteria

Every change must have traceable requirements, passing relevant tests, valid configuration,
clean Ruff checks, and an explicit report of anything not verified.
