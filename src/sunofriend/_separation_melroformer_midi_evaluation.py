"""Inactive downstream vocal-MIDI evaluation for one MelRoFormer result."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_midi_comparison import (
    AUTHORISED_MIDI_COMPARISON_SCHEMA,
    _artifact_path,
    _artifacts,
    _document_sha256,
    _make_private_tree,
    _persist_candidate,
    _production_component_identity,
    _regular_json,
    _sha256,
    _verify_artifacts,
    _write_json,
)
from ._separation_demucs_midi_metrics import _compare_note_events
from ._separation_demucs_refinement_evaluation import _validated_notes
from ._separation_melroformer_authorised_worker import (
    _validate_private_melroformer_authorised_worker,
)
from .models import NoteEvent
from .vocal import VocalConfig, transcribe_vocal_melody


SCHEMA = "sunofriend.private-melroformer-downstream-vocal-midi-evaluation.v1"
_REPORT_NAME = "private-melroformer-vocal-midi-evaluation.json"
_CONTROL_PACKS = ("local-htdemucs", "moises", "suno-a", "suno-b")


def _evaluate_private_melroformer_vocal_midi(
    worker_observation_path: str | Path,
    control_comparison_path: str | Path,
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Apply the unchanged control transcriber and compare note evidence."""

    worker_path = _regular_json(worker_observation_path, "worker observation")
    worker_sha256 = _sha256(worker_path)
    worker = _validate_private_melroformer_authorised_worker(
        json.loads(worker_path.read_text(encoding="utf-8"))
    )
    worker_root = worker_path.parent
    vocals_claim = next(
        item for item in worker["quarantine"]["outputs"] if item["role"] == "vocals"
    )
    vocals_path = _artifact_path(
        worker_root,
        {
            "path": "output/STEMS/vocals.wav",
            "bytes": vocals_claim["bytes"],
            "sha256": vocals_claim["sha256"],
        },
        "MelRoFormer quarantined vocals",
    )

    control_path = _regular_json(control_comparison_path, "control comparison")
    control_root = control_path.parent
    control_sha256 = _sha256(control_path)
    control = json.loads(control_path.read_text(encoding="utf-8"))
    if control.get("schema") != AUTHORISED_MIDI_COMPARISON_SCHEMA:
        raise ValueError("unsupported authorised MIDI comparison schema")
    if control.get("document_sha256") != _document_sha256(control):
        raise ValueError("authorised MIDI comparison document hash changed")
    _verify_artifacts(control_root, control.get("artifacts"))
    policy = control.get("policy", {})
    if (
        policy.get("bpm") != 136.0
        or policy.get("tuning_hz") != 440.0
        or policy.get("vocal_role_uses_separate_production_dominant_contour")
        is not True
        or policy.get("same_role_uses_identical_settings_across_every_pack")
        is not True
    ):
        raise ValueError("authorised MIDI control policy differs")
    controls = _load_control_notes(control_root, control)

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"MelRoFormer vocal MIDI evaluation already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=destination.parent)
    )
    temporary.chmod(0o700)
    try:
        role_out = temporary / "kim-vocal-2" / "vocals"
        role_out.mkdir(parents=True, mode=0o700)
        started = time.monotonic()
        transcription = transcribe_vocal_melody(
            vocals_path,
            config=VocalConfig(
                role="lead",
                tuning_hz=440.0,
                tuning_source="authorised-midi-comparison-explicit",
                bpm=136.0,
                tracker_mode="pyin",
                phrase_repair=True,
            ),
        )
        notes = _validated_notes(transcription.notes)
        from .evaluate import evaluate_stem_midi
        from .render import render_midi_to_wav

        candidate = _persist_candidate(
            root=temporary,
            role_out=role_out,
            label="primary",
            source=vocals_path,
            role="vocals",
            notes=notes,
            bpm=136.0,
            render=render_midi_to_wav,
            evaluate=evaluate_stem_midi,
        )
        comparisons = {
            pack_id: {
                "control_note_count": len(control_notes),
                "candidate_note_count": len(notes),
                "comparison": _compare_note_events(
                    control_notes,
                    notes,
                    tolerance_seconds=0.040,
                ),
                "reference_semantics": (
                    "control MIDI is a relative comparison baseline, not score truth"
                ),
            }
            for pack_id, control_notes in controls.items()
        }
        if _sha256(worker_path) != worker_sha256 or _sha256(vocals_path) != vocals_claim[
            "sha256"
        ]:
            raise ValueError("MelRoFormer worker evidence changed during MIDI evaluation")
        if _sha256(control_path) != control_sha256:
            raise ValueError("authorised MIDI controls changed during evaluation")
        _verify_artifacts(control_root, control.get("artifacts"))

        document: dict[str, Any] = {
            "schema": SCHEMA,
            "status": "complete_observation_not_acceptance",
            "evidence_scope": "private_development_only",
            "worker": {
                "observation_sha256": worker_sha256,
                "evidence_sha256": worker["evidence_sha256"],
                "candidate_id": worker["model"]["candidate_id"],
                "checkpoint_sha256": worker["model"]["checkpoint_sha256"],
                "authorisation_report_sha256": worker["artifacts"][
                    "authorisation_report_sha256"
                ],
                "vocal_pcm24_sha256": vocals_claim["sha256"],
                "vocal_pcm24_bytes": vocals_claim["bytes"],
                "network_denial_bound_to_model_worker": worker["conclusion"][
                    "network_denial_bound_to_model_worker"
                ],
                "pcm24_quarantine_bound_to_model_worker": worker["conclusion"][
                    "pcm24_quarantine_bound_to_model_worker"
                ],
            },
            "controls": {
                "comparison_sha256": control_sha256,
                "document_sha256": control["document_sha256"],
                "packs": list(_CONTROL_PACKS),
                "note_counts": {
                    pack_id: len(control_notes)
                    for pack_id, control_notes in controls.items()
                },
            },
            "policy": {
                "bpm": 136.0,
                "tuning_hz": 440.0,
                "role": "lead",
                "tracker_mode": "pyin",
                "phrase_repair": True,
                "onset_tolerance_ms": 40.0,
                "same_production_vocal_settings_as_controls": True,
                "absolute_ground_truth_claimed": False,
                "winner_selected": False,
            },
            "components": _production_component_identity(),
            "candidate": {
                "method": {
                    "pipeline": "production_vocal_dominant_contour",
                    "primary_variant": transcription.primary_variant,
                    "diagnostics": transcription.diagnostics.to_dict(),
                },
                "primary": candidate,
                "elapsed_seconds": round(time.monotonic() - started, 6),
            },
            "comparisons_to_existing_controls": comparisons,
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
                "inactive_midi_created": True,
                "dry_proxy_audition_created": candidate["render"] is not None,
                "source_graph_mutated": False,
                "worker_rerun": False,
            },
            "limitations": [
                "Every control is an estimated vocal stem, not score truth.",
                "The production vocal path reduces the source to one dominant monophonic contour.",
                "Pairwise MIDI agreement is not melody accuracy or listening preference.",
                "One 15-second excerpt cannot establish cross-song acceptance.",
                "The dry General MIDI audition is not a GarageBand patch recommendation.",
            ],
            "next": {
                "equal_level_blind_listening_required": True,
                "cross_song_repetition_required": True,
                "studio_import_created": False,
            },
        }
        document["artifacts"] = _artifacts(temporary)
        document["document_sha256"] = _document_sha256(document)
        report_path = temporary / _REPORT_NAME
        _write_json(report_path, document)
        _make_private_tree(temporary)
        if os.path.lexists(destination):
            raise FileExistsError(
                "MelRoFormer vocal MIDI evaluation output appeared during run"
            )
        os.rename(temporary, destination)
        document["report"] = str(destination / _REPORT_NAME)
        return document
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _load_control_notes(
    root: Path, document: Mapping[str, Any]
) -> dict[str, tuple[NoteEvent, ...]]:
    packs = document.get("packs")
    if not isinstance(packs, Mapping) or set(packs) != set(_CONTROL_PACKS):
        raise ValueError("authorised MIDI controls differ")
    result = {}
    for pack_id in _CONTROL_PACKS:
        try:
            raw = packs[pack_id]["vocals"]["primary"]["notes"]
        except (KeyError, TypeError) as error:
            raise ValueError("authorised vocal control evidence is incomplete") from error
        path = _artifact_path(root, raw, f"{pack_id} vocal note evidence")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            payload.get("schema")
            != "sunofriend.private-authorised-midi-note-evidence.v1"
            or payload.get("role") != "vocals"
            or payload.get("candidate") != "primary"
            or not isinstance(payload.get("notes"), list)
        ):
            raise ValueError("authorised vocal control note evidence differs")
        result[pack_id] = _validated_notes(
            tuple(
                NoteEvent(
                    start=float(note["start_seconds"]),
                    end=float(note["end_seconds"]),
                    pitch=int(note["pitch"]),
                    velocity=int(note["velocity"]),
                )
                for note in payload["notes"]
            )
        )
    return result


__all__ = ["SCHEMA", "_evaluate_private_melroformer_vocal_midi"]
