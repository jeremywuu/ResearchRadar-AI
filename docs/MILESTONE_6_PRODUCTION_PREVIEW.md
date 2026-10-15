# Milestone 6.1B — Research Source Production Preview

Date: 2026-10-15

Mode: read-only production preview

Production source activation: not authorized

## Safety boundary

The preview used production-shaped interfaces but exposed no GCS commit or Google Sheets apply
operation. It restored authoritative GCS state, collected only the three reviewed pilots,
reconciled them into an ignored local directory, read LIVE PILOT, and built a dry-run plan. It did
not modify the scheduled workflow or `default_adapters()`.

Production remains at `883403dce3a558a614b5bd84d2bbe253cf741711`. The local pilot branch remains
unpushed.

## Verified source identifiers

| Source | Exact source ID | Production role |
|---|---|---|
| [Paradromics Careers](https://paradromics.com/careers/) | `paradromics_careers_pilot` | Candidate opportunity feed |
| [RLDM 2027](https://rldm.org/) | `rldm_2027_official_pilot` | Candidate event feed |
| [CMU Neural Computation](https://www.cmu.edu/ni/academics/grad/programs/phd-neural-computation) | `cmu_neural_computation_profile` | Informational programme watch only |

All remain absent from `default_adapters()` and have `activate_in_production: false` in the review
registry.

## Authoritative state restoration

The existing GCS backend restored and validated:

- snapshot: `38565510105`
- schema version: `2`
- state checksum: `024190f35a6270ca046ee01862eaf93047a02c86d2953038e0b04497a8f718b4`
- pointer generation: `1791981644804175`
- records: 45 jobs, one PhD record, two events; 48 total

These values match the approved preview baseline. The post-preview read observed the same pointer
generation. No successor snapshot, manifest, or pointer was created.

## Live source results

| Source | Health | Fetched | Opportunities | Profiles | Errors |
|---|---|---:|---:|---:|---:|
| CMU Neural Computation | `SUCCESS_NO_MATCHES` | 1 | 0 | 1 | 0 |
| Paradromics | `SUCCESS` | 9 | 3 | 0 | 0 |
| RLDM 2027 | `SUCCESS` | 1 | 1 | 0 | 0 |

The client retained TLS and hostname validation, robots checks, timeouts, and the existing detail
cap. No blocked or unapproved source was contacted.

## Paradromics role-fit audit

Research-domain score and role-function audit answer different questions. A posting can concern
BCI or neural data while still being clinical implementation or platform engineering.

### `job_b64999c0ec2ba3e6` — Field Clinical Specialist/Engineer

- Status/location: verified open; Austin, Texas
- Score/domain/recommendation: 79.01 / `CORE_DOMAIN_FIT` / `HIGH_PRIORITY`
- Role audit: `CLINICAL_IMPLEMENTATION`
- Evidence: supports implantable BCI use during procedures, study visits, recording sessions, and
  neural-data workflows; it also mentions experimental workflows and decoding approaches
- Education: bachelor's in engineering, neuroscience, nursing, biomedical sciences, a related
  technical/clinical discipline, or an equivalent combination
- Salary: unknown
- Work authorization: the application asks whether the candidate is legally authorized to work in
  the United States; sponsorship policy is unknown
- Assessment: strong neurotechnology exposure, but not established as a primary computational
  research role

### `job_35958c530d6affa6` — Embedded Software Engineer

- Status/location: verified open; Austin, Texas
- Score/domain/recommendation: 60.12 / `ADJACENT_DOMAIN_FIT` / `RELEVANT`
- Role audit: `TECHNICAL_PLATFORM`
- Evidence: low-latency brain-machine implant software with neuroengineers and electronics
  designers
- Education and salary: unknown
- Work authorization: application question present; sponsorship policy unknown
- Assessment: useful BCI engineering transferability, but no verified ownership of neural
  decoding, cognitive modeling, or experimental research

### `job_a646588f3e94bbb7` — Software Engineer

- Status/location: verified open; Oakland, California
- Score/domain/recommendation: 76.10 / `CORE_DOMAIN_FIT` / `HIGH_PRIORITY`
- Role audit: `RESEARCH_ADJACENT_ENGINEERING`
- Evidence: BCI data curation, decoding algorithms, simulated and real neural data,
  hardware-in-the-loop work, Python, ML, signal processing, and time-series processing
- Education: bachelor's in computer science, computer engineering, or a related field, or
  equivalent experience; 3+ years of relevant professional experience
- Salary: USD 120,000–150,000 base
- Work authorization: application question present; sponsorship policy unknown
- Assessment: strongest industry match, while remaining engineering rather than a scientist role

Working language remains unknown for all three. English page text is not a language requirement.

## RLDM 2027 validation

The [official conference page](https://rldm.org/) and
[official call](https://rldm.org/call-for-abstracts-2027/) support:

- Record ID: `event_649df2090270890e`
- dates and location: 6–9 July 2027, Paris, France
- abstract deadline: 20 January 2027, AoE
- registration deadline: unknown

The deadline remains `submission_deadline`; `AoE` is preserved separately in the raw source
record. The restored baseline contains no same-ID or same-series/edition RLDM event.

## CMU Fall 2028 watch assessment

The [official CMU page](https://www.cmu.edu/ni/academics/grad/programs/phd-neural-computation)
produced one `PHD_PROGRAM_PROFILE` and no PhD opportunity. Admission cycle, Fall 2028 recruitment,
cycle-specific deadline, funding, and faculty recruitment statements remain unknown.

The general December 1 deadline is retained only as general programme information. The current
durable-state and Weekly Brief paths do not yet emit profile-specific change events, so CMU should
not be activated as an opportunity feed.

## Incremental comparison and Sheets preview

Against the restored baseline:

- `NEW_TO_RADAR`: 4
- content changes: 0
- observation-only changes: 0
- duplicate IDs or semantic conflicts: 0
- source failures: 0
- officially newly posted: unknown; no official posting date was extracted

The authenticated LIVE PILOT dry-run proposed:

| Category | Inserts | Updates | Unchanged | Invalid | Conflicts |
|---|---:|---:|---:|---:|---:|
| Jobs | 3 | 0 | 0 | 0 | 0 |
| PhD | 0 | 0 | 0 | 0 | 0 |
| Events | 1 | 0 | 0 | 0 | 0 |

Fingerprint: `cd567959fd42f4923c5f296c66544809678b38fa88840dd8bf29d314ed2dd2fa`.

The plan is hypothetical. CMU is correctly absent. The three job inserts expose a quality issue:
recommendation priority does not yet incorporate the role-function audit, so clinical
implementation and embedded platform work would be admitted alongside the decoding role.

## Production activation proposal

### RLDM — recommend activation

- Enable `rldm_2027_official_pilot` without changing its ID.
- Maximum activity is two content requests plus bounded robots checks.
- First run should add one event only if the semantic duplicate guard still passes.

### Paradromics — recommend conditional activation

- Source reliability and ATS provenance are production-suitable.
- The five-detail cap remains; this run used one careers request and three details, plus robots
  checks.
- Before top-match placement, reporting should consume a generic role-function gate: highlight
  research-adjacent engineering, hold clinical implementation for review, and keep technical
  platform work secondary. This does not require changing scoring weights.

### CMU Neural Computation — defer opportunity-feed activation

- Keep `cmu_neural_computation_profile` informational.
- Add profile-specific durable comparison and report rendering before monitoring activation.
- Never write it to `PhD_Opportunities` without an actionable official cycle.

## Exact changes requiring separate approval

1. Add only approved source IDs to production adapter construction; keep the review registry
   default-disabled.
2. Add profile-aware monitoring if CMU is approved.
3. Add the generic role-function reporting gate before Paradromics top-match placement.
4. Run a new restore-first dry-run against the then-current GCS baseline.
5. Review IDs, semantic duplicates, metrics, and the proposed successor state before pushing.

Rollback means disabling future collection while retaining observed history. It must not roll
back `current.json`, delete snapshots, or infer closures.
