from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research_radar.storage.durable_state import (
    GCS_READ_WRITE_SCOPES,
    DurableStateError,
    GoogleCloudStorageStateBackend,
    LocalFilesystemStateBackend,
    StateCommitRequest,
    StateConflictError,
    StatePermissionError,
    StateSchemaError,
)

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


def _snapshot(root: Path, record_id: str = "job_1") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    record = {
        "opportunity": {
            "opportunity_id": record_id,
            "title": "Research Scientist",
            "first_seen_at": "2026-10-01T00:00:00+00:00",
            "last_seen_at": "2026-10-13T09:00:00+00:00",
            "content_updated_at": "2026-10-01T00:00:00+00:00",
        },
        "score": {"final_score": 80},
    }
    for category in ("jobs", "phd", "events"):
        records = [record] if category == "jobs" else []
        (root / f"{category}.json").write_text(
            json.dumps({"category": category, "records": records}), encoding="utf-8"
        )
    (root / "source_metadata.json").write_text(
        json.dumps({"sources": {"official_jobs": {"health": "SUCCESS"}}}),
        encoding="utf-8",
    )
    return root


def _request(
    run_id: str,
    *,
    bootstrap: bool = False,
    base_snapshot_id: str | None = None,
) -> StateCommitRequest:
    return StateCommitRequest(
        run_id=run_id,
        committed_at=NOW,
        preference_configuration_hash="preferences-v1",
        source_health={"official_jobs": "SUCCESS"},
        bootstrap=bootstrap,
        base_snapshot_id=base_snapshot_id,
    )


def test_local_first_commit_requires_explicit_bootstrap(tmp_path: Path) -> None:
    backend = LocalFilesystemStateBackend(tmp_path / "state")

    with pytest.raises(DurableStateError, match="bootstrap"):
        backend.commit(
            _snapshot(tmp_path / "snapshot"),
            _request("run-1"),
            expected_current_generation=None,
        )


