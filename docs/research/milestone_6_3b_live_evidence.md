# Milestone 6.3B live official-source evidence

**Observed:** 2026-10-17 (Europe/Brussels)  
**Scope:** read-only verification of current careers indexes and their first-party-linked ATS pages.  
**Status vocabulary:**

- `CONFIRMED_LISTED`: present on the employer's current careers index (or its currently linked ATS index) and backed by an accessible official detail page.
- `DETAIL_PAGE_ACCESSIBLE_ONLY`: a detail URL resolves, but the role is not confirmed on the current index. A surviving ATS page alone is not evidence that a vacancy remains open.
- `SOURCE_UNAVAILABLE`: the relevant official page cannot be read through bounded, normal requests. This is source health, not evidence that a role is closed.
- `SUCCESS_NO_MATCHES`: the current official index was read successfully but contains no matching vacancy.

Only employer pages and ATS pages reached through those employer careers surfaces were used. No proxy, anti-bot bypass, search-result snippet, or third-party job aggregator was used. The Neuralink index check used one bounded request to Greenhouse's public board API; the other checks used ordinary page retrieval.

## Executive result

| Organization | Official careers entry | Current ATS relationship | Result |
|---|---|---|---|
| Neuralink | [neuralink.com/careers](https://neuralink.com/careers/) | Greenhouse board/API; the six requested Greenhouse IDs are all in the current 80-role index | Six requested roles are `CONFIRMED_LISTED` |
| Precision Neuroscience | [precisionneuro.io/careers](https://www.precisionneuro.io/careers) | The employer careers page links to the [Precision Kula index](https://careers.kula.ai/precision-neuroscience), which carries Precision branding and applications | Ten roles currently listed; three research-relevant roles reviewed below |
| Synchron | [synchron.com/careers](https://synchron.com/careers) | Current roles on the first-party index link to organization-specific ADP Workforce Now job pages | Seven San Diego roles listed; the New York Cognition Lab explicitly has no current openings |

The current-index check is decisive here: none of the Neuralink or Precision roles assessed below is merely a stale, detail-page-only result.

## Neuralink

### Index and ATS provenance

Neuralink's official careers entry is [https://neuralink.com/careers/](https://neuralink.com/careers/). Its active listings resolve to a Neuralink Greenhouse board. A bounded read of the [official Greenhouse public board API](https://boards-api.greenhouse.io/v1/boards/neuralink/jobs?content=true) returned 80 current jobs and contained each of the six requested job IDs. The corresponding Greenhouse detail pages contain Neuralink's description, location, compensation, requirements, and application screening questions.

### Requested-role audit

| Official ID | Current status | Role / location | Research-relevant duties | Education / experience evidence | Official compensation | On-site / work-authorization evidence |
|---|---|---|---|---|---|---|
| `6594261003` | `CONFIRMED_LISTED` | [Machine Learning Engineer Intern](https://job-boards.greenhouse.io/neuralink/jobs/6594261003), South San Francisco | Develop neural decoders for BCI control; build ML solutions and BCI features; analyze complex data. Preferred experience includes time-series or other unstructured data. | The posting requires evidence of high-impact academic or industry projects, ML model development, ML fundamentals, analysis, communication, and coding. It does **not** state a degree requirement. The application asks graduation year and prior internship/co-op experience. | USD 35/hour in California | The application states the internship is on-site and that relocation assistance is not available. It asks whether the applicant is currently authorized to work in the US and whether future sponsorship will be required. These questions do not promise sponsorship or establish eligibility. |
| `7483748003` | `CONFIRMED_LISTED` | [Neuroengineer Intern](https://job-boards.greenhouse.io/neuralink/jobs/7483748003), South San Francisco | Map neural correlates and build ML architectures from neural activity to multidimensional outputs; work spans non-human-primate electrophysiology and human fMRI. Preferred evidence includes population dynamics/manifolds, movement or speech decoding, human fMRI, in-vivo electrophysiology, and closed-loop BCI. | Exceptional ability in neuroscience, ML, biomedical engineering, or a related field; at least 2 years of academic or industry experience; scientific method and Python. No explicit degree requirement is stated. | USD 35/hour in California | On-site internship; no relocation assistance. Application asks current US work authorization and future sponsorship need. |
| `5663271003` | `CONFIRMED_LISTED` | [Machine Learning Engineer](https://job-boards.greenhouse.io/neuralink/jobs/5663271003), Austin or South San Francisco | Decode virtual-arm control and brain-to-voice; train on more than 50,000 hours of neural data; address distribution drift, online adaptation, model compression, self-supervised neural representations, reinforcement learning, evaluation, and rollout. | Bachelor's degree or higher in computer science or a related field, or equivalent experience; evidence of shipped real-time ML and sequence modeling. No minimum number of years is stated. | USD 129,000-331,000 base salary | The description states five days per week on-site. The application asks future sponsorship need and on-site willingness; it does not establish a sponsorship policy. |
| `7571489003` | `CONFIRMED_LISTED` | [Neuroengineer, Next Gen](https://job-boards.greenhouse.io/neuralink/jobs/7571489003), Austin or South San Francisco | Build computational models and encoding strategies for electrical stimulation; run recording/stimulation experiments; work on prosthetic vision, machine vision, smart glasses, eye tracking, and participant research sessions. | Exceptional ability in neuroscience, biomedical/electrical engineering, ML, or a related field; at least 4 years of academic or industry experience; Python. Preferred evidence includes neural stimulation, statistics/ML, NEURON or finite-element modeling, and in-vivo electrophysiology/closed-loop BCI. | USD 122,000-226,000 base salary | Application asks current US work authorization, future sponsorship need, on-site willingness, and location/relocation. No sponsorship promise is made. |
| `6681863003` | `CONFIRMED_LISTED` | [Signal Processing Engineer](https://job-boards.greenhouse.io/neuralink/jobs/6681863003), Austin or South San Francisco | Develop embedded/on-chip DSP for cortical sensing, spike detection, electrode health, compression, fixed-point/quantized algorithms, and hardware mapping. | BS, MS, or PhD in electrical/computer engineering, signal processing, or related field; at least 3 years of DSP algorithm/product experience; Python and C. | USD 121,000-230,500 base salary | Application asks current US work authorization, future sponsorship need, and on-site willingness. No sponsorship promise is made. |
| `6596365003` | `CONFIRMED_LISTED` | [Software Engineer, BCI Applications](https://job-boards.greenhouse.io/neuralink/jobs/6596365003), Austin or South San Francisco | Build native applications that turn live neural streams into device control with sub-15 ms latency; develop interaction paradigms for cursor, text, and speech and integrate with operating-system accessibility APIs. | BS in computer science or a related field, or equivalent experience. The posting says it hires from junior through senior levels and requires strong CS fundamentals plus shipped production or open-source software. It does not require neuroscience experience. | USD 128,000-281,000 base salary | Five days per week on-site. Application asks future sponsorship need and on-site willingness; it does not establish a sponsorship policy. |

### Interpretation boundaries

- The two intern roles and four full-time roles above are current-index confirmed, not inferred from accessible legacy pages.
- Current index membership establishes availability on the careers surface, not user eligibility or a recent posting date. Greenhouse's `updated_at` metadata is an ATS modification timestamp and must not be transformed into `Posted_At`.
- Employer screening questions are evidence that authorization/sponsorship is evaluated. They are not evidence that Neuralink will sponsor a particular role or applicant.
- The BCI Applications role is product/application software in a BCI context. Employer domain alone must not turn it into a research-direct classification.

## Precision Neuroscience

### Index and ATS provenance

Precision's [official careers page](https://www.precisionneuro.io/careers) links applicants to the [Precision Neuroscience Kula careers index](https://careers.kula.ai/precision-neuroscience). The linked index currently lists ten roles: Full-Stack Software Engineer; Senior Mechanical Engineer; Senior Quality Reliability Engineer; DSP Algorithm Engineer; R&D Senior Process Engineer; Senior Director, Brand & Communications; Director, Business Development; Senior Human Factors Engineer; Firmware Engineer; and Senior Director, Mechanical Engineering and Surgical. This direct employer-to-ATS link, consistent employer identity, and organization-specific index establish the Kula pages as the active official recruitment surface.

### Research-relevant current listings

#### DSP Algorithm Engineer — `39009-dsp-algorithm-engineer`

**Status:** `CONFIRMED_LISTED`  
**Official detail:** [Precision Kula job page](https://careers.kula.ai/precision-neuroscience/39009-dsp-algorithm-engineer)

- Full-time, Electronics, on-site; Chicago, Framingham, New York, or Santa Clara.
- USD 155,000-185,000 per year.
- Owns algorithms across the signal chain from sensors to ML feature extraction, including adaptive filtering and translating bench models into practical implementations.
- Evidence requested includes DSP/statistical signal processing, control, Python, MATLAB/Simulink/SystemC/SystemVerilog, embedded fixed-point implementation, and working PyTorch knowledge; on-device ML is a plus.
- The current page does not state a minimum degree or number of years, so neither should be inferred.
- Exact geographic/authorization restriction: Precision says it cannot consider remote workers or people who are not currently based in the US and legally authorized to work in the US. The page does not promise sponsorship.

This is a strong BCI/neural-signal method match, but the stated function is algorithm and product engineering rather than automatically `RESEARCH_DIRECT`.

#### Full-Stack Software Engineer — `25805-full-stack-software-engineer`

**Status:** `CONFIRMED_LISTED`  
**Official detail:** [Precision Kula job page](https://careers.kula.ai/precision-neuroscience/25805-full-stack-software-engineer)

- Full-time, Software, hybrid; Santa Clara, Addison, Indianapolis, New York, or Chicago.
- USD 168,000-210,000 per year.
- Builds clinical user experiences and a cloud platform, renders high-frequency physiological data, develops APIs/data models, prototypes, and works under IEC 62304; up to 10% travel.
- Requires a bachelor's degree or equivalent in CS, computer engineering, or related discipline, at least 3 years of full-stack experience, and at least 1 year using commercial AI tooling; regulated-product experience is also requested.
- Same exact restriction: no remote applicants and no applicants who are not currently US-based and legally authorized to work in the US.

This is a BCI platform/product role with transferable engineering value, not evidence of neural-decoding research responsibility.

#### Senior Human Factors Engineer — `54912-senior-human-factors-engineer`

**Status:** `CONFIRMED_LISTED`  
**Official detail:** [Precision Kula job page](https://careers.kula.ai/precision-neuroscience/54912-senior-human-factors-engineer)

- Full-time, Product, hybrid; Santa Clara; USD 150,000-175,000 per year.
- Owns human-factors and usability research for the Layer 7 platform, including formative and summative usability studies, task and use-related risk analysis, clinical/user workflows, and human-subject research; up to 10% travel.
- Requires 3-6 years of human-factors/usability research in regulated medical devices and a bachelor's or master's degree in human factors engineering, biomedical/industrial engineering, HCI, cognitive science, or related field.
- Same current-US-base and legal-work-authorization restriction; the page does not promise sponsorship.

This is the strongest additional Human-AI/HCI research-method listing on the current Precision index, but it is senior and regulated-clinical-product oriented. It should not be presented as near-term eligibility.

### Index/detail semantics

All three reviewed roles are present on the current Kula organization index and therefore `CONFIRMED_LISTED`. If a Kula detail page later remains accessible after disappearing from that index, it must be downgraded to `DETAIL_PAGE_ACCESSIBLE_ONLY` until the official current index confirms it again. A temporary failure of either page is `SOURCE_UNAVAILABLE`, not `CONFIRMED_CLOSED`.

## Synchron

### Current index and ADP provenance

Synchron's [first-party careers page](https://synchron.com/careers) is itself the current index. Its listed job links point to organization-specific ADP Workforce Now pages, establishing ADP as Synchron's official ATS. The current San Diego index lists seven roles: Principal Mechanical Engineer; ASIC Technical Lead; AFE Test & Integration Engineer; Senior Accountant; Microfabrication Technician; Senior Quality Engineer, New Product Development; and Senior Director, Regulatory Affairs.

The ADP detail interface returned only its normal supported-browser shell to bounded non-browser retrieval. Accordingly, current listing status is verified from Synchron's first-party index, while detailed requirements are `SOURCE_UNAVAILABLE` through this retrieval method. No attempt was made to bypass the interface.

### Cognition Lab status

Synchron's official New York section describes a cognition lab working on neural signals and models of human thought, including machine learning, data/software engineering, neuroscience, HCI, real-time neural pipelines, closed-loop neurofeedback, model serving, Apple-native applications, and scaling laws for brain data. The same current page explicitly says **“No current openings here. Express interest.”**

Result: `SUCCESS_NO_MATCHES` for a current cognition-lab vacancy. “Express interest” is a general talent-contact route, not a `CONFIRMED_JOB_OPENING`. The research-team description may support an informational research-team profile, but it must remain separate from opportunity records.

None of the seven San Diego titles is a clear computational-neuroscience, neural-decoding, or cognition-lab research opening. Employer relevance alone is insufficient to promote them.

## Recommended bounded pilots

1. **Neuralink Greenhouse — feasible.** The current-index API and official details provide stable ATS IDs, explicit requirements, location, compensation, and authorization screening. A pilot should cap index candidates and detail requests, preserve the index/detail distinction, and never convert Greenhouse update timestamps into posting dates.
2. **Precision Kula — feasible.** The active index and detail pages are readable and evidence-rich. A pilot should ingest only roles present on the current Kula index, preserve the exact US-based/legal-authorization language, and apply role-function and career-stage gates independently of employer domain.
3. **Synchron — informational/index-health pilot only for now.** The first-party index is reliable enough to detect titles and the explicit cognition-lab no-match state, but the normal HTTP path does not yield usable ADP detail evidence. Do not fabricate fields or treat general “express interest” language as a vacancy.

## Safety conclusions

- Current-index membership and detail-page accessibility are separate facts. Every role marked `CONFIRMED_LISTED` above has both current-index evidence and an official detail page.
- Absence, a blocked detail renderer, or a transient network error cannot establish closure.
- No official posting dates were verified in this review. ATS update metadata is not a substitute.
- No visa sponsorship conclusion is supported. Neuralink asks screening questions; Precision expressly requires current US base and legal work authorization; neither fact should be expanded beyond its text.
- No production registry, workflow, cloud state, Google Sheet, or external account was modified during this review.
