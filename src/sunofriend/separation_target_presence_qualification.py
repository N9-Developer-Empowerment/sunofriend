"""Compose exact reviewed target-present excerpts into one canary cohort."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable

from .separation_target_presence_review import (
    PRESENCE_MANIFEST_SCHEMA,
    PRESENCE_RESULT_SCHEMA,
    file_sha256,
    load_presence_manifest,
    presence_document_sha256,
    validate_presence_result,
)


QUALIFICATION_SCHEMA = "sunofriend.fine-stem-target-presence-qualification.v1"
QUALIFIED_PRESENCE_PACKAGE_NAME = "fine-stem-target-presence-qualified-v1"
TARGET_IDS = ("synth_keyboard", "guitar")
CASES_PER_TARGET = 4


def _load_review(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    package = root.resolve(strict=True)
    manifest = load_presence_manifest(package)
    result_path = package / "PRESENCE-RESULT.json"
    if not result_path.is_file():
        raise RuntimeError("qualified presence source result is missing")
    result = validate_presence_result(
        json.loads(result_path.read_text(encoding="utf-8")), manifest
    )
    if result["status"] != "presence_review_complete_no_model_inference":
        raise RuntimeError("qualified presence source review is incomplete")
    return manifest, result


def compose_qualified_presence_package(
    *, source_roots: Iterable[Path], out: Path
) -> dict[str, Any]:
    """Copy only exact target-present source excerpts into one immutable package."""

    roots = [root.resolve(strict=True) for root in source_roots]
    destination = out.resolve()
    if (
        destination.name != QUALIFIED_PRESENCE_PACKAGE_NAME
        or destination.exists()
        or len(roots) < 2
        or len(set(roots)) != len(roots)
    ):
        raise RuntimeError("fresh exact qualified presence package is required")

    reviews = [(root, *_load_review(root)) for root in roots]
    targets = reviews[0][1].get("targets")
    if set(targets or {}) != set(TARGET_IDS) or any(
        manifest.get("targets") != targets for _, manifest, _ in reviews[1:]
    ):
        raise RuntimeError("qualified presence target definitions differ")

    source_records = []
    selected: list[tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for root, manifest, result in reviews:
        by_id = {case["case_id"]: case for case in result["cases"]}
        source_records.append(
            {
                "package_name": root.name,
                "manifest_sha256": manifest["document_sha256"],
                "result_sha256": result["document_sha256"],
            }
        )
        for case in manifest["cases"]:
            decision = by_id[case["case_id"]]
            if decision["listened"] and decision["decision"] == "present":
                selected.append((root, manifest, case, decision))

    for target_id in TARGET_IDS:
        target_cases = [item for item in selected if item[2]["target_id"] == target_id]
        if len(target_cases) != CASES_PER_TARGET or len(
            {item[2]["track_id"] for item in target_cases}
        ) != CASES_PER_TARGET:
            raise RuntimeError(
                f"qualified presence needs exactly four song-disjoint {target_id} cases"
            )

    qualification: dict[str, Any] = {
        "schema": QUALIFICATION_SCHEMA,
        "document_sha256": "",
        "status": "qualified_source_presence_no_model_inference",
        "source_reviews": source_records,
        "rules": {
            "target_ids": list(TARGET_IDS),
            "cases_per_target": CASES_PER_TARGET,
            "decision_required": "present",
            "listening_required": True,
            "song_disjoint_within_target": True,
            "source_audio_identity_preserved": True,
            "provider_hints_carried_forward": False,
        },
        "effects": {
            "checkpoint_opened": False,
            "model_constructed": False,
            "inference_attempts": 0,
            "network_attempts": 0,
            "audio_uploaded": False,
            "source_selected": False,
            "midi_created": False,
        },
    }
    qualification["document_sha256"] = presence_document_sha256(qualification)

    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(
        tempfile.mkdtemp(prefix=".qualified-presence-", dir=destination.parent)
    )
    staging.chmod(0o700)
    manifest_cases: list[dict[str, Any]] = []
    result_cases: list[dict[str, Any]] = []
    try:
        for root, source_manifest, case, decision in selected:
            source_artifact = case["artifacts"]["source"]
            source = (root / source_artifact["relative_path"]).resolve(strict=True)
            if root not in source.parents or (
                source.stat().st_size != source_artifact["bytes"]
                or file_sha256(source) != source_artifact["sha256"]
            ):
                raise RuntimeError("qualified presence source audio identity differs")
            relative_path = f"CASES/{case['case_id']}/source.wav"
            copied = staging / relative_path
            copied.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(source, copied)
            copied.chmod(0o600)
            if (
                copied.stat().st_size != source_artifact["bytes"]
                or file_sha256(copied) != source_artifact["sha256"]
            ):
                raise RuntimeError("qualified presence copied audio identity differs")

            packaged_case = copy.deepcopy(case)
            packaged_case["artifacts"] = {
                "source": {**copy.deepcopy(source_artifact), "relative_path": relative_path},
                "hints": [],
            }
            matching_record = next(
                record
                for record in source_records
                if record["manifest_sha256"] == source_manifest["document_sha256"]
            )
            packaged_case["qualification_source"] = {
                "manifest_sha256": matching_record["manifest_sha256"],
                "result_sha256": matching_record["result_sha256"],
                "case_id": case["case_id"],
            }
            manifest_cases.append(packaged_case)
            result_cases.append(
                {
                    "case_id": case["case_id"],
                    "track_id": case["track_id"],
                    "target_id": case["target_id"],
                    "window_seconds": case["window_seconds"],
                    "played_items": ["source"],
                    "listened": True,
                    "decision": "present",
                    "notes": decision.get("notes", ""),
                    "inherited_exact_audio_review": True,
                }
            )

        manifest: dict[str, Any] = {
            "schema": PRESENCE_MANIFEST_SCHEMA,
            "document_sha256": "",
            "status": "source_presence_pending_no_model_inference",
            "plan_sha256": qualification["document_sha256"],
            "targets": copy.deepcopy(targets),
            "cases": manifest_cases,
            "input_count": len(manifest_cases),
            "qualification": copy.deepcopy(qualification),
            "effects": copy.deepcopy(qualification["effects"]),
        }
        manifest["document_sha256"] = presence_document_sha256(manifest)
        result: dict[str, Any] = {
            "schema": PRESENCE_RESULT_SCHEMA,
            "document_sha256": "",
            "status": "presence_review_complete_no_model_inference",
            "manifest_sha256": manifest["document_sha256"],
            "cases": result_cases,
            "boundaries": {
                "provider_estimates_are_truth": False,
                "model_inference_started": False,
                "source_selected": False,
                "midi_created": False,
                "audio_uploaded": False,
                "telemetry": False,
            },
            "qualification_sha256": qualification["document_sha256"],
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        result = validate_presence_result(result, manifest)

        technical = staging / "TECHNICAL"
        technical.mkdir(mode=0o700)
        for name, value in (
            ("QUALIFICATION.json", qualification),
            ("PRESENCE-MANIFEST.json", manifest),
        ):
            path = technical / name
            path.write_text(
                json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            path.chmod(0o600)
        result_path = staging / "PRESENCE-RESULT.json"
        result_path.write_text(
            json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        result_path.chmod(0o600)
        staging.rename(destination)
        return manifest
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = [
    "CASES_PER_TARGET",
    "QUALIFICATION_SCHEMA",
    "QUALIFIED_PRESENCE_PACKAGE_NAME",
    "TARGET_IDS",
    "compose_qualified_presence_package",
]
