# Industry Research Radar

## Domain-first objective

The industry radar prioritizes roles that directly use neural signals, brain/behavior evidence,
cognitive models, neural representations, or BCI/neurotechnology research. Employer identity is
source context, not evidence that every role is relevant.

The existing score architecture remains unchanged:

- research relevance: 45%, internally domain 55%, method 25%, question 20%;
- PhD career value: 25%;
- skills/career fit: 20%;
- compensation: 10%.

## Evidence gates

An official role can be collected only after the first-party careers page proves the relationship
to any ATS. Domain evaluation then uses the individual role page.

`RESEARCH_DOMAIN_FIT` asks whether the role investigates cognition, brain, behavior, neural data,
or BCI outcomes. `METHOD_TRANSFERABILITY` captures Python, signal processing, ML, data systems, or
engineering skills separately. `CAREER_STAGE_FIT` preserves PhD-required future targets without
claiming current eligibility. `ROLE_REQUIREMENTS` contains only explicitly stated degrees,
experience, location, salary, and work authorization facts.

Unknown education, salary, working language, and sponsorship remain unknown. An English-language
posting is not evidence that English is the working language.

## Source decisions

| Source | Official relationship | Current decision |
|---|---|---|
| Paradromics | First-party careers page links `paradromicsinc.applytojob.com` | `READY_FOR_PILOT` |
| Synchron | First-party page links ADP; distinguishes offices and no-opening states | `READY_FOR_PILOT` |
| Neuralink | First-party careers application, but basic HTML is a JS shell | `NEEDS_MANUAL_REVIEW` |
| Precision Neuroscience | First-party careers page; dynamic role data not exposed in basic HTML | `NEEDS_MANUAL_REVIEW` |
| Blackrock Neurotech | First-party careers page and scam guidance; roles are embedded | `NEEDS_MANUAL_REVIEW` |

Synchron is explicitly the BCI company at `synchron.com`; no Syncron enterprise-software source is
accepted.

## Paradromics pilot policy

The pilot reads the first-party job list, follows at most five plausible role links, and requires
role-specific BCI or neural-data evidence on the JazzHR detail page. Mechanical, manufacturing,
administrative, and unrelated roles are not promoted merely because the company builds BCIs.

Current observed outcomes:

- Field Clinical Specialist/Engineer: core fit based on role-level BCI/clinical/neuroscience
  evidence; explicit degree detail retained.
- Software Engineer: core fit based on BCI decoding, real neural data, ML, and signal processing;
  explicit USD 120,000–150,000 base salary retained.
- Embedded Software Engineer: adjacent fit; valuable implant/BCI technical transfer without a
  demonstrated cognitive research question.

The current title filter is a bounded discovery gate, not a complete labor-market census. It must
not be used as evidence that omitted roles are closed.

## Honest no-match behavior

A source with no relevant current roles returns `SUCCESS_NO_MATCHES`. Synchron's current Cognition
Lab “No current openings” state is an example: the source is healthy, the company is relevant, and
there is no matching vacancy. A talent pool or expression-of-interest form remains an
informational profile, not a specific job.

## Production activation gate

Before activation, review the live extracted fields, false-positive set, request budget, source
metrics, recommendation results, and stable IDs. Then add only the approved adapter ID to the
production registry under a separate authorization. No pilot adapter may enter weekly monitoring
solely because its tests pass.
