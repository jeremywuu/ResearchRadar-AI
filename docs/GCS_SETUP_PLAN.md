# GCS durable-state setup plan

No bucket, IAM role, service account, or workflow variable is created by this milestone. This plan
is for a separate approval and provisioning step.

## Location decision required

Choose one location before provisioning; ResearchRadar does not choose it silently.

| Option | Candidate | Cost profile | Residency and operations |
|---|---|---|---|
| US regional | `us-central1` | Eligible for the Cloud Storage Always Free storage/operation quotas when the account and usage qualify | Data resides in the US; cloud runner access is straightforward, but the project owner and primary use are in Europe |
| European regional | `europe-west1` (Belgium) | No Cloud Storage Always Free storage allowance; Standard storage and small request charges apply | Data remains in Belgium and aligns with the operator's location |

At current public list pricing, regional Standard storage is approximately USD 0.02 per GiB-month
in common regions. A 100 MiB state history is therefore roughly USD 0.002/month before operations,
soft-delete retention, and versioning overhead. Weekly snapshots should remain well below one
dollar per year at this scale, but pricing and free-tier eligibility must be rechecked immediately
before provisioning. The US Always Free allowance currently applies only to `us-west1`,
`us-central1`, and `us-east1`, subject to account and quota conditions.

References: [Cloud Storage pricing](https://cloud.google.com/storage/pricing) and
[bucket locations](https://docs.cloud.google.com/storage/docs/bucket-locations).

## Proposed bucket controls

- Globally unique bucket name chosen during the approved provisioning step.
- Project: `researchradar-ai` (`310248522001`).
- Standard storage class in the approved single region.
- Uniform bucket-level access enabled.
- Public access prevention enforced.
- No public principals and no object ACLs.
- Object Versioning enabled to retain previous generations of the mutable `current.json` pointer.
- Default soft delete retained initially for recovery, with its ongoing storage cost acknowledged.
- No retention lock until restore and lifecycle behavior have been proven.
- No automatic deletion of committed snapshots during the pilot.
- A later lifecycle rule may delete noncurrent pointer generations after 30 days and abandoned
  multipart uploads. Committed snapshot retention requires a separate policy decision because
  deleting snapshot objects makes their old manifests unrestorable.

Object Versioning and soft-deleted data are billable. Lifecycle actions are asynchronous, and
soft-delete retention can continue charges after a lifecycle deletion. See
[Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning),
[soft delete](https://docs.cloud.google.com/storage/docs/soft-delete), and
[lifecycle management](https://docs.cloud.google.com/storage/docs/lifecycle).

## Runtime identity and minimum permissions

Two designs were evaluated:

1. Reuse `researchradar-reader@researchradar-ai.iam.gserviceaccount.com` and grant it a custom role
   on only the dedicated state bucket.
2. Create a second state-only service account and add a separately restricted WIF impersonation
   path.

The safer practical pilot is option 1 with a bucket-scoped custom role. The existing WIF provider
already binds the exact repository, numeric owner/repository IDs, `main` branch, and exact workflow;
the bucket binding adds resource isolation without introducing a second cloud identity into one
job. A second identity offers stronger duty separation and should be reconsidered if Sheets and
state access later move to different workflows.

The proposed custom role contains only:

```text
storage.objects.get
storage.objects.list
storage.objects.create
storage.objects.update
```

`update` is needed only for generation-guarded replacement of `current.json`. The runtime does not
need object delete, bucket create/delete, IAM administration, or project-wide Storage Admin. The
predefined `roles/storage.objectUser` is operationally convenient but broader because it includes
delete and additional object operations, so it is not the preferred runtime grant. IAM may be
granted at bucket scope; see [Cloud Storage IAM](https://docs.cloud.google.com/storage/docs/access-control/iam)
and [Cloud Storage roles](https://docs.cloud.google.com/storage/docs/access-control/iam-roles).

Provisioning the bucket, custom role, bucket IAM binding, lifecycle, and workflow variables all
require a later explicit authorization. No service-account key is needed or permitted.

## Future workflow configuration

After bootstrap approval, add these repository variables:

```text
RESEARCH_RADAR_GCS_BUCKET=<approved globally unique bucket name>
RESEARCH_RADAR_GCS_PREFIX=researchradar/state/v1
```

Install the project with `.[sheets,gcs]` and append `--state-backend gcs` to `weekly-run`. Keep the
existing OIDC/WIF authentication, read-only Sheets scope, `workflow_dispatch`, and absence of every
Sheets `--apply` command. Do not enable the schedule in the same change as initial state migration.

## Provisioning acceptance checks

- Exact project, location, bucket, and public-access controls match the approved plan.
- Runtime identity has only the approved bucket-level object permissions.
- No service-account keys exist.
- A create-only object test, read/list test, pointer CAS test, and forbidden delete test pass.
- TEST and production spreadsheets remain inaccessible.
- The first bootstrap manifest is reviewed before upload.
- A second read-only workflow run restores the same checksum before scheduling is considered.

