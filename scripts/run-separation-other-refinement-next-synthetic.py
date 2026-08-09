#!/usr/bin/env python3
"""Run the one approved Mega-53 generated-tensor objective attempt."""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_other_refinement_next_synthetic_plan import (
    ALIGNED_CHUNK_SIZE,
    MAXIMUM_ELAPSED_SECONDS,
    MODEL_LOAD_REPORT_SHA256,
    NATIVE_ROLES,
    SAMPLE_RATE_HZ,
    SYNTH_ROLE_INDEX,
    build_next_synthetic_plan,
    validate_next_synthetic_plan,
)
from sunofriend.separation_other_refinement_next_synthetic_report import (
    REPORT_SCHEMA,
    report_sha256,
    validate_synthetic_report,
)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify(path: Path, expected: dict[str, object]) -> None:
    if (
        path.name != expected["file"]
        or path.stat().st_size != expected["bytes"]
        or _sha(path) != expected["sha256"]
    ):
        raise RuntimeError(f"artifact identity differs: {path.name}")


def _generated(np: object) -> object:
    rng = np.random.default_rng(0)
    phases = rng.random(6, dtype=np.float32) * np.float32(2 * math.pi)
    t = np.arange(ALIGNED_CHUNK_SIZE, dtype=np.float32) / np.float32(SAMPLE_RATE_HZ)
    return np.stack(
        (
            0.12 * np.sin(2 * math.pi * 220 * t + phases[0])
            + 0.04 * np.sin(2 * math.pi * 1760 * t + phases[1])
            + 0.02 * np.sin(2 * math.pi * 523.25 * t + phases[2]),
            0.11 * np.sin(2 * math.pi * 330 * t + phases[3])
            + 0.05 * np.sin(2 * math.pi * 2640 * t + phases[4])
            + 0.02 * np.sin(2 * math.pi * 659.25 * t + phases[5]),
        ),
        axis=0,
    ).astype(np.float32, copy=False)[None]


def _timeout(_signum: int, _frame: object) -> None:
    raise TimeoutError("Mega-53 approved synthetic ceiling reached")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-report", type=Path)
    for name in (
        "checkpoint",
        "config",
        "source-root",
        "source-evidence",
        "model-load-report",
        "report",
    ):
        parser.add_argument(f"--{name}", type=Path)
    parser.add_argument(
        "--accept-approved-generated-tensor-forward", action="store_true"
    )
    args = parser.parse_args()
    if args.validate_report is not None:
        report = validate_synthetic_report(
            json.loads(args.validate_report.resolve(strict=True).read_text())
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    required = (
        "checkpoint",
        "config",
        "source_root",
        "source_evidence",
        "model_load_report",
        "report",
    )
    missing = [
        name.replace("_", "-") for name in required if getattr(args, name) is None
    ]
    if missing:
        parser.error("execution requires " + ", ".join(f"--{name}" for name in missing))
    if not args.accept_approved_generated_tensor_forward:
        raise RuntimeError("explicit generated-tensor approval flag is required")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("approved Mega-53 forward requires Apple-silicon macOS")
    report_path = args.report.resolve()
    if report_path.name != "SYNTHETIC-REPORT.json" or report_path.exists():
        raise RuntimeError("fresh exact synthetic report path is required")
    plan = validate_next_synthetic_plan(build_next_synthetic_plan())
    import mlx.core as mx
    import numpy as np
    import yaml

    from sunofriend.separation_other_refinement_next_execution_guard import (
        Mega53RestrictedExecutionGuard,
    )
    from sunofriend.separation_other_refinement_next_model_load_contract import (
        CHECKPOINT,
        CONFIG,
        validate_model_load_report,
    )
    from sunofriend.separation_other_refinement_next_model_loading import (
        load_mega53_model,
    )
    from sunofriend.separation_other_refinement_next_source_evidence import (
        validate_source_evidence,
        verify_extracted_source_tree,
    )

    class _ConfigLoader(yaml.SafeLoader):
        pass

    _ConfigLoader.add_constructor(
        "tag:yaml.org,2002:python/tuple",
        lambda loader, node: tuple(loader.construct_sequence(node)),
    )
    checkpoint, config = args.checkpoint.resolve(), args.config.resolve()
    _verify(checkpoint, CHECKPOINT)
    _verify(config, CONFIG)
    load_report = validate_model_load_report(
        json.loads(args.model_load_report.read_text())
    )
    if load_report["report_sha256"] != MODEL_LOAD_REPORT_SHA256:
        raise RuntimeError("model-load evidence differs")
    source_evidence = validate_source_evidence(
        json.loads(args.source_evidence.read_text())
    )
    verify_extracted_source_tree(source_evidence, args.source_root.resolve())
    document = yaml.load(config.read_text(), Loader=_ConfigLoader)
    guard = Mega53RestrictedExecutionGuard(checkpoint, expected_forward_calls=1)
    guard.install()
    started = time.monotonic()
    loaded = load_mega53_model(
        checkpoint=checkpoint,
        config_document=document,
        source_root=args.source_root.resolve(),
    )
    generated = _generated(np)
    mx.reset_peak_memory()
    previous = signal.signal(signal.SIGALRM, _timeout)
    signal.setitimer(signal.ITIMER_REAL, MAXIMUM_ELAPSED_SECONDS)
    output = None
    error = None
    try:
        guard.record_forward()
        output = loaded.model(mx.array(generated))
        mx.eval(output)
    except Exception as exc:  # retained objective failure, never retried
        error = f"{type(exc).__name__}: {exc}"
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    elapsed = time.monotonic() - started
    peak = int(mx.get_peak_memory())
    guard.assert_complete()
    result = {
        "forward_completed": output is not None,
        "failure": error,
        "elapsed_seconds": elapsed,
        "peak_mlx_memory_bytes": peak,
    }
    if output is not None:
        shape = list(output.shape)
        dtype = str(output.dtype).removeprefix("mlx.core.")
        finite = bool(mx.all(mx.isfinite(output)).item())
        synth = np.array(output[:, SYNTH_ROLE_INDEX], dtype=np.float32)
        residual = generated - synth
        result.update(
            {
                "output_shape": shape,
                "output_dtype": dtype,
                "all_samples_finite": finite,
                "synth_role": NATIVE_ROLES[SYNTH_ROLE_INDEX],
                "synth_role_index": SYNTH_ROLE_INDEX,
                "synth_peak": float(np.max(np.abs(synth))),
                "residual_peak": float(np.max(np.abs(residual))),
                "maximum_reconstruction_error": float(
                    np.max(np.abs((synth + residual) - generated))
                ),
            }
        )
    report = {
        "schema": REPORT_SCHEMA,
        "report_sha256": "",
        "status": "objective_pass"
        if output is not None
        else "objective_failure_retained",
        "profile_id": plan["profile_id"],
        "plan_sha256": plan["document_sha256"],
        "model_load_report_sha256": MODEL_LOAD_REPORT_SHA256,
        "guards": guard.report(),
        "result": result,
        "effects": {
            "audio_reads": 0,
            "audio_writes": 0,
            "inference_attempts": 1,
            "persisted_audio": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
            "automatic_retry": False,
        },
    }
    report["report_sha256"] = report_sha256(report)
    validate_synthetic_report(report)
    report_path.parent.mkdir(parents=True, exist_ok=False)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
