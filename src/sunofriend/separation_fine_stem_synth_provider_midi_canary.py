"""Plan-bound private three-arm synth MIDI comparison executor."""

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

from .midi import MidiTrack, write_midi_file
from .separation_fine_stem_canary_audio import file_sha256
from .separation_fine_stem_integration_report import (
    validate_fine_stem_integration_report,
)
from .separation_fine_stem_synth_provider_midi_plan import (
    ARM_IDS,
    validate_fine_stem_synth_provider_midi_plan,
)
from .separation_fine_stem_synth_provider_outcome import (
    validate_fine_stem_synth_provider_outcome,
)
from .separation_fine_stem_synth_provider_qualification import (
    validate_fine_stem_synth_provider_qualification,
)
from .separation_midi_comparison import (
    TRANSCRIPTION_PARAMETERS,
    Renderer,
    Transcriber,
    artifact,
    make_private,
    match_preview_loudness,
    regular_inside,
    render_to_fixed_float,
    validated_notes,
    verify_audio_identity,
    write_notes,
    write_pcm24,
)


CANARY_SCHEMA = "sunofriend.fine-stem-synth-provider-midi-canary.v1"
CANARY_STATUS = "complete_private_three_arm_review_required_no_selection"


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


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path.name}")
    return value


def _root_map(
    *,
    integration_root: str | Path,
    provider_root: str | Path,
    grouped_other_root: str | Path,
) -> dict[str, Path]:
    return {
        "six_role_integration": Path(integration_root).expanduser().resolve(strict=True),
        "provider_qualification": Path(provider_root).expanduser().resolve(strict=True),
        "downstream_midi_canary": Path(grouped_other_root)
        .expanduser()
        .resolve(strict=True),
    }


