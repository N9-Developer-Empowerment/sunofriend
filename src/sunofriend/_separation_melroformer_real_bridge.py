"""Fail-closed private bridge for the exact Kim Vocal 2 MLX checkpoint.

This module has no public route and imports no tensor runtime at module import
time. The explicit loader re-verifies every local artifact, constructs only
the fixed audited source overlay, binds the checkpoint through an already-open
descriptor, and proves complete sanitizer/key/shape coverage. Bounded private
audio inference remains separate from every product route and persists no
audio.
"""

from __future__ import annotations

import hashlib
import io
import importlib.metadata
import json
import os
import fcntl
import platform
import re
import stat
import sys
import time
import types
import wave
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, BinaryIO, Iterator, Mapping, Sequence

from ._separation_melroformer_adapter_contract import (
    REAL_ENGINE_SCHEMA,
    _RealMelRoFormerAdapterObservation,
    _RealMelRoFormerEngineResult,
    _accept_private_melroformer_real_result,
)
from ._separation_melroformer_artifacts import (
    APPROVAL_RECORDED_AT,
    CONFIG_NAME,
    _inspect_companion_files,
)
from ._separation_melroformer_runtime_evidence import (
    SOURCE_MANIFEST_SHA256,
    SOURCE_REVISION,
    _expected_source_manifest,
    _read_exact_regular_file,
    _verify_private_melroformer_source_tree,
)
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from ._separation_safetensors_inspection import (
    _inspect_private_safetensors,
    _inspect_private_safetensors_descriptor,
)


