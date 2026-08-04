"""Verify and resolve one private targeted join-remediation review.

The status path validates only the public review evidence and deliberately
does not open the sealed answer key.  The resolver repeats those checks before
opening the key and records the listener's identity-resolved evidence without
selecting, accepting or exposing a separator to any product route.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_full_song_executor import (
    _require_private_directory,
    _require_private_regular,
)
from ._separation_full_song_join_remediation_executor import (
    CANDIDATE_REPORT_NAME,
    REPORT_NAME as EXECUTION_REPORT_NAME,
    SCHEMA as EXECUTION_SCHEMA,
    STATUS_COMPLETE as EXECUTION_STATUS,
    _FALSE_PERMISSIONS,
    _state_sha256,
    _verify_candidate_report,
)
from ._separation_full_song_join_remediation_review import (
    ANSWER_KEY_NAME,
    AUDIO_DIRECTORY,
    POLICY_ID,
    REPORT_NAME as REVIEW_NAME,
    SCHEMA as REVIEW_SCHEMA,
    STATUS as REVIEW_STATUS,
    TARGET_SAMPLE_RATE,
    _FALSE_EFFECTS,
    _PAIR_CHOICES,
    _review_instructions,
    _validated_grouped_patches,
)
from ._separation_full_song_review import (
    _load_stitch_report,
    _verify_stitch_audio,
)
from ._separation_full_song_stitch import REPORT_NAME as STITCH_REPORT_NAME

STATUS_SCHEMA = (
    "sunofriend.private-separation-full-song-join-remediation-review-status.v1"
)
RESULT_SCHEMA = (
    "sunofriend.private-separation-full-song-join-remediation-review-result.v1"
)
RESULT_STATUS = "complete_review_no_activation"
ANSWER_KEY_SCHEMA = (
    "sunofriend.private-separation-full-song-join-remediation-answer-key.v1"
)
_KINDS = ("boundary_role_pair", "patch_edge_pair", "complete_song_pair")
_IDENTITY_OUTCOMES = (
    "candidate_preferred",
    "raw_preferred",
    "equivalent",
    "neither",
    "cannot_tell",
)
_MAXIMUM_NOTES_CHARACTERS = 1_000
_MAXIMUM_REVIEW_EXPORT_BYTES = 8 * 1024 * 1024
_QUESTION = (
    "Did targeted overlap re-inference reduce the reviewed joins without "
    "creating worse patch edges or complete-song problems?"
)
_LIMITATIONS = [
    "Short-loop sample-RMS matching attenuates only the louder clip and is not LUFS matching.",
    "Complete-song A/B files are unchanged external controls and candidates, not copied into this package.",
    "A listening preference does not select, accept or publish a separator.",
]
_PUBLIC_DOCUMENT_KEYS = {
    "schema",
    "status",
    "evidence_scope",
    "policy_id",
    "package_commitment",
    "question",
    "instructions",
    "bindings",
    "expected_counts",
    "units",
    "summary",
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
_RESULT_EFFECTS = {
    **_FALSE_EFFECTS,
    "candidate_audio_selected": False,
    "readiness_gate_closed": False,
    "review_evidence_mutated": False,
}
_PUBLIC_VERIFICATION_CLAIMS = {
    "review_seed_and_export_bounded_single_read_snapshots": True,
    "review_seed_and_export_no_symlink_follow": True,
    "review_seed_and_export_identity_stable_before_after": True,
    "review_seed_and_export_owner_only_single_link": True,
    "public_semantics_reconstructed_from_verified_sources": True,
    "short_pcm24_pairs_verified_key_blind": True,
    "complete_song_records_verified_key_blind": True,
    "identical_short_pcm24_pairs_rejected": True,
}
_SNAPSHOT_SCOPE_LIMITATIONS = {
    "execution_candidate_and_stitch_json_snapshot_held": False,
    "wav_descriptors_snapshot_held_across_verification": False,
    "non_snapshot_private_inputs_assumed_quiescent": True,
}


class _PrivateJsonSnapshotError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        path: Path,
        chmod_recommended: bool = False,
    ) -> None:
        super().__init__(message)
        self.path = path
        self.chmod_recommended = chmod_recommended


def _status_private_join_remediation_review(
    review_path: str | Path,
    *,
    review_package_dir: str | Path,
    execution_dir: str | Path,
    stitch_package_dir: str | Path,
) -> dict[str, Any]:
    """Verify one complete export without opening or revealing the answer key."""

    context = _load_verified_public_review(
        review_path,
        review_package_dir=review_package_dir,
        execution_dir=execution_dir,
        stitch_package_dir=stitch_package_dir,
    )
    review = context["review"]
    status = {
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
        "answer_key_opened": False,
        "identity_mapping_revealed": False,
        "verification_claims": {
            **_PUBLIC_VERIFICATION_CLAIMS,
            "answer_key_bounded_single_read_snapshot_verified": False,
            "answer_key_slot_identities_and_levels_verified": False,
            "result_temp_fsynced_before_no_overwrite_publication": False,
            "result_published_by_no_overwrite_hard_link": False,
        },
        "verification_limitations": dict(_SNAPSHOT_SCOPE_LIMITATIONS),
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_RESULT_EFFECTS),
    }
    status["document_sha256"] = _document_sha256(status)
    return status


def _resolve_private_join_remediation_review(
    review_path: str | Path,
    *,
    review_package_dir: str | Path,
    execution_dir: str | Path,
    stitch_package_dir: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Resolve one verified complete export without activating its outcome."""

    output = Path(out).expanduser().absolute()
    if not os.path.lexists(output.parent):
        output.parent.mkdir(parents=True, mode=0o700)
    _require_private_directory(
        output.parent, "private join-remediation review result directory"
    )
    context = _load_verified_public_review(
        review_path,
        review_package_dir=review_package_dir,
        execution_dir=execution_dir,
        stitch_package_dir=stitch_package_dir,
    )
    seed = context["seed"]
    review = context["review"]
    answer, answer_snapshot = _load_verified_answer_key(
        context["review_package"], seed=seed
    )
    _verify_answer_key_audio_bindings(
        review,
        answer,
        reconstructed=context["reconstructed"],
        audio_evidence=context["audio_evidence"],
    )
    answers = answer["units"]
    resolved_units: list[dict[str, Any]] = []
    summary = {kind: {outcome: 0 for outcome in _IDENTITY_OUTCOMES} for kind in _KINDS}
    overall = {outcome: 0 for outcome in _IDENTITY_OUTCOMES}
    for unit, answer_unit in zip(review["units"], answers):
        choice = str(unit["choice"])
        assignment = answer_unit["assignment"]
        if choice in ("A", "B"):
            resolved_choice = f"{assignment[choice]}_preferred"
        else:
            resolved_choice = choice
        summary[unit["kind"]][resolved_choice] += 1
        overall[resolved_choice] += 1
        resolved_units.append(
            {
                "unit_id": unit["unit_id"],
                "kind": unit["kind"],
                "title": unit["title"],
                "focus": unit["focus"],
                "source_window": deepcopy(unit["source_window"]),
                "blind_choice": choice,
                "candidate_a_identity": assignment["A"],
                "candidate_b_identity": assignment["B"],
                "resolved_choice": resolved_choice,
                "notes": unit["notes"],
            }
        )

    boundary = summary["boundary_role_pair"]
    edges = summary["patch_edge_pair"]
    songs = summary["complete_song_pair"]
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "status": RESULT_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "blind_review": True,
        "package_commitment": review["package_commitment"],
        "bindings": {
            **deepcopy(seed["bindings"]),
            "review_seed_sha256": context["seed_snapshot"]["sha256"],
            "review_export_sha256": context["review_snapshot"]["sha256"],
            "answer_key_sha256": answer_snapshot["sha256"],
            "answer_key_document_sha256": answer["document_sha256"],
        },
        "reviewed_unit_count": len(resolved_units),
        "counts_by_kind_and_outcome": summary,
        "overall_outcome_counts": overall,
        "units": resolved_units,
        "readiness_evidence": {
            "human_join_remediation_review_complete": True,
            "all_targeted_join_pairs_candidate_preferred": (
                boundary["candidate_preferred"]
                == review["expected_counts"]["boundary_role_pairs"]
            ),
            "all_patch_edges_candidate_or_equivalent": (
                edges["candidate_preferred"] + edges["equivalent"]
                == review["expected_counts"]["patch_edge_pairs"]
            ),
            "all_complete_songs_candidate_or_equivalent": (
                songs["candidate_preferred"] + songs["equivalent"]
                == review["expected_counts"]["complete_song_pairs"]
            ),
            "readiness_reassessment_eligible": True,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "choices_are_human_listening_evidence": True,
            "candidate_preference_is_join_elimination": False,
            "candidate_preference_is_separator_accuracy": False,
            "review_completion_is_quality_acceptance": False,
            "answer_key_opened_only_after_complete_review_verified": True,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "verification_claims": {
            **_PUBLIC_VERIFICATION_CLAIMS,
            "answer_key_bounded_single_read_snapshot_verified": True,
            "answer_key_slot_identities_and_levels_verified": True,
            "result_temp_fsynced_before_no_overwrite_publication": True,
            "result_published_by_no_overwrite_hard_link": True,
        },
        "verification_limitations": dict(_SNAPSHOT_SCOPE_LIMITATIONS),
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_RESULT_EFFECTS),
    }
    result["document_sha256"] = _document_sha256(result)
    _write_json_exclusive(output, result)
    return {**result, "report": str(output)}


