from __future__ import annotations

import asyncio
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest

import sunofriend.tui_listening_master as module
from sunofriend.tui_listening_master import ProductionListeningMasterRunner
from sunofriend.tui_listening_master_contract import (
    ListeningMasterConflictError,
    ListeningMasterRequest,
)
from sunofriend.tui_model import TuiProjectConfig, TuiProjectSnapshot


_SELECTION_A = "a" * 64
_SELECTION_B = "b" * 64
_BALANCED_A = "c" * 64
_BALANCED_B = "d" * 64
_CACHE_KEY = "e" * 64
_MASTER_MANIFEST = "f" * 64
_PENDING_TOKEN = "1" * 32


class _FakeArtifacts:
    def __init__(
        self,
        preview_path: Path,
        selections: list[str],
        balanced_hashes: list[str],
    ) -> None:
        self.preview_path = preview_path
        self.selections = selections
        self.balanced_hashes = balanced_hashes
        self.read_index = -1

    def decoded_arrangement_selection_manifest(
        self,
        _catalog: dict[str, Any],
        _current: dict[str, Any],
    ) -> dict[str, Any]:
        self.read_index += 1
        return {
            "selection_manifest_sha256": self.selections[
                min(self.read_index, len(self.selections) - 1)
            ]
        }

    def cached_balanced_arrangement(
        self,
        _catalog: dict[str, Any],
        _current: dict[str, Any],
    ) -> dict[str, Any]:
        index = min(self.read_index, len(self.selections) - 1)
        return {
            "selection_manifest_sha256": self.selections[index],
            "manifest_sha256": self.balanced_hashes[index],
            "preview": {"path": str(self.preview_path)},
        }


class _FakeService:
    def __init__(
        self,
        artifact: dict[str, Any],
        *,
        initially_cached: bool,
    ) -> None:
        self.artifact = artifact
        self.initially_cached = initially_cached
        self.cached_calls = 0
        self.prepare_calls = 0
        self.promote_calls: list[tuple[str, str]] = []
        self.discard_calls: list[tuple[str, str]] = []

    def cached(self, _balanced: dict[str, Any]) -> dict[str, Any] | None:
        self.cached_calls += 1
        return self.artifact if self.initially_cached else None

    def prepare(self, _balanced: dict[str, Any]) -> dict[str, Any]:
        self.prepare_calls += 1
        return {
            **self.artifact,
            "cache_hit": False,
            "_pending_token": _PENDING_TOKEN,
        }

    def promote(self, cache_key: str, pending_token: str) -> dict[str, Any]:
        self.promote_calls.append((cache_key, pending_token))
        return {**self.artifact, "cache_hit": False}

    def discard(self, cache_key: str, pending_token: str) -> bool:
        self.discard_calls.append((cache_key, pending_token))
        return True


def _snapshot(tmp_path: Path) -> TuiProjectSnapshot:
    project = tmp_path / "project"
    project.mkdir(parents=True)
    state = tmp_path / "state"
    state.mkdir()
    (state / "workbench.sqlite3").touch()
    (state / "artifacts").mkdir()
    config = TuiProjectConfig.create(project, state_dir=state)
    return TuiProjectSnapshot(
        config=config,
        catalog={"project_id": "project-1", "stems": []},
        public={},
        home={},
        document={},
        decision_store_exists=True,
    )


def _artifact(
    tmp_path: Path,
    *,
    selection: str = _SELECTION_A,
    balanced: str = _BALANCED_A,
) -> tuple[dict[str, Any], Path]:
    preview = tmp_path / "balanced-selected-midi-preview.wav"
    master = tmp_path / "listening-master.wav"
    receipt = tmp_path / "listening-master-receipt.json"
    preview.write_bytes(b"control")
    master.write_bytes(b"master")
    receipt.write_text("{}", encoding="utf-8")
    return (
        {
            "cache_key": _CACHE_KEY,
            "selection_manifest_sha256": selection,
            "balanced_arrangement_manifest_sha256": balanced,
            "manifest_sha256": _MASTER_MANIFEST,
            "policy": "fixed-test-policy",
            "summary": {
                "input_integrated_lufs": -19.0,
                "output_integrated_lufs": -16.0,
                "output_true_peak_dbtp": -1.0,
            },
            "mastered": True,
            "release_master": False,
            "effects": {
                "selection_changed": False,
                "feedback_recorded": False,
                "listening_master_created": True,
            },
            "master": {"path": str(master)},
            "receipt": {"path": str(receipt)},
        },
        preview,
    )


