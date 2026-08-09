"""Profile-local batch worker for the bounded private six-role canary.

The coordinator invokes this module three times, sequentially, under macOS
network denial.  Each invocation loads exactly one model and writes temporary
float32 estimates for the coordinator's single PCM24 writer.
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

from .separation_fine_stem_canary_audio import (
    file_sha256,
    read_canonical_pcm24,
)
from .separation_fine_stem_canary_contract import (
    MAXIMUM_ELAPSED_SECONDS,
    MAXIMUM_PEAK_MLX_MEMORY_BYTES,
    PROFILE_CONTRACTS,
    WINDOW_FRAMES,
)


WORKER_SCHEMA = "sunofriend.fine-stem-six-role-integration-worker.v1"
MODES = ("scnet", "mega53-synth", "sw-guitar")


def _read_request(path: Path, mode: str) -> dict[str, Any]:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    expected_cases = 8 if mode == "scnet" else 4
    if (
        value.get("schema") != "sunofriend.fine-stem-six-role-worker-request.v1"
        or value.get("mode") != mode
        or value.get("network_denied") is not True
        or len(value.get("cases", [])) != expected_cases
        or len({case.get("case_id") for case in value["cases"]}) != expected_cases
    ):
        raise ValueError("fine-stem integration worker request differs")
    return value


def _source_path(case: Mapping[str, Any]) -> Path:
    artifact = case["source"]
    path = Path(artifact["path"]).resolve(strict=True)
    if (
        path.stat().st_size != artifact["bytes"]
        or file_sha256(path) != artifact["sha256"]
    ):
        raise RuntimeError("fine-stem integration source identity differs")
    return path


def _source(case: Mapping[str, Any]) -> np.ndarray:
    return read_canonical_pcm24(_source_path(case))


def _write_estimate(path_value: str, value: Any) -> dict[str, Any]:
    path = Path(path_value).resolve()
    array = np.ascontiguousarray(value, dtype=np.float32)
    if array.shape != (WINDOW_FRAMES, 2) or not np.isfinite(array).all():
        raise RuntimeError("fine-stem integration temporary estimate differs")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        raise FileExistsError("fine-stem integration temporary estimate exists")
    with path.open("xb") as handle:
        np.save(handle, array, allow_pickle=False)
    path.chmod(0o600)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "finite": True,
        "rms": float(np.sqrt(np.mean(np.square(array.astype(np.float64))))),
        "peak": float(np.max(np.abs(array), initial=0.0)),
    }


def _yaml_document(path: Path) -> dict[str, Any]:
    import yaml

    class ConfigLoader(yaml.SafeLoader):
        pass

    ConfigLoader.add_constructor(
        "tag:yaml.org,2002:python/tuple",
        lambda loader, node: tuple(loader.construct_sequence(node)),
    )
    document = yaml.load(path.read_text(encoding="utf-8"), Loader=ConfigLoader)
    if not isinstance(document, dict):
        raise RuntimeError("fine-stem configuration differs")
    return document


def _run_scnet(request: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if sys_version()[:2] != (3, 13):
        raise RuntimeError("SCNet integration worker requires Python 3.13")
    import torch
    import yaml

    from .separation_demucs_mlx_worker import (
        CHANNELS,
        MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES,
        MODEL_SOURCE_ORDER,
        read_canonical_source,
    )
    from .separation_profiles import SCNET_RELEASE_PROFILE_ID, separation_profile
    from .separation_scnet_worker import _apply_one_shift, _load_model

    spec = separation_profile(SCNET_RELEASE_PROFILE_ID)
    packages = {name: importlib.metadata.version(name) for name in spec.packages()}
    if packages != dict(spec.packages()):
        raise RuntimeError("SCNet integration runtime identity differs")
    model_root = Path(request["model_root"]).resolve(strict=True)
    torch.set_grad_enabled(False)
    torch.manual_seed(0)
    random.seed(0)
    loaded_at = time.monotonic()
    model, model_receipt = _load_model(model_root, torch=torch, yaml=yaml)
    load_seconds = time.monotonic() - loaded_at
    if tuple(model.sources) != tuple(MODEL_SOURCE_ORDER) or model.audio_channels != CHANNELS:
        raise RuntimeError("SCNet integration role contract differs")
    cases = []
    total_forward_passes = 0
    for case in request["cases"]:
        source = read_canonical_source(_source_path(case), np=np).astype(np.float32)
        if source.shape != (WINDOW_FRAMES, CHANNELS):
            raise RuntimeError("SCNet integration source clock differs")
        source_tensor = torch.from_numpy(np.ascontiguousarray(source.T)).unsqueeze(0)
        mono = source_tensor.mean(dim=1)
        mean = mono.mean()
        standard_deviation = mono.std()
        if not math.isfinite(float(standard_deviation)) or float(standard_deviation) <= 0:
            raise ValueError("SCNet integration source has no separable variance")
        normalized = (source_tensor - mean) / standard_deviation
        with torch.inference_mode():
            separated, shift_offset, forward_passes = _apply_one_shift(
                model, normalized, torch=torch
            )
        expected = (1, len(MODEL_SOURCE_ORDER), CHANNELS, WINDOW_FRAMES)
        if tuple(separated.shape) != expected:
            raise RuntimeError("SCNet integration output geometry differs")
        separated = separated * standard_deviation + mean
        raw = separated[0].detach().cpu().numpy()
        outputs = {
            role: _write_estimate(case["outputs"][role], raw[index].T)
            for index, role in enumerate(MODEL_SOURCE_ORDER)
        }
        total_forward_passes += forward_passes
        cases.append(
            {
                "case_id": case["case_id"],
                "shift_offset_frames": shift_offset,
                "forward_passes": forward_passes,
                "outputs": outputs,
            }
        )
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if peak > MAXIMUM_PEAK_UNIFIED_MEMORY_BYTES:
        raise MemoryError("SCNet integration exceeded its 12 GiB ceiling")
    return cases, {
        "profile_id": SCNET_RELEASE_PROFILE_ID,
        "model_loads": 1,
        "model_receipt": model_receipt,
        "model_load_seconds": load_seconds,
        "forward_passes": total_forward_passes,
        "peak_unified_memory_bytes": peak,
        "packages": packages,
    }


class _ForwardGuardedModel:
    def __init__(self, model: Any, guard: Any) -> None:
        self._model = model
        self._guard = guard

    def __call__(self, value: Any) -> Any:
        self._guard.record_forward()
        return self._model(value)


def _run_specialist(
    request: Mapping[str, Any], *, mode: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if sys_version()[:2] != (3, 12):
        raise RuntimeError("BS-RoFormer integration worker requires Python 3.12")
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
    for path, expected in ((checkpoint, profile["checkpoint"]), (config, profile["config"])):
        if (
            path.name != expected["file"]
            or path.stat().st_size != expected["bytes"]
            or file_sha256(path) != expected["sha256"]
        ):
            raise RuntimeError("BS-RoFormer integration artifact identity differs")
    source_root = Path(request["source_root"]).resolve(strict=True)
    source_evidence = validate_source_evidence(
        json.loads(Path(request["source_evidence"]).resolve(strict=True).read_text())
    )
    verify_extracted_source_tree(source_evidence, source_root)
    sources = [Path(case["source"]["path"]).resolve(strict=True) for case in request["cases"]]
    expected_forwards = 4 if mode == "mega53-synth" else 20
    guard = FineStemCanaryExecutionGuard(
        checkpoint,
        audio_inputs=sources,
        audio_outputs=(),
        expected_forward_calls=expected_forwards,
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

        validate_model_load_report(
            json.loads(Path(request["model_load_report"]).resolve(strict=True).read_text())
        )
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
        source = _source(case)
        if mode == "mega53-synth":
            target = _mega53_target(loaded.model, guard, source)
        else:
            separated = backend.separate(source.astype(np.float32).T)
            if set(separated) != set(profile["native_roles"]):
                raise RuntimeError("BS-RoFormer-SW integration native roles differ")
            target = separated["guitar"].T
        cases.append(
            {
                "case_id": case["case_id"],
                "outputs": {profile["target_role"]: _write_estimate(case["output"], target)},
            }
        )
    peak = int(mx.get_peak_memory())
    if peak > MAXIMUM_PEAK_MLX_MEMORY_BYTES:
        raise MemoryError("BS-RoFormer integration exceeded its memory ceiling")
    guard.assert_complete()
    return cases, {
        "profile_id": profile_id,
        "model_loads": 1,
        "model_load_seconds": load_seconds,
        "model": loaded.evidence,
        "guard": guard.report(),
        "peak_mlx_memory_bytes": peak,
    }


def _mega53_target(model: Any, guard: Any, source: np.ndarray) -> np.ndarray:
    import mlx.core as mx

    from .separation_other_refinement_next_synthetic_plan import (
        ALIGNED_CHUNK_SIZE,
        SYNTH_ROLE_INDEX,
    )

    mixture = np.zeros((1, 2, ALIGNED_CHUNK_SIZE), dtype=np.float32)
    mixture[0, :, :WINDOW_FRAMES] = source.astype(np.float32).T
    guard.record_forward()
    output = model(mx.array(mixture))
    mx.eval(output)
    if list(output.shape) != [1, 53, 2, ALIGNED_CHUNK_SIZE]:
        raise RuntimeError("Mega-53 integration output shape differs")
    if not bool(mx.all(mx.isfinite(output)).item()):
        raise RuntimeError("Mega-53 integration output is non-finite")
    target = np.array(output[0, SYNTH_ROLE_INDEX, :, :WINDOW_FRAMES], dtype=np.float32)
    del output
    mx.clear_cache()
    return target.T


def sys_version() -> tuple[int, int, int]:
    import sys

    return sys.version_info[:3]


def run(args: argparse.Namespace) -> dict[str, Any]:
    if platform.system() != "Darwin" or platform.machine().casefold() != "arm64":
        raise RuntimeError("fine-stem integration requires Apple-silicon macOS")
    if not args.network_denial_enforced:
        raise RuntimeError("fine-stem integration requires coordinator network denial")
    request = _read_request(args.request, args.mode)
    result_path = args.result.resolve()
    if result_path.exists():
        raise FileExistsError("fine-stem integration worker result exists")
    started = time.monotonic()
    if args.mode == "scnet":
        cases, model = _run_scnet(request)
    else:
        cases, model = _run_specialist(request, mode=args.mode)
    elapsed = time.monotonic() - started
    if elapsed > MAXIMUM_ELAPSED_SECONDS:
        raise TimeoutError("fine-stem integration worker exceeded its time ceiling")
    document = {
        "schema": WORKER_SCHEMA,
        "status": "complete_unpublished_private_temporary_estimates",
        "mode": args.mode,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "network_denied": True,
        },
        "model": model,
        "cases": cases,
        "elapsed_seconds": elapsed,
        "effects": {
            "model_loads": 1,
            "inference_attempts": len(cases),
            "network_attempts": 0,
            "automatic_retry": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
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
    parser.add_argument("--mode", choices=MODES, required=True)
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
            f"fine-stem integration worker failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
