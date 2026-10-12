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

Status: complete.

- Add Google authentication and the concrete API adapter after explicit approval.
- Create or validate a real workbook and issue targeted RAW batch operations.
- Verify quotas, retries, permission errors, and partial-write recovery against a test spreadsheet.

Acceptance criteria:

- Mocked tests cover authentication errors, initialization, retries, targeted RAW writes,
  sorting races, feedback preservation, and read-only status without credentials.
- Live commands use only `GOOGLE_SPREADSHEET_ID`; writes require explicit `--apply`.
- Synthetic writes are refused unless `RESEARCH_RADAR_SHEETS_ENV=test`.
- Authentication, reviewed dry-runs, first TEST writes, repeated sync, and feedback round-trip are
  verified before the milestone commit is created.

Completion evidence:

- The dedicated TEST spreadsheet accepted 9 jobs, 6 PhD opportunities, 6 events, and 38
  watchlist targets with unique stable IDs and preserved source URLs.
- Repeated live synchronization inserted no duplicates, preserved `First_Seen`, and produced
  unique change events for intentional `Last_Seen` observation updates.
- A synthetic job feedback row survived synchronization with preference, saved, hidden, and notes
  intact while its base research relevance remained unchanged.
- All seven schemas and the opt-in read-only live integration test passed.

## Milestone 4A/4B — Initial official-source adapters and bounded collection

Status: complete.

- Review access terms before implementing each adapter.
- Connect a small number of official sources for every category.
- Track adapter health separately from source verification and opportunity status.
- Store real records only in ignored local JSON; do not synchronize them to Sheets yet.
- Keep Anthropic detail retrieval bounded, report UCL access challenges as `BLOCKED`, and read
  only robots-permitted COSYNE public HTML.

Acceptance criteria:

- Anthropic, UCL Gatsby, and COSYNE adapters use verified official source relationships.
- Mocked/recorded tests cover success, no matches, malformed content, access failures, retries,
  evidence, dates/cycles, deduplication, repeat observations, and category isolation.
- `Last_Seen`-only updates do not create content-change events; material changes update
  `Content_Updated_At`.
- CLI collection requires explicit `--live`, writes only under ignored `data/live/`, and never
  writes to Google Sheets.
- A bounded live smoke test reports actual results without bypassing blocked access.

Completion evidence:

- Final bounded retrieval succeeded for the verified Anthropic Greenhouse API, UCL Gatsby public
  programme page, and COSYNE public HTML pages.
- The run observed 645 Anthropic board entries, requested details for the bounded 25-title
  candidate set, and accepted 25 records; these volatile counts are observations, not fixtures.
- UCL yielded one confirmed 2027 programme record; COSYNE yielded one distinct 2027 event with
  abstract, workshop-proposal, and conditional presenter-registration deadlines kept separate.
- A repeated observation preserved `First_Seen` and `Content_Updated_At` while advancing
  `Last_Seen`; record IDs remained unique.

## Milestone 4C.1 — Verified live-data Sheets review

Status: complete.

- Load only cached, non-fictional records from `data/live/`; no source refresh is implied.
- Reuse the existing category pipelines and Sheets planner.
- Audit required provenance and separate facts, normalization, rule interpretations, and unknowns.
- Keep synthetic TEST, live pilot, and future production targets explicitly incompatible.
- Produce an ignored Markdown review report and an offline dry-run when no pilot is configured.
- Disable every live-data `--apply` path for this milestone.

Acceptance criteria:

- The 25 Anthropic jobs, one UCL Gatsby PhD programme, and one COSYNE edition retain stable IDs,
  source evidence, and cached observation timestamps.
- COSYNE overall, main-meeting, and workshop dates and its distinct deadlines remain separate.
- Provenance-blocked records cannot enter a proposed Sheets write; optional unknowns remain review
  flags and are never invented.
- Source coverage reports returned, considered, extracted, and accepted counts separately.
- The offline live preview proposes changes without Google credentials or writes and saves a
  human-readable review report under ignored local data.
- Automated tests cover environment rejection, timestamp behavior, feedback preservation,
  provenance, coverage, conference dates, and dry-run safety.

## Milestone 4C.2 — Live pilot preparation and data-quality review

Status: complete. Worksheet initialization was separately authorized and completed.

- Add YAML-configured deterministic recommendation classifications and explanations.
- Keep source validity, opportunity facts, career stage, scoring, and personal relevance separate.
- Propose Sheets actions only for provenance-valid `HIGH_PRIORITY` and `RELEVANT` records.
- Hold `NEEDS_REVIEW`; retain `LOW_PRIORITY` in the local archive.
- Validate the dedicated workbook ID, exact LIVE PILOT title, and `live-pilot` environment.
- Permit only read-only status, initialization dry-run, and synchronization dry-run.

Acceptance evidence:

- The 27-record review reports 8 high-priority, 7 relevant, 6 needs-review, and 6 low-priority
  records; the proposed empty-workbook plan contains 15 opportunities.