def test_local_bootstrap_restore_and_stable_history(tmp_path: Path) -> None:
    backend = LocalFilesystemStateBackend(tmp_path / "state")
    source = _snapshot(tmp_path / "snapshot")
    committed = backend.commit(
        source, _request("run-1", bootstrap=True), expected_current_generation=None
    )

    restored = backend.restore(tmp_path / "restored")

    assert restored.available is True
    assert restored.snapshot_id == "run-1"
    assert restored.current_generation == committed.current_generation
    opportunity = json.loads((tmp_path / "restored" / "jobs.json").read_text())["records"][0][
        "opportunity"
    ]
    assert opportunity["first_seen_at"] == "2026-10-01T00:00:00+00:00"

    manifest = json.loads(
        (tmp_path / "state" / "commits" / "run-1.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == 2
    assert manifest["record_counts"] == {"events": 0, "jobs": 1, "phd": 0}
    assert manifest["records"] == [
        {
            "adapter_source_id": None,
            "category": "jobs",
            "content_updated_at": "2026-10-01T00:00:00+00:00",
            "first_seen_at": "2026-10-01T00:00:00+00:00",
            "last_seen_at": "2026-10-13T09:00:00+00:00",
            "official_source_url": None,
            "record_id": "job_1",
            "source_retrieved_at": None,
            "source_verification_status": None,
        }
    ]


def test_local_commit_detects_concurrent_pointer_change(tmp_path: Path) -> None:
    backend = LocalFilesystemStateBackend(tmp_path / "state")
    backend.commit(
        _snapshot(tmp_path / "one"),
        _request("run-1", bootstrap=True),
        expected_current_generation=None,
    )

    with pytest.raises(StateConflictError, match="changed"):
        backend.commit(
            _snapshot(tmp_path / "two", "job_2"),
            _request("run-2"),
            expected_current_generation="stale-generation",
        )


def test_duplicate_snapshot_id_is_rejected(tmp_path: Path) -> None:
    backend = LocalFilesystemStateBackend(tmp_path / "state")
    first = backend.commit(
        _snapshot(tmp_path / "one"),
        _request("run-1", bootstrap=True),
        expected_current_generation=None,
    )

    with pytest.raises(StateConflictError, match="already exists"):
        backend.commit(
            _snapshot(tmp_path / "two"),
            _request("run-1"),
            expected_current_generation=first.current_generation,
        )


def test_corrupted_latest_manifest_recovers_previous_snapshot(tmp_path: Path) -> None:
    backend = LocalFilesystemStateBackend(tmp_path / "state")
    first = backend.commit(
        _snapshot(tmp_path / "one"),
        _request("run-1", bootstrap=True),
        expected_current_generation=None,
    )
    backend.commit(
        _snapshot(tmp_path / "two", "job_2"),
        _request("run-2"),
        expected_current_generation=first.current_generation,
    )
    (tmp_path / "state" / "commits" / "run-2.json").write_text("{}", encoding="utf-8")

    restored = backend.restore(tmp_path / "restored")

    assert restored.snapshot_id == "run-1"
    assert restored.recovered_from_snapshot_id == "run-2"


def test_checksum_corruption_is_not_silently_accepted(tmp_path: Path) -> None:
    backend = LocalFilesystemStateBackend(tmp_path / "state")
    backend.commit(
        _snapshot(tmp_path / "one"),
        _request("run-1", bootstrap=True),
        expected_current_generation=None,
    )
    (tmp_path / "state" / "snapshots" / "run-1" / "jobs.json").write_text("{}", encoding="utf-8")

    with pytest.raises(DurableStateError, match="checksum"):
        backend.restore(tmp_path / "restored")


def test_schema_version_mismatch_is_rejected(tmp_path: Path) -> None:
    backend = LocalFilesystemStateBackend(tmp_path / "state")
    backend.commit(
        _snapshot(tmp_path / "one"),
        _request("run-1", bootstrap=True),
        expected_current_generation=None,
    )
    path = tmp_path / "state" / "commits" / "run-1.json"
    manifest = json.loads(path.read_text())
    manifest["schema_version"] = 999
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(StateSchemaError, match="unsupported"):
        backend.restore(tmp_path / "restored")


def test_manifest_pointer_mismatch_is_rejected(tmp_path: Path) -> None:
    backend = LocalFilesystemStateBackend(tmp_path / "state")
    backend.commit(
        _snapshot(tmp_path / "one"),
        _request("run-1", bootstrap=True),
        expected_current_generation=None,
    )
    path = tmp_path / "state" / "commits" / "run-1.json"
    manifest = json.loads(path.read_text())
    manifest["committed_at"] = "2026-10-13T10:00:00+00:00"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(DurableStateError, match="pointer mismatch"):
        backend.restore(tmp_path / "restored")


def test_gcs_backend_requires_explicit_bucket_configuration() -> None:
    with pytest.raises(DurableStateError, match="RESEARCH_RADAR_GCS_BUCKET"):
        GoogleCloudStorageStateBackend.from_environment({})


def test_gcs_backend_requires_explicit_prefix_configuration() -> None:
    with pytest.raises(DurableStateError, match="RESEARCH_RADAR_GCS_PREFIX"):
        GoogleCloudStorageStateBackend.from_environment(
            {"RESEARCH_RADAR_GCS_BUCKET": "private-state"}
        )


def test_gcs_backend_uses_explicit_storage_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}
    client = FakeClient()

    def credentials(*, scopes: tuple[str, ...]) -> tuple[object, str]:
        calls["scopes"] = scopes
        return object(), "researchradar-ai"

    def client_factory(*, project: str, credentials: object) -> FakeClient:
        calls["project"] = project
        calls["credentials"] = credentials
        return client

    monkeypatch.setattr(
        GoogleCloudStorageStateBackend,
        "_load_official_libraries",
        staticmethod(lambda: (credentials, client_factory, (RuntimeError,))),
    )

    backend = GoogleCloudStorageStateBackend.from_environment(
        {
            "RESEARCH_RADAR_GCS_BUCKET": "private-state",
            "RESEARCH_RADAR_GCS_PREFIX": "researchradar/state/v1",
        }
    )

    assert backend.bucket is client.value
    assert calls["scopes"] == GCS_READ_WRITE_SCOPES
    assert calls["project"] == "researchradar-ai"


def test_gcs_backend_reports_failed_credential_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CredentialFailure(Exception):
        pass

    def credentials(*, scopes: tuple[str, ...]) -> tuple[object, str]:
        raise CredentialFailure("credential detail must not be exposed")

    monkeypatch.setattr(
        GoogleCloudStorageStateBackend,
        "_load_official_libraries",
        staticmethod(lambda: (credentials, object, (CredentialFailure,))),
    )

    with pytest.raises(DurableStateError, match="authenticate GCS durable state"):
        GoogleCloudStorageStateBackend.from_environment(
            {
                "RESEARCH_RADAR_GCS_BUCKET": "private-state",
                "RESEARCH_RADAR_GCS_PREFIX": "researchradar/state/v1",
            }
        )


class PreconditionFailed(Exception):
    pass


class PermissionDenied(Exception):
    pass


class NotFound(Exception):
    pass


class FakeBlob:
    def __init__(self, bucket: FakeBucket, name: str) -> None:
        self.bucket = bucket
        self.name = name
        self.generation = bucket.generations.get(name, 0)

    def exists(self) -> bool:
        return self.name in self.bucket.objects

    def download_as_bytes(self, *, if_generation_match: int | None = None) -> bytes:
        current = self.bucket.generations.get(self.name, 0)
        if if_generation_match is not None and current != if_generation_match:
            raise PreconditionFailed("412")
        if self.name not in self.bucket.objects:
            raise NotFound("404")
        return self.bucket.objects[self.name]

    def reload(self) -> None:
        self.generation = self.bucket.generations.get(self.name, 0)

    def upload_from_string(
        self, data: bytes, *, content_type: str, if_generation_match: int
    ) -> None:
        current = self.bucket.generations.get(self.name, 0)
        if current != if_generation_match:
            raise PreconditionFailed("412")
        if current and self.name not in self.bucket.overwritable_names:
            raise PermissionDenied("403")
        if current:
            self.bucket.overwritten_names.append(self.name)
        self.bucket.objects[self.name] = bytes(data)
        self.bucket.generations[self.name] = current + 1
        self.generation = current + 1


class FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.generations: dict[str, int] = {}
        self.overwritable_names = {"researchradar/state/v1/current.json"}
        self.overwritten_names: list[str] = []

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self, name)


