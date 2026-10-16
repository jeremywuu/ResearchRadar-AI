# Milestone 6.3A — Industry Research Job Discovery & Career Fit

Verified 2026-10-16. This milestone is offline-only. It does not alter production sources,
workflow triggers, GCS, Sheets, IAM, WIF, scoring weights, or historical timestamps.

## Source conclusions

| Source | Official recruitment evidence | Result |
| --- | --- | --- |
| Neuralink | First-party careers page links the Neuralink Greenhouse board | Ready for bounded pilot |
| Precision Neuroscience | First-party careers page and current Kula organization index agree | Ready for bounded pilot |
| Synchron | First-party index links ADP; cognition lab explicitly has no current openings | Index-only pilot; honest no-match |
| Blackrock Neurotech | First-party page identifies Rippling, but the current index is not reliably enumerable | Manual review |
| Paradromics | Existing verified JazzHR adapter | Keep existing production source |
| Neuroelectrics | Existing first-party adapter; an empty current listing is not failure | Keep existing production source |
| Meta AI | Official TRIBE v2 research page plus separate careers entry | Research-team profile only |
| Google DeepMind | Official reward-learning research page plus separate careers entry | Research-team profile only |

The disabled pilot IDs are `neuralink_careers_discovery`,
`precision_neuroscience_careers_discovery`, and `synchron_careers_discovery`. They are returned only
by `milestone_6_3a_pilot_adapters()` and are not part of the production registry.

## Verified current-job evidence

Neuralink's current index supports stable Greenhouse IDs and bounded detail retrieval. Particularly
relevant listings included ML Engineer Intern — BCI Applications (6594261003), Neuroengineer
Intern — Next Gen (7483748003), Neuroengineer — Next Gen (7571489003), Signal Processing Engineer
(6681863003), and Software Engineer — BCI Applications (6596365003). These span near-term
internships, experienced research engineering, DSP, and research-adjacent software; they are not
one interchangeable class.

Precision's current index confirmed DSP Algorithm Engineer (39009): neural acquisition, adaptive
filtering, ML feature extraction, and signal-chain modeling, with a listed USD 155,000–185,000
range and explicit US-based/legal-work-authorization condition. Full-Stack Software Engineer
(25805) is a useful negative control: BCI-company employment with technical-platform rather than
direct neural-decoding research. Older Staff Neuroscientist or ML Scientist detail pages are not
current openings without index evidence.

Synchron's New York cognition lab is highly relevant as a team, but the official page currently
says there are no openings there. The correct output is `SUCCESS_NO_MATCHES` plus an informational
team profile—not a vacancy.

## Listing and identity policy

`CONFIRMED_LISTED` requires current official index membership and an official or first-party-linked
ATS relationship. An accessible old detail page is `DETAIL_PAGE_ACCESSIBLE_ONLY`. Temporary failure
is `SOURCE_UNAVAILABLE`; absence is `NOT_OBSERVED`; only explicit official closure evidence supports
`CONFIRMED_CLOSED`. Stable ATS job IDs plus canonical organization identity survive title edits.

## Anthropic audit

The live adapter fetches a large Greenhouse index but examines only a bounded detail set. Repeated
title-first selection can spend the same budget on broad AI engineering, obscure whether relevant
departments were covered, and repeatedly surface low-value new records. The offline proposal keeps
the cap at 25, reserves a small new-candidate budget, retains tracked relevant IDs, ranks cognition
and neuroscience evidence first, and round-robins across cognition/neuroscience,
interpretability/alignment, research science, and general ML groups. It is deterministic and
coverage-aware. It has not replaced the production policy in this milestone.

## Benchmark conclusion

The reviewed benchmark separates neural-decoding scientists, brain-ANN scientists, BCI ML
engineers, computational-neuroscience engineers, neural-signal researchers, clinical specialists,
embedded engineers, generic ML infrastructure, generic LLM pretraining, internships, and teams
without openings. Employer branding alone never establishes direct research. Unknown requirements
do not yield confirmed eligibility. Career timing and role function remain independent.

## Deployment proposal

1. Review fixtures against a fresh current index immediately before deployment.
2. Consider Neuralink and Precision behind a disabled feature flag; keep request budgets at five
   and three details respectively.
3. Use Synchron as an index-level/team watch until ADP details are reliably retrievable.
4. Do not activate Blackrock until current-index enumeration is reproducible.
5. Run a read-only production-style preview against the latest GCS baseline, then separately
   authorize any registry change and successor commit.

Production must continue preserving schema v2, conservative closure semantics, read-only Sheets,
and the existing research-role gate.
