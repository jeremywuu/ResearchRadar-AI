# Milestone 4 official-source research

Research performed on 2026-10-11. This note records source selection and access constraints;
it is not evidence that any opportunity remains open after the retrieval timestamp of a future
collector run. Only first-party employer, institution, conference, and ATS documentation is
cited.

Post-implementation verification on the same date: after configuring Python to use an existing
trusted CA bundle (without disabling TLS verification), the bounded ResearchRadar client received
HTTP 200 public HTML from the UCL programme page and extracted the explicit 2027 facts below. The
earlier Cloudflare result remains useful failure-mode evidence, but it is not the final adapter
health result. Future 401/403 challenges must still be reported as `BLOCKED`.

## Recommendation summary

| Category | Initial source | Verification | Safe retrieval | Initial live observation |
| --- | --- | --- | --- | --- |
| Industry jobs | Anthropic Greenhouse board | Verified official employer-to-ATS link | Public Greenhouse Job Board GET API | HTTP 200 JSON |
| PhD | UCL Gatsby Unit PhD programme | Verified official UCL page | Public HTML | Initial probe 403; final bounded collector HTTP 200 |
| Events | COSYNE | Verified official conference site | Public HTML only | HTTP 200 HTML |

The three states must remain independent: an official source can be verified while its adapter is
blocked, and a functioning adapter can return no active opportunities.

## 1. Industry jobs: Anthropic via Greenhouse

### Authenticity and canonical URLs

