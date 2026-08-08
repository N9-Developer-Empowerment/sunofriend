#!/usr/bin/env python3
"""Run the one approved nine-case private Banquet reference canary."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
from pathlib import Path
import platform
import resource
import signal
import sys
import tempfile
import time
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import numpy as np
import torch
import torchaudio

from sunofriend.separation_other_refinement_query_forward_adapter import (
    BoundedBanquetReferenceForward,
)
from sunofriend.separation_other_refinement_query_forward_contract import (
    build_query_forward_contract,
    validate_query_forward_contract,
)
from sunofriend.separation_other_refinement_query_load_contract import (
    EXPECTED_CHECKPOINTS,
    QUERY_BANDIT_SOURCE_REVISION,
    validate_query_model_load_report,
)
from sunofriend.separation_other_refinement_query_model_adapter import (
    BanquetLoadAdapter,
)
from sunofriend.separation_other_refinement_query_model_loading import (
    load_query_models,
)
from sunofriend.separation_other_refinement_query_reference_audio import (
    audio_artifact,
    build_pcm24_accounting,
    file_sha256,
    inspect_pcm_wav,
    quantize_pcm24,
    read_pcm24,
    read_wav_window,
    write_pcm24,
)
from sunofriend.separation_other_refinement_query_reference_contract import (
    build_query_reference_input_contract,
    validate_query_reference_input_contract,
)
from sunofriend.separation_other_refinement_query_reference_guard import (
    QueryReferenceExecutionGuard,
)
from sunofriend.separation_other_refinement_query_reference_plan import (
    build_query_reference_plan,
    validate_query_reference_plan,
)
from sunofriend.separation_other_refinement_query_reference_report import (
    build_query_reference_report,
    render_query_reference_review,
    validate_query_reference_report,
)
from sunofriend.separation_other_refinement_query_synthetic_plan import (
    build_query_synthetic_plan,
    validate_query_synthetic_plan,
)
from sunofriend.separation_other_refinement_query_synthetic_report import (
    EXPECTED_RUNTIME,
)
from sunofriend.separation_other_refinement_query_synthetic_report_validation import (
    validate_query_synthetic_report,
)


OUTPUT_NAME = "query-bandit-reference-canary-v1"
REPORT_NAME = "REFERENCE-REPORT.json"


def _peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if platform.system() == "Darwin" else value * 1024)


def _timeout(_signum: int, _frame: object) -> None:
    raise TimeoutError("reference-query canary exceeded 180 seconds")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    path.chmod(0o600)


def _exclusive_publish(staging: Path, destination: Path) -> None:
    if platform.system() != "Darwin" or staging.parent != destination.parent:
        raise RuntimeError("reference canary requires macOS atomic publication")
    library = ctypes.CDLL(None, use_errno=True)
    function = getattr(library, "renameatx_np", None)
    if function is None:
        raise RuntimeError("exclusive atomic directory publication is unavailable")
    function.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    function.restype = ctypes.c_int
    parent_fd = os.open(staging.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        result = function(
            parent_fd,
            os.fsencode(staging.name),
            parent_fd,
            os.fsencode(destination.name),
            0x00000004,
        )
    finally:
        os.close(parent_fd)
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(destination)
    raise OSError(error_number, os.strerror(error_number), destination)


def _input_paths(
    *, stem_root: Path, contract: dict[str, Any]
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for item in contract["inputs"]:
        path = (stem_root / item["relative_path"]).resolve(strict=True)
        if stem_root not in path.parents:
            raise RuntimeError("reference input escapes the authorised corpus")
        paths[item["label"]] = path
    return paths


def _verify_inputs(
    contract: dict[str, Any], paths: dict[str, Path]
) -> list[dict[str, Any]]:
    receipts = []
    for expected in contract["inputs"]:
        path = paths[expected["label"]]
        geometry = inspect_pcm_wav(path)
        actual = {
            "label": expected["label"],
            "kind": expected["kind"],
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
            **{key: geometry[key] for key in (
                "sample_rate_hz",
                "channels",
                "sample_width_bytes",
                "frames",
            )},
        }
        comparable = {key: expected[key] for key in actual}
        if actual != comparable:
            raise RuntimeError(f"reference input identity differs: {expected['label']}")
        receipts.append(actual)
    return receipts


def _verify_checkpoint(label: str, path: Path) -> dict[str, Any]:
    expected = EXPECTED_CHECKPOINTS[label]
    actual = {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }
    if actual != expected:
        raise RuntimeError(f"{label} checkpoint identity differs")
    return actual


def _case_output_paths(staging: Path, plan: dict[str, Any]) -> list[Path]:
    paths = []
    for mixture in plan["test_mixtures"]:
        for query in plan["query_bank"]["queries"]:
            case = staging / "CASES" / f"{mixture['track_id']}--{query['target_id']}"
            paths.extend(
                case / name
                for name in (
                    "source-reference.wav",
                    "query-reference.wav",
                    "target.wav",
                    "residual.wav",
                )
            )
    return paths


def _preserve_failure(staging: Path, destination: Path, error: BaseException) -> None:
    try:
        technical = staging / "TECHNICAL"
        technical.mkdir(parents=True, exist_ok=True, mode=0o700)
        failure = technical / "RETAINED-FAILURE.json"
        if not failure.exists():
            _write_json(
                failure,
                {
                    "schema": "sunofriend.other-refinement-query-reference-failure.v1",
                    "status": "retained_objective_failure_no_retry",
                    "error_type": type(error).__name__,
                    "error": str(error)[:2000],
                    "automatic_retry": False,
                    "public_activation": False,
                    "source_selected": False,
                    "midi_created": False,
                },
            )
        failed = destination.with_name(destination.name + "-FAILED")
        _exclusive_publish(staging, failed)
        print(f"retained failure evidence: {failed}", file=sys.stderr)
    except BaseException as preserve_error:
        print(f"could not publish failure evidence: {preserve_error}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stem-root", type=Path, required=True)
    parser.add_argument("--banquet", type=Path, required=True)
    parser.add_argument("--passt", type=Path, required=True)
    parser.add_argument("--model-load-report", type=Path, required=True)
    parser.add_argument("--synthetic-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--accept-approved-reference-canary", action="store_true")
    args = parser.parse_args()
    if not args.accept_approved_reference_canary:
        raise RuntimeError("the explicit approved reference-canary flag is required")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("the approved reference canary requires Apple-silicon macOS")
    destination = args.out.resolve()
    if destination.name != OUTPUT_NAME:
        raise RuntimeError("reference canary output name differs")
    if destination.exists():
        raise FileExistsError("reference canary output already exists; no retry is authorised")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{OUTPUT_NAME}.staging-", dir=destination.parent)
    )
    staging.chmod(0o700)
    try:
        plan = validate_query_reference_plan(build_query_reference_plan())
        contract = validate_query_reference_input_contract(
            build_query_reference_input_contract()
        )
        validate_query_forward_contract(build_query_forward_contract())
        synthetic_plan = validate_query_synthetic_plan(build_query_synthetic_plan())
        if contract["plan_document_sha256"] != plan["document_sha256"]:
            raise RuntimeError("reference input contract is bound to another plan")
        stem_root = args.stem_root.resolve(strict=True)
        if file_sha256(stem_root / "corpus.json") != plan["evidence_binding"][
            "authorised_corpus_manifest_sha256"
        ]:
            raise RuntimeError("authorised corpus manifest differs")
        if file_sha256(
            stem_root / "other-refinement-evaluation-v1.json"
        ) != plan["evidence_binding"]["frozen_window_manifest_sha256"]:
            raise RuntimeError("frozen reference window manifest differs")

        load_report = json.loads(args.model_load_report.read_text(encoding="utf-8"))
        validate_query_model_load_report(load_report)
        synthetic_report = json.loads(args.synthetic_report.read_text(encoding="utf-8"))
        validate_query_synthetic_report(
            synthetic_report,
            expected_plan_sha256=synthetic_plan["document_sha256"],
        )
        if synthetic_report["report_sha256"] != plan["evidence_binding"][
            "synthetic_report_sha256"
        ]:
            raise RuntimeError("synthetic report identity differs")

        input_paths = _input_paths(stem_root=stem_root, contract=contract)
        checkpoint_paths = {
            "banquet": args.banquet.resolve(strict=True),
            "passt": args.passt.resolve(strict=True),
        }
        output_paths = _case_output_paths(staging, plan)
        guard = QueryReferenceExecutionGuard(
            checkpoint_paths.values(), input_paths.values(), output_paths
        )
        guard.install()
        started = time.monotonic()
        previous_handler = signal.signal(signal.SIGALRM, _timeout)
        signal.setitimer(signal.ITIMER_REAL, 180.0)
        try:
            input_receipts = _verify_inputs(contract, input_paths)
            checkpoints = {
                label: _verify_checkpoint(label, path)
                for label, path in checkpoint_paths.items()
            }
            runtime = {
                "device": "cpu",
                "numpy": np.__version__,
                "python": sys.version.split()[0],
                "torch": torch.__version__,
                "torchaudio": torchaudio.__version__,
            }
            if runtime != EXPECTED_RUNTIME:
                raise RuntimeError("reference runtime identity differs")
            torch.manual_seed(0)
            torch.use_deterministic_algorithms(True)
            loaded = load_query_models(checkpoint_paths, guard.load_calls)
            if not isinstance(loaded.banquet, BanquetLoadAdapter):
                raise RuntimeError("reference Banquet adapter identity differs")
            forward = BoundedBanquetReferenceForward(loaded.banquet)
            query_tensors = {
                query["target_id"]: read_wav_window(
                    input_paths[f"query:{query['target_id']}"],
                    start_seconds=query["start_seconds"],
                    end_seconds=query["end_seconds"],
                    expected_frames=441_000,
                )
                for query in plan["query_bank"]["queries"]
            }
            cases: list[dict[str, Any]] = []
            receipt_by_label = {item["label"]: item for item in input_receipts}
            with torch.inference_mode():
                for mixture_spec in plan["test_mixtures"]:
                    track_id = mixture_spec["track_id"]
                    for query_spec in plan["query_bank"]["queries"]:
                        target_id = query_spec["target_id"]
                        case_id = f"{track_id}--{target_id}"
                        start, end = mixture_spec["windows"][target_id]
                        mixture = read_wav_window(
                            input_paths[f"mixture:{track_id}"],
                            start_seconds=start,
                            end_seconds=end,
                            expected_frames=661_500,
                        )
                        query = query_tensors[target_id]
                        target = forward.run_next(mixture, query)
                        if target.shape != mixture.shape or target.dtype != torch.float32:
                            raise RuntimeError(f"reference output differs: {case_id}")
                        residual = mixture - target
                        finite = bool(
                            torch.isfinite(target).all()
                            and torch.isfinite(residual).all()
                        )
                        tensor_error = float(
                            ((target + residual) - mixture).abs().max()
                        )
                        accounting = build_pcm24_accounting(mixture, target)
                        query_pcm, query_attenuation = quantize_pcm24(query)
                        case_root = staging / "CASES" / case_id
                        paths = {
                            "source_reference": case_root / "source-reference.wav",
                            "query_reference": case_root / "query-reference.wav",
                            "target": case_root / "target.wav",
                            "residual": case_root / "residual.wav",
                        }
                        write_pcm24(paths["source_reference"], accounting["source"])
                        write_pcm24(paths["query_reference"], query_pcm)
                        write_pcm24(paths["target"], accounting["target"])
                        write_pcm24(paths["residual"], accounting["residual"])
                        persisted_error = int(
                            np.max(
                                np.abs(
                                    read_pcm24(paths["target"])
                                    + read_pcm24(paths["residual"])
                                    - read_pcm24(paths["source_reference"])
                                )
                            )
                        )
                        if persisted_error != accounting[
                            "maximum_reconstruction_error_lsb"
                        ]:
                            raise RuntimeError("persisted reconstruction receipt differs")
                        artifacts = {
                            key: audio_artifact(path, relative_to=staging)
                            for key, path in paths.items()
                        }
                        cases.append(
                            {
                                "case_id": case_id,
                                "track_id": track_id,
                                "target_id": target_id,
                                "song_disjoint_query": True,
                                "mixture_window_seconds": [start, end],
                                "query_window_seconds": [
                                    query_spec["start_seconds"],
                                    query_spec["end_seconds"],
                                ],
                                "mixture_input": receipt_by_label[
                                    f"mixture:{track_id}"
                                ],
                                "query_input": receipt_by_label[
                                    f"query:{target_id}"
                                ],
                                "provider_query_is_truth": False,
                                "geometry": {
                                    "sample_rate_hz": 44_100,
                                    "channels": 2,
                                    "frames": 661_500,
                                },
                                "accounting": {
                                    "finite": finite,
                                    "shared_attenuation": accounting[
                                        "shared_attenuation"
                                    ],
                                    "query_attenuation": query_attenuation,
                                    "source_peak": accounting["source_peak"],
                                    "target_peak": accounting["target_peak"],
                                    "residual_peak": accounting["residual_peak"],
                                    "maximum_tensor_reconstruction_error": tensor_error,
                                    "maximum_reconstruction_error_lsb": persisted_error,
                                    "reconstruction_accounting_is_separation_accuracy": False,
                                },
                                "artifacts": artifacts,
                            }
                        )
            if forward.attempts != 9 or len(cases) != 9:
                raise RuntimeError("reference inference attempt count differs")
            guard.assert_no_forbidden_effects()
            elapsed = time.monotonic() - started
            report = build_query_reference_report(
                plan_sha256=plan["document_sha256"],
                input_contract_sha256=contract["document_sha256"],
                runtime=runtime,
                model={
                    "source_revision": QUERY_BANDIT_SOURCE_REVISION,
                    "checkpoints": checkpoints,
                    "strict_load": loaded.evidence,
                    "models_loaded_once": True,
                    "seed": 0,
                },
                cases=cases,
                guards=guard.report(),
                elapsed_seconds=elapsed,
                peak_resident_set_bytes=_peak_rss_bytes(),
            )
            validate_query_reference_report(report)
            _write_json(staging / "TECHNICAL" / REPORT_NAME, report)
            _write_json(staging / "TECHNICAL" / "INPUT-CONTRACT.json", contract)
            review = staging / "REVIEW" / "review.html"
            review.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            review.write_text(render_query_reference_review(report), encoding="utf-8")
            review.chmod(0o600)
            start_here = staging / "START-HERE.txt"
            start_here.write_text(
                "Serve REVIEW/review.html locally and listen to every case. "
                "The provider query is a comparison estimate, not truth. "
                "No source was selected and no MIDI was created.\n",
                encoding="utf-8",
            )
            start_here.chmod(0o600)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
        _exclusive_publish(staging, destination)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "root": str(destination),
                    "report": str(destination / "TECHNICAL" / REPORT_NAME),
                    "review": str(destination / "REVIEW" / "review.html"),
                    "document_sha256": report["document_sha256"],
                    "inference_attempts": len(report["cases"]),
                    "elapsed_seconds": report["resources"]["elapsed_seconds"],
                    "peak_resident_set_bytes": report["resources"][
                        "peak_resident_set_bytes"
                    ],
                    "public_activation": False,
                    "source_selected": False,
                    "midi_created": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except BaseException as error:
        if staging.exists():
            _preserve_failure(staging, destination, error)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
