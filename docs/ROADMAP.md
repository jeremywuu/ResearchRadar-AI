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

### One-time scoring reconciliation

Status: complete; only the separately approved LIVE PILOT score cells were written.

- Rebuilt the approved plan immediately before writing and matched fingerprint
  `735889b24307eca84a9a35f97a95a5922b45e28461a4621875aa73bb94cad9ae`.
- Updated personalized scores for 13 existing jobs, one PhD record, and one event while refusing
  inserts, watchlist changes, feedback writes, and source-content Change Log events.
- Preserved all record IDs and source timestamps. The post-write dry-run reported 13/1/1
  opportunities and 38 watchlist rows unchanged, with zero inserts, updates, invalid records, or
  conflicts.

## Milestone 5 — Discovery and personalization

- Add a configurable open-web search adapter.
- Apply feedback without treating saved or hidden as relevance signals.
- Retain controlled exploratory results.
- Record paid-call usage and enforce budgets.

## Milestone 5A — GitHub Actions weekly automation infrastructure

Status: complete; the private repository is deployed with manual dispatch only. The first
GitHub-hosted read-only smoke test completed successfully through OIDC/WIF.

- Add Monday 09:00 Europe/Brussels scheduling plus manual dispatch.
- Separate offline tests from authenticated, read-only source collection and Sheets planning.
- Use OIDC/WIF-compatible ADC with the Sheets read-only scope while preserving local OAuth.
- Generate a Markdown brief, job summary, and private 14-day review artifact.
- Isolate source failures, bound runtime, prevent concurrent runs, and omit every Sheets apply path.
- Explicitly report missing durable state rather than fabricating cross-run change history.

Acceptance requires local workflow/schema tests, pytest, Ruff, configuration validation, and a
manual review of the workflow before any repository or Google Cloud setup.

## Milestone 5B.1 — Secure repository deployment

Status: complete; the audited history is on private `jeremywuu/ResearchRadar-AI` at `main`.

- Keep the first deployed workflow manual-only while WIF is unconfigured.
- Use GitHub Free-compatible repository variables rather than private-repository Environments.
- Bind future OIDC trust to the exact repository, `main` branch, and workflow file.
- Audit tracked files and complete Git history before configuring the sole approved remote.
- Push only to `jeremywuu/ResearchRadar-AI` after confirming that it exists, is private, and empty.

## Milestone 5B.2/5B.3 — Google Cloud WIF and first hosted smoke test

Status: complete for the read-only pilot.

- Reuse project `researchradar-ai` and record its verified project number.
- Anchor trust to immutable GitHub repository and owner IDs plus the exact `main` ref and
  `workflow_ref` claim.
- Create no persistent key and grant only repository-scoped `roles/iam.workloadIdentityUser` on a
  dedicated service account.
- Share only LIVE PILOT as Viewer and retain the Sheets read-only OAuth scope.
- Keep the workflow manual-only and perform no cloud, IAM, Sheets, or GitHub Actions mutation
  during preflight.

## Milestone 5C.1A — Durable state architecture and local implementation

Status: complete; local and GCS adapters share the validated schema-v2 contract.

- Add one immutable snapshot contract with filesystem and GCS adapters.
- Validate schemas, stable IDs, deterministic serialization, and layered checksums.
- Commit immutable snapshot objects before a generation-guarded current pointer.
- Recover from corrupt newer commits using a bounded verified predecessor history.
- Preserve unavailable-source history and reject unsafe or all-failed state advancement.
- Keep empty state in explicit bootstrap mode; never auto-upload a first baseline.
- Correct semantic deadline reporting and isolate accepted counts per source.
- Kept the hosted workflow stateless until bucket location, IAM, and migration were approved.

## Milestone 5C.1B — GCS security and bootstrap preflight

Status: complete; the private europe-west1 bucket, conditional IAM, and reviewed bootstrap exist.

- Select `europe-west1` Standard with uniform access, enforced public-access prevention, seven-day
  soft delete, disabled versioning, and no completed-object deletion lifecycle.
- Correct runtime IAM to prefix-conditioned object get/create plus exact-pointer-conditioned object
  delete; metadata update and object list are not required.
- Bind pointer downloads to the observed generation and retain a bounded multi-generation recovery
  chain.