- Recruiter, counsel, sales, political-advocacy, recruiting, and GTM title signals are classified
  low priority without changing their verified-source state or deleting their records.
- PhD-required research roles remain eligible future career targets.
- The provided LIVE PILOT workbook passed authentication, environment, and exact-title checks.
- Read-only inspection found all seven approved worksheets missing; initialization requires a
  separately authorized `--apply`.
- The authorized initializer created exactly the seven approved worksheets with valid headers,
  formatting, filters, and feedback controls; existing sheets and data were not deleted.
- The post-initialization live dry-run matched the offline plan: 13 jobs, one PhD programme, one
  event, and 38 watchlist targets proposed; all invalid/conflict counts were zero.
- A final status read found zero opportunity, watchlist, feedback, run-log, and change-log records.
  Initial live synchronization required separate authorization.

## Milestone 4C.3B — First verified LIVE PILOT synchronization

Status: complete. General recurring live writes remain disabled.

- Rebuild and validate the exact approved plan immediately before the one authorized write.
- Require 13 jobs, one PhD opportunity, one event, 38 watchlist rows, zero invalid records and
  conflicts, 27 valid provenance audits, and the approved recommendation distribution.
- Reject fictional, provenance-blocked, `NEEDS_REVIEW`, and `LOW_PRIORITY` opportunity records.
- Read back the workbook and perform a dry-run-only idempotency check after the write.

Acceptance evidence:

- The LIVE PILOT workbook contains 13 jobs, one PhD opportunity, one event, and 38 watchlist rows.
- All 15 opportunity IDs are non-empty and unique, and all 15 official URLs use HTTPS.
- The workbook contains three run logs and 15 unique new-opportunity change events.
- `My_Feedback` contains no feedback records or validation conflicts; 1,999 formatted template rows
  remain ignored and unchanged.
- The post-write dry-run reports zero inserts and updates, with 13/1/1 opportunities and 38
  watchlist rows unchanged.
- The initial apply path now rejects a second invocation before writing; future recurring live
  synchronization requires a new authorization and design review.

## Milestone 4C.4 — Feedback round-trip and incremental live sync

Status: complete. Incremental apply remains disabled.

- Load canonical user feedback, accept an omitted feedback timestamp as unknown, validate linkage,
  and count ignored checkbox template rows.
- Build repeatable incremental plans with stable fingerprints and ignored recovery artifacts.
- Treat whitespace, timestamps, scoring, recommendation, and feedback changes separately from
  meaningful official-source changes.
- Preserve absent opportunities and distinguish not-observed from unavailable-source states.
- Reconcile partial outcomes by Record_ID, avoiding completed inserts and reporting missing
  deterministic history events or concurrent-value conflicts.
- Provide `sheets-sync --live --incremental --dry-run`; keep every incremental apply path disabled.

Acceptance criteria:

- Repeated cached synchronization proposes zero inserts and meaningful updates and preserves source
  observation timestamps.
- New records, material salary/status/date/content updates, Last_Seen-only observations, duplicate
  IDs, missing IDs, recommendation demotion, and partial failures have deterministic tests.
- Feedback preference, Saved, Hidden, and notes remain independent and untouched by planning.
- The authenticated LIVE PILOT check reads all seven valid schemas. The corrected feedback row is
  linked to `job_fd5e30f801bee750` with preference `Interested`, Saved true, Hidden false, and notes
  preserved. The accepted dry-run reported zero inserts, updates, conflicts, or invalid records.
- Pytest, Ruff, YAML validation, and the opt-in read-only Google integration test pass.

## Milestone 4D.1 — Fresh observation and real-world change detection

Status: complete after TLS repair and one bounded retry. No Google Sheets apply is authorized.

- Archive the prior verified live snapshot before any source retrieval.
- Perform one bounded read-only collection through each of the three existing official adapters.
- Compare stable IDs and separate content changes, observation refreshes, missing records, explicit
  closures, source failures, and review conflicts.
- Preserve unobserved history, source evidence, recommendation state, and user feedback.
- Generate an ignored human review report and a fresh read-only LIVE PILOT plan fingerprint.

Acceptance criteria:

- Anthropic detail requests remain capped at 25 while prioritizing tracked IDs and reserving new
  discovery capacity; coverage metrics do not imply full-market recall.
- `First_Seen` is stable, only observed records advance `Last_Seen`, and only material changes
  advance `Content_Updated_At`.
- Missing, capped, blocked, timed-out, partial, or parser-failed records are never inferred closed.
- New and materially changed records retain official evidence and deterministic prospective change
  IDs; dry-run creates no Sheets or Change_Log writes.
- The LIVE PILOT plan preserves canonical feedback and reports a new evidence-derived fingerprint.
- Offline tests, configuration validation, Ruff, and authenticated read-only checks pass.

Completion evidence:

- The prior 27-record snapshot was archived before the sole bounded collection attempt; the raw
  failed observation and comparison artifact were stored separately under ignored local data.
