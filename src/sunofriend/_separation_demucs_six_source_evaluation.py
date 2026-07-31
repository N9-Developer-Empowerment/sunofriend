"""Private provider-leaf and MIDI evidence for the Demucs six-source challenger.

The evaluator is intentionally absent from every public product surface.  It
binds one completed six-source experiment to the exact authorised excerpt used
by an existing narrow-``other`` report, compares guitar/piano/other/residual
audio with every supplied provider leaf, and transcribes all of those signals
with one unchanged neutral pitched setting.  It creates listening evidence,
not a mapping, selection or separator acceptance.
"""

from __future__ import annotations

import html
import json
import math
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ._separation_authorised_excerpt import (
    AUTHORISED_EXCERPT_SCHEMA,
    _document_sha256 as _excerpt_document_sha256,
)
from ._separation_authorised_narrow_other import AUTHORISED_NARROW_OTHER_SCHEMA
from ._separation_authorised_role_mapping import (
    AUTHORISED_ROLE_MAPPING_SCHEMA,
    _artifact,
    _artifact_path,
    _artifacts,
    _document_sha256,
    _features,
    _make_private_tree,
    _regular_json,
    _safe_token,
    _sha256,
    _similarity,
    _verify_artifacts,
    _write_json,
)
from ._separation_demucs_midi_metrics import (
    _compare_note_events,
    _validated_notes,
)
from ._separation_demucs_private_run import (
    PRIVATE_DEMUCS_6S_EXPERIMENT_SCHEMA,
    _document_sha256 as _experiment_document_sha256,
)
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent


PRIVATE_DEMUCS_6S_EVALUATION_SCHEMA = (
    "sunofriend.private-demucs-six-source-provider-midi-evaluation.v1"
)
_REPORT_NAME = "private-six-source-provider-midi-evaluation.json"
_HTML_NAME = "six_source_provider_midi_review.html"
_CANDIDATES = ("guitar", "piano", "other", "residual")
_SAMPLE_RATE = 44_100
_ONSET_TOLERANCE_SECONDS = 0.040
_GM_PROGRAM = 4