- Preserve correct commit lineage after fallback by recording the snapshot actually restored as
  the new commit's base.
- Reconcile the 32-record local history, 15 LIVE PILOT records, and first hosted structured
  artifact into a proposed 33-record schema-v2 bootstrap snapshot.
- Keep the proposed bootstrap manifest and downloaded cloud evidence in Git-ignored review data.
- Require separate approval for bucket creation, IAM, bootstrap upload, workflow integration, and
  every hosted validation run.

## Milestone 5C.2A — GitHub Actions durable-state integration

Status: complete; two independent hosted state-commit runs and a Node.js 24 compatibility run
restored and advanced the authoritative GCS state successfully.

- Restore the authoritative GCS baseline before any official-source collection.
- Fail closed on missing configuration, authentication, state, schema, or checksum failures.
- Request separate read-only Sheets and read/write durable-state OAuth scopes through WIF ADC.
- Commit only validated reconciled snapshots using immutable objects and pointer-generation CAS.
- Keep all Google Sheets operations read-only.

## Milestone 5C.3 — Weekly monitoring production activation

Status: complete; Monday 09:00 Europe/Brussels monitoring is active with manual dispatch retained.

- Pin both jobs to `ubuntu-24.04` and use Node.js 24-compatible official Actions.
- Serialize manual and scheduled runs without cancelling an active GCS commit.
- Preserve restore-first operation, immutable snapshots, generation CAS, and Sheets read-only mode.
- Generate a private 14-day Weekly Brief artifact and GitHub job summary for every run.
- Treat scheduled starts as best-effort and review the runner pin during future maintenance.

## Milestone 6 — Automation and reliability

- Add an approved durable snapshot backend before claiming reliable hosted change detection.
- Verify the first private GitHub-hosted read-only run and measure actual usage.
- Consider daily mode only after weekly reliability and cost are understood.

## Milestone 6.1A — Research opportunity source discovery and validation

Status: implemented locally; production activation is not authorized.

- Review 15 first-party PhD, BCI/neurotechnology, and event sources using domain relevance rather
  than raw opportunity counts.
- Keep programme, lab, faculty, opening, cycle-announcement, and funding entities distinct.
- Add review-only CMU Neural Computation, Paradromics, and RLDM 2027 pilot adapters outside the
  production source registry.
- Preserve Fall 2028 uncertainty, honest no-match results, ATS provenance, bounded retrieval, and
  existing scoring behavior.
- Propose a research-first Weekly Brief structure without changing the production report.

Acceptance evidence:

- The project client retrieved CMU PNC, Paradromics/JazzHR, and RLDM successfully with robots and
  TLS verification; UCL Gatsby, UCL Gatsby-SWC, and Princeton returned HTTP 403 and remained
  blocked without bypasses.
- CMU emits one `PHD_PROGRAM_PROFILE` and zero opportunities because no Fall 2028 cycle is stated.
- Paradromics found nine jobs, considered three evidence-bearing candidates, and extracted three
  BCI/neural-data roles without requesting an unrelated mechanical role.
- RLDM 2027 preserves July 6–9 in Paris and the January 20, 2027 AoE abstract deadline as distinct
  event facts.
- All pilot sources remain disabled for production; weekly scheduling, GCS state, Sheets, and IAM
  are unchanged.

## Milestone 6.1B — Research source production preview

Status: complete locally; production activation remains unauthorized.

- Restore the current 48-record authoritative GCS snapshot through the read-only backend.
- Collect only CMU Neural Computation, Paradromics, and RLDM into an ignored isolated preview.
- Compare stable and semantic identities without committing a snapshot.
- Audit research-role function separately from domain fit and recommendation priority.
- Read LIVE PILOT and build a hypothetical dry-run with no Google Sheets writes.
- Keep all pilots outside `default_adapters()` and preserve the active production schedule.

Acceptance evidence:

- GCS snapshot `38565510105` restored with the expected checksum, generation, schema, and 45/1/2
  counts; the pointer remained unchanged.
- Paradromics returned nine listings and three verified roles: clinical implementation, technical
  platform, and research-adjacent BCI decoding engineering.
