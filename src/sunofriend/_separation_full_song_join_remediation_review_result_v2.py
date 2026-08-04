"""Verify and resolve the targeted v2 join-remediation listening review.

The status path reconstructs the public six-unit review from the exact v1/v2
evidence while deliberately leaving the sealed answer key unopened.  The
resolver repeats that verification before opening the key and records absolute
cleanliness separately from comparative preference.  Neither path selects or
accepts a separator, closes a readiness gate, or enables publication.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_executor import _FALSE_PERMISSIONS
from ._separation_full_song_join_remediation_executor_v2 import (
    _read_pcm24_snapshot,
)
from ._separation_full_song_join_remediation_plan_v2 import (
    TARGET_SAMPLE_RATE,
    _private_child_regular,
)
from ._separation_full_song_join_remediation_review_result import (
    _browser_json_equal,
    _is_nonce,
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_join_remediation_review_v2 import (
    ANSWER_KEY_NAME,
    AUDIO_DIRECTORY,
    HTML_NAME,
    POLICY_ID,
    REPORT_NAME as REVIEW_NAME,
    SCHEMA as REVIEW_SCHEMA,
    STATUS as REVIEW_STATUS,
    _ABSOLUTE_CHOICES,
    _BOUNDARY_KIND,
    _COMPARATIVE_CHOICES,
    _EDGE_HALF_FRAMES,
    _EDGE_KIND,
    _FALSE_EFFECTS,
    _PAIR_HALF_FRAMES,
    _load_review_inputs,
    _sample_rms,
    _source_bindings,
)


STATUS_SCHEMA = (
    "sunofriend.private-separation-full-song-join-remediation-review-status.v2"
)
RESULT_SCHEMA = (
    "sunofriend.private-separation-full-song-join-remediation-review-result.v2"
)
RESULT_STATUS = "complete_review_no_activation"
ANSWER_KEY_SCHEMA = (
    "sunofriend.private-separation-full-song-join-remediation-answer-key.v2"
)
_MAXIMUM_NOTES_CHARACTERS = 1_000
_QUESTION = (
    "Does the expanded-context candidate produce clean target joins "
    "and clean patch edges compared with the preserved candidate?"
)
_INSTRUCTIONS = [
    "For each anonymous boundary comparison, hear A and B before deciding.",
    "Rate A and B independently as clean, audible join or cannot tell.",
    "Then record which is preferable; equivalent, neither and cannot tell are valid.",
    "Finally hear each expanded-candidate patch edge and rate its absolute cleanliness.",
    "This review does not select, accept or publish either candidate.",
    "Do not open the separate answer key before exporting the completed review.",
]
_LIMITATIONS = [
    "Boundary-pair sample-RMS matching only attenuates the louder clip and is not LUFS matching.",
    "Single patch-edge clips preserve the exact v2 PCM24 samples and receive no level processing.",
    "This targeted package contains no complete-song review and no alignment evidence.",
    "Absolute cleanliness and comparative preference are separate human judgements.",
    "A completed review cannot select, accept or publish a separator.",
]
_EXPECTED_COUNTS = {
    "boundary_comparison_units": 2,
    "v2_patch_edge_units": 4,
    "total_units": 6,
    "anonymous_boundary_audio_clips": 4,
    "v2_edge_audio_clips": 4,
    "total_audio_references": 8,
}
_READINESS_SEED = {
    "targeted_v2_review_complete": False,
    "new_candidate_full_song_review_complete": False,
    "new_candidate_alignment_complete": False,
    "original_audible_joins_resolved": False,
    "publication_ready": False,
}
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
    "readiness",
    "permissions",
    "effects",
    "limitations",
    "document_sha256",
}
_BOUNDARY_UNIT_KEYS = {
    "unit_id",
    "kind",
    "title",
    "focus",
    "source_window",
    "level_policy",
    "audio",
    "heard",
    "absolute_cleanliness",
    "comparative_choice",
    "notes",
}
_EDGE_UNIT_KEYS = _BOUNDARY_UNIT_KEYS - {"comparative_choice"}
_AUDIO_RECORD_KEYS = {
    "path",
    "sha256",
    "bytes",
    "geometry",
    "pcm24_int32_sequence_sha256",
}
_GEOMETRY = {
    "sample_rate": TARGET_SAMPLE_RATE,
    "channels": 2,
    "sample_width_bytes": 3,
}
_PUBLIC_VERIFICATION_CLAIMS = {
    "review_seed_and_export_bounded_single_read_snapshots": True,
    "review_seed_and_export_no_symlink_follow": True,
    "review_seed_and_export_identity_stable_before_after": True,
    "review_seed_and_export_owner_only_single_link": True,
    "public_semantics_reconstructed_from_verified_sources": True,
    "boundary_pcm24_pairs_verified_key_blind": True,
    "v2_patch_edge_pcm24_verified_key_blind": True,
    "identical_boundary_pcm24_pairs_rejected": True,
}
_SNAPSHOT_SCOPE_LIMITATIONS = {
    "v1_v2_execution_and_stitch_json_snapshot_held": False,
    "wav_descriptors_snapshot_held_across_verification": False,
    "non_snapshot_private_inputs_assumed_quiescent": True,
}


def _status_private_join_remediation_review_v2(
    review_path: str | Path,
    *,
    review_package_dir: str | Path,
    v2_execution_dir: str | Path,
    v2_plan_path: str | Path,
    v1_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    full_song_review_result_path: str | Path,
    v1_plan_path: str | Path,
    resolved_join_review_result_path: str | Path,
    publication_readiness_path: str | Path,
) -> dict[str, Any]:
    """Verify a complete v2 export without opening or revealing the key."""

    context = _load_verified_public_review_v2(
        review_path,
        review_package_dir=review_package_dir,
        v2_execution_dir=v2_execution_dir,
        v2_plan_path=v2_plan_path,
        v1_execution_dir=v1_execution_dir,
        stitch_package_dir=stitch_package_dir,
        full_song_review_result_path=full_song_review_result_path,
        v1_plan_path=v1_plan_path,
        resolved_join_review_result_path=resolved_join_review_result_path,
        publication_readiness_path=publication_readiness_path,
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
        "effects": dict(_FALSE_EFFECTS),
    }
    status["document_sha256"] = _document_sha256(status)
    return status


def _resolve_private_join_remediation_review_v2(
    review_path: str | Path,
    *,
    review_package_dir: str | Path,
    v2_execution_dir: str | Path,
    v2_plan_path: str | Path,
    v1_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    full_song_review_result_path: str | Path,
    v1_plan_path: str | Path,
    resolved_join_review_result_path: str | Path,
    publication_readiness_path: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Resolve verified v2 identities without activating the candidate."""

    output = Path(out).expanduser().absolute()
    if not os.path.lexists(output.parent):
        output.parent.mkdir(parents=True, mode=0o700)
    _require_private_directory(
        output.parent, "private v2 join-remediation review result directory"
    )
    context = _load_verified_public_review_v2(
        review_path,
        review_package_dir=review_package_dir,
        v2_execution_dir=v2_execution_dir,
        v2_plan_path=v2_plan_path,
        v1_execution_dir=v1_execution_dir,
        stitch_package_dir=stitch_package_dir,
        full_song_review_result_path=full_song_review_result_path,
        v1_plan_path=v1_plan_path,
        resolved_join_review_result_path=resolved_join_review_result_path,
        publication_readiness_path=publication_readiness_path,
    )
    seed = context["seed"]
    review = context["review"]
    answer, answer_snapshot = _load_verified_answer_key_v2(
        context["review_package"],
        seed=seed,
        context=context["source_context"],
        audio_evidence=context["audio_evidence"],
    )

    answer_by_id = {row["unit_id"]: row for row in answer["boundary_assignments"]}
    resolved_units: list[dict[str, Any]] = []
    boundary_absolute = {
        identity: {choice: 0 for choice in _ABSOLUTE_CHOICES}
        for identity in ("v1_candidate", "v2_candidate")
    }
    comparison_counts = {
        "v1_candidate_preferred": 0,
        "v2_candidate_preferred": 0,
        "equivalent": 0,
        "neither": 0,
        "cannot_tell": 0,
    }
    edge_counts = {choice: 0 for choice in _ABSOLUTE_CHOICES}
    for unit in review["units"]:
        if unit["kind"] == _BOUNDARY_KIND:
            assignment = answer_by_id[unit["unit_id"]]["assignment"]
            identity_ratings = {
                assignment[slot]: unit["absolute_cleanliness"][slot]
                for slot in ("A", "B")
            }
            for identity, rating in identity_ratings.items():
                boundary_absolute[identity][rating] += 1
            choice = unit["comparative_choice"]
            if choice in ("A", "B"):
                resolved_choice = f"{assignment[choice]}_preferred"
            else:
                resolved_choice = choice
            comparison_counts[resolved_choice] += 1
            resolved_units.append(
                {
                    "unit_id": unit["unit_id"],
                    "kind": unit["kind"],
                    "title": unit["title"],
                    "focus": unit["focus"],
                    "source_window": deepcopy(unit["source_window"]),
                    "candidate_a_identity": assignment["A"],
                    "candidate_b_identity": assignment["B"],
                    "blind_absolute_cleanliness": deepcopy(
                        unit["absolute_cleanliness"]
                    ),
                    "identity_absolute_cleanliness": identity_ratings,
                    "blind_comparative_choice": choice,
                    "resolved_comparative_choice": resolved_choice,
                    "notes": unit["notes"],
                }
            )
            continue

        rating = unit["absolute_cleanliness"]
        edge_counts[rating] += 1
        resolved_units.append(
            {
                "unit_id": unit["unit_id"],
                "kind": unit["kind"],
                "title": unit["title"],
                "focus": unit["focus"],
                "source_window": deepcopy(unit["source_window"]),
                "candidate_identity": "v2_candidate",
                "absolute_cleanliness": rating,
                "notes": unit["notes"],
            }
        )

    target_boundaries_clean = (
        boundary_absolute["v2_candidate"]["clean"]
        == _EXPECTED_COUNTS["boundary_comparison_units"]
    )
    patch_edges_clean = edge_counts["clean"] == _EXPECTED_COUNTS["v2_patch_edge_units"]
    targeted_pass = target_boundaries_clean and patch_edges_clean
    source_bindings = _source_bindings(context["source_context"])
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "status": RESULT_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "blind_review": True,
        "package_commitment": review["package_commitment"],
        "bindings": {
            **source_bindings,
            "review_seed_sha256": context["seed_snapshot"]["sha256"],
            "review_seed_document_sha256": seed["document_sha256"],
            "review_export_sha256": context["review_snapshot"]["sha256"],
            "answer_key_sha256": answer_snapshot["sha256"],
            "answer_key_document_sha256": answer["document_sha256"],
        },
        "reviewed_unit_count": len(resolved_units),
        "counts": {
            "boundary_absolute_cleanliness_by_identity": boundary_absolute,
            "boundary_comparative_outcomes": comparison_counts,
            "v2_patch_edge_absolute_cleanliness": edge_counts,
        },
        "units": resolved_units,
        "readiness_evidence": {
            "targeted_v2_review_complete": True,
            "all_targeted_v2_boundary_versions_clean": target_boundaries_clean,
            "all_v2_patch_edges_clean": patch_edges_clean,
            "targeted_v2_absolute_cleanliness_pass": targeted_pass,
            "fresh_candidate_bound_full_song_review_eligible": targeted_pass,
            "fresh_candidate_bound_alignment_review_eligible": targeted_pass,
            "new_candidate_full_song_review_complete": False,
            "new_candidate_alignment_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "absolute_cleanliness_is_distinct_from_comparative_preference": True,
            "comparative_preference_is_join_elimination": False,
            "targeted_pass_is_full_song_acceptance": False,
            "targeted_pass_is_alignment_acceptance": False,
            "targeted_pass_is_separator_accuracy": False,
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
        "effects": dict(_FALSE_EFFECTS),
    }
    result["document_sha256"] = _document_sha256(result)
    _write_json_exclusive(output, result)
    return {**result, "report": str(output)}