def _load_verified_public_review(
    review_path: str | Path,
    *,
    review_package_dir: str | Path,
    execution_dir: str | Path,
    stitch_package_dir: str | Path,
) -> dict[str, Any]:
    review_package = Path(review_package_dir).expanduser().absolute()
    execution = Path(execution_dir).expanduser().absolute()
    stitch_package = Path(stitch_package_dir).expanduser().absolute()
    _require_private_directory(review_package, "private remediation review package")
    _require_private_directory(execution, "private remediation execution root")
    _require_private_directory(stitch_package, "private stitch package")
    seed_path = review_package / REVIEW_NAME
    seed_snapshot = _load_private_json_snapshot(
        seed_path,
        "private remediation review seed",
    )
    seed = seed_snapshot["document"]
    _verify_seed(seed)

    execution_path = execution / EXECUTION_REPORT_NAME
    _require_private_regular(execution_path, "private remediation execution report")
    state = _load_json(execution_path, "private remediation execution report")
    if (
        state.get("schema") != EXECUTION_SCHEMA
        or state.get("status") != EXECUTION_STATUS
        or state.get("state_sha256") != _state_sha256(state)
        or state.get("permissions") != _FALSE_PERMISSIONS
        or state.get("summary", {}).get("candidate_audio_complete") is not True
        or state.get("summary", {}).get("human_candidate_review_complete") is not False
    ):
        raise ValueError("private remediation execution differs")
    stitch_path = stitch_package / STITCH_REPORT_NAME
    stitch = _load_stitch_report(stitch_path)
    _verify_stitch_audio(stitch_package, stitch)
    candidate = _verify_candidate_report(execution, state, stitch=stitch)
    candidate_path = execution / CANDIDATE_REPORT_NAME
    expected_bindings = {
        "execution_report_sha256": _sha256(execution_path),
        "execution_state_sha256": state["state_sha256"],
        "candidate_report_sha256": _sha256(candidate_path),
        "candidate_document_sha256": candidate["document_sha256"],
        "stitch_report_sha256": _sha256(stitch_path),
        "stitch_document_sha256": stitch["document_sha256"],
    }
    if any(
        seed["bindings"].get(key) != value for key, value in expected_bindings.items()
    ):
        raise ValueError("private remediation review source bindings differ")
    reconstructed = _reconstruct_public_review(
        candidate,
        stitch=stitch,
        review_package=review_package,
        execution=execution,
        stitch_package=stitch_package,
    )
    _verify_reconstructed_public_semantics(seed, reconstructed=reconstructed)

    review_snapshot = _load_private_json_snapshot(
        review_path,
        "reviewed remediation export",
    )
    review_file = review_snapshot["path"]
    review = review_snapshot["document"]
    if not _browser_json_equal(
        _immutable_review_document(review), _immutable_review_document(seed)
    ):
        raise ValueError("private remediation review export changed immutable evidence")
    _validate_completed_review(review)
    audio_reference_count, audio_paths = _verify_audio_references(
        review,
        review_package=review_package,
        execution=execution,
        stitch_package=stitch_package,
    )
    audio_evidence = _verify_blind_audio_contract(
        review,
        reconstructed=reconstructed,
        audio_paths=audio_paths,
    )
    return {
        "review_package": review_package,
        "execution": execution,
        "stitch_package": stitch_package,
        "seed_path": seed_path,
        "seed_snapshot": seed_snapshot,
        "seed": seed,
        "review_path": review_file,
        "review_snapshot": review_snapshot,
        "review": review,
        "state": state,
        "candidate": candidate,
        "stitch": stitch,
        "reconstructed": reconstructed,
        "audio_evidence": audio_evidence,
        "audio_reference_count": audio_reference_count,
    }


