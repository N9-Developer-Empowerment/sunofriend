"""Verify and resolve one blind follow-up separator review.

Status validation never opens the sealed answer key.  Resolution repeats all
public checks, opens the key only after the completed browser export verifies,
and records identity-resolved listening evidence without selecting or
accepting either separator candidate.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
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
    _sorted_records,
    _verify_audio_record,
    _write_json_exclusive,
)
from ._separation_candidate_join_remediation_review import (
    ANSWER_KEY_NAME,
    POLICY,
    REPORT_NAME as REVIEW_NAME,
    SCHEMA as REVIEW_SCHEMA,
    STATUS as REVIEW_STATUS,
    TARGET_SAMPLE_RATE,
    _FALSE_EFFECTS,
    _input_bindings,
    _load_verified_inputs,
    _validated_patches,
)


STATUS_SCHEMA = "sunofriend.private-separation-candidate-join-remediation-review-status.v1"
RESULT_SCHEMA = "sunofriend.private-separation-candidate-join-remediation-review-result.v1"
RESULT_STATUS = "complete_review_no_activation"
ANSWER_KEY_SCHEMA = (
    "sunofriend.private-separation-candidate-join-remediation-answer-key.v1"
)
_KINDS = ("boundary_role_pair", "patch_edge_pair", "complete_song_pair")
_IDENTITIES = ("v2_control", "followup_candidate")
_OUTCOMES = (
    "v2_control_preferred",
    "followup_candidate_preferred",
    "equivalent",
    "neither",
    "cannot_tell",
)
_MAXIMUM_NOTES_CHARACTERS = 1_000
_QUESTION = (
    "Did the review-derived follow-up reduce the ten audible v2 joins "
    "without creating worse patch edges or complete-song problems?"
)
_INSTRUCTIONS = [
    "Review A and B by listening; neither letter is a recommendation.",
    "Complete all ten boundary comparisons before judging patch edges.",
    "Then hear all three complete-song pairs for broader side effects.",
    "Equivalent, neither and cannot tell are valid outcomes.",
    "Do not open the separate answer key before exporting the review.",
]
_LIMITATIONS = [
    "The v2 candidate is an immutable control; the follow-up remains unselected.",
    "Short-loop sample-RMS matching attenuates only the louder clip and is not LUFS matching.",
    "Complete-song A/B files are unchanged external controls and candidates.",
    "A listening preference does not select, accept or publish a separator.",
]
_READINESS_SEED = {
    "targeted_followup_review_complete": False,
    "followup_complete_song_review_complete": False,
    "followup_alignment_complete": False,
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
    "instructions",
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
    "public_semantics_reconstructed_from_verified_candidates": True,
    "short_pcm24_pairs_verified_key_blind": True,
    "complete_song_records_verified_key_blind": True,
    "adaptive_audible_edge_window_verified": True,
    "identical_short_pcm24_pairs_rejected": True,
}


def _status_private_candidate_join_remediation_review(
    review_path: str | Path,
    *,
    review_package_dir: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
) -> dict[str, Any]:
    """Verify one completed export without opening its answer key."""

    context = _load_verified_public_review(
        review_path,
        review_package_dir=review_package_dir,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
    )
    review = context["review"]
    status: dict[str, Any] = {
        "schema": STATUS_SCHEMA,
        "status": "complete_review_verified_key_unopened",
        "evidence_scope": "private_development_only",
        "policy_id": POLICY,
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
            **_VERIFICATION_CLAIMS,
            "answer_key_verified": False,
            "result_published_exclusively": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
    }
    status["document_sha256"] = _document_sha256(status)
    return status


def _resolve_private_candidate_join_remediation_review(
    review_path: str | Path,
    *,
    review_package_dir: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Resolve verified identities without activating either candidate."""

    output = Path(out).expanduser().absolute()
    if not os.path.lexists(output.parent):
        output.parent.mkdir(parents=True, mode=0o700)
    _require_private_directory(output.parent, "private follow-up review result directory")
    context = _load_verified_public_review(
        review_path,
        review_package_dir=review_package_dir,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
    )
    review = context["review"]
    answer, answer_snapshot = _load_verified_answer_key(
        context["review_package"],
        seed=context["seed"],
        inputs=context["inputs"],
    )
    _verify_answer_bindings(
        review,
        answer,
        reconstructed=context["reconstructed"],
        audio_evidence=context["audio_evidence"],
    )

    counts = {kind: {outcome: 0 for outcome in _OUTCOMES} for kind in _KINDS}
    overall = {outcome: 0 for outcome in _OUTCOMES}
    resolved_units: list[dict[str, Any]] = []
    for unit, answer_unit in zip(review["units"], answer["units"]):
        choice = str(unit["choice"])
        assignment = answer_unit["assignment"]
        resolved = f"{assignment[choice]}_preferred" if choice in ("A", "B") else choice
        counts[unit["kind"]][resolved] += 1
        overall[resolved] += 1
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
                "resolved_choice": resolved,
                "notes": unit["notes"],
            }
        )

    expected = review["expected_counts"]
    boundary_pass = (
        counts["boundary_role_pair"]["followup_candidate_preferred"]
        == expected["boundary_role_pairs"]
    )
    edge_pass = (
        counts["patch_edge_pair"]["followup_candidate_preferred"]
        + counts["patch_edge_pair"]["equivalent"]
        == expected["patch_edge_pairs"]
    )
    song_pass = (
        counts["complete_song_pair"]["followup_candidate_preferred"]
        + counts["complete_song_pair"]["equivalent"]
        == expected["complete_song_pairs"]
    )
    targeted_pass = boundary_pass and edge_pass and song_pass
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "status": RESULT_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY,
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
        "counts_by_kind_and_outcome": counts,
        "overall_outcome_counts": overall,
        "units": resolved_units,
        "readiness_evidence": {
            "targeted_followup_review_complete": True,
            "all_targeted_boundaries_followup_preferred": boundary_pass,
            "all_patch_edges_followup_or_equivalent": edge_pass,
            "all_complete_songs_followup_or_equivalent": song_pass,
            "targeted_followup_listening_pass": targeted_pass,
            "fresh_all_boundaries_review_eligible": targeted_pass,
            "fresh_alignment_eligible": targeted_pass,
            "followup_complete_song_review_complete": False,
            "followup_alignment_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "choices_are_human_listening_evidence": True,
            "comparative_preference_is_join_elimination": False,
            "comparative_preference_is_separator_accuracy": False,
            "targeted_pass_is_full_song_acceptance": False,
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
    }
    result["document_sha256"] = _document_sha256(result)
    _write_json_exclusive(output, result)
    return {**result, "report": str(output)}


