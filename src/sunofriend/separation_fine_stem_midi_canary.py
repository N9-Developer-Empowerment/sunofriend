"""Private, plan-bound fine-stem versus grouped-other MIDI comparison."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Callable, Mapping

import numpy as np

from .midi import MidiTrack, write_midi_file
from .separation_fine_stem_canary_audio import PCM24_MAX, PCM24_MIN, file_sha256
from .separation_fine_stem_integration_report import (
    validate_fine_stem_integration_report,
)
from .separation_fine_stem_midi_plan import (
    validate_fine_stem_midi_plan,
)
from .separation_midi_comparison import (
    TRANSCRIPTION_PARAMETERS,
    Renderer,
    Transcriber,
    artifact as _artifact,
    make_private as _make_private,
    match_preview_loudness,
    read_pcm24_integer as _read_pcm24_integer,
    regular_inside as _regular_inside,
    render_to_fixed_float as _render_to_fixed_float,
    validated_notes as _validated_notes,
    verify_audio_identity as _verify_audio_identity,
    write_notes as _write_notes,
    write_pcm24 as _write_pcm24,
)


CANARY_SCHEMA = "sunofriend.fine-stem-downstream-midi-canary.v1"
CANARY_STATUS = "complete_private_review_required_no_selection"


def canary_document_sha256(value: Mapping[str, Any]) -> str:
    payload = {
        key: item for key, item in value.items() if key != "document_sha256"
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _matched_preview_pair(
    candidate: np.ndarray, control: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    integers, matching = match_preview_loudness(
        {"candidate": candidate, "control": control}
    )
    status = matching["status"]
    if status == "not_applicable_one_or_more_silent":
        status = "not_applicable_one_or_both_silent"
    return integers["candidate"], integers["control"], {
        "policy": "pair RMS matched at or below -24 dBFS with -3.10 dBFS peak cap",
        "status": status,
        "pre_rms": [matching["pre_rms"][key] for key in ("candidate", "control")],
        "pre_peak": [matching["pre_peak"][key] for key in ("candidate", "control")],
        "gains": [matching["gains"][key] for key in ("candidate", "control")],
        "post_rms": [matching["post_rms"][key] for key in ("candidate", "control")],
    }


def _blind_order(case_id: str) -> list[str]:
    labels = ("candidate", "control")
    return sorted(
        labels,
        key=lambda label: hashlib.sha256(
            f"{case_id}|seed=0|{label}".encode()
        ).hexdigest(),
    )


def execute_fine_stem_midi_canary(
    plan_path: str | Path,
    integration_root: str | Path,
    *,
    out_dir: str | Path,
    expected_plan_sha256: str,
    transcribe: Transcriber,
    render: Renderer,
    network_observation: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    """Execute the one frozen canary and atomically publish private evidence."""

    plan_file = Path(plan_path).expanduser().resolve(strict=True)
    plan = validate_fine_stem_midi_plan(
        json.loads(plan_file.read_text(encoding="utf-8"))
    )
    if plan["document_sha256"] != expected_plan_sha256:
        raise ValueError("approved downstream-MIDI plan SHA-256 differs")
    root = Path(integration_root).expanduser().resolve(strict=True)
    integration_report = validate_fine_stem_integration_report(
        json.loads(
            (root / "TECHNICAL/INTEGRATION-REPORT.json").read_text(
                encoding="utf-8"
            )
        )
    )
    if integration_report["report_sha256"] != plan["integration_report_sha256"]:
        raise ValueError("downstream-MIDI integration report binding differs")

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"fresh downstream-MIDI output required: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=destination.parent)
    )
    staging.chmod(0o700)
    started = time.monotonic()
    source_identities: dict[str, dict[str, Any]] = {}
    attempts: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    try:
        for case in plan["cases"]:
            case_id = str(case["case_id"])
            case_root = staging / "CASES" / case_id
            case_root.mkdir(parents=True, mode=0o700)
            paths: dict[str, Path] = {}
            integers: dict[str, np.ndarray] = {}
            for identity in case["grouped_other_control_inputs"]:
                role = str(identity["role"])
                path = _verify_audio_identity(
                    root, identity, f"{case_id} {role} input"
                )
                paths[role] = path
                integers[role] = _read_pcm24_integer(path)
                source_identities[identity["relative_path"]] = {
                    "bytes": identity["bytes"],
                    "sha256": identity["sha256"],
                }
            candidate = _verify_audio_identity(
                root, case["candidate"], f"{case_id} candidate"
            )
            if candidate != paths[case["confirmed_present_target_role"]]:
                raise ValueError("fine-stem MIDI candidate/input binding differs")
            control_integer = integers["synth"] + integers["guitar"] + integers["other"]
            if (
                control_integer.min(initial=0) < PCM24_MIN
                or control_integer.max(initial=0) > PCM24_MAX
            ):
                raise RuntimeError("grouped-other control exceeds PCM24")
            control_path = case_root / "grouped-other-control.wav"
            control_artifact = _write_pcm24(control_path, control_integer)
            reread = _read_pcm24_integer(control_path)
            reconstruction_lsb = int(
                np.max(np.abs(reread - control_integer), initial=0)
            )
            if reconstruction_lsb != 0:
                raise RuntimeError("grouped-other control accounting changed")

            outputs: dict[str, dict[str, Any]] = {}
            preview_float: dict[str, np.ndarray] = {}
            for comparison_id, audio_path in (
                ("candidate", candidate),
                ("control", control_path),
            ):
                attempt_number = len(attempts) + 1
                attempt_started = time.monotonic()
                notes = _validated_notes(
                    transcribe(
                        str(audio_path),
                        kind=case["transcription"]["processing_kind"],
                        **TRANSCRIPTION_PARAMETERS,
                    )
                )
                notes_path = case_root / f"{comparison_id}.notes.json"
                _write_notes(notes_path, notes)
                midi_path = case_root / f"{comparison_id}.mid"
                write_midi_file(
                    midi_path,
                    [
                        MidiTrack(
                            f"{case['confirmed_present_target_role']} {comparison_id}",
                            int(case["transcription"]["general_midi_channel"]),
                            int(
                                case["transcription"][
                                    "general_midi_program_zero_based"
                                ]
                            ),
                            notes,
                        )
                    ],
                    bpm=float(case["metadata"]["bpm"]),
                )
                midi_path.chmod(0o600)
                raw_path = case_root / f".{comparison_id}.render.wav"
                preview_float[comparison_id], render_status = _render_to_fixed_float(
                    midi_path, raw_path, notes=notes, render=render
                )
                if raw_path.exists():
                    raw_path.unlink()
                elapsed = time.monotonic() - attempt_started
                attempt = {
                    "attempt_number": attempt_number,
                    "case_id": case_id,
                    "comparison_id": comparison_id,
                    "processing_kind": case["transcription"]["processing_kind"],
                    "parameters": dict(TRANSCRIPTION_PARAMETERS),
                    "note_count": len(notes),
                    "elapsed_seconds": elapsed,
                    "status": "complete",
                }
                attempts.append(attempt)
                outputs[comparison_id] = {
                    "notes": _artifact(notes_path, staging),
                    "midi": _artifact(midi_path, staging),
                    "note_count": len(notes),
                    "pitch_range": (
                        [min(note.pitch for note in notes), max(note.pitch for note in notes)]
                        if notes
                        else None
                    ),
                    "render_status": render_status,
                }

            candidate_i, control_i, matching = _matched_preview_pair(
                preview_float["candidate"], preview_float["control"]
            )
            for comparison_id, integer in (
                ("candidate", candidate_i),
                ("control", control_i),
            ):
                preview_path = case_root / f"{comparison_id}.preview.wav"
                preview_artifact = _write_pcm24(preview_path, integer)
                preview_artifact["relative_path"] = preview_path.relative_to(
                    staging
                ).as_posix()
                outputs[comparison_id]["preview"] = preview_artifact
            control_artifact["relative_path"] = control_path.relative_to(
                staging
            ).as_posix()
            cases.append(
                {
                    "case_id": case_id,
                    "track_id": case["track_id"],
                    "title": case["title"],
                    "confirmed_present_target_role": case[
                        "confirmed_present_target_role"
                    ],
                    "window_seconds": case["window_seconds"],
                    "metadata": case["metadata"],
                    "transcription": case["transcription"],
                    "grouped_other_control": {
                        "artifact": control_artifact,
                        "construction": case["grouped_other_control"][
                            "construction"
                        ],
                        "maximum_reconstruction_error_lsb": reconstruction_lsb,
                    },
                    "outputs": outputs,
                    "loudness_matching": matching,
                    "blind_order": _blind_order(case_id),
                }
            )

        if len(attempts) != 16 or [row["attempt_number"] for row in attempts] != list(
            range(1, 17)
        ):
            raise RuntimeError("downstream-MIDI attempt budget differs")
        for relative, identity in source_identities.items():
            path = _regular_inside(root, relative, "post-run source input")
            if (
                path.stat().st_size != identity["bytes"]
                or file_sha256(path) != identity["sha256"]
            ):
                raise RuntimeError("downstream-MIDI source changed during execution")
        network = dict(network_observation())
        if (
            network.get("os_network_denial_enforced") is not True
            or network.get("python_network_attempts") != 0
        ):
            raise RuntimeError("downstream-MIDI network-denial evidence differs")

        document: dict[str, Any] = {
            "schema": CANARY_SCHEMA,
            "document_sha256": "",
            "status": CANARY_STATUS,
            "evidence_scope": "private_development_only",
            "plan": {
                "path": str(plan_file),
                "document_sha256": plan["document_sha256"],
            },
            "integration": {
                "report_sha256": integration_report["report_sha256"],
                "plan_sha256": integration_report["plan_sha256"],
            },
            "policy": {
                "attempt_budget": 16,
                "attempts_completed": len(attempts),
                "same_transcriber_parameters_per_pair": True,
                "transcription_parameters": dict(TRANSCRIPTION_PARAMETERS),
                "blind_order_seed": 0,
                "automatic_winner_selection": False,
                "automatic_retry": False,
            },
            "cases": cases,
            "attempts": attempts,
            "network": network,
            "effects": {
                "private_audio_input_identities": sum(
                    len(case["grouped_other_control_inputs"])
                    for case in plan["cases"]
                ),
                "unique_private_audio_input_files": len(source_identities),
                "grouped_other_controls_written": 8,
                "midi_transcription_attempts": len(attempts),
                "midi_files_written": 16,
                "neutral_preview_audio_files_written": 16,
                "separator_model_loads": 0,
                "separator_inference_attempts": 0,
                "checkpoint_loads": 0,
                "network_attempts": 0,
                "source_selected": False,
                "public_activation": False,
                "audio_upload": False,
            },
            "boundaries": {
                "human_review_required": True,
                "review_selects_source_automatically": False,
                "negative_feedback_disables_six_role_evidence": False,
                "source_selection": False,
                "public_activation": False,
                "hosting": False,
                "redistribution": False,
                "audio_upload": False,
            },
            "elapsed_seconds": time.monotonic() - started,
        }
        document["document_sha256"] = canary_document_sha256(document)
        technical = staging / "TECHNICAL"
        technical.mkdir(mode=0o700)
        report_path = technical / "MIDI-CANARY-REPORT.json"
        report_path.write_text(
            json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        report_path.chmod(0o600)
        review = staging / "REVIEW"
        review.mkdir(mode=0o700)
        from .separation_fine_stem_midi_review import render_midi_canary_review

        page = review / "midi_review.html"
        page.write_text(render_midi_canary_review(document), encoding="utf-8")
        page.chmod(0o600)
        _make_private(staging)
        os.rename(staging, destination)
        return copy.deepcopy(document)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def validate_fine_stem_midi_canary(value: Mapping[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(dict(value))
    if (
        document.get("schema") != CANARY_SCHEMA
        or document.get("status") != CANARY_STATUS
        or document.get("document_sha256") != canary_document_sha256(document)
    ):
        raise ValueError("fine-stem MIDI canary identity differs")
    cases = document.get("cases")
    attempts = document.get("attempts")
    if not isinstance(cases, list) or len(cases) != 8:
        raise ValueError("fine-stem MIDI canary cases differ")
    if not isinstance(attempts, list) or len(attempts) != 16:
        raise ValueError("fine-stem MIDI canary attempts differ")
    if [row.get("attempt_number") for row in attempts] != list(range(1, 17)):
        raise ValueError("fine-stem MIDI canary attempt order differs")
    if document.get("effects", {}).get("source_selected") is not False:
        raise ValueError("fine-stem MIDI canary selected a source")
    if document.get("effects", {}).get("separator_inference_attempts") != 0:
        raise ValueError("fine-stem MIDI canary reran separation")
    if document.get("network", {}).get("python_network_attempts") != 0:
        raise ValueError("fine-stem MIDI canary network attempts differ")
    return document


__all__ = [
    "CANARY_SCHEMA",
    "CANARY_STATUS",
    "TRANSCRIPTION_PARAMETERS",
    "canary_document_sha256",
    "execute_fine_stem_midi_canary",
    "validate_fine_stem_midi_canary",
]
