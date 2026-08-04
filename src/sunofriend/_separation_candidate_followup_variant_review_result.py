"""Verify and resolve the sealed second-remediation variant review.

Status is deliberately key-blind.  Resolution repeats every public check and
opens the sealed answer key only after the completed browser export, all audio
references and the reconstructed review contract have verified.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_candidate_followup_variant_review import (
    POLICY_ID,
    SCHEMA as REVIEW_SCHEMA,
    STATUS as REVIEW_STATUS,
    TARGET_SAMPLE_RATE,
    _FALSE_EFFECTS,
    _input_bindings,
    _load_verified_variant_inputs,
    _variant_definitions,
)
from ._separation_candidate_join_remediation_review import (
    ANSWER_KEY_NAME,
    REPORT_NAME as REVIEW_NAME,
)
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
)
from ._separation_full_song_join_remediation_review import (
    AUDIO_DIRECTORY,
    HTML_NAME,
    _PAIR_CHOICES,
)
from ._separation_full_song_join_remediation_review_result import (
    _audio_pcm24_sha256,
    _browser_json_equal,
    _finite_number,
    _immutable_review_document,
    _is_nonce,
    _is_sha256,
    _load_private_json_snapshot,
    _rendered_pcm24_sha256,
    _sample_rms,
    _verify_audio_record,
    _write_json_exclusive,
)


STATUS_SCHEMA = (
    "sunofriend.private-separation-candidate-followup-variant-review-status.v1"
)
RESULT_SCHEMA = (
    "sunofriend.private-separation-candidate-followup-variant-review-result.v1"
)
RESULT_STATUS = "complete_review_no_activation"
ANSWER_KEY_SCHEMA = (
    "sunofriend.private-separation-candidate-followup-variant-answer-key.v1"
)
_AUDIO_SCHEMA = (
    "sunofriend.private-separation-candidate-followup-variant-review-audio.v1"
)
_KINDS = ("boundary_role_pair", "patch_edge_pair", "complete_song_pair")
_ROLES = ("vocals", "instrumental", "reconstruction")
_CONTROL_IDENTITY = "followup_control"
_OUTCOME_SUFFIX = "_preferred"
_NEUTRAL_OUTCOMES = ("equivalent", "neither", "cannot_tell")
_MAXIMUM_NOTES_CHARACTERS = 1_000
_QUESTION = (
    "Do either of the two explicit second-remediation hypotheses improve the "
    "failed joins and edges without making the complete song worse?"
)
_LIMITATIONS = [
    "Candidate A/B identities are randomised independently per unit.",
    "The second edge hypothesis is repeated only where its PCM24 differs from the first.",
    "Short clips attenuate only the louder whole-window sample RMS.",
    "Complete-song files are byte-identical opaque package-local clones.",
    "A listening preference does not select, accept or publish a separator.",
]
_READINESS_SEED = {
    "variant_review_complete": False,
    "variant_preferred": False,
    "original_audible_joins_resolved": False,
    "publication_ready": False,
}
_PUBLIC_KEYS = {
    "schema",
    "status",
    "evidence_scope",
    "policy_id",
    "package_commitment",
    "question",
    "bindings",
    "expected_counts",
    "units",
    "summary",
    "readiness",
    "permissions",
    "effects",
    "limitations",
    "document_sha256",
}
_PUBLIC_UNIT_KEYS = {
    "unit_id",
    "kind",
    "title",
    "focus",
    "source_window",
    "level_policy",
    "audio",
    "heard",
    "choice",
    "notes",
}
_VERIFICATION_CLAIMS = {
    "review_seed_and_export_bounded_owner_only_snapshots": True,
    "public_semantics_reconstructed_from_verified_variants": True,
    "short_pcm24_pairs_verified_key_blind": True,
    "complete_song_clones_verified_key_blind": True,
    "adaptive_audible_windows_verified": True,
    "audio_inventory_exact_and_private": True,
    "identical_short_pcm24_pairs_recorded_as_identity_ambiguous": True,
}
_COMPLETE_ASSET = re.compile(r"audio/complete-song-asset-[0-9]{2,}\.wav\Z")


def _status_private_candidate_followup_variant_review(
    review_path: str | Path,
    *,
    plan_path: str | Path,
    review_package_dir: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
) -> dict[str, Any]:
    """Verify one completed export without reading the answer-key file."""

    context = _load_verified_public_review(
        review_path,
        plan_path=plan_path,
        review_package_dir=review_package_dir,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    review = context["review"]
    status: dict[str, Any] = {
        "schema": STATUS_SCHEMA,
        "status": "complete_review_verified_key_unopened",
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "package_commitment": review["package_commitment"],
        "question": review["question"],
        "review_export_sha256": context["review_snapshot"]["sha256"],
        "review_seed_sha256": context["seed_snapshot"]["sha256"],
        "reviewed_units": len(review["units"]),
        "counts_by_kind": _counts_by_kind(review["units"]),
        "audio_references_verified": context["audio_reference_count"],
        "unique_audio_files_verified": context["unique_audio_file_count"],
        "pcm24_identical_short_pairs": _identical_pair_count(
            context["audio_evidence"], complete=False
        ),
        "pcm24_identical_complete_song_pairs": _identical_pair_count(
            context["audio_evidence"], complete=True
        ),
        "answer_key_opened": False,
        "identity_mapping_revealed": False,
        "verification_claims": {
            **_VERIFICATION_CLAIMS,
            "answer_key_verified": False,
            "result_published_exclusively": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
    }
    status["document_sha256"] = _document_sha256(status)
    return status


def _resolve_private_candidate_followup_variant_review(
    review_path: str | Path,
    *,
    plan_path: str | Path,
    review_package_dir: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Resolve identities after key-blind verification without selecting a variant."""

    output = Path(out).expanduser().absolute()
    if not os.path.lexists(output.parent):
        output.parent.mkdir(parents=True, mode=0o700)
    _require_private_directory(
        output.parent, "private follow-up variant review result directory"
    )
    context = _load_verified_public_review(
        review_path,
        plan_path=plan_path,
        review_package_dir=review_package_dir,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    review = context["review"]
    answer, answer_snapshot = _load_verified_answer_key(
        context["review_package"],
        seed=context["seed"],
        source_context=context["source_context"],
        reconstructed=context["reconstructed"],
    )
    _verify_answer_bindings(
        review,
        answer,
        reconstructed=context["reconstructed"],
        audio_evidence=context["audio_evidence"],
    )

    outcome_names = _outcome_names(context["reconstructed"])
    counts = {kind: {outcome: 0 for outcome in outcome_names} for kind in _KINDS}
    overall = {outcome: 0 for outcome in outcome_names}
    resolved_units: list[dict[str, Any]] = []
    resolved_by_id: dict[str, str] = {}
    for unit, answer_unit, expected in zip(
        review["units"], answer["units"], context["reconstructed"]["units"]
    ):
        choice = str(unit["choice"])
        assignment = answer_unit["assignment"]
        pcm24_identical = bool(
            context["audio_evidence"][unit["unit_id"]].get("pcm24_identical", False)
        )
        resolved = (
            "equivalent"
            if pcm24_identical and choice in ("A", "B")
            else (
                _preferred_outcome(assignment[choice])
                if choice in ("A", "B")
                else choice
            )
        )
        counts[unit["kind"]][resolved] += 1
        overall[resolved] += 1
        resolved_by_id[unit["unit_id"]] = resolved
        resolved_units.append(
            {
                "unit_id": unit["unit_id"],
                "kind": unit["kind"],
                "title": unit["title"],
                "focus": unit["focus"],
                "source_window": deepcopy(unit["source_window"]),
                "comparison_set": expected["comparison_set"],
                "candidate_identity": expected["candidate_identity"],
                "boundary_index": expected.get("boundary_index"),
                "role": expected["role"],
                "action": expected.get("action"),
                "edge": expected.get("edge"),
                "blind_choice": choice,
                "candidate_a_identity": assignment["A"],
                "candidate_b_identity": assignment["B"],
                "resolved_choice": resolved,
                "pcm24_identical": pcm24_identical,
                "blind_letter_preference_identity_suppressed": (
                    pcm24_identical and choice in ("A", "B")
                ),
                "notes": unit["notes"],
            }
        )

    inherited = _verify_inherited_identical_units(
        context["source_context"],
        reconstructed=context["reconstructed"],
        resolved_by_id=resolved_by_id,
    )
    eligibility = _candidate_eligibility(
        context["source_context"],
        reconstructed=context["reconstructed"],
        resolved_by_id=resolved_by_id,
        inherited=inherited,
    )
    eligible = [
        candidate_id
        for candidate_id, evidence in eligibility.items()
        if evidence["eligible_for_fresh_all_boundary_review"] is True
    ]
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "status": RESULT_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "blind_review": True,
        "package_commitment": review["package_commitment"],
        "bindings": {
            **deepcopy(context["seed"]["bindings"]),
            "review_seed_sha256": context["seed_snapshot"]["sha256"],
            "review_export_sha256": context["review_snapshot"]["sha256"],
            "answer_key_sha256": answer_snapshot["sha256"],
            "answer_key_document_sha256": answer["document_sha256"],
        },
        "reviewed_unit_count": len(resolved_units),
        "pcm24_identical_short_pairs": _identical_pair_count(
            context["audio_evidence"], complete=False
        ),
        "pcm24_identical_complete_song_pairs": _identical_pair_count(
            context["audio_evidence"], complete=True
        ),
        "counts_by_kind_and_outcome": counts,
        "overall_outcome_counts": overall,
        "units": resolved_units,
        "inherited_pcm24_identical_units": inherited,
        "candidate_gate_evidence": eligibility,
        "fresh_all_boundary_review_eligible_variant_ids": eligible,
        "readiness_evidence": {
            "variant_review_complete": True,
            "one_or_more_variants_eligible_for_fresh_all_boundary_review": bool(
                eligible
            ),
            "variant_selected": False,
            "fresh_all_boundary_review_complete": False,
            "alignment_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "choices_are_human_listening_evidence": True,
            "pcm24_inheritance_requires_local_byte_identity": True,
            "eligibility_is_not_variant_selection": True,
            "eligible_variants_may_be_multiple": True,
            "comparative_preference_is_join_elimination": False,
            "comparative_preference_is_separator_accuracy": False,
            "answer_key_opened_only_after_complete_review_verified": True,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "verification_claims": {
            **_VERIFICATION_CLAIMS,
            "answer_key_verified": True,
            "result_published_exclusively": True,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": [
            "The execution, candidate and review trees must remain quiescent during verification.",
            "Eligibility permits only a fresh all-boundary review; it is not selection or acceptance.",
            "Inherited listening evidence is used only where both variant windows are PCM24-identical.",
        ],
    }
    result["document_sha256"] = _document_sha256(result)
    _write_json_exclusive(output, result)
    return {**result, "report": str(output)}


def _load_verified_public_review(
    review_path: str | Path,
    *,
    plan_path: str | Path,
    review_package_dir: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
) -> dict[str, Any]:
    review_package = Path(review_package_dir).expanduser().absolute()
    _require_private_directory(
        review_package, "private follow-up variant review package"
    )
    source_context = _load_verified_variant_inputs(
        plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    reconstructed = _reconstruct_public_review(source_context)
    seed_snapshot = _load_private_json_snapshot(
        review_package / REVIEW_NAME, "private follow-up variant review seed"
    )
    seed = seed_snapshot["document"]
    _verify_seed(seed, source_context=source_context, reconstructed=reconstructed)
    _verify_review_page(
        review_package / HTML_NAME, seed=seed, source_context=source_context
    )

    review_snapshot = _load_private_json_snapshot(
        review_path, "reviewed follow-up variant export"
    )
    review = review_snapshot["document"]
    if not _browser_json_equal(
        _immutable_review_document(review), _immutable_review_document(seed)
    ):
        raise ValueError("private follow-up variant export changed immutable evidence")
    _validate_completed_review(review)
    reference_count, unique_count, audio_paths = _verify_audio_references(
        review, review_package=review_package
    )
    audio_evidence = _verify_blind_audio_contract(
        review,
        reconstructed=reconstructed,
        audio_paths=audio_paths,
    )
    return {
        "review_package": review_package,
        "source_context": source_context,
        "seed_snapshot": seed_snapshot,
        "seed": seed,
        "review_snapshot": review_snapshot,
        "review": review,
        "reconstructed": reconstructed,
        "audio_evidence": audio_evidence,
        "audio_reference_count": reference_count,
        "unique_audio_file_count": unique_count,
    }


def _reconstruct_public_review(source_context: Mapping[str, Any]) -> dict[str, Any]:
    standard, preserved = _variant_definitions(source_context["plan"])
    units: list[dict[str, Any]] = []
    comparison_count = 0
    comparison_groups: list[dict[str, Any]] = []
    for window in source_context["plan"]["windows"]:
        for role, action in sorted(window["role_actions"].items()):
            comparison_count += 1
            group = _reconstructed_region_comparison(
                set_index=1,
                comparison_index=comparison_count,
                window=window,
                role=role,
                action=action,
                raw_path=source_context["base_paths"][role],
                candidate_path=source_context["variant_paths"][standard["variant_id"]][
                    role
                ],
                candidate_identity=standard["variant_id"],
            )
            units.extend(group)
            comparison_groups.append(
                {
                    "set_index": 1,
                    "candidate_identity": standard["variant_id"],
                    "boundary_index": int(window["boundary_index"]),
                    "role": role,
                    "action": deepcopy(dict(action)),
                    "unit_ids": [item["public"]["unit_id"] for item in group],
                }
            )
            if action["action"] == "edge_aware_reinference_and_blend_search":
                comparison_count += 1
                group = _reconstructed_region_comparison(
                    set_index=2,
                    comparison_index=comparison_count,
                    window=window,
                    role=role,
                    action=action,
                    raw_path=source_context["base_paths"][role],
                    candidate_path=source_context["variant_paths"][
                        preserved["variant_id"]
                    ][role],
                    candidate_identity=preserved["variant_id"],
                )
                units.extend(group)
                comparison_groups.append(
                    {
                        "set_index": 2,
                        "candidate_identity": preserved["variant_id"],
                        "boundary_index": int(window["boundary_index"]),
                        "role": role,
                        "action": deepcopy(dict(action)),
                        "unit_ids": [item["public"]["unit_id"] for item in group],
                    }
                )

    complete_groups: dict[str, list[str]] = {}
    for set_index, definition in enumerate((standard, preserved), start=1):
        candidate_identity = str(definition["variant_id"])
        complete_groups[candidate_identity] = []
        for role in _ROLES:
            unit_id = f"set-{set_index:02d}-complete-song-{role}"
            units.append(
                {
                    "public": {
                        "unit_id": unit_id,
                        "kind": "complete_song_pair",
                        "title": f"Complete song set {set_index}: {role}",
                        "focus": (
                            "Hear both complete tracks. Which remains useful overall and avoids new "
                            "clicks, cut-offs, level jumps or sudden tone changes?"
                        ),
                        "source_window": None,
                        "level_policy": (
                            "unchanged-full-song-files-package-local-byte-clones"
                        ),
                    },
                    "comparison_set": set_index,
                    "candidate_identity": candidate_identity,
                    "role": role,
                    "raw_path": source_context["base_paths"][role],
                    "candidate_path": source_context["variant_paths"][
                        candidate_identity
                    ][role],
                    "complete_records": {
                        _CONTROL_IDENTITY: _source_record(
                            source_context["base_paths"][role]
                        ),
                        candidate_identity: _source_record(
                            source_context["variant_paths"][candidate_identity][role]
                        ),
                    },
                }
            )
            complete_groups[candidate_identity].append(unit_id)

    expected_counts = {
        "boundary_role_pairs": comparison_count,
        "patch_edge_pairs": 2 * comparison_count,
        "complete_song_pairs": 2 * len(_ROLES),
        "total_units": 3 * comparison_count + 2 * len(_ROLES),
    }
    if len(units) != expected_counts["total_units"]:
        raise ValueError("private follow-up variant source semantics differ")
    return {
        "expected_counts": expected_counts,
        "units": units,
        "comparison_groups": comparison_groups,
        "complete_groups": complete_groups,
        "variant_ids": [standard["variant_id"], preserved["variant_id"]],
    }


def _reconstructed_region_comparison(
    *,
    set_index: int,
    comparison_index: int,
    window: Mapping[str, Any],
    role: str,
    action: Mapping[str, Any],
    raw_path: Path,
    candidate_path: Path,
    candidate_identity: str,
) -> list[dict[str, Any]]:
    boundary = int(window["boundary_index"])
    start = int(action["patch_start_frame"])
    end = int(action["patch_end_frame"])
    prefix = f"set-{set_index:02d}-trial-{comparison_index:02d}"
    result: list[dict[str, Any]] = []
    for kind, suffix, title, centre, focus, edge in (
        (
            "boundary_role_pair",
            "boundary",
            f"Set {set_index}, comparison {comparison_index}: boundary {boundary} {role}",
            (start + end) // 2,
            f"Which version has the less audible join while preserving {role} continuity?",
            None,
        ),
        (
            "patch_edge_pair",
            "start-edge",
            f"Set {set_index}, comparison {comparison_index}: start edge {role}",
            start,
            "Which version has the cleaner start transition without a click, jump or cut-off?",
            "start",
        ),
        (
            "patch_edge_pair",
            "end-edge",
            f"Set {set_index}, comparison {comparison_index}: end edge {role}",
            end,
            "Which version has the cleaner end transition without a click, jump or cut-off?",
            "end",
        ),
    ):
        window_claim = _audible_source_window(
            raw_path, candidate_path, centre_frame=centre
        )
        result.append(
            {
                "public": {
                    "unit_id": f"{prefix}-{boundary:02d}-{role}-{suffix}",
                    "kind": kind,
                    "title": title,
                    "focus": focus,
                    "source_window": window_claim,
                    "level_policy": (
                        "attenuate-louder-to-quieter-whole-window-sample-rms-v1"
                    ),
                },
                "comparison_set": set_index,
                "candidate_identity": candidate_identity,
                "boundary_index": boundary,
                "role": role,
                "action": action["action"],
                "edge": edge,
                "failed_edges": deepcopy(action.get("failed_edges", [])),
                "raw_path": raw_path,
                "candidate_path": candidate_path,
            }
        )
    return result


def _audible_source_window(
    raw_path: Path, candidate_path: Path, *, centre_frame: int
) -> dict[str, Any]:
    import numpy as np
    import soundfile

    total_frames = int(soundfile.info(raw_path).frames)
    for seconds in (1, 2, 3, 4):
        half_frames = seconds * TARGET_SAMPLE_RATE
        start = max(0, centre_frame - half_frames)
        end = min(total_frames, centre_frame + half_frames)
        if end - start < TARGET_SAMPLE_RATE:
            continue
        raw, raw_rate = soundfile.read(
            raw_path, start=start, stop=end, dtype="float64", always_2d=True
        )
        candidate, candidate_rate = soundfile.read(
            candidate_path, start=start, stop=end, dtype="float64", always_2d=True
        )
        if (
            int(raw_rate) != TARGET_SAMPLE_RATE
            or int(candidate_rate) != TARGET_SAMPLE_RATE
            or raw.shape != candidate.shape
            or raw.shape != (end - start, 2)
        ):
            raise ValueError("private follow-up variant clip geometry differs")
        if min(_sample_rms(raw, np=np), _sample_rms(candidate, np=np)) > 10 ** (
            -60 / 20
        ):
            return {
                "start_frame": start,
                "end_frame": end,
                "start_seconds": start / TARGET_SAMPLE_RATE,
                "end_seconds": end / TARGET_SAMPLE_RATE,
            }
    raise ValueError("private follow-up variant clip is too quiet")


def _verify_seed(
    seed: Mapping[str, Any],
    *,
    source_context: Mapping[str, Any],
    reconstructed: Mapping[str, Any],
) -> None:
    units = seed.get("units")
    bindings = seed.get("bindings")
    expected_bindings = _input_bindings(source_context)
    if (
        set(seed) != _PUBLIC_KEYS
        or seed.get("schema") != REVIEW_SCHEMA
        or seed.get("status") != REVIEW_STATUS
        or seed.get("evidence_scope") != "private_development_only"
        or seed.get("policy_id") != POLICY_ID
        or seed.get("question") != _QUESTION
        or seed.get("limitations") != _LIMITATIONS
        or seed.get("expected_counts") != reconstructed["expected_counts"]
        or seed.get("summary")
        != {"reviewed_units": 0, "total_units": len(units or []), "complete": False}
        or seed.get("readiness") != _READINESS_SEED
        or seed.get("permissions") != _FALSE_PERMISSIONS
        or seed.get("effects") != _FALSE_EFFECTS
        or seed.get("document_sha256") != _document_sha256(seed)
        or not isinstance(units, list)
        or len(units) != reconstructed["expected_counts"]["total_units"]
        or not isinstance(bindings, Mapping)
        or any(bindings.get(key) != value for key, value in expected_bindings.items())
        or set(bindings)
        != set(expected_bindings)
        | {
            "audio_manifest_sha256",
            "answer_key_sha256",
            "answer_key_document_sha256",
        }
        or any(not _is_sha256(bindings[key]) for key in bindings)
    ):
        raise ValueError("private follow-up variant review seed differs")
    if _audio_manifest_sha256(seed) != bindings["audio_manifest_sha256"]:
        raise ValueError("private follow-up variant audio manifest differs")
    commitment = hashlib.sha256(
        (
            f"{bindings['answer_key_sha256']}:"
            f"{bindings['answer_key_document_sha256']}:"
            f"{bindings['audio_manifest_sha256']}"
        ).encode("ascii")
    ).hexdigest()
    if seed.get("package_commitment") != commitment:
        raise ValueError("private follow-up variant commitment differs")
    identifiers: set[str] = set()
    for unit, expected in zip(units, reconstructed["units"]):
        _validate_seed_unit(unit)
        if unit["unit_id"] in identifiers:
            raise ValueError("private follow-up variant unit identities differ")
        identifiers.add(unit["unit_id"])
        if any(
            not _browser_json_equal(unit.get(key), value)
            for key, value in expected["public"].items()
        ):
            raise ValueError("private follow-up variant source semantics differ")
        if unit["kind"] != "complete_song_pair":
            if any(
                unit["audio"][slot]["path"]
                != f"{AUDIO_DIRECTORY}/{unit['unit_id']}-{slot}.wav"
                for slot in ("A", "B")
            ):
                raise ValueError("private follow-up variant short audio path differs")
        elif any(
            _COMPLETE_ASSET.fullmatch(unit["audio"][slot]["path"]) is None
            for slot in ("A", "B")
        ):
            raise ValueError("private follow-up variant complete audio path differs")


def _validate_seed_unit(unit: object) -> None:
    if not isinstance(unit, Mapping) or set(unit) != _PUBLIC_UNIT_KEYS:
        raise ValueError("private follow-up variant review unit differs")
    audio = unit.get("audio")
    if (
        unit.get("kind") not in _KINDS
        or not isinstance(unit.get("unit_id"), str)
        or not unit["unit_id"]
        or not isinstance(unit.get("title"), str)
        or not unit["title"]
        or not isinstance(unit.get("focus"), str)
        or not unit["focus"]
        or not isinstance(audio, Mapping)
        or set(audio) != {"A", "B"}
        or unit.get("heard") != {"A": False, "B": False}
        or unit.get("choice") is not None
        or unit.get("notes") != ""
    ):
        raise ValueError("private follow-up variant review unit differs")
    for record in audio.values():
        if (
            not isinstance(record, Mapping)
            or set(record) != {"path", "sha256", "bytes"}
            or not isinstance(record.get("path"), str)
            or not record["path"]
            or Path(record["path"]).is_absolute()
            or not _is_sha256(record.get("sha256"))
            or not isinstance(record.get("bytes"), int)
            or isinstance(record.get("bytes"), bool)
            or record["bytes"] <= 0
        ):
            raise ValueError("private follow-up variant audio claim differs")


def _validate_completed_review(review: Mapping[str, Any]) -> None:
    units = review.get("units")
    if (
        review.get("status") != "reviewed"
        or not isinstance(units, list)
        or review.get("summary")
        != {"reviewed_units": len(units), "total_units": len(units), "complete": True}
        or review.get("permissions") != _FALSE_PERMISSIONS
        or review.get("effects") != _FALSE_EFFECTS
    ):
        raise ValueError("private follow-up variant review is incomplete")
    for unit in units:
        if (
            not isinstance(unit, Mapping)
            or unit.get("heard") != {"A": True, "B": True}
            or unit.get("choice") not in _PAIR_CHOICES
            or not isinstance(unit.get("notes"), str)
            or len(unit["notes"]) > _MAXIMUM_NOTES_CHARACTERS
        ):
            raise ValueError("private follow-up variant review unit is incomplete")


def _verify_review_page(
    path: Path, *, seed: Mapping[str, Any], source_context: Mapping[str, Any]
) -> None:
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("private follow-up variant review page differs")
    try:
        page = path.read_text(encoding="utf-8")
        embedded = page.split('<script id="seed" type="application/json">', 1)[1].split(
            "</script><script>", 1
        )[0]
    except (OSError, UnicodeDecodeError, IndexError) as error:
        raise ValueError("private follow-up variant review page differs") from error
    standard, preserved = _variant_definitions(source_context["plan"])
    if (
        json.loads(embedded) != seed
        or "Export reviewed JSON" not in page
        or "Mark review complete" not in page
        or '"assignment"' in page
        or ANSWER_KEY_NAME in page
        or standard["variant_id"] in page
        or preserved["variant_id"] in page
    ):
        raise ValueError("private follow-up variant review page differs")


def _verify_audio_references(
    review: Mapping[str, Any], *, review_package: Path
) -> tuple[int, int, dict[str, dict[str, Path]]]:
    audio_root = review_package / AUDIO_DIRECTORY
    _require_private_directory(audio_root, "private follow-up variant audio root")
    referenced_records: dict[Path, dict[str, Any]] = {}
    paths_by_unit: dict[str, dict[str, Path]] = {}
    reference_count = 0
    for unit in review["units"]:
        unit_paths: dict[str, Path] = {}
        for slot in ("A", "B"):
            record = unit["audio"][slot]
            path = _verify_audio_record(
                review_package, record, allowed_roots=(audio_root,)
            )
            previous = referenced_records.get(path)
            if previous is not None and (
                unit["kind"] != "complete_song_pair" or previous != dict(record)
            ):
                raise ValueError(
                    "private follow-up variant audio is reused incorrectly"
                )
            referenced_records[path] = dict(record)
            unit_paths[slot] = path
            reference_count += 1
        paths_by_unit[unit["unit_id"]] = unit_paths
    expected = int(review["expected_counts"]["total_units"]) * 2
    if reference_count != expected:
        raise ValueError("private follow-up variant audio reference inventory differs")
    actual_files: set[Path] = set()
    for item in audio_root.iterdir():
        if item.is_dir():
            raise ValueError("private follow-up variant audio tree differs")
        actual_files.add(item.resolve(strict=True))
    if actual_files != set(referenced_records):
        raise ValueError("private follow-up variant audio file inventory differs")
    return reference_count, len(referenced_records), paths_by_unit


def _verify_blind_audio_contract(
    review: Mapping[str, Any],
    *,
    reconstructed: Mapping[str, Any],
    audio_paths: Mapping[str, Mapping[str, Path]],
) -> dict[str, dict[str, Any]]:
    import numpy as np
    import soundfile

    evidence: dict[str, dict[str, Any]] = {}
    for unit, expected in zip(review["units"], reconstructed["units"]):
        unit_id = unit["unit_id"]
        if unit_id != expected["public"]["unit_id"]:
            raise ValueError("private follow-up variant audio semantics differ")
        identities = (_CONTROL_IDENTITY, expected["candidate_identity"])
        if unit["kind"] == "complete_song_pair":
            actual = [
                {
                    "sha256": unit["audio"][slot]["sha256"],
                    "bytes": unit["audio"][slot]["bytes"],
                }
                for slot in ("A", "B")
            ]
            wanted = [expected["complete_records"][identity] for identity in identities]
            if _sorted_claims(actual) != _sorted_claims(wanted):
                raise ValueError(
                    "private follow-up variant complete-song audio differs"
                )
            evidence[unit_id] = {
                "kind": unit["kind"],
                "pcm24_identical": len(
                    {(item["sha256"], item["bytes"]) for item in wanted}
                )
                == 1,
                "complete_records": expected["complete_records"],
            }
            continue
        window = expected["public"]["source_window"]
        start = int(window["start_frame"])
        end = int(window["end_frame"])
        values: dict[str, Any] = {}
        rms: dict[str, float] = {}
        for identity, path in (
            (_CONTROL_IDENTITY, expected["raw_path"]),
            (expected["candidate_identity"], expected["candidate_path"]),
        ):
            values[identity], rate = soundfile.read(
                path, start=start, stop=end, dtype="float64", always_2d=True
            )
            if int(rate) != TARGET_SAMPLE_RATE or values[identity].shape != (
                end - start,
                2,
            ):
                raise ValueError("private follow-up variant clip geometry differs")
            rms[identity] = _sample_rms(values[identity], np=np)
        target = min(rms.values())
        if target <= 10 ** (-60 / 20):
            raise ValueError("private follow-up variant clip is too quiet")
        gains = {identity: target / rms[identity] for identity in identities}
        expected_hashes = {
            identity: _rendered_pcm24_sha256(
                values[identity] * gains[identity], soundfile=soundfile, np=np
            )
            for identity in identities
        }
        actual_hashes = {
            slot: _audio_pcm24_sha256(
                audio_paths[unit_id][slot],
                expected_frames=end - start,
                soundfile=soundfile,
                np=np,
            )
            for slot in ("A", "B")
        }
        if sorted(actual_hashes.values()) != sorted(expected_hashes.values()):
            raise ValueError("private follow-up variant short review audio differs")
        evidence[unit_id] = {
            "kind": unit["kind"],
            "pcm24_identical": len(set(expected_hashes.values())) == 1,
            "expected_hashes": expected_hashes,
            "actual_hashes": actual_hashes,
            "levels": {
                "raw_gain": round(gains[_CONTROL_IDENTITY], 12),
                "candidate_gain": round(gains[expected["candidate_identity"]], 12),
                "raw_rms": round(rms[_CONTROL_IDENTITY], 12),
                "candidate_rms": round(rms[expected["candidate_identity"]], 12),
            },
        }
    return evidence


def _load_verified_answer_key(
    review_package: Path,
    *,
    seed: Mapping[str, Any],
    source_context: Mapping[str, Any],
    reconstructed: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = _load_private_json_snapshot(
        review_package / ANSWER_KEY_NAME, "private follow-up variant answer key"
    )
    bindings = seed["bindings"]
    answer = snapshot["document"]
    expected_bindings = {
        **_input_bindings(source_context),
        "audio_manifest_sha256": bindings["audio_manifest_sha256"],
    }
    if (
        snapshot["sha256"] != bindings["answer_key_sha256"]
        or answer.get("schema") != ANSWER_KEY_SCHEMA
        or answer.get("status") != "sealed_do_not_open_before_review"
        or answer.get("document_sha256") != _document_sha256(answer)
        or answer.get("document_sha256") != bindings["answer_key_document_sha256"]
        or answer.get("bindings") != expected_bindings
        or answer.get("permissions") != _FALSE_PERMISSIONS
        or not _is_nonce(answer.get("nonce"))
        or not isinstance(answer.get("units"), list)
        or len(answer["units"]) != len(seed["units"])
    ):
        raise ValueError("private follow-up variant answer key differs")
    for seed_unit, answer_unit, expected in zip(
        seed["units"], answer["units"], reconstructed["units"]
    ):
        _validate_answer_unit(seed_unit, answer_unit, expected=expected)
    return answer, snapshot


def _validate_answer_unit(
    seed_unit: Mapping[str, Any], answer_unit: object, *, expected: Mapping[str, Any]
) -> None:
    if not isinstance(answer_unit, Mapping):
        raise ValueError("private follow-up variant answer unit differs")
    assignment = answer_unit.get("assignment")
    expected_identities = {_CONTROL_IDENTITY, expected["candidate_identity"]}
    if (
        answer_unit.get("unit_id") != seed_unit["unit_id"]
        or not isinstance(assignment, Mapping)
        or set(assignment) != {"A", "B"}
        or set(assignment.values()) != expected_identities
    ):
        raise ValueError("private follow-up variant answer unit differs")
    if seed_unit["kind"] == "complete_song_pair":
        if set(answer_unit) != {"unit_id", "assignment"}:
            raise ValueError("private follow-up variant complete answer differs")
        return
    if set(answer_unit) != {
        "unit_id",
        "assignment",
        "raw_gain",
        "candidate_gain",
        "raw_rms",
        "candidate_rms",
    }:
        raise ValueError("private follow-up variant short answer differs")
    raw_gain = _finite_number(answer_unit.get("raw_gain"), "follow-up control gain")
    candidate_gain = _finite_number(answer_unit.get("candidate_gain"), "variant gain")
    raw_rms = _finite_number(answer_unit.get("raw_rms"), "follow-up control RMS")
    candidate_rms = _finite_number(answer_unit.get("candidate_rms"), "variant RMS")
    if (
        not 0 < raw_gain <= 1
        or not 0 < candidate_gain <= 1
        or raw_rms <= 0
        or candidate_rms <= 0
        or max(raw_gain, candidate_gain) != 1
    ):
        raise ValueError("private follow-up variant level evidence differs")


def _verify_answer_bindings(
    review: Mapping[str, Any],
    answer: Mapping[str, Any],
    *,
    reconstructed: Mapping[str, Any],
    audio_evidence: Mapping[str, Mapping[str, Any]],
) -> None:
    for unit, answer_unit, expected in zip(
        review["units"], answer["units"], reconstructed["units"]
    ):
        assignment = answer_unit["assignment"]
        evidence = audio_evidence[unit["unit_id"]]
        if unit["kind"] == "complete_song_pair":
            for slot in ("A", "B"):
                expected_record = expected["complete_records"][assignment[slot]]
                actual_record = {
                    "sha256": unit["audio"][slot]["sha256"],
                    "bytes": unit["audio"][slot]["bytes"],
                }
                if actual_record != expected_record:
                    raise ValueError(
                        "private follow-up variant complete answer binding differs"
                    )
            continue
        if any(
            evidence["actual_hashes"][slot]
            != evidence["expected_hashes"][assignment[slot]]
            for slot in ("A", "B")
        ) or any(
            not _browser_json_equal(answer_unit.get(key), value)
            for key, value in evidence["levels"].items()
        ):
            raise ValueError("private follow-up variant short answer binding differs")


def _verify_inherited_identical_units(
    source_context: Mapping[str, Any],
    *,
    reconstructed: Mapping[str, Any],
    resolved_by_id: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Prove when the preserved variant may reuse an explicit standard review."""

    import numpy as np
    import soundfile

    standard, preserved = _variant_definitions(source_context["plan"])
    result: list[dict[str, Any]] = []
    for group in reconstructed["comparison_groups"]:
        if (
            group["candidate_identity"] != standard["variant_id"]
            or group["action"]["action"] == "edge_aware_reinference_and_blend_search"
        ):
            continue
        for unit_id in group["unit_ids"]:
            expected = _unit_by_id(reconstructed, unit_id)
            window = expected["public"]["source_window"]
            start = int(window["start_frame"])
            end = int(window["end_frame"])
            hashes: dict[str, str] = {}
            for candidate_id in (standard["variant_id"], preserved["variant_id"]):
                path = source_context["variant_paths"][candidate_id][group["role"]]
                samples, rate = soundfile.read(
                    path, start=start, stop=end, dtype="int32", always_2d=True
                )
                if int(rate) != TARGET_SAMPLE_RATE or samples.shape != (end - start, 2):
                    raise ValueError(
                        "private follow-up inherited PCM24 geometry differs"
                    )
                hashes[candidate_id] = hashlib.sha256(
                    np.asarray(samples, dtype="<i4").tobytes(order="C")
                ).hexdigest()
            if len(set(hashes.values())) != 1:
                raise ValueError(
                    "private follow-up preserved variant differs in an inherited review window"
                )
            result.append(
                {
                    "source_review_unit_id": unit_id,
                    "source_candidate_identity": standard["variant_id"],
                    "inheriting_candidate_identity": preserved["variant_id"],
                    "pcm24_sequence_sha256": hashes[standard["variant_id"]],
                    "resolved_choice": _translate_candidate_outcome(
                        resolved_by_id[unit_id],
                        from_candidate=standard["variant_id"],
                        to_candidate=preserved["variant_id"],
                    ),
                }
            )
    return result


def _candidate_eligibility(
    source_context: Mapping[str, Any],
    *,
    reconstructed: Mapping[str, Any],
    resolved_by_id: Mapping[str, str],
    inherited: list[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    standard, preserved = _variant_definitions(source_context["plan"])
    inherited_by_unit = {
        item["source_review_unit_id"]: item["resolved_choice"] for item in inherited
    }
    evidence: dict[str, dict[str, Any]] = {}
    for candidate_id in (standard["variant_id"], preserved["variant_id"]):
        checks: list[dict[str, Any]] = []
        for window in source_context["plan"]["windows"]:
            for role, action in sorted(window["role_actions"].items()):
                group = _explicit_group(
                    reconstructed,
                    candidate_identity=candidate_id,
                    boundary_index=int(window["boundary_index"]),
                    role=role,
                )
                inherited_check = False
                if group is None:
                    if candidate_id != preserved["variant_id"]:
                        raise ValueError(
                            "private follow-up variant gate evidence differs"
                        )
                    group = _explicit_group(
                        reconstructed,
                        candidate_identity=standard["variant_id"],
                        boundary_index=int(window["boundary_index"]),
                        role=role,
                    )
                    inherited_check = True
                assert group is not None
                outcomes: dict[str, str] = {}
                for unit_id in group["unit_ids"]:
                    expected = _unit_by_id(reconstructed, unit_id)
                    key = "boundary" if expected["edge"] is None else expected["edge"]
                    outcome = (
                        inherited_by_unit[unit_id]
                        if inherited_check
                        else resolved_by_id[unit_id]
                    )
                    outcomes[key] = outcome
                candidate_preferred = _preferred_outcome(candidate_id)
                boundary_allowed = (
                    {candidate_preferred, "equivalent"}
                    if action["action"] == "edge_aware_reinference_and_blend_search"
                    else {candidate_preferred}
                )
                boundary_pass = outcomes["boundary"] in boundary_allowed
                failed_edges = {item["edge"] for item in action.get("failed_edges", [])}
                edge_pass = all(
                    outcomes[edge]
                    in (
                        {candidate_preferred}
                        if edge in failed_edges
                        else {candidate_preferred, "equivalent"}
                    )
                    for edge in ("start", "end")
                )
                checks.append(
                    {
                        "boundary_index": int(window["boundary_index"]),
                        "role": role,
                        "action": action["action"],
                        "evidence_mode": (
                            "pcm24_identical_inheritance"
                            if inherited_check
                            else "explicit_blind_review"
                        ),
                        "outcomes": outcomes,
                        "failed_edges": sorted(failed_edges),
                        "boundary_gate_pass": boundary_pass,
                        "edge_gate_pass": edge_pass,
                        "pass": boundary_pass and edge_pass,
                    }
                )
        complete_outcomes = {
            _unit_by_id(reconstructed, unit_id)["role"]: resolved_by_id[unit_id]
            for unit_id in reconstructed["complete_groups"][candidate_id]
        }
        song_pass = all(
            outcome in {_preferred_outcome(candidate_id), "equivalent"}
            for outcome in complete_outcomes.values()
        )
        targeted_pass = all(item["pass"] for item in checks)
        evidence[candidate_id] = {
            "targeted_checks": checks,
            "complete_song_outcomes": complete_outcomes,
            "all_targeted_checks_pass": targeted_pass,
            "all_complete_songs_candidate_or_equivalent": song_pass,
            "eligible_for_fresh_all_boundary_review": targeted_pass and song_pass,
            "selected": False,
            "accepted": False,
        }
    return evidence


def _explicit_group(
    reconstructed: Mapping[str, Any],
    *,
    candidate_identity: str,
    boundary_index: int,
    role: str,
) -> Mapping[str, Any] | None:
    matches = [
        item
        for item in reconstructed["comparison_groups"]
        if item["candidate_identity"] == candidate_identity
        and item["boundary_index"] == boundary_index
        and item["role"] == role
    ]
    if len(matches) > 1:
        raise ValueError("private follow-up variant comparison inventory differs")
    return matches[0] if matches else None


def _unit_by_id(reconstructed: Mapping[str, Any], unit_id: str) -> Mapping[str, Any]:
    matches = [
        item for item in reconstructed["units"] if item["public"]["unit_id"] == unit_id
    ]
    if len(matches) != 1:
        raise ValueError("private follow-up variant unit inventory differs")
    return matches[0]


def _translate_candidate_outcome(
    outcome: str, *, from_candidate: str, to_candidate: str
) -> str:
    if outcome == _preferred_outcome(from_candidate):
        return _preferred_outcome(to_candidate)
    return outcome


def _preferred_outcome(identity: str) -> str:
    return f"{identity.replace('-', '_')}{_OUTCOME_SUFFIX}"


def _outcome_names(reconstructed: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        _preferred_outcome(_CONTROL_IDENTITY),
        *(_preferred_outcome(item) for item in reconstructed["variant_ids"]),
        *_NEUTRAL_OUTCOMES,
    )


def _source_record(path: Path) -> dict[str, Any]:
    return {"sha256": _sha256(path), "bytes": path.stat().st_size}


def _sorted_claims(records: list[Mapping[str, Any]]) -> list[bytes]:
    return sorted(canonical_json_bytes(dict(item)) for item in records)


def _audio_manifest_sha256(review: Mapping[str, Any]) -> str:
    manifest = {
        "schema": _AUDIO_SCHEMA,
        "units": [
            {"unit_id": unit["unit_id"], "audio": unit["audio"]}
            for unit in review["units"]
        ],
    }
    return hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()


def _counts_by_kind(units: list[Mapping[str, Any]]) -> dict[str, int]:
    return {kind: sum(unit.get("kind") == kind for unit in units) for kind in _KINDS}


def _identical_pair_count(
    evidence: Mapping[str, Mapping[str, Any]], *, complete: bool
) -> int:
    wanted_kind = "complete_song_pair" if complete else None
    return sum(
        item.get("pcm24_identical") is True
        and (
            item.get("kind") == wanted_kind
            if complete
            else item.get("kind") != "complete_song_pair"
        )
        for item in evidence.values()
    )


__all__: tuple[str, ...] = ()