def _load_verified_public_review_v2(
    review_path: str | Path,
    *,
    review_package_dir: str | Path,
    v2_execution_dir: str | Path,
    v2_plan_path: str | Path,
    v1_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    full_song_review_result_path: str | Path,
    v1_plan_path: str | Path,
    resolved_join_review_result_path: str | Path,
    publication_readiness_path: str | Path,
) -> dict[str, Any]:
    review_package = Path(review_package_dir).expanduser().absolute()
    _require_private_directory(review_package, "private v2 remediation review package")
    source_context = _load_review_inputs(
        v2_execution_dir,
        v2_plan_path=v2_plan_path,
        v1_execution_dir=v1_execution_dir,
        stitch_package_dir=stitch_package_dir,
        full_song_review_result_path=full_song_review_result_path,
        v1_plan_path=v1_plan_path,
        resolved_join_review_result_path=resolved_join_review_result_path,
        publication_readiness_path=publication_readiness_path,
    )
    seed_path = review_package / REVIEW_NAME
    seed_snapshot = _load_private_json_snapshot(
        seed_path, "private v2 remediation review seed"
    )
    seed = seed_snapshot["document"]
    reconstructed = _reconstruct_public_review_v2(source_context)
    _verify_seed_v2(seed, reconstructed=reconstructed)

    page_path = _private_child_regular(
        review_package, HTML_NAME, "private v2 remediation review page"
    )
    _verify_review_page_v2(page_path, seed=seed)

    review_snapshot = _load_private_json_snapshot(
        review_path, "reviewed v2 remediation export"
    )
    review = review_snapshot["document"]
    if not _browser_json_equal(
        _immutable_review_document_v2(review),
        _immutable_review_document_v2(seed),
    ):
        raise ValueError(
            "private v2 remediation review export changed immutable evidence"
        )
    _validate_completed_review_v2(review)
    audio_evidence = _verify_audio_contract_v2(
        review,
        review_package=review_package,
        reconstructed=reconstructed,
    )
    return {
        "review_package": review_package,
        "seed_snapshot": seed_snapshot,
        "seed": seed,
        "review_snapshot": review_snapshot,
        "review": review,
        "source_context": source_context,
        "reconstructed": reconstructed,
        "audio_evidence": audio_evidence,
        "audio_reference_count": 8,
    }


