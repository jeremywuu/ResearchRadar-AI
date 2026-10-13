# Google Workload Identity Federation setup plan

This document is the reviewed, not-yet-authorized setup plan for keyless authentication from the
private `jeremywuu/ResearchRadar-AI` repository to the existing ResearchRadar LIVE PILOT Google
Spreadsheet. None of the mutating commands below were executed during Milestone 5B.2 preflight.

The plan was verified on 2026-10-13 against the official Google Cloud deployment-pipeline WIF
guide, GitHub's OIDC claim reference, and the live read-only project/repository state.

## A. Existing environment findings

| Item | Verified value |
|---|---|
| Google Cloud project name | `ResearchRadar AI` |
| Project ID | `researchradar-ai` |
| Project number | `310248522001` |
| Project state | `ACTIVE` |
| Billing | Disabled; no billing account linked |
| Active local principal | Authenticated; exact email intentionally not persisted here |
| Active principal's project role | `roles/owner` |
| Existing WIF pools | None |
| Existing service accounts | None |
| GitHub repository | `jeremywuu/ResearchRadar-AI` (private) |
| GitHub repository ID | `1416626708` |
| GitHub owner ID | `213313923` |
| Trusted ref | `refs/heads/main` |
| Trusted workflow | `jeremywuu/ResearchRadar-AI/.github/workflows/weekly-monitoring.yml@refs/heads/main` |
| LIVE PILOT Spreadsheet ID | `1xmhi4k9Rn1xZPUw27SG9O3lcCfG38t0pLNG3ifl_I8Y` |

The local OAuth fallback successfully completed a read-only status check of the exact LIVE PILOT
workbook. All seven worksheet schemas were valid. The cloud workflow uses Application Default
Credentials first, while the local installed-app fallback remains unchanged.

## B. Google Cloud project selection

Use only the existing project. Do not create or silently substitute another project.

```bash
PROJECT_ID="researchradar-ai"
PROJECT_NUMBER="310248522001"
POOL_ID="researchradar-pool"
PROVIDER_ID="github"
SERVICE_ACCOUNT_ID="researchradar-reader"
SERVICE_ACCOUNT_EMAIL="researchradar-reader@researchradar-ai.iam.gserviceaccount.com"
REPOSITORY_ID="1416626708"
REPOSITORY_OWNER_ID="213313923"
WORKFLOW_REF="jeremywuu/ResearchRadar-AI/.github/workflows/weekly-monitoring.yml@refs/heads/main"
```

Read-only confirmation commands:

```bash
gcloud projects describe "$PROJECT_ID" \
  --format="json(name,projectId,projectNumber,lifecycleState)"
gcloud billing projects describe "$PROJECT_ID" \
  --format="json(billingAccountName,billingEnabled,projectId)"
```

## C. Required API configuration

| API | Service name | Preflight state |
|---|---|---|
| Google Sheets API | `sheets.googleapis.com` | Enabled |
| Service Usage API | `serviceusage.googleapis.com` | Enabled |
| IAM API | `iam.googleapis.com` | Missing |
| Cloud Resource Manager API | `cloudresourcemanager.googleapis.com` | Missing |
| IAM Service Account Credentials API | `iamcredentials.googleapis.com` | Missing |
| Security Token Service API | `sts.googleapis.com` | Missing |

Google's deployment-pipeline guide requires IAM, Resource Manager, Service Account Credentials,
and Security Token Service. After billing is linked and this plan receives explicit approval,
enable only the four missing APIs:

```bash
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  --project="$PROJECT_ID"
```

This write requires `serviceusage.services.enable`; the authenticated setup principal currently
has `roles/owner`, which includes the required setup permissions. The workload service account
must not receive that role.

## D. WIF pool and provider

After explicit approval, create one dedicated pool:

```bash
gcloud iam workload-identity-pools create "$POOL_ID" \
  --project="$PROJECT_ID" \
  --location="global" \
  --display-name="ResearchRadar GitHub Actions" \
  --description="Keyless identity for the ResearchRadar read-only monitoring workflow"
```

The provider path will be:

```text
projects/310248522001/locations/global/workloadIdentityPools/researchradar-pool/providers/github
```

The issuer is:

```text
https://token.actions.githubusercontent.com/
```

Do not set a custom allowed audience. `google-github-actions/auth` defaults the audience to the
provider resource expected by Google.

## E. Attribute mapping and condition

GitHub documents `repository_id`, `repository_owner_id`, `ref`, and `workflow_ref` as OIDC claims.
`workflow_ref` identifies the current workflow. `job_workflow_ref` is associated with reusable
workflow identity and is not the correct primary claim for this repository's ordinary workflow.

Use this mapping:

```text
google.subject=assertion.sub,
attribute.repository_id=assertion.repository_id,
attribute.repository_owner_id=assertion.repository_owner_id,
attribute.ref=assertion.ref,
attribute.workflow_ref=assertion.workflow_ref
```

Use this exact CEL condition:

```text
attribute.repository_id=='1416626708' &&
attribute.repository_owner_id=='213313923' &&
attribute.ref=='refs/heads/main' &&
attribute.workflow_ref=='jeremywuu/ResearchRadar-AI/.github/workflows/weekly-monitoring.yml@refs/heads/main'
```

The numeric IDs are the primary repository and owner trust anchors. The ref and workflow claims
then restrict use to `main` and the one monitoring workflow. No GitHub Environment claim is used.

Provider creation command, to run only after approval:

