# Official source adapters

## Contract

Every adapter exposes a `SourceDescriptor` and a read-only `collect(observed_at=...)` operation.
The descriptor provides a stable source ID, organization, category, official source URL,
retrieval URL/method, and source-verification state. Collection returns `SourceCollectionResult`
with source health, extraction status, retrieval timestamps, counts, HTTP statuses, errors, and
bounded extracted records.

Coverage counters have distinct meanings: `records_fetched` is the population returned by the
source, `records_considered` is the bounded filter result considered for detail extraction,
`records_extracted` is the parsed candidate count, and `records_accepted` is the downstream
pipeline count. These must not be collapsed into a claim about total source coverage.

The states are independent:

- `VERIFIED_OFFICIAL` means the organization controls or explicitly links the source.
- `SourceHealth` describes this adapter run; `SUCCESS_NO_MATCHES` is not a failure.
- `OpportunityStatus` requires source evidence about a specific opening or event.

## Initial sources

### Anthropic jobs

Anthropic's official careers page links roles on the `anthropic` Greenhouse board. The adapter
uses Greenhouse's public, unauthenticated GET API: one lightweight `content=false` list request,
then at most 25 details whose titles match deterministic research-role terms. The bound limits
payload and request volume; it is not a quota between opportunity categories. Job IDs and
canonical Greenhouse URLs provide source-owned identity. Unknown language and compensation remain
unknown.

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

On this Mac, Python required a configured trusted CA bundle for HTTPS verification. The final
smoke test used the already-installed virtual-environment CA bundle through `SSL_CERT_FILE`; TLS
verification was never disabled. Environments with a correctly configured system trust store do
not need this override.
