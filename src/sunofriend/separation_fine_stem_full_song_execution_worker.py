"""One-profile worker for the approval-bound full-song six-role canary.

The coordinator starts this module three times under macOS network denial.
Each process loads exactly one verified model, runs exactly three planned songs,
and persists only temporary float32 arrays for the coordinator's sole PCM24
writer.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import random
import resource
import time
from typing import Any, Mapping, Sequence

import numpy as np

from .separation_demucs_mlx_worker import read_canonical_source
from .separation_fine_stem_canary_audio import file_sha256
from .separation_fine_stem_canary_contract import (
    MAXIMUM_PEAK_MLX_MEMORY_BYTES,
    PROFILE_CONTRACTS,
)
from .separation_fine_stem_full_song_execution_contract import (
    PROFILE_MODES,
    WORKER_REQUEST_SCHEMA,
    WORKER_RESULT_SCHEMA,
    mega53_chunk_starts,
    scnet_forward_calls,
    sw_forward_calls,
)
from .separation_fine_stem_integration_worker import (
    _ForwardGuardedModel,
    _yaml_document,
)


MAXIMUM_ELAPSED_SECONDS_PER_SONG = 900.0


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("full-song worker JSON must be an object")
    return value


def _read_request(path: Path, mode: str) -> dict[str, Any]:
    value = _json(path)
    cases = value.get("cases")
    if (
        value.get("schema") != WORKER_REQUEST_SCHEMA
        or value.get("mode") != mode
        or value.get("network_denied") is not True
        or not isinstance(cases, list)
        or len(cases) != 3
        or len({case.get("track_id") for case in cases}) != 3
    ):
        raise ValueError("full-song worker request differs")
    expected_calls = sum(
        (
            scnet_forward_calls(int(case["source"]["frames"]))
            if mode == "scnet"
            else len(mega53_chunk_starts(int(case["source"]["frames"])))
            if mode == "mega53-synth"
            else sw_forward_calls(int(case["source"]["frames"]))
        )
        for case in cases
    )
    if value.get("expected_forward_calls") != expected_calls:
        raise ValueError("full-song worker forward budget differs")
    return value


def _source_path(case: Mapping[str, Any]) -> Path:
    artifact = case["source"]
    path = Path(artifact["path"]).resolve(strict=True)
    if (
        path.stat().st_size != artifact["bytes"]
        or file_sha256(path) != artifact["sha256"]
    ):
        raise RuntimeError("full-song worker source identity differs")
    return path


def _source(case: Mapping[str, Any]) -> np.ndarray:
    value = read_canonical_source(_source_path(case), np=np).astype(np.float32)
    expected = (int(case["source"]["frames"]), 2)
    if value.shape != expected or not np.isfinite(value).all():
        raise RuntimeError("full-song worker source clock differs")
    return value


def _write_estimate(path_value: str, value: Any, *, frames: int) -> dict[str, Any]:
    path = Path(path_value).resolve()
    array = np.ascontiguousarray(value, dtype=np.float32)
    if array.shape != (frames, 2) or not np.isfinite(array).all():
        raise RuntimeError("full-song temporary estimate differs")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        raise FileExistsError("full-song temporary estimate already exists")
    with path.open("xb") as handle:
        np.save(handle, array, allow_pickle=False)
    path.chmod(0o600)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "shape": list(array.shape),
        "dtype": "float32",
        "finite": True,
        "rms": float(np.sqrt(np.mean(np.square(array.astype(np.float64))))),
        "peak": float(np.max(np.abs(array), initial=0.0)),
    }


def _run_scnet(
    request: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if platform.python_version_tuple()[:2] != ("3", "13"):
        raise RuntimeError("full-song SCNet worker requires Python 3.13")
    import torch
    import yaml

    from .separation_demucs_mlx_worker import (
        CHANNELS,
        MODEL_SOURCE_ORDER,
    )
    from .separation_profiles import SCNET_RELEASE_PROFILE_ID, separation_profile
    from .separation_scnet_worker import _apply_one_shift, _load_model

    spec = separation_profile(SCNET_RELEASE_PROFILE_ID)
    packages = {name: importlib.metadata.version(name) for name in spec.packages()}
    if packages != dict(spec.packages()):
        raise RuntimeError("full-song SCNet runtime identity differs")
    torch.set_grad_enabled(False)
    torch.manual_seed(0)
    random.seed(0)
    model_root = Path(request["model_root"]).resolve(strict=True)
    loaded_at = time.monotonic()
    model, model_receipt = _load_model(model_root, torch=torch, yaml=yaml)
    load_seconds = time.monotonic() - loaded_at
    if (
        tuple(model.sources) != tuple(MODEL_SOURCE_ORDER)
        or model.audio_channels != CHANNELS
    ):
        raise RuntimeError("full-song SCNet role contract differs")
    cases: list[dict[str, Any]] = []
    total_forward_passes = 0
    for case in request["cases"]:
        case_started = time.monotonic()
        source = _source(case)
        frames = len(source)
        source_tensor = torch.from_numpy(np.ascontiguousarray(source.T)).unsqueeze(0)
        mono = source_tensor.mean(dim=1)
        mean = mono.mean()
        standard_deviation = mono.std()
        if (
            not math.isfinite(float(standard_deviation))
            or float(standard_deviation) <= 0
        ):
            raise ValueError("full-song SCNet source has no separable variance")
        normalized = (source_tensor - mean) / standard_deviation
        with torch.inference_mode():
            separated, shift_offset, forward_passes = _apply_one_shift(
                model, normalized, torch=torch
            )
        if tuple(separated.shape) != (1, len(MODEL_SOURCE_ORDER), 2, frames):
            raise RuntimeError("full-song SCNet output geometry differs")
        separated = separated * standard_deviation + mean
        raw = separated[0].detach().cpu().numpy()
        outputs = {
            role: _write_estimate(case["outputs"][role], raw[index].T, frames=frames)
            for index, role in enumerate(MODEL_SOURCE_ORDER)
        }
        elapsed = time.monotonic() - case_started
        if elapsed > MAXIMUM_ELAPSED_SECONDS_PER_SONG:
            raise TimeoutError("full-song SCNet case exceeded 900 seconds")
        total_forward_passes += forward_passes
        cases.append(
            {
                "track_id": case["track_id"],
                "elapsed_seconds": elapsed,
                "shift_offset_frames": shift_offset,
                "forward_calls": forward_passes,
                "outputs": outputs,
            }
        )
        del source, source_tensor, normalized, separated, raw
    if total_forward_passes != request["expected_forward_calls"]:
        raise RuntimeError("full-song SCNet forward accounting differs")
    for relative_path, identity in model_receipt["artifacts"].items():
        if file_sha256(model_root / relative_path) != identity["sha256"]:
            raise RuntimeError("full-song SCNet model artifact changed")
    return cases, {
        "profile_id": SCNET_RELEASE_PROFILE_ID,
        "model_loads": 1,
        "model_receipt": model_receipt,
        "model_load_seconds": load_seconds,
        "forward_calls": total_forward_passes,
        "peak_unified_memory_bytes": int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        ),
        "packages": packages,
    }


def _fade_window(size: int) -> np.ndarray:
    fade = size // 10
    value = np.ones(size, dtype=np.float32)
    value[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
    value[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return value


def _mega53_target(model: Any, guard: Any, source: np.ndarray) -> np.ndarray:
    import mlx.core as mx

    from .separation_other_refinement_next_synthetic_plan import (
        ALIGNED_CHUNK_SIZE,
        SYNTH_ROLE_INDEX,
    )

    starts = mega53_chunk_starts(len(source))
    result = np.zeros((2, len(source)), dtype=np.float32)
    counter = np.zeros(len(source), dtype=np.float32)
    template = _fade_window(ALIGNED_CHUNK_SIZE)
    for start in starts:
        stop = min(start + ALIGNED_CHUNK_SIZE, len(source))
        length = stop - start
        mixture = np.zeros((1, 2, ALIGNED_CHUNK_SIZE), dtype=np.float32)
        mixture[0, :, :length] = source[start:stop].T
        guard.record_forward()
        output = model(mx.array(mixture))
        mx.eval(output)
        if list(output.shape) != [1, 53, 2, ALIGNED_CHUNK_SIZE]:
            raise RuntimeError("full-song Mega-53 output shape differs")
        if not bool(mx.all(mx.isfinite(output)).item()):
            raise RuntimeError("full-song Mega-53 output is non-finite")
        target = np.array(output[0, SYNTH_ROLE_INDEX, :, :length], dtype=np.float32)
        window = template[:length].copy()
        if start == 0:
            window[: min(ALIGNED_CHUNK_SIZE // 10, length)] = 1
        if stop == len(source):
            window[max(0, length - ALIGNED_CHUNK_SIZE // 10) :] = 1
        result[:, start:stop] += target * window
        counter[start:stop] += window
        del output, target, mixture
        mx.clear_cache()
    if np.any(counter <= 0):
        raise RuntimeError("full-song Mega-53 overlap accounting differs")
    target = (result / counter).T
    if target.shape != source.shape or not np.isfinite(target).all():
        raise RuntimeError("full-song Mega-53 target geometry differs")
    return target


def _run_specialist(
    request: Mapping[str, Any], *, mode: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if platform.python_version_tuple()[:2] != ("3", "12"):
        raise RuntimeError("full-song BS-RoFormer worker requires Python 3.12")
    import mlx.core as mx

    from .separation_fine_stem_canary_guard import FineStemCanaryExecutionGuard
    from .separation_other_refinement_next_source_evidence import (
        validate_source_evidence,
        verify_extracted_source_tree,
    )

    profile_id = (
        "bs-roformer-mega-53-synth-v1"
        if mode == "mega53-synth"
        else "bs-roformer-sw-guitar-v1"
    )
    profile = PROFILE_CONTRACTS[profile_id]
    checkpoint = Path(request["checkpoint"]).resolve(strict=True)
    config = Path(request["config"]).resolve(strict=True)
    for path, expected in (
        (checkpoint, profile["checkpoint"]),
        (config, profile["config"]),
    ):
        if (
            path.name != expected["file"]
            or path.stat().st_size != expected["bytes"]
            or file_sha256(path) != expected["sha256"]
        ):
            raise RuntimeError("full-song specialist artifact identity differs")
    source_root = Path(request["source_root"]).resolve(strict=True)
    source_evidence = validate_source_evidence(_json(Path(request["source_evidence"])))
    verify_extracted_source_tree(source_evidence, source_root)
    sources = [_source_path(case) for case in request["cases"]]
    guard = FineStemCanaryExecutionGuard(
        checkpoint,
        audio_inputs=sources,
        audio_outputs=(),
        expected_forward_calls=int(request["expected_forward_calls"]),
    )
    guard.install()
    document = _yaml_document(config)
    mx.reset_peak_memory()
    loaded_at = time.monotonic()
    if mode == "mega53-synth":
        from .separation_other_refinement_next_model_load_contract import (
            validate_model_load_report,
        )
        from .separation_other_refinement_next_model_loading import load_mega53_model

        validate_model_load_report(_json(Path(request["model_load_report"])))
        loaded = load_mega53_model(
            checkpoint=checkpoint,
            config_document=document,
            source_root=source_root,
        )
        backend = None
    else:
        from bs_roformer.backends.mlx_backend import MLXBackend
        from .separation_bs_roformer_sw_loading import load_sw_model

        loaded = load_sw_model(
            checkpoint=checkpoint,
            config_document=document,
            source_root=source_root,
        )
        backend = MLXBackend(_ForwardGuardedModel(loaded.model, guard), loaded.config)
    load_seconds = time.monotonic() - loaded_at
    cases = []
    for case in request["cases"]:
        case_started = time.monotonic()
        source = _source(case)
        if mode == "mega53-synth":
            target = _mega53_target(loaded.model, guard, source)
        else:
            separated = backend.separate(source.T)
            if set(separated) != set(profile["native_roles"]):
                raise RuntimeError("full-song BS-RoFormer-SW roles differ")
            target = separated["guitar"].T
        elapsed = time.monotonic() - case_started
        if elapsed > MAXIMUM_ELAPSED_SECONDS_PER_SONG:
            raise TimeoutError("full-song specialist case exceeded 900 seconds")
        cases.append(
            {
                "track_id": case["track_id"],
                "elapsed_seconds": elapsed,
                "forward_calls": (
                    len(mega53_chunk_starts(len(source)))
                    if mode == "mega53-synth"
                    else sw_forward_calls(len(source))
                ),
                "outputs": {
                    profile["target_role"]: _write_estimate(
                        case["output"], target, frames=len(source)
                    )
                },
            }
        )
        del source, target
        mx.clear_cache()
    guard.assert_complete()
    verify_extracted_source_tree(source_evidence, source_root)
    for path, expected in (
        (checkpoint, profile["checkpoint"]),
        (config, profile["config"]),
    ):
        if file_sha256(path) != expected["sha256"]:
            raise RuntimeError("full-song specialist artifact changed")
    peak_mlx = int(mx.get_peak_memory())
    peak_resident = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    peak = max(peak_mlx, peak_resident)
    if peak > MAXIMUM_PEAK_MLX_MEMORY_BYTES:
        raise MemoryError("full-song specialist exceeded its memory ceiling")
    return cases, {
        "profile_id": profile_id,
        "model_loads": 1,
        "model_load_seconds": load_seconds,
        "model": loaded.evidence,
        "guard": guard.report(),
        "forward_calls": guard.forward_calls,
        "peak_mlx_memory_bytes": peak_mlx,
        "peak_resident_set_bytes": peak_resident,
        "peak_unified_memory_bytes": peak,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if platform.system() != "Darwin" or platform.machine().casefold() != "arm64":
        raise RuntimeError("full-song six-role worker requires Apple-silicon macOS")
    if not args.network_denial_enforced:
        raise RuntimeError("full-song six-role worker requires network denial")
    request = _read_request(args.request, args.mode)
    result_path = args.result.resolve()
    if result_path.exists():
        raise FileExistsError("full-song worker result already exists")
    started = time.monotonic()
    if args.mode == "scnet":
        cases, model = _run_scnet(request)
    else:
        cases, model = _run_specialist(request, mode=args.mode)
    document = {
        "schema": WORKER_RESULT_SCHEMA,
        "status": "complete_unpublished_private_temporary_estimates",
        "mode": args.mode,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "network_denied": True,
        },
        "model": model,
        "cases": cases,
        "elapsed_seconds": time.monotonic() - started,
        "effects": {
            "model_loads": 1,
            "profile_inference_attempts": 3,
            "network_attempts": 0,
            "automatic_retry": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
        },
    }
    result_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    result_path.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    result_path.chmod(0o600)
    return document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=PROFILE_MODES, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--network-denial-enforced", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run(args)
    except Exception as error:
        import sys

        print(
            f"full-song six-role worker failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