def _reconstruct_public_review_v2(context: Mapping[str, Any]) -> dict[str, Any]:
    units: list[dict[str, Any]] = []
    for window in context["v2_report"]["windows"]:
        boundary_index = int(window["boundary_index"])
        role = str(window["role"])
        start = int(window["patch_start_frame"])
        end = int(window["patch_end_frame"])
        if end - start != 2 * _PAIR_HALF_FRAMES:
            raise ValueError("private v2 remediation review boundary window differs")
        unit_id = f"target-boundary-{boundary_index:02d}-{role}"
        sources = {
            "v1_candidate": context["v1_audio"][role]["samples"][start:end],
            "v2_candidate": context["v2_audio"][role]["samples"][start:end],
        }
        floats = {
            identity: samples.astype("float64") / 2_147_483_648.0
            for identity, samples in sources.items()
        }
        rms = {
            identity: _sample_rms(value, np=_numpy())
            for identity, value in floats.items()
        }
        target = min(rms.values())
        gains = {identity: target / rms[identity] for identity in floats}
        expected_hashes = {
            identity: _projected_pcm24_sequence_sha256(
                floats[identity] * gains[identity]
            )
            for identity in floats
        }
        if expected_hashes["v1_candidate"] == expected_hashes["v2_candidate"]:
            raise ValueError("private v2 remediation boundary pair is PCM24-identical")
        units.append(
            {
                "public": {
                    "unit_id": unit_id,
                    "kind": _BOUNDARY_KIND,
                    "title": f"Boundary {boundary_index}: {role}",
                    "focus": (
                        "Rate each version independently for an audible join, then compare "
                        f"which better preserves the musical continuity of the {role}."
                    ),
                    "source_window": _source_window(start, end),
                    "level_policy": (
                        "attenuate-louder-to-quieter-whole-window-sample-rms-v2"
                    ),
                },
                "expected_hashes": expected_hashes,
                "levels": {
                    "v1_candidate_gain": round(gains["v1_candidate"], 12),
                    "v2_candidate_gain": round(gains["v2_candidate"], 12),
                    "v1_candidate_rms": round(rms["v1_candidate"], 12),
                    "v2_candidate_rms": round(rms["v2_candidate"], 12),
                },
            }
        )
    for window in context["v2_report"]["windows"]:
        boundary_index = int(window["boundary_index"])
        role = str(window["role"])
        for edge_name in ("start", "end"):
            centre = int(window[f"patch_{edge_name}_frame"])
            start = centre - _EDGE_HALF_FRAMES
            end = centre + _EDGE_HALF_FRAMES
            samples = context["v2_audio"][role]["samples"][start:end]
            if samples.shape != (2 * _EDGE_HALF_FRAMES, 2):
                raise ValueError("private v2 remediation edge window differs")
            unit_id = f"v2-edge-boundary-{boundary_index:02d}-{role}-{edge_name}"
            units.append(
                {
                    "public": {
                        "unit_id": unit_id,
                        "kind": _EDGE_KIND,
                        "title": (
                            f"Boundary {boundary_index}: {role} expanded patch "
                            f"{edge_name} edge"
                        ),
                        "focus": (
                            "Is this edge clean? Listen for a click, level jump, "
                            "cut-off sound or sudden tone change."
                        ),
                        "source_window": _source_window(start, end),
                        "level_policy": "unchanged-v2-pcm24-window-no-level-processing",
                    },
                    "expected_hash": _pcm24_sequence_sha256(samples),
                }
            )
    if len(units) != _EXPECTED_COUNTS["total_units"]:
        raise ValueError("private v2 remediation review unit inventory differs")
    source_bindings = _source_bindings(context)
    return {
        "units": units,
        "expected_counts": dict(_EXPECTED_COUNTS),
        "source_bindings_commitment": hashlib.sha256(
            canonical_json_bytes(source_bindings)
        ).hexdigest(),
    }


