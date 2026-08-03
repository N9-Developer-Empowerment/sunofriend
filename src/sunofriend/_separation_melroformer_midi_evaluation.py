"""Inactive downstream vocal-MIDI evaluation for one MelRoFormer result."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import stat
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
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_melroformer_native_attempt_darwin import (
    _EVIDENCE_SCHEMA as _NATIVE_ATTEMPT_EVIDENCE_SCHEMA,
    _inspect_attempt_pcm24,
)
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from .models import NoteEvent
from .vocal import VocalConfig, transcribe_vocal_melody


SCHEMA = "sunofriend.private-melroformer-downstream-vocal-midi-evaluation.v2"
_REPORT_NAME = "private-melroformer-vocal-midi-evaluation.json"
_SUPPORTED_CONTROL_PACKS = ("local-htdemucs", "moises", "suno-a", "suno-b")
_REGISTER_HYPOTHESES = (
    "lowest_line",
    "dominant_line",
    "top_line",
    "harmony_stack",
)


def _evaluate_private_melroformer_vocal_midi(
    worker_observation_path: str | Path,
    control_comparison_path: str | Path,
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Apply the unchanged control transcriber and compare note evidence."""

    worker_path = _regular_json(worker_observation_path, "worker observation")
    worker_sha256 = _sha256(worker_path)
    worker, vocals_path = _load_verified_vocal_source(worker_path)

    control_path = _regular_json(control_comparison_path, "control comparison")
    control_root = control_path.parent
    control_sha256 = _sha256(control_path)
    control = json.loads(control_path.read_text(encoding="utf-8"))
    if control.get("schema") != AUTHORISED_MIDI_COMPARISON_SCHEMA:
        raise ValueError("unsupported authorised MIDI comparison schema")
    if control.get("document_sha256") != _document_sha256(control):
        raise ValueError("authorised MIDI comparison document hash changed")
    _verify_artifacts(control_root, control.get("artifacts"))
    bpm, tuning_hz = _validated_control_policy(control.get("policy"))
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
        lead_transcription = transcribe_vocal_melody(
            vocals_path,
            config=VocalConfig(
                role="lead",
                tuning_hz=tuning_hz,
                tuning_source="authorised-midi-comparison-explicit",
                bpm=bpm,
                tracker_mode="pyin",
                phrase_repair=True,
            ),
        )
        lead_notes = _validated_notes(lead_transcription.notes)
        polyphonic_transcription = transcribe_vocal_melody(
            vocals_path,
            config=VocalConfig(
                role="backing",
                tuning_hz=tuning_hz,
                tuning_source="authorised-midi-comparison-explicit",
                bpm=bpm,
            ),
        )
        from .evaluate import evaluate_stem_midi
        from .render import render_midi_to_wav

        lead_candidate = _persist_candidate(
            root=temporary,
            role_out=role_out,
            label="primary",
            source=vocals_path,
            role="vocals",
            notes=lead_notes,
            bpm=bpm,
            render=render_midi_to_wav,
            evaluate=evaluate_stem_midi,
        )
        comparisons = _compare_to_controls(lead_notes, controls)
        register_hypotheses: dict[str, Any] = {}
        for variant in _REGISTER_HYPOTHESES:
            variant_notes = _validated_notes(
                polyphonic_transcription.variants.get(variant, ())
            )
            if not variant_notes:
                continue
            persisted = _persist_candidate(
                root=temporary,
                role_out=role_out,
                label=f"hypothesis-{variant}",
                source=vocals_path,
                role="vocals",
                notes=variant_notes,
                bpm=bpm,
                render=render_midi_to_wav,
                evaluate=evaluate_stem_midi,
            )
            register_hypotheses[variant] = {
                "semantics": (
                    "audition-only register hypothesis; not an inferred lead or "
                    "backing-vocal assignment"
                ),
                "candidate": persisted,
                "comparisons_to_existing_controls": _compare_to_controls(
                    variant_notes, controls
                ),
            }
        if (
            _sha256(worker_path) != worker_sha256
            or _sha256(vocals_path) != worker["vocal_pcm24_sha256"]
            or _load_verified_vocal_source(worker_path) != (worker, vocals_path)
        ):
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
                **worker,
            },
            "controls": {
                "comparison_sha256": control_sha256,
                "document_sha256": control["document_sha256"],
                "packs": list(controls),
                "note_counts": {
                    pack_id: len(control_notes)
                    for pack_id, control_notes in controls.items()
                },
            },
            "policy": {
                "bpm": bpm,
                "tuning_hz": tuning_hz,
                "role": "lead",
                "tracker_mode": "pyin",
                "phrase_repair": True,
                "polyphonic_tracker": "basic_pitch",
                "register_hypotheses": list(_REGISTER_HYPOTHESES),
                "onset_tolerance_ms": 40.0,
                "same_production_vocal_settings_as_controls": True,
                "absolute_ground_truth_claimed": False,
                "winner_selected": False,
                "lead_backing_role_assignment_inferred": False,
                "lowest_register_is_lead_claimed": False,
            },
            "components": _production_component_identity(),
            "candidate": {
                "method": {
                    "pipeline": "production_vocal_dominant_contour",
                    "primary_variant": lead_transcription.primary_variant,
                    "diagnostics": lead_transcription.diagnostics.to_dict(),
                },
                "primary": lead_candidate,
                "register_hypotheses": {
                    "method": {
                        "pipeline": "production_backing_vocal_voice_selector",
                        "primary_unchanged": True,
                        "diagnostics": polyphonic_transcription.diagnostics.to_dict(),
                    },
                    "variants": register_hypotheses,
                },
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
                "dry_proxy_audition_created": lead_candidate["render"] is not None,
                "register_hypothesis_auditions_created": any(
                    value["candidate"]["render"] is not None
                    for value in register_hypotheses.values()
                ),
                "source_graph_mutated": False,
                "worker_rerun": False,
            },
            "limitations": [
                "Every control is an estimated vocal stem, not score truth.",
                "The production vocal path reduces the source to one dominant monophonic contour.",
                "Lowest, dominant and top register lanes can each switch singer or follow a harmonic within one excerpt.",
                "A lower register is not automatically the lead voice and a higher register is not automatically backing.",
                "Pairwise MIDI agreement is not melody accuracy or listening preference.",
                "One 15-second excerpt cannot establish cross-song acceptance.",
                "The dry General MIDI audition is not a GarageBand patch recommendation.",
            ],
            "next": {
                "equal_level_blind_listening_required": True,
                "lead_backing_identity_listening_required": True,
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


def _load_verified_vocal_source(
    evidence_path: Path,
) -> tuple[dict[str, Any], Path]:
    """Normalize legacy and fixed-native evidence without widening permissions."""

    raw = json.loads(evidence_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("MelRoFormer worker evidence must be a JSON object")
    if raw.get("schema") == _NATIVE_ATTEMPT_EVIDENCE_SCHEMA:
        return _load_native_attempt_vocal_source(evidence_path, raw)

    worker = _validate_private_melroformer_authorised_worker(raw)
    vocals_claim = next(
        item for item in worker["quarantine"]["outputs"] if item["role"] == "vocals"
    )
    vocals_path = _artifact_path(
        evidence_path.parent,
        {
            "path": "output/STEMS/vocals.wav",
            "bytes": vocals_claim["bytes"],
            "sha256": vocals_claim["sha256"],
        },
        "MelRoFormer quarantined vocals",
    )
    return (
        {
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
        vocals_path,
    )


def _load_native_attempt_vocal_source(
    evidence_path: Path,
    document: Mapping[str, Any],
) -> tuple[dict[str, Any], Path]:
    payload = dict(document)
    evidence_sha256 = payload.pop("evidence_sha256", None)
    bindings = document.get("bindings")
    conclusion = document.get("conclusion")
    permissions = document.get("permissions")
    outputs = document.get("outputs")
    if (
        document.get("status") != "private_native_attempt_verified_not_selected"
        or document.get("evidence_scope")
        != "private_local_execution_and_output_binding_only"
        or document.get("candidate_id") != "mlx-melroformer-kim-vocal-2"
        or not _is_sha256(evidence_sha256)
        or evidence_sha256
        != hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        or not isinstance(bindings, Mapping)
        or bindings.get("checkpoint_sha256") != CONVERSION_CHECKPOINT_SHA256
        or bindings.get("checkpoint_bytes") != CONVERSION_CHECKPOINT_BYTES
        or any(
            not _is_sha256(bindings.get(name))
            for name in (
                "request_sha256",
                "terminal_receipt_sha256",
                "worker_source_sha256",
                "authorisation_report_sha256",
                "source_manifest_sha256",
                "companion_manifest_sha256",
            )
        )
        or not isinstance(conclusion, Mapping)
        or any(
            conclusion.get(name) is not True
            for name in (
                "native_execution_terminal",
                "network_denial_bound_to_model_worker",
                "pcm24_quarantine_bound_to_model_worker",
                "parent_staging_verification_complete",
                "checkpoint_remeasured_and_closed",
            )
        )
        or conclusion.get("listening_quality_established") is not False
        or not isinstance(permissions, Mapping)
        or set(permissions)
        != {
            "accepted",
            "automatic_selection",
            "source_graph_activation",
            "simple_mode_available",
            "studio_import_available",
            "product_route_permitted",
            "publication_permitted",
        }
        or any(value is not False for value in permissions.values())
        or not isinstance(outputs, list)
        or len(outputs) != 2
    ):
        raise ValueError("private Kim native attempt evidence differs")

    _validate_native_attempt_receipt(evidence_path.parent, bindings)

    output_by_role = {
        item.get("role"): item for item in outputs if isinstance(item, Mapping)
    }
    if set(output_by_role) != {"instrumental", "vocals"}:
        raise ValueError("private Kim native attempt outputs differ")
    for role in ("instrumental", "vocals"):
        if dict(output_by_role[role]) != dict(
            _inspect_attempt_pcm24(evidence_path.parent, role=role)
        ):
            raise ValueError("private Kim native attempt output changed")

    vocals_claim = output_by_role["vocals"]
    return (
        {
            "evidence_sha256": evidence_sha256,
            "candidate_id": document["candidate_id"],
            "checkpoint_sha256": bindings["checkpoint_sha256"],
            "authorisation_report_sha256": bindings[
                "authorisation_report_sha256"
            ],
            "vocal_pcm24_sha256": vocals_claim["sha256"],
            "vocal_pcm24_bytes": vocals_claim["bytes"],
            "network_denial_bound_to_model_worker": conclusion[
                "network_denial_bound_to_model_worker"
            ],
            "pcm24_quarantine_bound_to_model_worker": conclusion[
                "pcm24_quarantine_bound_to_model_worker"
            ],
        },
        evidence_path.parent / "staging" / "quarantine" / "STEMS" / "vocals.wav",
    )


def _validate_native_attempt_receipt(
    attempt_root: Path,
    bindings: Mapping[str, Any],
) -> None:
    path = attempt_root / "native-attempt-receipt.json"
    try:
        state = path.lstat()
    except OSError as error:
        raise ValueError("private Kim native terminal receipt is missing") from error
    if (
        stat.S_ISLNK(state.st_mode)
        or not stat.S_ISREG(state.st_mode)
        or state.st_nlink != 1
        or state.st_uid != os.geteuid()
        or stat.S_IMODE(state.st_mode) != 0o600
        or not 1 <= state.st_size <= 2 * 1024 * 1024
    ):
        raise ValueError("private Kim native terminal receipt differs")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(receipt, Mapping):
        raise ValueError("private Kim native terminal receipt differs")
    payload = dict(receipt)
    receipt_sha256 = payload.pop("receipt_sha256", None)
    lifecycle = receipt.get("lifecycle")
    receipt_permissions = receipt.get("permissions")
    if (
        receipt.get("schema")
        != "sunofriend.private-melroformer-native-coordinator.v1"
        or receipt.get("status")
        != "private_native_worker_complete_and_terminal"
        or receipt.get("request_sha256") != bindings["request_sha256"]
        or receipt_sha256 != bindings["terminal_receipt_sha256"]
        or receipt_sha256
        != hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        or not isinstance(lifecycle, Mapping)
        or not lifecycle
        or any(value is not True for value in lifecycle.values())
        or not isinstance(receipt_permissions, Mapping)
        or not receipt_permissions
        or any(value is not False for value in receipt_permissions.values())
    ):
        raise ValueError("private Kim native terminal receipt differs")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _compare_to_controls(
    notes: tuple[NoteEvent, ...],
    controls: Mapping[str, tuple[NoteEvent, ...]],
) -> dict[str, Any]:
    return {
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


def _validated_control_policy(value: object) -> tuple[float, float]:
    if not isinstance(value, Mapping):
        raise ValueError("authorised MIDI control policy differs")
    bpm = value.get("bpm")
    tuning_hz = value.get("tuning_hz")
    if (
        isinstance(bpm, bool)
        or not isinstance(bpm, (int, float))
        or not math.isfinite(float(bpm))
        or not 20.0 <= float(bpm) <= 400.0
        or isinstance(tuning_hz, bool)
        or not isinstance(tuning_hz, (int, float))
        or not math.isfinite(float(tuning_hz))
        or not 400.0 <= float(tuning_hz) <= 480.0
        or value.get("vocal_role_uses_separate_production_dominant_contour")
        is not True
        or value.get("same_role_uses_identical_settings_across_every_pack")
        is not True
    ):
        raise ValueError("authorised MIDI control policy differs")
    return float(bpm), float(tuning_hz)


def _load_control_notes(
    root: Path, document: Mapping[str, Any]
) -> dict[str, tuple[NoteEvent, ...]]:
    packs = document.get("packs")
    if not isinstance(packs, Mapping):
        raise ValueError("authorised MIDI controls differ")
    pack_ids = set(packs)
    if (
        len(pack_ids) < 2
        or not pack_ids.issubset(_SUPPORTED_CONTROL_PACKS)
        or "local-htdemucs" not in pack_ids
    ):
        raise ValueError("authorised MIDI controls differ")
    result = {}
    for pack_id in _SUPPORTED_CONTROL_PACKS:
        if pack_id not in pack_ids:
            continue
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


__all__ = [
    "SCHEMA",
    "_evaluate_private_melroformer_vocal_midi",
    "_load_verified_vocal_source",
    "_validated_control_policy",
]
