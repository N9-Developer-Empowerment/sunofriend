"""Private downstream-MIDI observations for the synthetic Demucs canary.

This module deliberately compares an estimated stem with the matching clean
synthetic reference under identical existing Sunofriend transcription
settings. It does not establish absolute musical truth, select a candidate,
mutate the source graph or expose real separation through a product surface.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import stat
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ._separation_demucs_demo_evaluation import (
    _inside,
    _require_hash,
    _validate_documents,
)
from ._separation_demucs_midi_metrics import (
    _compare_drum_hits,
    _compare_note_events,
)
from .drum_roles import COMPOSITE_DRUM_PROCESSING_KIND
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent
from .transcribe_drums import DrumHit


PRIVATE_DEMUCS_MIDI_EVALUATION_SCHEMA = (
    "sunofriend.private-demucs-downstream-midi-evaluation.v1"
)
_REPORT_NAME = "private-demucs-downstream-midi-evaluation.json"
_ROLES = ("bass", "drums", "other", "vocals")
_BPM = 120.0
_TUNING_HZ = 440.0
_ONSET_TOLERANCE_SECONDS = 0.040
_PROGRAMS = {
    "bass": (0, 38),
    "drums": (9, 0),
    "other": (0, 81),
    "vocals": (0, 81),
}


def _evaluate_private_demucs_downstream_midi(
    fixture_manifest_path: str | Path,
    experiment_report_path: str | Path,
    *,
    out_dir: str | Path,
    pitched_transcriber: Callable[[Path, str], Sequence[NoteEvent]] | None = None,
    drum_transcriber: Callable[[Path], Any] | None = None,
    vocal_transcriber: Callable[[Path], Any] | None = None,
) -> dict[str, Any]:
    """Compare reference and estimated-stem transcription without promotion."""

    injected_transcribers = (
        pitched_transcriber is not None,
        drum_transcriber is not None,
        vocal_transcriber is not None,
    )
    if any(injected_transcribers) and not all(injected_transcribers):
        raise ValueError(
            "pitched, drum and vocal transcribers must all be injected together"
        )

    fixture_path = _regular_json(fixture_manifest_path, "fixture manifest")
    experiment_path = _regular_json(
        experiment_report_path,
        "experiment report",
    )
    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"Private downstream MIDI evaluation already exists: {destination}"
        )

    fixture_file_sha256 = _sha256(fixture_path)
    experiment_file_sha256 = _sha256(experiment_path)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
    _validate_documents(fixture, experiment)
    _validate_demo_policy(fixture)
    fixture_root = fixture_path.parent
    experiment_root = experiment_path.parent

    role_paths: dict[str, dict[str, Path]] = {}
    expected_hashes: dict[Path, str] = {}
    for role in _ROLES:
        reference = _inside(
            fixture_root,
            fixture["references"][role]["path"],
            f"{role} reference",
        )
        estimate = _inside(
            experiment_root,
            experiment["estimated_stems"][role]["path"],
            f"{role} estimate",
        )
        reference_hash = fixture["references"][role]["sha256"]
        estimate_hash = experiment["estimated_stems"][role]["sha256"]
        _require_hash(reference, reference_hash, f"{role} reference")
        _require_hash(estimate, estimate_hash, f"{role} estimate")
        expected_hashes[reference] = reference_hash
        expected_hashes[estimate] = estimate_hash
        role_paths[role] = {"reference": reference, "estimate": estimate}

    uses_production_transcribers = not any(injected_transcribers)
    pitched = pitched_transcriber or _production_pitched_transcriber
    drums = drum_transcriber or _production_drum_transcriber
    vocals = vocal_transcriber or _production_vocal_transcriber

    observations: dict[str, dict[str, Any]] = {}
    derived: dict[str, dict[str, dict[str, Any]]] = {}
    for role in _ROLES:
        observations[role] = {}
        derived[role] = {}
        for side in ("reference", "estimate"):
            path = role_paths[role][side]
            started = time.monotonic()
            if role == "drums":
                transcription = drums(path)
                hits = tuple(transcription.main_hits)
                notes = tuple(transcription.to_notes(include_possible=False))
                detail = {
                    "main_hit_count": len(hits),
                    "possible_hit_count": len(transcription.possible_hits),
                    "families": _counts(hit.family for hit in hits),
                }
            elif role == "vocals":
                transcription = vocals(path)
                hits = ()
                notes = tuple(transcription.notes)
                detail = {
                    "primary_variant": transcription.primary_variant,
                    "warnings": list(transcription.diagnostics.warnings),
                }
            else:
                kind = "bass" if role == "bass" else "synth"
                hits = ()
                notes = tuple(pitched(path, kind))
                detail = {"processing_kind": kind}
            _validate_notes(notes)
            notes = tuple(
                sorted(
                    notes,
                    key=lambda note: (
                        note.start,
                        note.pitch,
                        note.end,
                        note.velocity,
                    ),
                )
            )
            observations[role][side] = {
                "notes": notes,
                "hits": hits,
                "detail": detail,
                "elapsed_seconds": round(time.monotonic() - started, 6),
            }

        reference_observation = observations[role]["reference"]
        estimate_observation = observations[role]["estimate"]
        if role == "drums":
            metrics = _compare_drum_hits(
                reference_observation["hits"],
                estimate_observation["hits"],
                tolerance_seconds=_ONSET_TOLERANCE_SECONDS,
            )
        else:
            metrics = _compare_note_events(
                reference_observation["notes"],
                estimate_observation["notes"],
                tolerance_seconds=_ONSET_TOLERANCE_SECONDS,
            )
        derived[role]["metrics"] = metrics

    for path, expected_hash in expected_hashes.items():
        _require_hash(path, expected_hash, f"{path.name} transcription input")
    if _sha256(fixture_path) != fixture_file_sha256:
        raise ValueError("fixture manifest changed during MIDI evaluation")
    if _sha256(experiment_path) != experiment_file_sha256:
        raise ValueError("experiment report changed during MIDI evaluation")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o700)
    destination.chmod(0o700)
    for side in ("reference", "estimate"):
        side_dir = destination / side.upper()
        side_dir.mkdir(mode=0o700)
        side_dir.chmod(0o700)

    role_results: dict[str, Any] = {}
    for role in _ROLES:
        role_results[role] = {
            "processing_kind": _processing_kind(role),
            "comparison": derived[role]["metrics"],
        }
        for side in ("reference", "estimate"):
            observation = observations[role][side]
            notes = list(observation["notes"])
            side_dir = destination / side.upper()
            notes_path = side_dir / f"{role}.notes.json"
            midi_path = side_dir / f"{role}.mid"
            note_document = {
                "schema": "sunofriend.private-transcribed-note-evidence.v1",
                "role": role,
                "side": side,
                "source_path": str(role_paths[role][side]),
                "source_sha256": expected_hashes[role_paths[role][side]],
                "processing_kind": _processing_kind(role),
                "notes": [_note_document(note) for note in notes],
                "detail": observation["detail"],
            }
            if role == "drums":
                note_document["drum_hits"] = [
                    _drum_hit_document(hit) for hit in observation["hits"]
                ]
            _write_json(notes_path, note_document)
            channel, program = _PROGRAMS[role]
            write_midi_file(
                midi_path,
                [
                    MidiTrack(
                        name=f"{role} {side} private canary",
                        channel=channel,
                        program=program,
                        notes=notes,
                    )
                ],
                bpm=_BPM,
            )
            _make_private_file(midi_path)
            role_results[role][side] = {
                "source_path": str(role_paths[role][side]),
                "source_sha256": expected_hashes[role_paths[role][side]],
                "note_count": len(notes),
                "elapsed_seconds": observation["elapsed_seconds"],
                "detail": observation["detail"],
                "notes": _artifact(destination, notes_path),
                "midi": _artifact(destination, midi_path),
            }

    transcriber_identity = (
        _production_transcriber_identity()
        if uses_production_transcribers
        else {
            "mode": "test_injected",
            "production_identity_captured": False,
        }
    )
    document: dict[str, Any] = {
        "schema": PRIVATE_DEMUCS_MIDI_EVALUATION_SCHEMA,
        "status": "complete_observation_not_acceptance",
        "evidence_scope": "private_development_only",
        "fixture": {
            "manifest_path": str(fixture_path),
            "manifest_sha256": fixture_file_sha256,
            "document_sha256": fixture["document_sha256"],
        },
        "experiment": {
            "report_path": str(experiment_path),
            "report_sha256": experiment_file_sha256,
            "document_sha256": experiment["document_sha256"],
        },
        "policy": {
            "comparison": (
                "same existing Sunofriend transcriber and explicit settings "
                "for each clean reference and matching estimated stem"
            ),
            "measurement_layer": "seed_transcriber_only",
            "full_refine_stem_pipeline_run": False,
            "independent_audio_to_midi_evaluator_run": False,
            "renderer_or_soundfont_used": False,
            "bpm": _BPM,
            "tuning_hz": _TUNING_HZ,
            "onset_tolerance_ms": _ONSET_TOLERANCE_SECONDS * 1000.0,
            "absolute_ground_truth_claimed": False,
            "clean_reference_transcription_is_relative_baseline": True,
        },
        "transcribers": transcriber_identity,
        "roles": role_results,
        "permissions": {
            "accepted": False,
            "production_eligible": False,
            "automatic_selection": False,
            "automatic_promotion": False,
            "source_graph_activation": False,
            "public_result": False,
            "simple_mode_available": False,
            "studio_import_available": False,
        },
        "effects": {
            "source_audio_mutated": False,
            "experiment_audio_mutated": False,
            "midi_candidates_activated": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "The clean-reference transcription is a relative baseline, not absolute score truth.",
            "This first MIDI observation measures seed transcribers only; it does not run refine_stem, rendering, iterative repair or candidate variants.",
            "The broad other role contains keys and lead, so one synth transcriber cannot prove role ownership.",
            "The composite drums comparison measures current onset-family classification, not original multitrack labels.",
            "A synthetic eight-second fixture cannot establish cross-song separator acceptance.",
            "No human listening result, hidden-set result or production threshold is included.",
        ],
        "next": {
            "human_listening_required": True,
            "authorised_real_excerpt_evaluation_required": True,
            "full_production_refinement_parity_required": True,
            "studio_import_created": False,
        },
        "artifacts": _artifacts(destination),
    }
    document["document_sha256"] = _document_sha256(document)
    report_path = destination / _REPORT_NAME
    _write_json(report_path, document)
    document["report"] = str(report_path)
    return document


def _production_pitched_transcriber(
    path: Path,
    kind: str,
) -> Sequence[NoteEvent]:
    from .transcribe_pitched import transcribe_pitched_stem

    return transcribe_pitched_stem(
        str(path),
        kind=kind,
        onset_threshold=0.5,
        frame_threshold=0.3,
        min_note_ms=60.0,
    )


def _production_drum_transcriber(path: Path) -> Any:
    from .transcribe_drums import transcribe_drum_stem_detailed

    return transcribe_drum_stem_detailed(
        str(path),
        COMPOSITE_DRUM_PROCESSING_KIND,
        delta=0.18,
        possible_delta=None,
    )


def _production_vocal_transcriber(path: Path) -> Any:
    from .vocal import VocalConfig, transcribe_vocal_melody

    return transcribe_vocal_melody(
        path,
        config=VocalConfig(
            role="lead",
            tuning_hz=_TUNING_HZ,
            tuning_source="private-demo-fixture",
            bpm=_BPM,
            tracker_mode="pyin",
            phrase_repair=True,
        ),
    )


def _production_transcriber_identity() -> dict[str, Any]:
    from . import transcribe_drums, transcribe_pitched, vocal
    from .transcribe_pitched import _model_path

    modules = {}
    for name, module in (
        ("pitched", transcribe_pitched),
        ("drums", transcribe_drums),
        ("vocal", vocal),
    ):
        path = Path(module.__file__).resolve(strict=True)
        modules[name] = {
            "path": str(path),
            "sha256": _sha256(path),
        }
    model_path = Path(_model_path()).expanduser().resolve(strict=True)
    return {
        "mode": "existing_production_apis",
        "production_identity_captured": True,
        "settings": {
            "bass": {
                "api": "transcribe_pitched_stem",
                "kind": "bass",
                "onset_threshold": 0.5,
                "frame_threshold": 0.3,
                "minimum_note_ms": 60.0,
            },
            "drums": {
                "api": "transcribe_drum_stem_detailed",
                "kind": COMPOSITE_DRUM_PROCESSING_KIND,
                "delta": 0.18,
                "possible_delta": None,
            },
            "other": {
                "api": "transcribe_pitched_stem",
                "kind": "synth",
                "onset_threshold": 0.5,
                "frame_threshold": 0.3,
                "minimum_note_ms": 60.0,
            },
            "vocals": {
                "api": "transcribe_vocal_melody",
                "role": "lead",
                "tracker_mode": "pyin",
                "phrase_repair": True,
            },
        },
        "modules": modules,
        "basic_pitch_model": {
            "path": str(model_path),
            "sha256": _sha256(model_path),
            "bytes": model_path.stat().st_size,
        },
        "packages": {
            name: _package_version(name)
            for name in ("basic-pitch", "librosa", "numpy", "soundfile")
        },
    }


def _validate_demo_policy(fixture: Mapping[str, Any]) -> None:
    if fixture.get("mapping") != {
        "bass": ["bass"],
        "drums": ["kick", "snare", "hat"],
        "other": ["keys", "lead"],
        "vocals": [],
    }:
        raise ValueError("private demo role mapping changed")
    geometry = fixture.get("geometry")
    if not isinstance(geometry, Mapping) or geometry != {
        "sample_rate": 44_100,
        "channels": 2,
        "frames": 352_800,
        "duration_seconds": 8.0,
    }:
        raise ValueError("private demo geometry changed")


def _validate_notes(notes: Sequence[NoteEvent]) -> None:
    for note in notes:
        if not isinstance(note, NoteEvent):
            raise ValueError("transcriber returned a non-NoteEvent value")
        if (
            not math.isfinite(note.start)
            or not math.isfinite(note.end)
            or note.start < 0
            or note.end <= note.start
            or isinstance(note.pitch, bool)
            or not isinstance(note.pitch, int)
            or not 0 <= note.pitch <= 127
            or isinstance(note.velocity, bool)
            or not isinstance(note.velocity, int)
            or not 1 <= note.velocity <= 127
        ):
            raise ValueError("transcriber returned an invalid NoteEvent")


def _processing_kind(role: str) -> str:
    return {
        "bass": "bass",
        "drums": "composite-drums",
        "other": "synth-proxy-for-keys-plus-lead",
        "vocals": "lead-vocal-melody",
    }[role]


def _note_document(note: NoteEvent) -> dict[str, Any]:
    return {
        "start_seconds": note.start,
        "end_seconds": note.end,
        "pitch": note.pitch,
        "velocity": note.velocity,
    }


def _drum_hit_document(hit: DrumHit) -> dict[str, Any]:
    return {
        "time_seconds": hit.time,
        "gm_pitch": hit.gm_pitch,
        "velocity": hit.velocity,
        "strength": hit.strength,
        "family": hit.family,
        "tier": hit.tier,
        "provenance": hit.provenance,
        "source_time_seconds": hit.source_time,
    }


def _counts(values: Sequence[str] | Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


def _regular_json(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().absolute()
    try:
        details = path.lstat()
    except OSError as error:
        raise ValueError(
            f"{label} must be a non-empty regular non-link JSON file"
        ) from error
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or details.st_size <= 0
        or path.suffix.lower() != ".json"
    ):
        raise ValueError(f"{label} must be a non-empty regular non-link JSON file")
    return path


def _artifact(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _artifacts(root: Path) -> dict[str, Any]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("private MIDI evaluation contains a symbolic link")
        if path.is_file() and path.name != _REPORT_NAME:
            result[path.relative_to(root).as_posix()] = {
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
    return result


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _make_private_file(path: Path) -> None:
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError(f"private MIDI artifact is not a regular file: {path}")
    path.chmod(0o600)


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            document,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    _make_private_file(path)


def _document_sha256(document: Mapping[str, Any]) -> str:
    canonical = dict(document)
    canonical.pop("document_sha256", None)
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__: tuple[str, ...] = ()