def _verify_review_page_v2(path: Path, *, seed: Mapping[str, Any]) -> None:
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("private v2 remediation review page differs")
    try:
        page = path.read_text(encoding="utf-8")
        prefix = '<script id="seed" type="application/json">'
        suffix = "</script><script>"
        embedded = page.split(prefix, 1)[1].split(suffix, 1)[0]
        embedded_seed = json.loads(embedded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, IndexError) as error:
        raise ValueError("private v2 remediation review page differs") from error
    if (
        embedded_seed != seed
        or "Export reviewed JSON" not in page
        or "Mark review complete" not in page
        or "v1_candidate" in page
        or "v2_candidate" in page
        or "boundary_assignments" in page
        or ANSWER_KEY_NAME in page
    ):
        raise ValueError("private v2 remediation review page differs")


def _verify_seed_v2(
    seed: Mapping[str, Any], *, reconstructed: Mapping[str, Any]
) -> None:
    units = seed.get("units")
    bindings = seed.get("bindings")
    if (
        set(seed) != _PUBLIC_DOCUMENT_KEYS
        or seed.get("schema") != REVIEW_SCHEMA
        or seed.get("status") != REVIEW_STATUS
        or seed.get("evidence_scope") != "private_development_only"
        or seed.get("policy_id") != POLICY_ID
        or seed.get("question") != _QUESTION
        or seed.get("instructions") != _INSTRUCTIONS
        or seed.get("expected_counts") != _EXPECTED_COUNTS
        or seed.get("summary")
        != {"reviewed_units": 0, "total_units": 6, "complete": False}
        or seed.get("readiness") != _READINESS_SEED
        or seed.get("permissions") != _FALSE_PERMISSIONS
        or seed.get("effects") != _FALSE_EFFECTS
        or seed.get("limitations") != _LIMITATIONS
        or seed.get("document_sha256") != _document_sha256(seed)
        or not isinstance(units, list)
        or len(units) != 6
        or not isinstance(bindings, Mapping)
        or set(bindings)
        != {
            "source_bindings_commitment",
            "audio_manifest_sha256",
            "answer_key_sha256",
            "answer_key_document_sha256",
        }
        or not all(_is_sha256(bindings[key]) for key in bindings)
    ):
        raise ValueError("private v2 remediation review seed differs")
    for unit, expected in zip(units, reconstructed["units"]):
        public = expected["public"]
        required_keys = (
            _BOUNDARY_UNIT_KEYS if public["kind"] == _BOUNDARY_KIND else _EDGE_UNIT_KEYS
        )
        if set(unit) != required_keys or any(
            not _browser_json_equal(unit.get(key), value)
            for key, value in public.items()
        ):
            raise ValueError("private v2 remediation review public semantics differ")
        _validate_seed_unit_v2(unit)
    if len({unit["unit_id"] for unit in units}) != len(units):
        raise ValueError("private v2 remediation review unit identities differ")

    audio_manifest = _audio_manifest_sha256(seed)
    if audio_manifest != bindings["audio_manifest_sha256"]:
        raise ValueError("private v2 remediation review audio manifest differs")
    if (
        bindings["source_bindings_commitment"]
        != reconstructed["source_bindings_commitment"]
    ):
        raise ValueError("private v2 remediation review source bindings differ")
    commitment = hashlib.sha256(
        (
            f"{bindings['answer_key_sha256']}:"
            f"{bindings['answer_key_document_sha256']}:"
            f"{audio_manifest}"
        ).encode("ascii")
    ).hexdigest()
    if seed.get("package_commitment") != commitment:
        raise ValueError("private v2 remediation review package commitment differs")