class FakeClient:
    def __init__(self) -> None:
        self.value = FakeBucket()

    def bucket(self, name: str) -> FakeBucket:
        assert name == "private-state"
        return self.value


def test_gcs_bootstrap_and_restore_use_generation_preconditions(tmp_path: Path) -> None:
    client = FakeClient()
    backend = GoogleCloudStorageStateBackend(client, "private-state")
    committed = backend.commit(
        _snapshot(tmp_path / "snapshot"),
        _request("run-1", bootstrap=True),
        expected_current_generation=None,
    )

    restored = backend.restore(tmp_path / "restored")

    assert committed.current_generation == 1
    assert restored.snapshot_id == "run-1"
    assert restored.current_generation == 1


def test_gcs_pointer_cas_overwrites_only_the_current_pointer(tmp_path: Path) -> None:
    client = FakeClient()
    backend = GoogleCloudStorageStateBackend(client, "private-state")
    first = backend.commit(
        _snapshot(tmp_path / "one"),
        _request("run-1", bootstrap=True),
        expected_current_generation=None,
    )

    backend.commit(
        _snapshot(tmp_path / "two", "job_2"),
        _request("run-2"),
        expected_current_generation=first.current_generation,
    )

    assert client.value.overwritten_names == ["researchradar/state/v1/current.json"]
    assert all(
        generation == 1
        for name, generation in client.value.generations.items()
        if name != "researchradar/state/v1/current.json"
    )


def test_gcs_missing_pointer_overwrite_permission_fails_without_changing_baseline(
    tmp_path: Path,
) -> None:
    client = FakeClient()
    backend = GoogleCloudStorageStateBackend(client, "private-state")
    first = backend.commit(
        _snapshot(tmp_path / "one"),
        _request("run-1", bootstrap=True),
        expected_current_generation=None,
    )
    client.value.overwritable_names.clear()

    with pytest.raises(StatePermissionError, match="storage.objects.delete"):
        backend.commit(
            _snapshot(tmp_path / "two", "job_2"),
            _request("run-2"),
            expected_current_generation=first.current_generation,
        )

    assert backend.restore(tmp_path / "restored").snapshot_id == "run-1"


