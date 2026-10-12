# Milestone 5A platform research

Checked on 2026-10-12 against primary platform documentation.

## Findings

1. GitHub Actions scheduled workflows support POSIX cron plus an optional IANA `timezone`. The
   workflow can therefore express Monday 09:00 Europe/Brussels directly instead of maintaining two
   UTC schedules for daylight-saving time. Source:
   [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
2. GitHub OIDC jobs require `id-token: write`; this grants token minting rather than repository
   write permission. Environment, repository, ref, workflow, and immutable repository identity
   claims are available for trust restrictions. Source:
   [GitHub OIDC reference](https://docs.github.com/en/actions/reference/security/oidc).
3. Google recommends Workload Identity Federation for deployment pipelines rather than exported
   service-account keys, and requires tenant/repository restrictions for public multi-tenant OIDC
   issuers such as GitHub. Source:
   [Google Cloud deployment-pipeline WIF guide](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).
4. The maintained Google authentication action supports WIF and exports an ADC credential file.
   Service-account impersonation is appropriate here because Google Sheets can share the workbook
   directly with the dedicated service-account email. Source:
   [`google-github-actions/auth`](https://github.com/google-github-actions/auth).
5. Workflow artifacts can use a per-upload retention period but are run artifacts, not a durable
   monitoring database. Source:
   [GitHub artifact documentation](https://docs.github.com/actions/configuring-and-managing-workflows/persisting-workflow-data-using-artifacts).
6. Private-repository Actions minutes and artifact storage have plan-specific included quotas;
   usage beyond them can be billable. Current listed GitHub Free allowances are 2,000 minutes and
   500 MB, while GitHub Pro lists 3,000 minutes and 1 GB. Source:
   [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

## Decision

Milestone 5A uses artifacts only for 14-day private review and labels missing durable history. A
private, versioned, lifecycle-managed GCS bucket is the recommended later state backend because it
can use the same short-lived WIF trust while keeping Sheets Viewer-only. No bucket, identity, IAM
binding, or paid service is created in this milestone.