def _validate_seed_unit_v2(unit: Mapping[str, Any]) -> None:
    kind = unit["kind"]
    if (
        not isinstance(unit.get("unit_id"), str)
        or not unit["unit_id"]
        or not isinstance(unit.get("title"), str)
        or not unit["title"]
        or not isinstance(unit.get("focus"), str)
        or not unit["focus"]
        or unit.get("notes") != ""
        or not isinstance(unit.get("audio"), Mapping)
    ):
        raise ValueError("private v2 remediation review unit differs")
    expected_slots = {"A", "B"} if kind == _BOUNDARY_KIND else {"clip"}
    if set(unit["audio"]) != expected_slots:
        raise ValueError("private v2 remediation review audio inventory differs")
    for slot, record in unit["audio"].items():
        expected_name = (
            f"{unit['unit_id']}-{slot}.wav"
            if kind == _BOUNDARY_KIND
            else f"{unit['unit_id']}.wav"
        )
        geometry = record.get("geometry") if isinstance(record, Mapping) else None
        if (
            not isinstance(record, Mapping)
            or set(record) != _AUDIO_RECORD_KEYS
            or record.get("path") != f"{AUDIO_DIRECTORY}/{expected_name}"
            or not _is_sha256(record.get("sha256"))
            or not _is_sha256(record.get("pcm24_int32_sequence_sha256"))
            or type(record.get("bytes")) is not int
            or record["bytes"] <= 0
            or not isinstance(geometry, Mapping)
            or set(geometry) != {*_GEOMETRY, "frames"}
            or any(geometry.get(key) != value for key, value in _GEOMETRY.items())
            or type(geometry.get("frames")) is not int
            or geometry["frames"] <= 0
        ):
            raise ValueError("private v2 remediation review audio claim differs")
    if kind == _BOUNDARY_KIND:
        if (
            unit.get("heard") != {"A": False, "B": False}
            or unit.get("absolute_cleanliness") != {"A": None, "B": None}
            or unit.get("comparative_choice") is not None
        ):
            raise ValueError("private v2 remediation boundary seed differs")
    elif kind == _EDGE_KIND:
        if (
            unit.get("heard") is not False
            or unit.get("absolute_cleanliness") is not None
        ):
            raise ValueError("private v2 remediation edge seed differs")
    else:
        raise ValueError("private v2 remediation review unit kind differs")


