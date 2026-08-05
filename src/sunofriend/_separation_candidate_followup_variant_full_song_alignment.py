"""Measure every independently reviewed eligible remediation variant.

The preceding human stage may contain one or two eligible variants.  This
module requires that complete review set and measures the source clock against
each exact reconstruction in canonical plan order.  It accepts no preferred
subset and records no winner, acceptance, activation or publication decision.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_candidate_followup_variant_full_song_review_result import (
    RESULT_SCHEMA as FULL_SONG_RESULT_SCHEMA,
    RESULT_STATUS as FULL_SONG_RESULT_STATUS,
    _load_completed_reviews,
    _resolved_result_document,
    _result_bindings,
    _reverify_completed_reviews,
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
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_stitch import _make_private_tree


SCHEMA = (
    "sunofriend.private-separation-candidate-followup-variant-"
    "full-song-alignment-package.v1"
)
STATUS = "complete_independent_variant_alignments_no_activation"
VARIANT_SCHEMA = (
    "sunofriend.private-separation-candidate-followup-variant-"
    "full-song-alignment-result.v1"
)
VARIANT_STATUS = "complete_independent_variant_alignment_no_activation"
POLICY_ID = f"{ALIGNMENT_POLICY_ID}:independent-reviewed-eligible-variant-bound"
REPORT_NAME = (
    "private-separation-candidate-followup-variant-full-song-alignment.json"
)
VARIANT_REPORT_NAME = "private-separation-variant-full-song-alignment.json"
_FALSE_EFFECTS = {
    "alignment_evidence_created": True,
    "audio_created_or_mutated": False,
    "candidate_accepted": False,
    "candidate_selected": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "source_graph_mutated": False,
}
_VARIANT_FALSE_EFFECTS = {
    **_FALSE_EFFECTS,
    "alignment_evidence_created": False,
}
_LIMITATIONS = [
    "Each reviewed eligible variant is measured independently in canonical plan order.",
    "The command accepts no preferred variant or caller-selected subset.",
    "Clock synchronization is not stem fidelity, musical quality or separator accuracy.",
    "Human full-song and boundary ratings remain separate evidence.",
    "Input JSON and WAV descriptors are not one atomic snapshot; keep every evidence tree quiescent.",
]


def _measure_private_candidate_followup_variant_full_song_alignments(
    full_song_review_result_path: str | Path,
    *,
    full_song_review_export_paths: Sequence[str | Path],
    full_song_review_package_dir: str | Path,
    variant_review_result_path: str | Path,
    variant_reviewed_export_path: str | Path,
    variant_review_package_dir: str | Path,
    plan_path: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Write one atomic package containing every required fresh alignment."""

    import numpy as np
    import soundfile

    if isinstance(full_song_review_export_paths, (str, bytes, Path)):
        raise TypeError(
            "full_song_review_export_paths must be the complete review sequence"
        )
    reviewed_exports = list(full_song_review_export_paths)
    if not reviewed_exports:
        raise ValueError("no eligible-variant full-song reviews supplied")

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            "private eligible-variant alignment package already exists: "
            f"{destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    _require_private_directory(
        destination.parent, "private eligible-variant alignment parent"
    )

    review_kwargs = {
        "review_package_dir": full_song_review_package_dir,
        "variant_review_result_path": variant_review_result_path,
        "variant_reviewed_export_path": variant_reviewed_export_path,
        "variant_review_package_dir": variant_review_package_dir,
        "plan_path": plan_path,
        "execution_dir": execution_dir,
        "v2_execution_dir": v2_execution_dir,
        "variant_execution_dir": variant_execution_dir,
        "stitch_package_dir": stitch_package_dir,
    }
    context = _load_completed_reviews(reviewed_exports, **review_kwargs)
    result_snapshot, expected_review_result = _require_exact_full_song_result(
        full_song_review_result_path, context=context
    )

    _require_output_disjoint_from_inputs(
        destination,
        evidence_roots=(
            context["package"],
            context["variant_review_package"],
            context["base_root"],
            context["v2_root"],
            context["variant_root"],
            context["stitch_root"],
        ),
        evidence_paths=(
            result_snapshot["path"],
            context["package_snapshot"]["path"],
            context["variant_result_snapshot"]["path"],
            context["reviewed_variant_export"],
            context["plan_snapshot"]["path"],
            context["execution_snapshot"]["path"],
            context["candidates_snapshot"]["path"],
            context["inputs"]["execution_snapshot"]["path"],
            context["inputs"]["candidate_snapshot"]["path"],
            context["inputs"]["v2_snapshot"]["path"],
            context["stitch_snapshot"]["path"],
            *(item["review_snapshot"]["path"] for item in context["completed_reviews"]),
        ),
    )

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=destination.parent)
    )
    temporary.chmod(0o700)
    audio_snapshots: list[dict[str, Any]] = []
    published = False
    try:
        clock = context["package_report"]["clock"]
        expected_frames = int(clock["frames"])
        review_results = {
            item["variant_id"]: item
            for item in expected_review_result["variant_results"]
        }
        variant_alignments: list[dict[str, Any]] = []
        for index, item in enumerate(context["completed_reviews"], start=1):
            variant_id = item["variant_id"]
            review_result = review_results[variant_id]
            package_root = item["package_root"]
            artifacts = item["package_item"]["artifacts"]
            source_path = package_root / artifacts["source"]["path"]
            reconstruction_path = package_root / artifacts["reconstruction"]["path"]
            source_snapshot = _read_pcm24_snapshot(
                source_path,
                artifacts["source"],
                expected_frames=expected_frames,
                label=f"private eligible-variant {variant_id} alignment source",
            )
            reconstruction_snapshot = _read_pcm24_snapshot(
                reconstruction_path,
                artifacts["reconstruction"],
                expected_frames=expected_frames,
                label=(
                    f"private eligible-variant {variant_id} alignment reconstruction"
                ),
            )
            _require_audio_clock(source_path, clock=clock, soundfile=soundfile)
            _require_audio_clock(
                reconstruction_path, clock=clock, soundfile=soundfile
            )
            observation = _measure_alignment_observation(
                source_path,
                reconstruction_path,
                clock=clock,
                soundfile=soundfile,
                np=np,
            )
            variant_document = _variant_alignment_document(
                context=context,
                result_snapshot=result_snapshot,
                expected_review_result=expected_review_result,
                item=item,
                review_result=review_result,
                source_snapshot=source_snapshot,
                reconstruction_snapshot=reconstruction_snapshot,
                observation=observation,
            )
            variant_root = temporary / f"variant-{index:02d}"
            variant_root.mkdir(mode=0o700)
            variant_report = variant_root / VARIANT_REPORT_NAME
            _write_json_exclusive(variant_report, variant_document)
            variant_alignments.append(
                {
                    "alignment_id": f"eligible-variant-alignment-{index:02d}",
                    "review_id": item["package_item"]["review_id"],
                    "variant_id": variant_id,
                    "report": variant_report.relative_to(temporary).as_posix(),
                    "report_sha256": _sha256(variant_report),
                    "report_document_sha256": variant_document["document_sha256"],
                    "alignment_gate_passed": observation["gate_passed"],
                    "selected": False,
                    "accepted": False,
                }
            )
            audio_snapshots.append(
                {
                    "source_path": source_path,
                    "source_snapshot": source_snapshot,
                    "reconstruction_path": reconstruction_path,
                    "reconstruction_snapshot": reconstruction_snapshot,
                    "expected_frames": expected_frames,
                }
            )

        document = _alignment_package_document(
            context=context,
            result_snapshot=result_snapshot,
            expected_review_result=expected_review_result,
            variant_alignments=variant_alignments,
        )
        _write_json_exclusive(temporary / REPORT_NAME, document)
        _verify_written_package(temporary, document=document)
        _reverify_alignment_inputs(
            context=context,
            full_song_review_result_path=full_song_review_result_path,
            result_snapshot=result_snapshot,
            expected_review_result=expected_review_result,
            audio_snapshots=audio_snapshots,
        )
        _make_private_tree(temporary)
        os.replace(temporary, destination)
        published = True
        _verify_written_package(destination, document=document)
        _reverify_alignment_inputs(
            context=context,
            full_song_review_result_path=full_song_review_result_path,
            result_snapshot=result_snapshot,
            expected_review_result=expected_review_result,
            audio_snapshots=audio_snapshots,
        )
    except BaseException:
        if published:
            shutil.rmtree(destination, ignore_errors=True)
        else:
            shutil.rmtree(temporary, ignore_errors=True)
        raise

    return {
        **document,
        "report": str(destination / REPORT_NAME),
        "variant_reports": [
            str(destination / item["report"])
            for item in document["variant_alignments"]
        ],
        "output_directory": str(destination),
    }