def _load_verified_public_review(
    review_path: str | Path,
    *,
    review_package_dir: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
) -> dict[str, Any]:
    review_package = Path(review_package_dir).expanduser().absolute()
    execution = Path(execution_dir).expanduser().absolute()
    v2_execution = Path(v2_execution_dir).expanduser().absolute()
    _require_private_directory(review_package, "private follow-up review package")
    inputs = _load_verified_inputs(execution, v2_execution)
    reconstructed = _reconstruct_public_review(inputs, review_package=review_package)
    seed_snapshot = _load_private_json_snapshot(
        review_package / REVIEW_NAME, "private follow-up review seed"
    )
    seed = seed_snapshot["document"]
    _verify_seed(seed, inputs=inputs, reconstructed=reconstructed)
    _verify_review_page(review_package / HTML_NAME, seed=seed)

    review_snapshot = _load_private_json_snapshot(
        review_path, "reviewed follow-up remediation export"
    )
    review = review_snapshot["document"]
    if not _browser_json_equal(
        _immutable_review_document(review), _immutable_review_document(seed)
    ):
        raise ValueError("private follow-up review export changed immutable evidence")
    _validate_completed_review(review)
    audio_reference_count, audio_paths = _verify_audio_references(
        review,
        review_package=review_package,
        execution=execution,
        v2_execution=v2_execution,
    )
    audio_evidence = _verify_blind_audio_contract(
        review, reconstructed=reconstructed, audio_paths=audio_paths
    )
    return {
        "review_package": review_package,
        "inputs": inputs,
        "seed_snapshot": seed_snapshot,
        "seed": seed,
        "review_snapshot": review_snapshot,
        "review": review,
        "reconstructed": reconstructed,
        "audio_evidence": audio_evidence,
        "audio_reference_count": audio_reference_count,
    }


