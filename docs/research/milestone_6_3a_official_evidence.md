# Milestone 6.3A official-source evidence dossier

Verified: 2026-10-16 (Europe/Brussels)

This dossier separates three kinds of evidence:

- a company's current official careers index;
- an authorized ATS record linked by that index; and
- a research-team or publication profile that does **not** establish a job opening.

The status of an individual role is `CONFIRMED_LISTED` only when it is present on the
current official careers index (or its current authorized ATS index). A detail page that
can still be loaded without corresponding index evidence is
`DETAIL_PAGE_ACCESSIBLE_ONLY`; it is not enough to call the role open. A temporary
retrieval failure is `SOURCE_UNAVAILABLE`, not `CONFIRMED_CLOSED`.

## Executive findings

| Organization | Official careers / research entry point | Verified recruitment system | Current access | Recommended disposition |
| --- | --- | --- | --- | --- |
| Neuralink | [Careers](https://neuralink.com/careers/) | [Greenhouse board](https://job-boards.greenhouse.io/neuralink) linked from the company careers experience | Index and individual details are readable; bounded structured collection is feasible | `READY_FOR_PILOT` |
| Precision Neuroscience | [Careers](https://www.precisionneuro.io/careers) | [Kula careers index](https://careers.kula.ai/precision-neuroscience) used by the official careers page | Current index and individual detail pages are readable | `READY_FOR_PILOT` |
| Synchron | [Careers](https://synchron.com/careers) | ADP Workforce Now links embedded in the first-party careers index | First-party index is readable; ADP detail rendering is browser-dependent | `READY_FOR_PILOT` for index-level monitoring and honest no-match results |
| Blackrock Neurotech | [Careers](https://blackrockneurotech.com/careers/) | Rippling is identified by the company as its recruitment channel | Company page is readable; current job list is dynamically embedded and not reliably exposed in ordinary HTML | `NEEDS_MANUAL_REVIEW` before an adapter |
| Paradromics | [Careers](https://paradromics.com/careers/) | Existing verified JazzHR integration in ResearchRadar | First-party page currently lists nine roles | Existing production source; do not duplicate |
| Neuroelectrics | [Careers](https://www.neuroelectrics.com/careers) | Existing production integration; the company says its careers page is the only official source | Page is readable, but no specific vacancies are currently rendered in ordinary HTML | Existing production source; preserve honest no-match behavior |
| Meta AI | [TRIBE v2 publication](https://ai.meta.com/research/publications/a-foundation-model-of-vision-audition-and-language-for-in-silico-neuroscience/), [AI careers](https://ai.meta.com/join-us/) | Meta Careers | Research and careers pages are readable, but the publication is not a vacancy | `RESEARCH_TEAM_PROFILE` only |
| Google DeepMind | [Hybrid neural-cognitive models](https://deepmind.google/research/publications/94006/), [Careers](https://deepmind.google/careers/) | Google Careers, linked from DeepMind | Research and careers pages are readable, but the publication is not a vacancy | `RESEARCH_TEAM_PROFILE` only |

## Recommended pilot set

1. **Neuralink** — strongest source mechanics: the official careers page exposes a
   current role index and the linked Greenhouse board provides stable numeric job IDs,
   complete duties, requirements, locations and compensation. Candidate processing can
   remain bounded after domain-first title/department filtering.
2. **Precision Neuroscience** — the current Kula index is readable and currently exposes
   a directly relevant DSP role. It offers a useful test of BCI relevance without assuming
   every medical-device role is research work.
3. **Synchron** — monitor the readable first-party index. The scientifically attractive
   New York cognition lab currently says **"No current openings here"**, so the correct
   research-role result is `SUCCESS_NO_MATCHES`. The pilot still provides value by
   detecting a future transition from research-team profile to listed opening.

Blackrock is highly valuable but should follow after its dynamic Rippling index can be
retrieved reproducibly without treating discoverable detail URLs as current-index proof.

## Neuralink

### Source relationship and feasibility

The [Neuralink careers page](https://neuralink.com/careers/) currently presents the
company's role index and links roles to the `job-boards.greenhouse.io/neuralink` board.
The careers page reports 79 open roles at verification time and separates BCI
Applications, Brain Interfaces, Internships and other departments. This first-party link
establishes Greenhouse ownership; matching the organization name or discovering a
Greenhouse URL in a search engine alone would not.

The board is suitable for a bounded adapter because:

- current index membership can be checked before a detail is accepted;
- Greenhouse numeric IDs are stable source identifiers;
- details include duties, required and preferred qualifications, location, compensation
  and application questions; and
- a small title/department shortlist can be inspected without downloading every detail.

### Current high-value roles

All roles below were present on the current official careers index and their official
Greenhouse details were readable on 2026-10-16.

#### Machine Learning Engineer Intern — BCI Applications

- Official detail: [Greenhouse job 6594261003](https://job-boards.greenhouse.io/neuralink/jobs/6594261003)
- Status: `CONFIRMED_LISTED`
- Location: South San Francisco, California; on-site expectations and availability are
  part of the application evidence.
- Work: develop neural decoders to improve BCI control speed, accuracy, reliability and
  functionality; analyze complex datasets and work with cross-functional BCI teams.
- Required evidence: prior ML model-building, strong ML fundamentals, analysis of complex
  data, communication and coding. Time-series experience is preferred.
- Official compensation evidence: USD 35/hour for California.
- Assessment boundary: unusually strong near-term technical and domain fit, but the page
  asks about current US work authorization and future sponsorship. It does not prove the
  user's eligibility or sponsorship outcome.

#### Neuroengineer Intern — Next Gen

- Official detail: [Greenhouse job 7483748003](https://job-boards.greenhouse.io/neuralink/jobs/7483748003)
- Status: `CONFIRMED_LISTED`
- Location: South San Francisco, California.
- Work: map neural correlates, build ML architectures mapping neural activity to
  multidimensional outputs, and run experiments spanning non-human-primate
  electrophysiology and human fMRI.
- Required evidence: exceptional ability in neuroscience, ML, biomedical engineering or
  related work; at least two years of academic or industry experience; Python data
  analysis and scientific-method understanding.
- Preferred evidence includes neural population dynamics, manifold analysis, neural
  decoding, human fMRI and closed-loop BCI.
- Official compensation evidence: USD 35/hour for California.
- Assessment boundary: strong user-method overlap, but "2+ years" and application-season
  details must be evaluated explicitly; academic experience must not automatically be
  rewritten as professional experience.

#### Neuroengineer, Next Gen

- Official detail: [Greenhouse job 7571489003](https://job-boards.greenhouse.io/neuralink/jobs/7571489003)
- Status: `CONFIRMED_LISTED`
- Locations: Austin and South San Francisco.
- Work: neural recording/stimulation experiments, computational stimulation models,
  encoding strategies, behavioral data interpretation, prosthetic vision, machine vision
  and eye tracking.
- Required evidence: at least four years of academic or industry experience, Python,
  scientific-method and engineering fundamentals.
- Official base-salary evidence: USD 122,000–226,000.
- Career-stage interpretation: long-term / experienced research-engineering pathway, not
  assumed immediately application-ready.

#### Signal Processing Engineer

- Official detail: [Greenhouse job 6681863003](https://job-boards.greenhouse.io/neuralink/jobs/6681863003)
- Status: `CONFIRMED_LISTED`
- Locations: Austin and South San Francisco.
- Work: real-time cortical signal sensing, spike detection, electrode-health algorithms,
  compression and hardware-constrained DSP.
- Required evidence: BS/MS/PhD in a relevant field and at least three years of DSP
  algorithm/product experience, with Python and C.
- Official base-salary evidence: USD 121,000–230,500.
- Role boundary: direct neural-signal domain work, but primarily embedded/DSP engineering;
  it should not be presented as cognitive research simply because neural data are involved.

#### Software Engineer, BCI Applications

- Official detail: [Greenhouse job 6596365003](https://job-boards.greenhouse.io/neuralink/jobs/6596365003)
- Status: `CONFIRMED_LISTED`
- Locations: Austin and South San Francisco.
- Work: low-latency applications converting live neural streams into device control and
  interaction paradigms for cursor, text, speech and assistive devices.
- Current listing explicitly says neuroscience experience is not required and that hiring
  spans junior through senior levels; a bachelor's degree in CS or related field, or
  equivalent experience, is required.
- Official base-salary evidence: USD 128,000–281,000.
- Role boundary: strongly BCI-adjacent software, but research intensity depends on the
  responsibilities actually extracted; employer/domain branding alone must not turn it
  into `RESEARCH_DIRECT`.

### Stable identity guidance

Use the Greenhouse job ID plus canonical organization identity, not title text. Title
wording changed between an older cached version of job `6596365003` and the current page,
while the source ID remained stable. This is a content change, not a new opportunity.

## Precision Neuroscience

### Source relationship and feasibility

The [first-party careers page](https://www.precisionneuro.io/careers) embeds its open-role
index, and the matching [Kula organization index](https://careers.kula.ai/precision-neuroscience)
currently provides stable numeric detail paths, locations, departments, workplace type and
salary ranges. The matching current titles on both pages establish the relationship; an
unlinked Kula page alone would not.

At verification time, the current Kula index listed ten positions. Only one was an obvious
neural-signal / algorithm candidate. This is a useful domain-first selection test: most
roles are mechanical, quality, firmware, marketing, product or business positions and
must not be promoted merely because Precision builds a BCI.

### Current high-value role: DSP Algorithm Engineer

- Official ATS detail: [Kula job 39009](https://careers.kula.ai/precision-neuroscience/39009-dsp-algorithm-engineer)
- Status: `CONFIRMED_LISTED`, because it appears on the current Kula organization index
  and the official company careers index.
- Locations: Chicago, Framingham, New York and Santa Clara; on-site.
- Work: improve the end-to-end BCI acquisition chain, from sensor signals through ML
  feature extraction; design adaptive filtering and model device performance.
- Required evidence: analog/digital and statistical signal processing, system modeling,
  embedded signal processing and Python/MATLAB/Simulink/SystemC/SystemVerilog. PyTorch and
  on-device ML are listed as working knowledge / pluses rather than a pure research mandate.
- Official base-salary evidence: USD 155,000–185,000.
- Official work-location evidence: the listing says Precision cannot consider remote
  workers or people not currently US-based and legally authorized to work in the US.
- Assessment boundary: strong BCI method relevance and long-term technical value, but the
  role is signal-chain engineering rather than demonstrated cognitive-neuroscience
  research. Current application readiness and work authorization are not established.

### Other current role useful for negative-control classification

[Full-Stack Software Engineer, Kula job 25805](https://careers.kula.ai/precision-neuroscience/25805-full-stack-software-engineer)
is currently listed, requires at least three years of full-stack experience, and focuses on
clinical UX, cloud-platform infrastructure and physiological-data visualization. It is a
BCI-company job with transferable technical value, not direct evidence of neural-decoding
research. The listing says candidates must currently be US-based and legally authorized to
work in the US. These facts should lower current-readiness confidence without inferring the
user's personal eligibility.

### Index-versus-detail rule

Earlier official/company posts mentioned Staff Neuroscientist, Staff Machine Learning
Scientist and Clinical Data Scientist roles, but these titles were not on the current
official/Kula index at verification time. They must therefore not be emitted as
`CONFIRMED_LISTED`; if their old details remain accessible, their status is at most
`DETAIL_PAGE_ACCESSIBLE_ONLY` pending current-index evidence.

## Synchron

### First-party index and ATS relationship

The [Synchron careers page](https://synchron.com/careers) is a directly readable
first-party index. Its San Diego roles link to ADP Workforce Now with an organization-
specific `ccId`, `cid` and job ID. That first-party link establishes ADP ownership.
Direct ADP detail requests return a supported-browser shell in ordinary HTTP retrieval,
so the official Synchron index should remain the authoritative listing surface.

### Current research-job result

The company describes its New York Soho location as a cognition lab working on neural
signals, models of human thought, real-time neural-data pipelines, closed-loop
neurofeedback, model serving and HCI. The same current page states **"No current openings
here"**. This is:

- a strong `RESEARCH_TEAM_PROFILE`;
- a valid future team watch; and
- `SUCCESS_NO_MATCHES` for current research vacancies.

It is not a talent-pool job and must not be emitted as a confirmed vacancy.

The current San Diego index lists seven positions (including Principal Mechanical
Engineer, ASIC Technical Lead and AFE Test & Integration Engineer), while Melbourne also
states no current openings. None should become a high-priority cognitive-neuroscience
role merely from Synchron's mission. The ADP detail-rendering limitation also makes
requirements incomplete unless individual details can be retrieved normally.

### Recommended pilot behavior

- Parse the official index only, with bounded requests.
- Preserve ADP URLs and job IDs for current San Diego listings.
- Emit source health independently of research matches.
- Return `SUCCESS_NO_MATCHES` for the cognition-lab research filter while retaining the
  team profile as informational evidence.
- Never turn the "Express interest" link into a specific vacancy.

## Blackrock Neurotech

The [official careers page](https://blackrockneurotech.com/careers/) identifies recruitment
communications from Blackrock domains and a Rippling ATS address. It also says internships
are posted on the careers page when available. The page's ordinary HTML did not expose a
reliable current role index during this review.

A Rippling detail for [Neural Data Infrastructure Engineer](https://ats.rippling.com/en-CA/blackrockneurotech/jobs/91ebe665-8784-4195-aae8-03031f7c3f6e)
was directly readable and is highly relevant: it describes ownership of intracortical
recording pipelines, spike processing, neural/behavioral alignment, scientific formats,
PyTorch data interfaces and collaboration with model researchers. It requires either a
bachelor's plus three years, a master's plus one year, or a relevant PhD/equivalent.

Because this review could not independently enumerate the current Rippling organization
index from the first-party page, the conservative status is
`DETAIL_PAGE_ACCESSIBLE_ONLY`, not `CONFIRMED_LISTED`. A future adapter should first solve
current-index discovery and only then fetch bounded details. The role illustrates why
Blackrock is a high-value later source, but it is not one of this milestone's safest pilot
adapters.

## Existing production sources

### Paradromics

Do not add another adapter. The existing source already follows the
[official Paradromics careers page](https://paradromics.com/careers/) and its verified
JazzHR relationship. The first-party page currently lists nine jobs, including Field
Clinical Specialist/Engineer, Embedded Software Engineer and Software Engineer. Existing
role-function gates remain necessary: the clinical role is not a top research match; the
embedded role is technical platform work; the Oakland software role is research-adjacent
because its verified duties include BCI data and decoding.

### Neuroelectrics

Do not add another adapter. The [official careers page](https://www.neuroelectrics.com/careers)
explicitly states that it is the only official source for openings. It is currently
readable and describes modeling, EEG/stimulation and digital-brain work, but no specific
vacancy is exposed in the ordinary page content. The correct current result is therefore
an honest no-match / informational result unless the existing authorized recruitment
surface supplies a current role. Team testimonials are not job openings.

## Research-organization watch profiles

### Meta AI / Human & Machine Intelligence

The official Meta AI paper ["A foundation model of vision, audition, and language for
in-silico neuroscience"](https://ai.meta.com/research/publications/a-foundation-model-of-vision-audition-and-language-for-in-silico-neuroscience/)
was published on 2026-03-26. It introduces TRIBE v2, trained with more than 1,000 hours of
fMRI from 720 participants to predict brain activity across novel stimuli, tasks and
subjects. Its official research topic is Human & Machine Intelligence. This is direct
evidence of a highly relevant active research direction in multimodal encoding,
brain-model comparison and interpretable latent representations.

The [Meta AI Join Us page](https://ai.meta.com/join-us/) provides separate routes to Meta
Careers for Research Scientist, User Research and Software Engineering roles and describes
Human & Machine Intelligence as combining cognitive science with AI. That page is a
careers entry point, not evidence that the TRIBE v2 team has a current vacancy.

Safe representation:

- entity: `RESEARCH_TEAM_PROFILE`;
- research relevance: very high for Track A / cross-modal brain encoding;
- current team-specific opening: `UNKNOWN`;
- current application eligibility: `UNKNOWN`.

The AI Residency page describes a pre-PhD-oriented training pathway, but its generic
description does not establish a currently open 2026 application cycle. It must be
monitored independently for a dated, current application announcement.

### Google DeepMind / human reward-learning research

The official DeepMind publication ["Hybrid neural–cognitive models reveal how memory
shapes human reward learning"](https://deepmind.google/research/publications/94006/) was
published on 2026-02-05 in *Nature Human Behaviour*. It combines artificial neural
networks with interpretable cognitive architectures and applies them to human reward-
learning data, finding that successful models require flexible memory representations.
This is direct evidence of an active research direction strongly aligned with Track B.

The [DeepMind careers page](https://deepmind.google/careers/) separately defines Research
Engineer and Research Scientist pathways. It says Research Scientists normally hold a PhD;
Research Engineers bridge experimental research and implementation. The page links to
Google's open-role index, but the publication itself does not identify a vacancy or imply
that its authors' team is hiring.

Safe representation:

- entity: `RESEARCH_TEAM_PROFILE`;
- research relevance: very high for hybrid cognitive/ANN models and reward learning;
- team-specific confirmed job: none established by this review;
- plausible career stage: long-term/post-PhD for Research Scientist; role-specific evidence
  is required for any Research Engineer or student opportunity.

## ATS status model and adapter acceptance rules

The pilot should preserve these independent fields:

1. `careers_index_observed`: whether the official company or authorized ATS index was
   successfully read;
2. `detail_page_observed`: whether an individual detail page was read;
3. `listing_status`: `CONFIRMED_LISTED`, `DETAIL_PAGE_ACCESSIBLE_ONLY`, `NOT_OBSERVED`,
   `CONFIRMED_CLOSED`, or `SOURCE_UNAVAILABLE`;
4. `source_health`: retrieval/parsing health, independent of listing status; and
5. `evidence_observed_at`: the timestamp for each observation.

Rules:

- `CONFIRMED_LISTED` requires current-index evidence. Detail accessibility alone is
  insufficient.
- `CONFIRMED_CLOSED` requires explicit first-party closure evidence; disappearance,
  bounded candidate processing, HTTP failure or parser failure is not closure.
- When the index succeeds but a bounded filter does not select a role, preserve it as
  `NOT_OBSERVED` by this bounded run, not closed.
- Reappearing roles use organization + ATS job ID for stable identity.
- Talent pools and "express interest" forms remain informational, not specific openings.
- Research publications and team pages never become job records without a separate current
  careers-index link.

## Implications for career-stage assessment

Evidence from these sources supports keeping career stage separate from role function:

- Neuralink ML Engineer Intern and Neuroengineer Intern are candidates for
  `NEAR_TERM_INTERNSHIP_OR_RA`, subject to current enrollment, location and work-
  authorization evidence.
- Neuralink Neuroengineer, Signal Processing Engineer and Precision DSP Algorithm Engineer
  are `PRE_PHD_RESEARCH_ENGINEERING` or `POST_PHD_RESEARCH_CAREER` depending on their
  explicit experience/education requirements; the label must not imply readiness.
- Synchron's cognition lab, Meta TRIBE v2 and the DeepMind reward-learning work are
  `INFORMATIONAL_RESEARCH_TEAM` until a current role is linked.
- Platform/full-stack, firmware and embedded roles may be `TRANSFERABLE_TECHNICAL` even at
  a BCI company.

No source reviewed here establishes visa sponsorship, the user's work authorization, or
the equivalence of academic research and required professional experience. Those facts
remain unknown unless a specific official listing states them.

## Recommended production sequence after offline validation

1. Pilot Neuralink and Precision against fixtures and one explicitly authorized bounded
   live preview.
2. Pilot Synchron as a first-party index plus research-team watch, accepting
   `SUCCESS_NO_MATCHES` for current cognition roles.
3. Add Blackrock only after current-index discovery is reproducible and tested against
   stale-detail false positives.
4. Keep Meta and DeepMind in a future informational research-team watch; do not register
   publication pages as opportunity feeds.
5. Reuse the existing Paradromics and Neuroelectrics adapters; do not duplicate them.