def _reconstruct_public_review(
    candidate: Mapping[str, Any],
    *,
    stitch: Mapping[str, Any],
    review_package: Path,
    execution: Path,
    stitch_package: Path,
) -> dict[str, Any]:
    """Rebuild v1 public semantics solely from verified source evidence."""

    total_frames = _integer(stitch.get("clock", {}).get("frames"), "stitch frames")
    if total_frames < TARGET_SAMPLE_RATE:
        raise ValueError("private remediation review source semantics differ")
    raw_paths = {
        role: stitch_package / stitch["artifacts"][role]["path"]
        for role in ("vocals", "instrumental", "reconstruction")
    }
    candidate_paths = {
        role: execution / candidate["artifacts"][role]["path"]
        for role in ("vocals", "instrumental", "reconstruction")
    }
    grouped_patches = _validated_grouped_patches(
        candidate,
        total_frames=total_frames,
        boundary_count=_integer(
            stitch.get("clock", {}).get("boundary_count"),
            "stitch boundary count",
        ),
    )
    units: list[dict[str, Any]] = []
    for boundary_index, role in sorted(grouped_patches):
        if role not in raw_paths:
            raise ValueError("private remediation review source semantics differ")
        patch = grouped_patches[(boundary_index, role)]
        start_frame = _integer(patch.get("start_frame"), "patch start frame")
        end_frame = _integer(patch.get("end_frame"), "patch end frame")
        if boundary_index < 1 or start_frame < 0 or end_frame <= start_frame:
            raise ValueError("private remediation review source semantics differ")
        boundary_frame = (start_frame + end_frame) // 2
        units.append(
            _reconstructed_unit(
                unit_id=f"boundary-{boundary_index:02d}-{role}",
                kind="boundary_role_pair",
                title=f"Boundary {boundary_index}: {role}",
                focus=(
                    "Which version has the less audible join while preserving the "
                    f"musical continuity of the {role}?"
                ),
                role=role,
                centre_frame=boundary_frame,
                half_frames=2 * TARGET_SAMPLE_RATE,
                total_frames=total_frames,
                raw_path=raw_paths[role],
                candidate_path=candidate_paths[role],
            )
        )
        for edge_name, edge_frame in (
            ("start", start_frame),
            ("end", end_frame),
        ):
            units.append(
                _reconstructed_unit(
                    unit_id=f"edge-{boundary_index:02d}-{role}-{edge_name}",
                    kind="patch_edge_pair",
                    title=f"Boundary {boundary_index}: {role} patch {edge_name} edge",
                    focus=(
                        "Which version has the cleaner transition at this patch edge? "
                        "Listen for a click, level jump, cut-off sound or sudden tone change."
                    ),
                    role=role,
                    centre_frame=edge_frame,
                    half_frames=TARGET_SAMPLE_RATE,
                    total_frames=total_frames,
                    raw_path=raw_paths[role],
                    candidate_path=candidate_paths[role],
                )
            )
    for role in ("vocals", "instrumental", "reconstruction"):
        units.append(
            {
                "public": {
                    "unit_id": f"complete-song-{role}",
                    "kind": "complete_song_pair",
                    "title": f"Complete song: {role}",
                    "focus": (
                        "Hear both complete tracks. Which remains useful overall and avoids new "
                        "clicks, cut-offs, level jumps or sudden tone changes?"
                    ),
                    "source_window": None,
                    "level_policy": "unchanged-full-song-files-no-level-processing",
                },
                "role": role,
                "raw_path": raw_paths[role],
                "candidate_path": candidate_paths[role],
                "complete_records": {
                    "raw": _external_audio_record(raw_paths[role], review_package),
                    "candidate": _external_audio_record(
                        candidate_paths[role], review_package
                    ),
                },
            }
        )
    expected_counts = {
        "boundary_role_pairs": len(grouped_patches),
        "patch_edge_pairs": 2 * len(grouped_patches),
        "complete_song_pairs": 3,
        "total_units": 3 * len(grouped_patches) + 3,
    }
    if len(units) != expected_counts["total_units"]:
        raise ValueError("private remediation review source semantics differ")
    return {"expected_counts": expected_counts, "units": units}


