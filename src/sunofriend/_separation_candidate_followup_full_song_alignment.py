"""Measure alignment for an exactly reviewed follow-up separator candidate."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_candidate_followup_full_song_review_result import (
    _load_completed_review,
    _resolved_result_document,
)
from ._separation_full_song_alignment import (
    POLICY_ID as ALIGNMENT_POLICY_ID,
    _measure_alignment_observation,
    _require_audio_clock,
)
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _read_pcm24_snapshot,
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_join_remediation_plan_v2 import _private_child_regular
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)


SCHEMA = (
    "sunofriend.private-separation-candidate-followup-full-song-alignment-result.v1"
)
STATUS = "complete_followup_alignment_no_activation"
POLICY_ID = f"{ALIGNMENT_POLICY_ID}:review-derived-followup-candidate-bound"
REPORT_NAME = "private-separation-candidate-followup-full-song-alignment.json"
_FALSE_EFFECTS = {
    "audio_created_or_mutated": False,
    "candidate_accepted": False,
    "candidate_selected": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "source_graph_mutated": False,
}


def _measure_private_candidate_followup_full_song_alignment(
    full_song_review_result_path: str | Path,
    *,
    full_song_review_export_path: str | Path,
    full_song_review_package_dir: str | Path,
    targeted_review_result_path: str | Path,
    targeted_reviewed_export_path: str | Path,
    targeted_review_package_dir: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Write a path-free nine-window result for the exact follow-up candidate."""

    import numpy as np
    import soundfile

    output = Path(out).expanduser().absolute()
    _require_private_directory(
        output.parent, "private follow-up alignment result parent"
    )
    if os.path.lexists(output):
        raise FileExistsError(f"private follow-up alignment result exists: {output}")
    review_kwargs = {
        "review_package_dir": full_song_review_package_dir,
        "targeted_review_result_path": targeted_review_result_path,
        "targeted_reviewed_export_path": targeted_reviewed_export_path,
        "targeted_review_package_dir": targeted_review_package_dir,
        "execution_dir": execution_dir,
        "v2_execution_dir": v2_execution_dir,
        "stitch_package_dir": stitch_package_dir,
    }
    context = _load_completed_review(full_song_review_export_path, **review_kwargs)
    review_result_snapshot = _load_private_json_snapshot(
        full_song_review_result_path,
        "private follow-up full-song review result",
    )
    expected_review_result = _resolved_result_document(context)
    if review_result_snapshot["document"] != expected_review_result:
        raise ValueError("private follow-up full-song review result differs")

    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(
            context["package"],
            context["execution"],
            context["v2_execution"],
            context["targeted_package"],
            context["stitch_root"],
        ),
        evidence_paths=(
            review_result_snapshot["path"],
            context["review_snapshot"]["path"],
            context["package_snapshot"]["path"],
            context["targeted_result_snapshot"]["path"],
            context["inputs"]["execution_snapshot"]["path"],
            context["inputs"]["candidate_snapshot"]["path"],
            context["inputs"]["v2_snapshot"]["path"],
            context["stitch_snapshot"]["path"],
        ),
    )

    clock = context["stitch"]["clock"]
    expected_frames = int(clock["frames"])
    source_record = context["stitch"]["artifacts"]["source"]
    reconstruction_record = context["inputs"]["candidate"]["artifacts"][
        "reconstruction"
    ]
    source_path = _private_child_regular(
        context["stitch_root"],
        source_record["path"],
        "private follow-up alignment source",
    )
    reconstruction_path = context["inputs"]["candidate_paths"]["reconstruction"]
    source_snapshot = _read_pcm24_snapshot(
        source_path,
        source_record,
        expected_frames=expected_frames,
        label="private follow-up alignment source",
    )
    reconstruction_snapshot = _read_pcm24_snapshot(
        reconstruction_path,
        reconstruction_record,
        expected_frames=expected_frames,
        label="private follow-up alignment reconstruction",
    )
    _require_audio_clock(source_path, clock=clock, soundfile=soundfile)
    _require_audio_clock(reconstruction_path, clock=clock, soundfile=soundfile)
    observation = _measure_alignment_observation(
        source_path,
        reconstruction_path,
        clock=clock,
        soundfile=soundfile,
        np=np,
    )
    readiness = expected_review_result["readiness_evidence"]
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "candidate_identity": "review_derived_followup_join_remediation",
        "bindings": {
            "followup_full_song_review_result_sha256": review_result_snapshot[
                "sha256"
            ],
            "followup_full_song_review_result_document_sha256": expected_review_result[
                "document_sha256"
            ],
            "followup_review_package_report_sha256": context["package_snapshot"][
                "sha256"
            ],
            "followup_review_export_sha256": context["review_snapshot"]["sha256"],
            "followup_execution_report_sha256": context["inputs"][
                "execution_snapshot"
            ]["sha256"],
            "followup_candidate_report_sha256": context["inputs"][
                "candidate_snapshot"
            ]["sha256"],
            "stitch_report_sha256": context["stitch_snapshot"]["sha256"],
            "stitch_document_sha256": context["stitch"]["document_sha256"],
            "source_audio_sha256": source_snapshot["sha256"],
            "source_pcm24_int32_sequence_sha256": source_snapshot[
                "pcm24_int32_sequence_sha256"
            ],
            "reconstruction_audio_sha256": reconstruction_snapshot["sha256"],
            "reconstruction_pcm24_int32_sequence_sha256": reconstruction_snapshot[
                "pcm24_int32_sequence_sha256"
            ],
        },
        "clock": deepcopy(clock),
        "protocol": observation["protocol"],
        "thresholds": observation["thresholds"],
        "windows": observation["windows"],
        "summary": observation["summary"],
        "readiness_evidence": {
            "targeted_followup_listening_pass": True,
            "followup_complete_song_review_complete": True,
            "all_followup_boundaries_clean": readiness[
                "all_followup_boundaries_clean"
            ],
            "all_followup_full_song_roles_useful": readiness[
                "all_followup_full_song_roles_useful"
            ],
            "followup_alignment_complete": True,
            "source_to_reconstruction_alignment_verified": observation["gate_passed"],
            "drift_acceptance_complete": observation["gate_passed"],
            "alignment_gate_passed": observation["gate_passed"],
            "fresh_readiness_reassessment_eligible": True,
            "original_audible_joins_resolved": False,
            "separator_accuracy_established": False,
            "publication_ready": False,
        },
        "interpretation": {
            "alignment_is_separator_quality": False,
            "reconstruction_similarity_is_role_fidelity": False,
            "gate_pass_is_separator_acceptance": False,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": [
            "This report measures only the exact follow-up source-to-reconstruction clock and drift.",
            "The v2 candidate alignment result is not inherited.",
            "A synchronized reconstruction can still contain bleed, omissions or artefacts.",
            "Human full-song and all-boundary ratings remain separate evidence.",
        ],
    }
    result["document_sha256"] = _document_sha256(result)
    published = False
    try:
        _write_json_exclusive(output, result)
        published = True
        _reverify_alignment_inputs(
            review_result_snapshot=review_result_snapshot,
            expected_review_result=expected_review_result,
            full_song_review_export_path=full_song_review_export_path,
            review_kwargs=review_kwargs,
            source_path=source_path,
            source_snapshot=source_snapshot,
            reconstruction_path=reconstruction_path,
            reconstruction_snapshot=reconstruction_snapshot,
            expected_frames=expected_frames,
        )
    except BaseException:
        if published:
            try:
                output.unlink()
            except FileNotFoundError:
                pass
        raise
    return {**result, "report": str(output)}