SCHEMA = "sunofriend.private-melroformer-real-bridge-probe.v1"
CANDIDATE_ID = "mlx-melroformer-kim-vocal-2"
_RUNTIME_VERSIONS = {
    "mlx": "0.31.2",
    "mlx-metal": "0.31.2",
    "numpy": "2.3.5",
}
_SUPPORTED_PYTHON_MINORS = frozenset({(3, 12), (3, 13)})
_PACKAGE_PATHS = {
    "mlx_audio": "mlx_audio",
    "mlx_audio.sts": "mlx_audio/sts",
    "mlx_audio.sts.models": "mlx_audio/sts/models",
    "mlx_audio.sts.models.mel_roformer": "mlx_audio/sts/models/mel_roformer",
}
_MODULE_PATHS = {
    "mlx_audio.dsp": "mlx_audio/dsp.py",
    "mlx_audio.sts.models.mel_roformer.config": (
        "mlx_audio/sts/models/mel_roformer/config.py"
    ),
    "mlx_audio.sts.models.mel_roformer.model": (
        "mlx_audio/sts/models/mel_roformer/model.py"
    ),
}
_OFFLINE_ENVIRONMENT = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "PYTHONNOUSERSITE": "1",
}
_MASK_MLP_RE = re.compile(
    r"^(mask_estimators\.\d+\.to_freqs\.\d+)\.0\.(\d+)\.(weight|bias)$"
)
_PERMITTED_DROPPED_SUFFIX = ".rotary_embed.freqs"
MAXIMUM_PROBE_FRAMES = 352_800
MINIMUM_PROBE_FRAMES = 4_096
MAXIMUM_EXCERPT_FRAMES = 661_500
NOMINAL_CHUNK_FRAMES = 352_800
NOMINAL_HOP_FRAMES = 176_400
_REAL_INFERENCE_EFFECTS = {
    "filesystem_accessed": True,
    "filesystem_written": False,
    "network_used": False,
    "package_installed": False,
    "checkpoint_opened": True,
    "tensor_deserialized": True,
    "model_imported": True,
    "process_started": False,
    "audio_inference_called": True,
}
_AUTHORISED_EXCERPT_SCHEMA = "sunofriend.private-authorised-separation-excerpt.v1"
_PRIVATE_REFERENCE_CORPUS_SCHEMA = (
    "sunofriend.private-reference-separation-corpus.v1"
)
_CREATOR_RIGHTS_AUTHORITY = "creator_and_copyright_holder"
_PRIVATE_REFERENCE_RIGHTS_AUTHORITY = (
    "user_authorised_private_local_evaluation"
)
_PERMITTED_RIGHTS_AUTHORITIES = frozenset(
    {_CREATOR_RIGHTS_AUTHORITY, _PRIVATE_REFERENCE_RIGHTS_AUTHORITY}
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class _PrivateMelRoFormerHandle:
    """Internal loaded model plus path-free probe evidence."""

    model: Any
    mx: Any
    np: Any
    device: str
    config: Any
    sanitized_weight_keys: tuple[str, ...]
    expected_model_keys: tuple[str, ...]
    dropped_raw_weight_keys: tuple[str, ...]
    evidence: Mapping[str, Any]


def _load_private_authorised_excerpt(
    handle: _PrivateMelRoFormerHandle,
    *,
    report_path: str | Path,
    expected_report_sha256: str,
) -> tuple[Any, Mapping[str, Any]]:
    """Load one report-bound PCM24 excerpt without exposing its path."""

    if type(handle) is not _PrivateMelRoFormerHandle:
        raise ValueError("MelRoFormer excerpt loading requires an exact private handle")
    return _load_private_authorised_excerpt_pcm24(
        handle.np,
        report_path=report_path,
        expected_report_sha256=expected_report_sha256,
    )


def _load_private_authorised_excerpt_pcm24(
    np: Any,
    *,
    report_path: str | Path,
    expected_report_sha256: str,
) -> tuple[Any, Mapping[str, Any]]:
    """Load one report-bound PCM24 excerpt without requiring a model handle."""

    if not isinstance(expected_report_sha256, str) or not _SHA256_RE.fullmatch(
        expected_report_sha256
    ):
        raise ValueError("MelRoFormer authorisation report hash is invalid")
    report = Path(report_path).expanduser().absolute()
    attached = report.lstat()
    if attached.st_size > 2 * 1024 * 1024:
        raise ValueError("MelRoFormer authorisation report is too large")
    raw_report = _read_exact_regular_file(
        report,
        expected_sha256=expected_report_sha256,
        expected_bytes=attached.st_size,
    )
    document = json.loads(
        raw_report,
        object_pairs_hook=_reject_duplicate_json_object,
    )
    if not isinstance(document, dict):
        raise ValueError("MelRoFormer authorisation report is not an object")
    self_hash = document.get("document_sha256")
    canonical = dict(document)
    canonical.pop("document_sha256", None)
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    if self_hash != hashlib.sha256(encoded).hexdigest():
        raise ValueError("MelRoFormer authorisation report self-hash differs")
    rights_authority = _validate_authorisation_document(document)
    local_input = document["original"]["local_model_input"]
    artifact = local_input["artifact"]
    relative = artifact["path"]
    if relative != "LOCAL-MODEL-INPUT/source-44100.wav":
        raise ValueError("MelRoFormer authorised excerpt path differs")
    excerpt_path = report.parent / relative
    if (
        report.parent.resolve(strict=True)
        not in excerpt_path.resolve(strict=True).parents
    ):
        raise ValueError("MelRoFormer authorised excerpt escapes its report root")
    raw_audio = _read_exact_regular_file(
        excerpt_path,
        expected_sha256=artifact["sha256"],
        expected_bytes=artifact["bytes"],
    )
    audio = _decode_pcm24_excerpt(np, raw_audio)
    geometry = local_input["geometry"]
    if (
        audio.shape != (geometry["frames"], geometry["channels"])
        or geometry["sample_rate"] != 44_100
        or not MINIMUM_PROBE_FRAMES <= len(audio) <= MAXIMUM_EXCERPT_FRAMES
    ):
        raise ValueError("MelRoFormer authorised excerpt geometry differs")
    evidence = {
        "schema": "sunofriend.private-melroformer-authorised-input.v1",
        "track_id": document["corpus"]["track_id"],
        "track_title": document["corpus"]["track_title"],
        "report_sha256": expected_report_sha256,
        "audio_sha256": artifact["sha256"],
        "source_start_seconds": document["excerpt"]["start_seconds"],
        "source_end_seconds": document["excerpt"]["end_seconds"],
        "sample_rate": geometry["sample_rate"],
        "channels": geometry["channels"],
        "frames": geometry["frames"],
        "rights_authority": rights_authority,
        "evidence_scope": document["evidence_scope"],
        "audio_persisted_by_bridge": False,
    }
    return audio, MappingProxyType(evidence)


def _load_private_melroformer_model(
    *,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
    device: str = "gpu",
    checkpoint_descriptor: int | None = None,
) -> _PrivateMelRoFormerHandle:
    """Load the exact model without calling upstream ``from_pretrained``."""

    if device not in {"gpu", "cpu"}:
        raise ValueError("MelRoFormer device must be gpu or cpu")
    runtime = _verify_runtime()
    source = Path(source_root).expanduser().absolute()
    checkpoint = Path(checkpoint_path).expanduser().absolute()
    companions = Path(companion_root).expanduser().absolute()
    source_observation = _verify_private_melroformer_source_tree(source)
    companion_observation = _inspect_companion_files(companions)
    if checkpoint_descriptor is None:
        static_inspection = _inspect_private_safetensors(
            checkpoint,
            expected_bytes=CONVERSION_CHECKPOINT_BYTES,
            expected_sha256=CONVERSION_CHECKPOINT_SHA256,
        )
        checkpoint_transport = "verified_path_to_private_descriptor"
    else:
        static_inspection = _inspect_private_safetensors_descriptor(
            checkpoint_descriptor,
            expected_bytes=CONVERSION_CHECKPOINT_BYTES,
            expected_sha256=CONVERSION_CHECKPOINT_SHA256,
        )
        checkpoint_transport = "inherited_read_only_descriptor"

    if not companion_observation["all_cryptographic_identities_verified"]:
        raise ValueError("MelRoFormer companion identities differ")
    _require_clean_source_namespace()
    _apply_offline_environment()

    started = time.perf_counter()
    import mlx.core as mx
    import numpy as np
    from mlx.utils import tree_flatten

    mx.set_default_device(mx.gpu if device == "gpu" else mx.cpu)
    if str(mx.default_device()) != f"Device({device}, 0)":
        raise RuntimeError("MelRoFormer MLX device selection differs")

    source_manifest = _expected_source_manifest()
    manifest_files = {item["path"]: item for item in source_manifest["files"]}
    _install_namespace_packages(source)
    try:
        _execute_audited_module(
            "mlx_audio.dsp",
            source=source,
            item=manifest_files[_MODULE_PATHS["mlx_audio.dsp"]],
        )
        config_module = _execute_audited_module(
            "mlx_audio.sts.models.mel_roformer.config",
            source=source,
            item=manifest_files[
                _MODULE_PATHS["mlx_audio.sts.models.mel_roformer.config"]
            ],
        )
        model_module = _execute_audited_module(
            "mlx_audio.sts.models.mel_roformer.model",
            source=source,
            item=manifest_files[
                _MODULE_PATHS["mlx_audio.sts.models.mel_roformer.model"]
            ],
        )
        config = config_module.MelRoFormerConfig.kim_vocal_2()
        _verify_fixed_config(config, companions / CONFIG_NAME)
        model = model_module.MelRoFormer(config)
        expected = dict(tree_flatten(model.parameters()))

        checkpoint_stream = (
            _verified_checkpoint_stream(checkpoint)
            if checkpoint_descriptor is None
            else _verified_checkpoint_descriptor_stream(checkpoint_descriptor)
        )
        with checkpoint_stream as stream:
            weights = dict(mx.load(stream, format="safetensors"))
        sanitized = model.sanitize(weights)
        coverage = _validate_weight_inventory(
            raw=weights,
            sanitized=sanitized,
            expected=expected,
        )
        model.load_weights(list(sanitized.items()), strict=False)
        mx.eval(model.parameters())
        model.eval()
        peak_memory = int(mx.get_peak_memory())
    except BaseException:
        _remove_source_namespace()
        raise

    elapsed = time.perf_counter() - started
    evidence = {
        "schema": SCHEMA,
        "status": "verified_model_constructed_and_weights_bound_not_inferred",
        "candidate_id": CANDIDATE_ID,
        "approval": {
            "recorded": True,
            "recorded_at": APPROVAL_RECORDED_AT,
            "scope": "exact checkpoint for private local evaluation only",
            "redistribution_permitted": False,
        },
        "source": {
            "revision": SOURCE_REVISION,
            "manifest_sha256": SOURCE_MANIFEST_SHA256,
            "verified": source_observation["status"] == "verified_not_imported",
            "package_initializers_executed": [],
            "executed_modules": sorted(_MODULE_PATHS),
            "upstream_from_pretrained_called": False,
        },
        "checkpoint": {
            "bytes": CONVERSION_CHECKPOINT_BYTES,
            "sha256": CONVERSION_CHECKPOINT_SHA256,
            "static_inspection_schema": static_inspection["schema"],
            "static_tensor_count": static_inspection["tensor_count"],
            "descriptor_pinned_during_tensor_load": True,
            "transport": checkpoint_transport,
            "path_reopened_by_loader": checkpoint_descriptor is None,
            "descriptor_number_retained": False,
        },
        "runtime": {**runtime, "mlx_device": device},
        "config": {
            "family": config.checkpoint_family,
            "sample_rate": config.sample_rate,
            "channels": 2,
            "chunk_frames": config.chunk_size,
            "overlap": config.num_overlap,
        },
        "weight_coverage": coverage,
        "measurement": {
            "load_seconds": elapsed,
            "mlx_peak_memory_bytes": peak_memory,
            "audio_inference_called": False,
        },
        "isolation": {
            "offline_environment_applied": True,
            "network_denial_os_enforced": False,
            "network_used": False,
            "child_process_started": False,
            "fresh_process_required_for_inference": True,
        },
        "permissions": {
            "private_probe_permitted": True,
            "private_inference_permitted": False,
            "worker_start_permitted": False,
            "publication_permitted": False,
            "automatic_selection_permitted": False,
            "product_route_permitted": False,
        },
        "effects": {
            "filesystem_accessed": True,
            "filesystem_written": False,
            "checkpoint_opened": True,
            "tensor_deserialized": True,
            "model_imported": True,
            "audio_inference_called": False,
            "network_used": False,
            "package_installed": False,
            "process_started": False,
        },
    }
    return _PrivateMelRoFormerHandle(
        model=model,
        mx=mx,
        np=np,
        device=device,
        config=config,
        sanitized_weight_keys=tuple(sorted(sanitized)),
        expected_model_keys=tuple(sorted(expected)),
        dropped_raw_weight_keys=tuple(coverage["dropped_raw_weight_keys"]),
        evidence=MappingProxyType(evidence),
    )


def _infer_private_melroformer_probe(
    handle: _PrivateMelRoFormerHandle,
    source: Any,
    *,
    sample_rate: int,
) -> _RealMelRoFormerAdapterObservation:
    """Run one bounded in-memory chunk and validate it without persistence."""

    _require_sample_rate(sample_rate)
    audio = _validate_source_array(handle, source, maximum_frames=MAXIMUM_PROBE_FRAMES)
    vocals, elapsed, peak_memory = _run_model_chunk_array(handle, audio)
    return _validate_real_inference(
        handle,
        audio,
        vocals,
        sample_rate=sample_rate,
        inference_seconds=elapsed,
        peak_memory_bytes=peak_memory,
        chunk_count=1,
        chunk_frames=len(audio),
        hop_frames=len(audio),
    )


def _infer_private_melroformer_excerpt(
    handle: _PrivateMelRoFormerHandle,
    source: Any,
    *,
    sample_rate: int,
) -> _RealMelRoFormerAdapterObservation:
    """Run up to 15 seconds using fixed eight-second 50%-overlap chunks."""

    _require_sample_rate(sample_rate)
    audio = _validate_source_array(
        handle, source, maximum_frames=MAXIMUM_EXCERPT_FRAMES
    )
    if len(audio) <= MAXIMUM_PROBE_FRAMES:
        return _infer_private_melroformer_probe(handle, audio, sample_rate=sample_rate)
    np = handle.np
    accumulator = np.zeros(audio.shape, dtype=np.float64)
    weight_sum = np.zeros((len(audio),), dtype=np.float64)
    chunks = _plan_excerpt_chunks(len(audio))
    total_seconds = 0.0
    maximum_peak_memory = 0
    for start, end in chunks:
        vocals, elapsed, peak_memory = _run_model_chunk_array(handle, audio[start:end])
        weights = _chunk_crossfade_weights(
            end - start,
            fade_in=start > 0,
            fade_out=end < len(audio),
            np=np,
        )
        accumulator[start:end] += vocals.astype(np.float64) * weights[:, None]
        weight_sum[start:end] += weights
        total_seconds += elapsed
        maximum_peak_memory = max(maximum_peak_memory, peak_memory)
        handle.mx.clear_cache()
    if not bool((weight_sum > 0).all()):
        raise ValueError("MelRoFormer excerpt overlap weights left an uncovered frame")
    vocals = (accumulator / weight_sum[:, None]).astype(np.float32)
    return _validate_real_inference(
        handle,
        audio,
        vocals,
        sample_rate=sample_rate,
        inference_seconds=total_seconds,
        peak_memory_bytes=maximum_peak_memory,
        chunk_count=len(chunks),
        chunk_frames=NOMINAL_CHUNK_FRAMES,
        hop_frames=NOMINAL_HOP_FRAMES,
    )


def _validate_source_array(
    handle: _PrivateMelRoFormerHandle, source: Any, *, maximum_frames: int
) -> Any:
    if type(handle) is not _PrivateMelRoFormerHandle:
        raise ValueError("MelRoFormer inference requires an exact private handle")
    np = handle.np
    audio = np.asarray(source)
    if audio.dtype != np.float32:
        raise ValueError("MelRoFormer inference source must be float32")
    if (
        audio.ndim != 2
        or audio.shape[1] != 2
        or not MINIMUM_PROBE_FRAMES <= audio.shape[0] <= maximum_frames
    ):
        raise ValueError(
            "MelRoFormer inference source geometry is outside probe bounds"
        )
    if not bool(np.isfinite(audio).all()) or float(np.max(np.abs(audio))) > 1.0:
        raise ValueError("MelRoFormer inference source samples are outside bounds")
    return np.ascontiguousarray(audio)


def _validate_authorisation_document(document: Mapping[str, Any]) -> str:
    try:
        permission = document["corpus"]["permission"]
        local_input = document["original"]["local_model_input"]
        artifact = local_input["artifact"]
        geometry = local_input["geometry"]
        excerpt = document["excerpt"]
        product_permissions = document["permissions"]
    except (KeyError, TypeError) as exc:
        raise ValueError("MelRoFormer authorisation report is incomplete") from exc
    if not all(
        isinstance(value, Mapping)
        for value in (
            document.get("corpus"),
            permission,
            document.get("original"),
            local_input,
            artifact,
            geometry,
            excerpt,
            product_permissions,
        )
    ):
        raise ValueError("MelRoFormer authorisation report is incomplete")
    if (
        document.get("schema") != _AUTHORISED_EXCERPT_SCHEMA
        or document.get("status") != "complete_review_required"
        or document.get("evidence_scope") != "private_development_only"
        or not isinstance(document["corpus"].get("track_id"), str)
        or not document["corpus"]["track_id"]
        or not isinstance(document["corpus"].get("track_title"), str)
        or not document["corpus"]["track_title"]
    ):
        raise ValueError("MelRoFormer authorisation scope differs")
    rights_authority = _validated_rights_authority(document["corpus"], permission)
    if (
        type(artifact.get("bytes")) is not int
        or not 1 <= artifact["bytes"] <= 8 * 1024 * 1024
        or not isinstance(artifact.get("sha256"), str)
        or not _SHA256_RE.fullmatch(artifact["sha256"])
        or type(geometry.get("frames")) is not int
        or geometry
        != {
            "channels": 2,
            "duration_seconds": geometry.get("frames", 0) / 44_100,
            "frames": geometry.get("frames"),
            "sample_rate": 44_100,
        }
        or not MINIMUM_PROBE_FRAMES
        <= geometry.get("frames", 0)
        <= MAXIMUM_EXCERPT_FRAMES
    ):
        raise ValueError("MelRoFormer authorised model input differs")
    if (
        isinstance(excerpt.get("start_seconds"), bool)
        or not isinstance(excerpt.get("start_seconds"), (int, float))
        or isinstance(excerpt.get("end_seconds"), bool)
        or not isinstance(excerpt.get("end_seconds"), (int, float))
        or excerpt["end_seconds"] <= excerpt["start_seconds"]
        or abs(
            (excerpt["end_seconds"] - excerpt["start_seconds"])
            - geometry["duration_seconds"]
        )
        > 1e-9
    ):
        raise ValueError("MelRoFormer authorised excerpt clock differs")
    denied = (
        "accepted",
        "automatic_promotion",
        "automatic_selection",
        "production_eligible",
        "public_result",
        "simple_mode_available",
        "source_graph_activation",
        "studio_import_available",
    )
    if any(product_permissions.get(name) is not False for name in denied):
        raise ValueError("MelRoFormer authorisation product permissions differ")
    return rights_authority


def _validated_rights_authority(
    corpus: Mapping[str, Any], permission: Mapping[str, Any]
) -> str:
    if (
        permission.get("authority") == _CREATOR_RIGHTS_AUTHORITY
        and permission.get("allowed_use")
        == "download, study, transform and reuse"
    ):
        return _CREATOR_RIGHTS_AUTHORITY

    expected_private_permission_fields = {
        "public_demo_use",
        "recorded_on",
        "repository_distribution",
        "scope",
        "status",
    }
    if (
        corpus.get("manifest_schema") == _PRIVATE_REFERENCE_CORPUS_SCHEMA
        and corpus.get("authority_scope")
        == "track-specific private local evaluation only"
        and corpus.get("artist") is None
        and corpus.get("preferred_credit") is None
        and set(permission) == expected_private_permission_fields
        and permission.get("status") == "user_authorised"
        and permission.get("scope") == "private_local_evaluation_only"
        and permission.get("repository_distribution") is False
        and permission.get("public_demo_use") is False
        and isinstance(permission.get("recorded_on"), str)
        and permission["recorded_on"].strip()
    ):
        return _PRIVATE_REFERENCE_RIGHTS_AUTHORITY

    raise ValueError("MelRoFormer authorisation scope differs")


def _decode_pcm24_excerpt(np: Any, contents: bytes) -> Any:
    with wave.open(io.BytesIO(contents), "rb") as reader:
        if (
            reader.getnchannels() != 2
            or reader.getframerate() != 44_100
            or reader.getsampwidth() != 3
            or reader.getcomptype() != "NONE"
            or not MINIMUM_PROBE_FRAMES <= reader.getnframes() <= MAXIMUM_EXCERPT_FRAMES
        ):
            raise ValueError("MelRoFormer authorised WAV format differs")
        frames = reader.getnframes()
        raw = reader.readframes(frames)
        if len(raw) != frames * 2 * 3 or reader.readframes(1):
            raise ValueError("MelRoFormer authorised WAV payload differs")
    packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
    samples = (
        packed[:, 0].astype(np.int32)
        | packed[:, 1].astype(np.int32) << 8
        | packed[:, 2].astype(np.int32) << 16
    )
    samples = np.where(samples & 0x800000, samples - 0x1000000, samples)
    return np.ascontiguousarray(
        samples.astype(np.float32).reshape(frames, 2) / np.float32(8_388_608.0)
    )


def _reject_duplicate_json_object(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("MelRoFormer authorisation report has duplicate keys")
        result[key] = value
    return result


def _require_sample_rate(sample_rate: int) -> None:
    if type(sample_rate) is not int or sample_rate != 44_100:
        raise ValueError("MelRoFormer inference requires exact 44.1 kHz audio")


def _run_model_chunk_array(
    handle: _PrivateMelRoFormerHandle, audio: Any
) -> tuple[Any, float, int]:
    np = handle.np
    mx = handle.mx
    if not MINIMUM_PROBE_FRAMES <= len(audio) <= NOMINAL_CHUNK_FRAMES:
        raise ValueError("MelRoFormer model chunk is outside the measured bound")
    mx.reset_peak_memory()
    started = time.perf_counter()
    output = handle.model(mx.array(audio.T[None, :, :]))
    mx.eval(output)
    elapsed = time.perf_counter() - started
    vocals = np.array(output[0], copy=True).T.astype(np.float32, copy=False)
    if vocals.shape != audio.shape:
        raise ValueError("MelRoFormer inference output geometry differs")
    if not bool(np.isfinite(vocals).all()):
        raise ValueError("MelRoFormer inference output contains non-finite samples")
    return vocals, elapsed, int(mx.get_peak_memory())


def _validate_real_inference(
    handle: _PrivateMelRoFormerHandle,
    audio: Any,
    vocals: Any,
    *,
    sample_rate: int,
    inference_seconds: float,
    peak_memory_bytes: int,
    chunk_count: int,
    chunk_frames: int,
    hop_frames: int,
) -> _RealMelRoFormerAdapterObservation:
    _require_sample_rate(sample_rate)
    engine_result = _RealMelRoFormerEngineResult(
        schema=REAL_ENGINE_SCHEMA,
        engine_kind="private_real_kim_vocal_2",
        vocals=vocals.tolist(),
        sanitized_weight_keys=handle.sanitized_weight_keys,
        expected_model_keys=handle.expected_model_keys,
        dropped_raw_weight_keys=handle.dropped_raw_weight_keys,
        inference_seconds=inference_seconds,
        peak_memory_bytes=peak_memory_bytes,
        device=handle.device,
        chunk_count=chunk_count,
        chunk_frames=chunk_frames,
        hop_frames=hop_frames,
        effects=dict(_REAL_INFERENCE_EFFECTS),
    )
    return _accept_private_melroformer_real_result(
        audio.tolist(), sample_rate=sample_rate, engine_result=engine_result
    )


def _plan_excerpt_chunks(total_frames: int) -> tuple[tuple[int, int], ...]:
    if (
        isinstance(total_frames, bool)
        or not isinstance(total_frames, int)
        or not MINIMUM_PROBE_FRAMES <= total_frames <= MAXIMUM_EXCERPT_FRAMES
    ):
        raise ValueError("MelRoFormer excerpt frame count is outside bounds")
    if total_frames <= NOMINAL_CHUNK_FRAMES:
        return ((0, total_frames),)
    chunks: list[tuple[int, int]] = []
    start = 0
    while start < total_frames:
        end = min(start + NOMINAL_CHUNK_FRAMES, total_frames)
        chunks.append((start, end))
        if end == total_frames:
            break
        start += NOMINAL_HOP_FRAMES
    return tuple(chunks)


def _chunk_crossfade_weights(
    frames: int, *, fade_in: bool, fade_out: bool, np: Any
) -> Any:
    if isinstance(frames, bool) or not isinstance(frames, int) or frames < 1:
        raise ValueError("MelRoFormer chunk weight frame count is invalid")
    weights = np.ones((frames,), dtype=np.float64)
    fade_frames = min(NOMINAL_CHUNK_FRAMES - NOMINAL_HOP_FRAMES, frames)
    if fade_in:
        weights[:fade_frames] *= np.linspace(
            0.0, 1.0, fade_frames, endpoint=False, dtype=np.float64
        )
    if fade_out:
        weights[-fade_frames:] *= np.linspace(
            1.0, 0.0, fade_frames, endpoint=False, dtype=np.float64
        )
    return weights


def _verify_runtime() -> dict[str, Any]:
    if (
        sys.version_info[:2] not in _SUPPORTED_PYTHON_MINORS
        or platform.system() != "Darwin"
        or platform.machine() != "arm64"
    ):
        raise RuntimeError(
            "MelRoFormer bridge requires Python 3.12 or 3.13 on Apple silicon"
        )
    observed: dict[str, str] = {}
    for name, expected in _RUNTIME_VERSIONS.items():
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise RuntimeError(f"MelRoFormer runtime version differs: {name}")
        observed[name] = actual
    try:
        importlib.metadata.version("mlx-audio")
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        raise RuntimeError("MelRoFormer bridge forbids the mlx-audio distribution")
    return {
        "python": platform.python_version(),
        "platform": "macOS arm64",
        "packages": observed,
        "mlx_audio_distribution_installed": False,
    }


def _apply_offline_environment() -> None:
    for name, expected in _OFFLINE_ENVIRONMENT.items():
        current = os.environ.get(name)
        if current not in {None, expected}:
            raise RuntimeError(f"MelRoFormer offline environment differs: {name}")
        os.environ[name] = expected


def _require_clean_source_namespace() -> None:
    collisions = sorted(
        name
        for name in sys.modules
        if name == "mlx_audio" or name.startswith("mlx_audio.")
    )
    if collisions:
        raise RuntimeError("MelRoFormer bridge requires a fresh mlx_audio namespace")


def _install_namespace_packages(source: Path) -> None:
    for name, relative in _PACKAGE_PATHS.items():
        module = types.ModuleType(name)
        module.__package__ = name
        module.__path__ = [str(source / relative)]
        module.__file__ = None
        sys.modules[name] = module


def _execute_audited_module(
    name: str, *, source: Path, item: Mapping[str, Any]
) -> types.ModuleType:
    relative = item["path"]
    path = source / relative
    attached = path.lstat()
    if attached.st_nlink != 1:
        raise ValueError("MelRoFormer source module must be a single-link file")
    contents = _read_exact_regular_file(
        path,
        expected_sha256=item["sha256"],
        expected_bytes=item["bytes"],
    )
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = name.rpartition(".")[0]
    sys.modules[name] = module
    code = compile(contents, str(path), "exec", dont_inherit=True, optimize=0)
    exec(code, module.__dict__)
    return module


def _remove_source_namespace() -> None:
    for name in list(sys.modules):
        if name == "mlx_audio" or name.startswith("mlx_audio."):
            sys.modules.pop(name, None)


def _verify_fixed_config(config: Any, path: Path) -> None:
    attached = path.lstat()
    if attached.st_nlink != 1:
        raise ValueError("MelRoFormer config must be a single-link file")
    contents = _read_exact_regular_file(
        path,
        expected_sha256=(
            "3300eacac960ab46933ef6df6b838eb35de1f0321db9242c1b06e6d2a6a62b58"
        ),
        expected_bytes=833,
    )
    published = json.loads(contents)
    fields = (
        "dim",
        "depth",
        "heads",
        "dim_head",
        "num_bands",
        "num_stems",
        "ff_mult",
        "mlp_expansion_factor",
        "mask_estimator_depth",
        "n_fft",
        "hop_length",
        "win_length",
        "sample_rate",
        "chunk_size",
        "num_overlap",
        "checkpoint_family",
    )
    observed = {name: getattr(config, name) for name in fields}
    expected = {name: published[name] for name in fields}
    if observed != expected:
        raise ValueError("MelRoFormer fixed config differs from pinned companion")


@contextmanager
def _verified_checkpoint_stream(path: Path) -> Iterator[BinaryIO]:
    attached = path.lstat()
    if (
        stat.S_ISLNK(attached.st_mode)
        or not stat.S_ISREG(attached.st_mode)
        or attached.st_nlink != 1
        or attached.st_size != CONVERSION_CHECKPOINT_BYTES
    ):
        raise ValueError("MelRoFormer checkpoint descriptor identity differs")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if os.get_inheritable(descriptor) or _identity(opened) != _identity(attached):
            raise ValueError("MelRoFormer checkpoint changed before tensor load")
        digest = hashlib.sha256()
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        if digest.hexdigest() != CONVERSION_CHECKPOINT_SHA256:
            raise ValueError("MelRoFormer checkpoint changed before tensor load")
        os.lseek(descriptor, 0, os.SEEK_SET)
        duplicate = os.dup(descriptor)
        os.set_inheritable(duplicate, False)
        with os.fdopen(duplicate, "rb") as stream:
            yield stream
        if _identity(os.fstat(descriptor)) != _identity(opened) or _identity(
            path.lstat()
        ) != _identity(opened):
            raise ValueError("MelRoFormer checkpoint changed during tensor load")
    finally:
        os.close(descriptor)


@contextmanager
def _verified_checkpoint_descriptor_stream(descriptor: int) -> Iterator[BinaryIO]:
    """Yield the exact inherited fd5 bytes without resolving a pathname."""

    if isinstance(descriptor, bool) or not isinstance(descriptor, int) or descriptor < 0:
        raise ValueError("MelRoFormer checkpoint descriptor is invalid")
    try:
        attached = os.fstat(descriptor)
        inheritable = os.get_inheritable(descriptor)
        access_mode = fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE
    except OSError as error:
        raise ValueError("MelRoFormer checkpoint descriptor is unavailable") from error
    if (
        inheritable
        or access_mode != os.O_RDONLY
        or not stat.S_ISREG(attached.st_mode)
        or attached.st_nlink != 1
        or attached.st_size != CONVERSION_CHECKPOINT_BYTES
    ):
        raise ValueError("MelRoFormer checkpoint descriptor identity differs")
    digest = hashlib.sha256()
    count = 0
    while count < CONVERSION_CHECKPOINT_BYTES:
        block = os.pread(
            descriptor,
            min(1024 * 1024, CONVERSION_CHECKPOINT_BYTES - count),
            count,
        )
        if not block:
            raise ValueError("MelRoFormer checkpoint descriptor is truncated")
        count += len(block)
        digest.update(block)
    if digest.hexdigest() != CONVERSION_CHECKPOINT_SHA256:
        raise ValueError("MelRoFormer checkpoint changed before tensor load")

    duplicate = os.dup(descriptor)
    try:
        os.set_inheritable(duplicate, False)
        os.lseek(duplicate, 0, os.SEEK_SET)
        with os.fdopen(duplicate, "rb", closefd=False) as stream:
            yield stream
        if (
            os.get_inheritable(descriptor)
            or _identity(os.fstat(descriptor)) != _identity(attached)
        ):
            raise ValueError("MelRoFormer checkpoint changed during tensor load")
    finally:
        os.close(duplicate)


def _validate_weight_inventory(
    *, raw: Mapping[str, Any], sanitized: Mapping[str, Any], expected: Mapping[str, Any]
) -> dict[str, Any]:
    raw_keys = _checked_keys(raw, "raw checkpoint")
    sanitized_keys = _checked_keys(sanitized, "sanitized")
    expected_keys = _checked_keys(expected, "model parameter")
    transformed, dropped = _transform_checkpoint_keys(raw_keys)
    if transformed != sanitized_keys:
        raise ValueError("MelRoFormer sanitizer mapping differs from audited mapping")
    missing = sorted(set(expected_keys) - set(sanitized_keys))
    unexpected = sorted(set(sanitized_keys) - set(expected_keys))
    if missing or unexpected:
        raise ValueError("MelRoFormer post-sanitisation model-key coverage differs")
    shape_mismatches = sorted(
        key
        for key in expected_keys
        if tuple(expected[key].shape) != tuple(sanitized[key].shape)
    )
    if shape_mismatches:
        raise ValueError("MelRoFormer post-sanitisation tensor shapes differ")
    dtypes = sorted({str(value.dtype) for value in raw.values()})
    if dtypes != ["mlx.core.bfloat16"]:
        raise ValueError("MelRoFormer checkpoint runtime dtype differs")
    return {
        "raw_checkpoint_key_count": len(raw_keys),
        "raw_checkpoint_keys_sha256": _sequence_sha256(raw_keys),
        "sanitized_key_count": len(sanitized_keys),
        "sanitized_keys_sha256": _sequence_sha256(sanitized_keys),
        "expected_model_key_count": len(expected_keys),
        "expected_model_keys_sha256": _sequence_sha256(expected_keys),
        "dropped_raw_weight_key_count": len(dropped),
        "dropped_raw_weight_keys": list(dropped),
        "dropped_raw_weight_keys_sha256": _sequence_sha256(dropped),
        "permitted_dropped_suffix": _PERMITTED_DROPPED_SUFFIX,
        "missing_model_keys": [],
        "unexpected_sanitized_keys": [],
        "shape_mismatches": [],
        "checkpoint_dtypes": dtypes,
        "complete": True,
    }


def _checked_keys(value: Mapping[str, Any], label: str) -> tuple[str, ...]:
    if not isinstance(value, Mapping) or not 1 <= len(value) <= 100_000:
        raise ValueError(f"MelRoFormer {label} key set is invalid")
    keys = tuple(sorted(value))
    if any(
        not isinstance(key, str) or not key or len(key.encode()) > 1024 for key in keys
    ):
        raise ValueError(f"MelRoFormer {label} key is invalid")
    return keys


def _transform_checkpoint_keys(
    raw_keys: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    transformed: list[str] = []
    dropped: list[str] = []
    for original in sorted(raw_keys):
        if original.endswith(_PERMITTED_DROPPED_SUFFIX):
            dropped.append(original)
            continue
        if "to_qkv.weight" in original:
            prefix = original.replace("to_qkv.weight", "")
            transformed.extend(
                f"{prefix}{suffix}.weight" for suffix in ("to_q", "to_k", "to_v")
            )
            continue
        key = original
        match = _MASK_MLP_RE.match(key)
        if match:
            prefix, sequence_index, kind = match.groups()
            key = f"{prefix}.{int(sequence_index) // 2}.0.{kind}"
        if key.endswith("to_out.0.weight"):
            key = key[: -len(".0.weight")] + ".weight"
        if key.endswith(".gamma"):
            key = key[: -len(".gamma")] + ".weight"
        transformed.append(key)
    if len(transformed) != len(set(transformed)):
        raise ValueError("MelRoFormer sanitizer mapping contains a key collision")
    return tuple(sorted(transformed)), tuple(sorted(dropped))


def _sequence_sha256(values: Sequence[str]) -> str:
    payload = json.dumps(
        list(values), ensure_ascii=False, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
    )


__all__ = [
    "MAXIMUM_EXCERPT_FRAMES",
    "MAXIMUM_PROBE_FRAMES",
    "MINIMUM_PROBE_FRAMES",
    "NOMINAL_CHUNK_FRAMES",
    "NOMINAL_HOP_FRAMES",
    "SCHEMA",
    "_PrivateMelRoFormerHandle",
    "_load_private_authorised_excerpt",
    "_load_private_authorised_excerpt_pcm24",
    "_load_private_melroformer_model",
    "_infer_private_melroformer_probe",
    "_infer_private_melroformer_excerpt",
    "_plan_excerpt_chunks",
    "_transform_checkpoint_keys",
    "_validate_weight_inventory",
]
