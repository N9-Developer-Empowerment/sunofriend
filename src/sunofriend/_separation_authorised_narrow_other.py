"""Private audio evidence for the leaf stems inside broad ``other`` groups.

This module deliberately sits outside Sunofriend's product graph. It takes a
verified authorised broad-role report, stages every provider member assigned
to ``other`` at a common geometry, and ranks each leaf against every leaf in
the other provider packs. Labels are retained for human review but never
contribute to an audio score or activate a mapping.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import (
    AUTHORISED_EXCERPT_SCHEMA,
    _document_sha256 as _excerpt_document_sha256,
    _write_model_input,
)
from ._separation_authorised_role_mapping import (
    AUTHORISED_ROLE_MAPPING_SCHEMA,
    _artifact,
    _artifact_path,
    _artifacts,
    _assign_provider_items,
    _document_sha256,
    _features,
    _make_private_tree,
    _regular_json,
    _require_common_geometry,
    _safe_token,
    _sha256,
    _similarity,
    _verify_artifacts,
    _write_json,
)


AUTHORISED_NARROW_OTHER_SCHEMA = (
    "sunofriend.private-authorised-narrow-other-evidence.v1"
)
_REPORT_NAME = "authorised-narrow-other-evidence.json"
_SAMPLE_RATE = 44_100


def _compare_authorised_other_leaves(
    role_mapping_report_path: str | Path,
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Rank provider ``other`` leaves without accepting a narrow mapping."""

    import numpy as np
    import soundfile

    mapping_path = _regular_json(role_mapping_report_path, "role mapping report")
    mapping_root = mapping_path.parent
    mapping_report_sha256 = _sha256(mapping_path)
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    if mapping.get("schema") != AUTHORISED_ROLE_MAPPING_SCHEMA:
        raise ValueError("unsupported authorised role mapping schema")
    if mapping.get("document_sha256") != _document_sha256(mapping):
        raise ValueError("authorised role mapping document hash changed")
    _verify_artifacts(mapping_root, mapping.get("artifacts"), "role mapping")
    if (
        mapping.get("next", {}).get(
            "inactive_downstream_midi_comparison_allowed"
        )
        is not True
    ):
        raise ValueError("role mapping does not allow inactive downstream evidence")

    excerpt_path = _regular_json(
        mapping.get("source_excerpt", {}).get("report_path", ""),
        "source excerpt report",
    )
    expected_excerpt_report_hash = mapping.get("source_excerpt", {}).get(
        "report_sha256"
    )
    if _sha256(excerpt_path) != expected_excerpt_report_hash:
        raise ValueError("source excerpt report hash changed")
    excerpt_root = excerpt_path.parent
    excerpt = json.loads(excerpt_path.read_text(encoding="utf-8"))
    if excerpt.get("schema") != AUTHORISED_EXCERPT_SCHEMA:
        raise ValueError("unsupported authorised excerpt schema")
    if excerpt.get("document_sha256") != _excerpt_document_sha256(excerpt):
        raise ValueError("authorised excerpt document hash changed")
    if excerpt.get("document_sha256") != mapping.get("source_excerpt", {}).get(
        "document_sha256"
    ):
        raise ValueError("source excerpt document identity changed")
    _verify_artifacts(excerpt_root, excerpt.get("artifacts"), "excerpt")

    provider_packs = excerpt.get("provider_packs")
    proposals = excerpt.get("excerpt", {}).get("role_group_proposals")
    if not isinstance(provider_packs, Mapping) or not isinstance(proposals, Mapping):
        raise ValueError("source excerpt provider evidence is missing")
    if set(provider_packs) != set(proposals) or len(provider_packs) < 2:
        raise ValueError("at least two matching provider packs are required")

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"Narrow other evidence already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-",
            dir=destination.parent,
        )
    )
    temporary.chmod(0o700)
    try:
        leaves_root = temporary / "OTHER-LEAVES"
        leaves_root.mkdir(mode=0o700)
        leaves: dict[str, dict[str, Any]] = {}
        leaf_features: dict[str, dict[str, Any]] = {}
        source_rate = int(excerpt["excerpt"]["geometry"]["sample_rate"])

        for pack_id in sorted(provider_packs):
            pack = provider_packs[pack_id]
            pack_proposals = proposals[pack_id]
            if not isinstance(pack, Mapping) or not isinstance(pack_proposals, Mapping):
                raise ValueError(f"invalid provider evidence: {pack_id}")
            memberships = _assign_provider_items(pack_id, pack, pack_proposals)
            members = sorted(
                memberships["other"],
                key=lambda item: str(item.get("source_path", "")).casefold(),
            )
            pack_out = leaves_root / _safe_token(pack_id)
            pack_out.mkdir(mode=0o700)
            leaves[pack_id] = {}
            leaf_features[pack_id] = {}
            for index, item in enumerate(members, start=1):
                leaf_id = f"leaf-{index:02d}"
                source_path = _artifact_path(
                    excerpt_root,
                    item.get("excerpt"),
                    f"{pack_id} other {leaf_id}",
                )
                value, rate = soundfile.read(
                    source_path,
                    dtype="float32",
                    always_2d=True,
                )
                if int(rate) != source_rate:
                    raise ValueError(f"{pack_id} {leaf_id} source geometry changed")
                target = pack_out / f"{leaf_id}.wav"
                common_value, derivation = _write_model_input(
                    value.astype("float64"),
                    source_rate=source_rate,
                    target=target,
                    soundfile=soundfile,
                    np=np,
                )
                _require_common_geometry(
                    common_value,
                    _SAMPLE_RATE,
                    f"{pack_id} {leaf_id}",
                )
                display_name = Path(str(item.get("source_path", ""))).name
                leaves[pack_id][leaf_id] = {
                    "display_name": display_name,
                    "normalised_label": _normalised_label(display_name),
                    "semantic_hint": _semantic_hint(display_name),
                    "source_sha256": item.get("source_sha256"),
                    "source_excerpt_sha256": item.get("excerpt", {}).get("sha256"),
                    "artifact": _artifact(temporary, target),
                    "derivation": derivation,
                }
                leaf_features[pack_id][leaf_id] = _features(
                    common_value.astype("float64"),
                    sample_rate=_SAMPLE_RATE,
                    np=np,
                )

        comparisons: dict[str, Any] = {}
        label_counterpart_observations: list[dict[str, Any]] = []
        semantic_counterpart_observations: list[dict[str, Any]] = []
        pack_ids = sorted(leaves)
        for left_index, left_pack in enumerate(pack_ids):
            for right_pack in pack_ids[left_index + 1 :]:
                comparison_id = f"{left_pack}__{right_pack}"
                matrix = {
                    left_id: {
                        right_id: _similarity(
                            leaf_features[left_pack][left_id],
                            leaf_features[right_pack][right_id],
                            np=np,
                        )
                        for right_id in leaves[right_pack]
                    }
                    for left_id in leaves[left_pack]
                }
                left_rankings = _rank_rows(matrix)
                transposed = {
                    right_id: {
                        left_id: matrix[left_id][right_id]
                        for left_id in leaves[left_pack]
                    }
                    for right_id in leaves[right_pack]
                }
                right_rankings = _rank_rows(transposed)
                comparisons[comparison_id] = {
                    "left_pack": left_pack,
                    "right_pack": right_pack,
                    "matrix": matrix,
                    "left_to_right_rankings": left_rankings,
                    "right_to_left_rankings": right_rankings,
                }
                label_counterpart_observations.extend(
                    _label_observations(
                        left_pack,
                        right_pack,
                        leaves,
                        left_rankings,
                        right_rankings,
                        label_field="normalised_label",
                        match_basis="normalised_provider_label",
                    )
                )
                semantic_counterpart_observations.extend(
                    _label_observations(
                        left_pack,
                        right_pack,
                        leaves,
                        left_rankings,
                        right_rankings,
                        label_field="semantic_hint",
                        match_basis="semantic_provider_hint",
                    )
                )

        _verify_artifacts(mapping_root, mapping.get("artifacts"), "role mapping")
        _verify_artifacts(excerpt_root, excerpt.get("artifacts"), "excerpt")
        if _sha256(mapping_path) != mapping_report_sha256:
            raise ValueError("role mapping report changed during narrow comparison")
        if _sha256(excerpt_path) != expected_excerpt_report_hash:
            raise ValueError("source excerpt report changed during narrow comparison")

        document: dict[str, Any] = {
            "schema": AUTHORISED_NARROW_OTHER_SCHEMA,
            "status": "complete_observation_not_acceptance",
            "evidence_scope": "private_development_only",
            "source_role_mapping": {
                "report_path": str(mapping_path),
                "report_sha256": mapping_report_sha256,
                "document_sha256": mapping["document_sha256"],
                "track_id": mapping["source_excerpt"]["track_id"],
                "start_seconds": mapping["source_excerpt"]["start_seconds"],
                "end_seconds": mapping["source_excerpt"]["end_seconds"],
            },
            "policy": {
                "scope": "provider leaves provisionally assigned to broad other",
                "common_sample_rate": _SAMPLE_RATE,
                "labels_contribute_to_audio_score": False,
                "similarity_is_descriptive_not_acceptance": True,
                "same_label_is_observation_not_ground_truth": True,
                "semantic_hint_is_observation_not_ground_truth": True,
                "similarity_weights": {
                    "spectral_shape": 0.55,
                    "envelope": 0.30,
                    "absolute_waveform": 0.15,
                },
            },
            "leaves": leaves,
            "pairwise_audio_comparisons": comparisons,
            "same_label_counterpart_observations": label_counterpart_observations,
            "semantic_counterpart_observations": semantic_counterpart_observations,
            "observations": {
                "provider_pack_count": len(leaves),
                "leaf_counts": {
                    pack_id: len(pack_leaves)
                    for pack_id, pack_leaves in leaves.items()
                },
                "same_label_counterpart_count": len(
                    label_counterpart_observations
                ),
                "semantic_counterpart_count": len(
                    semantic_counterpart_observations
                ),
                "all_same_label_counterparts_rank_first_both_directions": (
                    all(
                        item["rank_first_both_directions"]
                        for item in label_counterpart_observations
                    )
                    if label_counterpart_observations
                    else None
                ),
                "all_semantic_counterparts_rank_first_both_directions": (
                    all(
                        item["rank_first_both_directions"]
                        for item in semantic_counterpart_observations
                    )
                    if semantic_counterpart_observations
                    else None
                ),
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
                "leaf_auditions_created": True,
                "midi_created": False,
                "source_graph_mutated": False,
            },
            "limitations": [
                "Provider leaves can contain several instruments or separation leakage.",
                "A nearest neighbour is not necessarily the same musical source.",
                "Matching labels are provider metadata, not listening ground truth.",
                (
                    "Spectral, envelope and waveform similarity cannot identify "
                    "an instrument by themselves."
                ),
                "Human listening remains required before activating a narrow-stem mapping.",
            ],
            "next": {
                "human_leaf_review_required": True,
                "narrow_separator_choice_allowed": False,
                "automatic_mapping_selection_allowed": False,
            },
        }
        document["artifacts"] = _artifacts(temporary)
        document["document_sha256"] = _document_sha256(document)
        report_path = temporary / _REPORT_NAME
        _write_json(report_path, document)
        _make_private_tree(temporary)
        if os.path.lexists(destination):
            raise FileExistsError(
                f"Narrow other evidence output appeared during run: {destination}"
            )
        os.rename(temporary, destination)
        document["report"] = str(destination / _REPORT_NAME)
        return document
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _rank_rows(matrix: Mapping[str, Mapping[str, Mapping[str, float]]]) -> dict[str, Any]:
    rankings: dict[str, Any] = {}
    for source_id, row in matrix.items():
        ranked = sorted(
            row,
            key=lambda candidate_id: (
                -row[candidate_id]["evidence_similarity"],
                candidate_id,
            ),
        )
        best = row[ranked[0]]["evidence_similarity"]
        runner_up = row[ranked[1]]["evidence_similarity"] if len(ranked) > 1 else 0.0
        rankings[source_id] = {
            "ranked_leaf_ids": ranked,
            "nearest_leaf_id": ranked[0],
            "nearest_evidence_similarity": best,
            "margin_over_runner_up": round(best - runner_up, 9),
            "accepted": False,
        }
    return rankings