def test_gcs_stale_generation_leaves_current_baseline_unchanged(tmp_path: Path) -> None:
    client = FakeClient()
    backend = GoogleCloudStorageStateBackend(client, "private-state")
    backend.commit(
        _snapshot(tmp_path / "one"),
        _request("run-1", bootstrap=True),
        expected_current_generation=None,
    )

    with pytest.raises(StateConflictError, match="changed"):
        backend.commit(
            _snapshot(tmp_path / "two", "job_2"),
            _request("run-2"),
            expected_current_generation=99,
        )

    restored = backend.restore(tmp_path / "restored")
    assert restored.snapshot_id == "run-1"


def test_gcs_incomplete_upload_never_changes_current_pointer(tmp_path: Path) -> None:
    client = FakeClient()
    backend = GoogleCloudStorageStateBackend(client, "private-state")
    backend.commit(
        _snapshot(tmp_path / "one"),
        _request("run-1", bootstrap=True),
        expected_current_generation=None,
    )
    client.value.generations["researchradar/state/v1/snapshots/run-2/jobs.json"] = 1

    with pytest.raises(StateConflictError):
        backend.commit(
            _snapshot(tmp_path / "two", "job_2"),
            _request("run-2"),
            expected_current_generation=1,
        )

    assert backend.restore(tmp_path / "restored").snapshot_id == "run-1"


def test_gcs_missing_current_snapshot_object_recovers_previous_commit(tmp_path: Path) -> None:
    client = FakeClient()
    backend = GoogleCloudStorageStateBackend(client, "private-state")
    first = backend.commit(
        _snapshot(tmp_path / "one"),
        _request("run-1", bootstrap=True),
        expected_current_generation=None,
    )
    backend.commit(
        _snapshot(tmp_path / "two", "job_2"),
        _request("run-2"),
        expected_current_generation=first.current_generation,
    )
    missing_name = "researchradar/state/v1/snapshots/run-2/jobs.json"
    del client.value.objects[missing_name]
    del client.value.generations[missing_name]

    restored = backend.restore(tmp_path / "restored")

    assert restored.snapshot_id == "run-1"
    assert restored.recovered_from_snapshot_id == "run-2"

    committed = backend.commit(
        _snapshot(tmp_path / "three", "job_3"),
        _request("run-3", base_snapshot_id=restored.snapshot_id),
        expected_current_generation=restored.current_generation,
    )
    manifest = json.loads(
        client.value.objects["researchradar/state/v1/commits/run-3.json"].decode("utf-8")
    )
    assert committed.previous_snapshot_id == "run-1"
    assert manifest["previous_snapshot_id"] == "run-1"


def test_local_recovery_walks_multiple_recorded_predecessors(tmp_path: Path) -> None:
    backend = LocalFilesystemStateBackend(tmp_path / "state")
    first = backend.commit(
        _snapshot(tmp_path / "one"),
        _request("run-1", bootstrap=True),
        expected_current_generation=None,
    )
    second = backend.commit(
        _snapshot(tmp_path / "two", "job_2"),
        _request("run-2"),
        expected_current_generation=first.current_generation,
    )
    backend.commit(
        _snapshot(tmp_path / "three", "job_3"),
        _request("run-3"),
        expected_current_generation=second.current_generation,
    )
    for run_id in ("run-3", "run-2"):
        (tmp_path / "state" / "commits" / f"{run_id}.json").write_text("{}", encoding="utf-8")

    restored = backend.restore(tmp_path / "restored")

    assert restored.snapshot_id == "run-1"
    assert restored.recovered_from_snapshot_id == "run-3"

    fourth = backend.commit(
        _snapshot(tmp_path / "four", "job_4"),
        _request("run-4", base_snapshot_id=restored.snapshot_id),
        expected_current_generation=restored.current_generation,
    )
    manifest = json.loads(
        (tmp_path / "state" / "commits" / "run-4.json").read_text(encoding="utf-8")
    )
    assert fourth.previous_snapshot_id == "run-1"
    assert manifest["previous_snapshot_id"] == "run-1"


def test_commit_rejects_restored_base_outside_pointer_history(tmp_path: Path) -> None:
    backend = LocalFilesystemStateBackend(tmp_path / "state")
    first = backend.commit(
        _snapshot(tmp_path / "one"),
        _request("run-1", bootstrap=True),
        expected_current_generation=None,
    )

    with pytest.raises(StateConflictError, match="recovery history"):
        backend.commit(
            _snapshot(tmp_path / "two", "job_2"),
            _request("run-2", base_snapshot_id="unknown-run"),
            expected_current_generation=first.current_generation,
        )