def _require_exact_full_song_result(
    result_path: str | Path, *, context: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = _load_private_json_snapshot(
        result_path, "private eligible-variant full-song review result"
    )
    expected = _resolved_result_document(context)
    document = snapshot["document"]
    if (
        document != expected
        or document.get("schema") != FULL_SONG_RESULT_SCHEMA
        or document.get("status") != FULL_SONG_RESULT_STATUS
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("reviewed_variant_ids") != context["eligible_variant_ids"]
        or document.get("reviewed_variant_count")
        != len(context["eligible_variant_ids"])
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("readiness_evidence", {}).get("variant_selected") is not False
    ):
        raise ValueError("private eligible-variant full-song review result differs")
    return snapshot, expected


def _variant_alignment_document(
    *,
    context: Mapping[str, Any],
    result_snapshot: Mapping[str, Any],
    expected_review_result: Mapping[str, Any],
    item: Mapping[str, Any],
    review_result: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
    reconstruction_snapshot: Mapping[str, Any],
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": VARIANT_SCHEMA,
        "status": VARIANT_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "alignment_id": item["package_item"]["review_id"],
        "variant_id": item["variant_id"],
        "bindings": {
            "variant_full_song_review_result_sha256": result_snapshot["sha256"],
            "variant_full_song_review_result_document_sha256": expected_review_result[
                "document_sha256"
            ],
            "variant_full_song_review_export_sha256": item["review_snapshot"][
                "sha256"
            ],
            "variant_full_song_review_seed_sha256": item["seed_snapshot"]["sha256"],
            "variant_full_song_review_package_commitment": item["seed_snapshot"][
                "document"
            ]["package_commitment"],
            "source_audio_sha256": source_snapshot["sha256"],
            "source_pcm24_int32_sequence_sha256": source_snapshot[
                "pcm24_int32_sequence_sha256"
            ],
            "reconstruction_audio_sha256": reconstruction_snapshot["sha256"],
            "reconstruction_pcm24_int32_sequence_sha256": reconstruction_snapshot[
                "pcm24_int32_sequence_sha256"
            ],
        },
        "clock": deepcopy(context["package_report"]["clock"]),
        "protocol": deepcopy(observation["protocol"]),
        "thresholds": deepcopy(observation["thresholds"]),
        "windows": deepcopy(observation["windows"]),
        "summary": deepcopy(observation["summary"]),
        "readiness_evidence": {
            "variant_targeted_review_complete": True,
            "variant_full_song_review_complete": True,
            "all_full_song_roles_useful": review_result["readiness_evidence"][
                "all_full_song_roles_useful"
            ],
            "all_original_boundaries_clean": review_result["readiness_evidence"][
                "all_boundaries_clean"
            ],
            "alignment_complete": True,
            "source_to_reconstruction_alignment_verified": observation["gate_passed"],
            "drift_acceptance_complete": observation["gate_passed"],
            "alignment_gate_passed": observation["gate_passed"],
            "fresh_readiness_reassessment_eligible": True,
            "selected": False,
            "accepted": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "alignment_is_separator_quality": False,
            "reconstruction_similarity_is_role_fidelity": False,
            "gate_pass_is_separator_acceptance": False,
            "package_order_is_preference": False,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_VARIANT_FALSE_EFFECTS),
        "limitations": list(_LIMITATIONS),
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _alignment_package_document(
    *,
    context: Mapping[str, Any],
    result_snapshot: Mapping[str, Any],
    expected_review_result: Mapping[str, Any],
    variant_alignments: list[dict[str, Any]],
) -> dict[str, Any]:
    all_passed = all(item["alignment_gate_passed"] for item in variant_alignments)
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            **_result_bindings(context),
            "variant_full_song_review_result_sha256": result_snapshot["sha256"],
            "variant_full_song_review_result_document_sha256": expected_review_result[
                "document_sha256"
            ],
        },
        "clock": deepcopy(context["package_report"]["clock"]),
        "reviewed_variant_ids": list(context["eligible_variant_ids"]),
        "aligned_variant_ids": list(context["eligible_variant_ids"]),
        "aligned_variant_count": len(variant_alignments),
        "variant_alignments": variant_alignments,
        "readiness_evidence": {
            "all_eligible_variant_full_song_reviews_complete": True,
            "all_eligible_variant_alignments_complete": True,
            "all_alignment_gates_passed": all_passed,
            "fresh_readiness_reassessment_eligible": True,
            "variant_selected": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "every_reviewed_variant_aligned": True,
            "variants_remain_independent": True,
            "package_order_is_preference": False,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": list(_LIMITATIONS),
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _verify_written_package(root: Path, *, document: Mapping[str, Any]) -> None:
    snapshot = _load_private_json_snapshot(
        root / REPORT_NAME, "private eligible-variant alignment package"
    )
    if snapshot["document"] != document:
        raise ValueError("private eligible-variant alignment package differs")
    alignments = document.get("variant_alignments")
    if (
        not isinstance(alignments, list)
        or len(alignments) != document.get("aligned_variant_count")
        or [item.get("variant_id") for item in alignments]
        != document.get("aligned_variant_ids")
    ):
        raise ValueError("private eligible-variant alignment inventory differs")
    for item in alignments:
        child = _load_private_json_snapshot(
            root / item["report"], "private independent variant alignment result"
        )
        if (
            child["sha256"] != item["report_sha256"]
            or child["document"].get("document_sha256")
            != item["report_document_sha256"]
            or child["document"].get("variant_id") != item["variant_id"]
            or child["document"].get("status") != VARIANT_STATUS
            or child["document"].get("permissions") != _FALSE_PERMISSIONS
            or child["document"].get("effects") != _VARIANT_FALSE_EFFECTS
        ):
            raise ValueError("private independent variant alignment result differs")


def _reverify_alignment_inputs(
    *,
    context: Mapping[str, Any],
    full_song_review_result_path: str | Path,
    result_snapshot: Mapping[str, Any],
    expected_review_result: Mapping[str, Any],
    audio_snapshots: Sequence[Mapping[str, Any]],
) -> None:
    _reverify_completed_reviews(context)
    current = _load_private_json_snapshot(
        full_song_review_result_path,
        "private eligible-variant full-song review result",
    )
    if (
        current["sha256"] != result_snapshot["sha256"]
        or current["document"] != expected_review_result
    ):
        raise ValueError("private eligible-variant full-song review result changed")
    for item in audio_snapshots:
        for role in ("source", "reconstruction"):
            path = item[f"{role}_path"]
            snapshot = item[f"{role}_snapshot"]
            current_audio = _read_pcm24_snapshot(
                path,
                snapshot,
                expected_frames=int(item["expected_frames"]),
                label=f"private eligible-variant alignment {role}",
            )
            if (
                current_audio["sha256"] != snapshot["sha256"]
                or current_audio["pcm24_int32_sequence_sha256"]
                != snapshot["pcm24_int32_sequence_sha256"]
            ):
                raise ValueError("private eligible-variant alignment audio changed")


__all__: tuple[str, ...] = ()
