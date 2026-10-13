# GCS durable-state setup plan

No bucket, role, IAM binding, object, lifecycle rule, or workflow variable is created by this
milestone. Every command below is a reviewed future command, not an executed action.

## Approved preflight target

```text
project: researchradar-ai
project number: 310248522001
region: europe-west1 (Belgium)
storage class: STANDARD
proposed bucket: researchradar-state-310248522001-euw1
```

A read-only lookup on 2026-10-13 returned HTTP 404, so the name was unallocated at that moment. The
global namespace is race-prone and the check is not a reservation; repeat it immediately before
creation. Bucket names are publicly visible. Google recommends not embedding project numbers or
other identifiable information in bucket names, so retaining this exact user-proposed name requires
accepting that correlation risk. See
[bucket naming guidance](https://docs.cloud.google.com/storage/docs/buckets).

## Final proposed bucket controls

- Regional `europe-west1` Standard storage.
- Uniform bucket-level access enabled at creation.
- Public access prevention enforced at creation.
- No public principals and no object ACLs.
- Seven-day soft delete configured explicitly.
- Object Versioning disabled.
- No retention lock initially.
- No delete or storage-class-transition lifecycle rule for completed objects.
- Optional `AbortIncompleteMultipartUpload` after seven days only.
- No service-account key.

Object Versioning is unnecessary because snapshots and manifests are immutable, pointer writes are
generation-guarded, the pointer retains a bounded recovery chain, and soft delete retains recently
overwritten pointer generations for seven days. Soft-deleted bytes remain billable. An age-only
snapshot deletion rule is unsafe because it can remove content still referenced by a valid commit
manifest. See [Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning),
[soft delete](https://docs.cloud.google.com/storage/docs/soft-delete), and
[lifecycle management](https://docs.cloud.google.com/storage/docs/lifecycle).

## IAM correction

The Python adapter uses `Blob.upload_from_string` to replace `current.json`. This is an object
content insert/overwrite, not a metadata patch. Google requires both `storage.objects.create` and
`storage.objects.delete` when an insert replaces an existing object. `storage.objects.update` is a
metadata permission and is not used. The implementation resolves known paths and does not list
objects, so `storage.objects.list` is also unnecessary.

Use two project-defined roles granted only on the dedicated bucket:

```text
Normal state role:
  storage.objects.get
  storage.objects.create

Exact pointer replacement role:
  storage.objects.delete
```

The normal role is conditioned to this prefix:

```cel
resource.type == 'storage.googleapis.com/Object' &&
resource.name.startsWith(
  'projects/_/buckets/researchradar-state-310248522001-euw1/objects/researchradar/state/v1/'
)
```

The delete role is conditioned to exactly one object:

```cel
resource.type == 'storage.googleapis.com/Object' &&
resource.name ==
  'projects/_/buckets/researchradar-state-310248522001-euw1/objects/researchradar/state/v1/current.json'
```

The two bindings combine only for `current.json`. The runtime cannot delete snapshots or commit
manifests. Do not grant `roles/storage.objectAdmin`, `roles/storage.objectUser`, a project-wide
Storage role, bucket administration, or IAM administration. See
[object insert permissions](https://docs.cloud.google.com/storage/docs/json_api/v1/objects/insert),
[Cloud Storage IAM](https://docs.cloud.google.com/storage/docs/access-control/iam), and
[IAM condition resource names](https://docs.cloud.google.com/iam/docs/conditions-resource-attributes).

## Service-account decision

Reuse `researchradar-reader@researchradar-ai.iam.gserviceaccount.com` for the pilot. Its WIF trust
is already restricted to the exact private repository, numeric repository and owner IDs, `main`
branch, and exact workflow. Bucket-only conditional grants keep storage authority out of project
IAM and avoid introducing a second impersonated identity into one job. It retains Viewer-only LIVE
PILOT access and the `spreadsheets.readonly` OAuth scope.

A separate state identity offers stronger duty separation but would require a second WIF
impersonation path or moving both reads into a new identity. Reconsider that design if Sheets and
state operations later move to separate workflows. No service-account keys are permitted.

## Option A versus pointer-free commits

Keep Option A: immutable snapshots plus generation-CAS `current.json`.

- Immutable objects use `ifGenerationMatch=0`.
- Pointer content is downloaded with its observed generation.
- Pointer replacement succeeds only for that same generation.
- A losing concurrent run receives HTTP 412 and cannot replace the winner.
- Interrupted immutable uploads are unreferenced orphans, never the baseline.
- The previous pointer remains valid after a failed update.
- Recovery walks up to 32 known predecessor IDs and validates schema, inventory, sizes, and hashes.
- A post-recovery commit names the snapshot actually restored as its base and rejects a base that
  is absent from the generation-matched recovery history.

A pointer-free protocol would have to list all manifests and deterministically resolve concurrent
sibling commits from the same parent. It would add branch-selection, malformed/future timestamp,
incomplete candidate, and unbounded-list behavior. A lock object would recreate a mutable pointer.
The exact-object delete condition makes Option A simpler and acceptably narrow.

## Pricing and cost risks

Current list prices checked on 2026-10-13:

- `europe-west1` regional Standard: about USD 0.020/GiB-month.
- Single-region Class A operations: USD 0.005 per 1,000.
- Single-region Class B operations: USD 0.0004 per 1,000.
- Inbound transfer: free.
- General Internet outbound transfer begins around USD 0.12/GiB in the first tier; GitHub-hosted
  runners are external to Google Cloud.
- `europe-west1` is not an Always Free Cloud Storage region.
- Soft-deleted bytes are billed like stored bytes during the seven-day retention period.

At current scale, 100 MiB costs about USD 0.00195/month to store and about USD 0.0117 for one full
Internet download. Weekly operations should remain below one cent per month. The material risks are
unbounded snapshot accumulation, unexpectedly large raw evidence, or repeated egress—not the current
33-record candidate. Preserve the existing project-scoped budget and monitor bytes, Class A calls,
and outbound transfer. Pricing can change; verify the
[current Cloud Storage pricing table](https://cloud.google.com/storage/pricing) before creation.

## Exact provisioning commands — do not execute yet

```bash
gcloud storage buckets describe \
  gs://researchradar-state-310248522001-euw1

gcloud storage buckets create \
  gs://researchradar-state-310248522001-euw1 \
  --project=researchradar-ai \
  --location=europe-west1 \
  --default-storage-class=STANDARD \
  --uniform-bucket-level-access \
  --public-access-prevention \
  --soft-delete-duration=7d

gcloud storage buckets update \
  gs://researchradar-state-310248522001-euw1 \
  --no-versioning

gcloud iam roles create researchRadarStateObjectWriter \
  --project=researchradar-ai \
  --title="ResearchRadar State Object Writer" \
  --description="Read and create immutable ResearchRadar state objects" \
  --permissions=storage.objects.get,storage.objects.create \
  --stage=GA

gcloud iam roles create researchRadarStatePointerDelete \
  --project=researchradar-ai \
  --title="ResearchRadar State Pointer Replacer" \
  --description="Delete only the ResearchRadar current pointer during CAS replacement" \
  --permissions=storage.objects.delete \
  --stage=GA

gcloud storage buckets add-iam-policy-binding \
  gs://researchradar-state-310248522001-euw1 \
  --member=serviceAccount:researchradar-reader@researchradar-ai.iam.gserviceaccount.com \
  --role=projects/researchradar-ai/roles/researchRadarStateObjectWriter \
  --condition="title=researchradar-state-prefix,expression=resource.type == 'storage.googleapis.com/Object' && resource.name.startsWith('projects/_/buckets/researchradar-state-310248522001-euw1/objects/researchradar/state/v1/')"

gcloud storage buckets add-iam-policy-binding \
  gs://researchradar-state-310248522001-euw1 \
  --member=serviceAccount:researchradar-reader@researchradar-ai.iam.gserviceaccount.com \
  --role=projects/researchradar-ai/roles/researchRadarStatePointerDelete \
  --condition="title=researchradar-current-pointer-only,expression=resource.type == 'storage.googleapis.com/Object' && resource.name == 'projects/_/buckets/researchradar-state-310248522001-euw1/objects/researchradar/state/v1/current.json'"
```

No lifecycle command is included because the initial policy deliberately deletes no completed
objects. Add an incomplete-multipart rule only after reviewing its exact JSON separately.

## Future workflow configuration

After bootstrap approval, add these repository variables:

```text
RESEARCH_RADAR_GCS_BUCKET=researchradar-state-310248522001-euw1
RESEARCH_RADAR_GCS_PREFIX=researchradar/state/v1
```

Install `.[sheets,gcs]` and add `--state-backend gcs` to `weekly-run`. Keep OIDC/WIF,
`spreadsheets.readonly`, `workflow_dispatch`, and the complete absence of Sheets `--apply`. Do not
enable scheduling in the same change as bootstrap migration.

## Provisioning acceptance checks

1. Name lookup still returns 404 immediately before creation.
2. Location is `EUROPE-WEST1`, class is `STANDARD`, uniform access is enabled, and public access
   prevention is `enforced`.
3. Soft delete is seven days and Object Versioning is disabled.
4. Runtime identity has no project-wide Storage role and no user-managed key.
5. Prefix role contains only get/create; pointer role contains only exact-object-conditioned delete.
6. Immutable create/read succeeds; overwriting or deleting a snapshot is denied.
7. Pointer generation-0 bootstrap and current-generation replacement succeed; stale generation
   fails with HTTP 412.
8. The approved bootstrap checksum and inventory match after readback.
9. TEST and production spreadsheets remain inaccessible.
10. Scheduling remains disabled until a separate manual restore smoke test succeeds.

