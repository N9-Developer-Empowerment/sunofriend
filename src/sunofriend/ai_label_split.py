"""Auditable label-only MIDI derivatives from immutable AI transcription runs.

MuScriptor instrument conditioning is guidance rather than an output schema.  A
run requested as one role can still contain several model-reported labels.  This
module partitions those existing notes exactly; it does not run a model, repair
notes, or claim that a label identifies the audible physical instrument.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Mapping

from .ai_bakeoff import _candidate_tracks
from .ai_expression import expression_velocities
from .ai_matrix import build_ai_candidate_matrix
from .ai_runtime import AITranscriptionCandidate, AITranscriptionRequest
from .clip import read_midi_clips
from .midi import write_midi_file
from .midi_tempo import retime_midi_bytes
from .note_safety import MidiNoteInterval, normalize_midi_intervals


AI_LABEL_SPLIT_SCHEMA = "sunofriend.ai-label-split.v1"
AI_LABEL_PARTITION_SCHEMA = "sunofriend.ai-label-partition.v1"
_RUN_SCHEMA = "sunofriend.ai-bakeoff-run.v1"
_TICKS_PER_BEAT = 480
_PATH_KEY = re.compile(
    r"(?:^|_)(?:path|paths|dir|directory|cwd|command|argv|executable|python)(?:_|$)"
)
_PATH_SUFFIXES = (
    ".json",
    ".log",
    ".mid",
    ".onnx",
    ".py",
    ".safetensors",
    ".sf2",
    ".wav",
)
_REDACTED = object()


def split_ai_candidate_label(
    run_directory: str | Path,
    *,
    label: str,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Atomically publish one exact model-label partition and MIDI auditions."""

    run_dir = Path(run_directory).expanduser().absolute()
    output = Path(out_dir).expanduser().absolute()
    _validated_label(label)
    if not run_dir.is_dir():
        raise ValueError(f"AI run directory does not exist: {run_dir}")
    _require_output_outside_run(run_dir, output)
    if output.exists():
        raise FileExistsError(f"AI label-split output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output.name}.label-split-", dir=output.parent
    ) as temporary:
        staging = Path(temporary) / "result"
        report = _split_ai_candidate_label_staged(
            run_dir,
            label=label,
            out_dir=staging,
        )
        if output.exists():
            raise FileExistsError(f"AI label-split output already exists: {output}")
        os.replace(staging, output)
    return report


