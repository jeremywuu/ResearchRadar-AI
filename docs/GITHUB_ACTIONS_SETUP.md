# GitHub Actions weekly monitoring setup

This guide prepares the private-repository, read-only cloud pilot implemented by
`.github/workflows/weekly-monitoring.yml`. It does not authorize unattended Google Sheets writes
or create any Google Cloud resources.

Platform behavior and allowances were checked against the linked official documentation on
2026-10-13. Recheck them before provisioning because action versions, quotas, and billing terms can
change.

## 1. Private repository preparation

1. Create a private GitHub repository only after separate authorization.
2. Push the default branch containing this workflow.
3. In **Settings → Secrets and variables → Actions → Variables**, use repository variables for
   the three non-secret configuration values listed below.
4. In **Settings → Actions → General**, allow the official actions used by the workflow.
5. Set a spending budget or disable paid overages as appropriate for the account.

The initial deployment is compatible with a private repository on GitHub Free and therefore does
not use a GitHub Environment. GitHub currently requires Pro, Team, or Enterprise for environment
secrets, environment variables, and deployment-branch controls in private repositories. The WIF
condition and an in-workflow preflight instead restrict the identity to the exact repository,
`main` branch, and workflow file. Recheck GitHub's official environment documentation before
changing this design.

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
Both jobs are pinned to `ubuntu-24.04` for the initial production period so a future
`ubuntu-latest` migration cannot silently change the runner image. Review this pin during routine
maintenance. The official checkout, Python setup, Google authentication, and artifact actions use
Node.js 24-compatible major versions; report artifacts use `actions/upload-artifact@v7`.

## 3. Manual execution and weekly schedule

The scheduled production monitoring is active alongside manual dispatch:

```yaml
schedule:
  - cron: "0 9 * * 1"
    timezone: "Europe/Brussels"
workflow_dispatch:
```

