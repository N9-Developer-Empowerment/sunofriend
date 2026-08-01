"""Inactive MIDI evidence for provider leaves inside broad vocal groups."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_authorised_excerpt import (
    AUTHORISED_EXCERPT_SCHEMA,
    _document_sha256 as _excerpt_document_sha256,
)
from ._separation_authorised_midi_comparison import (
    AUTHORISED_MIDI_COMPARISON_SCHEMA,
    _artifact_path as _midi_artifact_path,
    _artifacts,
    _document_sha256,
    _make_private_tree,
    _persist_candidate,
    _production_component_identity,
    _regular_json,
    _sha256,
    _verify_artifacts as _verify_midi_artifacts,
    _write_json,
)
from ._separation_authorised_role_mapping import (
    AUTHORISED_ROLE_MAPPING_SCHEMA,
    _artifact_path,
    _assign_provider_items,
    _safe_token,
    _verify_artifacts,
)
from ._separation_demucs_midi_metrics import _compare_note_events
from ._separation_demucs_refinement_evaluation import _validated_notes
from ._separation_melroformer_midi_evaluation import (
    SCHEMA as MELROFORMER_MIDI_SCHEMA,
    _load_control_notes,
    _validated_control_policy,
)
from ._separation_melroformer_real_bridge import _validate_authorisation_document
from .models import NoteEvent
from .vocal import VocalConfig, VocalTranscription, transcribe_vocal_melody


SCHEMA = "sunofriend.private-authorised-vocal-leaf-midi-evaluation.v1"
_REPORT_NAME = "authorised-vocal-leaf-midi-evaluation.json"
_ONSET_TOLERANCE_SECONDS = 0.040
_INACTIVE_PERMISSIONS = {
    "accepted": False,
    "automatic_promotion": False,
    "automatic_selection": False,
    "production_eligible": False,
    "public_result": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
}


def _evaluate_authorised_vocal_leaves(
    role_mapping_report_path: str | Path,
    control_comparison_path: str | Path,
    melroformer_evaluation_path: str | Path,
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Apply both unchanged vocal adapters to every broad-vocal provider leaf."""

    inputs = _load_inputs(
        role_mapping_report_path,
        control_comparison_path,
        melroformer_evaluation_path,
    )
    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"Vocal-leaf evaluation already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=destination.parent)
    )
    temporary.chmod(0o700)
    try:
        from .evaluate import evaluate_stem_midi
        from .render import render_midi_to_wav

        started = time.monotonic()
        leaves: dict[str, Any] = {}
        broad_loss: dict[str, bool] = {}
        for pack_id in sorted(inputs["provider_packs"]):
            pack = inputs["provider_packs"][pack_id]
            proposals = inputs["proposals"][pack_id]
            memberships = _assign_provider_items(pack_id, pack, proposals)
            vocal_members = sorted(
                memberships["vocals"],
                key=lambda item: str(item.get("source_path", "")).casefold(),
            )
            pack_out = temporary / _safe_token(pack_id)
            pack_out.mkdir(mode=0o700)
            leaves[pack_id] = {}
            pack_has_leaf_evidence = False
            for index, item in enumerate(vocal_members, start=1):
                leaf_id = f"leaf-{index:02d}"
                source = _artifact_path(
                    inputs["excerpt_root"],
                    item.get("excerpt"),
                    f"{pack_id} vocal {leaf_id}",
                )
                leaf_out = pack_out / leaf_id
                leaf_out.mkdir(mode=0o700)
                lead = transcribe_vocal_melody(
                    source,
                    config=VocalConfig(
                        role="lead",
                        tuning_hz=inputs["tuning_hz"],
                        tuning_source="authorised-midi-comparison-explicit",
                        bpm=inputs["bpm"],
                        tracker_mode="pyin",
                        phrase_repair=True,
                    ),
                )
                backing = transcribe_vocal_melody(
                    source,
                    config=VocalConfig(
                        role="backing",
                        tuning_hz=inputs["tuning_hz"],
                        tuning_source="authorised-midi-comparison-explicit",
                        bpm=inputs["bpm"],
                    ),
                )
                _require_backing_adapter_available(backing)
                adapters = {
                    "lead": _persist_transcription(
                        root=temporary,
                        role_out=leaf_out,
                        adapter="lead",
                        source=source,
                        transcription=lead,
                        bpm=inputs["bpm"],
                        controls=inputs["controls"],
                        kim_notes=inputs["kim_notes"],
                        render=render_midi_to_wav,
                        evaluate=evaluate_stem_midi,
                    ),
                    "backing": _persist_transcription(
                        root=temporary,
                        role_out=leaf_out,
                        adapter="backing",
                        source=source,
                        transcription=backing,
                        bpm=inputs["bpm"],
                        controls=inputs["controls"],
                        kim_notes=inputs["kim_notes"],
                        render=render_midi_to_wav,
                        evaluate=evaluate_stem_midi,
                    ),
                }
                pack_has_leaf_evidence = pack_has_leaf_evidence or any(
                    adapter["primary_note_count"] > 0 for adapter in adapters.values()
                )
                display_name = Path(str(item.get("source_path", ""))).name
                leaves[pack_id][leaf_id] = {
                    "display_name": display_name,
                    "provider_label_is_observation_not_ground_truth": True,
                    "source_sha256": item.get("source_sha256"),
                    "source_excerpt": dict(item.get("excerpt", {})),
                    "adapters": adapters,
                }
            broad_notes = inputs["controls"].get(pack_id, ())
            broad_loss[pack_id] = bool(not broad_notes and pack_has_leaf_evidence)

        _reverify_inputs(inputs)
        primary_counts = {
            f"{pack_id}/{leaf_id}/{adapter_id}": adapter["primary_note_count"]
            for pack_id, pack_leaves in leaves.items()
            for leaf_id, leaf in pack_leaves.items()
            for adapter_id, adapter in leaf["adapters"].items()
        }
        any_candidate = any(
            variant["candidate"]["note_count"] > 0
            for pack_leaves in leaves.values()
            for leaf in pack_leaves.values()
            for adapter in leaf["adapters"].values()
            for variant in adapter["variants"].values()
        )
        document: dict[str, Any] = {
            "schema": SCHEMA,
            "status": "complete_observation_not_acceptance",
            "evidence_scope": "private_development_only",
            "inputs": {
                "role_mapping_sha256": inputs["mapping_sha256"],
                "role_mapping_document_sha256": inputs["mapping"][
                    "document_sha256"
                ],
                "excerpt_sha256": inputs["excerpt_sha256"],
                "excerpt_document_sha256": inputs["excerpt"]["document_sha256"],
                "rights_authority": inputs["rights_authority"],
                "control_comparison_sha256": inputs["control_sha256"],
                "control_comparison_document_sha256": inputs["control"][
                    "document_sha256"
                ],
                "melroformer_evaluation_sha256": inputs["melroformer_sha256"],
                "melroformer_evaluation_document_sha256": inputs["melroformer"][
                    "document_sha256"
                ],
            },
            "policy": {
                "bpm": inputs["bpm"],
                "tuning_hz": inputs["tuning_hz"],
                "lead_adapter": "unchanged production pYIN dominant contour",
                "backing_adapter": (
                    "unchanged production Basic Pitch voice selector with its "
                    "explicit no-candidate pYIN fallback"
                ),
                "basic_pitch_runtime_required": True,
                "every_leaf_runs_both_adapters": True,
                "provider_labels_select_adapter": False,
                "onset_tolerance_ms": _ONSET_TOLERANCE_SECONDS * 1000.0,
                "absolute_ground_truth_claimed": False,
                "winner_selected": False,
            },
            "components": _production_component_identity(),
            "baselines": {
                "broad_control_note_counts": {
                    pack_id: len(notes)
                    for pack_id, notes in inputs["controls"].items()
                },
                "kim_primary_note_count": len(inputs["kim_notes"]),
            },
            "leaves": leaves,
            "observations": {
                "provider_pack_count": len(leaves),
                "leaf_counts": {
                    pack_id: len(pack_leaves)
                    for pack_id, pack_leaves in leaves.items()
                },
                "primary_note_counts": primary_counts,
                "within_pack_broad_group_zero_but_leaf_nonempty": broad_loss,
                "automatic_acceptance": False,
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
                "inactive_midi_created": any_candidate,
                "dry_proxy_auditions_created": any_candidate,
                "source_graph_mutated": False,
                "separator_rerun": False,
            },
            "limitations": [
                "Provider leaf labels are observations, not singer identity or score truth.",
                "Both unchanged adapters run on every leaf so a filename never selects the algorithm.",
                "A non-empty leaf result does not prove that every emitted note is correct.",
                "A zero-note broad sum can result from masking, polyphony or tracker confidence; this report does not infer which mechanism dominates.",
                "One 15-second excerpt cannot establish a production split or cross-song acceptance.",
                "Dry General MIDI auditions are not GarageBand patch recommendations.",
            ],
            "next": {
                "separate_vocal_leaf_candidates_in_future_separator_required": any(
                    broad_loss.values()
                ),
                "human_listening_required_before_any_promotion": True,
                "cross_song_repetition_required": True,
                "studio_import_created": False,
            },
            "elapsed_seconds": round(time.monotonic() - started, 6),
        }
        document["artifacts"] = _artifacts(temporary)
        document["document_sha256"] = _document_sha256(document)
        report_path = temporary / _REPORT_NAME
        _write_json(report_path, document)
        _make_private_tree(temporary)
        if os.path.lexists(destination):
            raise FileExistsError("Vocal-leaf evaluation output appeared during run")
        os.rename(temporary, destination)
        document["report"] = str(destination / _REPORT_NAME)
        return document
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _persist_transcription(
    *,
    root: Path,
    role_out: Path,
    adapter: str,
    source: Path,
    transcription: VocalTranscription,
    bpm: float,
    controls: Mapping[str, tuple[NoteEvent, ...]],
    kim_notes: tuple[NoteEvent, ...],
    render: Any,
    evaluate: Any,
) -> dict[str, Any]:
    adapter_out = role_out / adapter
    adapter_out.mkdir(mode=0o700)
    variants = {}
    for variant, raw_notes in sorted(transcription.variants.items()):
        notes = _validated_notes(raw_notes)
        persisted = _persist_candidate(
            root=root,
            role_out=adapter_out,
            label=_safe_token(variant),
            source=source,
            role="vocals",
            notes=notes,
            bpm=bpm,
            render=render,
            evaluate=evaluate,
        )
        variants[variant] = {
            "candidate": persisted,
            "comparisons_to_broad_controls": _compare_to_references(
                notes, controls
            ),
            "comparison_to_kim_primary": _comparison(notes, kim_notes),
        }
    primary = variants.get(transcription.primary_variant)
    if primary is None:
        raise ValueError("vocal adapter primary variant is missing")
    return {
        "primary_variant": transcription.primary_variant,
        "primary_note_count": primary["candidate"]["note_count"],
        "diagnostics": transcription.diagnostics.to_dict(),
        "descriptions": dict(transcription.descriptions),
        "variants": variants,
    }