def _split_ai_candidate_label_staged(
    run_directory: str | Path,
    *,
    label: str,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Write one exact model-label track and its exhaustive complement.

    The immutable source run is fully verified before and after the derivative
    is written.  ``label-partition.json`` preserves the exact source events and
    source indices.  The MIDI files are deterministic audition renders: MIDI's
    integer pitch/tick grid and unambiguous note-lifetime rules can quantize or
    normalize those events, and the report records those effects explicitly.
    """

    run_dir = Path(run_directory).expanduser().absolute()
    output = Path(out_dir).expanduser().absolute()
    target_label = _validated_label(label)
    if not run_dir.is_dir():
        raise ValueError(f"AI run directory does not exist: {run_dir}")
    _require_output_outside_run(run_dir, output)
    if output.exists():
        raise FileExistsError(f"AI label-split output already exists: {output}")

    source_tree_before = _tree_fingerprints(run_dir)
    verification_before = build_ai_candidate_matrix(
        [("S0-label-split", run_dir)]
    )
    run_path = run_dir / "run.json"
    run = _read_json(run_path)
    if run.get("schema") != _RUN_SCHEMA or run.get("status") != "complete":
        raise ValueError("AI label split requires a completed immutable run")
    if run.get("run_id") != run_dir.name:
        raise ValueError("AI label-split run ID disagrees with its directory")
    request_record = _verified_run_artifact(run, run_dir, "request.json")
    candidate_record = _verified_run_artifact(run, run_dir, "candidate.json")
    candidate_midi_record = _verified_run_artifact(run, run_dir, "candidate.mid")
    request = AITranscriptionRequest.from_dict(
        _read_json(run_dir / "request.json"), require_audio=False
    )
    candidate = AITranscriptionCandidate.from_dict(
        _read_json(run_dir / "candidate.json")
    )
    if candidate.backend != request.backend or candidate.backend != run.get("backend"):
        raise ValueError("AI label-split backend records disagree")
    candidate_execution = candidate.metadata.get("execution")
    if isinstance(candidate_execution, Mapping) and run.get("execution") != candidate_execution:
        raise ValueError("AI label-split execution differs from pinned candidate metadata")
    source_record = _verified_source_record(request, run)

    selected_indices = [
        index
        for index, note in enumerate(candidate.notes)
        if (note.instrument or "unlabelled") == target_label
    ]
    selected_index_set = set(selected_indices)
    complement_indices = [
        index for index in range(len(candidate.notes)) if index not in selected_index_set
    ]
    if sorted(selected_indices + complement_indices) != list(range(len(candidate.notes))):
        raise AssertionError("AI label split did not form an exact note partition")

    bpm, embedded_bpm = _verified_render_bpm(run, run_dir / "candidate.mid")
    velocities, velocity_policy = _audition_velocities(run_dir, candidate, run)
    selected_candidate = replace(
        candidate,
        notes=tuple(candidate.notes[index] for index in selected_indices),
        raw_artifacts=(),
    )
    complement_candidate = replace(
        candidate,
        notes=tuple(candidate.notes[index] for index in complement_indices),
        raw_artifacts=(),
    )
    selected_velocities = [velocities[index] for index in selected_indices]
    complement_velocities = [velocities[index] for index in complement_indices]

    output.mkdir(parents=True, exist_ok=False)
    source_request = output / "source-request.json"
    source_candidate = output / "source-candidate.json"
    control_midi = output / "unchanged-full-candidate.mid"
    selected_midi = output / "requested-label.mid"
    complement_midi = output / "unexpected-label-complement.mid"
    partition_path = output / "label-partition.json"
    report_path = output / "ai_label_split.json"
    shutil.copyfile(run_dir / "request.json", source_request)
    shutil.copyfile(run_dir / "candidate.json", source_candidate)
    shutil.copyfile(run_dir / "candidate.mid", control_midi)
    if _sha256(source_request) != request_record["sha256"]:
        raise ValueError("source request JSON control copy failed verification")
    if _sha256(source_candidate) != candidate_record["sha256"]:
        raise ValueError("source candidate JSON control copy failed verification")
    if _sha256(control_midi) != candidate_midi_record["sha256"]:
        raise ValueError("unchanged candidate MIDI control copy failed verification")
    write_midi_file(
        selected_midi,
        _candidate_tracks(selected_candidate, velocities=selected_velocities),
        bpm=bpm,
    )
    write_midi_file(
        complement_midi,
        _candidate_tracks(complement_candidate, velocities=complement_velocities),
        bpm=bpm,
    )

    selected_render = _midi_render_summary(
        selected_candidate, selected_velocities, bpm=bpm
    )
    complement_render = _midi_render_summary(
        complement_candidate, complement_velocities, bpm=bpm
    )
    _verify_rendered_note_count(selected_midi, selected_render)
    _verify_rendered_note_count(complement_midi, complement_render)
    render_contract = _render_contract(
        bpm=bpm,
        embedded_bpm=embedded_bpm,
        velocity_policy=velocity_policy,
    )

    partition = {
        "schema": AI_LABEL_PARTITION_SCHEMA,
        "source_request_sha256": request_record["sha256"],
        "source_candidate_sha256": candidate_record["sha256"],
        "source_candidate_midi_sha256": candidate_midi_record["sha256"],
        "source_audio_sha256": source_record["sha256"],
        "label": target_label,
        "velocity_policy": velocity_policy,
        "render_contract": render_contract,
        "source_note_count": len(candidate.notes),
        "selected": [
            _partition_note(index, candidate, velocities[index])
            for index in selected_indices
        ],
        "complement": [
            _partition_note(index, candidate, velocities[index])
            for index in complement_indices
        ],
        "partition": {
            "disjoint": not (selected_index_set & set(complement_indices)),
            "exhaustive": len(selected_indices) + len(complement_indices)
            == len(candidate.notes),
            "source_indices_changed": 0,
            "source_events_deleted": 0,
            "source_events_duplicated": 0,
        },
    }
    _atomic_json(partition_path, partition)

    counts = Counter(note.instrument or "unlabelled" for note in candidate.notes)
    selected_count = len(selected_indices)
    complement_count = len(complement_indices)
    status = "review-required" if selected_count else "no-evidence"
    report = {
        "schema": AI_LABEL_SPLIT_SCHEMA,
        "status": status,
        "operation": "ai-label-split",
        "label": target_label,
        "bpm": bpm,
        "source_run": {
            "run_id": run_dir.name,
            "run_json": _path_free_record(_file_record(run_path)),
            "backend": candidate.backend,
            "model_version": candidate.model_version,
            "source": source_record,
            "checkpoint": _verified_checkpoint_fingerprint(run),
            "worker": _verified_record_fingerprint(run.get("worker")),
            "execution": {
                "source": "pinned-request-and-candidate-artifacts",
                "request_options": _path_free_execution(request.options),
                "candidate": _path_free_execution(
                    candidate.metadata.get("execution")
                ),
            },
            "request": {
                "roles": list(request.roles),
                "start_seconds": request.start_seconds,
                "end_seconds": request.end_seconds,
                "sha256": request_record["sha256"],
            },
            "candidate": candidate_record,
            "candidate_midi": candidate_midi_record,
            "duration_seconds": verification_before["lanes"][0][
                "duration_seconds"
            ],
        },
        "evidence": {
            "detected_label_counts": dict(sorted(counts.items())),
            "selected_note_count": selected_count,
            "complement_note_count": complement_count,
            "selected_source_indices": selected_indices,
            "complement_source_indices": complement_indices,
            "selection_policy": "exact-model-reported-instrument-label",
            "physical_instrument_identified": False,
        },
        "artifacts": {
            source_request.name: _file_record(source_request, relative_to=output),
            source_candidate.name: _file_record(
                source_candidate, relative_to=output
            ),
            control_midi.name: _file_record(control_midi, relative_to=output),
            selected_midi.name: _file_record(selected_midi, relative_to=output),
            complement_midi.name: _file_record(
                complement_midi, relative_to=output
            ),
            partition_path.name: _file_record(partition_path, relative_to=output),
        },
        "effects": {
            "automatic_promotion": False,
            "model_rerun": False,
            "source_run_mutated": False,
            "raw_candidate_mutated": False,
            "source_midi_mutated": False,
            "source_partition_events_deleted": 0,
            "source_partition_events_duplicated": 0,
            "source_request_control_byte_identical": True,
            "source_candidate_control_byte_identical": True,
            "unchanged_control_byte_identical": True,
            "selected_audition_velocities_written": selected_count,
            "midi_rendering": {
                selected_midi.name: selected_render,
                complement_midi.name: complement_render,
            },
        },
        "warnings": [
            "The split follows model-reported labels only; it is not source separation or proof of an audible instrument.",
            "The JSON partition is exact; audition MIDI uses integer pitches and ticks and can collapse or truncate ambiguous same-pitch events.",
            "The requested-label and complement MIDI are deterministic listening derivatives, not new model candidates.",
            "Use unchanged-full-candidate.mid as the byte-identical control and choose only after listening.",
            "source-request.json and source-candidate.json are private local provenance controls; do not publish their contents.",
        ],
    }
    report["report_sha256"] = _document_hash(report)
    _atomic_json(report_path, report)
    verification_after = build_ai_candidate_matrix(
        [("S0-label-split", run_dir)]
    )
    if (
        verification_before != verification_after
        or source_tree_before != _tree_fingerprints(run_dir)
    ):
        raise ValueError("immutable AI run changed while writing its label split")
    return report


def _audition_velocities(
    run_dir: Path,
    candidate: AITranscriptionCandidate,
    run: Mapping[str, Any],
) -> tuple[list[int], str]:
    expression_path = run_dir / "candidate.expression.json"
    expression_record = run.get("artifacts", {}).get("candidate.expression.json")
    if expression_path.is_file() and isinstance(expression_record, Mapping):
        expected_path = Path(str(expression_record.get("path", "")))
        if expected_path.is_absolute():
            expected_path = expected_path.resolve()
        else:
            expected_path = (run_dir / expected_path).resolve()
        if expected_path != expression_path.resolve():
            raise ValueError("AI run expression artifact escapes or disagrees")
        if (
            expression_record.get("bytes") != expression_path.stat().st_size
            or expression_record.get("sha256") != _sha256(expression_path)
        ):
            raise ValueError("AI run expression artifact failed its size/SHA-256 check")
        document = _read_json(expression_path)
        try:
            return (
                expression_velocities(document, expected_notes=len(candidate.notes)),
                "verified-source-expression",
            )
        except ValueError:
            pass
    return (
        [int(note.velocity or 90) for note in candidate.notes],
        "model-or-fixed-90-fallback",
    )


def _partition_note(
    source_index: int,
    candidate: AITranscriptionCandidate,
    audition_velocity: int,
) -> dict[str, Any]:
    note = candidate.notes[source_index]
    return {
        "source_index": source_index,
        "source_event_id": note.source_event_id,
        "note": asdict(note),
        "audition_velocity": int(audition_velocity),
    }


def _validated_label(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("AI label must be text")
    label = value.strip()
    if not label:
        raise ValueError("AI label must not be empty")
    if len(label) > 128:
        raise ValueError("AI label must be at most 128 characters")
    return label


def _require_output_outside_run(run_dir: Path, output: Path) -> None:
    run_root = run_dir.resolve()
    output_root = output.resolve()
    if output_root == run_root or run_root in output_root.parents:
        raise ValueError("AI label-split output must be outside the source run")


def _verified_run_artifact(
    run: Mapping[str, Any], run_dir: Path, name: str
) -> dict[str, Any]:
    artifacts = run.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("AI label-split run has no artifact manifest")
    record = artifacts.get(name)
    if not isinstance(record, Mapping):
        raise ValueError(f"AI label-split run is missing pinned {name}")
    path_value = record.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"AI label-split {name} artifact has no path")
    recorded_path = Path(path_value)
    if not recorded_path.is_absolute():
        recorded_path = run_dir / recorded_path
    expected_path = (run_dir / name).resolve()
    if recorded_path.resolve() != expected_path:
        raise ValueError(f"AI label-split {name} artifact path disagrees")
    if not expected_path.is_file():
        raise ValueError(f"AI label-split pinned {name} does not exist")
    actual = {
        "bytes": expected_path.stat().st_size,
        "sha256": _sha256(expected_path),
    }
    if record.get("bytes") != actual["bytes"] or record.get("sha256") != actual["sha256"]:
        raise ValueError(f"AI label-split {name} failed its size/SHA-256 check")
    return actual


def _verified_source_record(
    request: AITranscriptionRequest, run: Mapping[str, Any]
) -> dict[str, Any]:
    source = run.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("AI label-split run has no pinned source audio")
    source_path = Path(request.audio_path).expanduser().resolve()
    recorded_value = source.get("path")
    if not isinstance(recorded_value, str) or not recorded_value:
        raise ValueError("AI label-split source audio record has no path")
    if Path(recorded_value).expanduser().resolve() != source_path:
        raise ValueError("pinned request and source audio paths disagree")
    if not source_path.is_file():
        raise ValueError("pinned source audio is no longer available")
    actual = {
        "bytes": source_path.stat().st_size,
        "sha256": _sha256(source_path),
    }
    if source.get("bytes") != actual["bytes"] or source.get("sha256") != actual["sha256"]:
        raise ValueError("pinned source audio failed its size/SHA-256 check")
    return actual


def _verified_render_bpm(run: Mapping[str, Any], candidate_midi: Path) -> tuple[float, float]:
    value = run.get("bpm")
    if isinstance(value, bool):
        raise ValueError("AI run has no valid BPM for the label-split MIDI")
    try:
        bpm = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("AI run has no valid BPM for the label-split MIDI") from exc
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("AI run has no valid BPM for the label-split MIDI")
    try:
        _, tempo = retime_midi_bytes(
            candidate_midi.read_bytes(), target_bpm=120.0
        )
    except (OSError, ValueError) as exc:
        raise ValueError(f"pinned candidate MIDI tempo is invalid: {exc}") from exc
    if tempo.tempo_event_inserted or tempo.tempo_events_changed != 1:
        raise ValueError("pinned candidate MIDI must have one explicit tempo event")
    if tempo.ticks_per_beat != _TICKS_PER_BEAT:
        raise ValueError("pinned candidate MIDI has an unexpected tick resolution")
    microseconds = int(round(60_000_000.0 / bpm))
    expected_embedded = 60_000_000.0 / microseconds
    if not math.isclose(
        tempo.source_bpm, expected_embedded, rel_tol=0.0, abs_tol=1e-12
    ):
        raise ValueError("AI run BPM disagrees with the pinned candidate MIDI tempo")
    return bpm, tempo.source_bpm


def _render_contract(
    *, bpm: float, embedded_bpm: float, velocity_policy: str
) -> dict[str, Any]:
    return {
        "policy": "deterministic-midi-audition-v1",
        "purpose": "audition-only; label-partition.json is the exact event record",
        "ticks_per_beat": _TICKS_PER_BEAT,
        "tempo_input_bpm": bpm,
        "embedded_bpm": embedded_bpm,
        "pitch_quantization": "nearest integer via Python round (ties to even), clamped 0..127",
        "time_quantization": "nearest 1/480 quarter-note tick via Python round (ties to even)",
        "minimum_duration_ticks": 1,
        "duplicate_onset_policy": "same track/channel/pitch/tick collapses to longest end and greatest velocity",
        "same_pitch_overlap_policy": "an earlier note ends at the next onset on the same track/channel/pitch",
        "velocity_policy": velocity_policy,
    }


def _midi_render_summary(
    candidate: AITranscriptionCandidate,
    velocities: list[int],
    *,
    bpm: float,
) -> dict[str, Any]:
    tracks = _candidate_tracks(candidate, velocities=velocities)
    seconds_per_tick = 60.0 / (bpm * _TICKS_PER_BEAT)
    pitch_quantized = 0
    onset_quantized = 0
    end_quantized = 0
    duration_quantized = 0
    for note in candidate.notes:
        rendered_pitch = max(0, min(127, round(note.pitch)))
        if float(rendered_pitch) != note.pitch:
            pitch_quantized += 1
        start_tick = _seconds_to_ticks(note.start_seconds, bpm)
        end_tick = _seconds_to_ticks(note.end_seconds, bpm)
        if not math.isclose(
            start_tick * seconds_per_tick,
            note.start_seconds,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            onset_quantized += 1
        if not math.isclose(
            end_tick * seconds_per_tick,
            note.end_seconds,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            end_quantized += 1
        if not math.isclose(
            (end_tick - start_tick) * seconds_per_tick,
            note.end_seconds - note.start_seconds,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            duration_quantized += 1

    raw: list[MidiNoteInterval] = []
    for owner, track in enumerate(tracks):
        for note in track.notes:
            raw.append(
                MidiNoteInterval(
                    owner=owner,
                    channel=track.channel,
                    start_tick=_seconds_to_ticks(note.start, bpm),
                    end_tick=_seconds_to_ticks(note.end, bpm),
                    pitch=max(0, min(127, int(note.pitch))),
                    velocity=max(1, min(127, int(note.velocity))),
                )
            )
    normalized = normalize_midi_intervals(raw)
    unique: dict[tuple[int, int, int, int], MidiNoteInterval] = {}
    for note in raw:
        key = (note.owner, note.channel, note.pitch, note.start_tick)
        existing = unique.get(key)
        safe_end = max(note.end_tick, note.start_tick + 1)
        if existing is None or safe_end > existing.end_tick:
            unique[key] = MidiNoteInterval(
                owner=note.owner,
                channel=note.channel,
                start_tick=note.start_tick,
                end_tick=safe_end,
                pitch=note.pitch,
                velocity=note.velocity,
            )
    voices: dict[tuple[int, int, int], list[MidiNoteInterval]] = {}
    for note in unique.values():
        voices.setdefault((note.owner, note.channel, note.pitch), []).append(note)
    overlap_truncated = 0
    for notes in voices.values():
        notes.sort(key=lambda item: (item.start_tick, item.end_tick))
        overlap_truncated += sum(
            left.end_tick > right.start_tick
            for left, right in zip(notes, notes[1:])
        )
    duplicate_collapsed = len(raw) - len(unique)
    minimum_extended = sum(note.end_tick <= note.start_tick for note in raw)
    rendered_count = len(normalized)
    source_count = len(candidate.notes)
    changed = any(
        (
            pitch_quantized,
            onset_quantized,
            end_quantized,
            duration_quantized,
            minimum_extended,
            duplicate_collapsed,
            overlap_truncated,
        )
    )
    return {
        "source_event_count": source_count,
        "rendered_midi_note_count": rendered_count,
        "rendered_midi_note_signatures": [
            {
                "track_index": note.owner,
                "channel": note.channel,
                "start_tick": note.start_tick,
                "end_tick": note.end_tick,
                "pitch": note.pitch,
                "velocity": note.velocity,
            }
            for note in normalized
        ],
        "integer_pitch_quantized_event_count": pitch_quantized,
        "onset_tick_quantized_event_count": onset_quantized,
        "end_tick_quantized_event_count": end_quantized,
        "duration_tick_quantized_event_count": duration_quantized,
        "minimum_duration_extended_event_count": minimum_extended,
        "duplicate_same_pitch_tick_onset_collapsed_event_count": duplicate_collapsed,
        "same_pitch_overlap_truncated_event_count": overlap_truncated,
        "source_event_to_midi_note_count_delta": rendered_count - source_count,
        "lossless_event_render": not changed,
    }


def _seconds_to_ticks(seconds: float, bpm: float) -> int:
    return int(round(seconds / (60.0 / bpm) * _TICKS_PER_BEAT))


def _verify_rendered_note_count(path: Path, summary: Mapping[str, Any]) -> None:
    actual = sum(len(clip.notes) for clip in read_midi_clips(path))
    if actual != summary["rendered_midi_note_count"]:
        raise ValueError(f"deterministic MIDI render audit disagrees for {path.name}")


def _verified_record_fingerprint(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("AI label-split verified record is missing")
    byte_count = value.get("bytes")
    digest = value.get("sha256")
    if (
        isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 0
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
    ):
        raise ValueError("AI label-split verified record fingerprint is invalid")
    return {"bytes": byte_count, "sha256": digest}


def _verified_checkpoint_fingerprint(run: Mapping[str, Any]) -> dict[str, Any]:
    checkpoint = run.get("checkpoint")
    result = _verified_record_fingerprint(checkpoint)
    if isinstance(checkpoint, Mapping) and checkpoint.get("kind") is not None:
        result["kind"] = str(checkpoint["kind"])
    if isinstance(checkpoint, Mapping) and isinstance(
        checkpoint.get("config"), Mapping
    ):
        result["config"] = _verified_record_fingerprint(checkpoint["config"])
    return result


def _path_free_record(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    cleaned = _path_free_value(value)
    return cleaned if isinstance(cleaned, dict) else None


def _path_free_execution(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    cleaned = _path_free_value(value)
    return cleaned if isinstance(cleaned, dict) else None


def _path_free_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            name = str(key)
            normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            if _PATH_KEY.search(normalized) or any(
                token in normalized
                for token in ("workingdirectory", "filepath", "filename")
            ):
                continue
            cleaned = _path_free_value(item)
            if cleaned is not _REDACTED:
                result[name] = cleaned
        return result
    if isinstance(value, (list, tuple)):
        cleaned_items = [_path_free_value(item) for item in value]
        return [item for item in cleaned_items if item is not _REDACTED]
    if isinstance(value, str) and _looks_like_path(value):
        return _REDACTED
    return value


def _looks_like_path(value: str) -> bool:
    text = value.strip()
    lowered = text.lower()
    return bool(
        text.startswith(("/", "~/", "./", "../", "\\\\"))
        or lowered.startswith("file:")
        or re.match(r"^[a-zA-Z]:[\\/]", text)
        or "/" in text
        or "\\" in text
        or lowered.endswith(_PATH_SUFFIXES)
    )


def _file_record(path: Path, *, relative_to: Path | None = None) -> dict[str, Any]:
    shown = path.relative_to(relative_to) if relative_to else path
    return {
        "path": str(shown),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_fingerprints(root: Path) -> dict[str, tuple[int, str]]:
    return {
        str(path.relative_to(root)): (path.stat().st_size, _sha256(path))
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _document_hash(document: Mapping[str, Any]) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid AI label-split JSON {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"AI label-split JSON must be an object: {path.name}")
    return value


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


__all__ = [
    "AI_LABEL_PARTITION_SCHEMA",
    "AI_LABEL_SPLIT_SCHEMA",
    "split_ai_candidate_label",
]