def _evaluate_private_demucs_six_source_provider_midi(
    experiment_report_path: str | Path,
    narrow_other_report_path: str | Path,
    *,
    out_dir: str | Path,
    bpm: float,
    transcriber: Callable[[Path], Sequence[NoteEvent]] | None = None,
    renderer: Callable[[Path, Path], Any] | None = None,
) -> dict[str, Any]:
    """Create inactive audio/MIDI evidence for one exact authorised window."""

    import numpy as np
    import soundfile

    bpm = _positive_finite(bpm, "bpm")
    if (transcriber is None) != (renderer is None):
        raise ValueError("transcriber and renderer must be injected together")
    uses_production_components = transcriber is None
    transcribe = transcriber or _production_transcriber
    render = renderer or _production_renderer

    experiment_path = _regular_json(experiment_report_path, "six-source report")
    narrow_path = _regular_json(narrow_other_report_path, "narrow-other report")
    experiment_root = experiment_path.parent
    narrow_root = narrow_path.parent
    experiment_file_sha256 = _sha256(experiment_path)
    narrow_file_sha256 = _sha256(narrow_path)
    experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
    narrow = json.loads(narrow_path.read_text(encoding="utf-8"))
    binding = _validate_inputs(
        experiment_path=experiment_path,
        experiment=experiment,
        narrow_path=narrow_path,
        narrow=narrow,
    )

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"Six-source evaluation already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=destination.parent)
    )
    temporary.chmod(0o700)
    try:
        audio_dir = temporary / "AUDIO"
        midi_dir = temporary / "MIDI"
        preview_dir = temporary / "PREVIEWS"
        notes_dir = temporary / "NOTES"
        for directory in (audio_dir, midi_dir, preview_dir, notes_dir):
            directory.mkdir(mode=0o700)

        source_path = _experiment_artifact_path(
            experiment_root,
            experiment,
            "source-excerpt.wav",
            "six-source source excerpt",
        )
        if _sha256(source_path) != experiment["source"]["sha256"]:
            raise ValueError(
                "six-source source excerpt is not the authorised model derivative"
            )
        source_copy = audio_dir / "source-excerpt.wav"
        _copy_private(source_path, source_copy)

        candidate_paths = {
            role: _candidate_path(experiment_root, experiment, role)
            for role in _CANDIDATES
        }
        leaf_paths: dict[str, Path] = {}
        leaf_metadata: dict[str, dict[str, Any]] = {}
        for pack_id, leaves in sorted(narrow["leaves"].items()):
            for leaf_id, evidence in sorted(leaves.items()):
                item_id = f"{_safe_token(pack_id)}--{_safe_token(leaf_id)}"
                leaf_paths[item_id] = _artifact_path(
                    narrow_root,
                    evidence["artifact"],
                    f"{pack_id} {leaf_id} provider leaf",
                )
                leaf_metadata[item_id] = {
                    "pack_id": pack_id,
                    "leaf_id": leaf_id,
                    "display_name": evidence["display_name"],
                    "semantic_hint": evidence.get("semantic_hint"),
                    "normalised_label": evidence.get("normalised_label"),
                }

        audio_features: dict[str, Any] = {}
        observations: dict[str, Any] = {}
        all_paths = {
            **{f"candidate:{role}": path for role, path in candidate_paths.items()},
            **{f"leaf:{item_id}": path for item_id, path in leaf_paths.items()},
        }
        for item_id, source in all_paths.items():
            safe_id = _safe_token(item_id.replace(":", "-"))
            copied_audio = audio_dir / f"{safe_id}.wav"
            _copy_private(source, copied_audio)
            value, rate = soundfile.read(source, dtype="float64", always_2d=True)
            if int(rate) != _SAMPLE_RATE or value.ndim != 2 or value.shape[1] != 2:
                raise ValueError(f"{item_id} does not have 44.1 kHz stereo geometry")
            if value.shape[0] != int(experiment["source"]["frames"]):
                raise ValueError(f"{item_id} frame count differs from the fixed excerpt")
            if not np.all(np.isfinite(value)):
                raise ValueError(f"{item_id} contains non-finite samples")
            audio_features[item_id] = _features(value, sample_rate=rate, np=np)

            started = time.monotonic()
            notes = _validated_notes(tuple(transcribe(source)), item_id)
            elapsed = round(time.monotonic() - started, 6)
            notes_path = notes_dir / f"{safe_id}.notes.json"
            midi_path = midi_dir / f"{safe_id}.mid"
            preview_path = preview_dir / f"{safe_id}.wav"
            _write_json(
                notes_path,
                {
                    "schema": "sunofriend.private-six-source-note-evidence.v1",
                    "item_id": item_id,
                    "source_sha256": _sha256(source),
                    "processing_kind": "neutral-synth-proxy",
                    "notes": [_note_document(note) for note in notes],
                },
            )
            write_midi_file(
                midi_path,
                [
                    MidiTrack(
                        name=f"{item_id} private six-source review",
                        channel=0,
                        program=_GM_PROGRAM,
                        notes=list(notes),
                    )
                ],
                bpm=bpm,
            )
            midi_path.chmod(0o600)
            preview: dict[str, Any] | None = None
            if notes:
                render(midi_path, preview_path)
                preview_path.chmod(0o600)
                preview = _artifact(temporary, preview_path)
            observations[item_id] = {
                "source_audio": _artifact(temporary, copied_audio),
                "source_sha256": _sha256(source),
                "rms": round(float(np.sqrt(np.mean(value**2))), 12),
                "peak": round(float(np.max(np.abs(value))), 12),
                "note_count": len(notes),
                "pitch_minimum": min((note.pitch for note in notes), default=None),
                "pitch_maximum": max((note.pitch for note in notes), default=None),
                "elapsed_seconds": elapsed,
                "notes": _artifact(temporary, notes_path),
                "midi": _artifact(temporary, midi_path),
                "preview": preview,
                "_notes": notes,
            }

        audio_comparisons: dict[str, Any] = {}
        midi_comparisons: dict[str, Any] = {}
        rankings: dict[str, Any] = {}
        for role in _CANDIDATES:
            candidate_id = f"candidate:{role}"
            audio_comparisons[role] = {}
            midi_comparisons[role] = {}
            for leaf_item_id in sorted(leaf_paths):
                leaf_id = f"leaf:{leaf_item_id}"
                audio_comparisons[role][leaf_item_id] = _similarity(
                    audio_features[candidate_id],
                    audio_features[leaf_id],
                    np=np,
                )
                midi_comparisons[role][leaf_item_id] = _compare_note_events(
                    observations[leaf_id]["_notes"],
                    observations[candidate_id]["_notes"],
                    tolerance_seconds=_ONSET_TOLERANCE_SECONDS,
                )
            audio_rank = sorted(
                leaf_paths,
                key=lambda item: (
                    -audio_comparisons[role][item]["evidence_similarity"],
                    item,
                ),
            )
            midi_rank = sorted(
                leaf_paths,
                key=lambda item: (*_midi_sort_key(midi_comparisons[role][item]), item),
            )
            rankings[role] = {
                "audio_leaf_ids": audio_rank,
                "midi_leaf_ids": midi_rank,
                "audio_nearest_leaf_id": audio_rank[0],
                "midi_nearest_leaf_id": midi_rank[0],
                "same_nearest_leaf": audio_rank[0] == midi_rank[0],
                "accepted": False,
            }

        for observation in observations.values():
            observation.pop("_notes")

        review_path = temporary / _HTML_NAME
        review_path.write_text(
            _review_html(
                observations=observations,
                leaf_metadata=leaf_metadata,
                audio_comparisons=audio_comparisons,
                midi_comparisons=midi_comparisons,
                rankings=rankings,
                track_id=binding["track_id"],
            ),
            encoding="utf-8",
        )
        review_path.chmod(0o600)

        _verify_artifacts(experiment_root, experiment["artifacts"], "six-source")
        _verify_artifacts(narrow_root, narrow["artifacts"], "narrow-other")
        if _sha256(experiment_path) != experiment_file_sha256:
            raise ValueError("six-source report changed during evaluation")
        if _sha256(narrow_path) != narrow_file_sha256:
            raise ValueError("narrow-other report changed during evaluation")

        document: dict[str, Any] = {
            "schema": PRIVATE_DEMUCS_6S_EVALUATION_SCHEMA,
            "status": "complete_observation_not_acceptance",
            "evidence_scope": "private_development_only",
            "bindings": {
                **binding,
                "experiment_report_sha256": experiment_file_sha256,
                "experiment_document_sha256": experiment["document_sha256"],
                "narrow_other_report_sha256": narrow_file_sha256,
                "narrow_other_document_sha256": narrow["document_sha256"],
            },
            "policy": {
                "audio_similarity": "same existing spectral-envelope-waveform evidence",
                "midi_transcriber": "same neutral synth-proxy Basic Pitch settings for every candidate and provider leaf",
                "bpm": bpm,
                "gm_program_zero_based": _GM_PROGRAM,
                "onset_tolerance_ms": _ONSET_TOLERANCE_SECONDS * 1000.0,
                "labels_contribute_to_audio_or_midi_score": False,
                "metrics_are_descriptive_not_acceptance": True,
            },
            "components": (
                _production_component_identity()
                if uses_production_components
                else {"mode": "test_injected"}
            ),
            "leaf_metadata": leaf_metadata,
            "observations": observations,
            "audio_comparisons": audio_comparisons,
            "midi_comparisons": midi_comparisons,
            "rankings": rankings,
            "review": {
                "html": _artifact(temporary, review_path),
                "human_listening_required": True,
                "review_recorded": False,
            },
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
                "provider_audio_mutated": False,
                "midi_candidates_created": True,
                "midi_candidates_activated": False,
                "source_graph_mutated": False,
            },
            "limitations": [
                "Provider leaves and six-source estimates can contain bleed or several instruments.",
                "A nearest audio or MIDI neighbour is not an instrument identity or accuracy score.",
                "The neutral synth proxy tests usable note geometry, not matching timbre.",
                "The residual is accounting audio and can contain valid music plus model error.",
                "Human listening remains required and no result is selected or promoted.",
            ],
            "next": {
                "human_listening_required": True,
                "six_source_acceptance_allowed": False,
                "automatic_mapping_selection_allowed": False,
            },
        }
        document["artifacts"] = _artifacts(temporary)
        document["document_sha256"] = _document_sha256(document)
        report_path = temporary / _REPORT_NAME
        _write_json(report_path, document)
        _make_private_tree(temporary)
        if os.path.lexists(destination):
            raise FileExistsError(f"Six-source output appeared during run: {destination}")
        os.rename(temporary, destination)
        document["report"] = str(destination / _REPORT_NAME)
        return document
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _validate_inputs(
    *,
    experiment_path: Path,
    experiment: Mapping[str, Any],
    narrow_path: Path,
    narrow: Mapping[str, Any],
) -> dict[str, Any]:
    experiment_root = experiment_path.parent
    narrow_root = narrow_path.parent
    if experiment.get("schema") != PRIVATE_DEMUCS_6S_EXPERIMENT_SCHEMA:
        raise ValueError("unsupported six-source experiment schema")
    if experiment.get("status") != "complete_review_required":
        raise ValueError("six-source experiment is not complete review-required evidence")
    if experiment.get("document_sha256") != _experiment_document_sha256(experiment):
        raise ValueError("six-source experiment document hash changed")
    _verify_artifacts(experiment_root, experiment.get("artifacts"), "six-source")
    if any(experiment.get("permissions", {}).values()):
        raise ValueError("six-source experiment contains an enabled permission")

    if narrow.get("schema") != AUTHORISED_NARROW_OTHER_SCHEMA:
        raise ValueError("unsupported narrow-other evidence schema")
    if narrow.get("document_sha256") != _document_sha256(narrow):
        raise ValueError("narrow-other document hash changed")
    _verify_artifacts(narrow_root, narrow.get("artifacts"), "narrow-other")

    mapping_evidence = narrow.get("source_role_mapping", {})
    mapping_path = _regular_json(mapping_evidence.get("report_path", ""), "role mapping")
    if _sha256(mapping_path) != mapping_evidence.get("report_sha256"):
        raise ValueError("role mapping report hash changed")
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    if mapping.get("schema") != AUTHORISED_ROLE_MAPPING_SCHEMA:
        raise ValueError("unsupported role mapping schema")
    if mapping.get("document_sha256") != _document_sha256(mapping):
        raise ValueError("role mapping document hash changed")
    _verify_artifacts(mapping_path.parent, mapping.get("artifacts"), "role mapping")

    excerpt_evidence = mapping.get("source_excerpt", {})
    excerpt_path = _regular_json(excerpt_evidence.get("report_path", ""), "excerpt report")
    if _sha256(excerpt_path) != excerpt_evidence.get("report_sha256"):
        raise ValueError("authorised excerpt report hash changed")
    excerpt = json.loads(excerpt_path.read_text(encoding="utf-8"))
    if excerpt.get("schema") != AUTHORISED_EXCERPT_SCHEMA:
        raise ValueError("unsupported authorised excerpt schema")
    if excerpt.get("document_sha256") != _excerpt_document_sha256(excerpt):
        raise ValueError("authorised excerpt document hash changed")
    _verify_artifacts(excerpt_path.parent, excerpt.get("artifacts"), "excerpt")
    model_input = _artifact_path(
        excerpt_path.parent,
        {
            "path": "LOCAL-MODEL-INPUT/source-44100.wav",
            **excerpt["artifacts"]["LOCAL-MODEL-INPUT/source-44100.wav"],
        },
        "authorised model input",
    )
    if _sha256(model_input) != experiment.get("source", {}).get("sha256"):
        raise ValueError("six-source input is not the authorised model derivative")
    geometry = excerpt.get("original", {}).get("local_model_input", {}).get(
        "geometry", {}
    )
    source = experiment.get("source", {})
    if (
        int(source.get("sample_rate", 0)) != int(geometry.get("sample_rate", 0))
        or int(source.get("frames", 0)) != int(geometry.get("frames", 0))
        or int(source.get("channels", 0)) != int(geometry.get("channels", 0))
    ):
        raise ValueError("six-source and authorised excerpt geometry differ")
    return {
        "track_id": mapping_evidence["track_id"],
        "start_seconds": mapping_evidence["start_seconds"],
        "end_seconds": mapping_evidence["end_seconds"],
        "authorised_model_input_sha256": _sha256(model_input),
        "role_mapping_report_sha256": _sha256(mapping_path),
        "authorised_excerpt_report_sha256": _sha256(excerpt_path),
    }