def _require_backing_adapter_available(
    transcription: VocalTranscription,
) -> None:
    if any(
        str(warning).startswith("Polyphonic backing extraction unavailable:")
        for warning in transcription.diagnostics.warnings
    ):
        raise RuntimeError(
            "Vocal-leaf evaluation requires the installed Basic Pitch runtime"
        )


def _compare_to_references(
    notes: tuple[NoteEvent, ...],
    references: Mapping[str, tuple[NoteEvent, ...]],
) -> dict[str, Any]:
    return {
        pack_id: _comparison(notes, reference)
        for pack_id, reference in references.items()
    }


def _comparison(
    notes: tuple[NoteEvent, ...], reference: tuple[NoteEvent, ...]
) -> dict[str, Any]:
    return {
        "reference_note_count": len(reference),
        "candidate_note_count": len(notes),
        "comparison": _compare_note_events(
            reference,
            notes,
            tolerance_seconds=_ONSET_TOLERANCE_SECONDS,
        ),
        "reference_semantics": "relative estimated MIDI evidence, not score truth",
    }


def _load_inputs(
    role_mapping_report_path: str | Path,
    control_comparison_path: str | Path,
    melroformer_evaluation_path: str | Path,
) -> dict[str, Any]:
    mapping_path = _regular_json(role_mapping_report_path, "role mapping report")
    mapping_root = mapping_path.parent
    mapping_sha256 = _sha256(mapping_path)
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    if (
        mapping.get("schema") != AUTHORISED_ROLE_MAPPING_SCHEMA
        or mapping.get("document_sha256") != _document_sha256(mapping)
        or mapping.get("next", {}).get("inactive_downstream_midi_comparison_allowed")
        is not True
    ):
        raise ValueError("authorised role mapping differs")
    _require_private_inactive(mapping, "authorised role mapping")
    _verify_artifacts(mapping_root, mapping.get("artifacts"), "role mapping")

    excerpt_path = _regular_json(
        mapping.get("source_excerpt", {}).get("report_path", ""),
        "source excerpt report",
    )
    excerpt_root = excerpt_path.parent
    excerpt_sha256 = _sha256(excerpt_path)
    excerpt = json.loads(excerpt_path.read_text(encoding="utf-8"))
    if (
        excerpt.get("schema") != AUTHORISED_EXCERPT_SCHEMA
        or excerpt.get("document_sha256") != _excerpt_document_sha256(excerpt)
        or excerpt_sha256 != mapping["source_excerpt"].get("report_sha256")
        or excerpt.get("document_sha256")
        != mapping["source_excerpt"].get("document_sha256")
    ):
        raise ValueError("authorised excerpt differs")
    _require_private_inactive(excerpt, "authorised excerpt")
    rights_authority = _validate_authorisation_document(excerpt)
    _verify_artifacts(excerpt_root, excerpt.get("artifacts"), "excerpt")

    control_path = _regular_json(control_comparison_path, "control comparison")
    control_root = control_path.parent
    control_sha256 = _sha256(control_path)
    control = json.loads(control_path.read_text(encoding="utf-8"))
    if (
        control.get("schema") != AUTHORISED_MIDI_COMPARISON_SCHEMA
        or control.get("document_sha256") != _document_sha256(control)
        or control.get("source_role_mapping", {}).get("report_sha256")
        != mapping_sha256
        or control.get("source_role_mapping", {}).get("document_sha256")
        != mapping.get("document_sha256")
    ):
        raise ValueError("authorised MIDI controls differ")
    _require_private_inactive(control, "authorised MIDI controls")
    _verify_midi_artifacts(control_root, control.get("artifacts"))
    bpm, tuning_hz = _validated_control_policy(control.get("policy"))
    controls = _load_control_notes(control_root, control)

    melroformer_path = _regular_json(
        melroformer_evaluation_path, "MelRoFormer MIDI evaluation"
    )
    melroformer_root = melroformer_path.parent
    melroformer_sha256 = _sha256(melroformer_path)
    melroformer = json.loads(melroformer_path.read_text(encoding="utf-8"))
    if (
        melroformer.get("schema") != MELROFORMER_MIDI_SCHEMA
        or melroformer.get("document_sha256") != _document_sha256(melroformer)
        or melroformer.get("controls", {}).get("comparison_sha256")
        != control_sha256
        or melroformer.get("controls", {}).get("document_sha256")
        != control.get("document_sha256")
        or melroformer.get("worker", {}).get("authorisation_report_sha256")
        != excerpt_sha256
    ):
        raise ValueError("MelRoFormer MIDI evaluation differs")
    _require_private_inactive(melroformer, "MelRoFormer MIDI evaluation")
    _verify_midi_artifacts(melroformer_root, melroformer.get("artifacts"))
    kim_notes = _load_notes(
        melroformer_root,
        melroformer.get("candidate", {}).get("primary", {}).get("notes"),
        role="vocals",
        candidate="primary",
    )
    if len(kim_notes) != melroformer["candidate"]["primary"].get("note_count"):
        raise ValueError("MelRoFormer primary note count differs")

    provider_packs = excerpt.get("provider_packs")
    proposals = excerpt.get("excerpt", {}).get("role_group_proposals")
    if (
        not isinstance(provider_packs, Mapping)
        or not provider_packs
        or not isinstance(proposals, Mapping)
        or set(provider_packs) != set(proposals)
    ):
        raise ValueError("provider vocal-leaf evidence is missing")
    return {
        "mapping_path": mapping_path,
        "mapping_root": mapping_root,
        "mapping_sha256": mapping_sha256,
        "mapping": mapping,
        "excerpt_path": excerpt_path,
        "excerpt_root": excerpt_root,
        "excerpt_sha256": excerpt_sha256,
        "excerpt": excerpt,
        "control_path": control_path,
        "control_root": control_root,
        "control_sha256": control_sha256,
        "control": control,
        "melroformer_path": melroformer_path,
        "melroformer_root": melroformer_root,
        "melroformer_sha256": melroformer_sha256,
        "melroformer": melroformer,
        "bpm": bpm,
        "tuning_hz": tuning_hz,
        "controls": controls,
        "kim_notes": kim_notes,
        "rights_authority": rights_authority,
        "provider_packs": provider_packs,
        "proposals": proposals,
    }