def _patch_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    artifacts: _FakeArtifacts,
    service: _FakeService,
    preflight: Any,
) -> list[str]:
    event_reads: list[str] = []

    def read_events(_path: Path, project_id: str) -> list[dict[str, Any]]:
        event_reads.append(project_id)
        return [{"read": len(event_reads)}]

    monkeypatch.setattr(
        module,
        "WorkbenchArtifacts",
        lambda *_args, **_kwargs: artifacts,
    )
    monkeypatch.setattr(
        module,
        "WorkbenchListeningMasterService",
        lambda *_args, **_kwargs: service,
    )
    monkeypatch.setattr(
        module,
        "read_workbench_events_read_only",
        read_events,
    )
    monkeypatch.setattr(
        module,
        "fold_workbench_events",
        lambda _catalog, events: {"event_reads": len(events)},
    )
    monkeypatch.setattr(
        module,
        "check_listening_master_dependencies",
        preflight,
    )
    return event_reads


def test_request_has_no_mastering_or_output_parameters(tmp_path: Path) -> None:
    request = ListeningMasterRequest.create(_snapshot(tmp_path))

    assert request.snapshot.config.state_dir == (tmp_path / "state").resolve()
    assert [field.name for field in fields(ListeningMasterRequest)] == ["snapshot"]


def test_runner_reuses_cache_before_preflight_and_reads_state_twice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, preview = _artifact(tmp_path)
    artifacts = _FakeArtifacts(
        preview,
        [_SELECTION_A, _SELECTION_A],
        [_BALANCED_A, _BALANCED_A],
    )
    service = _FakeService(artifact, initially_cached=True)

    def forbidden_preflight(_ffmpeg_path: Path | None) -> None:
        raise AssertionError("cache hit must precede fresh-build preflight")

    event_reads = _patch_runtime(
        monkeypatch,
        artifacts=artifacts,
        service=service,
        preflight=forbidden_preflight,
    )
    progress = []

    result = asyncio.run(
        ProductionListeningMasterRunner().run(
            ListeningMasterRequest.create(_snapshot(tmp_path / "snapshot")),
            on_progress=progress.append,
        )
    )

    assert result.succeeded is True
    assert result.cache_hit is True
    assert result.preflight_ready == ()
    assert result.mastered is True
    assert result.release_master is False
    assert result.balanced_control_path == preview.resolve()
    assert result.selection_manifest_sha256 == _SELECTION_A
    assert result.balanced_arrangement_manifest_sha256 == _BALANCED_A
    assert event_reads == ["project-1", "project-1"]
    assert service.prepare_calls == 0
    assert [(item.completed, item.total, item.phase) for item in progress] == [
        (0, 4, "inspect"),
        (4, 4, "reused"),
    ]
    assert all(str(tmp_path) not in item.message for item in progress)


def test_runner_preflights_prepares_rechecks_and_promotes_exact_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, preview = _artifact(tmp_path)
    artifacts = _FakeArtifacts(
        preview,
        [_SELECTION_A, _SELECTION_A],
        [_BALANCED_A, _BALANCED_A],
    )
    service = _FakeService(artifact, initially_cached=False)
    preflight_calls: list[Path | None] = []

    def preflight(ffmpeg_path: Path | None) -> dict[str, Any]:
        preflight_calls.append(ffmpeg_path)
        return {"ready": True}

    event_reads = _patch_runtime(
        monkeypatch,
        artifacts=artifacts,
        service=service,
        preflight=preflight,
    )
    progress = []

    result = asyncio.run(
        ProductionListeningMasterRunner().run(
            ListeningMasterRequest.create(_snapshot(tmp_path / "snapshot")),
            on_progress=progress.append,
        )
    )

    assert result.succeeded is True
    assert result.cache_hit is False
    assert result.preflight_ready == ("soundfile", "ffmpeg", "loudnorm")
    assert result.listening_master_manifest_sha256 == _MASTER_MANIFEST
    assert result.summary["output_integrated_lufs"] == -16.0
    assert result.effects["feedback_recorded"] is False
    assert preflight_calls == [None]
    assert event_reads == ["project-1", "project-1", "project-1"]
    assert service.prepare_calls == 1
    assert service.promote_calls == [(_CACHE_KEY, _PENDING_TOKEN)]
    assert service.discard_calls == []
    assert [item.phase for item in progress] == [
        "inspect",
        "preflight",
        "build",
        "verify",
        "complete",
    ]
    assert [item.completed for item in progress] == [0, 1, 2, 3, 4]
    assert all(item.total == 4 for item in progress)
    assert all(str(tmp_path) not in item.message for item in progress)


