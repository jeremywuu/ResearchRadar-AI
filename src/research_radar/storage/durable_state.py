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

STATE_SCHEMA_VERSION = 2
SNAPSHOT_FILES = ("jobs.json", "phd.json", "events.json", "source_metadata.json")
RECOVERY_HISTORY_LIMIT = 32
GCS_READ_WRITE_SCOPES = ("https://www.googleapis.com/auth/devstorage.read_write",)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class DurableStateError(RuntimeError):
    """Base error for state integrity, configuration, or commit failures."""


class StateConflictError(DurableStateError):
    """Raised when an immutable object exists or the current pointer changed."""


class StateSchemaError(DurableStateError):
    """Raised when a snapshot uses an unsupported schema."""


class StatePermissionError(DurableStateError):
    """Raised when the configured state identity lacks a required permission."""


@dataclass(frozen=True)
class StateRestoreResult:
    available: bool
    snapshot_id: str | None = None
    current_generation: str | int | None = None
    recovered_from_snapshot_id: str | None = None
    record_counts: Mapping[str, int] | None = None


@dataclass(frozen=True)
class StateCommitRequest:
    run_id: str
    committed_at: datetime
    preference_configuration_hash: str
    source_health: Mapping[str, str]
    bootstrap: bool = False
    base_snapshot_id: str | None = None


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
        "records": _record_inventory(payloads),
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
    if manifest.get("records") != _record_inventory(payloads):
        raise DurableStateError("state manifest record inventory mismatch")


