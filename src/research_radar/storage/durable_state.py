"""Durable, immutable monitoring snapshots with filesystem and GCS adapters."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

STATE_SCHEMA_VERSION = 1
SNAPSHOT_FILES = ("jobs.json", "phd.json", "events.json", "source_metadata.json")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class DurableStateError(RuntimeError):
    """Base error for state integrity, configuration, or commit failures."""


class StateConflictError(DurableStateError):
    """Raised when an immutable object exists or the current pointer changed."""


class StateSchemaError(DurableStateError):
    """Raised when a snapshot uses an unsupported schema."""


@dataclass(frozen=True)
class StateRestoreResult:
    available: bool
    snapshot_id: str | None = None
    current_generation: str | int | None = None
    recovered_from_snapshot_id: str | None = None


@dataclass(frozen=True)
class StateCommitRequest:
    run_id: str
    committed_at: datetime
    preference_configuration_hash: str
    source_health: Mapping[str, str]
    bootstrap: bool = False


@dataclass(frozen=True)
class StateCommitResult:
    snapshot_id: str
    state_checksum: str
    current_generation: str | int
    previous_snapshot_id: str | None


class DurableStateBackend(Protocol):
    """Restore the current valid snapshot and atomically commit its successor."""

    def restore(self, target_dir: Path) -> StateRestoreResult: ...

    def commit(
        self,
        snapshot_dir: Path,
        request: StateCommitRequest,
        *,
        expected_current_generation: str | int | None,
    ) -> StateCommitResult: ...


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def _read_json_bytes(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DurableStateError(f"invalid JSON in {label}") from exc
    if not isinstance(value, dict):
        raise DurableStateError(f"{label} must contain a JSON object")
    return value


def _snapshot_payloads(snapshot_dir: Path) -> dict[str, bytes]:
    payloads: dict[str, bytes] = {}
    seen_ids: set[str] = set()
    for name in SNAPSHOT_FILES:
        path = snapshot_dir / name
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise DurableStateError(f"snapshot is missing {name}") from exc
        except json.JSONDecodeError as exc:
            raise DurableStateError(f"snapshot file is invalid JSON: {name}") from exc
        if not isinstance(value, dict):
            raise DurableStateError(f"snapshot file must contain an object: {name}")
        if name != "source_metadata.json":
            category = name.removesuffix(".json")
            records = value.get("records")
            if value.get("category") != category or not isinstance(records, list):
                raise DurableStateError(f"invalid category snapshot: {name}")
            for record in records:
                opportunity = record.get("opportunity") if isinstance(record, dict) else None
                record_id = (
                    opportunity.get("opportunity_id") if isinstance(opportunity, dict) else None
                )
                if not isinstance(record_id, str) or not record_id:
                    raise DurableStateError(f"{name} contains a record without a stable ID")
                if record_id in seen_ids:
                    raise DurableStateError(f"duplicate Record_ID across snapshot: {record_id}")
                seen_ids.add(record_id)
        elif not isinstance(value.get("sources"), dict):
            raise DurableStateError("source_metadata.json must contain sources")
        payloads[name] = _canonical_bytes(value)
    return payloads


def _manifest(
    snapshot_id: str,
    payloads: Mapping[str, bytes],
    request: StateCommitRequest,
    previous_snapshot_id: str | None,
) -> dict[str, Any]:
    files = {
        name: {"sha256": sha256(data).hexdigest(), "size": len(data)}
        for name, data in sorted(payloads.items())
    }
    state_checksum = sha256(
        "".join(f"{name}:{item['sha256']}\n" for name, item in files.items()).encode()
    ).hexdigest()
    record_counts = {
        name.removesuffix(".json"): len(_read_json_bytes(data, name).get("records", []))
        for name, data in payloads.items()
        if name != "source_metadata.json"
    }
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "run_id": request.run_id,
        "committed_at": request.committed_at.isoformat(),
        "bootstrap": request.bootstrap,
        "previous_snapshot_id": previous_snapshot_id,
        "preference_configuration_hash": request.preference_configuration_hash,
        "source_health": dict(sorted(request.source_health.items())),
        "record_counts": record_counts,
        "state_checksum": state_checksum,
        "files": files,
    }


def _validate_manifest(manifest: dict[str, Any], payloads: Mapping[str, bytes]) -> None:
    if manifest.get("schema_version") != STATE_SCHEMA_VERSION:
        raise StateSchemaError(
            f"unsupported state schema version: {manifest.get('schema_version')}"
        )
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != set(SNAPSHOT_FILES):
        raise DurableStateError("state manifest has an invalid file set")
    for name, data in payloads.items():
        expected = files.get(name)
        if not isinstance(expected, dict) or expected.get("sha256") != sha256(data).hexdigest():
            raise DurableStateError(f"checksum mismatch for {name}")
        if expected.get("size") != len(data):
            raise DurableStateError(f"size mismatch for {name}")
    expected_state = sha256(
        "".join(f"{name}:{files[name]['sha256']}\n" for name in sorted(files)).encode()
    ).hexdigest()
    if manifest.get("state_checksum") != expected_state:
        raise DurableStateError("state checksum mismatch")


def _write_restored(target_dir: Path, payloads: Mapping[str, bytes]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        (target_dir / name).write_bytes(data)
    _snapshot_payloads(target_dir)


class LocalFilesystemStateBackend:
    """Append-only snapshots with an atomic local current-pointer update."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def restore(self, target_dir: Path) -> StateRestoreResult:
        pointer_path = self.root / "current.json"
        if not pointer_path.is_file():
            return StateRestoreResult(available=False)
        pointer_bytes = pointer_path.read_bytes()
        pointer = _read_json_bytes(pointer_bytes, "current.json")
        generation = sha256(pointer_bytes).hexdigest()
        current = pointer.get("snapshot_id")
        previous = pointer.get("previous_snapshot_id")
        try:
            restored = self._restore_snapshot(
                str(current),
                target_dir,
                expected_manifest_sha256=pointer.get("manifest_sha256"),
            )
            return StateRestoreResult(True, restored, generation)
        except DurableStateError:
            if not isinstance(previous, str) or not previous:
                raise
            restored = self._restore_snapshot(previous, target_dir)
            return StateRestoreResult(True, restored, generation, str(current))

    def _restore_snapshot(
        self,
        snapshot_id: str,
        target_dir: Path,
        *,
        expected_manifest_sha256: object | None = None,
    ) -> str:
        manifest_path = self.root / "commits" / f"{snapshot_id}.json"
        try:
            manifest_bytes = manifest_path.read_bytes()
            payloads = {
                name: (self.root / "snapshots" / snapshot_id / name).read_bytes()
                for name in SNAPSHOT_FILES
            }
        except OSError as exc:
            raise DurableStateError(f"incomplete local snapshot: {snapshot_id}") from exc
        manifest = _read_json_bytes(manifest_bytes, str(manifest_path))
        if manifest.get("schema_version") != STATE_SCHEMA_VERSION:
            raise StateSchemaError(
                f"unsupported state schema version: {manifest.get('schema_version')}"
            )
        if (
            expected_manifest_sha256 is not None
            and expected_manifest_sha256 != sha256(_canonical_bytes(manifest)).hexdigest()
        ):
            raise DurableStateError(f"manifest pointer mismatch for {snapshot_id}")
        _validate_manifest(manifest, payloads)
        _write_restored(target_dir, payloads)
        return snapshot_id

    def commit(
        self,
        snapshot_dir: Path,
        request: StateCommitRequest,
        *,
        expected_current_generation: str | int | None,
    ) -> StateCommitResult:
        _validate_request(request)
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / ".commit.lock"
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise StateConflictError("another local state commit is in progress") from exc
        os.close(lock_fd)
        try:
            pointer, actual_generation = self._current_pointer()
            if actual_generation != expected_current_generation:
                raise StateConflictError("current state changed after restoration")
            previous = pointer.get("snapshot_id") if pointer else None
            if previous is None and not request.bootstrap:
                raise DurableStateError("initial state commit must be explicitly marked bootstrap")
            snapshot_id = request.run_id
            payloads = _snapshot_payloads(snapshot_dir)
            manifest = _manifest(snapshot_id, payloads, request, previous)
            snapshot_root = self.root / "snapshots" / snapshot_id
            snapshot_root.mkdir(parents=True, exist_ok=False)
            for name, data in payloads.items():
                (snapshot_root / name).write_bytes(data)
            commits = self.root / "commits"
            commits.mkdir(parents=True, exist_ok=True)
            commit_path = commits / f"{snapshot_id}.json"
            with commit_path.open("xb") as handle:
                handle.write(_canonical_bytes(manifest))
            pointer_value = {
                "schema_version": STATE_SCHEMA_VERSION,
                "snapshot_id": snapshot_id,
                "previous_snapshot_id": previous,
                "manifest_sha256": sha256(_canonical_bytes(manifest)).hexdigest(),
            }
            temporary = self.root / f".current.{snapshot_id}.tmp"
            temporary.write_bytes(_canonical_bytes(pointer_value))
            os.replace(temporary, self.root / "current.json")
            generation = sha256(_canonical_bytes(pointer_value)).hexdigest()
            return StateCommitResult(snapshot_id, manifest["state_checksum"], generation, previous)
        except FileExistsError as exc:
            raise StateConflictError(f"snapshot already exists: {request.run_id}") from exc
        finally:
            lock_path.unlink(missing_ok=True)

    def _current_pointer(self) -> tuple[dict[str, Any] | None, str | None]:
        path = self.root / "current.json"
        if not path.is_file():
            return None, None
        data = path.read_bytes()
        return _read_json_bytes(data, "current.json"), sha256(data).hexdigest()


