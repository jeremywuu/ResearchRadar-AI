# GitHub Actions weekly monitoring setup

This guide prepares the private-repository, read-only cloud pilot implemented by
`.github/workflows/weekly-monitoring.yml`. It does not authorize unattended Google Sheets writes
or create any Google Cloud resources.

Platform behavior and allowances were checked against the linked official documentation on
2026-10-12. Recheck them before provisioning because action versions, quotas, and billing terms can
change.

## 1. Private repository preparation

1. Create a private GitHub repository only after separate authorization.
2. Push the default branch containing this workflow.
3. In **Settings → Environments**, create `live-pilot-read-only`.
4. Restrict deployment branches to the trusted default branch. Do not add required reviewers if
   Monday runs must remain unattended.
5. In **Settings → Actions → General**, allow the official actions used by the workflow.
6. Set a spending budget or disable paid overages as appropriate for the account.

The workflow itself grants `contents: read`; only the monitoring job receives `id-token: write`,
which is required to request a GitHub OIDC token. It never receives `contents: write`.

## 2. Workflow architecture

The workflow has two jobs:

1. `test`: installs the offline development dependencies, validates YAML, runs pytest, and runs
   Ruff. It has no Google identity.
2. `monitor`: waits for `test`, obtains short-lived Google credentials through OIDC, collects only
   the six already implemented official adapters, reads LIVE PILOT, generates an incremental
   dry-run, writes a Markdown job summary, and uploads a private 14-day artifact.

The workflow-level concurrency group permits only one active monitoring run for a given ref.
Jobs have 15- and 35-minute limits. There is no `--apply` command in the workflow.

## 3. Schedule and manual execution

GitHub now supports an IANA `timezone` on scheduled workflows. The configured schedule is Monday
09:00 in Brussels, including daylight-saving transitions:

```yaml
schedule:
  - cron: "0 9 * * 1"
    timezone: "Europe/Brussels"
workflow_dispatch:
```

