# Milestone 6.1C-A — Research-role gate and activation preparation

## Decision boundary

This milestone prepared two opportunity sources. Milestone 6.1C-B wires them into the production
registry behind a default-false feature flag, without enabling that flag:

| Source ID | Mode | Readiness | Production active |
|---|---|---|---|
| `rldm_2027_official_pilot` | event opportunity | approved for preparation | no |
| `paradromics_careers_pilot` | industry jobs | conditional on role-function gate | no |
| `cmu_neural_computation_profile` | informational PhD watch | informational only | no |

`default_adapters()` returns the original six sources while
`RESEARCH_RADAR_RESEARCH_SOURCES_ENABLED` is absent or false. With an explicit true value it adds
only Paradromics and RLDM. The active Monday 09:00 Europe/Brussels workflow reads the repository
variable, which remains unset/false for this deployment.

## Research-role suitability gate

The deterministic role-function module reads role-level responsibility evidence from the
normalized job and its preserved `original_values`. Employer identity and title are not sufficient
evidence. It derives one of:

- `RESEARCH_DIRECT`: explicit ownership of research, experiments, hypotheses, scientific studies,
  computational models, publication, or neural-data analysis.
- `RESEARCH_ADJACENT_ENGINEERING`: engineering responsibilities explicitly tied to neural data,
  decoding, signal processing, or computational modeling.
- `CLINICAL_IMPLEMENTATION`: clinical-site, surgical, patient-visit, training, or field-support
  implementation work.
- `TECHNICAL_PLATFORM`: embedded, firmware, infrastructure, deployment, low-latency, or platform
  responsibilities without direct research ownership.
- `NON_RESEARCH`: explicit sales, recruiting, legal, marketing, business-development, or
  administrative responsibilities.
- `UNKNOWN`: role-level evidence is absent or does not support a reliable function class.

The gate does not modify the approved 45/25/20/10 score, Domain Fit, career-stage classification,
or source facts. Recommendation decisions retain the base recommendation and add an effective
recommendation plus a display group. Clinical and unknown roles are held in `NEEDS_REVIEW`;
non-research roles are `LOW_PRIORITY`; platform roles are displayed as transferable technical;
direct and research-adjacent roles remain eligible only when their independent domain and
recommendation evidence also qualifies.

The role assessment is derived at planning/report time. It is not added to stored opportunity
records, so durable-state schema version 2 remains compatible and no GCS migration is required.

## Paradromics acceptance cases

| Record ID | Domain Fit | Role function | Effective placement | Qualification caution |
|---|---|---|---|---|
| `job_b64999c0ec2ba3e6` | `CORE_DOMAIN_FIT` | `CLINICAL_IMPLEMENTATION` | Clinical Neurotechnology / Needs Review | Not a top computational research role |
| `job_35958c530d6affa6` | `ADJACENT_DOMAIN_FIT` | `TECHNICAL_PLATFORM` | Transferable Technical Roles | Research ownership not established |
| `job_a646588f3e94bbb7` | `CORE_DOMAIN_FIT` | `RESEARCH_ADJACENT_ENGINEERING` | NeuroAI / BCI Research-Adjacent Roles | Posting states 3+ years professional experience; current eligibility and sponsorship remain unverified |

The Software Engineer evidence includes BCI data curation, BCI decoding algorithms, evaluation
with simulated and real neural data, signal processing, Python, and machine learning. No inference
is made about sponsorship or immediate applicant eligibility.

## RLDM production preparation

- Stable source ID: `rldm_2027_official_pilot`
- Stable Record_ID: `event_649df2090270890e`
- Official source: <https://rldm.org/>
- Dates: July 6–9, 2027
- Location: Paris, France
- Abstract deadline: January 20, 2027 AoE
- Registration deadline: unknown

The adapter retains bounded requests, first-party provenance, source health, stable identity, and
semantic deadline separation. The activation change must check semantic event identity before
adding the adapter to avoid a duplicate under another Record_ID.

## CMU informational watch

`cmu_neural_computation_profile` remains a `PHD_PROGRAM_PROFILE`, not an opportunity feed.
Fall 2028 opening, cycle-specific deadline, and faculty recruitment are unknown. The general
December 1 information must remain profile evidence, not a Fall 2028 deadline.

Future PhD Watch support needs durable informational-profile records, profile-change detection,
an explicit transition from profile to announced cycle/opening, faculty recruitment evidence, and
a report section that never mixes profiles with open opportunities. This milestone does not add a
parallel database.

## Production activation seam

A separately authorized flag activation will:

1. Set `RESEARCH_RADAR_RESEARCH_SOURCES_ENABLED=true` after a controlled cloud-run authorization;
   no further adapter-registry code change is required.
2. Keep `CmuNeuralComputationProgramAdapter` out of the opportunity adapter registry.
3. Retain CMU as informational and inactive.
4. Run one restore-first production-style dry-run, confirm RLDM semantic deduplication and the
   three Paradromics effective placements, then review the proposed GCS successor.
5. Commit no Google Sheets changes; all Sheets behavior remains dry-run/read-only.

Expected added request budget per monitoring run is two RLDM HTML pages plus the Paradromics
careers page, robots checks, and at most the existing bounded relevant-role detail requests.
Rollback is setting the repository variable to false for future runs; historical GCS observations
remain immutable and are not deleted.

## Three collected jobs versus two proposed inserts

Paradromics produced three valid canonical opportunities. Collection and history retain all three.
The Sheets admission policy independently admits only `HIGH_PRIORITY` and `RELEVANT` effective
recommendations. The Field Clinical Specialist/Engineer retains `CORE_DOMAIN_FIT` but is classified
as `CLINICAL_IMPLEMENTATION`, making its effective recommendation `NEEDS_REVIEW`; it is therefore
held from the proposed Sheets insertion and Top Research Matches. Embedded Software Engineer and
Software Engineer remain insertable in their technical and research-adjacent placements. This is
a recommendation-filtering result, not source filtering, deletion, deduplication, or a missing
record.

## Safety verification

The production workflow, schedule, WIF/IAM, active adapter list, Google Sheets, and GCS pointer are
outside this change. The source-preview seam exposes restore but no commit; Sheets planning uses a
read-only or in-memory adapter. Personal feedback remains authoritative in Google Sheets and notes
are excluded from reports.
