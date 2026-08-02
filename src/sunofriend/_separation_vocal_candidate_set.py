"""Path-free inventory of inactive private vocal MIDI candidates."""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_authorised_midi_comparison import (
    _artifact_path,
    _document_sha256,
    _make_private_tree,
    _regular_json,
    _sha256,
    _verify_artifacts,
    _write_json,
)
from ._separation_authorised_role_mapping import _safe_token
from ._separation_authorised_vocal_leaves import (
    SCHEMA as VOCAL_LEAF_SCHEMA,
    _require_private_inactive,
)
from ._separation_melroformer_midi_evaluation import (
    SCHEMA as MELROFORMER_MIDI_SCHEMA,
)
from ._separation_vocal_phrase_completeness import (
    SCHEMA as PHRASE_COMPLETENESS_SCHEMA,
    _REGISTER_HYPOTHESES,
    _load_note_claim,
)


SCHEMA = "sunofriend.private-vocal-candidate-set.v1"
_REPORT_NAME = "vocal-candidate-set.json"
_ARTIFACT_KINDS = ("midi", "notes", "render")


def _build_vocal_candidate_set(
    melroformer_evaluation_path: str | Path,
    vocal_leaf_evaluation_path: str | Path,
    phrase_completeness_path: str | Path,
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Create one private inventory without choosing or copying candidates."""

    inputs = _load_inputs(
        melroformer_evaluation_path,
        vocal_leaf_evaluation_path,
        phrase_completeness_path,
    )
    document = _build_document(inputs)
    _reverify_inputs(inputs)

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"Vocal candidate-set output already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-", dir=destination.parent
        )
    )
    temporary.chmod(0o700)
    try:
        document["document_sha256"] = _document_sha256(document)
        _write_json(temporary / _REPORT_NAME, document)
        _make_private_tree(temporary)
        if os.path.lexists(destination):
            raise FileExistsError(
                "Vocal candidate-set output appeared during publication"
            )
        os.rename(temporary, destination)
        document["report"] = str(destination / _REPORT_NAME)
        return document
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _build_document(inputs: Mapping[str, Any]) -> dict[str, Any]:
    candidates = list(inputs["candidates"])
    candidate_ids = [candidate["candidate_id"] for candidate in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("vocal candidate identifiers are not unique")
    if not candidates:
        raise ValueError("vocal candidate set is empty")

    family_counts: dict[str, int] = {}
    provider_counts: dict[str, int] = {}
    nonempty = 0
    for candidate in candidates:
        family = str(candidate["family"])
        family_counts[family] = family_counts.get(family, 0) + 1
        provider = candidate.get("provider_group")
        if isinstance(provider, str):
            provider_counts[provider] = provider_counts.get(provider, 0) + 1
        if candidate["audition_state"] == "available":
            nonempty += 1

    phrase = inputs["phrase"]
    primary_vs_lowest = phrase.get("primary_vs_lowest")
    consensus = phrase.get("provider_consensus")
    if not isinstance(primary_vs_lowest, Mapping) or not isinstance(consensus, Mapping):
        raise ValueError("phrase-completeness diagnostics differ")

    return {
        "schema": SCHEMA,
        "status": "complete_inventory_not_acceptance",
        "evidence_scope": "private_development_only",
        "inputs": {
            "melroformer_evaluation_sha256": inputs["melroformer_sha256"],
            "melroformer_evaluation_document_sha256": inputs["melroformer"][
                "document_sha256"
            ],
            "vocal_leaf_evaluation_sha256": inputs["leaf_sha256"],
            "vocal_leaf_evaluation_document_sha256": inputs["leaf"]["document_sha256"],
            "phrase_completeness_sha256": inputs["phrase_sha256"],
            "phrase_completeness_document_sha256": phrase["document_sha256"],
        },
        "policy": {
            "bpm": inputs["bpm"],
            "tuning_hz": inputs["tuning_hz"],
            "duration_seconds": inputs["duration_seconds"],
            "all_input_candidates_preserved": True,
            "candidate_ranked": False,
            "candidate_selected": False,
            "candidate_merged": False,
            "candidate_repaired": False,
            "default_candidate_assigned": False,
            "singer_identity_inferred": False,
            "serialization_order_has_rank_semantics": False,
            "paths_or_audio_copied": False,
        },
        "summary": {
            "candidate_count": len(candidates),
            "audition_available_count": nonempty,
            "no_note_evidence_count": len(candidates) - nonempty,
            "family_counts": dict(sorted(family_counts.items())),
            "provider_leaf_counts": dict(sorted(provider_counts.items())),
        },
        "candidates": candidates,
        "phrase_context": {
            "semantics": (
                "activity-only context copied from the sealed phrase diagnostic; "
                "not pitch truth, a score or a ranking"
            ),
            "provider_consensus": {
                "active_seconds": consensus.get("active_seconds"),
                "interval_count": consensus.get("interval_count"),
                "phrase_count": consensus.get("phrase_count"),
            },
            "primary_vs_lowest": {
                key: primary_vs_lowest.get(key)
                for key in (
                    "both_candidates_consensus_seconds",
                    "primary_only_consensus_seconds",
                    "lowest_only_consensus_seconds",
                    "neither_candidate_consensus_seconds",
                    "automatic_merge_performed",
                )
            },
        },
        "permissions": {
            "accepted": False,
            "automatic_promotion": False,
            "automatic_selection": False,
            "production_eligible": False,
            "public_result": False,
            "simple_mode_available": False,
            "source_graph_activation": False,
            "studio_import_available": False,
        },
        "effects": {
            "audio_created": False,
            "candidate_manifest_created": True,
            "midi_created": False,
            "review_created": False,
            "source_audio_mutated": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "Artifact identities are path-free references to sealed private evidence; this report copies no MIDI, notes or audio.",
            "Provider names identify evidence groups, not independent ground truth or singer identity.",
            "Lead and backing adapters are processing hypotheses, not labels assigned to a singer.",
            "Zero-note candidates remain present because absence is diagnostic evidence.",
            "The phrase context measures activity only and cannot establish pitch correctness or musical usefulness.",
            "No candidate is ranked, selected, merged, repaired, promoted or exposed to Studio or Simple mode.",
        ],
        "next": {
            "audition_adapter_requires_separate_design": True,
            "automatic_route_allowed": False,
            "focused_review_created": False,
            "human_choice_required_before_any_candidate_use": True,
        },
    }


def _load_inputs(
    melroformer_evaluation_path: str | Path,
    vocal_leaf_evaluation_path: str | Path,
    phrase_completeness_path: str | Path,
) -> dict[str, Any]:
    melroformer_path, melroformer_root, melroformer_sha256, melroformer = (
        _load_private_document(
            melroformer_evaluation_path,
            label="MelRoFormer MIDI evaluation",
            schema=MELROFORMER_MIDI_SCHEMA,
            require_artifacts=True,
        )
    )
    leaf_path, leaf_root, leaf_sha256, leaf = _load_private_document(
        vocal_leaf_evaluation_path,
        label="vocal leaf evaluation",
        schema=VOCAL_LEAF_SCHEMA,
        require_artifacts=True,
    )
    phrase_path, phrase_root, phrase_sha256, phrase = _load_private_document(
        phrase_completeness_path,
        label="phrase completeness",
        schema=PHRASE_COMPLETENESS_SCHEMA,
        require_artifacts=False,
    )

    leaf_inputs = leaf.get("inputs", {})
    control = melroformer.get("controls", {})
    if (
        leaf_inputs.get("melroformer_evaluation_sha256") != melroformer_sha256
        or leaf_inputs.get("melroformer_evaluation_document_sha256")
        != melroformer.get("document_sha256")
        or leaf_inputs.get("control_comparison_sha256")
        != control.get("comparison_sha256")
        or leaf_inputs.get("control_comparison_document_sha256")
        != control.get("document_sha256")
    ):
        raise ValueError("vocal leaf evaluation is not bound to MelRoFormer evidence")
    phrase_inputs = phrase.get("inputs", {})
    if (
        phrase_inputs.get("melroformer_evaluation_sha256") != melroformer_sha256
        or phrase_inputs.get("melroformer_evaluation_document_sha256")
        != melroformer.get("document_sha256")
        or phrase_inputs.get("vocal_leaf_evaluation_sha256") != leaf_sha256
        or phrase_inputs.get("vocal_leaf_evaluation_document_sha256")
        != leaf.get("document_sha256")
        or phrase_inputs.get("control_comparison_sha256")
        != control.get("comparison_sha256")
        or phrase_inputs.get("control_comparison_document_sha256")
        != control.get("document_sha256")
    ):
        raise ValueError("phrase completeness is not bound to candidate evidence")
    if (
        melroformer.get("policy", {}).get("winner_selected") is not False
        or melroformer.get("policy", {}).get("lead_backing_role_assignment_inferred")
        is not False
        or phrase.get("policy", {}).get("candidate_ranked_or_selected") is not False
        or phrase.get("policy", {}).get("singer_identity_inferred") is not False
        or phrase.get("primary_vs_lowest", {}).get("automatic_merge_performed")
        is not False
    ):
        raise ValueError("vocal candidate selection policy differs")

    bpm = _finite_number(melroformer.get("policy", {}).get("bpm"), "BPM")
    tuning_hz = _finite_number(melroformer.get("policy", {}).get("tuning_hz"), "tuning")
    duration = _finite_number(
        melroformer.get("candidate", {})
        .get("method", {})
        .get("diagnostics", {})
        .get("duration_seconds"),
        "duration",
    )
    if bpm <= 0.0 or tuning_hz <= 0.0 or not 0.0 < duration <= 15.1:
        raise ValueError("vocal candidate geometry differs")
    for label, document in (("leaf", leaf), ("phrase", phrase)):
        policy = document.get("policy", {})
        if (
            float(policy.get("bpm", -1.0)) != bpm
            or float(policy.get("tuning_hz", -1.0)) != tuning_hz
        ):
            raise ValueError(f"{label} policy differs")
    if float(phrase.get("policy", {}).get("duration_seconds", -1.0)) != duration:
        raise ValueError("phrase duration differs")

    candidates = _melroformer_candidates(melroformer_root, melroformer, phrase)
    candidates.extend(_leaf_candidates(leaf_root, leaf))
    return {
        "melroformer_path": melroformer_path,
        "melroformer_root": melroformer_root,
        "melroformer_sha256": melroformer_sha256,
        "melroformer": melroformer,
        "leaf_path": leaf_path,
        "leaf_root": leaf_root,
        "leaf_sha256": leaf_sha256,
        "leaf": leaf,
        "phrase_path": phrase_path,
        "phrase_root": phrase_root,
        "phrase_sha256": phrase_sha256,
        "phrase": phrase,
        "bpm": bpm,
        "tuning_hz": tuning_hz,
        "duration_seconds": duration,
        "candidates": tuple(candidates),
    }


def _load_private_document(
    raw_path: str | Path, *, label: str, schema: str, require_artifacts: bool
) -> tuple[Path, Path, str, dict[str, Any]]:
    path = _regular_json(raw_path, label)
    root = path.parent
    file_sha256 = _sha256(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(document, dict)
        or document.get("schema") != schema
        or document.get("document_sha256") != _document_sha256(document)
    ):
        raise ValueError(f"{label} differs")
    _require_private_inactive(document, label)
    artifacts = document.get("artifacts")
    if require_artifacts and not isinstance(artifacts, Mapping):
        raise ValueError(f"{label} artifact manifest is missing")
    if artifacts is not None:
        _verify_artifacts(root, artifacts)
    return path, root, file_sha256, document


def _melroformer_candidates(
    root: Path, document: Mapping[str, Any], phrase: Mapping[str, Any]
) -> list[dict[str, Any]]:
    raw = document.get("candidate")
    if not isinstance(raw, Mapping) or not isinstance(raw.get("primary"), Mapping):
        raise ValueError("MelRoFormer candidates differ")
    result = [
        _candidate_record(
            candidate_id="kim/primary",
            family="kim_primary",
            candidate=raw["primary"],
            root=root,
            expected_notes_candidate="primary",
            variant="primary",
            activity_diagnostic=_activity_diagnostic(phrase, "primary"),
        )
    ]
    variants = raw.get("register_hypotheses", {}).get("variants")
    if not isinstance(variants, Mapping) or set(variants) != set(_REGISTER_HYPOTHESES):
        raise ValueError("MelRoFormer register hypotheses differ")
    for variant in sorted(_REGISTER_HYPOTHESES):
        payload = variants[variant]
        candidate = payload.get("candidate") if isinstance(payload, Mapping) else None
        if not isinstance(candidate, Mapping):
            raise ValueError("MelRoFormer register candidate differs")
        result.append(
            _candidate_record(
                candidate_id=f"kim/register/{_safe_token(variant)}",
                family="kim_register",
                candidate=candidate,
                root=root,
                expected_notes_candidate=f"hypothesis-{variant}",
                variant=variant,
                activity_diagnostic=_activity_diagnostic(phrase, variant),
            )
        )
    return result


def _leaf_candidates(root: Path, document: Mapping[str, Any]) -> list[dict[str, Any]]:
    leaves = document.get("leaves")
    if not isinstance(leaves, Mapping) or not leaves:
        raise ValueError("vocal leaf candidates differ")
    result = []
    for provider_id, provider_leaves in sorted(leaves.items()):
        if not isinstance(provider_id, str) or not isinstance(provider_leaves, Mapping):
            raise ValueError("vocal leaf provider differs")
        provider_token = _safe_token(provider_id)
        for leaf_id, leaf in sorted(provider_leaves.items()):
            if not isinstance(leaf_id, str) or not isinstance(leaf, Mapping):
                raise ValueError("vocal leaf evidence differs")
            adapters = leaf.get("adapters")
            if not isinstance(adapters, Mapping) or set(adapters) != {
                "backing",
                "lead",
            }:
                raise ValueError("vocal leaf adapters differ")
            for adapter_id, adapter in sorted(adapters.items()):
                if not isinstance(adapter, Mapping):
                    raise ValueError("vocal leaf adapter differs")
                variant = adapter.get("primary_variant")
                variants = adapter.get("variants")
                if (
                    not isinstance(variant, str)
                    or not isinstance(variants, Mapping)
                    or not isinstance(variants.get(variant), Mapping)
                ):
                    raise ValueError("vocal leaf primary candidate differs")
                candidate = variants[variant].get("candidate")
                if not isinstance(candidate, Mapping):
                    raise ValueError("vocal leaf primary candidate differs")
                result.append(
                    _candidate_record(
                        candidate_id=(
                            f"provider/{provider_token}/{_safe_token(leaf_id)}/"
                            f"{_safe_token(adapter_id)}/{_safe_token(variant)}"
                        ),
                        family="provider_leaf",
                        candidate=candidate,
                        root=root,
                        expected_notes_candidate=_safe_token(variant),
                        variant=variant,
                        provider_group=provider_id,
                        leaf_id=leaf_id,
                        adapter=adapter_id,
                        activity_diagnostic=None,
                    )
                )
    return result


def _candidate_record(
    *,
    candidate_id: str,
    family: str,
    candidate: Mapping[str, Any],
    root: Path,
    expected_notes_candidate: str,
    variant: str,
    activity_diagnostic: Mapping[str, Any] | None,
    provider_group: str | None = None,
    leaf_id: str | None = None,
    adapter: str | None = None,
) -> dict[str, Any]:
    note_count = candidate.get("note_count")
    if (
        isinstance(note_count, bool)
        or not isinstance(note_count, int)
        or note_count < 0
    ):
        raise ValueError("vocal candidate note count differs")
    _load_note_claim(
        root,
        candidate.get("notes"),
        expected_candidate=expected_notes_candidate,
        expected_note_count=note_count,
    )
    status = candidate.get("status")
    if note_count:
        if status != "ok" or any(
            candidate.get(kind) is None for kind in _ARTIFACT_KINDS
        ):
            raise ValueError("auditionable vocal candidate differs")
        audition_state = "available"
    else:
        if (
            status != "no_evidence"
            or candidate.get("midi") is not None
            or candidate.get("render") is not None
        ):
            raise ValueError("zero-note vocal candidate differs")
        audition_state = "no_note_evidence"
    artifacts = {
        kind: _verified_path_free_artifact(
            root,
            candidate.get(kind),
            kind=kind,
            required=(kind == "notes" or note_count > 0),
            candidate_id=candidate_id,
        )
        for kind in _ARTIFACT_KINDS
    }
    return {
        "candidate_id": candidate_id,
        "family": family,
        "provider_group": provider_group,
        "leaf_id": leaf_id,
        "adapter": adapter,
        "variant": variant,
        "musical_identity": "unassigned_vocal_candidate",
        "note_count": note_count,
        "audition_state": audition_state,
        "artifacts": artifacts,
        "activity_diagnostic": dict(activity_diagnostic)
        if activity_diagnostic
        else None,
        "selection_state": "unselected",
    }


def _path_free_artifact(
    raw: Any, *, kind: str, required: bool
) -> dict[str, Any] | None:
    if raw is None:
        if required:
            raise ValueError(f"vocal candidate {kind} artifact is missing")
        return None
    if not isinstance(raw, Mapping):
        raise ValueError(f"vocal candidate {kind} artifact differs")
    sha256 = raw.get("sha256")
    size = raw.get("bytes")
    if (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size <= 0
    ):
        raise ValueError(f"vocal candidate {kind} artifact identity differs")
    return {"sha256": sha256, "bytes": size}


def _verified_path_free_artifact(
    root: Path,
    raw: Any,
    *,
    kind: str,
    required: bool,
    candidate_id: str,
) -> dict[str, Any] | None:
    identity = _path_free_artifact(raw, kind=kind, required=required)
    if identity is not None:
        _artifact_path(root, raw, f"{candidate_id} {kind}")
    return identity


def _activity_diagnostic(
    phrase: Mapping[str, Any], candidate_id: str
) -> dict[str, Any]:
    raw = phrase.get("candidates", {}).get(candidate_id)
    if not isinstance(raw, Mapping):
        raise ValueError("phrase candidate diagnostic differs")
    return {
        key: raw.get(key)
        for key in (
            "active_seconds",
            "consensus_covered_seconds",
            "consensus_coverage_ratio",
            "phrase_count_with_any_coverage",
        )
    }


def _finite_number(raw: Any, label: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"vocal candidate {label} differs")
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"vocal candidate {label} differs")
    return value


def _reverify_inputs(inputs: Mapping[str, Any]) -> None:
    for label in ("melroformer", "leaf", "phrase"):
        if _sha256(inputs[f"{label}_path"]) != inputs[f"{label}_sha256"]:
            raise ValueError(f"{label} evidence changed during candidate-set build")
        artifacts = inputs[label].get("artifacts")
        if artifacts is not None:
            _verify_artifacts(inputs[f"{label}_root"], artifacts)


__all__: Sequence[str] = ()