def _label_observations(
    left_pack: str,
    right_pack: str,
    leaves: Mapping[str, Mapping[str, Mapping[str, Any]]],
    left_rankings: Mapping[str, Mapping[str, Any]],
    right_rankings: Mapping[str, Mapping[str, Any]],
    *,
    label_field: str,
    match_basis: str,
) -> list[dict[str, Any]]:
    result = []
    for left_id, left in leaves[left_pack].items():
        label = left[label_field]
        if label is None:
            continue
        matches = [
            right_id
            for right_id, right in leaves[right_pack].items()
            if right[label_field] == label
        ]
        for right_id in matches:
            left_rank = left_rankings[left_id]["ranked_leaf_ids"].index(right_id) + 1
            right_rank = right_rankings[right_id]["ranked_leaf_ids"].index(left_id) + 1
            result.append(
                {
                    "left_pack": left_pack,
                    "left_leaf_id": left_id,
                    "left_display_name": left["display_name"],
                    "right_pack": right_pack,
                    "right_leaf_id": right_id,
                    "right_display_name": leaves[right_pack][right_id]["display_name"],
                    "matched_label": label,
                    "match_basis": match_basis,
                    "left_to_right_rank": left_rank,
                    "right_to_left_rank": right_rank,
                    "rank_first_both_directions": left_rank == 1 and right_rank == 1,
                    "accepted": False,
                }
            )
    return result


def _normalised_label(value: str) -> str:
    stem = Path(value).stem.casefold()
    stem = re.sub(r"^\s*\d+\s*[-_. ]*", "", stem)
    return "-".join(re.findall(r"[a-z0-9]+", stem))


def _semantic_hint(value: str) -> str | None:
    tokens = set(re.findall(r"[a-z0-9]+", Path(value).stem.casefold()))
    aliases = (
        ("keyboard", {"keyboard", "keyboards", "keys"}),
        ("guitar", {"guitar", "guitars"}),
        ("synth", {"synth", "synths", "synthesizer", "synthesizers"}),
        ("strings", {"string", "strings"}),
        ("wind", {"wind", "winds"}),
        ("piano", {"piano", "pianos"}),
        ("lead", {"lead"}),
        ("rhythm", {"rhythm"}),
        ("other", {"other"}),
    )
    for label, candidates in aliases:
        if tokens & candidates:
            return label
    return None


__all__: tuple[str, ...] = ()