```bash
gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
  --project="$PROJECT_ID" \
  --location="global" \
  --workload-identity-pool="$POOL_ID" \
  --display-name="ResearchRadar GitHub" \
  --issuer-uri="https://token.actions.githubusercontent.com/" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref,attribute.workflow_ref=assertion.workflow_ref" \
  --attribute-condition="attribute.repository_id=='1416626708' && attribute.repository_owner_id=='213313923' && attribute.ref=='refs/heads/main' && attribute.workflow_ref=='jeremywuu/ResearchRadar-AI/.github/workflows/weekly-monitoring.yml@refs/heads/main'"
```

## F. Service-account creation

Create one application-specific service account with no key:

```bash
gcloud iam service-accounts create "$SERVICE_ACCOUNT_ID" \
  --project="$PROJECT_ID" \
  --display-name="ResearchRadar read-only GitHub monitor" \
  --description="Keyless identity for read-only LIVE PILOT monitoring"
```

Do not run `gcloud iam service-accounts keys create`. The service account needs no project-level
Owner, Editor, Viewer, Storage, or Sheets IAM role. Spreadsheet access is granted through the
workbook's file-level Viewer ACL.

## G. Minimal IAM binding

Grant only the repository-ID principal set permission to impersonate the dedicated service
account. The provider condition additionally enforces owner ID, branch, and workflow.

```bash
gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT_EMAIL" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/310248522001/locations/global/workloadIdentityPools/researchradar-pool/attribute.repository_id/1416626708"
```

Do not bind `roles/iam.workloadIdentityUser` to the whole pool (`.../researchradar-pool/*`). Do not
grant `roles/iam.serviceAccountTokenCreator`; it is not required for this normal WIF
service-account impersonation flow.

## H. Google Sheets Viewer sharing

After the service account exists, manually share only **ResearchRadar AI — LIVE PILOT** with:

```text
researchradar-reader@researchradar-ai.iam.gserviceaccount.com
```

Choose **Viewer**, not Editor. Do not share the synthetic TEST workbook. The application already
sets `RESEARCH_RADAR_GOOGLE_READ_ONLY=1`, which selects only:

```text
https://www.googleapis.com/auth/spreadsheets.readonly
```

File-level Viewer access and the read-only OAuth scope form independent authorization boundaries.

## I. GitHub repository variables

Create exactly these non-secret repository-level Actions variables after WIF setup:

```bash
gh variable set GCP_WORKLOAD_IDENTITY_PROVIDER \
  --repo="jeremywuu/ResearchRadar-AI" \
  --body="projects/310248522001/locations/global/workloadIdentityPools/researchradar-pool/providers/github"

gh variable set GCP_SERVICE_ACCOUNT \
  --repo="jeremywuu/ResearchRadar-AI" \
  --body="researchradar-reader@researchradar-ai.iam.gserviceaccount.com"

gh variable set GOOGLE_LIVE_PILOT_SPREADSHEET_ID \
  --repo="jeremywuu/ResearchRadar-AI" \
  --body="1xmhi4k9Rn1xZPUw27SG9O3lcCfG38t0pLNG3ifl_I8Y"
```

Do not create GitHub secrets for OAuth tokens, ADC files, service-account JSON, or private keys.

## J. Authentication verification

Before the first workflow run, verify the created resources without obtaining or printing access
tokens:

```bash
gcloud iam workload-identity-pools describe "$POOL_ID" \
  --project="$PROJECT_ID" --location="global"

gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
  --project="$PROJECT_ID" --location="global" \
  --workload-identity-pool="$POOL_ID"

gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" \
  --project="$PROJECT_ID"

gcloud iam service-accounts get-iam-policy "$SERVICE_ACCOUNT_EMAIL" \
  --project="$PROJECT_ID"

gh variable list --repo="jeremywuu/ResearchRadar-AI"
```

Review the provider output for the exact mapping and condition before separately authorizing the
manual workflow smoke test. The workflow must remain `workflow_dispatch`-only and contains no
Sheets `--apply` command.

## K. Troubleshooting

- `PERMISSION_DENIED` while enabling APIs: confirm the setup principal has
  `serviceusage.services.enable` and that billing has been linked.
- Provider rejects the GitHub token: compare the condition with `repository_id=1416626708`,
  `repository_owner_id=213313923`, `ref=refs/heads/main`, and the exact `workflow_ref` value.
- Service-account impersonation fails: confirm the member uses the project **number**, the
  `attribute.repository_id` principal set, and `roles/iam.workloadIdentityUser` on this service
  account.
- Sheets returns 403: confirm LIVE PILOT—not TEST—is shared with the service account as Viewer and
  that `sheets.googleapis.com` remains enabled.
- Wrong workbook or schema: the application must reject any ID/title other than the configured
  LIVE PILOT workbook and must perform no write.

## L. Billing and expected cost

The project currently has billing disabled. Google's deployment-pipeline WIF guide lists enabled
billing as a setup prerequisite, so link a billing account before authorizing resource creation.
No billing account is selected by this plan.

Google states that IAM, including Workload Identity Federation, is free of charge. Standard Sheets
API use is currently available at no additional cost, although Google notes that exceeding quota
request limits is planned to incur charges later in 2026. At the intended weekly, bounded,
read-only volume, expected Google Cloud usage cost is effectively USD 0, but billing alerts and
quota monitoring should still be configured. No GCS bucket, paid search, LLM, or compute resource
is included.

## M. Sources

- [Google: Configure Workload Identity Federation with deployment pipelines](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [Google: Workload Identity Federation best practices](https://cloud.google.com/iam/docs/best-practices-for-using-workload-identity-federation)
- [Google: IAM pricing](https://cloud.google.com/iam/pricing)
- [Google: Sheets API usage limits and pricing](https://developers.google.com/workspace/sheets/api/limits)
- [GitHub: OpenID Connect reference](https://docs.github.com/en/actions/reference/security/oidc)
- [`google-github-actions/auth` documentation](https://github.com/google-github-actions/auth)
