from __future__ import annotations

import hashlib
import http.client
import json
import os
import stat
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import numpy as np
import pytest
import soundfile

import sunofriend.workbench_listening_master as master_service
from sunofriend.listening_master_contract import (
    LISTENING_MASTER_EFFECTS,
    LISTENING_MASTER_POLICY,
    LISTENING_MASTER_SCHEMA,
    LISTENING_MASTER_TARGETS,
    LISTENING_MASTER_VERIFICATION_SCHEMA,
)
from sunofriend.workbench_balanced_contract import BALANCED_MIX_CONTRACT
from sunofriend.workbench_listening_master import (
    LISTENING_MASTER_SERVICE_EFFECTS,
    WORKBENCH_LISTENING_MASTER_SCHEMA,
    WorkbenchListeningMasterService,
)
from sunofriend.workbench_server import create_workbench_server
from tests.test_workbench_balanced_server import (
    _catalog,
    _render_preview,
)


GOOD_STATS = {
    "input_i": -18.4,
    "input_tp": -2.2,
    "input_lra": 3.1,
    "input_thresh": -28.5,
    "output_i": -16.0,
    "output_tp": -1.0,
    "output_lra": 3.2,
    "output_thresh": -26.1,
    "normalization_type": "dynamic",
    "target_offset": 0.0,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _document_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_owner_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _source_wav(path: Path) -> None:
    sample_rate = 8_000
    seconds = np.arange(sample_rate, dtype=np.float64) / sample_rate
    values = np.column_stack(
        [
            0.1 * np.sin(2 * np.pi * 220 * seconds),
            0.1 * np.sin(2 * np.pi * 330 * seconds),
        ]
    )
    soundfile.write(path, values, sample_rate, subtype="PCM_24")
    path.chmod(0o600)


def _fake_ffmpeg(path: Path) -> None:
    script = f"""#!/usr/bin/env python3
import json
import shutil
import sys

args = sys.argv[1:]
if "-version" in args:
    print("ffmpeg version sunofriend-workbench-master-test")
    raise SystemExit(0)
if "-filters" in args:
    print(" .. loudnorm          A->A       EBU R128 scanner")
    raise SystemExit(0)
source = args[args.index("-i") + 1]
destination = args[-1]
audio_filter = args[args.index("-af") + 1]
if destination != "-":
    shutil.copyfile(source, destination)
stats = {json.dumps(GOOD_STATS)}
if "dual_mono=false" in audio_filter:
    stats["input_i"] = -16.0
    stats["input_tp"] = -1.0
print(json.dumps(stats), file=sys.stderr)
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o700)


def _balanced(
    root: Path,
    *,
    identity: int = 1,
) -> dict[str, Any]:
    root.mkdir(mode=0o700, parents=True)
    preview = root / "balanced-selected-midi-preview.wav"
    report = root / "balanced-mix-receipt.json"
    _source_wav(preview)
    selection_sha256 = f"{identity:064x}"
    receipt_payload = {
        "schema": BALANCED_MIX_CONTRACT.receipt_schema,
        "selection_manifest_sha256": selection_sha256,
        "policy": BALANCED_MIX_CONTRACT.policy,
        "mastered": False,
    }
    receipt = {
        **receipt_payload,
        "receipt_sha256": _document_hash(receipt_payload),
    }
    _write_owner_json(report, receipt)
    return {
        "schema": BALANCED_MIX_CONTRACT.arrangement_schema,
        "cache_key": f"{identity + 100:064x}",
        "manifest_sha256": f"{identity + 200:064x}",
        "selection_manifest_sha256": selection_sha256,
        "policy": BALANCED_MIX_CONTRACT.policy,
        "mastered": False,
        "preview": {
            "path": str(preview),
            "name": preview.name,
            "bytes": preview.stat().st_size,
            "sha256": _sha256(preview),
        },
        "report": {
            "path": str(report),
            "name": report.name,
            "bytes": report.stat().st_size,
            "sha256": _sha256(report),
        },
        "receipt": receipt,
    }


def _contains_path(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key == "path"
            or key.endswith("_path")
            or _contains_path(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_path(child) for child in value)
    if isinstance(value, str):
        return value.startswith(("/", "~/", "../", "file://"))
    return False


def _contains_path_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key == "path"
            or key.endswith("_path")
            or _contains_path_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_path_key(child) for child in value)
    return False


def _fake_verification(
    source_path: str | Path,
    master_path: str | Path,
    receipt_path: str | Path,
) -> dict[str, Any]:
    source = Path(source_path)
    master = Path(master_path)
    receipt = Path(receipt_path)
    source_record = {
        "sha256": _sha256(source),
        "bytes": source.stat().st_size,
        "format": "WAV",
        "subtype": "PCM_24",
        "sample_rate": 8_000,
        "channels": 2,
        "frames": 8_000,
        "duration_seconds": 1.0,
    }
    master_record = {
        "name": master.name,
        "sha256": _sha256(master),
        "bytes": master.stat().st_size,
        "format": "WAV",
        "subtype": "PCM_24",
        "sample_rate": 8_000,
        "channels": 2,
        "frames": 8_000,
        "duration_seconds": 1.0,
    }
    return {
        "schema": LISTENING_MASTER_VERIFICATION_SCHEMA,
        "status": "verified",
        "receipt_schema": LISTENING_MASTER_SCHEMA,
        "policy": LISTENING_MASTER_POLICY,
        "mastered": True,
        "release_master": False,
        "receipt_document_sha256": "f" * 64,
        "receipt_file": {
            "sha256": _sha256(receipt),
            "bytes": receipt.stat().st_size,
        },
        "source": source_record,
        "master": master_record,
        "targets": dict(LISTENING_MASTER_TARGETS),
        "measurements": {
            "analysis": dict(GOOD_STATS),
            "render": dict(GOOD_STATS),
            "verification": {
                **GOOD_STATS,
                "input_i": -16.0,
                "input_tp": -1.0,
            },
        },
        "renderer": {
            "backend": "test",
            "executable_sha256": "e" * 64,
        },
        "timing": {
            "input_frames": 8_000,
            "output_frames": 8_000,
            "frame_horizon_changed": False,
        },
        "processing": {
            "integrated_loudness_normalisation": True,
            "true_peak_limiting": True,
        },
        "effects": dict(LISTENING_MASTER_EFFECTS),
        "receipt": {"test": True},
    }


def _fake_builder(
    _source_path: str | Path,
    *,
    output_path: str | Path,
    report_path: str | Path,
    ffmpeg_path: str | Path | None = None,
) -> dict[str, Any]:
    del ffmpeg_path
    output = Path(output_path)
    report = Path(report_path)
    output.write_bytes(b"private listening master")
    report.write_text('{"test":true}\n', encoding="utf-8")
    output.chmod(0o600)
    report.chmod(0o600)
    return {"status": "complete"}


def test_prepare_is_private_path_free_and_requires_explicit_promotion(
    tmp_path: Path,
) -> None:
    balanced = _balanced(tmp_path / "balanced")
    ffmpeg = tmp_path / "ffmpeg"
    _fake_ffmpeg(ffmpeg)
    service = WorkbenchListeningMasterService(
        tmp_path / "state",
        ffmpeg_path=ffmpeg,
    )

    prepared = service.prepare(balanced)

    assert prepared["schema"] == WORKBENCH_LISTENING_MASTER_SCHEMA
    assert prepared["cache_hit"] is False
    assert prepared["mastered"] is True
    assert prepared["release_master"] is False
    assert prepared["selection_manifest_sha256"] == (
        balanced["selection_manifest_sha256"]
    )
    assert prepared["balanced_arrangement_manifest_sha256"] == (
        balanced["manifest_sha256"]
    )
    assert prepared["balanced_arrangement_cache_key"] == balanced["cache_key"]
    assert prepared["balanced_preview_sha256"] == balanced["preview"]["sha256"]
    assert prepared["balanced_report_sha256"] == balanced["report"]["sha256"]
    assert prepared["receipt_schema"] == LISTENING_MASTER_SCHEMA
    assert prepared["summary"]["input_integrated_lufs"] == -18.4
    assert prepared["summary"]["output_integrated_lufs"] == -16.0
    assert prepared["summary"]["output_true_peak_dbtp"] == -1.0
    assert prepared["effects"] == LISTENING_MASTER_SERVICE_EFFECTS
    assert all(
        value is False
        for key, value in prepared["effects"].items()
        if key != "listening_master_created"
    )
    assert service.cached(balanced) is None

    pending_token = prepared["_pending_token"]
    pending_root = Path(prepared["master"]["path"]).parent
    manifest = json.loads(
        (pending_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert _contains_path(manifest) is False
    assert "cache_hit" not in manifest
    assert "pending_token" not in manifest
    assert stat.S_IMODE(service.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(pending_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(Path(prepared["master"]["path"]).stat().st_mode) == 0o600
    assert stat.S_IMODE(Path(prepared["receipt"]["path"]).stat().st_mode) == 0o600

    with pytest.raises(ValueError, match="pending token"):
        service.promote(prepared["cache_key"], "0" * 32)
    assert pending_root.is_dir()

    promoted = service.promote(prepared["cache_key"], pending_token)
    assert promoted["cache_hit"] is False
    assert promoted["manifest_sha256"] == prepared["manifest_sha256"]
    assert not pending_root.exists()
    assert Path(promoted["master"]["path"]).is_file()
    repeated_token = service.promote(prepared["cache_key"], pending_token)
    assert repeated_token["cache_hit"] is True
    assert repeated_token["manifest_sha256"] == promoted["manifest_sha256"]
    assert service.discard(prepared["cache_key"], pending_token) is False

    prepared_again = service.prepare(balanced)
    assert prepared_again["cache_hit"] is True
    assert "_pending_token" not in prepared_again

    restarted = WorkbenchListeningMasterService(
        tmp_path / "state",
        ffmpeg_path=ffmpeg,
    )
    cached = restarted.cached(balanced)
    assert cached is not None
    assert cached["cache_hit"] is True
    assert cached["manifest_sha256"] == promoted["manifest_sha256"]
    repeated = restarted.promote(cached["cache_key"], None)
    assert repeated["cache_hit"] is True


def test_cached_ignores_corrupt_optional_entry_but_prepare_fails_explicitly(
    tmp_path: Path,
) -> None:
    balanced = _balanced(tmp_path / "balanced")
    ffmpeg = tmp_path / "ffmpeg"
    _fake_ffmpeg(ffmpeg)
    service = WorkbenchListeningMasterService(
        tmp_path / "state",
        ffmpeg_path=ffmpeg,
    )
    prepared = service.prepare(balanced)
    promoted = service.promote(
        prepared["cache_key"],
        prepared["_pending_token"],
    )
    master = Path(promoted["master"]["path"])
    master.write_bytes(b"tampered")
    master.chmod(0o600)

    assert service.cached(balanced) is None
    with pytest.raises(ValueError, match="failed full verification"):
        service.prepare(balanced)


def test_discard_and_stale_cleanup_require_exact_authenticated_pending(
    tmp_path: Path,
) -> None:
    first = _balanced(tmp_path / "balanced-1", identity=1)
    second = _balanced(tmp_path / "balanced-2", identity=2)
    service = WorkbenchListeningMasterService(
        tmp_path / "state",
        builder=_fake_builder,
        pending_stale_seconds=1,
    )
    original_verifier = master_service.verify_listening_master_artifacts
    master_service.verify_listening_master_artifacts = _fake_verification
    try:
        prepared = service.prepare(first)
        assert service.discard(prepared["cache_key"], "f" * 32) is False
        assert service.discard(
            prepared["cache_key"],
            prepared["_pending_token"],
        )

        stale_service = WorkbenchListeningMasterService(
            tmp_path / "state",
            builder=_fake_builder,
            pending_stale_seconds=1,
        )
        stale = stale_service.prepare(first)
        stale_root = Path(stale["master"]["path"]).parent
        private_path = stale_root / ".private-binding.json"
        private = json.loads(private_path.read_text(encoding="utf-8"))
        private["created_ns"] = 0
        _write_owner_json(private_path, private)
        os.utime(stale_root, ns=(0, 0))

        pending_parent = stale_root.parent
        foreign = pending_parent / f"{'d' * 64}-{'e' * 32}.pending"
        foreign.mkdir(mode=0o700)
        os.utime(foreign, ns=(0, 0))
        symlink_target = tmp_path / "must-not-remove"
        symlink_target.mkdir()
        linked = pending_parent / f"{'c' * 64}-{'b' * 32}.pending"
        linked.symlink_to(symlink_target, target_is_directory=True)

        restarted = WorkbenchListeningMasterService(
            tmp_path / "state",
            builder=_fake_builder,
            pending_stale_seconds=1,
        )
        newer = restarted.prepare(second)

        assert not stale_root.exists()
        assert foreign.is_dir()
        assert linked.is_symlink()
        assert symlink_target.is_dir()
        assert restarted.discard(
            newer["cache_key"],
            newer["_pending_token"],
        )
    finally:
        master_service.verify_listening_master_artifacts = original_verifier


def test_cache_key_binds_exact_balance_and_cache_prunes_to_eight_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        master_service,
        "verify_listening_master_artifacts",
        _fake_verification,
    )
    service = WorkbenchListeningMasterService(
        tmp_path / "state",
        builder=_fake_builder,
    )
    cache_keys: list[str] = []
    for identity in range(1, 10):
        balanced = _balanced(
            tmp_path / f"balanced-{identity}",
            identity=identity,
        )
        prepared = service.prepare(balanced)
        cache_keys.append(prepared["cache_key"])
        service.promote(
            prepared["cache_key"],
            prepared["_pending_token"],
        )

    assert len(set(cache_keys)) == 9
    promoted = [
        path
        for path in service.root.iterdir()
        if path.name != ".pending" and path.is_dir() and not path.is_symlink()
    ]
    assert len(promoted) == 8
    assert cache_keys[-1] in {path.name for path in promoted}


def test_balanced_preview_or_report_drift_is_rejected_before_build(
    tmp_path: Path,
) -> None:
    balanced = _balanced(tmp_path / "balanced")
    called = False

    def builder(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return _fake_builder(*args, **kwargs)

    service = WorkbenchListeningMasterService(
        tmp_path / "state",
        builder=builder,
    )
    preview = Path(balanced["preview"]["path"])
    preview.write_bytes(b"changed")
    preview.chmod(0o600)

    with pytest.raises(ValueError, match="changed after balanced verification"):
        service.prepare(balanced)
    assert called is False


class _ListeningMasterHTTPFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.catalog, self.soundfont = _catalog(root)
        self.state_dir = root / "state"
        self.token = "listening-master-http-test-token"
        self._render_patch = patch(
            "sunofriend.workbench_artifacts.render_midi_to_wav",
            side_effect=_render_preview,
        )
        self.renderer = self._render_patch.start()
        self.server = create_workbench_server(
            self.catalog,
            state_dir=self.state_dir,
            token=self.token,
            soundfont_path=self.soundfont,
        )
        for stem in self.catalog["stems"]:
            candidate = stem["candidates"][0]
            self.server.store.append(
                self.catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "full_mix",
                    "problem_tags": [],
                    "notes": "private HTTP fixture note",
                },
            )
        self.builder = Mock(side_effect=_fake_builder)
        self.server.listening_masters._builder = self.builder
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._render_patch.stop()

    def restart(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.server = create_workbench_server(
            self.catalog,
            state_dir=self.state_dir,
            token=self.token,
            soundfont_path=self.soundfont,
        )
        self.builder = Mock(side_effect=_fake_builder)
        self.server.listening_masters._builder = self.builder
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()

    def create_balanced(self) -> tuple[dict[str, Any], dict[str, Any]]:
        status, project = self.json_request(
            "GET",
            f"/api/project?token={self.token}",
        )
        assert status == 200
        selection_sha256 = project["decoded_arrangement_selection"][
            "selection_manifest_sha256"
        ]
        status, payload = self.json_request(
            "POST",
            f"/api/balanced-arrangement?token={self.token}",
            {"selection_manifest_sha256": selection_sha256},
        )
        assert status == 200
        return project, payload

    def json_request(
        self,
        method: str,
        path: str,
        value: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        body = None if value is None else json.dumps(value).encode("utf-8")
        headers = {} if body is None else {"Content-Type": "application/json"}
        status, _headers, payload = self.request(
            method,
            path,
            body=body,
            headers=headers,
        )
        return status, json.loads(payload)

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.server.server_port,
            timeout=5,
        )
        try:
            connection.request(
                method,
                path,
                body=body,
                headers=headers or {},
            )
            response = connection.getresponse()
            return (
                response.status,
                {
                    name.lower(): value
                    for name, value in response.getheaders()
                },
                response.read(),
            )
        finally:
            connection.close()


@pytest.fixture
def listening_master_http(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> _ListeningMasterHTTPFixture:
    monkeypatch.setattr(
        master_service,
        "verify_listening_master_artifacts",
        _fake_verification,
    )
    fixture = _ListeningMasterHTTPFixture(tmp_path)
    try:
        yield fixture
    finally:
        fixture.close()


def _master_request(balanced: Mapping[str, Any]) -> dict[str, str]:
    return {
        "selection_manifest_sha256": str(
            balanced["selection_manifest_sha256"]
        ),
        "balanced_arrangement_manifest_sha256": str(
            balanced["manifest_sha256"]
        ),
    }


def _assert_pending_cache_is_empty(fixture: _ListeningMasterHTTPFixture) -> None:
    root = (
        fixture.state_dir
        / "artifacts"
        / "listening-masters"
    )
    if not root.exists():
        return
    promoted = [
        entry
        for entry in root.iterdir()
        if entry.name != ".pending"
    ]
    assert promoted == []
    pending = root / ".pending"
    if pending.exists():
        assert list(pending.iterdir()) == []


def _stable_review(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: child
        for key, child in value.items()
        if key not in {"exported_at", "review_sha256"}
    }


def test_http_master_is_path_free_downloadable_state_neutral_and_restored(
    listening_master_http: _ListeningMasterHTTPFixture,
) -> None:
    fixture = listening_master_http
    _project, balanced_payload = fixture.create_balanced()
    balanced = balanced_payload["balanced_arrangement"]
    assert balanced_payload["listening_master"] is None
    assert balanced_payload["product_outputs"]["optional_outputs"][
        "comparative_listening_master"
    ]["ready"] is False
    required_before = balanced_payload["product_outputs"]["required_outputs"]
    complete_before = balanced_payload["product_outputs"]["complete"]
    state_before = fixture.server.store.current_state(fixture.catalog)
    review_before = _stable_review(
        fixture.server.store.export_review(fixture.catalog)
    )

    status, payload = fixture.json_request(
        "POST",
        f"/api/listening-master?token={fixture.token}",
        _master_request(balanced),
    )

    assert status == 200
    master = payload["listening_master"]
    assert master["schema"] == WORKBENCH_LISTENING_MASTER_SCHEMA
    assert master["receipt_schema"] == LISTENING_MASTER_SCHEMA
    assert master["policy"] == LISTENING_MASTER_POLICY
    assert master["selection_manifest_sha256"] == (
        balanced["selection_manifest_sha256"]
    )
    assert master["balanced_arrangement_manifest_sha256"] == (
        balanced["manifest_sha256"]
    )
    assert master["balanced_preview_sha256"] == balanced["preview"]["sha256"]
    assert master["mastered"] is True
    assert master["release_master"] is False
    assert master["cache_hit"] is False
    assert "_pending_token" not in master
    assert "_balanced_binding" not in master
    assert _contains_path_key(master) is False
    assert str(fixture.root) not in json.dumps(master, sort_keys=True)
    assert "private HTTP fixture note" not in json.dumps(master, sort_keys=True)
    assert master["summary"]["master"]["subtype"] == "PCM_24"
    assert master["summary"]["timing"]["frame_horizon_changed"] is False
    assert master["summary"]["input_integrated_lufs"] == -18.4
    assert master["summary"]["output_integrated_lufs"] == -16.0
    assert master["summary"]["output_true_peak_dbtp"] == -1.0
    assert all(
        value is False
        for key, value in master["effects"].items()
        if key != "listening_master_created"
    )
    assert master["effects"]["listening_master_created"] is True
    assert payload["product_outputs"]["required_outputs"] == required_before
    assert payload["product_outputs"]["complete"] is complete_before
    optional = payload["product_outputs"]["optional_outputs"][
        "comparative_listening_master"
    ]
    assert optional["ready"] is True
    assert optional["available_through_workbench"] is True
    assert optional["automatic_promotion"] is False
    assert fixture.server.store.current_state(fixture.catalog) == state_before
    assert _stable_review(
        fixture.server.store.export_review(fixture.catalog)
    ) == review_before
    assert fixture.builder.call_count == 1

    downloaded: dict[str, bytes] = {}
    for key in ("master", "receipt"):
        assert master[f"{key}_url"].startswith("/media/")
        status, headers, body = fixture.request(
            "GET",
            master[f"{key}_url"],
        )
        assert status == 200
        assert headers["accept-ranges"] == "bytes"
        assert len(body) == master[key]["bytes"]
        assert hashlib.sha256(body).hexdigest() == master[key]["sha256"]
        assert str(fixture.root).encode() not in body
        downloaded[key] = body
    assert downloaded["master"] == b"private listening master"

    fixture.restart()
    status, restored = fixture.json_request(
        "GET",
        f"/api/project?token={fixture.token}",
    )
    assert status == 200
    restored_master = restored["listening_master"]
    assert restored_master is not None
    assert restored["balanced_arrangement"]["mastered"] is False
    assert restored["balanced_arrangement"]["manifest_sha256"] == (
        balanced["manifest_sha256"]
    )
    assert restored["balanced_arrangement"]["preview"]["sha256"] == (
        balanced["preview"]["sha256"]
    )
    assert restored_master["cache_hit"] is True
    assert restored_master["manifest_sha256"] == master["manifest_sha256"]
    assert restored_master["master"]["sha256"] == master["master"]["sha256"]
    assert restored_master["receipt"]["sha256"] == master["receipt"]["sha256"]
    assert restored["product_outputs"]["required_outputs"] == required_before
    assert restored["product_outputs"]["complete"] is complete_before
    assert restored["product_outputs"]["optional_outputs"][
        "comparative_listening_master"
    ]["ready"] is True
    assert fixture.builder.call_count == 0
    assert fixture.server.store.current_state(fixture.catalog) == state_before


def test_http_master_requires_exact_current_two_hash_contract(
    listening_master_http: _ListeningMasterHTTPFixture,
) -> None:
    fixture = listening_master_http
    _project, balanced_payload = fixture.create_balanced()
    balanced = balanced_payload["balanced_arrangement"]
    request = _master_request(balanced)
    fixture.builder.reset_mock()
    media_before = set(fixture.server.generated_media_ids)
    state_before = fixture.server.store.current_state(fixture.catalog)

    cases = (
        ({}, 400),
        ({"selection_manifest_sha256": request["selection_manifest_sha256"]}, 400),
        ({**request, "unexpected": True}, 400),
        (
            {
                **request,
                "selection_manifest_sha256": request[
                    "selection_manifest_sha256"
                ].upper(),
            },
            400,
        ),
        ({**request, "selection_manifest_sha256": "0" * 64}, 409),
        (
            {
                **request,
                "balanced_arrangement_manifest_sha256": "0" * 64,
            },
            409,
        ),
    )
    for body, expected_status in cases:
        status, payload = fixture.json_request(
            "POST",
            f"/api/listening-master?token={fixture.token}",
            body,
        )
        assert status == expected_status
        assert "error" in payload

    status, payload = fixture.json_request(
        "POST",
        "/api/listening-master?token=wrong",
        request,
    )
    assert status == 403
    assert "token" in payload["error"]
    fixture.builder.assert_not_called()
    assert set(fixture.server.generated_media_ids) == media_before
    assert fixture.server.store.current_state(fixture.catalog) == state_before


def test_http_master_discards_pending_on_selection_change(
    listening_master_http: _ListeningMasterHTTPFixture,
) -> None:
    fixture = listening_master_http
    _project, balanced_payload = fixture.create_balanced()
    balanced = balanced_payload["balanced_arrangement"]
    started = threading.Event()
    release = threading.Event()
    response: list[tuple[int, dict[str, Any]]] = []

    def delayed_builder(*args: Any, **kwargs: Any) -> dict[str, Any]:
        started.set()
        assert release.wait(timeout=5)
        return _fake_builder(*args, **kwargs)

    fixture.server.listening_masters._builder = delayed_builder
    original_discard = fixture.server.listening_masters.discard
    media_before = set(fixture.server.generated_media_ids)

    def request() -> None:
        response.append(
            fixture.json_request(
                "POST",
                f"/api/listening-master?token={fixture.token}",
                _master_request(balanced),
            )
        )

    with patch.object(
        fixture.server.listening_masters,
        "discard",
        wraps=original_discard,
    ) as discard:
        worker = threading.Thread(target=request)
        worker.start()
        assert started.wait(timeout=5)
        stem = fixture.catalog["stems"][0]
        candidate = stem["candidates"][0]
        fixture.server.store.append(
            fixture.catalog,
            {
                "event_type": "candidate_decision",
                "stem_id": stem["stem_id"],
                "candidate_id": candidate["candidate_id"],
                "decision": "reject",
                "context": "full_mix",
                "problem_tags": [],
            },
        )
        state_after_change = fixture.server.store.current_state(fixture.catalog)
        release.set()
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert len(response) == 1
    status, payload = response[0]
    assert status == 409
    assert "changed while" in payload["error"]
    discard.assert_called_once()
    _assert_pending_cache_is_empty(fixture)
    assert set(fixture.server.generated_media_ids) == media_before
    assert fixture.server.store.current_state(fixture.catalog) == state_after_change


def test_http_master_discards_pending_on_balanced_identity_change(
    listening_master_http: _ListeningMasterHTTPFixture,
) -> None:
    fixture = listening_master_http
    _project, balanced_payload = fixture.create_balanced()
    balanced = balanced_payload["balanced_arrangement"]
    state_before = fixture.server.store.current_state(fixture.catalog)
    media_before = set(fixture.server.generated_media_ids)
    original_cached = fixture.server.artifacts.cached_balanced_arrangement
    private_balanced = original_cached(fixture.catalog, state_before)
    assert private_balanced is not None
    calls = 0

    def changing_balanced(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return private_balanced
        return {
            **private_balanced,
            "manifest_sha256": "f" * 64,
        }

    original_discard = fixture.server.listening_masters.discard
    with (
        patch.object(
            fixture.server.artifacts,
            "cached_balanced_arrangement",
            side_effect=changing_balanced,
        ),
        patch.object(
            fixture.server.listening_masters,
            "discard",
            wraps=original_discard,
        ) as discard,
    ):
        status, payload = fixture.json_request(
            "POST",
            f"/api/listening-master?token={fixture.token}",
            _master_request(balanced),
        )

    assert status == 409
    assert "changed while" in payload["error"]
    discard.assert_called_once()
    _assert_pending_cache_is_empty(fixture)
    assert set(fixture.server.generated_media_ids) == media_before
    assert fixture.server.store.current_state(fixture.catalog) == state_before


def test_http_master_failure_exposes_no_partial_artifact(
    listening_master_http: _ListeningMasterHTTPFixture,
) -> None:
    fixture = listening_master_http
    _project, balanced_payload = fixture.create_balanced()
    balanced = balanced_payload["balanced_arrangement"]
    state_before = fixture.server.store.current_state(fixture.catalog)
    media_before = set(fixture.server.generated_media_ids)

    def failing_builder(*args: Any, **kwargs: Any) -> dict[str, Any]:
        _fake_builder(*args, **kwargs)
        raise OSError("simulated mastering failure")

    fixture.server.listening_masters._builder = failing_builder
    status, payload = fixture.json_request(
        "POST",
        f"/api/listening-master?token={fixture.token}",
        _master_request(balanced),
    )

    assert status == 400
    assert "simulated mastering failure" in payload["error"]
    _assert_pending_cache_is_empty(fixture)
    assert set(fixture.server.generated_media_ids) == media_before
    assert fixture.server.store.current_state(fixture.catalog) == state_before
    status, project = fixture.json_request(
        "GET",
        f"/api/project?token={fixture.token}",
    )
    assert status == 200
    assert project["listening_master"] is None
    assert project["product_outputs"]["optional_outputs"][
        "comparative_listening_master"
    ]["ready"] is False