- RLDM retained its stable ID, Paris dates, and January 20 AoE abstract deadline with no duplicate.
- CMU remained one informational programme profile and zero open Fall 2028 opportunities.
- The Sheets dry-run proposed three job and one event inserts with zero updates, invalid records,
  conflicts, GCS writes, or Sheets writes.

## Milestone 6.1C-A — Research-role fit and source activation preparation

Status: implemented locally; source activation and push remain unauthorized.

- Add a responsibility-evidence role-function gate without changing scoring weights or Domain Fit.
- Preserve base recommendation while deriving a conservative effective recommendation and Weekly
  Brief placement.
- Hold clinical implementation and unknown roles for review; separate research-adjacent and
  technical-platform roles.
- Prepare RLDM and Paradromics activation flags while keeping both outside `default_adapters()`.
- Keep CMU Neural Computation as an informational programme watch, not an open PhD feed.
- Preserve schema-v2 GCS compatibility and perform only read-only baseline verification.

## Milestone 6.1C-B — Controlled research-source deployment

Status: implementation complete; the production feature flag remains disabled pending a separate
cloud-run authorization.

- Add Paradromics and RLDM to the existing production registry only when
  `RESEARCH_RADAR_RESEARCH_SOURCES_ENABLED` is explicitly true.
- Preserve the original six-source registry exactly when the flag is absent or false.
- Keep CMU Neural Computation informational-only and outside the opportunity feed in both modes.
- Preserve all three valid Paradromics canonical records while holding the clinical implementation
  role from automatic Sheets admission and Top Research Matches.
- Keep Google Sheets read-only, GCS schema v2 unchanged, and the Monday 09:00 Europe/Brussels
  schedule intact.

## Milestone 6.1D — Reporting fixes and permanent research-source activation

Status: complete; Paradromics and RLDM are permanently enabled through the production repository
variable while CMU Neural Computation remains informational-only.

- Distinguish first ResearchRadar observation (`NEW_TO_RADAR`) from source-evidenced recent
  publication (`NEWLY_POSTED`) and preserve unknown posting dates without inference.
- Group PhD records by evidenced admission cycle so the historical Gatsby 2027 record cannot
  appear as a confirmed Fall 2028 opening.
- Surface official experience requirements while keeping immediate eligibility and work
  authorization unknown unless separately verified.
- Preserve the research-role gate, the original numerical scores and Domain Fit, schema-v2 GCS
  history, read-only Sheets behavior, and the existing weekly schedule.
- Enable exactly Paradromics and RLDM in addition to the original six production adapters; keep
  CMU's programme profile outside the opportunity feed.

## Later phases

## Milestone 6.3A — Industry Research Job Discovery & Career Fit

Status: complete on an isolated local branch; production activation is unauthorized.

- Verify first-party careers-to-ATS ownership for Neuralink, Precision Neuroscience, Synchron,
  Blackrock Neurotech, Paradromics, and Neuroelectrics.
- Add disabled Neuralink, Precision, and Synchron pilots with bounded retrieval and current-index
  proof; preserve honest no-match and unavailable outcomes.
- Derive career-stage fit and application readiness independently from role function, domain fit,
  scoring, and work-authorization evidence.
- Treat Meta AI and Google DeepMind neuroscience publications as research-team profiles, never as
  vacancies.
- Audit Anthropic's bounded candidate selection offline without changing the live adapter.
- Preserve the eight-source production registry, weekly workflow, GCS schema v2, and read-only
  Google Sheets behavior.

## Milestone 6.3B — BCI Job Radar production-style preview

Status: complete on the isolated Job Radar branch; production activation is unauthorized.

- Revalidate Neuralink and Precision through their current first-party-linked ATS indexes and
  retain Synchron as an honest no-match informational/index-health source.
- Preserve current-index membership separately from detail-page accessibility and never infer a
  posting date from ATS modification metadata.
- Compare nine canonical pilot jobs with the verified 57-record historical baseline without a GCS
  commit or Google Sheets write.
- Keep domain fit, role function, career stage, application readiness, and official eligibility
  constraints independent in the Job Radar preview.
- Leave all three pilots outside `default_adapters()` until a separately authorized production
  deployment and cloud acceptance run.

- Reliable salary benchmarking and trends
- Skill-demand and company-hiring trends
- PhD career intelligence and industry pathways
- Weekly email digests and deadline alerts