def _validate_completed_review_v2(review: Mapping[str, Any]) -> None:
    units = review.get("units")
    if (
        review.get("status") != "reviewed"
        or not isinstance(units, list)
        or review.get("summary")
        != {"reviewed_units": 6, "total_units": 6, "complete": True}
        or review.get("permissions") != _FALSE_PERMISSIONS
        or review.get("effects") != _FALSE_EFFECTS
    ):
        raise ValueError("private v2 remediation review is incomplete")
    for unit in units:
        notes = unit.get("notes") if isinstance(unit, Mapping) else None
        if not isinstance(notes, str) or len(notes) > _MAXIMUM_NOTES_CHARACTERS:
            raise ValueError("private v2 remediation review unit is incomplete")
        if unit["kind"] == _BOUNDARY_KIND:
            absolute = unit.get("absolute_cleanliness")
            if (
                unit.get("heard") != {"A": True, "B": True}
                or not isinstance(absolute, Mapping)
                or set(absolute) != {"A", "B"}
                or any(absolute[slot] not in _ABSOLUTE_CHOICES for slot in absolute)
                or unit.get("comparative_choice") not in _COMPARATIVE_CHOICES
            ):
                raise ValueError("private v2 remediation review unit is incomplete")
        elif (
            unit.get("heard") is not True
            or unit.get("absolute_cleanliness") not in _ABSOLUTE_CHOICES
        ):
            raise ValueError("private v2 remediation review unit is incomplete")


