"""Measure alignment for the exact passing v2 full-song candidate.

This is fresh nine-window clock evidence.  It does not reuse the earlier
candidate's alignment decision and cannot select, accept or publish a
separator.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from typing import Any

from ._separation_authorised_excerpt import _document_sha256
from ._separation_candidate_full_song_review import (
    _require_review_result_unchanged,
    _verify_passing_v2_review_result,
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
from ._separation_full_song_join_remediation_review_v2 import (
    _load_review_inputs,
    _reverify_inputs,
)


SCHEMA = "sunofriend.private-separation-candidate-full-song-alignment-result.v1"
STATUS = "complete_candidate_alignment_no_activation"
POLICY_ID = f"{ALIGNMENT_POLICY_ID}:v2-candidate-bound"
REPORT_NAME = "private-separation-candidate-full-song-alignment.json"
_FALSE_EFFECTS = {
    "audio_created_or_mutated": False,
    "candidate_accepted": False,
    "candidate_selected": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "source_graph_mutated": False,
}


def _measure_private_candidate_full_song_alignment(
    v2_review_result_path: str | Path,
    *,
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
    """Write one path-free nine-window alignment result for the v2 candidate."""

    import numpy as np
    import soundfile

    output = Path(out).expanduser().absolute()
    _require_private_directory(
        output.parent, "private candidate alignment result parent"
    )
    if os.path.lexists(output):
        raise FileExistsError(f"private candidate alignment result exists: {output}")
    context = _load_review_inputs(
        v2_execution_dir,
        v2_plan_path=v2_plan_path,
        v1_execution_dir=v1_execution_dir,
        stitch_package_dir=stitch_package_dir,
        full_song_review_result_path=full_song_review_result_path,
        v1_plan_path=v1_plan_path,
        resolved_join_review_result_path=resolved_join_review_result_path,
        publication_readiness_path=publication_readiness_path,
    )
    review_result_snapshot = _load_private_json_snapshot(
        v2_review_result_path, "private resolved v2 join review result"
    )
    _verify_passing_v2_review_result(review_result_snapshot, context=context)
    evidence_paths = (
        review_result_snapshot["path"],
        context["v2_snapshot"]["path"],
        context["v2_plan_snapshot"]["path"],
        context["stitch_snapshot"]["path"],
        context["v1_execution_snapshot"]["path"],
        context["v1_candidate_snapshot"]["path"],
        *context["authority_paths"],
    )
    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(
            context["v1_root"],
            context["v2_root"],
            context["stitch_root"],
        ),
        evidence_paths=evidence_paths,
    )

    clock = context["stitch"]["clock"]
    expected_frames = int(clock["frames"])
    source_record = context["stitch"]["artifacts"]["source"]
    reconstruction_record = context["v2_report"]["artifacts"]["reconstruction"]
    source_path = _private_child_regular(
        context["stitch_root"],
        source_record["path"],
        "private candidate alignment source",
    )
    reconstruction_path = _private_child_regular(
        context["v2_root"],
        reconstruction_record["path"],
        "private candidate alignment reconstruction",
    )
    source_snapshot = _read_pcm24_snapshot(
        source_path,
        source_record,
        expected_frames=expected_frames,
        label="private candidate alignment source",
    )
    reconstruction_snapshot = _read_pcm24_snapshot(
        reconstruction_path,
        reconstruction_record,
        expected_frames=expected_frames,
        label="private candidate alignment reconstruction",
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
    _require_review_result_unchanged(review_result_snapshot)
    _reverify_inputs(context)

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "candidate_identity": "v2_expanded_context_join_remediation",
        "bindings": {
            "v2_review_result_sha256": review_result_snapshot["sha256"],
            "v2_review_result_document_sha256": review_result_snapshot[
                "document"
            ]["document_sha256"],
            "v2_execution_report_sha256": context["v2_snapshot"]["sha256"],
            "v2_execution_document_sha256": context["v2_report"][
                "document_sha256"
            ],
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
            "targeted_v2_absolute_cleanliness_pass": True,
            "new_candidate_alignment_complete": True,
            "source_to_reconstruction_alignment_verified": observation[
                "gate_passed"
            ],
            "drift_acceptance_complete": observation["gate_passed"],
            "alignment_gate_passed": observation["gate_passed"],
            "new_candidate_full_song_review_complete": False,
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
            "This report measures only the exact v2 source-to-reconstruction clock and drift.",
            "The earlier candidate's alignment result is not inherited.",
            "A synchronized reconstruction can still contain bleed, omissions or artefacts.",
            "Fresh candidate-bound full-song and boundary listening remains separate evidence.",
        ],
    }
    result["document_sha256"] = _document_sha256(result)
    published = False
    try:
        _write_json_exclusive(output, result)
        published = True
        _require_review_result_unchanged(review_result_snapshot)
        _reverify_inputs(context)
        for path, claim, label in (
            (source_path, source_snapshot, "private candidate alignment source"),
            (
                reconstruction_path,
                reconstruction_snapshot,
                "private candidate alignment reconstruction",
            ),
        ):
            _read_pcm24_snapshot(
                path,
                claim,
                expected_frames=expected_frames,
                label=label,
            )
    except BaseException:
        if published:
            try:
                output.unlink()
            except FileNotFoundError:
                pass
        raise
    return {**result, "report": str(output)}


__all__: tuple[str, ...] = ()