def _reconstructed_unit(
    *,
    unit_id: str,
    kind: str,
    title: str,
    focus: str,
    role: str,
    centre_frame: int,
    half_frames: int,
    total_frames: int,
    raw_path: Path,
    candidate_path: Path,
) -> dict[str, Any]:
    start = max(0, centre_frame - half_frames)
    end = min(total_frames, centre_frame + half_frames)
    if end - start < TARGET_SAMPLE_RATE:
        raise ValueError("private remediation review clip is too short")
    return {
        "public": {
            "unit_id": unit_id,
            "kind": kind,
            "title": title,
            "focus": focus,
            "source_window": {
                "start_frame": start,
                "end_frame": end,
                "start_seconds": start / TARGET_SAMPLE_RATE,
                "end_seconds": end / TARGET_SAMPLE_RATE,
            },
            "level_policy": ("attenuate-louder-to-quieter-whole-window-sample-rms-v1"),
        },
        "role": role,
        "raw_path": raw_path,
        "candidate_path": candidate_path,
    }


def _external_audio_record(path: Path, review_package: Path) -> dict[str, Any]:
    return {
        "path": os.path.relpath(path, review_package),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _verify_reconstructed_public_semantics(
    seed: Mapping[str, Any], *, reconstructed: Mapping[str, Any]
) -> None:
    if (
        set(seed) != _PUBLIC_DOCUMENT_KEYS
        or seed.get("question") != _QUESTION
        or seed.get("instructions")
        != _review_instructions(reconstructed["expected_counts"]["boundary_role_pairs"])
        or seed.get("limitations") != _LIMITATIONS
        or seed.get("expected_counts") != reconstructed["expected_counts"]
    ):
        raise ValueError("private remediation review public semantics differ")
    seed_units = seed["units"]
    expected_units = reconstructed["units"]
    if len(seed_units) != len(expected_units):
        raise ValueError("private remediation review public semantics differ")
    for unit, expected in zip(seed_units, expected_units):
        public = expected["public"]
        if set(unit) != _PUBLIC_UNIT_KEYS or any(
            not _browser_json_equal(unit.get(key), value)
            for key, value in public.items()
        ):
            raise ValueError("private remediation review public semantics differ")
        if unit["kind"] != "complete_song_pair":
            unit_id = unit["unit_id"]
            if any(
                unit["audio"][slot]["path"] != f"{AUDIO_DIRECTORY}/{unit_id}-{slot}.wav"
                for slot in ("A", "B")
            ):
                raise ValueError("private remediation review public semantics differ")


def _verify_seed(seed: Mapping[str, Any]) -> None:
    units = seed.get("units")
    expected = seed.get("expected_counts")
    if (
        seed.get("schema") != REVIEW_SCHEMA
        or seed.get("status") != REVIEW_STATUS
        or seed.get("evidence_scope") != "private_development_only"
        or seed.get("policy_id") != POLICY_ID
        or seed.get("document_sha256") != _document_sha256(seed)
        or seed.get("permissions") != _FALSE_PERMISSIONS
        or seed.get("effects") != _FALSE_EFFECTS
        or not isinstance(seed.get("question"), str)
        or not seed["question"]
        or not isinstance(units, list)
        or not isinstance(expected, Mapping)
        or expected.get("boundary_role_pairs")
        != _kind_count(units, "boundary_role_pair")
        or expected.get("patch_edge_pairs") != _kind_count(units, "patch_edge_pair")
        or expected.get("complete_song_pairs")
        != _kind_count(units, "complete_song_pair")
        or expected.get("total_units") != len(units)
        or seed.get("summary")
        != {"reviewed_units": 0, "total_units": len(units), "complete": False}
    ):
        raise ValueError("private remediation review seed differs")
    identifiers: list[str] = []
    for unit in units:
        _validate_seed_unit(unit)
        identifiers.append(str(unit["unit_id"]))
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("private remediation review unit identities differ")
    bindings = seed.get("bindings")
    if not isinstance(bindings, Mapping):
        raise ValueError("private remediation review bindings differ")
    required_hashes = {
        "execution_report_sha256",
        "execution_state_sha256",
        "candidate_report_sha256",
        "candidate_document_sha256",
        "stitch_report_sha256",
        "stitch_document_sha256",
        "audio_manifest_sha256",
        "answer_key_sha256",
        "answer_key_document_sha256",
    }
    if set(bindings) != required_hashes or any(
        not _is_sha256(bindings[key]) for key in required_hashes
    ):
        raise ValueError("private remediation review bindings differ")
    audio_manifest_sha256 = _audio_manifest_sha256(seed)
    if audio_manifest_sha256 != bindings["audio_manifest_sha256"]:
        raise ValueError("private remediation review audio manifest differs")
    commitment = hashlib.sha256(
        (
            f"{bindings['answer_key_sha256']}:"
            f"{bindings['answer_key_document_sha256']}:"
            f"{audio_manifest_sha256}"
        ).encode("ascii")
    ).hexdigest()
    if seed.get("package_commitment") != commitment:
        raise ValueError("private remediation review package commitment differs")


def _validate_seed_unit(unit: object) -> None:
    if not isinstance(unit, Mapping):
        raise ValueError("private remediation review unit differs")
    kind = unit.get("kind")
    audio = unit.get("audio")
    if (
        not isinstance(unit.get("unit_id"), str)
        or not unit["unit_id"]
        or kind not in _KINDS
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
        raise ValueError("private remediation review unit differs")
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
            raise ValueError("private remediation review audio claim differs")
    if kind == "complete_song_pair":
        if (
            unit.get("source_window") is not None
            or unit.get("level_policy")
            != "unchanged-full-song-files-no-level-processing"
        ):
            raise ValueError("private remediation complete-song unit differs")
    else:
        window = unit.get("source_window")
        if (
            not isinstance(window, Mapping)
            or set(window)
            != {"start_frame", "end_frame", "start_seconds", "end_seconds"}
            or unit.get("level_policy")
            != "attenuate-louder-to-quieter-whole-window-sample-rms-v1"
        ):
            raise ValueError("private remediation short review unit differs")
        start_frame = _integer(window.get("start_frame"), "review start frame")
        end_frame = _integer(window.get("end_frame"), "review end frame")
        start_seconds = _finite_number(
            window.get("start_seconds"), "review start seconds"
        )
        end_seconds = _finite_number(window.get("end_seconds"), "review end seconds")
        if (
            start_frame < 0
            or end_frame <= start_frame
            or start_seconds != start_frame / 44_100
            or end_seconds != end_frame / 44_100
        ):
            raise ValueError("private remediation review window differs")


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
        raise ValueError("private remediation review is incomplete")
    for unit in units:
        heard = unit.get("heard") if isinstance(unit, Mapping) else None
        if (
            not isinstance(heard, Mapping)
            or heard != {"A": True, "B": True}
            or unit.get("choice") not in _PAIR_CHOICES
            or not isinstance(unit.get("notes"), str)
            or len(unit["notes"]) > _MAXIMUM_NOTES_CHARACTERS
        ):
            raise ValueError("private remediation review unit is incomplete")


def _immutable_review_document(document: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(document))
    result["status"] = REVIEW_STATUS
    result["summary"] = {
        "reviewed_units": 0,
        "total_units": len(result.get("units", [])),
        "complete": False,
    }
    units = result.get("units")
    if isinstance(units, list):
        for unit in units:
            if isinstance(unit, dict):
                unit["heard"] = {"A": False, "B": False}
                unit["choice"] = None
                unit["notes"] = ""
    return result


def _browser_json_equal(reviewed: Any, seed: Any) -> bool:
    """Allow only JavaScript's directional integer-valued float rewrite."""

    if isinstance(reviewed, Mapping) or isinstance(seed, Mapping):
        return (
            isinstance(reviewed, Mapping)
            and isinstance(seed, Mapping)
            and set(reviewed) == set(seed)
            and all(_browser_json_equal(reviewed[key], seed[key]) for key in reviewed)
        )
    if isinstance(reviewed, list) or isinstance(seed, list):
        return (
            isinstance(reviewed, list)
            and isinstance(seed, list)
            and len(reviewed) == len(seed)
            and all(
                _browser_json_equal(reviewed_item, seed_item)
                for reviewed_item, seed_item in zip(reviewed, seed)
            )
        )
    if isinstance(reviewed, bool) or isinstance(seed, bool):
        return type(reviewed) is bool and type(seed) is bool and reviewed is seed
    if isinstance(reviewed, (int, float)) or isinstance(seed, (int, float)):
        if not isinstance(reviewed, (int, float)) or not isinstance(seed, (int, float)):
            return False
        if not math.isfinite(float(reviewed)) or not math.isfinite(float(seed)):
            return False
        if type(reviewed) is type(seed):
            return reviewed == seed
        if isinstance(reviewed, int) and isinstance(seed, float):
            return seed.is_integer() and reviewed == int(seed)
        return False
    return type(reviewed) is type(seed) and reviewed == seed


def _verify_audio_references(
    review: Mapping[str, Any],
    *,
    review_package: Path,
    execution: Path,
    stitch_package: Path,
) -> tuple[int, dict[str, dict[str, Path]]]:
    referenced: set[Path] = set()
    paths_by_unit: dict[str, dict[str, Path]] = {}
    short_root = review_package / "audio"
    _require_private_directory(short_root, "private remediation review audio root")
    for unit in review["units"]:
        kind = unit["kind"]
        unit_paths: dict[str, Path] = {}
        allowed_roots = (
            (short_root,)
            if kind != "complete_song_pair"
            else (execution, stitch_package)
        )
        for slot in ("A", "B"):
            record = unit["audio"][slot]
            path = _verify_audio_record(
                review_package,
                record,
                allowed_roots=allowed_roots,
            )
            if path in referenced:
                raise ValueError("private remediation review audio is reused")
            referenced.add(path)
            unit_paths[slot] = path
        paths_by_unit[unit["unit_id"]] = unit_paths
    expected = int(review["expected_counts"]["total_units"]) * 2
    if len(referenced) != expected:
        raise ValueError("private remediation review audio inventory differs")
    return len(referenced), paths_by_unit


def _verify_blind_audio_contract(
    review: Mapping[str, Any],
    *,
    reconstructed: Mapping[str, Any],
    audio_paths: Mapping[str, Mapping[str, Path]],
) -> dict[str, dict[str, Any]]:
    """Verify each unordered A/B pair without consulting the answer key."""

    import numpy as np
    import soundfile

    evidence: dict[str, dict[str, Any]] = {}
    for unit, expected in zip(review["units"], reconstructed["units"]):
        unit_id = unit["unit_id"]
        if unit_id != expected["public"]["unit_id"]:
            raise ValueError("private remediation review audio semantics differ")
        if unit["kind"] == "complete_song_pair":
            actual_records = [unit["audio"][slot] for slot in ("A", "B")]
            expected_records = [
                expected["complete_records"][identity]
                for identity in ("raw", "candidate")
            ]
            if _sorted_records(actual_records) != _sorted_records(expected_records):
                raise ValueError("private remediation complete-song audio differs")
            evidence[unit_id] = {
                "kind": unit["kind"],
                "complete_records": expected["complete_records"],
            }
            continue

        window = expected["public"]["source_window"]
        start = int(window["start_frame"])
        end = int(window["end_frame"])
        raw, raw_rate = soundfile.read(
            expected["raw_path"],
            start=start,
            stop=end,
            dtype="float64",
            always_2d=True,
        )
        candidate, candidate_rate = soundfile.read(
            expected["candidate_path"],
            start=start,
            stop=end,
            dtype="float64",
            always_2d=True,
        )
        if (
            int(raw_rate) != TARGET_SAMPLE_RATE
            or int(candidate_rate) != TARGET_SAMPLE_RATE
            or raw.shape != candidate.shape
            or raw.shape != (end - start, 2)
        ):
            raise ValueError("private remediation review clip geometry differs")
        raw_rms = _sample_rms(raw, np=np)
        candidate_rms = _sample_rms(candidate, np=np)
        target_rms = min(raw_rms, candidate_rms)
        if target_rms <= 10 ** (-60 / 20):
            raise ValueError("private remediation review clip is too quiet")
        raw_gain = target_rms / raw_rms
        candidate_gain = target_rms / candidate_rms
        expected_hashes = {
            "raw": _rendered_pcm24_sha256(raw * raw_gain, soundfile=soundfile, np=np),
            "candidate": _rendered_pcm24_sha256(
                candidate * candidate_gain,
                soundfile=soundfile,
                np=np,
            ),
        }
        if expected_hashes["raw"] == expected_hashes["candidate"]:
            raise ValueError(
                "private remediation short review pair is PCM24-identical and cannot be blind-resolved"
            )
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
            raise ValueError("private remediation short review audio differs")
        evidence[unit_id] = {
            "kind": unit["kind"],
            "expected_hashes": expected_hashes,
            "actual_hashes": actual_hashes,
            "levels": {
                "raw_gain": round(raw_gain, 12),
                "candidate_gain": round(candidate_gain, 12),
                "raw_rms": round(raw_rms, 12),
                "candidate_rms": round(candidate_rms, 12),
            },
        }
    return evidence


def _sorted_records(records: list[Mapping[str, Any]]) -> list[bytes]:
    return sorted(canonical_json_bytes(dict(record)) for record in records)


def _sample_rms(value: Any, *, np: Any) -> float:
    result = float(np.sqrt(np.mean(np.square(value, dtype="float64"))))
    if not math.isfinite(result) or result <= 0:
        raise ValueError("private remediation review RMS differs")
    return result


def _rendered_pcm24_sha256(value: Any, *, soundfile: Any, np: Any) -> str:
    buffer = io.BytesIO()
    soundfile.write(
        buffer,
        value,
        TARGET_SAMPLE_RATE,
        format="WAV",
        subtype="PCM_24",
    )
    buffer.seek(0)
    samples, sample_rate = soundfile.read(buffer, dtype="int32", always_2d=True)
    if int(sample_rate) != TARGET_SAMPLE_RATE or samples.shape != value.shape:
        raise ValueError("private remediation review PCM24 projection differs")
    return _pcm24_sequence_sha256(samples, np=np)


def _audio_pcm24_sha256(
    path: Path,
    *,
    expected_frames: int,
    soundfile: Any,
    np: Any,
) -> str:
    info = soundfile.info(path)
    samples, sample_rate = soundfile.read(path, dtype="int32", always_2d=True)
    if (
        int(sample_rate) != TARGET_SAMPLE_RATE
        or info.subtype != "PCM_24"
        or int(info.channels) != 2
        or int(info.frames) != expected_frames
        or samples.shape != (expected_frames, 2)
    ):
        raise ValueError("private remediation review PCM24 audio differs")
    return _pcm24_sequence_sha256(samples, np=np)


def _pcm24_sequence_sha256(value: Any, *, np: Any) -> str:
    little_endian = np.asarray(value, dtype="<i4")
    return hashlib.sha256(little_endian.tobytes(order="C")).hexdigest()


def _verify_audio_record(
    root: Path,
    record: Mapping[str, Any],
    *,
    allowed_roots: tuple[Path, ...],
) -> Path:
    relative = record["path"]
    unresolved = root / relative
    try:
        details = unresolved.lstat()
        path = unresolved.resolve(strict=True)
    except OSError as error:
        raise ValueError("private remediation review audio changed") from error
    resolved_roots = tuple(item.resolve(strict=True) for item in allowed_roots)
    if (
        not any(
            path == boundary or boundary in path.parents for boundary in resolved_roots
        )
        or stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or details.st_uid != os.geteuid()
        or stat.S_IMODE(details.st_mode) & 0o077
        or details.st_size != record["bytes"]
        or _sha256(path) != record["sha256"]
    ):
        raise ValueError("private remediation review audio changed")
    return path


def _load_verified_answer_key(
    review_package: Path, *, seed: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    answer_path = review_package / ANSWER_KEY_NAME
    snapshot = _load_private_json_snapshot(
        answer_path,
        "private remediation review answer key",
    )
    bindings = seed["bindings"]
    if snapshot["sha256"] != bindings["answer_key_sha256"]:
        raise ValueError("private remediation review answer key changed")
    answer = snapshot["document"]
    relevant_bindings = {
        key: bindings[key]
        for key in (
            "execution_report_sha256",
            "execution_state_sha256",
            "candidate_report_sha256",
            "candidate_document_sha256",
            "stitch_report_sha256",
            "stitch_document_sha256",
            "audio_manifest_sha256",
        )
    }
    if (
        answer.get("schema") != ANSWER_KEY_SCHEMA
        or answer.get("status") != "sealed_do_not_open_before_review"
        or answer.get("document_sha256") != _document_sha256(answer)
        or answer.get("document_sha256") != bindings["answer_key_document_sha256"]
        or answer.get("bindings") != relevant_bindings
        or answer.get("permissions") != _FALSE_PERMISSIONS
        or not _is_nonce(answer.get("nonce"))
    ):
        raise ValueError("private remediation review answer key differs")
    answer_units = answer.get("units")
    seed_units = seed["units"]
    if not isinstance(answer_units, list) or len(answer_units) != len(seed_units):
        raise ValueError("private remediation review answer units differ")
    for seed_unit, answer_unit in zip(seed_units, answer_units):
        _validate_answer_unit(seed_unit, answer_unit)
    return answer, snapshot


def _verify_answer_key_audio_bindings(
    review: Mapping[str, Any],
    answer: Mapping[str, Any],
    *,
    reconstructed: Mapping[str, Any],
    audio_evidence: Mapping[str, Mapping[str, Any]],
) -> None:
    """Bind revealed identities and level facts to already-verified audio."""

    for unit, answer_unit, expected in zip(
        review["units"], answer["units"], reconstructed["units"]
    ):
        unit_id = unit["unit_id"]
        assignment = answer_unit["assignment"]
        evidence = audio_evidence[unit_id]
        if unit["kind"] == "complete_song_pair":
            if any(
                unit["audio"][slot] != expected["complete_records"][assignment[slot]]
                for slot in ("A", "B")
            ):
                raise ValueError(
                    "private remediation complete-song answer binding differs"
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
            raise ValueError("private remediation short answer binding differs")


def _validate_answer_unit(seed_unit: Mapping[str, Any], answer_unit: object) -> None:
    if not isinstance(answer_unit, Mapping):
        raise ValueError("private remediation review answer unit differs")
    assignment = answer_unit.get("assignment")
    if (
        answer_unit.get("unit_id") != seed_unit["unit_id"]
        or not isinstance(assignment, Mapping)
        or set(assignment) != {"A", "B"}
        or set(assignment.values()) != {"raw", "candidate"}
    ):
        raise ValueError("private remediation review answer unit differs")
    if seed_unit["kind"] == "complete_song_pair":
        if set(answer_unit) != {"unit_id", "assignment"}:
            raise ValueError("private remediation complete-song answer differs")
        return
    if set(answer_unit) != {
        "unit_id",
        "assignment",
        "raw_gain",
        "candidate_gain",
        "raw_rms",
        "candidate_rms",
    }:
        raise ValueError("private remediation short answer differs")
    raw_gain = _finite_number(answer_unit.get("raw_gain"), "raw review gain")
    candidate_gain = _finite_number(
        answer_unit.get("candidate_gain"), "candidate review gain"
    )
    raw_rms = _finite_number(answer_unit.get("raw_rms"), "raw review RMS")
    candidate_rms = _finite_number(
        answer_unit.get("candidate_rms"), "candidate review RMS"
    )
    if (
        raw_gain <= 0.0
        or raw_gain > 1.0
        or candidate_gain <= 0.0
        or candidate_gain > 1.0
        or raw_rms <= 0.0
        or candidate_rms <= 0.0
        or max(raw_gain, candidate_gain) != 1.0
    ):
        raise ValueError("private remediation review level evidence differs")


def _audio_manifest_sha256(review: Mapping[str, Any]) -> str:
    manifest = {
        "schema": "sunofriend.private-separation-full-song-join-remediation-audio.v1",
        "units": [
            {"unit_id": unit["unit_id"], "audio": unit["audio"]}
            for unit in review["units"]
        ],
    }
    return hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()


def _counts_by_kind(units: list[Mapping[str, Any]]) -> dict[str, int]:
    return {kind: _kind_count(units, kind) for kind in _KINDS}


def _kind_count(units: list[Any], kind: str) -> int:
    return sum(isinstance(unit, Mapping) and unit.get("kind") == kind for unit in units)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} differs") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} differs")
    return value


def _load_private_json_snapshot(value: str | Path, label: str) -> dict[str, Any]:
    """Read one bounded owner-only JSON snapshot from one non-followed fd."""

    path = Path(value).expanduser().absolute()
    if path.suffix.lower() != ".json":
        raise _PrivateJsonSnapshotError(
            f"{label} must be a JSON file",
            path=path,
        )
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise _PrivateJsonSnapshotError(
            f"{label} cannot be opened without symbolic-link protection",
            path=path,
        )
    flags = os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise _PrivateJsonSnapshotError(
            f"{label} must be a regular non-link file",
            path=path,
        ) from error
    try:
        os.set_inheritable(descriptor, False)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or before.st_size > _MAXIMUM_REVIEW_EXPORT_BYTES
        ):
            raise _PrivateJsonSnapshotError(
                f"{label} must be a non-empty regular JSON file no larger than 8 MiB",
                path=path,
            )
        if before.st_uid != os.geteuid():
            raise _PrivateJsonSnapshotError(
                f"{label} must be owned by the current user",
                path=path,
            )
        if before.st_nlink != 1:
            raise _PrivateJsonSnapshotError(
                f"{label} must have exactly one filesystem link",
                path=path,
            )
        if stat.S_IMODE(before.st_mode) & 0o077:
            raise _PrivateJsonSnapshotError(
                f"{label} must not be readable, writable or executable by group or other users",
                path=path,
                chmod_recommended=True,
            )
        contents = os.read(descriptor, _MAXIMUM_REVIEW_EXPORT_BYTES + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        _snapshot_stat_identity(before) != _snapshot_stat_identity(after)
        or len(contents) != before.st_size
    ):
        raise _PrivateJsonSnapshotError(
            f"{label} changed while it was being read",
            path=path,
        )
    try:
        document = json.loads(contents.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _PrivateJsonSnapshotError(f"{label} differs", path=path) from error
    if not isinstance(document, dict):
        raise _PrivateJsonSnapshotError(f"{label} differs", path=path)
    return {
        "path": path,
        "document": document,
        "sha256": hashlib.sha256(contents).hexdigest(),
        "bytes": len(contents),
    }


def _snapshot_stat_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _write_json_exclusive(path: Path, document: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(
            document,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    created = os.fstat(descriptor)
    try:
        os.set_inheritable(descriptor, False)
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise RuntimeError("private remediation result write made no progress")
            offset += written
        os.fsync(descriptor)
        _require_same_inode(temp_path, created, "private remediation result temp")

        directory_descriptor = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            os.set_inheritable(directory_descriptor, False)
            # Linking a complete same-filesystem temp is the publication point.
            # link(2) fails with EEXIST and can never replace a raced result.
            os.link(temp_path, path, follow_symlinks=False)
            _require_same_inode(path, created, "published remediation result")
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        try:
            os.close(descriptor)
        finally:
            _unlink_same_inode_best_effort(temp_path, created)


def _require_same_inode(path: Path, expected: os.stat_result, label: str) -> None:
    visible = path.lstat()
    if (visible.st_dev, visible.st_ino) != (expected.st_dev, expected.st_ino):
        raise RuntimeError(f"{label} identity changed")


def _unlink_same_inode_best_effort(path: Path, expected: os.stat_result) -> None:
    """Remove only this call's hidden temp, never a raced replacement path."""

    try:
        visible = path.lstat()
        if (visible.st_dev, visible.st_ino) == (expected.st_dev, expected.st_ino):
            path.unlink()
    except OSError:
        pass


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} differs")
    return value


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} differs")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} differs")
    return result


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


def _is_nonce(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        return len(bytes.fromhex(value)) == 32
    except ValueError:
        return False


__all__: tuple[str, ...] = ()