def _candidate_path(root: Path, report: Mapping[str, Any], role: str) -> Path:
    if role == "residual":
        evidence = report["additive_accounting"]["source_minus_estimated_sum"]
        if evidence.get("pcm24_persisted") is not True:
            raise ValueError("six-source residual is not a persisted PCM24 WAV")
    else:
        evidence = report["estimated_stems"][role]
    return _experiment_artifact_path(root, report, evidence["path"], role)


def _experiment_artifact_path(
    root: Path,
    report: Mapping[str, Any],
    relative: str,
    label: str,
) -> Path:
    artifact = report["artifacts"].get(relative)
    if not isinstance(artifact, Mapping):
        raise ValueError(f"{label} is absent from the experiment artifact manifest")
    return _artifact_path(root, {"path": relative, **artifact}, label)


def _production_transcriber(path: Path) -> Sequence[NoteEvent]:
    from .transcribe_pitched import transcribe_pitched_stem

    return transcribe_pitched_stem(
        str(path),
        kind="synth",
        onset_threshold=0.5,
        frame_threshold=0.3,
        min_note_ms=60.0,
    )


def _production_renderer(midi_path: Path, wav_path: Path) -> None:
    from .render import render_midi_to_wav

    render_midi_to_wav(midi_path, wav_path)


