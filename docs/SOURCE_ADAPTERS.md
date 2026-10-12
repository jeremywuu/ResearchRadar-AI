# Official source adapters

## Contract

Every adapter exposes a `SourceDescriptor` and a read-only `collect(observed_at=...)` operation.
The descriptor provides a stable source ID, organization, category, official source URL,
retrieval URL/method, and source-verification state. Collection returns `SourceCollectionResult`
with source health, extraction status, retrieval timestamps, counts, HTTP statuses, errors, and
bounded extracted records.

Coverage counters have distinct meanings: `records_fetched` is the population returned by the
source, `records_matched` is the complete deterministic title-filter result,
`records_considered` is the bounded set selected for detail extraction, `records_extracted` is the
parsed candidate count, and `records_accepted` is the downstream pipeline count. These must not be
collapsed into a claim about total source coverage.

The states are independent:

- `VERIFIED_OFFICIAL` means the organization controls or explicitly links the source.
- `SourceHealth` describes this adapter run; `SUCCESS_NO_MATCHES` is not a failure.
- `OpportunityStatus` requires source evidence about a specific opening or event.

## Initial sources

### Anthropic jobs

Anthropic's official careers page links roles on the `anthropic` Greenhouse board. The adapter
uses Greenhouse's public, unauthenticated GET API: one lightweight `content=false` list request,
then at most 25 detail requests. A fresh-observation run prioritizes up to 20 previously tracked
official IDs and reserves up to five slots for new deterministic title matches; unused new slots
are filled by tracked roles. The bound limits payload and request volume and means an omitted role
cannot be treated as closed. Job IDs and canonical Greenhouse URLs provide source-owned identity.
Unknown language and compensation remain unknown.

### UCL Gatsby PhD programme

The adapter targets the official UCL programme page and extracts only explicit application-open,
cycle, deadline, funding, research-focus, and application-link evidence. An initial command-line
probe encountered a Cloudflare challenge, while the final verified collector run returned the
public page normally. The collector still reports any future 401/403 challenge as `BLOCKED`; it
does not bypass challenges or substitute an unofficial source. Recorded official-page excerpts
test parsing offline.

### COSYNE

The adapter reads only robots-permitted public HTML from the official COSYNE home, abstracts, and
workshop-call pages. Edition, meeting dates, abstract deadline, workshop-proposal deadline, and a
conditional presenter-registration deadline are stored with distinct meanings. Squarespace API
or JSON routes disallowed by robots policy are not used.

The 2027 model stores March 11–16 as the overall conference, March 11–14 as the main meeting,
and March 15–16 as the workshops. Annual editions retain distinct stable identities.

## Retrieval policy

- GET only; no applications, forms, authentication bypass, browser automation, or CAPTCHA work.
- Descriptive User-Agent, 15-second timeout, and at most three attempts with exponential backoff
  for 408, 429, 5xx, and network timeouts.
- HTML paths are checked against robots.txt. Explicit denial returns `BLOCKED`.
- 401/403 are `BLOCKED`; exhausted network, 404, malformed JSON, and parser failures are `FAILED`.
- One failed category does not prevent sibling categories from completing.
- External text is untrusted data. It is parsed as text, never executed or followed as an
  instruction.

## Cognitive-neuroscience expansion pilot

### CCN 2027

The adapter targets only `https://2027.ccneuro.org/` and requires explicit conference identity,
2027 dates, and Edinburgh location evidence. A submission deadline remains unknown unless the page
states a complete dated deadline. The initial bounded smoke run reached the page but encountered a
layout-sensitive parser miss; it was recorded as `FAILED`, not converted into an opportunity. An
authorized second bounded request on 2026-10-12 also returned official page content that did not
satisfy those deterministic extraction requirements. It therefore remained `FAILED`, emitted no
event record, and was not retried or replaced with an unofficial source. Offline parser fixtures
continue to cover the known layout variants; another live attempt requires separate authorization
and inspection of a safely bounded response fixture.

### CMU Cognitive Neuroscience PhD

The adapter verifies the official programme, admissions, and graduate-programme pages. It records
the cross-disciplinary mind/brain/behavior programme, computational and neuroimaging methods, the
general December 1 admissions information, and programme-level support statements. Because the
pages did not announce an admission year or Fall 2028 opening, the adapter emits a verified
informational programme profile and `SUCCESS_NO_MATCHES`, not a PhD opportunity.

### Neuroelectrics careers

The official Neuroelectrics careers page explicitly links the public
`neuroelectrics.jobs.personio.com` board. Only specific research-role links can become opportunity
candidates. General permanent and internship talent pools are retained as informational profiles;
they are not specific vacancies. A successful board read with only such profiles returns
`SUCCESS_NO_MATCHES`.

### Expansion backlog

`config/source_expansion.yaml` records RLDM, Synchron careers, and OHBM as
`VERIFIED_CANDIDATE`. This is a planning backlog only: none is called by the Milestone 4E pilot and
none is treated as an implemented source adapter.

## Evidence and storage

Collectors emit only bounded source facts and concise evidence strings, not arbitrary full-page
archives. Every accepted record preserves source organization, official/canonical URLs, source
type, extraction method, verification state, and retrieval time. Missing fields stay `None`.

Normalized output is written under Git-ignored `data/live/` using the existing category JSON
format. `source_metadata.json` contains source health, extraction summaries, evidence, and errors.
Nothing in this milestone writes live opportunities to Google Sheets.

## Adding an adapter

1. Prove the official relationship from a first-party page; never guess an ATS token.
2. Review robots.txt, access terms, authentication boundaries, and payload size.
3. Add a stable descriptor and inject `HttpClient` so tests need no network.
4. Extract only explicitly supported facts and concise evidence into the existing raw-record
   shape with `fictional: false`.
5. Pass records through the existing category pipeline rather than adding parallel models.
6. Add recorded/minimal fixtures for success, empty, malformed, access, retry, and missing-field
   cases.
7. Run a bounded, explicit `collect ... --live` smoke test and document actual limitations.

## TLS troubleshooting

The project uses Python `urllib`, not Requests. The default transport creates an `SSLContext` from
the project dependency `certifi`, with `CERT_REQUIRED` and hostname validation enabled. An explicit
`SSL_CERT_FILE` overrides certifi only when the operator needs an organization-approved CA bundle,
such as for an authorized HTTPS-inspecting proxy. `REQUESTS_CA_BUNDLE` does not configure urllib.

Useful diagnostics must compare the same small endpoint:

```bash
curl -o /dev/null -w '%{http_code} %{ssl_verify_result}\n' https://www.cosyne.org/robots.txt
python -c 'import ssl; print(ssl.get_default_verify_paths())'
python -c 'from research_radar.collectors.http import HttpClient; print(HttpClient(max_attempts=1).get("https://www.cosyne.org/robots.txt", accept="text/plain").status)'
```

On this Mac, the Python.org 3.11 default path
`/Library/Frameworks/Python.framework/Versions/3.11/etc/openssl/cert.pem` was absent, so its default
context loaded zero CA certificates. macOS curl succeeded through SecureTransport, and the same
Python request succeeded with the installed certifi bundle. That differential result identified a
missing Python CA path rather than an endpoint failure or visible proxy configuration. TLS
verification was never disabled and no system trust store was modified.

After repair, the ResearchRadar client reached small HTTPS endpoints for all three sources with
certificate and hostname checks enabled. In the bounded retry, Anthropic and COSYNE succeeded;
UCL completed TLS but returned HTTP 403 at the application layer and remained `BLOCKED` without a
bypass attempt.