- TLS diagnosis found the Python.org 3.11 default CA file missing and its default context empty.
  The verified urllib transport now uses the declared certifi bundle while preserving certificate,
  hostname, timeout, and retry checks.
- One bounded retry observed 646 Anthropic board entries, matched 71 titles, requested 25 details,
  and accepted 25 jobs. COSYNE succeeded with one event. UCL completed TLS but returned HTTP 403
  and remained conservatively `BLOCKED`.
- Reconciliation found five new jobs, 21 observation-only refreshes, five bounded-cap omissions,
  one unavailable PhD source, zero material content changes, and zero confirmed closures.
- The authenticated LIVE PILOT plan proposes five job inserts, eleven job observation updates, and
  one event observation update, with zero invalid records or conflicts. No operation was applied.
- Canonical feedback remains linked to `job_fd5e30f801bee750` as `Interested`, Saved true, Hidden
  false, with notes preserved and 1,998 template rows ignored.
- Source health and retrieval evidence now participate in the plan fingerprint even when no cell
  write is proposed.

## Milestone 4D.2 — Computational cognitive neuroscience recalibration

Status: complete pending user review; no Google Sheets apply is authorized.

- Recenter research identity on computational questions about cognition, brain, and behavior.
- Split research relevance into domain, method, and research-question components while preserving
  the approved 45/25/20/10 outer job weights.
- Keep technical AI/ML opportunities discoverable without treating generic technical keywords or
  research titles as core-domain evidence.
- Re-evaluate all 32 cached official-source records without a new collection or source timestamp
  mutation.
- Bind incremental plan fingerprints to the validated preference configuration.

Acceptance evidence:

- Automated tests establish that cognition/neuroscience roles outrank unrelated AI algorithm
  roles, generic research-engineer titles do not imply core fit, cybersecurity RL is lower
  priority, and NeuroAI/neural-decoding evidence can qualify as core fit.
- The 32-record recalibration contains 0 core, 2 adjacent, 17 technically transferable, 11 low-fit,
  and 2 insufficient-evidence records. The absence of current core records reflects limited source
  evidence, not an inferred absence from the broader market.
- The authenticated LIVE PILOT dry-run proposes no job insert or update, one PhD score update, and
  one event score plus prior-observation update. It creates zero content-change events and performs
  no writes.
- The old fingerprint `24307790c4b460ffc13e521a144a63b05766658a8acce271b446411b23626e11`
  is stale. The recalibrated plan has a different preference-bound fingerprint and requires a new
  review before any write authorization.

## Milestone 4E — Scoring reconciliation and cognitive-neuroscience source expansion

Status: implementation complete; live pilot remained read-only. The separately authorized CCN
parser retry was attempted in Milestone 4E.1 and failed closed without emitting an event.

- Separate new-record recommendation admission from existing-row score maintenance.
- Refresh personalized scores for all 13 existing jobs without deleting low-priority history or
  changing source-observation timestamps.
- Add deterministic adapters for CCN 2027, the CMU Cognitive Neuroscience PhD programme profile,
  and Neuroelectrics' official Personio board.
- Store non-actionable programme and talent-pool evidence as informational profiles rather than
  fabricated opportunities.
- Add verified backlog entries for RLDM, Synchron careers, and OHBM without implementing them.

Verification evidence:

- The authenticated read-only LIVE PILOT plan proposes score-only updates for 13 jobs, one PhD
  record, and one event; it proposes no inserts, invalid records, conflicts, timestamp changes, or
  content-change events.
- CMU returned `SUCCESS_NO_MATCHES` with one programme profile and no announced Fall 2028 cycle.
  Neuroelectrics returned `SUCCESS_NO_MATCHES` with two talent-pool profiles and no specific
  relevant vacancy.
- The initial CCN smoke collection reached the official page but failed deterministic extraction
  because of page-layout variation. The parser was made layout-tolerant and covered by offline
  tests; no unapproved retry or synthetic opportunity was created.

## Milestone 4E.1 — CCN collection recovery and final synchronization review

Status: complete; no Google Sheets writes were performed.

- Retry only the official CCN 2027 adapter once with bounded read-only retrieval.
- Keep parser failure distinct from source verification and avoid fabricating a conference record.
- Combine the fresh CCN result with the existing local archive without mutating either input.
- Rebuild the LIVE PILOT score-reconciliation plan and verify deterministic fingerprints.

Verification evidence:

- The authorized CCN request completed but deterministic extraction still failed because the
  returned content did not expose the required edition dates and location in a supported layout.
  Source health is `FAILED`; zero event records were emitted.
- Offline scoring of the separately verified CCN facts classifies the conference as
  `CORE_DOMAIN_FIT`, but that profile is not sync-eligible without a successful live extraction.
- The authenticated read-only LIVE PILOT plan proposes 13 job, one PhD, and one event personalized
  score update; 38 watchlist rows are unchanged. It proposes no inserts, source-content changes,
  observation-only changes, invalid records, conflicts, or Change Log events.
- Repeated dry-runs over unchanged inputs produced the same preference- and target-bound plan
  fingerprint.

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