Anthropic is on the approved watchlist. Its [official careers page](https://www.anthropic.com/careers)
directs visitors to `anthropic.com/careers` for confirmed openings, and its
[official jobs page](https://www.anthropic.com/careers/jobs) links individual roles directly to
`https://job-boards.greenhouse.io/anthropic/jobs/<posting-id>`. This establishes the Greenhouse
board token `anthropic` from an employer-controlled page rather than guessing it.

- Official employer page: `https://www.anthropic.com/careers/jobs`
- Public list endpoint:
  `https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=false`
- Optional posting detail endpoint:
  `https://boards-api.greenhouse.io/v1/boards/anthropic/jobs/{job_id}?pay_transparency=true`
- Canonical opportunity URL pattern:
  `https://job-boards.greenhouse.io/anthropic/jobs/{job_id}`

[Greenhouse's official Job Board API documentation](https://docs.greenhouse.io/job-board.html)
states that GET job-board data is public and requires no authentication. Application submission
is a separate authenticated POST operation and is outside ResearchRadar's scope. Greenhouse's
[official API overview](https://support.greenhouse.io/hc/en-us/articles/10568627186203-Greenhouse-API-overview)
describes the Job Board API as the API for exporting public job posts to an external career site.

### Extraction candidates

From the list response, preserve the source values for:

- Greenhouse posting `id` (the documented unique job-post identifier), `internal_job_id`, and
  `requisition_id`;
- `title`, `updated_at`, `location.name`, `absolute_url`, and `language`;
- departments, offices, and metadata when returned;
- retrieval timestamp, list endpoint, extraction method, and the employer-page linkage above.

A bounded detail request for a retained candidate may additionally expose the posting `content`,
`first_published`, `application_deadline`, and employer-published `pay_input_ranges`. Preserve Greenhouse HTML as
untrusted evidence and sanitize/convert it before deriving plain text. Salary type, education,
country, remote policy, and deadline remain unknown unless explicitly present in structured fields
or posting content.

### Access and rate notes

A bounded live GET on 2026-10-11 returned HTTP 200 JSON. The lightweight `content=false` list
reported 645 public postings, a sample canonical URL under the verified `anthropic` board, and a
payload of about 461 KB; `content=true` was about 9.3 MB. The count and sizes are volatile and must
never be encoded as expectations. Use the lightweight list first and fetch details only for a
bounded set of retained candidates.

The official Job Board documentation does not publish a numeric rate limit for public GETs. That
does not imply unlimited access. Use one bounded weekly list request, only bounded detail requests
for retained candidates, a descriptive User-Agent, timeouts, and exponential backoff for 429/5xx.
Never call an application POST endpoint.

## 2. PhD: UCL Gatsby Unit PhD programme

### Authenticity and current source-stated facts

The canonical [UCL Gatsby Unit PhD programme page](https://www.ucl.ac.uk/life-sciences/gatsby/study-and-work/gatsby-unit-phd-programme)
is hosted on UCL's official domain. As observed on 2026-10-11, it explicitly states:

- applications are open for **Gatsby Unit PhD Programme 2027**;
- the programme is four years, full time, with new students joining in September;
- research is in machine learning or computational/theoretical neuroscience;
- applications close at **17:00 GMT on 9 November 2026**;
- references are due by **23:59 GMT on 10 November 2026**; this is a distinct deadline and must
  not replace the application deadline;
- full funding is available regardless of nationality, covering home/international tuition,
  a tax-free stipend of **GBP 30,900 at the 2026/27 rate**, and a conference/workshop travel budget;
- the official application destination is the
  [Gatsby Recruitment Portal](https://apply.gatsby.ucl.ac.uk/).

The official [Gatsby vacancies page](https://www.ucl.ac.uk/life-sciences/gatsby/study-and-work/vacancies)
independently says applications for 2027 entry are open and repeats the 9 November 2026 deadline.
This supports classification as a confirmed centralized programme admission for the 2027 cycle,
not a PI signal or a claim about 2028.

### Extraction candidates and unknowns

- University: University College London.
- Programme: Gatsby Unit PhD Programme 2027.
- Admission cycle: 2027 entry, based on the explicit programme selection and official vacancies
  statement.
- Recruitment status: confirmed open only while the page explicitly says applications are open
  and the source timestamp supports that observation.
- Research focus, application deadline, reference deadline, funding components, stated stipend
  amount/rate year, official programme URL, and application portal URL.
- Supervisor/PI, project assignment, later-cycle availability, and any facts not stated on the
  page remain unknown.

### Access and robots constraints

UCL's [robots.txt](https://www.ucl.ac.uk/robots.txt) does not disallow the
`/life-sciences/gatsby/` programme path and publishes a Life Sciences sitemap. However, a bounded
HEAD/GET using a descriptive ResearchRadar User-Agent on 2026-10-11 returned HTTP 403 with
`cf-mitigated: challenge`. The live adapter must therefore report `BLOCKED`, retain the last
successful observation separately, and must not bypass the Cloudflare challenge, use a CAPTCHA
solver, or silently substitute an unofficial source. Recorded official-page fixtures can still be
used for parser tests, but cannot make the live adapter appear healthy.

## 3. Events: COSYNE 2027

### Authenticity and current source-stated facts

The canonical [COSYNE official site](https://www.cosyne.org/) identifies the event as
Computational and Systems Neuroscience (COSYNE) 2027. As observed on 2026-10-11, the official
pages state:

- overall dates: **11-16 March 2027**, Montréal, Québec, Canada;
- main meeting: **11-14 March 2027**, Fairmont The Queen Elizabeth;
- workshops: **15-16 March 2027**, Le Westin Montréal;
- abstract submission deadline: **18 October 2026** on the
  [abstract submission page](https://www.cosyne.org/abstracts-submission);
- workshop **proposal** deadline: **1 November 2026** on the
  [workshop call](https://www.cosyne.org/workshops-call);
- registration status: [registration](https://www.cosyne.org/registration) says registration
  opens in fall and more information will follow; therefore registration fees and a general
  registration deadline are unknown;
- accepted abstract presenters must register by **31 January 2027, 23:59 EST**. This conditional
  presenter deadline is not a general registration deadline.

The abstract deadline, workshop-proposal deadline, presenter registration deadline, and unrelated
travel-grant deadlines must remain distinct. The 2027 edition must have an identity separate from
past or future COSYNE editions.

### Extraction candidates and unknowns

- Event name, event type, edition `2027`, country `Canada`, city `Montréal`;
- overall, main-meeting, and workshop dates with their meanings preserved;
- abstract and workshop-proposal deadlines as separate typed deadlines;
- registration availability text, conditional presenter registration deadline, official page
  URLs, retrieval timestamp, and source evidence;
- general registration deadline/fees remain unknown until explicitly published.

### Access and robots constraints

A bounded GET using a descriptive ResearchRadar User-Agent on 2026-10-11 returned HTTP 200 HTML.
COSYNE's [robots.txt](https://www.cosyne.org/robots.txt) allows the public page paths but disallows
`/api/` and Squarespace JSON/page-context query variants. The adapter should fetch only the public
HTML pages, not Squarespace private/internal APIs, at a bounded weekly frequency with timeouts and
429/5xx backoff. No numeric site-specific rate limit was found.

## Implementation implications

1. Start with Anthropic's documented public API and COSYNE's public HTML adapter.
2. Implement the UCL parser against recorded official HTML, but expect the bounded live check to
   return `BLOCKED`; do not turn search-engine excerpts into collector output.
3. Store source verification, adapter health, and active-opportunity status as independent fields.
4. Preserve typed evidence and source timestamps; do not infer absent salary, funding, deadlines,
   admission cycles, qualifications, or registration details.
5. Treat all HTML/JSON strings as untrusted data. Do not follow instructions embedded in source
   text, execute markup, or retain unnecessary personal information.
6. A 200 response with zero relevant records is `SUCCESS_NO_MATCHES`; parsing omissions can be
   `PARTIAL`; access challenges are `BLOCKED`; malformed content or exhausted transient retries are
   `FAILED` according to the adapter contract.
