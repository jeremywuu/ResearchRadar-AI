# ResearchRadar AI — Product Requirements

## Vision

ResearchRadar AI is a long-term personal academic and industry intelligence system. It finds,
evaluates, tracks, and organizes opportunities relevant to cognitive and computational
neuroscience, AI, machine learning, BCI, behavioral science, and related research careers.

The primary user interface will be Google Sheets. The intended user is a KU Leuven Master's
student planning PhD applications for Fall 2027 and Fall 2028 and a later transition into
AI research, Big Tech, BCI, neurotechnology, or psychology-related technology.

## Monitoring domains

Three category pipelines run in parallel without a fixed quota:

1. PhD opportunities
2. Industry jobs
3. Conferences and events

Each pipeline owns its discovery, processing, result, and run status. A failure in one category
must not prevent the other categories from completing.

## Geographic and language policy

- Coverage: Europe, United States, Canada, and Australia.
- Industry jobs are not ranked by proximity to Belgium.
- Jobs must be compatible with an English-speaking professional environment.
- Unknown working-language requirements are retained and flagged for review.
- Events prioritize Europe while retaining important international events.

## Opportunity policy

Industry monitoring includes research and commercial roles. Current ineligibility does not
exclude a role. Every opportunity can be classified as:

- `CURRENT_OPPORTUNITY`
- `EARLY_PHD_OPPORTUNITY`
- `FUTURE_CAREER_TARGET`
- `UNCLASSIFIED`

PhD monitoring covers programs, funded vacancies, supervisors, laboratories, PI announcements,
and recruitment signals for Fall 2027 and Fall 2028. Signals must distinguish confirmed,
upcoming, potential, historical, closed, and unknown states.

## Source-state distinctions

These states answer different questions and must never be collapsed:

1. **Source verification**: Is this an official monitoring page or an officially linked ATS?
   `VERIFIED_ACTIVE_SOURCE` means only that the source identity was verified.
2. **Adapter status**: Can the implemented collector currently retrieve and parse that source?
   Milestone 1 initializes every watchlist adapter as `NOT_IMPLEMENTED`.
3. **Opportunity status**: Does collected evidence confirm a currently open or upcoming
   opportunity? A verified source alone provides no such confirmation.

Monitoring a target is not evidence of a vacancy, admission cycle, event edition, funding, or
deadline. Every asserted fact must preserve its source URL and observation time.

## Watchlist management

The initial watchlist is stored in `config/watchlist.yaml`. Users can add, disable, remove, or
reprioritize entries without changing Python. Disabling is preferred over removal when history
exists. Official URLs must be verified before a source is activated.

## Industry job ranking

Base scoring weights:

| Factor | Weight |
|---|---:|
| Research relevance | 45% |
| PhD-level research value | 25% |
| Skills and career fit | 20% |
| Compensation | 10% |

Current eligibility is a classification input, not a relevance penalty.

## Compensation policy

The initial MVP extracts explicitly disclosed compensation, preserves the original source text,
and applies configurable aspirational annual-base-salary flags. Base salary, bonus, equity, and
total compensation are separate fields. Base salary is never compared directly with total
compensation.

Missing compensation is `NOT_DISCLOSED` and does not reduce research relevance. Percentile
benchmarking is disabled for the MVP. It may be introduced only after a sufficiently reliable,
comparable dataset exists; insufficient samples must be marked as such rather than producing a
percentile.

The initial thresholds are personal attention flags, not market benchmarks or exclusions:

- United States: USD 150,000 annual base
- Canada: CAD 130,000 annual base
- Euro area: EUR 75,000 annual base
- United Kingdom: GBP 70,000 annual base
- Australia: AUD 140,000 annual base

## Feedback and visibility

Preference feedback is one of:

- `VERY_INTERESTED`
- `INTERESTED`
- `NOT_RELEVANT`

`saved` and `hidden` are independent Boolean actions. Saving does not change relevance. Hiding
controls default visibility only and never deletes the record, feedback, or history.

The eventual ranking system must retain controlled exploratory results so feedback does not
collapse discovery onto already-known preferences.

## Schedule

The approved initial schedule is Monday at 09:00 in `Europe/Brussels`, once per week. The system
will support weekly, daily, and manual modes. Every scheduled weekly scan runs all three category
pipelines. GitHub Actions implementation belongs to Milestone 6, not Milestone 1.

## MVP scope

The MVP includes YAML-managed preferences and sources, independent category pipelines,
evidence-preserving models, deterministic normalization and deduplication, explainable scoring,
feedback-aware ranking, idempotent Google Sheets synchronization, execution logs, cost tracking,
tests, and scheduled GitHub Actions execution.

The MVP excludes a frontend, database server, automatic applications, large-scale scraping,
trained personalization models, email digests, deadline alerts, and industry trend analytics.

## Future capabilities

- PhD career intelligence
- Salary trends and reliable compensation benchmarking
- Skill-demand and company-hiring trends
- PhD-to-industry pathways
- Weekly email digests
- Deadline alerts
