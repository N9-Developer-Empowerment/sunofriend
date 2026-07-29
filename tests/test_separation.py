from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import struct
import wave
from pathlib import Path

import pytest

import sunofriend.separation as separation_module
from sunofriend.audio_formats import file_sha256
from sunofriend.separation import (
    FAKE_SEPARATION_BACKEND_ID,
    REAL_SEPARATION_BACKENDS_SUPPORTED,
    SEPARATION_CACHE_REPLAY_SUPPORTED,
    SEPARATION_QUALITY_RELATIVE_PATH,
    SEPARATION_RECEIPT_FILENAME,
    FakeSeparationBackend,
    SeparationCancellationToken,
    SeparationRunMetadata,
    SeparationRunPlan,
    run_separation,
)
from sunofriend.separation_contract import (
    SeparationAudioGeometry,
    SeparationBackendOutput,
    SeparationRequest,
    SeparationResult,
    SeparationRunReceipt,
)
from sunofriend.source_receipt import canonical_json_bytes


def _write_pcm24_wave(
    path: Path,
    *,
    frames: int = 24,
    channels: int = 1,
    sample_rate: int = 24_000,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = (
        -2_000_000,
        -1_000_000,
        -250_000,
        0,
        125_000,
        750_000,
        1_500_000,
        250_000,
    )
    payload = bytearray()
    for frame_index in range(frames):
        for channel in range(channels):
            sample = values[(frame_index + channel) % len(values)]
            payload.extend(sample.to_bytes(3, "little", signed=True))
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(3)
        writer.setframerate(sample_rate)
        writer.writeframes(bytes(payload))


def _write_extensible_pcm24_wave(
    path: Path,
    *,
    frames: int = 24,
    channels: int = 1,
    sample_rate: int = 24_000,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = bytearray()
    for index in range(frames * channels):
        value = ((index % 9) - 4) * 250_000
        samples.extend(value.to_bytes(3, "little", signed=True))
    block_align = channels * 3
    byte_rate = sample_rate * block_align
    pcm_guid = bytes.fromhex(
        "0100000000001000800000aa00389b71"
    )
    fmt = (
        struct.pack(
            "<HHIIHHH",
            0xFFFE,
            channels,
            sample_rate,
            byte_rate,
            block_align,
            24,
            22,
        )
        + struct.pack("<HI", 24, 0)
        + pcm_guid
    )
    riff_size = 4 + 8 + len(fmt) + 8 + len(samples)
    path.write_bytes(
        b"RIFF"
        + struct.pack("<I", riff_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"data"
        + struct.pack("<I", len(samples))
        + bytes(samples)
    )


def _fixture(
    tmp_path: Path,
    *,
    output_name: str = "separation",
    backend_id: str = FAKE_SEPARATION_BACKEND_ID,
    roles: tuple[str, ...] = ("bass", "drums"),
) -> tuple[SeparationRequest, SeparationRunMetadata]:
    source = tmp_path / "canonical.wav"
    checkpoint = tmp_path / "fixture.checkpoint"
    if not source.exists():
        _write_pcm24_wave(source)
    if not checkpoint.exists():
        checkpoint.write_bytes(b"deterministic fake checkpoint\n")
    source_sha256 = file_sha256(source)
    checkpoint_sha256 = file_sha256(checkpoint)
    request = SeparationRequest.create(
        source_path=source,
        output_dir=tmp_path / output_name,
        checkpoint_path=checkpoint,
        source_id=f"sha256:{source_sha256}",
        source_sha256=source_sha256,
        canonical_sha256=source_sha256,
        source_geometry=SeparationAudioGeometry(
            sample_rate=24_000,
            channels=1,
            frames=24,
            duration_seconds=24 / 24_000,
        ),
        scope="broad",
        parent_node_id=None,
        backend_id=backend_id,
        checkpoint_id="fake-fixture",
        checkpoint_sha256=checkpoint_sha256,
        requested_roles=roles,
        settings={"algorithm": "identity-target-silent-residual"},
        seed=17,
    )
    return request, SeparationRunMetadata()


def _only_receipt_remains(output_dir: Path) -> None:
    assert sorted(
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
    ) == [SEPARATION_RECEIPT_FILENAME]
    assert not (output_dir / ".staging").exists()


def test_run_plan_is_path_free_frozen_and_binds_run_id(
    tmp_path: Path,
) -> None:
    request, metadata = _fixture(tmp_path)
    relocated, _ = _fixture(tmp_path, output_name="elsewhere")
    plan = SeparationRunPlan.create(request, metadata)
    relocated_plan = SeparationRunPlan.create(relocated, metadata)

    assert plan.run_id == relocated_plan.run_id
    assert plan.run_id == f"separation-run:{plan.plan_sha256}"
    assert str(tmp_path) not in json.dumps(plan.to_dict())
    plan.validate_run_id(plan.run_id)
    with pytest.raises(ValueError, match="not bound"):
        plan.validate_run_id(f"separation-run:{'0' * 64}")
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.device = "mps"  # type: ignore[misc]
    with pytest.raises(TypeError):
        plan.runtime["name"] = "changed"  # type: ignore[index]


def test_controlled_fake_complete_run_persists_parent_owned_evidence(
    tmp_path: Path,
) -> None:
    request, metadata = _fixture(tmp_path)
    plan = SeparationRunPlan.create(request, metadata)

    receipt = run_separation(
        request,
        FakeSeparationBackend(),
        metadata,
    )

    assert receipt.status == "complete"
    assert receipt.loadable is True
    assert receipt.run_id == plan.run_id
    assert receipt.run_plan_sha256 == plan.plan_sha256
    assert receipt.to_dict()["run_plan"] == plan.to_dict()
    plan.validate_run_id(receipt.run_id)
    assert REAL_SEPARATION_BACKENDS_SUPPORTED is False
    assert SEPARATION_CACHE_REPLAY_SUPPORTED is False
    assert receipt.effects == {
        "checkpoint_mutated": False,
        "model_downloaded": False,
        "network_used": False,
        "outside_output_writes": False,
        "source_mutated": False,
    }
    assert receipt.quality is not None
    assert receipt.quality["status"] == "review_required"
    assert receipt.quality["reconstruction"]["passed"] is True
    assert all(
        evidence["status"] == "not_measured"
        and evidence["metric"] is None
        and evidence["score"] is None
        and evidence["reference_id"] is None
        for evidence in receipt.quality["leakage"].values()
    )
    assert stat_private(request.output_dir)
    assert not (request.output_dir / ".staging").exists()

    expected_paths = {
        "QUALITY/separation-quality.json",
        "RESIDUALS/bass-residual.wav",
        "RESIDUALS/drums-residual.wav",
        "STEMS/bass-target.wav",
        "STEMS/drums-target.wav",
        SEPARATION_RECEIPT_FILENAME,
    }
    assert {
        path.relative_to(request.output_dir).as_posix()
        for path in request.output_dir.rglob("*")
        if path.is_file()
    } == expected_paths
    for artifact in (
        *receipt.outputs["targets"],
        *receipt.outputs["residuals"],
    ):
        artifact_path = request.output_dir / artifact["path"]
        assert artifact_path.is_file()
        assert file_sha256(artifact_path) == artifact["sha256"]
        assert artifact_path.stat().st_nlink == 1

    receipt_path = request.output_dir / SEPARATION_RECEIPT_FILENAME
    assert receipt_path.read_bytes() == receipt.canonical_bytes()
    assert SeparationRunReceipt.from_json(
        receipt_path.read_bytes()
    ).to_dict() == receipt.to_dict()
    quality_path = request.output_dir / SEPARATION_QUALITY_RELATIVE_PATH
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    assert quality_path.read_bytes() == canonical_json_bytes(quality)
    assert quality["run_plan"] == plan.to_dict()
    assert quality["run_plan_sha256"] == plan.plan_sha256
    assert quality["run_id"] == receipt.run_id == plan.run_id
    assert hashlib.sha256(
        canonical_json_bytes(quality["run_plan"])
    ).hexdigest() == quality["run_plan_sha256"]
    assert (
        quality["run_plan"]["runner"]["module_sha256"]
        == file_sha256(Path(separation_module.__file__))
    )
    assert (
        receipt.backend["commit"]
        == quality["run_plan"]["runner"]["module_sha256"][:40]
    )
    assert quality["status"] == "review_required"
    assert quality["reconstruction"]["passed"] is True
    assert quality["reconstruction_is_accuracy_evidence"] is False
    assert "not be promoted" in quality["limitations"][-1]
    assert not list(request.output_dir.rglob("*.tmp"))


def stat_private(path: Path) -> bool:
    return os.stat(path).st_mode & 0o077 == 0


def test_controlled_fake_is_deterministic_across_private_output_roots(
    tmp_path: Path,
) -> None:
    first, metadata = _fixture(tmp_path, output_name="first")
    second, _ = _fixture(tmp_path, output_name="second")

    first_receipt = run_separation(
        first,
        FakeSeparationBackend(),
        metadata,
    )
    second_receipt = run_separation(
        second,
        FakeSeparationBackend(),
        metadata,
    )

    assert first_receipt.run_id == second_receipt.run_id
    assert first_receipt.outputs == second_receipt.outputs
    assert first_receipt.quality == second_receipt.quality
    assert (
        first_receipt.execution["wall_time_seconds"] > 0
        and second_receipt.execution["wall_time_seconds"] > 0
    )
    assert (
        first.output_dir / SEPARATION_QUALITY_RELATIVE_PATH
    ).read_bytes() == (
        second.output_dir / SEPARATION_QUALITY_RELATIVE_PATH
    ).read_bytes()


@pytest.mark.parametrize(
    "change",
    ("source_hash", "checkpoint_hash", "geometry"),
)
def test_preflight_rejects_unverified_inputs_before_output_creation(
    tmp_path: Path,
    change: str,
) -> None:
    request, metadata = _fixture(tmp_path)
    if change == "source_hash":
        request = dataclasses.replace(
            request,
            canonical_sha256="0" * 64,
        )
        message = "source canonical SHA-256"
    elif change == "checkpoint_hash":
        request = dataclasses.replace(
            request,
            checkpoint_sha256="1" * 64,
        )
        message = "checkpoint SHA-256"
    else:
        request = dataclasses.replace(
            request,
            source_geometry=SeparationAudioGeometry(
                sample_rate=24_000,
                channels=1,
                frames=25,
                duration_seconds=25 / 24_000,
            ),
        )
        message = "geometry"

    with pytest.raises(ValueError, match=message):
        run_separation(
            request,
            FakeSeparationBackend(),
            metadata,
        )
    assert not request.output_dir.exists()


def test_existing_output_root_is_never_reused_or_cleaned(
    tmp_path: Path,
) -> None:
    request, metadata = _fixture(tmp_path)
    request.output_dir.mkdir()
    sentinel = request.output_dir / "keep.txt"
    sentinel.write_text("owned by caller", encoding="utf-8")

    with pytest.raises(FileExistsError, match="fresh"):
        run_separation(
            request,
            FakeSeparationBackend(),
            metadata,
        )

    assert sentinel.read_text(encoding="utf-8") == "owned by caller"


class _ProtocolLookalike:
    backend_id = FAKE_SEPARATION_BACKEND_ID

    def run(self, request, *, cancellation_requested=None):
        raise AssertionError("must not be called")


class _FakeSubclass(FakeSeparationBackend):
    pass


@pytest.mark.parametrize(
    "backend",
    (_ProtocolLookalike(), _FakeSubclass()),
)
def test_protocol_lookalikes_and_fake_subclasses_cannot_complete(
    tmp_path: Path,
    backend,
) -> None:
    request, metadata = _fixture(tmp_path)

    with pytest.raises(RuntimeError, match="isolated worker"):
        run_separation(request, backend, metadata)

    assert not request.output_dir.exists()


def test_backend_id_must_match_before_output_creation(
    tmp_path: Path,
) -> None:
    request, metadata = _fixture(tmp_path, backend_id="another-backend")

    with pytest.raises(ValueError, match="backend ID"):
        run_separation(
            request,
            FakeSeparationBackend(),
            metadata,
        )

    assert not request.output_dir.exists()


@pytest.mark.parametrize("status", ("failed", "cancelled"))
def test_failed_and_cancelled_receipts_are_path_free_and_nonloadable(
    tmp_path: Path,
    status: str,
) -> None:
    request, metadata = _fixture(tmp_path)
    plan = SeparationRunPlan.create(request, metadata)

    receipt = run_separation(
        request,
        FakeSeparationBackend(outcome=status),
        metadata,
    )

    assert receipt.status == status
    assert receipt.loadable is False
    assert receipt.run_plan_sha256 == plan.plan_sha256
    assert receipt.to_dict()["run_plan"] == plan.to_dict()
    assert receipt.run_id == plan.run_id
    assert receipt.outputs == {"targets": (), "residuals": ()}
    assert receipt.quality is None
    serialized = receipt.canonical_bytes()
    assert str(tmp_path).encode() not in serialized
    _only_receipt_remains(request.output_dir)


def test_cancellation_after_partial_fake_work_cleans_all_wavs(
    tmp_path: Path,
) -> None:
    request, metadata = _fixture(tmp_path)
    receipt = run_separation(
        request,
        FakeSeparationBackend(cancel_after_roles=1),
        metadata,
    )

    assert receipt.status == "cancelled"
    assert receipt.loadable is False
    _only_receipt_remains(request.output_dir)


def test_undeclared_backend_artifact_invalidates_and_cleans_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, metadata = _fixture(tmp_path)
    original_run = FakeSeparationBackend.run

    def run_with_extra(self, staged_request, *, cancellation_requested=None):
        result = original_run(
            self,
            staged_request,
            cancellation_requested=cancellation_requested,
        )
        extra = staged_request.output_dir / "undeclared.wav"
        _write_pcm24_wave(extra)
        return result

    monkeypatch.setattr(FakeSeparationBackend, "run", run_with_extra)
    receipt = run_separation(
        request,
        FakeSeparationBackend(),
        metadata,
    )

    assert receipt.status == "failed"
    assert receipt.error["code"] == "invalid_backend_output"
    _only_receipt_remains(request.output_dir)


def test_undeclared_empty_backend_directory_invalidates_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, metadata = _fixture(tmp_path)
    original_run = FakeSeparationBackend.run

    def run_with_empty_dir(
        self,
        staged_request,
        *,
        cancellation_requested=None,
    ):
        result = original_run(
            self,
            staged_request,
            cancellation_requested=cancellation_requested,
        )
        (staged_request.output_dir / "UNDECLARED").mkdir()
        return result

    monkeypatch.setattr(FakeSeparationBackend, "run", run_with_empty_dir)
    receipt = run_separation(
        request,
        FakeSeparationBackend(),
        metadata,
    )

    assert receipt.status == "failed"
    _only_receipt_remains(request.output_dir)


def test_interrupt_cleans_owned_staging_and_is_reraised(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, metadata = _fixture(tmp_path)

    def interrupt(self, staged_request, *, cancellation_requested=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(FakeSeparationBackend, "run", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run_separation(
            request,
            FakeSeparationBackend(),
            metadata,
        )

    assert not request.output_dir.exists()
    assert not list(tmp_path.glob(f".{request.output_dir.name}.*-*"))


def test_changed_staging_identity_is_never_recursively_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, metadata = _fixture(tmp_path)
    original_run = FakeSeparationBackend.run
    replacement: list[Path] = []

    def replace_staging(
        self,
        staged_request,
        *,
        cancellation_requested=None,
    ):
        result = original_run(
            self,
            staged_request,
            cancellation_requested=cancellation_requested,
        )
        displaced = staged_request.output_dir.with_name(
            staged_request.output_dir.name + ".displaced"
        )
        staged_request.output_dir.rename(displaced)
        staged_request.output_dir.mkdir(mode=0o700)
        sentinel = staged_request.output_dir / "unrelated.txt"
        sentinel.write_text("do not delete", encoding="utf-8")
        replacement.append(sentinel)
        return result

    monkeypatch.setattr(FakeSeparationBackend, "run", replace_staging)
    receipt = run_separation(
        request,
        FakeSeparationBackend(),
        metadata,
    )

    assert receipt.status == "failed"
    assert replacement[0].read_text(encoding="utf-8") == "do not delete"
    _only_receipt_remains(request.output_dir)
    shutil.rmtree(replacement[0].parent)


@pytest.mark.parametrize(
    ("constant", "value", "message"),
    (
        ("_MAX_CHECKPOINT_BYTES", 1, "checkpoint exceeds"),
        ("_MAX_AGGREGATE_OUTPUT_BYTES", 1, "projected separation"),
        ("_MAX_TERMINAL_FILE_COUNT", 1, "file count"),
    ),
)
def test_resource_bounds_fail_before_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    constant: str,
    value: int,
    message: str,
) -> None:
    request, metadata = _fixture(tmp_path)
    monkeypatch.setattr(separation_module, constant, value)

    with pytest.raises(ValueError, match=message):
        run_separation(
            request,
            FakeSeparationBackend(),
            metadata,
        )

    assert not request.output_dir.exists()
    assert not list(tmp_path.glob(f".{request.output_dir.name}.*-*"))


def test_metadata_cannot_execute_arbitrary_cancellation_callable() -> None:
    with pytest.raises(TypeError):
        SeparationRunMetadata(  # type: ignore[call-arg]
            cancellation_requested=lambda: False
        )

    class TokenSubclass(SeparationCancellationToken):
        pass

    with pytest.raises(ValueError, match="parent-owned"):
        SeparationRunMetadata(cancellation_token=TokenSubclass())


def test_symlink_backend_artifact_invalidates_and_cleans_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, metadata = _fixture(tmp_path)
    original_run = FakeSeparationBackend.run

    def run_with_symlink(self, staged_request, *, cancellation_requested=None):
        result = original_run(
            self,
            staged_request,
            cancellation_requested=cancellation_requested,
        )
        first = result.outputs[0]
        first.target_path.unlink()
        first.target_path.symlink_to(staged_request.source_path)
        return result

    monkeypatch.setattr(FakeSeparationBackend, "run", run_with_symlink)
    receipt = run_separation(
        request,
        FakeSeparationBackend(),
        metadata,
    )

    assert receipt.status == "failed"
    assert receipt.error["code"] == "invalid_backend_output"
    _only_receipt_remains(request.output_dir)


def test_source_mutation_after_backend_call_blocks_loadable_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, metadata = _fixture(tmp_path)
    original_run = FakeSeparationBackend.run

    def run_then_mutate(self, staged_request, *, cancellation_requested=None):
        result = original_run(
            self,
            staged_request,
            cancellation_requested=cancellation_requested,
        )
        with staged_request.source_path.open("ab") as handle:
            handle.write(b"changed")
        return result

    monkeypatch.setattr(FakeSeparationBackend, "run", run_then_mutate)
    receipt = run_separation(
        request,
        FakeSeparationBackend(),
        metadata,
    )

    assert receipt.status == "failed"
    assert receipt.loadable is False
    assert receipt.effects["source_mutated"] is True
    assert receipt.error["code"] == "immutable_input_changed"
    _only_receipt_remains(request.output_dir)


def test_backend_path_escape_is_rejected_without_deleting_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, metadata = _fixture(tmp_path)
    original_run = FakeSeparationBackend.run

    def run_with_escape(self, staged_request, *, cancellation_requested=None):
        result = original_run(
            self,
            staged_request,
            cancellation_requested=cancellation_requested,
        )
        first, *rest = result.outputs
        escaped = SeparationBackendOutput(
            role=first.role,
            target_path=staged_request.source_path,
            residual_path=first.residual_path,
        )
        return SeparationResult(
            status="complete",
            outputs=(escaped, *rest),
        )

    source_bytes = request.source_path.read_bytes()
    monkeypatch.setattr(FakeSeparationBackend, "run", run_with_escape)
    receipt = run_separation(
        request,
        FakeSeparationBackend(),
        metadata,
    )

    assert receipt.status == "failed"
    assert receipt.error["code"] == "invalid_backend_output"
    assert request.source_path.read_bytes() == source_bytes
    _only_receipt_remains(request.output_dir)


def test_controlled_fake_accepts_wave_format_extensible_pcm24(
    tmp_path: Path,
) -> None:
    request, metadata = _fixture(tmp_path)
    _write_extensible_pcm24_wave(request.source_path)
    source_sha256 = file_sha256(request.source_path)
    request = dataclasses.replace(
        request,
        source_id=f"sha256:{source_sha256}",
        source_sha256=source_sha256,
        canonical_sha256=source_sha256,
    )

    receipt = run_separation(
        request,
        FakeSeparationBackend(),
        metadata,
    )

    assert receipt.status == "complete"
    target = request.output_dir / receipt.outputs["targets"][0]["path"]
    assert target.read_bytes()[20:22] == struct.pack("<H", 0xFFFE)
    assert receipt.quality["reconstruction"]["passed"] is True