def _record_inventory(payloads: Mapping[str, bytes]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for name, data in payloads.items():
        if name == "source_metadata.json":
            continue
        category = name.removesuffix(".json")
        for record in _read_json_bytes(data, name).get("records", []):
            opportunity = record["opportunity"]
            inventory.append(
                {
                    "record_id": opportunity["opportunity_id"],
                    "category": category,
                    "adapter_source_id": opportunity.get("adapter_source_id"),
                    "official_source_url": opportunity.get("official_source_url")
                    or opportunity.get("source_url"),
                    "source_verification_status": opportunity.get("source_verification_status"),
                    "first_seen_at": opportunity.get("first_seen_at"),
                    "last_seen_at": opportunity.get("last_seen_at"),
                    "content_updated_at": opportunity.get("content_updated_at"),
                    "source_retrieved_at": opportunity.get("source_retrieved_at")
                    or opportunity.get("retrieved_at"),
                }
            )
    return sorted(inventory, key=lambda item: (item["category"], item["record_id"]))


def _write_restored(target_dir: Path, payloads: Mapping[str, bytes]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        (target_dir / name).write_bytes(data)
    _snapshot_payloads(target_dir)


def _snapshot_candidates(pointer: Mapping[str, Any]) -> tuple[str, ...]:
    current = pointer.get("snapshot_id")
    if not isinstance(current, str) or not current:
        raise DurableStateError("current pointer has no valid snapshot_id")
    values = [current, pointer.get("previous_snapshot_id")]
    history = pointer.get("fallback_snapshot_ids", [])
    if history is not None and not isinstance(history, list):
        raise DurableStateError("current pointer has invalid recovery history")
    values.extend(history or [])
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        if not isinstance(value, str) or not value:
            raise DurableStateError("current pointer has an invalid recovery snapshot ID")
        if value not in result:
            result.append(value)
    return tuple(result)


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
        candidates = _snapshot_candidates(pointer)
        current = candidates[0]
        failures: list[DurableStateError] = []
        for snapshot_id in candidates:
            try:
                restored = self._restore_snapshot(
                    snapshot_id,
                    target_dir,
                    expected_manifest_sha256=(
                        pointer.get("manifest_sha256") if snapshot_id == current else None
                    ),
                )
                return StateRestoreResult(
                    True,
                    restored,
                    generation,
                    current if snapshot_id != current else None,
                    _snapshot_record_counts(target_dir),
                )
            except StatePermissionError:
                raise
            except DurableStateError as exc:
                failures.append(exc)
        raise failures[-1]

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
            previous = _commit_base_snapshot(pointer, request)
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
                "fallback_snapshot_ids": (
                    list(_snapshot_candidates(pointer))[:RECOVERY_HISTORY_LIMIT] if pointer else []
                ),
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
        prefix = values.get("RESEARCH_RADAR_GCS_PREFIX", "").strip().strip("/")
        if not prefix:
            raise DurableStateError("RESEARCH_RADAR_GCS_PREFIX is required for GCS state")
        try:
            default_credentials, client_factory, credential_errors = cls._load_official_libraries()
        except ImportError as exc:
            raise DurableStateError("install the 'gcs' extra to use GCS durable state") from exc
        try:
            credentials, project = default_credentials(scopes=GCS_READ_WRITE_SCOPES)
            client = client_factory(project=project, credentials=credentials)
        except credential_errors as exc:
            raise DurableStateError("could not authenticate GCS durable state") from exc
        return cls(client, bucket, prefix=prefix)

    @staticmethod
    def _load_official_libraries() -> tuple[Any, Any, tuple[type[Exception], ...]]:
        import google.auth
        from google.auth.exceptions import DefaultCredentialsError, RefreshError
        from google.cloud import storage

        return google.auth.default, storage.Client, (DefaultCredentialsError, RefreshError)

    def restore(self, target_dir: Path) -> StateRestoreResult:
        pointer_blob = self.bucket.blob(f"{self.prefix}/current.json")
        try:
            if not pointer_blob.exists():
                return StateRestoreResult(available=False)
            pointer_blob.reload()
            generation = int(pointer_blob.generation)
            pointer_bytes = pointer_blob.download_as_bytes(if_generation_match=generation)
        except Exception as exc:
            if _is_precondition_failure(exc):
                raise StateConflictError("GCS current pointer changed during restoration") from exc
            if _is_permission_denied(exc):
                raise StatePermissionError("permission denied while reading GCS state") from exc
            raise
        pointer = _read_json_bytes(pointer_bytes, "GCS current.json")
        candidates = _snapshot_candidates(pointer)
        current = candidates[0]
        failures: list[DurableStateError] = []
        for snapshot_id in candidates:
            try:
                restored = self._restore_snapshot(
                    snapshot_id,
                    target_dir,
                    expected_manifest_sha256=(
                        pointer.get("manifest_sha256") if snapshot_id == current else None
                    ),
                )
                return StateRestoreResult(
                    True,
                    restored,
                    generation,
                    current if snapshot_id != current else None,
                    _snapshot_record_counts(target_dir),
                )
            except StatePermissionError:
                raise
            except DurableStateError as exc:
                failures.append(exc)
        raise failures[-1]

    def _restore_snapshot(
        self,
        snapshot_id: str,
        target_dir: Path,
        *,
        expected_manifest_sha256: object | None = None,
    ) -> str:
        try:
            manifest = _read_json_bytes(
                self.bucket.blob(f"{self.prefix}/commits/{snapshot_id}.json").download_as_bytes(),
                f"GCS manifest {snapshot_id}",
            )
            payloads = {
                name: self.bucket.blob(
                    f"{self.prefix}/snapshots/{snapshot_id}/{name}"
                ).download_as_bytes()
                for name in SNAPSHOT_FILES
            }
        except DurableStateError:
            raise
        except Exception as exc:
            if _is_not_found(exc):
                raise DurableStateError(f"incomplete GCS snapshot: {snapshot_id}") from exc
            if _is_permission_denied(exc):
                raise StatePermissionError("permission denied while reading GCS state") from exc
            raise
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
        pointer_blob = self.bucket.blob(f"{self.prefix}/current.json")
        pointer: dict[str, Any] | None = None
        previous = None
        if expected_current_generation is not None:
            try:
                pointer = _read_json_bytes(
                    pointer_blob.download_as_bytes(
                        if_generation_match=int(expected_current_generation)
                    ),
                    "GCS current.json",
                )
                previous = _commit_base_snapshot(pointer, request)
            except Exception as exc:
                if _is_precondition_failure(exc):
                    raise StateConflictError("GCS current pointer changed after restore") from exc
                if _is_permission_denied(exc):
                    raise StatePermissionError("permission denied while reading GCS state") from exc
                raise
        else:
            previous = _commit_base_snapshot(None, request)
            if not request.bootstrap:
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
                "fallback_snapshot_ids": (
                    list(_snapshot_candidates(pointer))[:RECOVERY_HISTORY_LIMIT] if pointer else []
                ),
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
            if _is_permission_denied(exc):
                raise StatePermissionError(
                    "permission denied while committing GCS state; replacing current.json "
                    "requires storage.objects.create and conditionally scoped "
                    "storage.objects.delete"
                ) from exc
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
    if request.base_snapshot_id is not None and not _SAFE_ID.fullmatch(request.base_snapshot_id):
        raise DurableStateError("base_snapshot_id must be a safe snapshot identifier")


def _snapshot_record_counts(snapshot_dir: Path) -> dict[str, int]:
    return {
        category: len(
            _read_json_bytes(
                (snapshot_dir / f"{category}.json").read_bytes(),
                f"{category}.json",
            ).get("records", [])
        )
        for category in ("jobs", "phd", "events")
    }


def _commit_base_snapshot(
    pointer: Mapping[str, Any] | None, request: StateCommitRequest
) -> str | None:
    if pointer is None:
        if request.base_snapshot_id is not None:
            raise StateConflictError("base snapshot was provided without a current state")
        return None
    candidates = _snapshot_candidates(pointer)
    if request.base_snapshot_id is None:
        return candidates[0]
    if request.base_snapshot_id not in candidates:
        raise StateConflictError("restored base snapshot is not in current recovery history")
    return request.base_snapshot_id


def _is_precondition_failure(exc: Exception) -> bool:
    return (
        exc.__class__.__name__ in {"PreconditionFailed", "Conflict"}
        or getattr(exc, "code", None) == 412
    )


def _is_permission_denied(exc: Exception) -> bool:
    return (
        exc.__class__.__name__ in {"Forbidden", "PermissionDenied"}
        or getattr(exc, "code", None) == 403
    )


def _is_not_found(exc: Exception) -> bool:
    return exc.__class__.__name__ == "NotFound" or getattr(exc, "code", None) == 404