def _reverify_alignment_inputs(
    *,
    review_result_snapshot: Mapping[str, Any],
    expected_review_result: Mapping[str, Any],
    full_song_review_export_path: str | Path,
    review_kwargs: Mapping[str, Any],
    source_path: Path,
    source_snapshot: Mapping[str, Any],
    reconstruction_path: Path,
    reconstruction_snapshot: Mapping[str, Any],
    expected_frames: int,
) -> None:
    current_result = _load_private_json_snapshot(
        review_result_snapshot["path"],
        "private follow-up full-song review result",
    )
    if (
        current_result["sha256"] != review_result_snapshot["sha256"]
        or current_result["document"] != expected_review_result
    ):
        raise ValueError("private follow-up full-song review result changed")
    current_context = _load_completed_review(
        full_song_review_export_path, **review_kwargs
    )
    if _resolved_result_document(current_context) != expected_review_result:
        raise ValueError("private follow-up full-song review evidence changed")
    for path, claim, label in (
        (source_path, source_snapshot, "private follow-up alignment source"),
        (
            reconstruction_path,
            reconstruction_snapshot,
            "private follow-up alignment reconstruction",
        ),
    ):
        _read_pcm24_snapshot(
            path,
            claim,
            expected_frames=expected_frames,
            label=label,
        )


__all__: tuple[str, ...] = ()
