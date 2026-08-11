#!/usr/bin/env python3
"""Preflight or execute one exact private full-song six-role canary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_full_song_execution_contract import (  # noqa: E402
    FAILURE_SCHEMA,
    REPORT_SCHEMA,
    REPORT_STATUS,
    WORKER_REQUEST_SCHEMA,
    WORKER_RESULT_SCHEMA,
    build_execution_request,
    full_song_forward_budget,
    mega53_chunk_starts,
    report_sha256,
    scnet_forward_calls,
    sw_forward_calls,
    validate_full_song_report,
)
from sunofriend.separation_fine_stem_full_song_plan_contract import (  # noqa: E402
    validate_fine_stem_full_song_plan,
)


SANDBOX_FLAG = "SUNOFRIEND_FULL_SONG_SIX_ROLE_NETWORK_SANDBOX"
DEFAULT_PLAN = (
    Path.home()
    / ".local/share/sunofriend/separation/evidence"
    / "fine-stem-full-song-six-role-plan-v1/FULL-SONG-SIX-ROLE-PLAN.json"
)
DEFAULT_OUT = (
    Path.home()
    / ".local/share/sunofriend/separation/evidence"
    / "fine-stem-full-song-six-role-canary-v1"
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("full-song six-role JSON must be an object")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


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


def _canonicalize(
    source: Path,
    destination: Path,
    *,
    ffmpeg: Path,
    remaining_seconds: float,
) -> None:
    if remaining_seconds <= 0:
        raise TimeoutError("full-song total time authority is exhausted")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    completed = subprocess.run(
        [
            str(ffmpeg),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-protocol_whitelist",
            "file",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-vn",
            "-sn",
            "-dn",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "pcm_s24le",
            "-fflags",
            "+bitexact",
            "-flags:a",
            "+bitexact",
            "-metadata",
            "encoder=",
            "-write_bext",
            "0",
            "-rf64",
            "auto",
            "-f",
            "wav",
            str(destination),
        ],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=max(1.0, min(1800.0, remaining_seconds)),
        env={**os.environ, "LANG": "C", "LC_ALL": "C"},
    )
    if completed.returncode:
        raise RuntimeError(
            f"full-song canonical decode failed: {completed.stderr[:2000]}"
        )
    destination.chmod(0o600)


def _canonical_identity(path: Path, *, expected_frames: int) -> dict[str, Any]:
    from sunofriend.separation_demucs_mlx_worker import read_canonical_source

    value = read_canonical_source(path, np=_numpy())
    if value.shape != (expected_frames, 2):
        raise RuntimeError("full-song canonical clock differs from approved plan")
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
        "sample_rate_hz": 44_100,
        "channels": 2,
        "frames": expected_frames,
        "subtype": "PCM_24",
    }


def _numpy() -> Any:
    import numpy as np

    return np


def _runtime_python(path: Path) -> Path:
    value = path.expanduser().absolute()
    if not value.is_file():
        raise FileNotFoundError(f"verified runtime Python is missing: {value}")
    return value


def _run_worker(
    *,
    mode: str,
    request: Mapping[str, Any],
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
            "PIP_NO_INDEX": "1",
            "NO_PROXY": "*",
            "no_proxy": "*",
        }
    )
    if mode != "scnet":
        source_package = Path(request["source_root"]).resolve(strict=True) / "src"
        if not (source_package / "bs_roformer").is_dir():
            raise FileNotFoundError("verified BS-RoFormer source package is missing")
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(ROOT / "src"), str(source_package))
        )
    command = [
        str(_runtime_python(python)),
        "-m",
        "sunofriend.separation_fine_stem_full_song_execution_worker",
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
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=max(1.0, remaining_seconds),
    )
    if completed.returncode:
        raise RuntimeError(
            f"{mode} full-song worker failed without retry: "
            + (completed.stderr.strip() or completed.stdout.strip())
        )
    result = _json(result_path)
    if (
        result.get("schema") != WORKER_RESULT_SCHEMA
        or result.get("mode") != mode
        or result.get("effects", {}).get("model_loads") != 1
        or result.get("effects", {}).get("profile_inference_attempts") != 3
        or result.get("effects", {}).get("network_attempts") != 0
    ):
        raise RuntimeError("full-song worker receipt differs")
    return result


def _case_map(result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    cases = result.get("cases", [])
    mapped = {case["track_id"]: case for case in cases}
    if len(mapped) != 3 or len(cases) != 3:
        raise RuntimeError("full-song worker case identities differ")
    return mapped


def _temporary_array(identity: Mapping[str, Any], *, frames: int) -> Any:
    np = _numpy()
    path = Path(identity["path"]).resolve(strict=True)
    if (
        path.stat().st_size != identity["bytes"]
        or _file_sha256(path) != identity["sha256"]
    ):
        raise RuntimeError("full-song temporary estimate identity differs")
    with path.open("rb") as handle:
        value = np.load(handle, allow_pickle=False)
    if (
        value.shape != (frames, 2)
        or value.dtype != np.float32
        or not np.isfinite(value).all()
    ):
        raise RuntimeError("full-song temporary estimate geometry differs")
    return value.astype(np.float64)


def _worker_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    model = result["model"]
    peak = model.get("peak_unified_memory_bytes", model.get("peak_mlx_memory_bytes"))
    summary = {
        "profile_id": model["profile_id"],
        "runtime": result["runtime"],
        "model_loads": 1,
        "profile_inference_attempts": 3,
        "internal_forward_calls": model["forward_calls"],
        "case_elapsed_seconds": {
            case["track_id"]: case["elapsed_seconds"] for case in result["cases"]
        },
        "elapsed_seconds": result["elapsed_seconds"],
        "peak_memory_bytes": int(peak),
        "network_attempts": 0,
    }
    if "packages" in model:
        summary["runtime_packages"] = model["packages"]
        summary["model_receipt"] = model["model_receipt"]
    else:
        summary["model_load_evidence"] = model["model"]
        summary["execution_guard"] = model["guard"]
    return summary


def _execute(args: argparse.Namespace, plan: dict[str, Any]) -> int:
    from sunofriend.separation_demucs_mlx_worker import read_canonical_source
    from sunofriend.separation_fine_stem_integration_audio import (
        persist_six_roles,
        project_within_grouped_other,
        quantize_six_roles,
    )

    if platform.system() != "Darwin" or platform.machine().casefold() != "arm64":
        raise RuntimeError("full-song six-role canary requires Apple-silicon macOS")
    if os.environ.get(SANDBOX_FLAG) != "1":
        return _sandbox_reexec()
    if not args.confirm_rights:
        raise RuntimeError(
            "--confirm-rights is required for the three approved sources"
        )
    if args.approved_plan_sha256 != plan["document_sha256"]:
        raise RuntimeError("full-song execution approval SHA-256 differs")
    if plan["next_approval"]["received"] is not False:
        raise RuntimeError("immutable plan approval state unexpectedly changed")
    out = args.out.expanduser().resolve()
    failed = out.with_name(out.name + "-FAILED")
    if out.exists() or failed.exists():
        raise FileExistsError("full-song output target must be fresh")
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix=f".{out.name}-", dir=out.parent))
    staging.chmod(0o700)
    temporary = staging / "TEMP"
    temporary.mkdir(mode=0o700)
    started = time.monotonic()
    ceiling = float(plan["execution_contract"]["maximum_total_elapsed_seconds"])
    source_before: dict[str, str] = {}
    try:
        ffmpeg = Path(shutil.which(args.ffmpeg) or "")
        if not ffmpeg.is_file():
            raise FileNotFoundError("ffmpeg is required for canonicalisation")
        planned_cases = []
        for case in plan["cases"]:
            canonical_started = time.monotonic()
            planned = case["full_song_source"]
            source = Path(planned["absolute_path"]).resolve(strict=True)
            if not source.is_file() or source.stat().st_size != planned["bytes"]:
                raise RuntimeError("approved full-song source metadata differs")
            digest = _file_sha256(source)
            if digest != planned["sha256"]:
                raise RuntimeError("approved full-song source hash differs")
            source_before[case["track_id"]] = digest
            canonical = temporary / "canonical" / case["track_id"] / "reference.wav"
            _canonicalize(
                source,
                canonical,
                ffmpeg=ffmpeg,
                remaining_seconds=ceiling - (time.monotonic() - started),
            )
            identity = _canonical_identity(
                canonical,
                expected_frames=int(planned["expected_canonical_frames"]),
            )
            planned_cases.append(
                {
                    **case,
                    "source_path": source,
                    "canonical": identity,
                    "canonical_elapsed_seconds": time.monotonic() - canonical_started,
                }
            )
            if time.monotonic() - started > ceiling:
                raise TimeoutError("full-song canonicalisation exceeded total ceiling")

        common = {"schema": WORKER_REQUEST_SCHEMA, "network_denied": True}
        scnet_request = {
            **common,
            "mode": "scnet",
            "model_root": str(args.scnet_root.resolve(strict=True)),
            "expected_forward_calls": sum(
                scnet_forward_calls(case["canonical"]["frames"])
                for case in planned_cases
            ),
            "cases": [
                {
                    "track_id": case["track_id"],
                    "source": case["canonical"],
                    "outputs": {
                        role: str(
                            temporary / "scnet" / case["track_id"] / f"{role}.npy"
                        )
                        for role in ("vocals", "drums", "bass", "other")
                    },
                }
                for case in planned_cases
            ],
        }

        def specialist_request(mode: str) -> dict[str, Any]:
            synth = mode == "mega53-synth"
            request = {
                **common,
                "mode": mode,
                "checkpoint": str(
                    (args.mega_checkpoint if synth else args.sw_checkpoint).resolve(
                        strict=True
                    )
                ),
                "config": str(
                    (args.mega_config if synth else args.sw_config).resolve(strict=True)
                ),
                "source_root": str(args.bs_source_root.resolve(strict=True)),
                "source_evidence": str(args.bs_source_evidence.resolve(strict=True)),
                "expected_forward_calls": sum(
                    len(mega53_chunk_starts(case["canonical"]["frames"]))
                    if synth
                    else sw_forward_calls(case["canonical"]["frames"])
                    for case in planned_cases
                ),
                "cases": [
                    {
                        "track_id": case["track_id"],
                        "source": case["canonical"],
                        "output": str(
                            temporary
                            / ("synth" if synth else "guitar")
                            / case["track_id"]
                            / ("synth.npy" if synth else "guitar.npy")
                        ),
                    }
                    for case in planned_cases
                ],
            }
            if synth:
                request["model_load_report"] = str(
                    args.mega_model_load_report.resolve(strict=True)
                )
            return request

        scnet_result = _run_worker(
            mode="scnet",
            request=scnet_request,
            python=args.scnet_python,
            temporary=temporary,
            remaining_seconds=ceiling - (time.monotonic() - started),
        )
        synth_result = _run_worker(
            mode="mega53-synth",
            request=specialist_request("mega53-synth"),
            python=args.bs_python,
            temporary=temporary,
            remaining_seconds=ceiling - (time.monotonic() - started),
        )
        guitar_result = _run_worker(
            mode="sw-guitar",
            request=specialist_request("sw-guitar"),
            python=args.bs_python,
            temporary=temporary,
            remaining_seconds=ceiling - (time.monotonic() - started),
        )
        worker_results = {
            "core_four": scnet_result,
            "synth": synth_result,
            "guitar": guitar_result,
        }
        by_worker = {name: _case_map(value) for name, value in worker_results.items()}
        cases = []
        for case in planned_cases:
            case_started = time.monotonic()
            frames = int(case["canonical"]["frames"])
            if (
                _file_sha256(Path(case["canonical"]["path"]))
                != case["canonical"]["sha256"]
            ):
                raise RuntimeError(
                    "canonical full-song source changed during inference"
                )
            reference = read_canonical_source(
                Path(case["canonical"]["path"]), np=_numpy()
            ).astype(_numpy().float64)
            core = {
                role: _temporary_array(
                    by_worker["core_four"][case["track_id"]]["outputs"][role],
                    frames=frames,
                )
                for role in ("vocals", "drums", "bass", "other")
            }
            raw_synth = _temporary_array(
                by_worker["synth"][case["track_id"]]["outputs"]["synth"],
                frames=frames,
            )
            raw_guitar = _temporary_array(
                by_worker["guitar"][case["track_id"]]["outputs"]["guitar"],
                frames=frames,
            )
            grouped_other = reference - core["vocals"] - core["drums"] - core["bass"]
            projected = project_within_grouped_other(
                grouped_other, raw_synth, raw_guitar
            )
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
                case_id=case["track_id"],
                quantized=quantized,
            )
            coordinator_elapsed = time.monotonic() - case_started
            case_model_elapsed = sum(
                float(by_worker[name][case["track_id"]]["elapsed_seconds"])
                for name in by_worker
            )
            case_elapsed = (
                case["canonical_elapsed_seconds"]
                + case_model_elapsed
                + coordinator_elapsed
            )
            if (
                case_elapsed
                > plan["execution_contract"]["maximum_elapsed_seconds_per_song"]
            ):
                raise TimeoutError(
                    f"{case['track_id']} exceeded its 900-second ceiling"
                )
            native_other_delta = grouped_other - core["other"]
            cases.append(
                {
                    "track_id": case["track_id"],
                    "title": case["title"],
                    "rights_category": case["rights_category"],
                    "scored_target_roles": case["scored_target_roles"],
                    "unscored_target_roles": case["unscored_target_roles"],
                    "confirmed_present_targets": case["confirmed_present_targets"],
                    "source_input": {
                        "bytes": case["full_song_source"]["bytes"],
                        "sha256": case["full_song_source"]["sha256"],
                        "canonical": {
                            key: case["canonical"][key]
                            for key in (
                                "bytes",
                                "sha256",
                                "sample_rate_hz",
                                "channels",
                                "frames",
                                "subtype",
                            )
                        },
                    },
                    "profile_elapsed_seconds": {
                        name: by_worker[name][case["track_id"]]["elapsed_seconds"]
                        for name in by_worker
                    },
                    "canonical_elapsed_seconds": case["canonical_elapsed_seconds"],
                    "coordinator_elapsed_seconds": coordinator_elapsed,
                    "elapsed_seconds": case_elapsed,
                    "scnet_native_other_correction": {
                        "rms": float(
                            _numpy().sqrt(
                                _numpy().mean(_numpy().square(native_other_delta))
                            )
                        ),
                        "peak": float(
                            _numpy().max(_numpy().abs(native_other_delta), initial=0.0)
                        ),
                        "used_for_separation_accuracy_claim": False,
                    },
                    "projection": projected["accounting"],
                    **persisted,
                }
            )

        for case in planned_cases:
            if _file_sha256(case["source_path"]) != source_before[case["track_id"]]:
                raise RuntimeError("approved source changed during full-song execution")
        elapsed = time.monotonic() - started
        peaks_by_worker = {
            name: int(
                result["model"].get(
                    "peak_unified_memory_bytes",
                    result["model"].get("peak_mlx_memory_bytes"),
                )
            )
            for name, result in worker_results.items()
        }
        coordinator_peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        peak = max(*peaks_by_worker.values(), coordinator_peak)
        maximum_memory = int(
            plan["execution_contract"]["maximum_peak_unified_memory_bytes"]
        )
        if elapsed > ceiling:
            raise TimeoutError("full-song canary exceeded its total time ceiling")
        if peak > maximum_memory:
            raise MemoryError("full-song canary exceeded its unified-memory ceiling")
        report = {
            "schema": REPORT_SCHEMA,
            "report_sha256": "",
            "status": REPORT_STATUS,
            "plan_sha256": plan["document_sha256"],
            "approved_plan_sha256": args.approved_plan_sha256,
            "release_tier": "private_studio_challenger",
            "profiles": plan["profiles"],
            "forward_budget": full_song_forward_budget(plan),
            "runtime": {
                "platform": platform.platform(),
                "machine": platform.machine(),
                "network_denied_by_parent_sandbox": True,
                "models_run_sequentially": True,
                "writer_count": 1,
            },
            "workers": {
                name: _worker_summary(result) for name, result in worker_results.items()
            },
            "resources": {
                "elapsed_seconds": elapsed,
                "maximum_elapsed_seconds": ceiling,
                "maximum_elapsed_seconds_per_song": plan["execution_contract"][
                    "maximum_elapsed_seconds_per_song"
                ],
                "peak_memory_bytes_by_worker": peaks_by_worker,
                "coordinator_peak_resident_set_bytes": coordinator_peak,
                "peak_memory_bytes": peak,
                "maximum_peak_unified_memory_bytes": maximum_memory,
                "within_ceilings": True,
            },
            "cases": cases,
            "accounting": {
                "projection": plan["output_contract"]["projection"],
                "maximum_reconstruction_error_lsb": max(
                    case["maximum_reconstruction_error_lsb"] for case in cases
                ),
                "reconstruction_accounting_is_separation_accuracy": False,
            },
            "effects": {
                "model_loads": 3,
                "profile_inference_attempts": 9,
                "source_files": 3,
                "canonicalization_attempts": 3,
                "audio_writes": 24,
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
        report["report_sha256"] = report_sha256(report)
        validate_full_song_report(report, plan)
        _write_json(staging / "TECHNICAL/FULL-SONG-SIX-ROLE-REPORT.json", report)
        from sunofriend.separation_fine_stem_full_song_execution_review import (
            render_full_song_review,
        )

        page = staging / "REVIEW/full_song_six_role_review.html"
        page.parent.mkdir(mode=0o700)
        page.write_text(render_full_song_review(report, plan), encoding="utf-8")
        page.chmod(0o600)
        shutil.rmtree(temporary)
        staging.rename(out)
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except BaseException as error:
        failure = {
            "schema": FAILURE_SCHEMA,
            "status": "objective_failure_retained_no_retry",
            "plan_sha256": plan["document_sha256"],
            "approved_plan_sha256": args.approved_plan_sha256,
            "failure_type": type(error).__name__,
            "failure": str(error),
            "elapsed_seconds": time.monotonic() - started,
            "automatic_retry": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
        }
        _write_json(staging / "FAILED-REPORT.json", failure)
        staging.rename(failed)
        raise


def build_parser() -> argparse.ArgumentParser:
    evidence = Path.home() / ".local/share/sunofriend/separation/evidence"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument(
        "--scnet-root",
        type=Path,
        default=Path.home()
        / ".local/share/sunofriend/separation/scnet-large-musdb-release-v1",
    )
    parser.add_argument(
        "--scnet-python",
        type=Path,
        default=Path.home()
        / ".local/share/sunofriend/separation/scnet-large-musdb-release-v1/runtime/bin/python",
    )
    parser.add_argument(
        "--bs-python",
        type=Path,
        default=evidence
        / "bs-roformer-mega-53-runtime-import-macos-arm64-py312-v1/runtime/bin/python",
    )
    parser.add_argument(
        "--bs-source-root",
        type=Path,
        default=evidence / "bs-roformer-infer-de35ada-source-v1/source",
    )
    parser.add_argument(
        "--bs-source-evidence",
        type=Path,
        default=evidence / "bs-roformer-infer-de35ada-source-v1/STATIC-EVIDENCE.json",
    )
    parser.add_argument(
        "--mega-checkpoint",
        type=Path,
        default=evidence
        / "bs-roformer-mega-53-synth-v1/mvsep_mega_model_bs_roformer_53_stems_v1.ckpt",
    )
    parser.add_argument(
        "--mega-config",
        type=Path,
        default=evidence
        / "bs-roformer-mega-53-synth-v1/mvsep_mega_model_bs_roformer_53_stems.yaml",
    )
    parser.add_argument(
        "--mega-model-load-report",
        type=Path,
        default=evidence / "bs-roformer-mega-53-model-load-v1/MODEL-LOAD-REPORT.json",
    )
    parser.add_argument(
        "--sw-checkpoint",
        type=Path,
        default=evidence / "bs-roformer-sw-guitar-v1/BS-Rofo-SW-Fixed.ckpt",
    )
    parser.add_argument(
        "--sw-config",
        type=Path,
        default=evidence
        / "bs-roformer-infer-de35ada-source-v1/source/src/bs_roformer/configs/BS-Rofo-SW-Fixed.yaml",
    )
    parser.add_argument("--approved-plan-sha256")
    parser.add_argument("--confirm-rights", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--validate-report", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    plan = validate_fine_stem_full_song_plan(_json(args.plan))
    if args.validate_report:
        value = validate_full_song_report(_json(args.validate_report), plan)
        print(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))
        return 0
    if not args.execute:
        request = build_execution_request(
            plan, proposed_output=str(args.out.expanduser().resolve())
        )
        print(json.dumps(request, indent=2, sort_keys=True, allow_nan=False))
        return 0
    if args.approved_plan_sha256 is None:
        raise SystemExit("execution requires --approved-plan-sha256")
    return _execute(args, plan)


if __name__ == "__main__":
    raise SystemExit(main())
