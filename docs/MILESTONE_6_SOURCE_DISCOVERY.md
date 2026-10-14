# Milestone 6.1A — Research Opportunity Source Discovery

## Scope and safety boundary

This milestone improves source quality without changing the active weekly source list. The review
registry is `config/source_discovery.yaml`; every entry has `activate_in_production: false`.
The three pilot adapters live in `research_radar.collectors.pilot` and are intentionally absent
from `collectors.service.default_adapters()`. No Google Sheets or GCS state was read or written,
and no GitHub Actions run was triggered.

The review was performed on 2026-10-14 with first-party pages only. Successful retrieval means
that the project HTTP client completed TLS and robots checks and received the page; it does not
mean an opportunity is open or relevant.

## Reviewed inventory

The full 15-source inventory is saved locally at
`data/review/milestone_6/source_inventory.csv` and mirrored in validated YAML. Summary:

| Status | Count | Interpretation |
|---|---:|---|
| `READY_FOR_PILOT` | 7 | Successful retrieval and a deterministic extraction path were demonstrated |
| `NEEDS_MANUAL_REVIEW` | 3 | Official page is reachable, but current jobs require a stable data-feed decision |
| `INFORMATIONAL_ONLY` | 2 | Useful programme evidence, not a current opening |
| `BLOCKED` | 3 | Normal project HTTP client received HTTP 403 |
| `UNSUITABLE` | 0 | No candidate was rejected as intrinsically unsuitable |

### PhD sources

