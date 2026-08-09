#!/usr/bin/env python3
"""Plan, execute or validate one bounded private synth/guitar canary."""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_canary_audio import (
    file_sha256,
    persist_target_and_residual,
    read_canonical_pcm24,
)
from sunofriend.separation_fine_stem_canary_review import render_fine_stem_review
from sunofriend.separation_fine_stem_canary_contract import (
    CANARY_REPORT_SCHEMA,
    MAXIMUM_ELAPSED_SECONDS,
    PROFILE_CONTRACTS,
    WINDOW_FRAMES,
    build_fine_stem_canary_plan,
    canary_document_sha256,
    validate_fine_stem_canary_plan,
    validate_fine_stem_canary_report,
)
from sunofriend.separation_target_presence_review import (
    load_presence_manifest,
    validate_presence_result,
)


_SANDBOX_FLAG = "SUNOFRIEND_FINE_STEM_NETWORK_SANDBOX"


def _verify_file(path: Path, expected: dict[str, Any]) -> None:
    if (
        path.name != expected["file"]
        or path.stat().st_size != expected["bytes"]
        or file_sha256(path) != expected["sha256"]
    ):
        raise RuntimeError("fine-stem profile artifact identity differs: " + path.name)


def _load_inputs(presence_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = load_presence_manifest(presence_root)
    result_path = presence_root / "PRESENCE-RESULT.json"
    if not result_path.is_file():
        raise RuntimeError("fine-stem target-presence result is missing")
    result = validate_presence_result(
        json.loads(result_path.read_text(encoding="utf-8")), manifest
    )
    return manifest, result


def _available(path: Any, expected: dict[str, Any]) -> bool:
    if not isinstance(path, Path) or not path.is_file():
        return False
    try:
        _verify_file(path.resolve(), expected)
    except RuntimeError:
        return False
    return True


def _yaml_document(path: Path) -> dict[str, Any]:
    import yaml

    class _ConfigLoader(yaml.SafeLoader):
        pass

    _ConfigLoader.add_constructor(
        "tag:yaml.org,2002:python/tuple",
        lambda loader, node: tuple(loader.construct_sequence(node)),
    )
    document = yaml.load(path.read_text(encoding="utf-8"), Loader=_ConfigLoader)
    if not isinstance(document, dict):
        raise RuntimeError("fine-stem profile configuration differs")
    return document


def _sandbox_reexec() -> int:
    sandbox = Path("/usr/bin/sandbox-exec")
    if not sandbox.is_file():
        raise RuntimeError("macOS sandbox-exec is required for network denial")
    environment = os.environ.copy()
    environment[_SANDBOX_FLAG] = "1"
    command = [
        str(sandbox),
        "-p",
        "(version 1)(allow default)(deny network*)",
        sys.executable,
        str(Path(__file__).resolve()),
        *sys.argv[1:],
    ]
    return subprocess.run(command, env=environment, check=False).returncode


def _timeout(_signum: int, _frame: Any) -> None:
    raise TimeoutError("fine-stem canary elapsed-time ceiling reached")


class _ForwardGuardedModel:
    def __init__(self, model: Any, guard: Any) -> None:
        self._model = model
        self._guard = guard

    def __call__(self, value: Any) -> Any:
        self._guard.record_forward()
        return self._model(value)


def _mega53_target(model: Any, guard: Any, source: Any) -> Any:
    import mlx.core as mx
    import numpy as np

    from sunofriend.separation_other_refinement_next_synthetic_plan import (
        ALIGNED_CHUNK_SIZE,
        SYNTH_ROLE_INDEX,
    )

    mixture = np.zeros((1, 2, ALIGNED_CHUNK_SIZE), dtype=np.float32)
    mixture[0, :, :WINDOW_FRAMES] = source.astype(np.float32).T
    guard.record_forward()
    output = model(mx.array(mixture))
    mx.eval(output)
    if list(output.shape) != [1, 53, 2, ALIGNED_CHUNK_SIZE]:
        raise RuntimeError("Mega-53 song-canary output shape differs")
    if not bool(mx.all(mx.isfinite(output)).item()):
        raise RuntimeError("Mega-53 song-canary output is non-finite")
    target = np.array(output[0, SYNTH_ROLE_INDEX, :, :WINDOW_FRAMES], dtype=np.float32)
    del output
    mx.clear_cache()
    return target.T


def _sw_backend(loaded: Any, guard: Any) -> Any:
    from bs_roformer.backends.mlx_backend import MLXBackend

    return MLXBackend(_ForwardGuardedModel(loaded.model, guard), loaded.config)


def _execute(args: argparse.Namespace, plan: dict[str, Any]) -> int:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("fine-stem canaries require Apple-silicon macOS")
    if os.environ.get(_SANDBOX_FLAG) != "1":
        return _sandbox_reexec()
    if not args.confirm_rights:
        raise RuntimeError("--confirm-rights is required for private audio")
    if plan["status"] != "ready_for_bounded_private_execution":
        raise RuntimeError("fine-stem canary plan is not executable: " + plan["status"])
    if args.out is None:
        raise RuntimeError("--out is required for execution")
    out = args.out.resolve()
    if out.exists():
        raise RuntimeError("fine-stem canary output must be fresh")
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    checkpoint = args.checkpoint.resolve(strict=True)
    config = args.config.resolve(strict=True)
    profile = PROFILE_CONTRACTS[args.profile]
    _verify_file(checkpoint, profile["checkpoint"])
    _verify_file(config, profile["config"])
    presence_root = args.presence_root.resolve(strict=True)
    manifest, result = _load_inputs(presence_root)
    current_plan = build_fine_stem_canary_plan(
        args.profile,
        manifest,
        result,
        checkpoint_available=True,
        config_available=True,
    )
    if current_plan != plan:
        raise RuntimeError("fine-stem canary plan changed before execution")
    source_paths = [
        (presence_root / case["source_artifact"]["relative_path"]).resolve(
            strict=True
        )
        for case in plan["cases"]
    ]
    staging = Path(
        tempfile.mkdtemp(prefix="." + out.name + "-", dir=str(out.parent))
    )
    staging.chmod(0o700)
    target_role = profile["target_role"]
    output_paths = []
    for case in plan["cases"]:
        case_root = staging / "CASES" / case["case_id"]
        output_paths.extend(
            [
                case_root / "reference.wav",
                case_root / (target_role + ".wav"),
                case_root / "residual.wav",
            ]
        )
    from sunofriend.separation_fine_stem_canary_guard import (
        FineStemCanaryExecutionGuard,
    )
    from sunofriend.separation_other_refinement_next_source_evidence import (
        validate_source_evidence,
        verify_extracted_source_tree,
    )

    source_evidence = validate_source_evidence(
        json.loads(args.source_evidence.resolve(strict=True).read_text())
    )
    verify_extracted_source_tree(source_evidence, args.source_root.resolve(strict=True))
    guard = FineStemCanaryExecutionGuard(
        checkpoint,
        audio_inputs=source_paths,
        audio_outputs=output_paths,
        expected_forward_calls=plan["execution"]["model_forward_calls"],
    )
    guard.install()
    import mlx.core as mx
    import numpy as np

    previous = signal.signal(signal.SIGALRM, _timeout)
    signal.setitimer(signal.ITIMER_REAL, MAXIMUM_ELAPSED_SECONDS)
    started = time.monotonic()
    mx.reset_peak_memory()
    cases = []
    model_evidence = {}
    try:
        document = _yaml_document(config)
        if args.profile == "bs-roformer-mega-53-synth-v1":
            from sunofriend.separation_other_refinement_next_model_load_contract import (
                validate_model_load_report,
            )
            from sunofriend.separation_other_refinement_next_model_loading import (
                load_mega53_model,
            )

            validate_model_load_report(
                json.loads(args.model_load_report.resolve(strict=True).read_text())
            )
            loaded = load_mega53_model(
                checkpoint=checkpoint,
                config_document=document,
                source_root=args.source_root.resolve(strict=True),
            )
            model_evidence = loaded.evidence
            backend = None
        else:
            from sunofriend.separation_bs_roformer_sw_loading import load_sw_model

            loaded = load_sw_model(
                checkpoint=checkpoint,
                config_document=document,
                source_root=args.source_root.resolve(strict=True),
            )
            model_evidence = loaded.evidence
            backend = _sw_backend(loaded, guard)
        for case, source_path in zip(plan["cases"], source_paths):
            artifact = case["source_artifact"]
            if (
                source_path.stat().st_size != artifact["bytes"]
                or file_sha256(source_path) != artifact["sha256"]
            ):
                raise RuntimeError("fine-stem presence source changed")
            source = read_canonical_pcm24(source_path)
            if args.profile == "bs-roformer-mega-53-synth-v1":
                native_target = _mega53_target(loaded.model, guard, source)
            else:
                separated = backend.separate(source.astype(np.float32).T)
                if set(separated) != set(profile["native_roles"]):
                    raise RuntimeError("BS-RoFormer-SW native roles differ")
                native_target = separated[target_role].T
            persisted = persist_target_and_residual(
                staging,
                case_id=case["case_id"],
                source=source,
                native_target=native_target,
                target_role=target_role,
            )
            cases.append(
                {
                    "case_id": case["case_id"],
                    "track_id": case["track_id"],
                    "title": case["title"],
                    "target_role": target_role,
                    "window_seconds": case["window_seconds"],
                    "source_input_sha256": artifact["sha256"],
                    **persisted,
                }
            )
        elapsed = time.monotonic() - started
        peak = int(mx.get_peak_memory())
        if elapsed > plan["execution"]["maximum_elapsed_seconds"]:
            raise RuntimeError("fine-stem canary exceeded its elapsed-time ceiling")
        if peak > plan["execution"]["maximum_peak_mlx_memory_bytes"]:
            raise RuntimeError("fine-stem canary exceeded its MLX-memory ceiling")
        guard.assert_complete()
        report = {
            "schema": CANARY_REPORT_SCHEMA,
            "report_sha256": "",
            "status": "objective_execution_complete_review_required",
            "profile_id": args.profile,
            "target_role": target_role,
            "plan": plan,
            "runtime": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "machine": platform.machine(),
                "network_denied_by_parent_sandbox": True,
            },
            "model": model_evidence,
            "guards": guard.report(),
            "resource": {
                "elapsed_seconds": elapsed,
                "peak_mlx_memory_bytes": peak,
                "elapsed_ceiling_seconds": MAXIMUM_ELAPSED_SECONDS,
                "memory_ceiling_bytes": plan["execution"][
                    "maximum_peak_mlx_memory_bytes"
                ],
            },
            "cases": cases,
            "effects": {
                "checkpoint_loads": 1,
                "model_constructions": 1,
                "inference_attempts": len(cases),
                "audio_reads": len(cases),
                "audio_writes": len(cases) * 3,
                "public_activation": False,
                "source_selection": False,
                "midi_created": False,
                "hosting": False,
                "redistribution": False,
                "automatic_retry": False,
                "human_review_recorded": False,
            },
        }
        report["report_sha256"] = canary_document_sha256(report)
        validate_fine_stem_canary_report(report)
        technical = staging / "TECHNICAL"
        review = staging / "REVIEW"
        technical.mkdir(mode=0o700)
        review.mkdir(mode=0o700)
        report_path = technical / "CANARY-REPORT.json"
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        report_path.chmod(0o600)
        review_path = review / "fine_stem_review.html"
        review_path.write_text(render_fine_stem_review(report), encoding="utf-8")
        review_path.chmod(0o600)
        staging.rename(out)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except BaseException as exc:
        failure = {
            "schema": "sunofriend.fine-stem-canary-failure.v1",
            "status": "objective_failure_retained_no_retry",
            "profile_id": args.profile,
            "failure_type": type(exc).__name__,
            "failure": str(exc),
            "guards": guard.report(),
            "effects": {
                "automatic_retry": False,
                "public_activation": False,
                "source_selection": False,
                "midi_created": False,
            },
        }
        failure_path = staging / "FAILED-REPORT.json"
        failure_path.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
        failure_path.chmod(0o600)
        failed = out.with_name(out.name + "-FAILED")
        if not failed.exists():
            staging.rename(failed)
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=sorted(PROFILE_CONTRACTS))
    parser.add_argument("--presence-root", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--source-evidence", type=Path)
    parser.add_argument("--model-load-report", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-rights", action="store_true")
    parser.add_argument("--validate-report", type=Path)
    args = parser.parse_args()
    if args.validate_report is not None:
        value = validate_fine_stem_canary_report(
            json.loads(args.validate_report.resolve(strict=True).read_text())
        )
        print(json.dumps(value, indent=2, sort_keys=True))
        return 0
    required = ("profile", "presence_root")
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("planning requires " + ", ".join("--" + name for name in missing))
    manifest, result = _load_inputs(args.presence_root.resolve(strict=True))
    profile = PROFILE_CONTRACTS[args.profile]
    plan = build_fine_stem_canary_plan(
        args.profile,
        manifest,
        result,
        checkpoint_available=_available(args.checkpoint, profile["checkpoint"]),
        config_available=_available(args.config, profile["config"]),
    )
    validate_fine_stem_canary_plan(plan)
    if not args.execute:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    for name in ("checkpoint", "config", "source_root", "source_evidence"):
        if getattr(args, name) is None:
            parser.error("execution requires --" + name.replace("_", "-"))
    if args.profile == "bs-roformer-mega-53-synth-v1" and args.model_load_report is None:
        parser.error("Mega-53 execution requires --model-load-report")
    return _execute(args, plan)


if __name__ == "__main__":
    raise SystemExit(main())