def _immutable_review_document_v2(document: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(document))
    result["status"] = REVIEW_STATUS
    result["summary"] = {"reviewed_units": 0, "total_units": 6, "complete": False}
    units = result.get("units")
    if isinstance(units, list):
        for unit in units:
            if not isinstance(unit, dict):
                continue
            if unit.get("kind") == _BOUNDARY_KIND:
                unit["heard"] = {"A": False, "B": False}
                unit["absolute_cleanliness"] = {"A": None, "B": None}
                unit["comparative_choice"] = None
            else:
                unit["heard"] = False
                unit["absolute_cleanliness"] = None
            unit["notes"] = ""
    return result


def _verify_audio_contract_v2(
    review: Mapping[str, Any],
    *,
    review_package: Path,
    reconstructed: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    referenced: set[Path] = set()
    evidence: dict[str, dict[str, Any]] = {}
    _require_private_directory(
        review_package / AUDIO_DIRECTORY, "private v2 remediation review audio root"
    )
    for unit, expected in zip(review["units"], reconstructed["units"]):
        if unit["unit_id"] != expected["public"]["unit_id"]:
            raise ValueError("private v2 remediation review audio semantics differ")
        actual_hashes: dict[str, str] = {}
        for slot, record in unit["audio"].items():
            path = _private_child_regular(
                review_package,
                record["path"],
                "private v2 remediation review audio",
            )
            if (
                path.parent != (review_package / AUDIO_DIRECTORY).resolve()
                or path in referenced
            ):
                raise ValueError("private v2 remediation review audio is reused")
            referenced.add(path)
            observed = _read_pcm24_snapshot(
                path,
                record,
                expected_frames=record["geometry"]["frames"],
                label="private v2 remediation review audio",
            )
            actual_hashes[slot] = observed["pcm24_int32_sequence_sha256"]
            if actual_hashes[slot] != record["pcm24_int32_sequence_sha256"]:
                raise ValueError("private v2 remediation review audio differs")
        expected_frames = (
            2 * _PAIR_HALF_FRAMES
            if unit["kind"] == _BOUNDARY_KIND
            else 2 * _EDGE_HALF_FRAMES
        )
        if any(
            record["geometry"]["frames"] != expected_frames
            for record in unit["audio"].values()
        ):
            raise ValueError("private v2 remediation review audio geometry differs")
        if unit["kind"] == _BOUNDARY_KIND:
            if sorted(actual_hashes.values()) != sorted(
                expected["expected_hashes"].values()
            ):
                raise ValueError("private v2 remediation boundary audio differs")
            evidence[unit["unit_id"]] = {
                "actual_hashes": actual_hashes,
                "expected_hashes": expected["expected_hashes"],
                "levels": expected["levels"],
            }
        else:
            if actual_hashes != {"clip": expected["expected_hash"]}:
                raise ValueError("private v2 remediation patch-edge audio differs")
            evidence[unit["unit_id"]] = {"actual_hashes": actual_hashes}
    if len(referenced) != _EXPECTED_COUNTS["total_audio_references"]:
        raise ValueError("private v2 remediation review audio inventory differs")
    return evidence


def _load_verified_answer_key_v2(
    review_package: Path,
    *,
    seed: Mapping[str, Any],
    context: Mapping[str, Any],
    audio_evidence: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = _load_private_json_snapshot(
        review_package / ANSWER_KEY_NAME,
        "private v2 remediation review answer key",
    )
    bindings = seed["bindings"]
    answer = snapshot["document"]
    source_bindings = _source_bindings(context)
    expected_bindings = {
        **source_bindings,
        "source_bindings_commitment": hashlib.sha256(
            canonical_json_bytes(source_bindings)
        ).hexdigest(),
        "audio_manifest_sha256": bindings["audio_manifest_sha256"],
    }
    if (
        snapshot["sha256"] != bindings["answer_key_sha256"]
        or set(answer)
        != {
            "schema",
            "status",
            "nonce",
            "bindings",
            "boundary_assignments",
            "permissions",
            "document_sha256",
        }
        or answer.get("schema") != ANSWER_KEY_SCHEMA
        or answer.get("status") != "sealed_do_not_open_before_review"
        or not _is_nonce(answer.get("nonce"))
        or answer.get("bindings") != expected_bindings
        or answer.get("permissions") != _FALSE_PERMISSIONS
        or answer.get("document_sha256") != _document_sha256(answer)
        or answer.get("document_sha256") != bindings["answer_key_document_sha256"]
    ):
        raise ValueError("private v2 remediation review answer key differs")
    assignments = answer.get("boundary_assignments")
    boundary_units = [unit for unit in seed["units"] if unit["kind"] == _BOUNDARY_KIND]
    if not isinstance(assignments, list) or len(assignments) != len(boundary_units):
        raise ValueError("private v2 remediation review answer inventory differs")
    for unit, assignment_record in zip(boundary_units, assignments):
        if not isinstance(assignment_record, Mapping):
            raise ValueError("private v2 remediation review answer differs")
        assignment = assignment_record.get("assignment")
        evidence = audio_evidence[unit["unit_id"]]
        if (
            set(assignment_record)
            != {
                "unit_id",
                "assignment",
                "v1_candidate_gain",
                "v2_candidate_gain",
                "v1_candidate_rms",
                "v2_candidate_rms",
            }
            or assignment_record.get("unit_id") != unit["unit_id"]
            or not isinstance(assignment, Mapping)
            or set(assignment) != {"A", "B"}
            or set(assignment.values()) != {"v1_candidate", "v2_candidate"}
            or any(
                not _browser_json_equal(assignment_record.get(key), value)
                for key, value in evidence["levels"].items()
            )
            or any(
                evidence["actual_hashes"][slot]
                != evidence["expected_hashes"][assignment[slot]]
                for slot in ("A", "B")
            )
        ):
            raise ValueError("private v2 remediation review answer binding differs")
        for key in (
            "v1_candidate_gain",
            "v2_candidate_gain",
            "v1_candidate_rms",
            "v2_candidate_rms",
        ):
            value = assignment_record[key]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value <= 0
            ):
                raise ValueError("private v2 remediation review answer level differs")
        if (
            max(
                assignment_record["v1_candidate_gain"],
                assignment_record["v2_candidate_gain"],
            )
            != 1
        ):
            raise ValueError("private v2 remediation review answer level differs")
    return answer, snapshot


def _audio_manifest_sha256(review: Mapping[str, Any]) -> str:
    manifest = {
        "schema": "sunofriend.private-separation-full-song-join-remediation-audio.v2",
        "units": [
            {"unit_id": unit["unit_id"], "audio": unit["audio"]}
            for unit in review["units"]
        ],
    }
    return hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()


def _source_window(start: int, end: int) -> dict[str, Any]:
    return {
        "start_frame": start,
        "end_frame": end,
        "start_seconds": start / TARGET_SAMPLE_RATE,
        "end_seconds": end / TARGET_SAMPLE_RATE,
    }


def _projected_pcm24_sequence_sha256(value: Any) -> str:
    import soundfile

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
        raise ValueError("private v2 remediation PCM24 projection differs")
    return _pcm24_sequence_sha256(samples)


def _pcm24_sequence_sha256(value: Any) -> str:
    np = _numpy()
    little_endian = np.asarray(value, dtype="<i4")
    return hashlib.sha256(little_endian.tobytes(order="C")).hexdigest()


def _numpy() -> Any:
    import numpy

    return numpy


def _counts_by_kind(units: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        _BOUNDARY_KIND: sum(unit.get("kind") == _BOUNDARY_KIND for unit in units),
        _EDGE_KIND: sum(unit.get("kind") == _EDGE_KIND for unit in units),
    }


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        return len(bytes.fromhex(value)) == 32
    except ValueError:
        return False


__all__: tuple[str, ...] = ()