def _reconstruct_public_review(
    inputs: Mapping[str, Any], *, review_package: Path
) -> dict[str, Any]:
    total_frames = int(inputs["execution"]["clock"]["frames"])
    patches = _validated_patches(
        inputs["candidate"],
        total_frames=total_frames,
        boundary_count=int(inputs["execution"]["clock"]["boundary_count"]),
    )
    units: list[dict[str, Any]] = []
    for boundary_index, role in sorted(patches):
        patch = patches[(boundary_index, role)]
        centre = (int(patch["patch_start_frame"]) + int(patch["patch_end_frame"])) // 2
        units.append(
            _reconstructed_short_unit(
                unit_id=f"boundary-{boundary_index:02d}-{role}",
                kind="boundary_role_pair",
                title=f"Boundary {boundary_index}: {role}",
                focus=(
                    "Which version has the less audible join while preserving the "
                    f"musical continuity of the {role}?"
                ),
                role=role,
                centre_frame=centre,
                half_frame_options=(2 * TARGET_SAMPLE_RATE,),
                total_frames=total_frames,
                inputs=inputs,
            )
        )
        for edge_name, centre in (
            ("start", int(patch["patch_start_frame"])),
            ("end", int(patch["patch_end_frame"])),
        ):
            units.append(
                _reconstructed_short_unit(
                    unit_id=f"edge-{boundary_index:02d}-{role}-{edge_name}",
                    kind="patch_edge_pair",
                    title=f"Boundary {boundary_index}: {role} patch {edge_name} edge",
                    focus=(
                        "Which version has the cleaner transition at this patch edge? "
                        "Listen for a click, level jump, cut-off sound or sudden tone change."
                    ),
                    role=role,
                    centre_frame=centre,
                    half_frame_options=tuple(
                        seconds * TARGET_SAMPLE_RATE for seconds in (1, 2, 3, 4)
                    ),
                    total_frames=total_frames,
                    inputs=inputs,
                )
            )
    for role in ("vocals", "instrumental", "reconstruction"):
        records = {
            "v2_control": _external_record(inputs["v2_paths"][role], review_package),
            "followup_candidate": _external_record(
                inputs["candidate_paths"][role], review_package
            ),
        }
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
                "complete_records": records,
            }
        )
    expected_counts = {
        "boundary_role_pairs": len(patches),
        "patch_edge_pairs": 2 * len(patches),
        "complete_song_pairs": 3,
        "total_units": 3 * len(patches) + 3,
    }
    if len(units) != expected_counts["total_units"]:
        raise ValueError("private follow-up review source semantics differ")
    return {"expected_counts": expected_counts, "units": units}


