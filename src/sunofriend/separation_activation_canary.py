"""Bounded activation-only execution for the blocked core-four profile."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from .audio_formats import file_sha256
from .separation_alpha import (
    _document_sha256,
    _run_worker,
    execute_separation,
    plan_separation,
    resolve_profile,
    separation_doctor,
)
from .separation_core_four_fixture import (
    DURATION_SECONDS,
    FIXTURE_POLICY_ID,
    ROLES,
    create_core_four_synthetic_fixture,
)
from .separation_profiles import (
    CORE_FOUR_FALLBACK_PROFILE_ID,
    CORE_FOUR_PROFILE_ID,
)
from .separation_scopes import FULL_STEM_SCOPE_ID


CANARY_SCHEMA = "sunofriend.core-four-activation-canary.v1"
BASELINE_REMEDIATION_EXHAUSTED = True
FALLBACK_REMEDIATION_EXHAUSTED = True
OBJECTIVE_FAILURE_ID = "demucs-mlx-fractional-segment-runtime-v1"
OBJECTIVE_FAILURE_SUMMARY = (
    "the pinned runtime repeats the config string '39/5' while calculating "
    "HTDemucs training length, including after the one permitted numeric "
    "apply-model remediation"
)
FALLBACK_FAILURE_ID = "demucs-infer-native-fraction-segment-contract-v1"
FALLBACK_FAILURE_SUMMARY = (
    "the installed single-model bag exposes its native segment as "
    "Fraction(39, 5), while the pinned fallback worker accepts only built-in "
    "int or float values; the one fallback remediation was already consumed "
    "by the exact runtime closure"
)


def plan_synthetic_canary(
    output: str | Path,
    *,
    model_root: str | Path | None = None,
) -> dict[str, Any]:
    destination = Path(output).expanduser().absolute()
    profile = resolve_profile(
        model_root=model_root,
        profile_id=CORE_FOUR_FALLBACK_PROFILE_ID,
    )
    doctor = separation_doctor(profile)
    return {
        "schema": CANARY_SCHEMA,
        "status": "blocked_objective_remediation_exhausted",
        "execution_enabled": False,
        "profile_id": CORE_FOUR_FALLBACK_PROFILE_ID,
        "profile_status_change": False,
        "public_access_change": False,
        "fixture_policy_id": FIXTURE_POLICY_ID,
        "duration_seconds": DURATION_SECONDS,
        "roles": list(ROLES),
        "output": str(destination),
        "output_fresh": not os.path.lexists(destination),
        "doctor_ready": doctor["ready"],
        "machine_class": doctor["checks"].get("machine_class"),
        "objective_failure": {
            "failure_id": FALLBACK_FAILURE_ID,
            "baseline_configurations": 1,
            "remediation_cycles": 1,
            "maximum_remediation_cycles": 1,
            "published_output": False,
            "human_listen_reached": False,
            "observed_native_segment_type": "Fraction",
            "observed_native_segment_repr": "Fraction(39, 5)",
            "summary": FALLBACK_FAILURE_SUMMARY,
            "next_action": "select a separately reviewed backend; do not retry this profile",
        },
        "failed_baseline": {
            "failure_id": OBJECTIVE_FAILURE_ID,
            "baseline_configurations": 1,
            "remediation_cycles": 1,
            "maximum_remediation_cycles": 1,
            "summary": OBJECTIVE_FAILURE_SUMMARY,
            "next_action": "qualify a separately approved fallback backend",
        },
        "effects_if_executed": {
            "network": [],
            "uploads": [],
            "installs": [],
            "writes": [],
            "profile_status_changes": [],
        },
        "execution_confirmation": None,
    }


def execute_synthetic_canary(
    output: str | Path,
    *,
    confirm_synthetic: bool,
    model_root: str | Path | None = None,
) -> dict[str, Any]:
    if FALLBACK_REMEDIATION_EXHAUSTED:
        raise RuntimeError(
            "fallback activation retries are disabled after the objective "
            "native-segment contract failure"
        )
    if confirm_synthetic is not True:
        raise PermissionError("synthetic canary requires --confirm-synthetic")
    destination = Path(output).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"activation canary output already exists: {destination}")
    profile = resolve_profile(
        model_root=model_root,
        profile_id=CORE_FOUR_FALLBACK_PROFILE_ID,
    )
    doctor = separation_doctor(profile)
    if not doctor["ready"]:
        raise RuntimeError("exact core-four installation is not ready")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".sunofriend-core-four-synthetic-",
        dir=destination.parent,
    ) as temporary:
        fixture = create_core_four_synthetic_fixture(Path(temporary) / "fixture")
        plan = plan_separation(
            fixture["source_path"],
            destination,
            rights_category="owned",
            scope_id=FULL_STEM_SCOPE_ID,
            profile=profile,
            activation_canary=True,
        )

        def activation_worker(
            worker_plan: Any, staging: Path
        ) -> Mapping[str, Any]:
            truth_root = staging / "GROUND-TRUTH"
            truth_root.mkdir(mode=0o700)
            truth: dict[str, Any] = {}
            for role in ROLES:
                source = Path(fixture["ground_truth_paths"][role])
                target = truth_root / f"{role}.wav"
                shutil.copy2(source, target)
                if file_sha256(source) != file_sha256(target):
                    raise ValueError("synthetic ground-truth copy changed")
                truth[role] = {
                    "path": str(target.relative_to(staging)),
                    "bytes": target.stat().st_size,
                    "sha256": file_sha256(target),
                }
            worker = dict(_run_worker(worker_plan, staging))
            worker["activation_ground_truth"] = {
                "fixture_schema": fixture["schema"],
                "fixture_policy_id": fixture["policy_id"],
                "fixture_document_sha256": fixture["document_sha256"],
                "all_roles_active": fixture["all_roles_active"],
                "roles": truth,
                "automatic_quality_threshold": None,
                "remediation_cycles": 0,
                "remediation": None,
                "failed_baseline_profile_id": CORE_FOUR_PROFILE_ID,
                "human_catastrophic_listen_complete": False,
                "mislabelled_corrupt_silent_or_mistimed": None,
            }
            (staging / "ACTIVATION-CANARY.txt").write_text(
                "Core-four activation evidence only.\n"
                "Listen to source, each ground-truth role, each estimate, and reconstruction.\n"
                "Record only catastrophic mislabelling, corruption, all-role silence, or gross timing.\n"
                "Do not assign a usefulness threshold and do not change profile status from this file.\n",
                encoding="utf-8",
            )
            return worker

        result = execute_separation(
            plan,
            confirm_rights=True,
            worker_runner=activation_worker,
        )
    technical = destination / "TECHNICAL/separation-report.json"
    published = json.loads(technical.read_text(encoding="utf-8"))
    if published.get("document_sha256") != _document_sha256(published):
        raise RuntimeError("activation canary report changed after publication")
    return {
        **result,
        "activation_canary": {
            "schema": CANARY_SCHEMA,
            "technical_passed": True,
            "remediation_cycles": 0,
            "profile_status_changed": False,
            "public_access_changed": False,
            "catastrophic_listen_complete": False,
            "synthetic_demo_passed": False,
            "pending": "one complete internal catastrophic listen",
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model-root")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-synthetic", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.execute:
            print(
                json.dumps(
                    plan_synthetic_canary(args.out, model_root=args.model_root),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        result = execute_synthetic_canary(
            args.out,
            confirm_synthetic=args.confirm_synthetic,
            model_root=args.model_root,
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"core-four activation canary: {exc}")
        return 2
    print(f"Complete technical canary: {result['root']}")
    print(f"Listen before marking the synthetic gate passed: {result['review_html']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