def _production_component_identity() -> dict[str, Any]:
    from . import render, transcribe_pitched
    from .transcribe_pitched import _model_path

    basic_pitch_model = Path(_model_path()).expanduser().resolve(strict=True)
    return {
        "mode": "existing_production_apis",
        "settings": {
            "transcriber": "transcribe_pitched_stem",
            "kind": "synth",
            "onset_threshold": 0.5,
            "frame_threshold": 0.3,
            "minimum_note_ms": 60.0,
            "renderer": "render_midi_to_wav",
        },
        "modules": {
            "evaluator_sha256": _sha256(Path(__file__).resolve()),
            "transcriber_sha256": _sha256(Path(transcribe_pitched.__file__).resolve()),
            "renderer_sha256": _sha256(Path(render.__file__).resolve()),
        },
        "basic_pitch_model": {
            "sha256": _sha256(basic_pitch_model),
            "bytes": basic_pitch_model.stat().st_size,
        },
    }


def _midi_sort_key(metrics: Mapping[str, Any]) -> tuple[float, float, float]:
    def score(name: str) -> float:
        value = metrics[name]["f1"]
        return -float(value) if value is not None else 1.0

    return (score("exact_pitch_onset"), score("chroma_onset"), score("onset_only"))


def _review_html(
    *,
    observations: Mapping[str, Mapping[str, Any]],
    leaf_metadata: Mapping[str, Mapping[str, Any]],
    audio_comparisons: Mapping[str, Mapping[str, Mapping[str, Any]]],
    midi_comparisons: Mapping[str, Mapping[str, Mapping[str, Any]]],
    rankings: Mapping[str, Mapping[str, Any]],
    track_id: str,
) -> str:
    sections = []
    for role in _CANDIDATES:
        candidate = observations[f"candidate:{role}"]
        rows = []
        for leaf_id in rankings[role]["audio_leaf_ids"][:5]:
            meta = leaf_metadata[leaf_id]
            leaf = observations[f"leaf:{leaf_id}"]
            midi_f1 = midi_comparisons[role][leaf_id]["exact_pitch_onset"]["f1"]
            rows.append(
                "<li><strong>"
                + html.escape(str(meta["display_name"]))
                + "</strong> — audio similarity "
                + f"{audio_comparisons[role][leaf_id]['evidence_similarity']:.3f}"
                + ", exact-pitch/onset F1 "
                + ("n/a" if midi_f1 is None else f"{midi_f1:.3f}")
                + f"<br><audio controls src=\"{html.escape(leaf['source_audio']['path'])}\"></audio>"
                + _preview_audio(leaf)
                + "</li>"
            )
        sections.append(
            f"<section><h2>{html.escape(role.title())}</h2>"
            f"<p>Raw six-source estimate, RMS {candidate['rms']:.6f}; "
            f"neutral MIDI has {candidate['note_count']} notes.</p>"
            f"<audio controls src=\"{html.escape(candidate['source_audio']['path'])}\"></audio>"
            + _preview_audio(candidate)
            + "<h3>Five nearest provider leaves by audio evidence</h3><ol>"
            + "".join(rows)
            + "</ol></section>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Six-source private review</title>
<style>body{{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;background:#0c1420;color:#edf6ff}}section{{border:1px solid #38506a;border-radius:12px;padding:1rem;margin:1rem 0}}audio{{width:min(100%,520px);display:block;margin:.4rem 0}}code{{color:#78d8ff}}li{{margin:1rem 0}}</style></head>
<body><h1>Sunofriend six-source private review</h1>
<p><strong>{html.escape(track_id)}</strong>. Compare each raw estimate and its neutral same-patch MIDI with provider leaves. The order is descriptive only. It does not identify an instrument, select MIDI or accept a separator.</p>
<p>Original fixed excerpt:</p><audio controls src="AUDIO/source-excerpt.wav"></audio>
{''.join(sections)}
</body></html>"""


def _preview_audio(observation: Mapping[str, Any]) -> str:
    preview = observation.get("preview")
    if not isinstance(preview, Mapping):
        return "<p>No note-bearing neutral MIDI preview.</p>"
    return (
        f"<p>Neutral MIDI preview ({observation['note_count']} notes):</p>"
        f"<audio controls src=\"{html.escape(str(preview['path']))}\"></audio>"
    )


def _copy_private(source: Path, target: Path) -> None:
    with source.open("rb") as read_handle, target.open("xb") as write_handle:
        shutil.copyfileobj(read_handle, write_handle, length=1024 * 1024)
        write_handle.flush()
        os.fsync(write_handle.fileno())
    target.chmod(0o600)


def _note_document(note: NoteEvent) -> dict[str, Any]:
    return {
        "start_seconds": note.start,
        "end_seconds": note.end,
        "pitch": note.pitch,
        "velocity": note.velocity,
    }


def _positive_finite(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a positive finite number")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{label} must be a positive finite number")
    return result


__all__: tuple[str, ...] = ()
