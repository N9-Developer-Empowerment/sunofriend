#!/usr/bin/env python3
"""Run exactly one approved, tensor-only Banquet synthetic forward attempt."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import resource
import signal
import sys
import time

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import numpy as np
import torch
import torchaudio

from sunofriend.separation_other_refinement_query_execution_guard import (
    QueryRestrictedExecutionGuard,
)
from sunofriend.separation_other_refinement_query_forward_adapter import (
    SingleUseBanquetForward,
)
from sunofriend.separation_other_refinement_query_forward_contract import (
    build_query_forward_contract,
    validate_query_forward_contract,
)
from sunofriend.separation_other_refinement_query_load_contract import (
    EXPECTED_CHECKPOINTS,
    validate_query_model_load_report,
)
from sunofriend.separation_other_refinement_query_model_adapter import (
    BanquetLoadAdapter,
)
from sunofriend.separation_other_refinement_query_model_loading import (
    load_query_models,
)
from sunofriend.separation_other_refinement_query_synthetic_plan import (
    build_query_synthetic_plan,
    validate_query_synthetic_plan,
)
from sunofriend.separation_other_refinement_query_synthetic_report import (
    EXPECTED_RUNTIME,
    MAXIMUM_ELAPSED_SECONDS,
    build_query_synthetic_report,
    validate_query_synthetic_report,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_checkpoint(label: str, path: Path) -> None:
    expected = EXPECTED_CHECKPOINTS[label]
    if (
        path.name != expected["file"]
        or path.stat().st_size != expected["bytes"]
        or _sha256(path) != expected["sha256"]
    ):
        raise RuntimeError(f"{label} checkpoint identity differs")


def _generated_inputs() -> tuple[torch.Tensor, torch.Tensor]:
    generator = torch.Generator(device="cpu")
    generator.manual_seed(0)
    phases = torch.rand(6, generator=generator, dtype=torch.float32) * (2 * math.pi)
    mixture_time = torch.arange(88_200, dtype=torch.float32) / 44_100
    query_time = torch.arange(441_000, dtype=torch.float32) / 44_100
    mixture = torch.stack(
        (
            0.12 * torch.sin(2 * math.pi * 220 * mixture_time + phases[0])
            + 0.04 * torch.sin(2 * math.pi * 1_760 * mixture_time + phases[1]),
            0.11 * torch.sin(2 * math.pi * 330 * mixture_time + phases[2])
            + 0.05 * torch.sin(2 * math.pi * 2_640 * mixture_time + phases[3]),
        ),
        dim=0,
    )[None, ...].contiguous()
    query = torch.stack(
        (
            0.13 * torch.sin(2 * math.pi * 440 * query_time + phases[4]),
            0.12 * torch.sin(2 * math.pi * 660 * query_time + phases[5]),
        ),
        dim=0,
    )[None, ...].contiguous()
    if mixture.shape != (1, 2, 88_200) or query.shape != (1, 2, 441_000):
        raise RuntimeError("generated tensor shape differs")
    return mixture, query


def _peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if platform.system() == "Darwin" else value * 1024)


def _timeout(_signum: int, _frame: object) -> None:
    raise TimeoutError("synthetic forward time ceiling reached")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--banquet", type=Path, required=True)
    parser.add_argument("--passt", type=Path, required=True)
    parser.add_argument("--model-load-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--accept-approved-synthetic-forward", action="store_true")
    args = parser.parse_args()
    if not args.accept_approved_synthetic_forward:
        raise RuntimeError("the explicit approved synthetic-forward flag is required")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("the approved synthetic run requires Apple-silicon macOS")
    report_path = args.report.resolve()
    if report_path.name != "SYNTHETIC-REPORT.json":
        raise RuntimeError("synthetic report filename differs")
    if report_path.parent.name != "query-bandit-synthetic-forward-v1":
        raise RuntimeError("synthetic report evidence root differs")
    if report_path.exists():
        raise RuntimeError("synthetic report already exists; a retry is not authorised")
    runtime = {
        "device": "cpu",
        "numpy": np.__version__,
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "torchaudio": torchaudio.__version__,
    }
    if runtime != EXPECTED_RUNTIME:
        raise RuntimeError("synthetic runtime identity differs")

    plan = validate_query_synthetic_plan(build_query_synthetic_plan())
    if plan["status"] != "approved_for_one_synthetic_inference_attempt":
        raise RuntimeError("synthetic plan is not approved for its one attempt")
    validate_query_forward_contract(build_query_forward_contract())
    load_report = json.loads(args.model_load_report.read_text(encoding="utf-8"))
    validate_query_model_load_report(load_report)

    paths = {"banquet": args.banquet.resolve(), "passt": args.passt.resolve()}
    for label, path in paths.items():
        _verify_checkpoint(label, path)

    started = time.monotonic()
    guard = QueryRestrictedExecutionGuard(paths.values(), phase="synthetic forward")
    guard.install()
    loaded = load_query_models(paths, guard.load_calls)
    if not isinstance(loaded.banquet, BanquetLoadAdapter):
        raise RuntimeError("loaded Banquet adapter identity differs")
    mixture, query = _generated_inputs()
    forward = SingleUseBanquetForward(loaded.banquet)

    remaining = MAXIMUM_ELAPSED_SECONDS - (time.monotonic() - started)
    if remaining <= 0:
        raise RuntimeError("synthetic ceiling elapsed before the forward attempt")
    previous_handler = signal.signal(signal.SIGALRM, _timeout)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    target = None
    try:
        with torch.inference_mode():
            target = forward.run_once(mixture, query)
    except Exception as error:
        print(
            f"synthetic forward retained objective failure: {type(error).__name__}",
            file=sys.stderr,
        )
        target = None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)

    elapsed = time.monotonic() - started
    guard.assert_no_forbidden_effects()
    base_result = {
        "forward_completed": target is not None,
        "output_shape": None,
        "output_dtype": None,
        "output_sample_rate_hz": None,
        "all_output_samples_finite": None,
        "target_peak": None,
        "residual_peak": None,
        "maximum_reconstruction_error": None,
        "residual_definition": None,
        "elapsed_seconds": elapsed,
        "peak_resident_set_bytes": _peak_rss_bytes(),
    }
    if target is not None:
        residual = mixture - target
        finite = bool(torch.isfinite(target).all() and torch.isfinite(residual).all())
        base_result.update(
            {
                "output_shape": list(target.shape),
                "output_dtype": str(target.dtype).removeprefix("torch."),
                "output_sample_rate_hz": 44_100,
                "all_output_samples_finite": finite,
                "residual_definition": "generated_mixture - requested_target",
            }
        )
        if finite:
            base_result.update(
                {
                    "target_peak": float(target.abs().max()),
                    "residual_peak": float(residual.abs().max()),
                    "maximum_reconstruction_error": float(
                        ((target + residual) - mixture).abs().max()
                    ),
                }
            )

    report = build_query_synthetic_report(
        result=base_result,
        guards=guard.report(),
        expected_plan_sha256=plan["document_sha256"],
    )
    validate_query_synthetic_report(
        report,
        expected_plan_sha256=plan["document_sha256"],
    )
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8") as handle:
        handle.write(rendered)
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
