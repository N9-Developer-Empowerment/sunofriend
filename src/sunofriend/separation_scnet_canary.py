"""Run one bounded copyright-safe synthetic SCNet inference canary."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any, Sequence
import wave

from .audio_formats import file_sha256
from .separation_core_four_fixture import (
    DURATION_SECONDS,
    FIXTURE_POLICY_ID,
    ROLES,
    create_core_four_synthetic_fixture,
)
from .separation_profiles import SCNET_RELEASE_PROFILE_ID, separation_profile
from .separation_scnet_worker import MAXIMUM_SECONDS_PER_AUDIO_MINUTE


CANARY_SCHEMA = "sunofriend.scnet-synthetic-canary.v1"
REFERENCE_DIAGNOSTICS_SCHEMA = "sunofriend.scnet-reference-diagnostics.v1"
DEFAULT_PROFILE_ROOT = (
    Path.home()
    / ".local/share/sunofriend/separation"
    / SCNET_RELEASE_PROFILE_ID
)


def plan_scnet_canary(
    output: str | Path,
    *,
    model_root: str | Path | None = None,
) -> dict[str, Any]:
    destination = Path(output).expanduser().absolute()
    root = (
        Path(model_root).expanduser().absolute()
        if model_root is not None
        else DEFAULT_PROFILE_ROOT
    )
    spec = separation_profile(SCNET_RELEASE_PROFILE_ID)
    return {
        "schema": CANARY_SCHEMA,
        "status": "ready" if root.is_dir() and not os.path.lexists(destination) else "blocked",
        "execution_enabled": True,
        "profile_id": spec.profile_id,
        "profile_status_before": spec.status,
        "profile_status_change": False,
        "public_access_change": False,
        "model_root": str(root),
        "model_root_present": root.is_dir(),
        "output": str(destination),
        "output_fresh": not os.path.lexists(destination),
        "fixture_policy_id": FIXTURE_POLICY_ID,
        "duration_seconds": DURATION_SECONDS,
        "roles": list(ROLES),
        "resource_ceiling": {
            "seconds_per_audio_minute": MAXIMUM_SECONDS_PER_AUDIO_MINUTE,
            "maximum_elapsed_seconds": (
                MAXIMUM_SECONDS_PER_AUDIO_MINUTE * DURATION_SECONDS / 60.0
            ),
            "peak_unified_memory_bytes": 12 * 1024**3,
        },
        "approvals": {
            "model_terms_approval_required": "already_recorded_by_setup",
            "checkpoint_use_approval_required": "already_recorded_by_setup",
            "synthetic_inference_confirmation_required": True,
            "personal_song_rights_confirmation_required": False,
        },
        "effects_if_executed": {
            "network": [],
            "uploads": [],
            "installs": [],
            "audio_sources": [
                "locally generated deterministic mathematical fixture"
            ],
            "writes": [str(destination)],
            "profile_status_changes": [],
        },
    }


def _reference_diagnostics(root: Path) -> dict[str, Any]:
    """Measure synthetic references without turning them into a quality gate."""

    import numpy as np

    from .separation_demucs_mlx_worker import decode_pcm24

    def read_audio(path: Path) -> Any:
        with wave.open(str(path), "rb") as reader:
            value = decode_pcm24(reader.readframes(reader.getnframes()), np=np)
        return value.astype(np.float64).reshape(-1)

    truth = {
        role: read_audio(root / "GROUND-TRUTH" / f"{role}.wav")
        for role in ROLES
    }
    estimates = {
        role: read_audio(root / "STEMS" / f"{role}.wav") for role in ROLES
    }
    levels: dict[str, dict[str, Any]] = {}
    correlations: dict[str, dict[str, Any]] = {}
    for estimate_role, estimate in estimates.items():
        levels[estimate_role] = {
            "rms": float(np.sqrt(np.mean(np.square(estimate)))),
            "peak": float(np.max(np.abs(estimate))),
            "active_above_one_pcm24_lsb": bool(
                np.any(np.abs(estimate) >= 1.0 / (1 << 23))
            ),
        }
        centered_estimate = estimate - estimate.mean()
        estimate_energy = float(np.dot(centered_estimate, centered_estimate))
        row: dict[str, Any] = {}
        for truth_role, reference in truth.items():
            centered_reference = reference - reference.mean()
            reference_energy = float(np.dot(centered_reference, centered_reference))
            denominator = math.sqrt(estimate_energy * reference_energy)
            row[truth_role] = (
                float(np.dot(centered_estimate, centered_reference) / denominator)
                if denominator > 0
                else None
            )
        correlations[estimate_role] = row
    return {
        "schema": REFERENCE_DIAGNOSTICS_SCHEMA,
        "roles": list(ROLES),
        "estimate_levels": levels,
        "pearson_correlation": {
            "rows": "persisted estimates",
            "columns": "synthetic ground truth",
            "matrix": correlations,
        },
        "admission_threshold": None,
        "automatic_role_or_model_winner": None,
        "interpretation": (
            "Diagnostics support human listening and known-limitations records; "
            "they do not block technically valid preview admission."
        ),
    }


def execute_scnet_canary(
    output: str | Path,
    *,
    confirm_synthetic: bool,
    model_root: str | Path | None = None,
) -> dict[str, Any]:
    if confirm_synthetic is not True:
        raise PermissionError("SCNet synthetic canary requires --confirm-synthetic")
    destination = Path(output).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"SCNet synthetic output already exists: {destination}")
    root = (
        Path(model_root).expanduser().absolute()
        if model_root is not None
        else DEFAULT_PROFILE_ROOT
    )
    runtime_python = root / "runtime/bin/python"
    if not root.is_dir() or not runtime_python.is_file():
        raise FileNotFoundError("installed SCNet profile or runtime is missing")
    installation = json.loads((root / "INSTALLATION.json").read_text(encoding="utf-8"))
    compatibility = json.loads((root / "COMPATIBILITY.json").read_text(encoding="utf-8"))
    if (
        installation.get("profile_id") != SCNET_RELEASE_PROFILE_ID
        or installation.get("model_terms_accepted") is not True
        or installation.get("checkpoint_use_accepted") is not True
        or compatibility.get("status") != "passed"
        or compatibility.get("compatibility", {}).get("remediation_cycles") != 1
    ):
        raise RuntimeError("installed SCNet approval or compatibility receipt differs")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=".sunofriend-scnet-canary-", dir=destination.parent
        )
    )
    work = temporary / "work"
    fixture_root = temporary / "fixture"
    work.mkdir(mode=0o700)
    started = time.perf_counter()
    try:
        fixture = create_core_four_synthetic_fixture(fixture_root)
        truth_root = work / "GROUND-TRUTH"
        truth_root.mkdir(mode=0o700)
        truth: dict[str, dict[str, Any]] = {}
        for role in ROLES:
            source = Path(fixture["ground_truth_paths"][role])
            target = truth_root / f"{role}.wav"
            shutil.copy2(source, target)
            if file_sha256(source) != file_sha256(target):
                raise ValueError("SCNet synthetic ground-truth copy changed")
            truth[role] = {
                "path": str(target.relative_to(work)),
                "bytes": target.stat().st_size,
                "sha256": file_sha256(target),
            }
        shutil.copy2(fixture["manifest"], work / "synthetic-fixture.json")

        repository_root = Path(__file__).resolve().parents[2]
        worker = repository_root / "src/sunofriend/separation_scnet_worker.py"
        result = work / "worker-result.json"
        command = [
            "/usr/bin/sandbox-exec",
            "-p",
            "(version 1)(deny network*)(allow default)",
            str(runtime_python),
            str(worker),
            "--source",
            fixture["source_path"],
            "--destination",
            str(work),
            "--result",
            str(result),
            "--model-root",
            str(root),
            "--network-denial-enforced",
        ]
        environment = dict(os.environ)
        source_path = str(repository_root / "src")
        environment.update(
            {
                "PYTHONPATH": source_path,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "NO_PROXY": "*",
                "no_proxy": "*",
                "PIP_NO_INDEX": "1",
            }
        )
        ceiling = MAXIMUM_SECONDS_PER_AUDIO_MINUTE * DURATION_SECONDS / 60.0
        completed = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=ceiling + 5.0,
            env=environment,
        )
        if completed.returncode:
            diagnostic = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(
                "SCNet synthetic worker failed with exit code "
                f"{completed.returncode}: {diagnostic[:4000] or 'no diagnostic'}"
            )
        worker_report = json.loads(result.read_text(encoding="utf-8"))
        if worker_report.get("profile_id") != SCNET_RELEASE_PROFILE_ID:
            raise ValueError("SCNet worker report profile differs")
        if worker_report.get("roles") != list(ROLES):
            raise ValueError("SCNet worker report roles differ")
        if worker_report.get("runtime", {}).get("network_used") is not False:
            raise ValueError("SCNet worker did not prove offline execution")
        if worker_report.get("resources", {}).get("within_runtime_ceiling") is not True:
            raise ValueError("SCNet worker exceeded the runtime ceiling")
        if worker_report.get("additive_accounting", {}).get("passed") is not True:
            raise ValueError("SCNet persisted reconstruction accounting failed")
        if set(worker_report.get("outputs", {})) != {
            "source_reference",
            "vocals",
            "drums",
            "bass",
            "other",
            "reconstruction_check",
        }:
            raise ValueError("SCNet persisted output contract differs")

        reference_diagnostics = _reference_diagnostics(work)
        (work / "REFERENCE-DIAGNOSTICS.json").write_text(
            json.dumps(
                reference_diagnostics,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )

        canary = {
            "schema": CANARY_SCHEMA,
            "status": "technical_pass_unreviewed",
            "profile_id": SCNET_RELEASE_PROFILE_ID,
            "fixture": {
                "schema": fixture["schema"],
                "policy_id": fixture["policy_id"],
                "document_sha256": fixture["document_sha256"],
                "source_kind": fixture["source_kind"],
                "all_roles_active": fixture["all_roles_active"],
                "ground_truth": truth,
            },
            "objective_gates": {
                "offline_execution": True,
                "exact_profile_identity": True,
                "exact_four_roles": True,
                "matching_clocks": True,
                "finite_bounded_audio": True,
                "reconstruction_accounting": True,
                "resource_ceiling": True,
            },
            "subjective_quality_gate": None,
            "reference_diagnostics": "REFERENCE-DIAGNOSTICS.json",
            "human_catastrophic_listen": {
                "complete": False,
                "mislabelled_corrupt_silent_or_grossly_mistimed": None,
                "minimum_usefulness_rating": None,
            },
            "profile_status_changed": False,
            "public_access_changed": False,
            "next_gate": "one complete internal catastrophic listen",
            "worker_report": "worker-result.json",
            "elapsed_seconds_including_fixture": time.perf_counter() - started,
        }
        (work / "CANARY.json").write_text(
            json.dumps(canary, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        (work / "START-HERE.txt").write_text(
            "SCNet copyright-safe synthetic canary\n\n"
            "Listen to SOURCE/source-reference.wav, all four STEMS files, all "
            "four GROUND-TRUTH files, and AUDIO/reconstruction-check.wav.\n"
            "Record only catastrophic mislabelling, corruption, silence across "
            "all roles, or gross timing at this gate.\n"
            "Musical usefulness may be poor or mixed and is not a preview veto.\n"
            "No audio or metadata was uploaded. No profile was activated.\n",
            encoding="utf-8",
        )
        work.rename(destination)
        shutil.rmtree(temporary, ignore_errors=True)
        return {**canary, "root": str(destination)}
    except BaseException:
        failed = Path(f"{destination}.failed.{os.getpid()}.evidence")
        if work.exists() and not os.path.lexists(failed):
            work.rename(failed)
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model-root")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-synthetic", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.execute:
        print(
            json.dumps(
                plan_scnet_canary(args.out, model_root=args.model_root),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    result = execute_scnet_canary(
        args.out,
        confirm_synthetic=args.confirm_synthetic,
        model_root=args.model_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CANARY_SCHEMA",
    "REFERENCE_DIAGNOSTICS_SCHEMA",
    "execute_scnet_canary",
    "main",
    "plan_scnet_canary",
]
