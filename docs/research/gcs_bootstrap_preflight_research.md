# GCS bootstrap preflight research

Date checked: 2026-10-13
Scope: official Google Cloud documentation and the current ResearchRadar implementation only.
No bucket, IAM binding, object, or lifecycle setting was created or changed.

## Executive finding

Keep the existing generation-guarded `current.json` design. It is materially simpler than a
pointer-free protocol and already has the right concurrency property, but the proposed permissions
were incorrect: replacing the contents of an existing Cloud Storage object requires both
`storage.objects.create` and `storage.objects.delete`. `storage.objects.update` changes object
metadata; it does not authorize replacing object contents. Google documents both rules explicitly
in its [Cloud Storage IAM permission reference](https://docs.cloud.google.com/storage/docs/access-control/iam-permissions).

The least-privilege practical design is therefore:

1. A bucket-scoped/prefix-conditioned runtime role containing `storage.objects.get` and
   `storage.objects.create` for `researchradar/state/v1/`.
2. A separate role containing only `storage.objects.delete`, bound with an IAM Condition that
   matches the exact `researchradar/state/v1/current.json` object.
3. Do not grant `storage.objects.update`; the current client does not update object metadata.
4. Do not grant `storage.objects.list` unless recovery is later changed to enumerate commits. The
   current implementation resolves known object paths and never invokes a list operation.

This keeps deletion unavailable for immutable snapshots and manifests while permitting the one
conditional pointer replacement required by the CAS protocol.

## Bucket name availability

Proposed name:

```text
researchradar-state-310248522001-euw1
```

A read-only lookup was performed with:

```bash
gcloud storage buckets describe \
  gs://researchradar-state-310248522001-euw1 \
  --format='value(name,location,storageClass)'
```

The command returned `404 ... not found`. The name is therefore unallocated as observed on
2026-10-13 and is syntactically valid. This is not a reservation: bucket names occupy one global
namespace and another party could claim the name before creation. Google also notes that bucket
names are publicly visible; the proposed name contains a project number, which Google advises not
to place in bucket names. The user explicitly proposed this name, so this is a disclosure risk to
accept or revise, not a technical blocker. See [About Cloud Storage buckets](https://docs.cloud.google.com/storage/docs/buckets).

## What the Python client actually does

`GoogleCloudStorageStateBackend` uses these calls:

| Code path | Client operation | Required object permission |
|---|---|---|
| Pointer existence, pointer/manifest/snapshot download, `Blob.reload()` | Object read/metadata get | `storage.objects.get` |
| Four immutable snapshot uploads | `Blob.upload_from_string(..., if_generation_match=0)` | `storage.objects.create` |
| Immutable commit-manifest upload | Same create-only upload | `storage.objects.create` |
| First `current.json` creation | Same upload with generation match `0` | `storage.objects.create` |
| Existing `current.json` replacement | Upload contents with the restored generation | `storage.objects.create` **and** `storage.objects.delete` |

The client method is documented as replacing existing contents when the object already exists, and
accepts `if_generation_match`; see the
[`Blob.upload_from_string` reference](https://docs.cloud.google.com/python/docs/reference/storage/latest/google.cloud.storage.blob.Blob#google_cloud_storage_blob_Blob_upload_from_string).
Generation `0` succeeds only when no live object with that name exists. A nonzero generation match
allows the replacement only when the live generation still matches and otherwise returns HTTP 412.
See [Cloud Storage request preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions).

`storage.objects.update` is explicitly a metadata permission, so it should be removed from the
planned runtime role. The implementation currently performs no object-list request, so
`storage.objects.list` is not a runtime requirement. If listing is added later, Google warns that
list permission is bucket-level and cannot be narrowed to a subset of objects using
`resource.name`; see [Cloud Storage IAM Conditions](https://docs.cloud.google.com/storage/docs/access-control/iam).

One edge case deserves documentation: for multipart/resumable uploads, the Python client can try to
delete a corrupted uploaded object after checksum failure. The proposed exact-pointer delete grant
does not allow cleanup of corrupt immutable uploads. That is acceptable for this design because
such an upload cannot become authoritative without a valid immutable manifest and a successful
pointer CAS, but the failed run ID must not be reused. The client behavior is documented in the
[`Blob.upload_from_string` checksum description](https://docs.cloud.google.com/python/docs/reference/storage/latest/google.cloud.storage.blob.Blob#google_cloud_storage_blob_Blob_upload_from_string).

## Exact conditional IAM shape

Cloud Storage supports bucket IAM Conditions using `resource.name`, but uniform bucket-level access
must be enabled first. Object resource names use
`projects/_/buckets/BUCKET/objects/OBJECT_NAME`; the underscore is required. Equality is supported,
so the delete grant can be restricted to precisely one object. See the
[IAM Conditions attribute reference](https://docs.cloud.google.com/iam/docs/conditions-attribute-reference)
and [Cloud Storage condition guidance](https://docs.cloud.google.com/storage/docs/access-control/iam).

Recommended bindings for the existing service account:

```text
serviceAccount:researchradar-reader@researchradar-ai.iam.gserviceaccount.com
```

Normal state condition:

```cel
resource.type == 'storage.googleapis.com/Object' &&
resource.name.startsWith(
  'projects/_/buckets/researchradar-state-310248522001-euw1/objects/researchradar/state/v1/'
)
```

Normal custom role permissions:

```text
storage.objects.get
storage.objects.create
```

Pointer-replacement condition:

```cel
resource.type == 'storage.googleapis.com/Object' &&
resource.name ==
  'projects/_/buckets/researchradar-state-310248522001-euw1/objects/researchradar/state/v1/current.json'
```

Pointer custom role permission:

```text
storage.objects.delete
```

The create permission from the first binding and exact delete permission from the second combine
for `current.json`. No delete permission applies to snapshot or manifest objects. Both custom roles
are defined in project `researchradar-ai`, but their grants are attached only to this bucket and
conditioned as above. Do not use `roles/storage.objectAdmin` or `roles/storage.objectUser`; the
predefined Object User role includes delete, move, restore, folder, and multipart-upload powers not
needed by this adapter. See [Cloud Storage roles](https://docs.cloud.google.com/iam/docs/roles-permissions/storage).

## Option A versus pointer-free Option B

### Option A: keep `current.json`

Properties:

- Immutable snapshot files and manifest use `ifGenerationMatch=0`.
- Pointer replacement is atomic for one object and guarded by the restored generation.
- A losing concurrent writer receives HTTP 412; its immutable objects remain unreferenced.
- An interrupted snapshot upload cannot become current because the pointer is written last.
- The previous pointer remains intact after a failed CAS.
- Reads and object listings are strongly consistent, and object writes/overwrites are atomic;
  Google documents these guarantees in [Cloud Storage consistency](https://docs.cloud.google.com/storage/docs/consistency).

Cost: one narrowly conditioned delete permission on the pointer object.

### Option B: append-only commits with no pointer

A pointer-free design would have to list all commit manifests and select a deterministic winner.
Although object listing is strongly consistent, a timestamp/run-ID ordering does not provide a
compare-and-swap link to the baseline that was restored. Two runs can create sibling commits from
the same predecessor. Additional rules would be required to select one branch, reject future-dated
or malformed commits, recover from incomplete candidates, and keep listing cost bounded as history
grows. A lock/lease object would merely recreate a mutable coordination primitive.

Recommendation: **Option A**. Exact-object conditional delete materially limits the extra privilege
and retains simpler, auditable concurrency and recovery semantics.

## Snapshot, crash, and recovery assessment

- `ifGenerationMatch=0` is the correct create-only precondition for snapshot and commit objects.
- Pointer CAS is correct when it uses the generation obtained during restore.
- Cloud Storage uploads are object-atomic; an interrupted upload is not exposed as a partial object.
- If some immutable objects upload but the manifest or pointer fails, they are orphans, not an
  authoritative baseline.
- Competing commits cannot silently overwrite the pointer because only one can satisfy the saved
  generation.
- File size and SHA-256 checks plus the state checksum detect missing or corrupted content.
- The preflight implementation now records a bounded list of up to 32 predecessor IDs in the
  pointer and validates candidates in order. A commit after fallback names the snapshot actually
  restored as its direct base, while keeping rejected newer candidates available for diagnosis.
- With no automatic deletion policy, lifecycle cannot remove the active snapshot. Any future
  deletion policy must be manifest-aware or operate only on proven orphans; an age-only rule can
  invalidate historical manifests.

## Versioning, soft delete, and lifecycle

The proposed controls are coherent:

- `europe-west1` is the Belgium region; see [bucket locations](https://docs.cloud.google.com/storage/docs/bucket-locations).
- Standard storage has no minimum storage duration.
- Object Versioning can remain disabled because all snapshots/manifests are immutable and the
  pointer is protected by generation CAS. Google currently recommends soft delete rather than
  Object Versioning for general accidental-deletion protection. Versioning would retain every
  replaced pointer generation and bill each like a live object. See
  [Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning).
- Seven-day soft delete is the default and retains deleted **or overwritten** objects for seven
  days. This means replaced pointer generations are recoverable administratively even with Object
  Versioning disabled. Soft-deleted bytes remain billable. See
  [soft delete](https://docs.cloud.google.com/storage/docs/soft-delete).
- Initial lifecycle recommendation: no delete or storage-class transition rule. Optionally configure
  only `AbortIncompleteMultipartUpload` after seven days; it does not target completed state
  objects. Lifecycle deletions themselves become soft-deleted and lifecycle processing is not a
  substitute for manifest-aware retention. See
  [Object Lifecycle Management](https://docs.cloud.google.com/storage/docs/lifecycle).

## Current pricing and material risks

Public list prices checked on 2026-10-13:

- `europe-west1` regional Standard storage: `$0.000027397/GiB-hour`, approximately
  `$0.020/GiB-month`.
- Single-region Standard operations: Class A `$0.005/1,000`, Class B `$0.0004/1,000`.
- Inbound transfer is free.
- General Internet outbound transfer to worldwide destinations other than Asia/Australia starts at
  `$0.12/GiB` for the first 10 TiB. GitHub-hosted runners are external to Google Cloud, so restored
  state can incur this outbound charge depending on runner destination.
- `europe-west1` is not one of the three regions eligible for Cloud Storage Always Free quotas.
- Live, noncurrent, and soft-deleted bytes accrue the same storage rate.

These values come from the current [Cloud Storage pricing table](https://cloud.google.com/storage/pricing).

Illustrative scale, not a bill promise:

| Stored/restored volume | Storage per month | One full Internet download |
|---|---:|---:|
| 100 MiB | about `$0.00195` | about `$0.0117` |
| 1 GiB | about `$0.020` | about `$0.12` |

At weekly ResearchRadar scale, operations should remain far below one cent per month. The material
risk is unbounded append-only accumulation or unexpectedly large repeated outbound restores, not
the current 33-record candidate. Seven-day soft delete adds at most the storage footprint of recently
overwritten/deleted objects; under this protocol that is normally tiny pointer data unless an
administrator deletes snapshots. Preserve the existing project-scoped budget alert and monitor
stored bytes, Class A operations, and outbound transfer after the first cloud run.

## Provisioning acceptance checks

Before bootstrap upload, verify all of the following:

1. Bucket name lookup still returns not found immediately before creation.
2. Location is exactly `EUROPE-WEST1`, class `STANDARD`, uniform access enabled, and public access
   prevention `enforced`.
3. Soft-delete retention is exactly seven days and Object Versioning is disabled.
4. The runtime service account has no project-wide Storage role.
5. Prefix role contains only object get/create; pointer role contains only object delete with exact
   resource-name equality.
6. Creating an immutable object works; overwriting it is denied.
7. Pointer bootstrap with generation `0` works; pointer replacement with the correct generation
   works; a stale generation fails with 412.
8. Deleting a snapshot or manifest is denied.
9. No service-account key exists.
10. The bootstrap manifest and checksum are reviewed separately before any upload.