class GoogleCloudStorageStateBackend:
    """GCS adapter using immutable objects and a generation-guarded current pointer."""

    def __init__(
        self, client: Any, bucket_name: str, *, prefix: str = "researchradar/state/v1"
    ) -> None:
        if not bucket_name.strip():
            raise ValueError("bucket_name must not be blank")
        self.bucket = client.bucket(bucket_name)
        self.prefix = prefix.strip("/")

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> GoogleCloudStorageStateBackend:
        values = environment if environment is not None else os.environ
        bucket = values.get("RESEARCH_RADAR_GCS_BUCKET", "").strip()
        if not bucket:
            raise DurableStateError("RESEARCH_RADAR_GCS_BUCKET is required for GCS state")
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise DurableStateError("install the 'gcs' extra to use GCS durable state") from exc
        return cls(
            storage.Client(),
            bucket,
            prefix=values.get("RESEARCH_RADAR_GCS_PREFIX", "researchradar/state/v1"),
        )

    def restore(self, target_dir: Path) -> StateRestoreResult:
        pointer_blob = self.bucket.blob(f"{self.prefix}/current.json")
        if not pointer_blob.exists():
            return StateRestoreResult(available=False)
        pointer_bytes = pointer_blob.download_as_bytes()
        pointer_blob.reload()
        pointer = _read_json_bytes(pointer_bytes, "GCS current.json")
        generation = int(pointer_blob.generation)
        current = str(pointer.get("snapshot_id") or "")
        previous = pointer.get("previous_snapshot_id")
        try:
            restored = self._restore_snapshot(
                current,
                target_dir,
                expected_manifest_sha256=pointer.get("manifest_sha256"),
            )
            return StateRestoreResult(True, restored, generation)
        except DurableStateError:
            if not isinstance(previous, str) or not previous:
                raise
            restored = self._restore_snapshot(previous, target_dir)
            return StateRestoreResult(True, restored, generation, current)

    def _restore_snapshot(
        self,
        snapshot_id: str,
        target_dir: Path,
        *,
        expected_manifest_sha256: object | None = None,
    ) -> str:
        manifest = _read_json_bytes(
            self.bucket.blob(f"{self.prefix}/commits/{snapshot_id}.json").download_as_bytes(),
            f"GCS manifest {snapshot_id}",
        )
        if manifest.get("schema_version") != STATE_SCHEMA_VERSION:
            raise StateSchemaError(
                f"unsupported state schema version: {manifest.get('schema_version')}"
            )
        if (
            expected_manifest_sha256 is not None
            and expected_manifest_sha256 != sha256(_canonical_bytes(manifest)).hexdigest()
        ):
            raise DurableStateError(f"manifest pointer mismatch for {snapshot_id}")
        payloads = {
            name: self.bucket.blob(
                f"{self.prefix}/snapshots/{snapshot_id}/{name}"
            ).download_as_bytes()
            for name in SNAPSHOT_FILES
        }
        _validate_manifest(manifest, payloads)
        _write_restored(target_dir, payloads)
        return snapshot_id

    def commit(
        self,
        snapshot_dir: Path,
        request: StateCommitRequest,
        *,
        expected_current_generation: str | int | None,
    ) -> StateCommitResult:
        _validate_request(request)
        pointer_blob = self.bucket.blob(f"{self.prefix}/current.json")
        previous = None
        if expected_current_generation is not None:
            pointer = _read_json_bytes(pointer_blob.download_as_bytes(), "GCS current.json")
            previous = pointer.get("snapshot_id")
        elif not request.bootstrap:
            raise DurableStateError("initial state commit must be explicitly marked bootstrap")
        payloads = _snapshot_payloads(snapshot_dir)
        manifest = _manifest(request.run_id, payloads, request, previous)
        try:
            for name, data in payloads.items():
                self.bucket.blob(
                    f"{self.prefix}/snapshots/{request.run_id}/{name}"
                ).upload_from_string(data, content_type="application/json", if_generation_match=0)
            self.bucket.blob(f"{self.prefix}/commits/{request.run_id}.json").upload_from_string(
                _canonical_bytes(manifest), content_type="application/json", if_generation_match=0
            )
            pointer_value = {
                "schema_version": STATE_SCHEMA_VERSION,
                "snapshot_id": request.run_id,
                "previous_snapshot_id": previous,
                "manifest_sha256": sha256(_canonical_bytes(manifest)).hexdigest(),
            }
            pointer_blob.upload_from_string(
                _canonical_bytes(pointer_value),
                content_type="application/json",
                if_generation_match=int(expected_current_generation or 0),
            )
            pointer_blob.reload()
        except Exception as exc:
            if _is_precondition_failure(exc):
                raise StateConflictError("GCS generation precondition failed") from exc
            raise
        return StateCommitResult(
            request.run_id,
            manifest["state_checksum"],
            int(pointer_blob.generation),
            previous,
        )


def _validate_request(request: StateCommitRequest) -> None:
    if not _SAFE_ID.fullmatch(request.run_id):
        raise DurableStateError("run_id must be a safe immutable object identifier")
    if request.committed_at.tzinfo is None:
        raise DurableStateError("committed_at must be timezone-aware")
    if not request.preference_configuration_hash:
        raise DurableStateError("preference configuration hash is required")


def _is_precondition_failure(exc: Exception) -> bool:
    return (
        exc.__class__.__name__ in {"PreconditionFailed", "Conflict"}
        or getattr(exc, "code", None) == 412
    )
