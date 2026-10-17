# Milestone 6.3B — BCI Job Radar production-style preview

## Outcome

The read-only preview verified two feasible official job feeds and one honest no-match source:

- `neuralink_careers_discovery`: `SUCCESS`; 80 current Greenhouse listings, six bounded role details, six accepted records.
- `precision_neuroscience_careers_discovery`: `SUCCESS`; ten current Kula listings, three bounded role details, three accepted records.
- `synchron_careers_discovery`: `SUCCESS_NO_MATCHES`; seven current first-party listings, no computational-neuroscience match, and one informational cognition-lab profile with an explicit no-current-openings statement.

The pilots remain outside `default_adapters()`. No production source, workflow, cloud object, spreadsheet, or external permission was changed.

## Historical baseline and preview boundary

On 2026-10-17, a read-only GCS pointer check confirmed that `current.json` still referenced snapshot `38888052294`. The previously verified local restore of that snapshot was independently validated against its manifest and used for comparison:

- checksum: `a14d959aa87842f1323a895b42774d53e78f3b84244c3bf0732a654c95cac7de`
- schema: 2
- records: 53 jobs, 1 PhD opportunity, 3 events (57 total)

The local account is not configured to impersonate the restricted runtime service account. Therefore, the pointer was checked live, but the full baseline was not downloaded again with the more privileged personal identity. This is a production-style local preview, not a fresh service-account restore and not a GCS commit.

## Current-index and provenance rules

`CONFIRMED_LISTED` requires both current-index membership and an official detail page. A surviving detail URL alone is `DETAIL_PAGE_ACCESSIBLE_ONLY`; a request failure is `SOURCE_UNAVAILABLE`, not closure. No official posting date was verified, so all nine roles are `NEW_TO_RADAR` with `UNKNOWN_POSTING_DATE`, never `NEWLY_POSTED`.

Neuralink's first-party careers page proves its current Greenhouse board relationship. The current board API returned 80 Neuralink records and the six selected IDs. Precision's first-party page links to the Precision-branded Kula index, whose structured identity names Precision and references the official careers page. Synchron's first-party index links to its organization-specific ADP surface; bounded normal HTTP could not retrieve usable ADP details.

Detailed evidence is recorded in [the live evidence dossier](research/milestone_6_3b_live_evidence.md).

## Verified jobs and fit assessment

| Record ID | Role | Score / domain | Role function | Career stage | Effective placement |
|---|---|---|---|---|---|
| `job_21e6f94d7c153e1c` | Neuralink Machine Learning Engineer Intern | 66.52 / adjacent | research-adjacent engineering | near-term internship or RA | research-adjacent / near-term |
| `job_39070100a7c32734` | Neuralink Neuroengineer Intern | 77.42 / adjacent | research-adjacent engineering | near-term internship or RA | research-adjacent / near-term |
| `job_92097157cd459124` | Neuralink Machine Learning Engineer | 57.00 / technical transferable | research-adjacent engineering | pre-PhD research engineering | needs review |
| `job_3aff5609cda2ae22` | Neuralink Neuroengineer, Next Gen | 79.02 / adjacent | research-adjacent engineering | pre-PhD research engineering | research-adjacent |
| `job_4a21f26a701be1a7` | Neuralink Signal Processing Engineer | 60.34 / technical transferable | research-adjacent engineering | pre-PhD research engineering | needs review |
| `job_6c74e9f3f683a363` | Neuralink Software Engineer, BCI Applications | 79.02 / adjacent | technical platform | transferable technical | transferable technical |
| `job_74e2213e3d51c59a` | Precision Full Stack Software Engineer | 79.02 / adjacent | technical platform | transferable technical | transferable technical |
| `job_5aca3b6096fc5989` | Precision DSP Algorithm Engineer | 67.02 / adjacent | research-adjacent engineering | pre-PhD research engineering | research-adjacent |
| `job_ca60fbb2ed102ea9` | Precision Senior Human Factors Engineer | 79.02 / adjacent | unknown | unknown | needs review |

This keeps four concepts separate: domain fit, role function, career stage, and application readiness. A high domain score does not establish present eligibility. The two Neuralink internships are the clearest near-term research paths. Neuralink Next Gen and Precision DSP are strong longer-term BCI method matches. The BCI Applications and Full Stack roles are product/platform work. Senior Human Factors is relevant to HCI methods, but the current general role gate conservatively leaves it in review rather than inventing a stronger classification.

## Requirements and eligibility boundaries

Precision states that it cannot consider remote workers or candidates who are not currently US-based and legally authorized to work in the United States. That is official role evidence; user eligibility remains unconfirmed. Neuralink's application asks authorization and future-sponsorship questions, but the postings do not establish a sponsorship policy. No such question is converted into a positive eligibility claim.

The final parser preserves hourly and annual salary evidence, explicit education alternatives, and stated experience. It also fixes two general extraction errors found in this preview: ATS slug acronyms now retain forms such as `DSP`, and substrings such as `15ms` or `minds` can no longer become false master's-degree requirements.

## Incremental comparison

Against the 57-record baseline:

- `NEW_TO_RADAR`: 9
- `CONTENT_CHANGED`: 0
- `OBSERVATION_ONLY_CHANGED`: 0
- `CONFIRMED_CLOSED`: 0
- duplicate `Record_ID`: 0
- semantic duplicates: 0

The hypothetical merged state would contain 62 jobs, 1 PhD opportunity, and 3 events (66 total). It was not committed. Existing timestamps and all prior records remain untouched.

## Hypothetical Sheets preview

An empty in-memory LIVE PILOT-shaped adapter produced six hypothetical job inserts, zero updates, zero conflicts, and fingerprint `9d7966d12eefbea33510c1f5932657254c50de9d07256def3c152e1d43274091`. Three valid canonical jobs were conservatively held from synchronization by effective `NEEDS_REVIEW` decisions: Neuralink Machine Learning Engineer, Neuralink Signal Processing Engineer, and Precision Senior Human Factors Engineer.

This is not a comparison with the actual LIVE PILOT workbook and is not authorization-ready. Its write-operation log remained empty. Google Sheets writes were zero.

## Anthropic bounded-selection audit

The proposed deterministic research-focused selector was evaluated with offline fixtures only. Compared with first-25/general-title behavior, it prioritizes research-domain and method signals, keeps stable candidate ordering, allocates coverage across relevant groups, and retains the same maximum of 25 detail requests. It reduces repeated low-value infrastructure candidates without increasing the network budget. The production Anthropic adapter was not changed.

## Production recommendation

1. **Neuralink: prepare for activation.** Its official Greenhouse feed is structured, stable-ID capable, evidence-rich, and bounded. Before deployment, approve the six-detail priority policy and review a production-style dry-run against the then-current GCS baseline.
2. **Precision Neuroscience: prepare for activation.** Kula is retrievable and exposes strong BCI signal-processing evidence plus explicit eligibility constraints. Preserve the exact index-membership requirement.
3. **Synchron: do not activate as a job-detail feed yet.** Retain as an informational/index-health candidate until normal bounded retrieval can obtain ADP details. `SUCCESS_NO_MATCHES` for the cognition lab is the correct current result.

Deployment requires a separate authorization to add approved source IDs behind a disabled feature flag, run a read-only cloud acceptance test, review canonical changes, and only then authorize a GCS successor. It must not imply a Sheets write.