def test_runner_discards_pending_artifact_when_two_hash_cas_drifts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, preview = _artifact(tmp_path)
    artifacts = _FakeArtifacts(
        preview,
        [_SELECTION_A, _SELECTION_B],
        [_BALANCED_A, _BALANCED_B],
    )
    service = _FakeService(artifact, initially_cached=False)
    _patch_runtime(
        monkeypatch,
        artifacts=artifacts,
        service=service,
        preflight=lambda _path: {"ready": True},
    )

    with pytest.raises(ListeningMasterConflictError, match="changed"):
        asyncio.run(
            ProductionListeningMasterRunner().run(
                ListeningMasterRequest.create(_snapshot(tmp_path / "snapshot")),
                on_progress=lambda _progress: None,
            )
        )

    assert service.promote_calls == []
    assert service.discard_calls == [(_CACHE_KEY, _PENDING_TOKEN)]


def test_runner_refuses_success_when_state_drifts_during_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, preview = _artifact(tmp_path)
    artifacts = _FakeArtifacts(
        preview,
        [_SELECTION_A, _SELECTION_A, _SELECTION_B],
        [_BALANCED_A, _BALANCED_A, _BALANCED_B],
    )
    service = _FakeService(artifact, initially_cached=False)
    _patch_runtime(
        monkeypatch,
        artifacts=artifacts,
        service=service,
        preflight=lambda _path: {"ready": True},
    )

    with pytest.raises(ListeningMasterConflictError, match="changed"):
        asyncio.run(
            ProductionListeningMasterRunner().run(
                ListeningMasterRequest.create(_snapshot(tmp_path / "snapshot")),
                on_progress=lambda _progress: None,
            )
        )

    assert service.promote_calls == [(_CACHE_KEY, _PENDING_TOKEN)]
    assert service.discard_calls == []


def test_runner_dependency_failure_never_prepares_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, preview = _artifact(tmp_path)
    artifacts = _FakeArtifacts(
        preview,
        [_SELECTION_A],
        [_BALANCED_A],
    )
    service = _FakeService(artifact, initially_cached=False)

    def unavailable(_path: Path | None) -> None:
        raise RuntimeError("ffmpeg has no loudnorm")

    _patch_runtime(
        monkeypatch,
        artifacts=artifacts,
        service=service,
        preflight=unavailable,
    )

    with pytest.raises(module.ListeningMasterError, match="not ready"):
        asyncio.run(
            ProductionListeningMasterRunner().run(
                ListeningMasterRequest.create(_snapshot(tmp_path / "snapshot")),
                on_progress=lambda _progress: None,
            )
        )

    assert service.prepare_calls == 0
    assert service.promote_calls == []
    assert service.discard_calls == []


def test_missing_balanced_artifact_root_fails_without_creating_it(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path)
    assert snapshot.config.state_dir is not None
    artifact_root = snapshot.config.state_dir / "artifacts"
    artifact_root.rmdir()

    with pytest.raises(
        module.ListeningMasterUnavailableError,
        match="balanced song-interpretation",
    ):
        asyncio.run(
            ProductionListeningMasterRunner().run(
                ListeningMasterRequest.create(snapshot),
                on_progress=lambda _progress: None,
            )
        )

    assert not artifact_root.exists()