def execute_fine_stem_synth_provider_midi_canary(
    plan_path: str | Path,
    *,
    integration_root: str | Path,
    provider_root: str | Path,
    grouped_other_root: str | Path,
    out_dir: str | Path,
    expected_plan_sha256: str,
    transcribe: Transcriber,
    render: Renderer,
    network_observation: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    """Execute exactly 12 approved attempts and atomically publish evidence."""

    plan_file = Path(plan_path).expanduser().resolve(strict=True)
    plan = validate_fine_stem_synth_provider_midi_plan(_load_json(plan_file))
    if plan["document_sha256"] != expected_plan_sha256:
        raise ValueError("approved provider synth MIDI plan SHA-256 differs")
    roots = _root_map(
        integration_root=integration_root,
        provider_root=provider_root,
        grouped_other_root=grouped_other_root,
    )
    integration = validate_fine_stem_integration_report(
        _load_json(roots["six_role_integration"] / "TECHNICAL/INTEGRATION-REPORT.json")
    )
    qualification = validate_fine_stem_synth_provider_qualification(
        _load_json(
            roots["provider_qualification"]
            / "TECHNICAL/PROVIDER-QUALIFICATION.json"
        )
    )
    presence = validate_fine_stem_synth_provider_outcome(
        _load_json(
            roots["provider_qualification"]
            / "TECHNICAL/PROVIDER-PRESENCE-OUTCOME.json"
        )
    )
    if (
        integration["report_sha256"] != plan["integration_report_sha256"]
        or qualification["document_sha256"]
        != plan["qualification_document_sha256"]
        or presence["document_sha256"]
        != plan["presence_outcome_document_sha256"]
    ):
        raise ValueError("provider synth MIDI evidence-root binding differs")

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"fresh provider synth MIDI output required: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=destination.parent)
    )
    staging.chmod(0o700)
    started = time.monotonic()
    input_identities: dict[str, dict[str, Any]] = {}
    attempts: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    try:
        for case in plan["cases"]:
            case_id = str(case["case_id"])
            case_root = staging / "CASES" / case_id
            case_root.mkdir(parents=True, mode=0o700)
            parameters = dict(case["frozen_transcription"]["parameters"])
            if parameters != TRANSCRIPTION_PARAMETERS:
                raise ValueError("provider synth MIDI transcription parameters differ")
            transcription = case["frozen_transcription"]["transcription"]
            if transcription.get("processing_kind") != "synth":
                raise ValueError("provider synth MIDI processing kind differs")

            source = case["source_reference"]
            source_root = roots[source["root_kind"]]
            verify_audio_identity(
                source_root,
                source["artifact"],
                f"{case_id} source reference",
            )
            source_key = f"{source['root_kind']}:{source['artifact']['relative_path']}"
            input_identities[source_key] = {
                "root_kind": source["root_kind"],
                "relative_path": source["artifact"]["relative_path"],
                "bytes": source["artifact"]["bytes"],
                "sha256": source["artifact"]["sha256"],
            }

            attempt_by_display = {
                attempt["display_id"]: attempt
                for attempt in plan["attempts"]
                if attempt["case_id"] == case_id
            }
            if set(attempt_by_display) != {"A", "B", "C"}:
                raise ValueError("provider synth MIDI display mapping differs")
            outputs: dict[str, dict[str, Any]] = {}
            preview_float = {}
            for display_id in ("A", "B", "C"):
                planned_attempt = attempt_by_display[display_id]
                arm_id = planned_attempt["arm_id"]
                arm = case["arms"][arm_id]
                if (
                    arm_id not in ARM_IDS
                    or arm["root_kind"] != planned_attempt["root_kind"]
                ):
                    raise ValueError("provider synth MIDI attempt/arm binding differs")
                audio_root = roots[arm["root_kind"]]
                audio_path = verify_audio_identity(
                    audio_root,
                    arm["artifact"],
                    f"{case_id} display {display_id} input",
                )
                identity_key = f"{arm['root_kind']}:{arm['artifact']['relative_path']}"
                input_identities[identity_key] = {
                    "root_kind": arm["root_kind"],
                    "relative_path": arm["artifact"]["relative_path"],
                    "bytes": arm["artifact"]["bytes"],
                    "sha256": arm["artifact"]["sha256"],
                }
                attempt_started = time.monotonic()
                notes = validated_notes(
                    transcribe(
                        str(audio_path),
                        kind=transcription["processing_kind"],
                        **parameters,
                    )
                )
                notes_path = case_root / f"{display_id}.notes.json"
                write_notes(notes_path, notes)
                midi_path = case_root / f"{display_id}.mid"
                write_midi_file(
                    midi_path,
                    [
                        MidiTrack(
                            f"synth comparison {display_id}",
                            int(transcription["general_midi_channel"]),
                            int(transcription["general_midi_program_zero_based"]),
                            notes,
                        )
                    ],
                    bpm=float(case["frozen_transcription"]["metadata"]["bpm"]),
                )
                midi_path.chmod(0o600)
                raw_path = case_root / f".{display_id}.render.wav"
                preview_float[display_id], render_status = render_to_fixed_float(
                    midi_path,
                    raw_path,
                    notes=notes,
                    render=render,
                )
                if raw_path.exists():
                    raw_path.unlink()
                elapsed = time.monotonic() - attempt_started
                attempt = {
                    "attempt_number": planned_attempt["attempt_number"],
                    "case_id": case_id,
                    "display_id": display_id,
                    "arm_id": arm_id,
                    "root_kind": arm["root_kind"],
                    "processing_kind": transcription["processing_kind"],
                    "parameters": parameters,
                    "note_count": len(notes),
                    "elapsed_seconds": elapsed,
                    "status": "complete",
                }
                attempts.append(attempt)
                outputs[display_id] = {
                    "arm_id": arm_id,
                    "root_kind": arm["root_kind"],
                    "notes": artifact(notes_path, staging),
                    "midi": artifact(midi_path, staging),
                    "note_count": len(notes),
                    "pitch_range": (
                        [
                            min(note.pitch for note in notes),
                            max(note.pitch for note in notes),
                        ]
                        if notes
                        else None
                    ),
                    "render_status": render_status,
                }

            matched, matching = match_preview_loudness(preview_float)
            for display_id in ("A", "B", "C"):
                preview_path = case_root / f"{display_id}.preview.wav"
                preview = write_pcm24(preview_path, matched[display_id])
                preview["relative_path"] = preview_path.relative_to(staging).as_posix()
                outputs[display_id]["preview"] = preview
            cases.append(
                {
                    "case_id": case_id,
                    "track_id": case["track_id"],
                    "title": case["title"],
                    "window_seconds": case["window_seconds"],
                    "metadata": case["frozen_transcription"]["metadata"],
                    "transcription": transcription,
                    "source_reference": {
                        "root_kind": source["root_kind"],
                        "artifact": source["artifact"],
                    },
                    "outputs": outputs,
                    "blind_display_labels": ["A", "B", "C"],
                    "loudness_matching": matching,
                }
            )

        attempts.sort(key=lambda item: item["attempt_number"])
        if (
            len(attempts) != 12
            or [attempt["attempt_number"] for attempt in attempts]
            != list(range(1, 13))
        ):
            raise RuntimeError("provider synth MIDI attempt budget differs")
        for identity in input_identities.values():
            path = regular_inside(
                roots[identity["root_kind"]],
                identity["relative_path"],
                "post-run provider synth MIDI input",
            )
            if (
                path.stat().st_size != identity["bytes"]
                or file_sha256(path) != identity["sha256"]
            ):
                raise RuntimeError("provider synth MIDI input changed during execution")
        network = dict(network_observation())
        if (
            network.get("os_network_denial_enforced") is not True
            or network.get("python_network_attempts") != 0
        ):
            raise RuntimeError("provider synth MIDI network-denial evidence differs")

        document: dict[str, Any] = {
            "schema": CANARY_SCHEMA,
            "document_sha256": "",
            "status": CANARY_STATUS,
            "evidence_scope": "private_development_only",
            "plan": {
                "document_sha256": plan["document_sha256"],
            },
            "bindings": {
                "integration_report_sha256": integration["report_sha256"],
                "qualification_document_sha256": qualification["document_sha256"],
                "presence_outcome_document_sha256": presence["document_sha256"],
            },
            "policy": {
                "attempt_budget": 12,
                "attempts_completed": len(attempts),
                "same_transcriber_parameters_for_all_arms": True,
                "transcription_parameters": dict(TRANSCRIPTION_PARAMETERS),
                "blind_display_labels": ["A", "B", "C"],
                "automatic_winner_selection": False,
                "automatic_retry": False,
            },
            "cases": cases,
            "attempts": attempts,
            "network": network,
            "effects": {
                "private_audio_input_identities": len(input_identities),
                "source_reference_inputs_verified": 4,
                "source_reference_transcription_attempts": 0,
                "midi_transcription_attempts": len(attempts),
                "midi_files_written": 12,
                "neutral_preview_audio_files_written": 12,
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
                "source_reference_visible_during_review": True,
                "review_selects_source_automatically": False,
                "negative_feedback_disables_core_four": False,
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
        report_path = technical / "PROVIDER-SYNTH-MIDI-CANARY.json"
        report_path.write_text(
            json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        report_path.chmod(0o600)
        review = staging / "REVIEW"
        review.mkdir(mode=0o700)
        from .separation_fine_stem_synth_provider_midi_review import (
            render_provider_synth_midi_review,
        )

        page = review / "provider_synth_midi_review.html"
        page.write_text(render_provider_synth_midi_review(document), encoding="utf-8")
        page.chmod(0o600)
        make_private(staging)
        os.rename(staging, destination)
        return copy.deepcopy(document)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def validate_fine_stem_synth_provider_midi_canary(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    document = copy.deepcopy(dict(value))
    if (
        document.get("schema") != CANARY_SCHEMA
        or document.get("status") != CANARY_STATUS
        or document.get("document_sha256") != canary_document_sha256(document)
    ):
        raise ValueError("provider synth MIDI canary identity differs")
    cases = document.get("cases")
    attempts = document.get("attempts")
    if (
        not isinstance(cases, list)
        or len(cases) != 4
        or not isinstance(attempts, list)
        or len(attempts) != 12
        or [attempt.get("attempt_number") for attempt in attempts]
        != list(range(1, 13))
    ):
        raise ValueError("provider synth MIDI canary budget differs")
    for case in cases:
        if (
            set(case.get("outputs", {})) != {"A", "B", "C"}
            or case.get("blind_display_labels") != ["A", "B", "C"]
            or {value.get("arm_id") for value in case["outputs"].values()}
            != set(ARM_IDS)
        ):
            raise ValueError("provider synth MIDI canary arms differ")
    effects = document.get("effects", {})
    if (
        effects.get("midi_transcription_attempts") != 12
        or effects.get("midi_files_written") != 12
        or effects.get("neutral_preview_audio_files_written") != 12
        or effects.get("separator_inference_attempts") != 0
        or effects.get("source_selected") is not False
        or effects.get("public_activation") is not False
    ):
        raise ValueError("provider synth MIDI canary effects differ")
    if (
        document.get("network", {}).get("os_network_denial_enforced") is not True
        or document.get("network", {}).get("python_network_attempts") != 0
    ):
        raise ValueError("provider synth MIDI canary network evidence differs")
    return document


__all__ = [
    "CANARY_SCHEMA",
    "CANARY_STATUS",
    "canary_document_sha256",
    "execute_fine_stem_synth_provider_midi_canary",
    "validate_fine_stem_synth_provider_midi_canary",
]