- [CMU Ph.D. in Neural Computation](https://www.cmu.edu/ni/academics/grad/programs/phd-neural-computation)
  is the strongest immediately parsable programme profile. It explicitly covers computational
  neuroscience, quantitative methods, experimental neuroscience, and cognition. The page states a
  general December 1 deadline but does not identify a Fall 2028 cycle, so the pilot emits one
  `PHD_PROGRAM_PROFILE` and zero opportunities.
- [Princeton Neuroscience](https://gradschool.princeton.edu/academics/degrees-requirements/fields-study/neuroscience)
  is an exceptionally strong research match. Its first-party page states that the displayed
  deadline is for fall 2027 and describes computational modeling, decision-making, fMRI, MEG, and
  cognition. The project client received HTTP 403, so it remains `BLOCKED`; the indexed page is
  evidence for review, not a parser success.
- [Duke Cognitive Neuroscience](https://gradschool.duke.edu/academics/programs-degrees/cognitive-neuroscience/)
  was retrieved successfully. It provides cognitive-neuroscience programme structure, MRI, EEG,
  psychophysics, and a general December 1 deadline, but no explicit Fall 2028 announcement.
- [Yale Psychology admissions](https://psychology.yale.edu/graduate/admissions/admissions-application-overview)
  was retrieved successfully but is an admissions overview rather than evidence of a specific
  computational cognitive neuroscience opening. It remains informational until joined to
  first-party faculty/research-area evidence.
- [UCL Gatsby](https://www.ucl.ac.uk/life-sciences/gatsby/study-and-work/gatsby-unit-phd-programme)
  and the [GCNU-SWC joint programme](https://www.ucl.ac.uk/life-sciences/gatsby/study-and-work/gcnu-swc-joint-phd-programme)
  both returned HTTP 403 to the normal project client. The official pages describe the 2027 cycle,
  a 9 November 2026 deadline, and funding; none of that establishes Fall 2028 availability. No
  bypass was attempted. The historical UCL identity remains authoritative for the existing record.

### Industry sources

- [Paradromics careers](https://paradromics.com/careers/) was retrieved successfully and directly
  links its public JazzHR postings. This first-party relationship is the strongest current pilot.
- [Synchron careers](https://synchron.com/careers) was retrieved successfully and links its ADP
  postings. The New York Cognition Lab explicitly reports no current openings. That is a valid
  `SUCCESS_NO_MATCHES` condition for core cognition roles, not a source failure.
- [Neuralink careers](https://neuralink.com/careers/) was reachable, but the basic response is a
  JavaScript shell. A stable, authorized public job-data endpoint still needs verification.
- [Precision Neuroscience careers](https://www.precisionneuro.io/careers) was reachable, but
  individual open roles were not present in the basic HTML response.
- [Blackrock Neurotech careers](https://blackrockneurotech.com/careers/) was reachable and includes
  first-party recruitment-scam guidance, but its embedded individual role data was not available
  to the current deterministic HTML parser.

The company domain is never used as a relevance shortcut. A role needs role-level evidence of
neural signals, BCI, decoding, neuroscience, behavior, or cognitive research before receiving
domain priority.

### Event sources

- [RLDM 2027](https://rldm.org/) states July 6–9, 2027 at Maison de la Chimie in Paris. Its
  [official call for abstracts](https://rldm.org/call-for-abstracts-2027/) states a 20 January
  2027 AoE submission deadline. The event explicitly spans learning and decision-making in humans,
  animals, and algorithms.
- [CCN 2027](https://2027.ccneuro.org/) and [COSYNE 2027](https://www.cosyne.org/) remain known,
  high-value sources. This milestone did not alter their production adapters or create duplicate
  event records.

## Offline pilot implementation and observed results

| Pilot | Health | Fetched | Matched/details | Opportunities | Profiles |
|---|---|---:|---:|---:|---:|
| CMU Neural Computation | `SUCCESS_NO_MATCHES` | 1 | 1 | 0 | 1 |
| Paradromics careers | `SUCCESS` | 9 | 3 | 3 | 0 |
| RLDM 2027 | `SUCCESS` | 1 | 1 | 1 | 0 |

The CMU result is intentionally not an opportunity. The programme page identifies a valuable
future target, but the admission cycle, Fall 2028 recruitment status, cycle-specific deadline,
and funding are unknown.

Paradromics selected only title candidates that could plausibly expose relevant evidence, then
required role-specific BCI or neural-data text on the official posting. The three current records
were:

| Record ID | Role | Domain fit | Score | Evidence highlights |
|---|---|---|---:|---|
| `job_b64999c0ec2ba3e6` | Field Clinical Specialist/Engineer | `CORE_DOMAIN_FIT` | 79.01 | BCI clinical work and explicit neuroscience/technical degree evidence |
| `job_35958c530d6affa6` | Embedded Software Engineer | `ADJACENT_DOMAIN_FIT` | 60.12 | Low-latency software for brain-machine implants; technical rather than cognitive research |
| `job_a646588f3e94bbb7` | Software Engineer | `CORE_DOMAIN_FIT` | 76.10 | BCI decoding algorithms, real neural data, Python, ML, and signal processing |

Only the Software Engineer posting disclosed base salary (`USD 120,000–150,000`). Working
language remained unknown for all three; English page text was not treated as a language
requirement. The mechanical-design role was not requested in detail merely because the employer
is a BCI company. No duplicate stable IDs were produced.

RLDM produced `event_649df2090270890e`, scored 94.0, and classified
`CORE_DOMAIN_FIT`. The abstract deadline is stored as `submission_deadline`; registration remains
unknown. A live-layout regression was found during the pilot, fixed, tested offline, and verified
with one RLDM-only bounded retry.

## Value versus the Anthropic-heavy baseline

The current baseline contains many technically transferable general-AI roles. The pilot is small
but qualitatively better aligned:

- 2 of 3 extracted industry roles have direct neural-data or BCI-decoding evidence and core fit.
- 1 role remains visible as adjacent technical transfer rather than being inflated to core fit.
- 1 highly relevant PhD programme is retained without fabricating an open cycle.
- 1 event directly covers computational decision-making rather than general conference prestige.
- False-positive control is source- and role-level; the company name alone cannot promote a job.

Success here is evidence completeness and domain alignment, not four additional records.

## Recommended next production sources

1. **Paradromics careers** — best first production candidate after a dry-run review of all current
   extracted fields and recommendation decisions.
2. **RLDM 2027** — stable, high-value event source with explicit deadline semantics.
3. **CMU Neural Computation** — activate only as an informational programme monitor until a dated
   cycle is officially stated.
4. **Synchron careers** — useful next no-match-aware adapter; do not turn hardware roles into core
   recommendations.
5. **Duke Cognitive Neuroscience** — high-value programme profile after a dedicated cycle-aware
   parser test.

Princeton and UCL remain blocked for automated normal-HTTP collection. Neuralink, Precision, and
Blackrock require a separate review of stable first-party job data before implementation.

## Weekly Brief proposal (not implemented)

The future first section should be `TOP RESEARCH MATCHES`, ordered as:

1. `Fall 2028 PhD Watch`
2. `Potential Supervisors & Labs`
3. `NeuroAI / BCI Industry Research`
4. `Conferences & Deadlines`
5. `Transferable General AI Roles`

Every item must carry a semantic label: `NEW_TO_RADAR`, `NEWLY_POSTED`, `APPLICATION_OPEN`,
`POTENTIAL_SUPERVISOR`, or `INFORMATIONAL_PROFILE`. `NEW_TO_RADAR` must never imply an official
posting date. Profiles must render separately from open opportunities, and potential supervisors
must not imply recruitment.

## Deployment gate

Production activation requires a separate approval that names the exact pilot source IDs, reviews
their current live outputs, adds them deliberately to `default_adapters()`, and validates the
resulting GCS transition in dry-run form. This milestone changed no production collection,
schedule, Sheets plan, GCS state, WIF/IAM configuration, or recommendation weights.