def _reconstructed_short_unit(
    *,
    unit_id: str,
    kind: str,
    title: str,
    focus: str,
    role: str,
    centre_frame: int,
    half_frame_options: tuple[int, ...],
    total_frames: int,
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    import numpy as np
    import soundfile

    control_path = inputs["v2_paths"][role]
    followup_path = inputs["candidate_paths"][role]
    selected: tuple[int, int] | None = None
    for half_frames in half_frame_options:
        start = max(0, centre_frame - half_frames)
        end = min(total_frames, centre_frame + half_frames)
        if end - start < TARGET_SAMPLE_RATE:
            continue
        control, control_rate = soundfile.read(
            control_path, start=start, stop=end, dtype="float64", always_2d=True
        )
        followup, followup_rate = soundfile.read(
            followup_path, start=start, stop=end, dtype="float64", always_2d=True
        )
        if (
            int(control_rate) != TARGET_SAMPLE_RATE
            or int(followup_rate) != TARGET_SAMPLE_RATE
            or control.shape != followup.shape
            or control.shape != (end - start, 2)
        ):
            raise ValueError("private follow-up review clip geometry differs")
        if min(_sample_rms(control, np=np), _sample_rms(followup, np=np)) > 10 ** (-60 / 20):
            selected = (start, end)
            break
    if selected is None:
        raise ValueError("private follow-up review clip is too quiet")
    start, end = selected
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
            "level_policy": "attenuate-louder-to-quieter-whole-window-sample-rms-v1",
        },
        "role": role,
        "v2_control_path": control_path,
        "followup_candidate_path": followup_path,
    }