Scheduled workflows run from the latest commit on the default branch. See the official
[workflow syntax documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
To run manually, open **Actions → ResearchRadar Weekly Monitoring → Run workflow** and select the
trusted branch.

## 4. Google Workload Identity Federation

Use Workload Identity Federation through a dedicated service account. Google Sheets sharing works
naturally with a service-account email, while federation avoids a downloadable service-account
key. The official [`google-github-actions/auth`](https://github.com/google-github-actions/auth)
action exports an Application Default Credentials file, which the existing Python authentication
provider discovers before the local OAuth fallback.

Complete these steps manually in a dedicated Google Cloud project:

1. Enable the Google Sheets API, IAM Service Account Credentials API, and Security Token Service
   API.
2. Create a dedicated service account, for example `researchradar-actions-reader`. Do not create a
   JSON key.
3. Create a Workload Identity Pool and GitHub OIDC provider with issuer
   `https://token.actions.githubusercontent.com/`.
4. Map at least `google.subject=assertion.sub`, `attribute.repository=assertion.repository`,
   `attribute.ref=assertion.ref`, and `attribute.environment=assertion.environment`.
5. Add an attribute condition for the exact repository, trusted branch, and environment, for
   example:

```text
assertion.repository=='OWNER/REPOSITORY' &&
assertion.ref=='refs/heads/main' &&
assertion.environment=='live-pilot-read-only'
```

For repositories using GitHub's immutable OIDC subjects, also verify the repository and owner IDs
shown in the token. GitHub documents the claim formats in its
[OIDC reference](https://docs.github.com/en/actions/reference/security/oidc). Google recommends
tenant/repository restrictions to prevent confused-deputy access in its
[deployment-pipeline WIF guide](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).

6. Grant the exact federated principal `roles/iam.workloadIdentityUser` on only this service
   account.
7. Open **ResearchRadar AI — LIVE PILOT** in Google Sheets and share it with the service-account
   email as **Viewer**, not Editor.
8. Do not share the synthetic TEST workbook with this identity.

No project-wide Google Sheets IAM role is required. Spreadsheet access is constrained by the
file's Viewer sharing permission, and the workflow additionally requests the
`spreadsheets.readonly` OAuth scope.

## 5. GitHub environment variables

Add these as variables on the `live-pilot-read-only` GitHub environment:

| Variable | Value |
|---|---|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Full provider resource name using the project number |
| `GCP_SERVICE_ACCOUNT` | Dedicated reader service-account email |
| `GOOGLE_LIVE_PILOT_SPREADSHEET_ID` | The dedicated LIVE PILOT ID |

The workflow sets these non-secret safety values itself:

```text
RESEARCH_RADAR_SHEETS_ENV=live-pilot
RESEARCH_RADAR_DATA_MODE=live
RESEARCH_RADAR_GOOGLE_READ_ONLY=1
```

Do not add OAuth refresh tokens, ADC files, or service-account JSON as GitHub secrets.

## 6. State persistence

GitHub-hosted runners are ephemeral. The ignored local `data/live/` directory is not present on a
new runner, so the first pilot can collect and compare current candidates with LIVE PILOT but
cannot reliably classify every record as new, changed, or not observed across runs.

| Option | Durable history | Trade-off |
|---|---|---|
| Actions artifacts | No guaranteed permanent history | Good for private review and debugging only |
| Actions cache | No | Evictable and intended for build dependencies, not records |
| Google Sheets alone | Partial | Omits unsynchronized/low-priority records and detailed source health |
| Git state branch | Durable | Requires repository write permission and conflict management |
| Private versioned GCS bucket | Yes | Recommended; small storage/operation cost is possible |

The recommended next step is a private GCS bucket with uniform access, object versioning or
immutable timestamped snapshots, lifecycle deletion, and generation-match preconditions. Store the
four current snapshot files under a stable prefix and archive prior generations under timestamped
paths. Grant the workflow identity bucket-scoped object read/create/update permissions only; do
not grant broad project storage roles. This backend is deliberately not provisioned or used in
Milestone 5A.

Until that backend is configured, every weekly brief states that durable cross-run change
detection is unavailable. The uploaded current snapshot must not be treated as authoritative
permanent history.

## 7. Reports and artifacts

After a run:

1. Open the workflow run in the repository's **Actions** tab.
2. Read the Markdown brief in the job summary.
3. Download `researchradar-weekly-RUN_ID` from the run's **Artifacts** section.

The artifact contains the brief, current local snapshot, dry-run review, and fingerprint artifact.
It is retained for 14 days. GitHub supports per-artifact `retention-days`; see
[artifact storage documentation](https://docs.github.com/actions/configuring-and-managing-workflows/persisting-workflow-data-using-artifacts).
Feedback notes are never rendered in the report or job summary.

## 8. Expected usage and cost

A weekly run uses two standard Ubuntu jobs. Based on the current local suite and six bounded source
adapters, a reasonable initial estimate is roughly 4–12 runner minutes per week, or 20–55 minutes
per month, plus small JSON/Markdown artifacts retained for two weeks. Actual network and package
installation time must be measured in the first hosted runs.

For private repositories, current included quotas depend on the account plan. GitHub's
[Actions billing documentation](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
currently lists 2,000 minutes and 500 MB artifact storage per month for GitHub Free, and 3,000
minutes plus 1 GB for GitHub Pro. These allowances are shared with other eligible usage and can
change. Configure a budget; do not assume the workflow is permanently zero-cost. GCS is not used by
this milestone and would require a separate cost review before activation.

## 9. Troubleshooting

- **Missing provider or service account:** set all three environment variables above.
- **OIDC permission denied:** verify `id-token: write`, the full provider resource name, attribute
  mappings, repository/ref/environment conditions, and `roles/iam.workloadIdentityUser`.
- **Spreadsheet 403:** share only LIVE PILOT with the service-account email as Viewer and confirm
  the Sheets API is enabled.
- **Workbook identity failure:** confirm the ID and exact title `ResearchRadar AI — LIVE PILOT`.
- **Source BLOCKED/FAILED:** inspect the report; do not bypass 403, robots rules, CAPTCHA, or
  anti-bot controls.
- **No durable baseline:** expected in the initial pilot. Do not interpret missing records as
  closures or trust artifact retention as permanent state.
- **Workflow does not run:** scheduled workflows execute from the default branch; verify Actions is
  enabled and the workflow is present there.

## 10. Security boundaries

- No unattended Sheets apply path.
- No TEST or production spreadsheet ID in the workflow.
- No long-lived Google credential.
- No feedback notes in logs or reports.
- No paid search, LLM, or database service.
- No source-access bypass.
- No durable-state claim until a reviewed backend is configured.