GitHub supports an IANA `timezone` on scheduled workflows, so this represents Monday 09:00 in
Brussels across daylight-saving transitions. Scheduled workflows are best-effort and may start
later than the nominal time. They run from the latest commit on the default branch. See the
official [workflow syntax documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
To run manually, open **Actions → ResearchRadar Weekly Monitoring → Run workflow** and select
`main`; the workflow refuses Google authentication from another repository, branch, or workflow
path. The latest scheduled or manual run appears at the top of the workflow's run list; open it to
read the job summary and download its private brief from **Artifacts**.

## 4. Google Workload Identity Federation

Use Workload Identity Federation through a dedicated service account. Google Sheets sharing works
naturally with a service-account email, while federation avoids a downloadable service-account
key. The official [`google-github-actions/auth`](https://github.com/google-github-actions/auth)
action exports an Application Default Credentials file, which the existing Python authentication
provider discovers before the local OAuth fallback.

The project-specific, preflight-verified commands and immutable GitHub IDs are documented in
[`GOOGLE_WIF_SETUP.md`](GOOGLE_WIF_SETUP.md). Treat that file as the approval plan for Milestone
5B.2; the generic steps below are supporting context.

Complete these steps manually in a dedicated Google Cloud project:

1. Enable the Google Sheets API, IAM Service Account Credentials API, and Security Token Service
   API.
2. Create a dedicated service account, for example `researchradar-actions-reader`. Do not create a
   JSON key.
3. Create a Workload Identity Pool and GitHub OIDC provider with issuer
   `https://token.actions.githubusercontent.com/`.
4. Map at least `google.subject=assertion.sub`, `attribute.repository=assertion.repository`,
   `attribute.repository_id=assertion.repository_id`,
   `attribute.repository_owner_id=assertion.repository_owner_id`,
   `attribute.ref=assertion.ref`, and `attribute.workflow_ref=assertion.workflow_ref`.
5. Add an attribute condition for the exact repository, trusted branch, and workflow file:

```text
attribute.repository_id=='1416626708' &&
attribute.repository_owner_id=='213313923' &&
attribute.ref=='refs/heads/main' &&
attribute.workflow_ref=='jeremywuu/ResearchRadar-AI/.github/workflows/weekly-monitoring.yml@refs/heads/main'
```

The numeric repository and owner IDs are the primary trust anchors. `workflow_ref` identifies this
ordinary monitoring workflow; `job_workflow_ref` is associated with reusable workflows. GitHub
documents the claim formats in its
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

## 5. GitHub repository variables

Add these as repository-level Actions variables under **Settings → Secrets and variables →
Actions → Variables**. They identify resources but are not credentials:

| Variable | Value |
|---|---|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Full provider resource name using the project number |
| `GCP_SERVICE_ACCOUNT` | Dedicated reader service-account email |
| `GOOGLE_LIVE_PILOT_SPREADSHEET_ID` | The dedicated LIVE PILOT ID |
| `RESEARCH_RADAR_GCS_BUCKET` | `researchradar-state-310248522001-euw1` |
| `RESEARCH_RADAR_GCS_PREFIX` | `researchradar/state/v1` |
| `RESEARCH_RADAR_RESEARCH_SOURCES_ENABLED` | Leave unset or `false` until a separately authorized activation |

The workflow sets these non-secret safety values itself:

```text
RESEARCH_RADAR_SHEETS_ENV=live-pilot
RESEARCH_RADAR_DATA_MODE=live
RESEARCH_RADAR_GOOGLE_READ_ONLY=1
```

The workflow passes `RESEARCH_RADAR_RESEARCH_SOURCES_ENABLED` from repository variables. A missing
variable is safely interpreted as false. Setting it to true changes source collection and therefore
requires a separately authorized cloud acceptance run; it never changes Sheets read-only mode.

Do not add OAuth refresh tokens, ADC files, or service-account JSON as GitHub secrets.

## 6. State persistence

GitHub-hosted runners are ephemeral. The workflow therefore restores the verified schema-v2 GCS
snapshot before any source collection and commits a validated successor only after reconciliation
and a safe Sheets dry-run. GCS mode fails closed when configuration, authentication, the current
pointer, schema, or checksums are invalid; it never falls back to an empty runner directory.

| Option | Durable history | Trade-off |
|---|---|---|
| Actions artifacts | No guaranteed permanent history | Good for private review and debugging only |
| Actions cache | No | Evictable and intended for build dependencies, not records |
| Google Sheets alone | Partial | Omits unsynchronized/low-priority records and detailed source health |
| Git state branch | Durable | Requires repository write permission and conflict management |
| Private versioned GCS bucket | Yes | Recommended; small storage/operation cost is possible |

The deployed bucket uses uniform access, public-access prevention, immutable snapshot and commit
objects, and a generation-matched `current.json` pointer. Runtime IAM is bucket- and
object-condition scoped; it has no project-wide Storage role. The authoritative initial baseline
is `bootstrap-preflight-38369663706-v2` (30 jobs, one PhD programme, and two events).

## 7. Reports and artifacts

After a run:

1. Open the workflow run in the repository's **Actions** tab.
2. Read the Markdown brief in the job summary.
3. Download `researchradar-weekly-RUN_ID` from the run's **Artifacts** section.

The artifact contains the brief, restored/reconciled snapshot, dry-run review, and fingerprint.
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
change. Configure a budget; do not assume the workflow is permanently zero-cost. The small GCS
JSON state also incurs regional storage and Class A/B operation charges, expected to remain small
at weekly cadence but still subject to current Google Cloud pricing.

## 9. Troubleshooting

- **Missing cloud configuration:** set all five repository variables above.
- **OIDC permission denied:** verify `id-token: write`, the full provider resource name, attribute
  mappings, numeric repository/owner IDs, ref/workflow conditions, and
  `roles/iam.workloadIdentityUser`.
- **Spreadsheet 403:** share only LIVE PILOT with the service-account email as Viewer and confirm
  the Sheets API is enabled.
- **Workbook identity failure:** confirm the ID and exact title `ResearchRadar AI — LIVE PILOT`.
- **Source BLOCKED/FAILED:** inspect the report; do not bypass 403, robots rules, CAPTCHA, or
  anti-bot controls.
- **No durable baseline:** this is a hard failure in configured GCS mode. Verify the bucket,
  prefix, WIF identity, pointer, manifest, and checksums; never bootstrap automatically.
- **Workflow does not run:** scheduled workflows execute from the default branch; verify Actions is
  enabled and the workflow is present there.

## 10. Security boundaries

- No unattended Sheets apply path.
- No TEST or production spreadsheet ID in the workflow.
- No long-lived Google credential.
- No feedback notes in logs or reports.
- No paid search, LLM, or database service.
- No source-access bypass.
- Durable-state permissions are confined to the approved prefix and exact mutable pointer.
