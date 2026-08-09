from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from sunofriend.separation_fine_stem_canary_contract import (
    build_fine_stem_canary_plan,
)
from sunofriend.separation_target_presence_plan import build_target_presence_plan
from sunofriend.separation_target_presence_qualification import (
    QUALIFIED_PRESENCE_PACKAGE_NAME,
    compose_qualified_presence_package,
)
from sunofriend.separation_target_presence_review import (
    PRESENCE_MANIFEST_SCHEMA,
    PRESENCE_RESULT_SCHEMA,
    load_presence_manifest,
    presence_document_sha256,
    validate_presence_result,
)


def _review_package(
    root: Path, cases: list[tuple[str, str]], *, absent_case: str | None = None
) -> None:
    manifest_cases = []
    result_cases = []
    for target_id, track_id in cases:
        case_id = f"{track_id}--{target_id}"
        path = root / "CASES" / case_id / "source.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (case_id + "-exact-audio").encode()
        path.write_bytes(content)
        artifact = {
            "relative_path": path.relative_to(root).as_posix(),
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "sample_rate_hz": 44_100,
            "channels": 2,
            "frames": 661_500,
            "subtype": "PCM_24",
        }
        manifest_cases.append(
            {
                "case_id": case_id,
                "track_id": track_id,
                "title": track_id.title(),
                "target_id": target_id,
                "window_seconds": [5, 20],
                "provider_estimates_are_truth": False,
                "artifacts": {"source": artifact, "hints": []},
            }
        )
        result_cases.append(
            {
                "case_id": case_id,
                "track_id": track_id,
                "target_id": target_id,
                "window_seconds": [5, 20],
                "played_items": ["source"],
                "listened": True,
                "decision": "absent" if case_id == absent_case else "present",
                "notes": "",
            }
        )
    manifest = {
        "schema": PRESENCE_MANIFEST_SCHEMA,
        "document_sha256": "",
        "status": "source_presence_pending_no_model_inference",
        "plan_sha256": "1" * 64,
        "targets": copy.deepcopy(build_target_presence_plan()["targets"]),
        "cases": manifest_cases,
        "input_count": len(cases),
        "effects": {"inference_attempts": 0},
    }
    manifest["document_sha256"] = presence_document_sha256(manifest)
    result = {
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
    }
    result = validate_presence_result(result, manifest)
    technical = root / "TECHNICAL"
    technical.mkdir()
    (technical / "PRESENCE-MANIFEST.json").write_text(json.dumps(manifest))
    (root / "PRESENCE-RESULT.json").write_text(json.dumps(result))


def test_composition_preserves_exact_audio_and_unblocks_both_canaries(
    tmp_path: Path,
) -> None:
    first = tmp_path / "review-first"
    second = tmp_path / "review-second"
    first_cases = [
        (target, f"{target}-track-{index}")
        for target in ("synth_keyboard", "guitar")
        for index in range(3)
    ]
    second_cases = [
        ("synth_keyboard", "synth-keyboard-track-3"),
        ("guitar", "guitar-track-3"),
    ]
    _review_package(first, first_cases)
    _review_package(second, second_cases)
    out = tmp_path / QUALIFIED_PRESENCE_PACKAGE_NAME

    manifest = compose_qualified_presence_package(
        source_roots=[first, second], out=out
    )
    result = validate_presence_result(
        json.loads((out / "PRESENCE-RESULT.json").read_text()),
        load_presence_manifest(out),
    )

    assert len(manifest["cases"]) == 8
    assert all(not case["artifacts"]["hints"] for case in manifest["cases"])
    assert result["status"] == "presence_review_complete_no_model_inference"
    assert manifest["qualification"]["effects"]["inference_attempts"] == 0
    for case in manifest["cases"]:
        artifact = case["artifacts"]["source"]
        copied = out / artifact["relative_path"]
        assert hashlib.sha256(copied.read_bytes()).hexdigest() == artifact["sha256"]
    for profile_id in (
        "bs-roformer-mega-53-synth-v1",
        "bs-roformer-sw-guitar-v1",
    ):
        plan = build_fine_stem_canary_plan(
            profile_id,
            manifest,
            result,
            checkpoint_available=True,
            config_available=True,
        )
        assert plan["status"] == "ready_for_bounded_private_execution"
        assert len(plan["cases"]) == 4


def test_composition_refuses_to_replace_an_absent_case_automatically(
    tmp_path: Path,
) -> None:
    first = tmp_path / "review-first"
    second = tmp_path / "review-second"
    _review_package(
        first,
        [
            (target, f"{target}-track-{index}")
            for target in ("synth_keyboard", "guitar")
            for index in range(3)
        ],
    )
    _review_package(
        second,
        [
            ("synth_keyboard", "synth-keyboard-track-3"),
            ("guitar", "guitar-track-3"),
        ],
        absent_case="guitar-track-3--guitar",
    )

    with pytest.raises(RuntimeError, match="four song-disjoint guitar"):
        compose_qualified_presence_package(
            source_roots=[first, second],
            out=tmp_path / QUALIFIED_PRESENCE_PACKAGE_NAME,
        )
