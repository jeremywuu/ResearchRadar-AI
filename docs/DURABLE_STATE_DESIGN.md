# Durable monitoring state

## Purpose and boundary

GitHub-hosted runners are ephemeral, so review artifacts and `data/live/` cannot be the
authoritative baseline for cross-run change detection. ResearchRadar now exposes one small state
contract with two implementations:

- `LocalFilesystemStateBackend` for offline development and recovery testing.
- `GoogleCloudStorageStateBackend` for a future explicitly configured cloud deployment.

Both adapters restore and commit the same four existing snapshot files. They do not introduce a
second opportunity model, scoring engine, or feedback store. Google Sheets remains authoritative
for preference, Saved, Hidden, and Personal Notes; those notes are not copied into durable state.

The weekly workflow still defaults to `--state-backend none`. GCS is not used until a bucket,
bucket-scoped IAM, workflow variables, and an approved bootstrap are configured separately.

## Logical snapshot

Every committed state contains:

```text
jobs.json
phd.json
events.json
source_metadata.json
```

The existing processed-record JSON carries stable `Record_ID`, canonical source facts,
`First_Seen`, `Last_Seen`, `Content_Updated_At`, source evidence, source observation time,
recommendation data, and source attribution. `source_metadata.json` carries source-health and
retrieval details. The immutable commit manifest adds:

```text
schema_version
snapshot_id / run_id
committed_at
bootstrap
previous_snapshot_id
preference_configuration_hash
source_health
record_counts
per-file SHA-256 and byte size
whole-state SHA-256
```

Serialization is canonical JSON: keys are sorted, separators are fixed, UTF-8 is retained, and a
single final newline is written. A restore rejects unsupported schemas, missing files, malformed
JSON, duplicate stable IDs, invalid category envelopes, size mismatches, checksum mismatches, and
a manifest that does not match the current pointer.

## Object layout

The filesystem root and GCS prefix use the same append-only layout:

```text
current.json
commits/<snapshot_id>.json
snapshots/<snapshot_id>/jobs.json
snapshots/<snapshot_id>/phd.json
snapshots/<snapshot_id>/events.json
snapshots/<snapshot_id>/source_metadata.json
```

Snapshot files and commit manifests are immutable. `current.json` is the only mutable object and
contains the current snapshot, its predecessor, and the canonical manifest checksum.

## Atomic commit protocol

1. Restore `current.json` and retain its local hash or GCS object generation.
2. Collect and reconcile into a complete temporary snapshot directory.
3. Validate every file, stable ID, and checksum locally.
4. Create the four immutable snapshot objects with create-only semantics.
5. Create the immutable commit manifest with create-only semantics.
6. Replace `current.json` only if its generation still matches the restored generation.

Local commits use an exclusive lock file and atomic `os.replace`. GCS commits use
`ifGenerationMatch=0` for immutable objects and a generation precondition for `current.json`.
If an upload is interrupted, objects may be orphaned but are not authoritative. If a competing run
wins the pointer update, the losing run raises a conflict and never replaces the winner. Workflow
concurrency remains useful for cost control, but correctness does not depend on it.

## Restore and recovery

At run start the backend reads the current pointer, validates its manifest, validates all file and
state checksums, verifies the schema, and writes the canonical files to a fresh working directory.
If the current committed snapshot is corrupt, it attempts the predecessor recorded in the pointer
and reports which snapshot was rejected. If neither is valid, the run fails visibly; corrupt state
is never silently accepted.

An empty backend returns `available=false`. This is explicit bootstrap mode: the weekly monitor may
produce a report and Sheets dry-run, but it does not classify the run against invented history and
does not automatically create the first authoritative commit.

## Partial source failures

The existing fresh-observation reconciler remains the merge authority. A successful source may
advance only the records it actually reobserved. A blocked, timed-out, rate-limited, malformed, or
otherwise unavailable source retains its previous verified records and timestamps. Missing records
from a bounded scan become not-observed, not closed. Only explicit official closure evidence may
produce a confirmed closure.

A partially successful run may commit when at least one source succeeded, the reconciliation has
no unresolved review state, and the Sheets dry-run has no invalid records or conflicts. Because the
reconciler copies forward unavailable-source records, unaffected history remains complete. If every
source fails or reconciliation is unsafe, the previous pointer remains authoritative.

## Weekly integration

The local opt-in command is:

```bash
research-radar weekly-run --live \
  --state-backend local \
  --state-dir data/automation/state/live \
  --output-dir data/automation/run
```

Future GCS runs use `--state-backend gcs` plus:

```text
RESEARCH_RADAR_GCS_BUCKET
RESEARCH_RADAR_GCS_PREFIX  # optional; defaults to researchradar/state/v1
```

No bucket name is hardcoded. The ordinary workflow currently omits `--state-backend gcs`, so a
missing bucket cannot accidentally change cloud behavior. Every mode remains read-only with
respect to Google Sheets.

## Security boundary

State contains public opportunity evidence and monitoring metadata, not OAuth credentials, GitHub
tokens, service-account keys, or personal feedback notes. The future bucket must block public
access, use uniform bucket-level access, and authorize the runtime identity only on that bucket.
Snapshot validation treats restored content as untrusted data.