def _external_record(path: Path, review_package: Path) -> dict[str, Any]:
    return {
        "path": os.path.relpath(path, review_package),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _verify_seed(
    seed: Mapping[str, Any], *, inputs: Mapping[str, Any], reconstructed: Mapping[str, Any]
) -> None:
    units = seed.get("units")
    bindings = seed.get("bindings")
    expected_bindings = _input_bindings(inputs)
    if (
        set(seed) != _PUBLIC_KEYS
        or seed.get("schema") != REVIEW_SCHEMA
        or seed.get("status") != REVIEW_STATUS
        or seed.get("evidence_scope") != "private_development_only"
        or seed.get("policy_id") != POLICY
        or seed.get("question") != _QUESTION
        or seed.get("instructions") != _INSTRUCTIONS
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
        or set(bindings) != set(expected_bindings) | {
            "audio_manifest_sha256",
            "answer_key_sha256",
            "answer_key_document_sha256",
        }
        or any(not _is_sha256(bindings[key]) for key in bindings)
    ):
        raise ValueError("private follow-up review seed differs")
    if _audio_manifest_sha256(seed) != bindings["audio_manifest_sha256"]:
        raise ValueError("private follow-up review audio manifest differs")
    commitment = hashlib.sha256(
        (
            f"{bindings['answer_key_sha256']}:"
            f"{bindings['answer_key_document_sha256']}:"
            f"{bindings['audio_manifest_sha256']}"
        ).encode("ascii")
    ).hexdigest()
    if seed.get("package_commitment") != commitment:
        raise ValueError("private follow-up review commitment differs")
    identifiers: set[str] = set()
    for unit, expected in zip(units, reconstructed["units"]):
        _validate_seed_unit(unit)
        if unit["unit_id"] in identifiers:
            raise ValueError("private follow-up review unit identities differ")
        identifiers.add(unit["unit_id"])
        if any(
            not _browser_json_equal(unit.get(key), value)
            for key, value in expected["public"].items()
        ):
            raise ValueError("private follow-up review source semantics differ")
        if unit["kind"] != "complete_song_pair" and any(
            unit["audio"][slot]["path"]
            != f"{AUDIO_DIRECTORY}/{unit['unit_id']}-{slot}.wav"
            for slot in ("A", "B")
        ):
            raise ValueError("private follow-up review short audio path differs")


def _validate_seed_unit(unit: object) -> None:
    if not isinstance(unit, Mapping) or set(unit) != _PUBLIC_UNIT_KEYS:
        raise ValueError("private follow-up review unit differs")
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
        raise ValueError("private follow-up review unit differs")
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
            raise ValueError("private follow-up review audio claim differs")


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
        raise ValueError("private follow-up review is incomplete")
    for unit in units:
        if (
            not isinstance(unit, Mapping)
            or unit.get("heard") != {"A": True, "B": True}
            or unit.get("choice") not in _PAIR_CHOICES
            or not isinstance(unit.get("notes"), str)
            or len(unit["notes"]) > _MAXIMUM_NOTES_CHARACTERS
        ):
            raise ValueError("private follow-up review unit is incomplete")


def _verify_review_page(path: Path, *, seed: Mapping[str, Any]) -> None:
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("private follow-up review page differs")
    try:
        page = path.read_text(encoding="utf-8")
        embedded = page.split('<script id="seed" type="application/json">', 1)[1].split(
            "</script><script>", 1
        )[0]
    except (OSError, UnicodeDecodeError, IndexError) as error:
        raise ValueError("private follow-up review page differs") from error
    if (
        json.loads(embedded) != seed
        or "Export reviewed JSON" not in page
        or "Mark review complete" not in page
        or '"assignment"' in page
        or ANSWER_KEY_NAME in page
    ):
        raise ValueError("private follow-up review page differs")


def _verify_audio_references(
    review: Mapping[str, Any],
    *,
    review_package: Path,
    execution: Path,
    v2_execution: Path,
) -> tuple[int, dict[str, dict[str, Path]]]:
    referenced: set[Path] = set()
    paths_by_unit: dict[str, dict[str, Path]] = {}
    short_root = review_package / AUDIO_DIRECTORY
    _require_private_directory(short_root, "private follow-up review audio root")
    for unit in review["units"]:
        allowed_roots = (
            (short_root,)
            if unit["kind"] != "complete_song_pair"
            else (execution, v2_execution)
        )
        unit_paths: dict[str, Path] = {}
        for slot in ("A", "B"):
            path = _verify_audio_record(
                review_package, unit["audio"][slot], allowed_roots=allowed_roots
            )
            if path in referenced:
                raise ValueError("private follow-up review audio is reused")
            referenced.add(path)
            unit_paths[slot] = path
        paths_by_unit[unit["unit_id"]] = unit_paths
    expected = int(review["expected_counts"]["total_units"]) * 2
    if len(referenced) != expected:
        raise ValueError("private follow-up review audio inventory differs")
    return len(referenced), paths_by_unit


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
            raise ValueError("private follow-up review audio semantics differ")
        if unit["kind"] == "complete_song_pair":
            actual = [unit["audio"][slot] for slot in ("A", "B")]
            wanted = [expected["complete_records"][identity] for identity in _IDENTITIES]
            if _sorted_records(actual) != _sorted_records(wanted):
                raise ValueError("private follow-up complete-song audio differs")
            evidence[unit_id] = {
                "kind": unit["kind"],
                "complete_records": expected["complete_records"],
            }
            continue
        window = expected["public"]["source_window"]
        start = int(window["start_frame"])
        end = int(window["end_frame"])
        values: dict[str, Any] = {}
        rms: dict[str, float] = {}
        for identity, path_key in (
            ("v2_control", "v2_control_path"),
            ("followup_candidate", "followup_candidate_path"),
        ):
            values[identity], rate = soundfile.read(
                expected[path_key], start=start, stop=end, dtype="float64", always_2d=True
            )
            if int(rate) != TARGET_SAMPLE_RATE or values[identity].shape != (end - start, 2):
                raise ValueError("private follow-up review clip geometry differs")
            rms[identity] = _sample_rms(values[identity], np=np)
        target = min(rms.values())
        if target <= 10 ** (-60 / 20):
            raise ValueError("private follow-up review clip is too quiet")
        gains = {identity: target / rms[identity] for identity in _IDENTITIES}
        expected_hashes = {
            identity: _rendered_pcm24_sha256(
                values[identity] * gains[identity], soundfile=soundfile, np=np
            )
            for identity in _IDENTITIES
        }
        if len(set(expected_hashes.values())) != 2:
            raise ValueError("private follow-up short review pair is PCM24-identical")
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
            raise ValueError("private follow-up short review audio differs")
        evidence[unit_id] = {
            "kind": unit["kind"],
            "expected_hashes": expected_hashes,
            "actual_hashes": actual_hashes,
            "levels": {
                "raw_gain": round(gains["v2_control"], 12),
                "candidate_gain": round(gains["followup_candidate"], 12),
                "raw_rms": round(rms["v2_control"], 12),
                "candidate_rms": round(rms["followup_candidate"], 12),
            },
        }
    return evidence


def _load_verified_answer_key(
    review_package: Path,
    *,
    seed: Mapping[str, Any],
    inputs: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = _load_private_json_snapshot(
        review_package / ANSWER_KEY_NAME, "private follow-up review answer key"
    )
    bindings = seed["bindings"]
    expected_bindings = {
        **_input_bindings(inputs),
        "audio_manifest_sha256": bindings["audio_manifest_sha256"],
    }
    answer = snapshot["document"]
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
        raise ValueError("private follow-up review answer key differs")
    for seed_unit, answer_unit in zip(seed["units"], answer["units"]):
        _validate_answer_unit(seed_unit, answer_unit)
    return answer, snapshot


def _validate_answer_unit(seed_unit: Mapping[str, Any], answer_unit: object) -> None:
    if not isinstance(answer_unit, Mapping):
        raise ValueError("private follow-up review answer unit differs")
    assignment = answer_unit.get("assignment")
    if (
        answer_unit.get("unit_id") != seed_unit["unit_id"]
        or not isinstance(assignment, Mapping)
        or set(assignment) != {"A", "B"}
        or set(assignment.values()) != set(_IDENTITIES)
    ):
        raise ValueError("private follow-up review answer unit differs")
    if seed_unit["kind"] == "complete_song_pair":
        if set(answer_unit) != {"unit_id", "assignment"}:
            raise ValueError("private follow-up complete-song answer differs")
        return
    if set(answer_unit) != {
        "unit_id",
        "assignment",
        "raw_gain",
        "candidate_gain",
        "raw_rms",
        "candidate_rms",
    }:
        raise ValueError("private follow-up short answer differs")
    raw_gain = _finite_number(answer_unit.get("raw_gain"), "v2 control gain")
    candidate_gain = _finite_number(answer_unit.get("candidate_gain"), "follow-up gain")
    raw_rms = _finite_number(answer_unit.get("raw_rms"), "v2 control RMS")
    candidate_rms = _finite_number(answer_unit.get("candidate_rms"), "follow-up RMS")
    if (
        not 0 < raw_gain <= 1
        or not 0 < candidate_gain <= 1
        or raw_rms <= 0
        or candidate_rms <= 0
        or max(raw_gain, candidate_gain) != 1
    ):
        raise ValueError("private follow-up review level evidence differs")


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
            if any(
                unit["audio"][slot] != expected["complete_records"][assignment[slot]]
                for slot in ("A", "B")
            ):
                raise ValueError("private follow-up complete-song answer binding differs")
            continue
        if any(
            evidence["actual_hashes"][slot]
            != evidence["expected_hashes"][assignment[slot]]
            for slot in ("A", "B")
        ) or any(
            not _browser_json_equal(answer_unit.get(key), value)
            for key, value in evidence["levels"].items()
        ):
            raise ValueError("private follow-up short answer binding differs")


def _audio_manifest_sha256(review: Mapping[str, Any]) -> str:
    manifest = {
        "schema": "sunofriend.private-separation-candidate-join-remediation-review-audio.v1",
        "units": [
            {"unit_id": unit["unit_id"], "audio": unit["audio"]}
            for unit in review["units"]
        ],
    }
    return hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()


def _counts_by_kind(units: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        kind: sum(unit.get("kind") == kind for unit in units) for kind in _KINDS
    }


__all__: tuple[str, ...] = ()
