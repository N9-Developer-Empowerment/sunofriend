"""Private PyTorch-to-MLX output parity for the exact Kim Vocal 2 model.

This separates two different comparisons which a single SDR can hide:

* original FP32 PyTorch checkpoint versus the published BF16 MLX checkpoint;
* the same PyTorch checkpoint rounded to BF16 versus the BF16 MLX runtime.

Only the second comparison isolates implementation parity.  The first also
contains the effect of publishing the converted weights at lower precision.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import time
from pathlib import Path
from typing import Any, Mapping

from ._separation_melroformer_conversion_parity import (
    _document_sha256,
    _open_verified_regular,
    _revalidate_open_file,
)
from ._separation_safetensors_inspection import _parse_unique_json
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_SHA256,
    SOURCE_CHECKPOINT_BYTES,
    SOURCE_CHECKPOINT_SHA256,
)


SCHEMA = "sunofriend.private-melroformer-inference-parity.v1"
POLICY_ID = "kim-vocal-2-bf16-runtime-output-parity-v1"
EVIDENCE_NAME = "private-separation-melroformer-inference-parity.json"
EVIDENCE_BYTES = 4_201
EVIDENCE_SHA256 = "a85939af317bdff203de02116b8d2e773bb9e1f392f49b601d3bb2ff1233b389"
PARITY_THRESHOLD_DB = 40.0
PARITY_FRAMES = 352_800
SAMPLE_RATE = 44_100
PYTORCH_REFERENCE = "bs_roformer.MelBandRoformer==0.3.10"
RUNTIME_VERSIONS = {
    "BS-RoFormer": "0.3.10",
    "beartype": "0.22.9",
    "einops": "0.8.2",
    "librosa": "0.11.0",
    "numpy": "2.3.5",
    "packaging": "26.2",
    "rotary-embedding-torch": "0.9.1",
    "torch": "2.13.0",
}
PINNED_WHEELS = {
    "BS_RoFormer-0.3.10-py3-none-any.whl": (
        "9a08d7ec6112ed0a5ab29740046fbcfee023484f697f1c6b646fa6d0706c5b9d"
    ),
    "beartype-0.22.9-py3-none-any.whl": (
        "d16c9bbc61ea14637596c5f6fbff2ee99cbe3573e46a716401734ef50c3060c2"
    ),
    "rotary_embedding_torch-0.9.1-py3-none-any.whl": (
        "489ef53e21ab4c4eb35c0c97b551d724f5eea71c2bca39acb8fee8d88b142a76"
    ),
}


def _run_private_melroformer_inference_parity(
    *,
    mlx_source_root: str | Path,
    source_checkpoint: str | Path,
    converted_checkpoint: str | Path,
    companion_root: str | Path,
    authorisation_report: str | Path,
    authorisation_report_sha256: str,
) -> dict[str, Any]:
    """Run one exact eight-second CPU parity observation without audio output."""

    outputs = _run_private_melroformer_inference_outputs(
        mlx_source_root=mlx_source_root,
        source_checkpoint=source_checkpoint,
        converted_checkpoint=converted_checkpoint,
        companion_root=companion_root,
        authorisation_report=authorisation_report,
        authorisation_report_sha256=authorisation_report_sha256,
    )
    return _build_inference_parity_report(
        audio=outputs["audio"],
        original=outputs["original"],
        rounded=outputs["rounded"],
        converted=outputs["converted"],
        runtime_versions=outputs["runtime_versions"],
        authorisation=outputs["authorisation"],
        timings=outputs["timings"],
    )


def _run_private_melroformer_inference_outputs(
    *,
    mlx_source_root: str | Path,
    source_checkpoint: str | Path,
    converted_checkpoint: str | Path,
    companion_root: str | Path,
    authorisation_report: str | Path,
    authorisation_report_sha256: str,
) -> dict[str, Any]:
    """Return the three exact eight-second outputs for bounded private gates.

    The caller may compute numeric evidence or create an owner-only listening
    package.  This helper itself persists no audio and exposes no product route.
    """

    from ._separation_melroformer_real_bridge import (
        _load_private_authorised_excerpt,
        _load_private_melroformer_model,
        _run_model_chunk_array,
    )

    versions = _verify_runtime_versions()
    source_path = Path(source_checkpoint).expanduser()
    if not source_path.is_absolute():
        raise ValueError("source checkpoint path must be absolute")
    source_fd, source_identity = _open_verified_regular(
        source_path,
        expected_bytes=SOURCE_CHECKPOINT_BYTES,
        expected_sha256=SOURCE_CHECKPOINT_SHA256,
        label="source checkpoint",
    )
    try:
        torch, model, original_state = _load_torch_model(source_fd)
        mlx_handle = _load_private_melroformer_model(
            source_root=mlx_source_root,
            checkpoint_path=converted_checkpoint,
            companion_root=companion_root,
            device="cpu",
        )
        source, authorisation = _load_private_authorised_excerpt(
            mlx_handle,
            report_path=authorisation_report,
            expected_report_sha256=authorisation_report_sha256,
        )
        if len(source) < PARITY_FRAMES:
            raise ValueError("authorised excerpt is shorter than the parity window")
        audio = mlx_handle.np.ascontiguousarray(source[:PARITY_FRAMES])
        mlx_output, mlx_seconds, mlx_peak = _run_model_chunk_array(mlx_handle, audio)

        started = time.perf_counter()
        with torch.inference_mode():
            original_output = model(torch.from_numpy(audio.T[None]))
        original_seconds = time.perf_counter() - started
        original = original_output[0].detach().cpu().numpy().T.astype("float32")

        rounded_state = {
            key: (
                value.to(torch.bfloat16).to(torch.float32)
                if value.is_floating_point()
                else value
            )
            for key, value in original_state.items()
        }
        model.load_state_dict(rounded_state, strict=True)
        started = time.perf_counter()
        with torch.inference_mode():
            rounded_output = model(torch.from_numpy(audio.T[None]))
        rounded_seconds = time.perf_counter() - started
        rounded = rounded_output[0].detach().cpu().numpy().T.astype("float32")
        result = {
            "audio": audio,
            "original": original,
            "rounded": rounded,
            "converted": mlx_output,
            "runtime_versions": versions,
            "authorisation": {
                "track_id": authorisation["track_id"],
                "source_start_seconds": authorisation["source_start_seconds"],
                "source_window_seconds": PARITY_FRAMES / SAMPLE_RATE,
                "report_sha256": authorisation_report_sha256,
                "source_pcm24_sha256": authorisation["audio_sha256"],
            },
            "timings": {
                "pytorch_original_fp32_seconds": original_seconds,
                "pytorch_bf16_roundtrip_seconds": rounded_seconds,
                "mlx_bf16_seconds": mlx_seconds,
                "mlx_peak_memory_bytes": mlx_peak,
            },
        }
        _revalidate_open_file(
            source_fd,
            source_path,
            source_identity,
            expected_sha256=SOURCE_CHECKPOINT_SHA256,
            label="source checkpoint",
        )
        return result
    finally:
        os.close(source_fd)


def _verify_tracked_inference_parity_evidence(
    repository_root: str | Path,
) -> dict[str, Any]:
    """Verify and read the tracked path-free observation without model access."""

    root = Path(repository_root).expanduser()
    if not root.is_absolute():
        raise ValueError("repository root path must be absolute")
    descriptor, _ = _open_verified_regular(
        root / EVIDENCE_NAME,
        expected_bytes=EVIDENCE_BYTES,
        expected_sha256=EVIDENCE_SHA256,
        label="inference-parity evidence",
    )
    try:
        encoded = os.pread(descriptor, EVIDENCE_BYTES, 0)
    finally:
        os.close(descriptor)
    evidence = _parse_unique_json(encoded[:-1] if encoded.endswith(b"\n") else encoded)
    if (
        evidence.get("schema") != SCHEMA
        or evidence.get("policy_id") != POLICY_ID
        or evidence.get("status")
        != "verified_bf16_runtime_parity_source_precision_delta_recorded"
        or evidence.get("document_sha256") != _document_sha256(evidence)
    ):
        raise ValueError("inference-parity evidence semantics differ")
    claims = evidence.get("claims")
    if not isinstance(claims, dict) or claims != {
        "bf16_publication_precision_delta_measured": True,
        "converted_bf16_runtime_output_parity_above_threshold": True,
        "original_fp32_source_to_converted_mlx_output_above_threshold": False,
        "same_audio_as_upstream_published_parity_test": False,
        "separator_quality_measured": False,
        "upstream_reported_66_08_db_independently_reproduced": False,
        "winner_selected": False,
    }:
        raise ValueError("inference-parity evidence claims differ")
    return evidence


def _build_inference_parity_report(
    *,
    audio: Any,
    original: Any,
    rounded: Any,
    converted: Any,
    runtime_versions: Mapping[str, str],
    authorisation: Mapping[str, Any],
    timings: Mapping[str, float | int],
) -> dict[str, Any]:
    np = _numpy()
    arrays = {
        "input": _validated_audio(audio, np=np),
        "pytorch_original_fp32": _validated_audio(original, np=np),
        "pytorch_bf16_roundtrip": _validated_audio(rounded, np=np),
        "mlx_published_bf16": _validated_audio(converted, np=np),
    }
    shapes = {tuple(value.shape) for value in arrays.values()}
    if shapes != {(PARITY_FRAMES, 2)}:
        raise ValueError("inference parity audio geometry differs")
    original_to_mlx = _metrics(
        arrays["pytorch_original_fp32"], arrays["mlx_published_bf16"], np=np
    )
    rounded_to_mlx = _metrics(
        arrays["pytorch_bf16_roundtrip"], arrays["mlx_published_bf16"], np=np
    )
    original_to_rounded = _metrics(
        arrays["pytorch_original_fp32"], arrays["pytorch_bf16_roundtrip"], np=np
    )
    runtime_parity = rounded_to_mlx["sdr_db"] > PARITY_THRESHOLD_DB
    source_precision_parity = original_to_mlx["sdr_db"] > PARITY_THRESHOLD_DB
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": (
            "verified_bf16_runtime_parity_source_precision_delta_recorded"
            if runtime_parity
            else "bf16_runtime_parity_below_threshold"
        ),
        "policy_id": POLICY_ID,
        "threshold_sdr_db": PARITY_THRESHOLD_DB,
        "reference": {
            "implementation": PYTORCH_REFERENCE,
            "source_checkpoint_sha256": SOURCE_CHECKPOINT_SHA256,
            "converted_checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "runtime_versions": dict(runtime_versions),
            "pinned_wheel_sha256": dict(PINNED_WHEELS),
            "device": "cpu",
        },
        "authorisation": dict(authorisation),
        "geometry": {
            "sample_rate": SAMPLE_RATE,
            "channels": 2,
            "frames": PARITY_FRAMES,
            "seconds": PARITY_FRAMES / SAMPLE_RATE,
            "alignment": "same exact source frames; single model chunk; no overlap",
        },
        "outputs": {
            name: {
                "float32_sha256": _array_sha256(value, np=np),
                "root_mean_square": float(
                    np.sqrt(np.mean(value.astype(np.float64) ** 2))
                ),
            }
            for name, value in arrays.items()
        },
        "comparisons": {
            "pytorch_original_fp32_vs_mlx_published_bf16": original_to_mlx,
            "pytorch_bf16_roundtrip_vs_mlx_published_bf16": rounded_to_mlx,
            "pytorch_original_fp32_vs_pytorch_bf16_roundtrip": original_to_rounded,
        },
        "claims": {
            "converted_bf16_runtime_output_parity_above_threshold": runtime_parity,
            "original_fp32_source_to_converted_mlx_output_above_threshold": source_precision_parity,
            "bf16_publication_precision_delta_measured": True,
            "same_audio_as_upstream_published_parity_test": False,
            "upstream_reported_66_08_db_independently_reproduced": False,
            "separator_quality_measured": False,
            "winner_selected": False,
        },
        "timings": dict(timings),
        "permissions": {
            "automatic_promotion": False,
            "automatic_selection": False,
            "checkpoint_publication": False,
            "simple_mode": False,
            "source_graph": False,
            "studio_mode": False,
        },
        "effects": {
            "audio_read": True,
            "audio_written": False,
            "checkpoint_deserialized": True,
            "filesystem_written": False,
            "model_inference": True,
            "network_used": False,
            "product_route_changed": False,
        },
    }
    report["document_sha256"] = _document_sha256(report)
    return report


def _load_torch_model(source_fd: int) -> tuple[Any, Any, dict[str, Any]]:
    import torch
    from bs_roformer import MelBandRoformer

    model = MelBandRoformer(
        dim=384,
        depth=6,
        stereo=True,
        num_stems=1,
        time_transformer_depth=1,
        freq_transformer_depth=1,
        num_bands=60,
        dim_head=64,
        heads=8,
        attn_dropout=0.0,
        ff_dropout=0.0,
        flash_attn=True,
        dim_freqs_in=1025,
        sample_rate=SAMPLE_RATE,
        stft_n_fft=2048,
        stft_hop_length=441,
        stft_win_length=2048,
        stft_normalized=False,
        mask_estimator_depth=2,
        multi_stft_resolution_loss_weight=1.0,
        multi_stft_resolutions_window_sizes=(4096, 2048, 1024, 512, 256),
        multi_stft_hop_size=147,
        multi_stft_normalized=False,
    )
    with os.fdopen(os.dup(source_fd), "rb", closefd=True) as source_handle:
        state = torch.load(source_handle, map_location="cpu", weights_only=True)
    if not isinstance(state, dict) or len(state) != 684:
        raise ValueError("PyTorch source checkpoint state dictionary differs")
    model.load_state_dict(state, strict=True)
    model.eval()
    return torch, model, dict(state)


def _verify_runtime_versions() -> dict[str, str]:
    observed: dict[str, str] = {}
    for distribution, expected in RUNTIME_VERSIONS.items():
        actual = importlib.metadata.version(distribution)
        if actual != expected:
            raise RuntimeError(
                f"private PyTorch parity runtime differs: {distribution}=={actual}"
            )
        observed[distribution] = actual
    return observed


def _metrics(reference: Any, estimate: Any, *, np: Any) -> dict[str, float]:
    ref = reference.astype(np.float64)
    est = estimate.astype(np.float64)
    difference = ref - est
    epsilon = 1e-10
    return {
        "sdr_db": float(
            10.0
            * np.log10(
                (np.sum(ref * ref) + epsilon)
                / (np.sum(difference * difference) + epsilon)
            )
        ),
        "maximum_absolute_difference": float(np.max(np.abs(difference))),
        "root_mean_square_difference": float(np.sqrt(np.mean(difference**2))),
    }


def _validated_audio(value: Any, *, np: Any) -> Any:
    array = np.ascontiguousarray(value, dtype=np.dtype("<f4"))
    if array.ndim != 2 or array.shape[1] != 2 or not np.isfinite(array).all():
        raise ValueError("inference parity audio must be finite stereo float32")
    return array


def _array_sha256(value: Any, *, np: Any) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(value, dtype=np.dtype("<f4")).tobytes(order="C")
    ).hexdigest()


def _numpy() -> Any:
    try:
        import numpy as np
    except ImportError as error:  # pragma: no cover - private runtime preflight
        raise RuntimeError("NumPy is required for inference parity") from error
    return np


__all__ = [
    "EVIDENCE_BYTES",
    "EVIDENCE_NAME",
    "EVIDENCE_SHA256",
    "PARITY_FRAMES",
    "PARITY_THRESHOLD_DB",
    "PINNED_WHEELS",
    "POLICY_ID",
    "PYTORCH_REFERENCE",
    "RUNTIME_VERSIONS",
    "SCHEMA",
    "_build_inference_parity_report",
    "_run_private_melroformer_inference_outputs",
    "_run_private_melroformer_inference_parity",
    "_verify_tracked_inference_parity_evidence",
    "_verify_runtime_versions",
]
