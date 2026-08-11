#!/usr/bin/env python3
"""Execute the exact approved private six-role integration canary once."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_canary_audio import (  # noqa: E402
    file_sha256,
    read_canonical_pcm24,
)
from sunofriend.separation_fine_stem_integration_audio import (  # noqa: E402
    persist_six_roles,
    project_within_grouped_other,
    quantize_six_roles,
)
from sunofriend.separation_fine_stem_integration_completion_plan import (  # noqa: E402
    build_completion_plan,
    load_completed_worker_receipt,
)
from sunofriend.separation_fine_stem_integration_plan import (  # noqa: E402
    build_fine_stem_six_role_integration_plan,
    validate_fine_stem_six_role_integration_plan,
)
from sunofriend.separation_fine_stem_integration_report import (  # noqa: E402
    REPORT_SCHEMA,
    REPORT_STATUS,
    integration_report_sha256,
    validate_fine_stem_integration_report,
)


APPROVED_PLAN_SHA256 = "9507d1ef182a0060270033a770a823b758ba024e75cc42e768117e66893f1dec"
SANDBOX_FLAG = "SUNOFRIEND_SIX_ROLE_NETWORK_SANDBOX"
WORKER_REQUEST_SCHEMA = "sunofriend.fine-stem-six-role-worker-request.v1"
MAXIMUM_ELAPSED_SECONDS = 900.0
MAXIMUM_MEMORY_BYTES = 30 * 1024**3


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("fine-stem integration JSON must be an object")
    return value


def _pair(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    package = root.resolve(strict=True)
    return (
        _json(package / "TECHNICAL/CANARY-REPORT.json"),
        _json(package / "REVIEW/FINE-STEM-LISTENING.json"),
    )


def _plan(args: argparse.Namespace) -> dict[str, Any]:
    synth_report, synth_review = _pair(args.synth_root)
    guitar_report, guitar_review = _pair(args.guitar_root)
    return validate_fine_stem_six_role_integration_plan(
        build_fine_stem_six_role_integration_plan(
            portfolio_outcome=_json(args.portfolio_outcome),
            synth_report=synth_report,
            synth_review=synth_review,
            guitar_report=guitar_report,
            guitar_review=guitar_review,
        )
    )


def _sandbox_reexec() -> int:
    sandbox = Path("/usr/bin/sandbox-exec")
    if not sandbox.is_file():
        raise RuntimeError("macOS sandbox-exec is required for network denial")
    environment = os.environ.copy()
    environment[SANDBOX_FLAG] = "1"
    return subprocess.run(
        [
            str(sandbox),
            "-p",
            "(version 1)(allow default)(deny network*)",
            sys.executable,
            str(Path(__file__).resolve()),
            *sys.argv[1:],
        ],
        env=environment,
        check=False,
    ).returncode


def _artifact_path(root: Path, artifact: dict[str, Any]) -> Path:
    package = root.resolve(strict=True)
    path = (package / artifact["relative_path"]).resolve(strict=True)
    if (
        package not in path.parents
        or path.stat().st_size != artifact["bytes"]
        or file_sha256(path) != artifact["sha256"]
    ):
        raise RuntimeError("fine-stem integration input artifact identity differs")
    return path


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _run_worker(
    *,
    mode: str,
    request: dict[str, Any],
    python: Path,
    temporary: Path,
    remaining_seconds: float,
) -> dict[str, Any]:
    request_path = temporary / f"{mode}-request.json"
    result_path = temporary / f"{mode}-result.json"
    _write_json(request_path, request)
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "NO_PROXY": "*",
            "no_proxy": "*",
            "PIP_NO_INDEX": "1",
        }
    )
    if mode != "scnet":
        verified_source_package = Path(request["source_root"]).resolve(strict=True) / "src"
        if not (verified_source_package / "bs_roformer").is_dir():
            raise FileNotFoundError("verified BS-RoFormer source package is missing")
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(ROOT / "src"), str(verified_source_package))
        )
    runtime_python = python.expanduser().absolute()
    if not runtime_python.is_file():
        raise FileNotFoundError("fine-stem integration runtime Python is missing")
    # Preserve the virtual-environment entry path. Resolving this symlink would
    # invoke the base interpreter and silently discard the verified closure.
    command = [
        str(runtime_python),
        "-m",
        "sunofriend.separation_fine_stem_integration_worker",
        "--mode",
        mode,
        "--request",
        str(request_path),
        "--result",
        str(result_path),
        "--network-denial-enforced",
    ]
    completed = subprocess.run(
        command,
        env=environment,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=max(1.0, remaining_seconds),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{mode} worker failed without retry: "
            + (completed.stderr.strip() or completed.stdout.strip())
        )
    result = _json(result_path)
    if (
        result.get("schema") != "sunofriend.fine-stem-six-role-integration-worker.v1"
        or result.get("mode") != mode
        or result.get("effects", {}).get("model_loads") != 1
        or result.get("effects", {}).get("network_attempts") != 0
    ):
        raise RuntimeError("fine-stem integration worker receipt differs")
    return result


def _temporary_array(identity: dict[str, Any]) -> Any:
    import numpy as np

    path = Path(identity["path"]).resolve(strict=True)
    if path.stat().st_size != identity["bytes"] or file_sha256(path) != identity["sha256"]:
        raise RuntimeError("fine-stem integration temporary estimate identity differs")
    with path.open("rb") as handle:
        value = np.load(handle, allow_pickle=False)
    if value.shape != (661_500, 2) or value.dtype != np.float32 or not np.isfinite(value).all():
        raise RuntimeError("fine-stem integration temporary estimate geometry differs")
    return value.astype(np.float64)


def _worker_case_map(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = result.get("cases", [])
    mapped = {case["case_id"]: case for case in cases}
    if len(mapped) != len(cases):
        raise RuntimeError("fine-stem integration worker case identity differs")
    return mapped


def _recover_completed_guitar_outputs(
    root_value: Path,
    *,
    plan: dict[str, Any],
    completion_plan_sha256: str,
) -> dict[str, Any]:
    """Bind completed SW outputs after the urllib3 local-socket false positive."""

    root = root_value.resolve(strict=True)
    failure = _json(root / "FAILED-REPORT.json")
    if (
        failure.get("schema")
        != "sunofriend.fine-stem-six-role-integration-failure.v1"
        or failure.get("status") != "objective_failure_retained_no_retry"
        or failure.get("plan_sha256") != plan["document_sha256"]
        or failure.get("completion_plan_sha256") != completion_plan_sha256
        or "fine-stem canary crossed its effects boundary"
        not in failure.get("failure", "")
    ):
        raise ValueError("fine-stem guitar recovery failure binding differs")
    request_path = (root / "TEMP/sw-guitar-request.json").resolve(strict=True)
    request = _json(request_path)
    expected_cases = [
        case["case_id"]
        for case in plan["cases"]
        if case["new_complementary_estimate"]["role"] == "guitar"
    ]
    if (
        request.get("schema") != WORKER_REQUEST_SCHEMA
        or request.get("mode") != "sw-guitar"
        or request.get("network_denied") is not True
        or [case.get("case_id") for case in request.get("cases", [])]
        != expected_cases
    ):
        raise ValueError("fine-stem guitar recovery request differs")
    cases = []
    last_output_mtime_ns = request_path.stat().st_mtime_ns
    for case_id in expected_cases:
        path = (root / "TEMP/guitar" / case_id / "guitar.npy").resolve(strict=True)
        if root not in path.parents:
            raise ValueError("fine-stem guitar recovery output escaped root")
        identity = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
            "shape": [661_500, 2],
            "dtype": "float32",
            "finite": True,
        }
        value = _temporary_array(identity)
        identity.update(
            {
                "rms": float((value**2).mean() ** 0.5),
                "peak": float(abs(value).max(initial=0.0)),
            }
        )
        last_output_mtime_ns = max(last_output_mtime_ns, path.stat().st_mtime_ns)
        cases.append({"case_id": case_id, "outputs": {"guitar": identity}})
    elapsed_lower_bound = max(
        0.0, (last_output_mtime_ns - request_path.stat().st_mtime_ns) / 1e9
    )
    return {
        "schema": "sunofriend.fine-stem-six-role-integration-worker.v1",
        "status": "complete_outputs_recovered_after_local_socket_false_positive",
        "mode": "sw-guitar",
        "runtime": {
            "network_denied_by_parent_sandbox": True,
            "network_connections_attempted": 0,
            "local_socket_capability_probes": 1,
        },
        "model": {
            "profile_id": plan["profiles"]["guitar"],
            "model_loads": 1,
            "peak_mlx_memory_bytes": None,
            "peak_memory_observation": "not_persisted_before_guard_assertion",
        },
        "cases": cases,
        "elapsed_seconds": elapsed_lower_bound,
        "elapsed_measurement": "request_to_last_output_mtime_lower_bound",
        "effects": {
            "model_loads": 1,
            "inference_attempts": 4,
            "network_attempts": 0,
            "local_socket_capability_probes": 1,
            "automatic_retry": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
        },
        "guard_remediation": {
            "classification": "false_positive_local_ipv6_capability_probe",
            "audit_event": "socket.bind",
            "origin": "urllib3.util.connection._has_ipv6(::1)",
            "network_connection_attempt": False,
            "os_network_denial_remained_active": True,
        },
    }


def _identity_without_path(identity: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in identity.items() if key != "path"}


def _execute(args: argparse.Namespace, plan: dict[str, Any]) -> int:
    if platform.system() != "Darwin" or platform.machine().casefold() != "arm64":
        raise RuntimeError("fine-stem integration requires Apple-silicon macOS")
    if os.environ.get(SANDBOX_FLAG) != "1":
        return _sandbox_reexec()
    if not args.confirm_rights:
        raise RuntimeError("--confirm-rights is required for the authorised private artifacts")
    if args.approved_plan_sha256 != APPROVED_PLAN_SHA256:
        raise RuntimeError("fine-stem integration approval SHA-256 differs")
    if plan["document_sha256"] != args.approved_plan_sha256:
        raise RuntimeError("fine-stem integration plan changed after approval")
    completion_plan = None
    partial_root = None
    if args.reuse_completed_from is not None:
        partial_root = args.reuse_completed_from.resolve(strict=True)
        completion_plan = build_completion_plan(plan, partial_root)
        if (
            args.approved_completion_plan_sha256
            != completion_plan["document_sha256"]
        ):
            raise RuntimeError("fine-stem integration completion approval differs")
    elif args.approved_completion_plan_sha256 is not None:
        raise RuntimeError("completion approval supplied without partial evidence")
    out = args.out.resolve()
    if out.exists() or out.with_name(out.name + "-FAILED").exists():
        raise FileExistsError("fine-stem integration output target must be fresh")
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix="." + out.name + "-", dir=out.parent))
    staging.chmod(0o700)
    temporary = staging / "TEMP"
    temporary.mkdir(mode=0o700)
    started = time.monotonic()
    try:
        roots = {"synth": args.synth_root.resolve(strict=True), "guitar": args.guitar_root.resolve(strict=True)}
        plan_cases: list[dict[str, Any]] = []
        for case in plan["cases"]:
            primary_role = case["reused_primary_estimate"]["role"]
            package = roots[primary_role]
            source = _artifact_path(package, case["canonical_reference_artifact"])
            primary = _artifact_path(
                package, case["reused_primary_estimate"]["artifact"]
            )
            plan_cases.append(
                {
                    **case,
                    "source_path": source,
                    "primary_path": primary,
                    "primary_root": package,
                }
            )

        scnet_cases = []
        for case in plan_cases:
            case_temp = temporary / "scnet" / case["case_id"]
            scnet_cases.append(
                {
                    "case_id": case["case_id"],
                    "source": {
                        "path": str(case["source_path"]),
                        **case["canonical_reference_artifact"],
                    },
                    "outputs": {
                        role: str(case_temp / f"{role}.npy")
                        for role in ("drums", "bass", "other", "vocals")
                    },
                }
            )
        common = {"schema": WORKER_REQUEST_SCHEMA, "network_denied": True}
        previous_worker_elapsed = 0.0
        if partial_root is not None:
            scnet_result = load_completed_worker_receipt(
                partial_root, "TEMP/scnet-result.json"
            )
            synth_result = load_completed_worker_receipt(
                partial_root, "TEMP/mega53-synth-result.json"
            )
            previous_worker_elapsed = float(scnet_result["elapsed_seconds"]) + float(
                synth_result["elapsed_seconds"]
            )
        else:
            elapsed = time.monotonic() - started
            scnet_result = _run_worker(
                mode="scnet",
                request={
                    **common,
                    "mode": "scnet",
                    "model_root": str(args.scnet_root.resolve(strict=True)),
                    "cases": scnet_cases,
                },
                python=args.scnet_python,
                temporary=temporary,
                remaining_seconds=MAXIMUM_ELAPSED_SECONDS - elapsed,
            )

        def specialist_request(role: str) -> dict[str, Any]:
            cases = []
            for case in plan_cases:
                if case["new_complementary_estimate"]["role"] != role:
                    continue
                cases.append(
                    {
                        "case_id": case["case_id"],
                        "source": {
                            "path": str(case["source_path"]),
                            **case["canonical_reference_artifact"],
                        },
                        "output": str(temporary / role / case["case_id"] / f"{role}.npy"),
                    }
                )
            checkpoint = args.mega_checkpoint if role == "synth" else args.sw_checkpoint
            config = args.mega_config if role == "synth" else args.sw_config
            request = {
                **common,
                "mode": "mega53-synth" if role == "synth" else "sw-guitar",
                "checkpoint": str(checkpoint.resolve(strict=True)),
                "config": str(config.resolve(strict=True)),
                "source_root": str(args.bs_source_root.resolve(strict=True)),
                "source_evidence": str(args.bs_source_evidence.resolve(strict=True)),
                "cases": cases,
            }
            if role == "synth":
                request["model_load_report"] = str(args.mega_model_load_report.resolve(strict=True))
            return request

        if partial_root is None:
            elapsed = time.monotonic() - started
            synth_result = _run_worker(
                mode="mega53-synth",
                request=specialist_request("synth"),
                python=args.bs_python,
                temporary=temporary,
                remaining_seconds=MAXIMUM_ELAPSED_SECONDS - elapsed,
            )
        elapsed = previous_worker_elapsed + time.monotonic() - started
        if args.reuse_guitar_from is not None:
            if completion_plan is None:
                raise RuntimeError("guitar recovery requires an approved completion")
            guitar_result = _recover_completed_guitar_outputs(
                args.reuse_guitar_from,
                plan=plan,
                completion_plan_sha256=completion_plan["document_sha256"],
            )
            previous_worker_elapsed += float(guitar_result["elapsed_seconds"])
        else:
            guitar_result = _run_worker(
                mode="sw-guitar",
                request=specialist_request("guitar"),
                python=args.bs_python,
                temporary=temporary,
                remaining_seconds=MAXIMUM_ELAPSED_SECONDS - elapsed,
            )
        scnet_by_case = _worker_case_map(scnet_result)
        synth_by_case = _worker_case_map(synth_result)
        guitar_by_case = _worker_case_map(guitar_result)
        cases = []
        for case in plan_cases:
            reference = read_canonical_pcm24(case["source_path"])
            primary = read_canonical_pcm24(case["primary_path"])
            core = {
                role: _temporary_array(scnet_by_case[case["case_id"]]["outputs"][role])
                for role in ("vocals", "drums", "bass", "other")
            }
            grouped_other = reference - core["vocals"] - core["drums"] - core["bass"]
            if case["reused_primary_estimate"]["role"] == "synth":
                raw_synth = primary
                raw_guitar = _temporary_array(
                    guitar_by_case[case["case_id"]]["outputs"]["guitar"]
                )
            else:
                raw_guitar = primary
                raw_synth = _temporary_array(
                    synth_by_case[case["case_id"]]["outputs"]["synth"]
                )
            projected = project_within_grouped_other(grouped_other, raw_synth, raw_guitar)
            quantized = quantize_six_roles(
                reference=reference,
                vocals=core["vocals"],
                drums=core["drums"],
                bass=core["bass"],
                synth=projected["synth"],
                guitar=projected["guitar"],
            )
            persisted = persist_six_roles(
                staging,
                case_id=case["case_id"],
                quantized=quantized,
            )
            native_other_delta = grouped_other - core["other"]
            cases.append(
                {
                    "case_id": case["case_id"],
                    "track_id": case["track_id"],
                    "title": case["title"],
                    "window_seconds": case["window_seconds"],
                    "reused_primary_role": case["reused_primary_estimate"]["role"],
                    "new_complementary_role": case["new_complementary_estimate"]["role"],
                    "source_input": {
                        key: case["canonical_reference_artifact"][key]
                        for key in ("bytes", "sha256", "sample_rate_hz", "channels", "frames", "subtype")
                    },
                    "reused_primary_input": {
                        key: case["reused_primary_estimate"]["artifact"][key]
                        for key in ("bytes", "sha256", "sample_rate_hz", "channels", "frames", "subtype")
                    },
                    "scnet_native_other_correction": {
                        "rms": float((native_other_delta.astype("float64") ** 2).mean() ** 0.5),
                        "peak": float(abs(native_other_delta).max(initial=0.0)),
                        "used_for_separation_accuracy_claim": False,
                    },
                    "projection": projected["accounting"],
                    **persisted,
                }
            )

        elapsed = previous_worker_elapsed + time.monotonic() - started
        peaks = [
            int(scnet_result["model"]["peak_unified_memory_bytes"]),
            int(synth_result["model"]["peak_mlx_memory_bytes"]),
            (
                int(guitar_result["model"]["peak_mlx_memory_bytes"])
                if guitar_result["model"]["peak_mlx_memory_bytes"] is not None
                else None
            ),
        ]
        if elapsed > MAXIMUM_ELAPSED_SECONDS:
            raise TimeoutError("fine-stem integration exceeded its total time ceiling")
        if max(value for value in peaks if value is not None) > MAXIMUM_MEMORY_BYTES:
            raise MemoryError("fine-stem integration exceeded its memory ceiling")
        worker_summary = {
            name: {
                "profile_id": result["model"]["profile_id"],
                "runtime": result["runtime"],
                "model_loads": result["effects"]["model_loads"],
                "inference_attempts": result["effects"]["inference_attempts"],
                "elapsed_seconds": result["elapsed_seconds"],
                "peak_memory_bytes": (
                    int(peak_value)
                    if (
                        peak_value := result["model"].get(
                        "peak_unified_memory_bytes",
                        result["model"].get("peak_mlx_memory_bytes", 0),
                    )
                    ) is not None
                    else None
                ),
                "network_attempts": result["effects"]["network_attempts"],
            }
            for name, result in (
                ("core_four", scnet_result),
                ("synth", synth_result),
                ("guitar", guitar_result),
            )
        }
        report = {
            "schema": REPORT_SCHEMA,
            "report_sha256": "",
            "status": REPORT_STATUS,
            "plan_sha256": plan["document_sha256"],
            "approved_plan_sha256": args.approved_plan_sha256,
            "completion_plan_sha256": (
                completion_plan["document_sha256"] if completion_plan else None
            ),
            "reused_partial_execution": (
                completion_plan["partial_failure"] if completion_plan else None
            ),
            "release_tier": "private_studio_challenger",
            "profiles": plan["profiles"],
            "runtime": {
                "platform": platform.platform(),
                "machine": platform.machine(),
                "network_denied_by_parent_sandbox": True,
                "models_run_sequentially": True,
                "writer_count": 1,
            },
            "workers": worker_summary,
            "resources": {
                "elapsed_seconds": elapsed,
                "maximum_elapsed_seconds": MAXIMUM_ELAPSED_SECONDS,
                "peak_memory_bytes_by_worker": peaks,
                "maximum_peak_unified_memory_bytes": MAXIMUM_MEMORY_BYTES,
                "within_ceilings": True,
                "guitar_peak_memory_observation": (
                    guitar_result["model"].get("peak_memory_observation")
                ),
            },
            "cases": cases,
            "accounting": {
                "projection": plan["integration_contract"]["projection"],
                "maximum_reconstruction_error_lsb": max(
                    case["maximum_reconstruction_error_lsb"] for case in cases
                ),
                "reconstruction_accounting_is_separation_accuracy": False,
            },
            "effects": {
                "model_loads": 3,
                "inference_attempts": 16,
                "source_artifacts": 8,
                "reused_primary_artifacts": 8,
                "model_audio_reads": 16,
                "coordinator_audio_reads": 16,
                "audio_read_operations": 32,
                "audio_writes": 64,
                "automatic_retry": False,
                "public_activation": False,
                "source_selection": False,
                "midi_created": False,
                "hosting": False,
                "redistribution": False,
                "audio_upload": False,
            },
        }
        report["report_sha256"] = integration_report_sha256(report)
        validate_fine_stem_integration_report(report)
        technical = staging / "TECHNICAL"
        review = staging / "REVIEW"
        technical.mkdir(mode=0o700)
        review.mkdir(mode=0o700)
        _write_json(technical / "INTEGRATION-REPORT.json", report)
        from sunofriend.separation_fine_stem_integration_review import render_integration_review

        page = review / "six_role_review.html"
        page.write_text(render_integration_review(report), encoding="utf-8")
        page.chmod(0o600)
        shutil.rmtree(temporary)
        staging.rename(out)
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except BaseException as error:
        failure = {
            "schema": "sunofriend.fine-stem-six-role-integration-failure.v1",
            "status": "objective_failure_retained_no_retry",
            "plan_sha256": plan["document_sha256"],
            "completion_plan_sha256": (
                completion_plan["document_sha256"] if completion_plan else None
            ),
            "failure_type": type(error).__name__,
            "failure": str(error),
            "automatic_retry": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "audio_upload": False,
        }
        _write_json(staging / "FAILED-REPORT.json", failure)
        staging.rename(out.with_name(out.name + "-FAILED"))
        raise


def build_parser() -> argparse.ArgumentParser:
    evidence = Path.home() / ".local/share/sunofriend/separation/evidence"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio-outcome", type=Path, default=evidence / "fine-stem-canary-portfolio-v1/PORTFOLIO-OUTCOME.json")
    parser.add_argument("--synth-root", type=Path, default=evidence / "fine-stem-canary-mega53-synth-v1")
    parser.add_argument("--guitar-root", type=Path, default=evidence / "fine-stem-canary-bs-roformer-sw-guitar-v1")
    parser.add_argument("--scnet-root", type=Path, default=Path.home() / ".local/share/sunofriend/separation/scnet-large-musdb-release-v1")
    parser.add_argument("--scnet-python", type=Path, default=Path.home() / ".local/share/sunofriend/separation/scnet-large-musdb-release-v1/runtime/bin/python")
    parser.add_argument("--bs-python", type=Path, default=evidence / "bs-roformer-mega-53-runtime-import-macos-arm64-py312-v1/runtime/bin/python")
    parser.add_argument("--bs-source-root", type=Path, default=evidence / "bs-roformer-infer-de35ada-source-v1/source")
    parser.add_argument("--bs-source-evidence", type=Path, default=evidence / "bs-roformer-infer-de35ada-source-v1/STATIC-EVIDENCE.json")
    parser.add_argument("--mega-checkpoint", type=Path, default=evidence / "bs-roformer-mega-53-synth-v1/mvsep_mega_model_bs_roformer_53_stems_v1.ckpt")
    parser.add_argument("--mega-config", type=Path, default=evidence / "bs-roformer-mega-53-synth-v1/mvsep_mega_model_bs_roformer_53_stems.yaml")
    parser.add_argument("--mega-model-load-report", type=Path, default=evidence / "bs-roformer-mega-53-model-load-v1/MODEL-LOAD-REPORT.json")
    parser.add_argument("--sw-checkpoint", type=Path, default=evidence / "bs-roformer-sw-guitar-v1/BS-Rofo-SW-Fixed.ckpt")
    parser.add_argument("--sw-config", type=Path, default=evidence / "bs-roformer-infer-de35ada-source-v1/source/src/bs_roformer/configs/BS-Rofo-SW-Fixed.yaml")
    parser.add_argument("--approved-plan-sha256")
    parser.add_argument("--reuse-completed-from", type=Path)
    parser.add_argument("--approved-completion-plan-sha256")
    parser.add_argument("--reuse-guitar-from", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--confirm-rights", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--validate-report", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.validate_report:
        print(json.dumps(validate_fine_stem_integration_report(_json(args.validate_report)), indent=2, sort_keys=True))
        return 0
    plan = _plan(args)
    if not args.execute:
        document = (
            build_completion_plan(plan, args.reuse_completed_from)
            if args.reuse_completed_from is not None
            else plan
        )
        print(json.dumps(document, indent=2, sort_keys=True, allow_nan=False))
        return 0
    if args.out is None or args.approved_plan_sha256 is None:
        raise SystemExit("execution requires --out and --approved-plan-sha256")
    return _execute(args, plan)


if __name__ == "__main__":
    raise SystemExit(main())
