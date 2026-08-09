"""Private, plan-bound fine-stem versus grouped-other MIDI comparison."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from .midi import MidiTrack, write_midi_file
from .models import NoteEvent
from .separation_fine_stem_canary_audio import (
    PCM24_MAX,
    PCM24_MIN,
    PCM24_SCALE,
    file_sha256,
)
from .separation_fine_stem_integration_report import (
    validate_fine_stem_integration_report,
)
from .separation_fine_stem_midi_plan import (
    validate_fine_stem_midi_plan,
)


CANARY_SCHEMA = "sunofriend.fine-stem-downstream-midi-canary.v1"
CANARY_STATUS = "complete_private_review_required_no_selection"
SAMPLE_RATE_HZ = 44_100
FRAMES = 661_500
TRANSCRIPTION_PARAMETERS = {
    "onset_threshold": 0.5,
    "frame_threshold": 0.3,
    "min_note_ms": 60.0,
}

Transcriber = Callable[..., Sequence[NoteEvent]]
Renderer = Callable[[Path, Path], Any]


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


def _regular_inside(root: Path, relative: str, label: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError(f"{label} must use a relative path")
    root = root.resolve(strict=True)
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} escapes its evidence root") from error
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError(f"{label} is not a regular non-link file")
    return path


def _verify_audio_identity(
    root: Path, identity: Mapping[str, Any], label: str
) -> Path:
    import soundfile as sf

    path = _regular_inside(root, str(identity.get("relative_path", "")), label)
    if path.stat().st_size != identity.get("bytes"):
        raise ValueError(f"{label} byte count changed")
    if file_sha256(path) != identity.get("sha256"):
        raise ValueError(f"{label} SHA-256 changed")
    info = sf.info(path)
    if (
        info.samplerate != identity.get("sample_rate_hz")
        or info.channels != identity.get("channels")
        or info.frames != identity.get("frames")
        or info.subtype != identity.get("subtype")
        or info.samplerate != SAMPLE_RATE_HZ
        or info.channels != 2
        or info.frames != FRAMES
        or info.subtype != "PCM_24"
    ):
        raise ValueError(f"{label} PCM24 geometry changed")
    return path


def _read_pcm24_integer(path: Path) -> np.ndarray:
    import soundfile as sf

    value = sf.read(path, dtype="float64", always_2d=True)[0]
    if value.shape != (FRAMES, 2) or not np.isfinite(value).all():
        raise ValueError("fine-stem MIDI input samples differ")
    integer = np.rint(value * PCM24_SCALE).astype(np.int64)
    if integer.min(initial=0) < PCM24_MIN or integer.max(initial=0) > PCM24_MAX:
        raise ValueError("fine-stem MIDI input exceeds PCM24")
    return integer


def _write_pcm24(path: Path, integer: np.ndarray) -> dict[str, Any]:
    import soundfile as sf

    value = np.asarray(integer, dtype=np.int64)
    if (
        value.shape != (FRAMES, 2)
        or value.min(initial=0) < PCM24_MIN
        or value.max(initial=0) > PCM24_MAX
    ):
        raise ValueError("fine-stem MIDI PCM24 output differs")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.path.lexists(path):
        raise FileExistsError(f"fine-stem MIDI artifact already exists: {path}")
    sf.write(
        path,
        value.astype(np.float64) / PCM24_SCALE,
        SAMPLE_RATE_HZ,
        format="WAV",
        subtype="PCM_24",
    )
    path.chmod(0o600)
    persisted = sf.read(path, dtype="float64", always_2d=True)[0]
    persisted_integer = np.rint(persisted * PCM24_SCALE).astype(np.int64)
    if not np.array_equal(persisted_integer, value):
        raise RuntimeError("fine-stem MIDI PCM24 persistence changed samples")
    return _audio_artifact(path)


def _artifact(path: Path, root: Path) -> dict[str, Any]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _audio_artifact(path: Path) -> dict[str, Any]:
    return {
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "channels": 2,
        "frames": FRAMES,
        "subtype": "PCM_24",
    }


def _validated_notes(values: Sequence[NoteEvent]) -> list[NoteEvent]:
    result: list[NoteEvent] = []
    for value in values:
        note = NoteEvent(
            start=float(value.start),
            end=float(value.end),
            pitch=int(value.pitch),
            velocity=int(value.velocity),
        )
        if (
            not math.isfinite(note.start)
            or not math.isfinite(note.end)
            or note.start < 0
            or note.end <= note.start
            or note.end > 15.25
            or not 0 <= note.pitch <= 127
            or not 1 <= note.velocity <= 127
        ):
            raise ValueError("fine-stem MIDI transcriber returned an invalid note")
        result.append(note)
    result.sort(key=lambda item: (item.start, item.pitch, item.end, item.velocity))
    return result


def _write_notes(path: Path, notes: Sequence[NoteEvent]) -> dict[str, Any]:
    payload = {
        "schema": "sunofriend.fine-stem-downstream-midi-notes.v1",
        "notes": [
            {
                "start": note.start,
                "end": note.end,
                "pitch": note.pitch,
                "velocity": note.velocity,
            }
            for note in notes
        ],
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return payload


def _render_to_fixed_float(
    midi_path: Path,
    raw_path: Path,
    *,
    notes: Sequence[NoteEvent],
    render: Renderer,
) -> tuple[np.ndarray, str]:
    import soundfile as sf

    if not notes:
        return np.zeros((FRAMES, 2), dtype=np.float64), "silence_no_notes"
    render(midi_path, raw_path)
    value, sample_rate = sf.read(raw_path, dtype="float64", always_2d=True)
    if sample_rate != SAMPLE_RATE_HZ or not np.isfinite(value).all():
        raise RuntimeError("neutral MIDI renderer clock or samples differ")
    if value.shape[1] == 1:
        value = np.repeat(value, 2, axis=1)
    if value.shape[1] != 2:
        raise RuntimeError("neutral MIDI renderer channel count differs")
    fixed = np.zeros((FRAMES, 2), dtype=np.float64)
    copied = min(FRAMES, len(value))
    fixed[:copied] = value[:copied]
    return fixed, "fluidsynth_dry_general_midi"


def _matched_preview_pair(
    candidate: np.ndarray, control: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    values = [
        np.asarray(candidate, dtype=np.float64),
        np.asarray(control, dtype=np.float64),
    ]
    rms = [float(np.sqrt(np.mean(np.square(value)))) for value in values]
    peaks = [float(np.max(np.abs(value), initial=0.0)) for value in values]
    target = 10 ** (-24.0 / 20.0)
    nonzero = [index for index, value in enumerate(rms) if value > 1e-12]
    if len(nonzero) == 2:
        achievable = [
            rms[index] * (0.7 / peaks[index]) if peaks[index] > 0 else target
            for index in nonzero
        ]
        matched = min(target, *achievable)
        gains = [matched / value for value in rms]
        status = "matched"
    else:
        gains = [
            min(target / value, 0.7 / peaks[index])
            if value > 1e-12 and peaks[index] > 0
            else 1.0
            for index, value in enumerate(rms)
        ]
        status = "not_applicable_one_or_both_silent"
    scaled = [values[index] * gains[index] for index in range(2)]
    integers = [
        np.rint(np.clip(value, -0.7, 0.7) * PCM24_SCALE).astype(np.int64)
        for value in scaled
    ]
    post_rms = [
        float(np.sqrt(np.mean(np.square(value.astype(np.float64) / PCM24_SCALE))))
        for value in integers
    ]
    return integers[0], integers[1], {
        "policy": "pair RMS matched at or below -24 dBFS with -3.10 dBFS peak cap",
        "status": status,
        "pre_rms": rms,
        "pre_peak": peaks,
        "gains": gains,
        "post_rms": post_rms,
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


def _make_private(root: Path) -> None:
    for directory, child_directories, files in os.walk(root):
        Path(directory).chmod(0o700)
        for name in child_directories:
            (Path(directory) / name).chmod(0o700)
        for name in files:
            (Path(directory) / name).chmod(0o600)


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