def _load_notes(
    root: Path,
    raw: Any,
    *,
    role: str,
    candidate: str,
) -> tuple[NoteEvent, ...]:
    path = _midi_artifact_path(root, raw, f"{candidate} note evidence")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema")
        != "sunofriend.private-authorised-midi-note-evidence.v1"
        or payload.get("role") != role
        or payload.get("candidate") != candidate
        or not isinstance(payload.get("notes"), list)
    ):
        raise ValueError("vocal note evidence differs")
    try:
        notes = tuple(
            NoteEvent(
                start=float(note["start_seconds"]),
                end=float(note["end_seconds"]),
                pitch=int(note["pitch"]),
                velocity=int(note["velocity"]),
            )
            for note in payload["notes"]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("vocal note evidence differs") from error
    return _validated_notes(notes)


def _reverify_inputs(inputs: Mapping[str, Any]) -> None:
    if _sha256(inputs["mapping_path"]) != inputs["mapping_sha256"]:
        raise ValueError("role mapping changed during vocal-leaf evaluation")
    if _sha256(inputs["excerpt_path"]) != inputs["excerpt_sha256"]:
        raise ValueError("excerpt changed during vocal-leaf evaluation")
    if _sha256(inputs["control_path"]) != inputs["control_sha256"]:
        raise ValueError("MIDI controls changed during vocal-leaf evaluation")
    if _sha256(inputs["melroformer_path"]) != inputs["melroformer_sha256"]:
        raise ValueError("MelRoFormer evidence changed during vocal-leaf evaluation")
    _verify_artifacts(
        inputs["mapping_root"], inputs["mapping"].get("artifacts"), "role mapping"
    )
    _verify_artifacts(
        inputs["excerpt_root"], inputs["excerpt"].get("artifacts"), "excerpt"
    )
    _verify_midi_artifacts(
        inputs["control_root"], inputs["control"].get("artifacts")
    )
    _verify_midi_artifacts(
        inputs["melroformer_root"], inputs["melroformer"].get("artifacts")
    )


def _require_private_inactive(document: Mapping[str, Any], label: str) -> None:
    if (
        document.get("evidence_scope") != "private_development_only"
        or document.get("permissions") != _INACTIVE_PERMISSIONS
    ):
        raise ValueError(f"{label} permissions differ")


__all__: Sequence[str] = ()
