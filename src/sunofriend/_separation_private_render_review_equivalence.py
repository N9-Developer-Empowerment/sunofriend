"""Bind prior human review to a sample-equivalent private render.

The policy is deliberately narrow: the canonical source and clock must match
exactly, and every generated PCM24 sample may differ by no more than one
least-significant bit. The record says that prior listening evidence remains
applicable; it does not claim a fresh audition, accept a separator, or enable
an import or product route.
"""

from __future__ import annotations

from copy import deepcopy
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_full_song_executor import (
    _require_private_directory,
    _require_private_regular,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_review import (
    _load_stitch_report,
    _resolve_private_separation_full_song_review,
    _verify_stitch_audio,
)
from ._separation_full_song_stitch import REPORT_NAME as STITCH_REPORT_NAME
from ._separation_private_developer_review_package import (
    REPORT_NAME as PACKAGE_REPORT_NAME,
    SCHEMA as PACKAGE_SCHEMA,
    STATUS as PACKAGE_STATUS,
    STITCH_DIRECTORY,
    _FALSE_PERMISSIONS,
)
from ._separation_song_disjoint_private_pilot import (
    _load_verified_unreviewed_seed,
)


SCHEMA = "sunofriend.private-separation-render-review-equivalence.v1"
STATUS = "prior_review_applies_to_pcm24_equivalent_render_no_activation"
POLICY_ID = "exact-source-clock-and-one-pcm24-lsb-equivalence-v1"
REPORT_NAME = "private-separation-render-review-equivalence.json"
MAXIMUM_PCM24_LSB_DIFFERENCE = 1
_ROLES = ("vocals", "instrumental", "reconstruction")
_FALSE_EQUIVALENCE_PERMISSIONS = {
    **_FALSE_PERMISSIONS,
    "prior_review_evidence_may_be_considered": True,
}


def _bind_private_separation_render_review_equivalence(
    reviewed_export_path: str | Path,
    *,
    reviewed_package_dir: str | Path,
    candidate_package_report_path: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Write one review-equivalence record without changing either package."""

    reviewed_export = Path(reviewed_export_path).expanduser().absolute()
    _require_private_regular(reviewed_export, "review-equivalence browser export")
    reviewed_package = Path(reviewed_package_dir).expanduser().absolute()
    _require_private_directory(reviewed_package, "review-equivalence reviewed package")
    reviewed_stitch_path = reviewed_package / STITCH_REPORT_NAME
    reviewed_stitch = _load_stitch_report(reviewed_stitch_path)
    _verify_stitch_audio(reviewed_package, reviewed_stitch)

    candidate = _load_candidate_package(candidate_package_report_path)
    output = Path(out).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(f"review-equivalence filename must be {REPORT_NAME}")
    _prepare_output_parent(output.parent)
    if os.path.lexists(output):
        raise FileExistsError(f"review-equivalence result exists: {output}")
    _require_output_disjoint(
        output,
        reviewed_export=reviewed_export,
        reviewed_package=reviewed_package,
        candidate_stitch_root=candidate["stitch_root"],
    )

    with tempfile.TemporaryDirectory(prefix="sunofriend-review-equivalence-") as name:
        temporary = Path(name)
        temporary.chmod(0o700)
        resolved = _resolve_private_separation_full_song_review(
            reviewed_export,
            package_dir=reviewed_package,
            out=temporary / "verified-prior-review.json",
        )
        prior_review = {key: value for key, value in resolved.items() if key != "report"}

    candidate_stitch = candidate["stitch"]
    if (
        reviewed_stitch["clock"] != candidate_stitch["clock"]
        or reviewed_stitch["artifacts"]["source"]["sha256"]
        != candidate_stitch["artifacts"]["source"]["sha256"]
        or reviewed_stitch["artifacts"]["source"]["bytes"]
        != candidate_stitch["artifacts"]["source"]["bytes"]
    ):
        raise ValueError("review-equivalence source or clock differs")

    comparisons: dict[str, Any] = {}
    for role in _ROLES:
        reviewed_audio = reviewed_package / reviewed_stitch["artifacts"][role]["path"]
        candidate_audio = (
            candidate["stitch_root"] / candidate_stitch["artifacts"][role]["path"]
        )
        comparison = _compare_pcm24_audio(reviewed_audio, candidate_audio)
        if comparison["maximum_absolute_pcm24_lsb_difference"] > MAXIMUM_PCM24_LSB_DIFFERENCE:
            raise ValueError("review-equivalence PCM24 difference exceeds policy")
        comparisons[role] = {
            **comparison,
            "reviewed_audio_sha256": reviewed_stitch["artifacts"][role]["sha256"],
            "candidate_audio_sha256": candidate_stitch["artifacts"][role]["sha256"],
        }

    document = _equivalence_document(
        reviewed_export=reviewed_export,
        reviewed_stitch_path=reviewed_stitch_path,
        reviewed_stitch=reviewed_stitch,
        prior_review=prior_review,
        candidate=candidate,
        comparisons=comparisons,
    )
    rechecked = _load_candidate_package(candidate_package_report_path)
    if _candidate_identity(rechecked) != _candidate_identity(candidate):
        raise ValueError("review-equivalence candidate evidence changed")
    _write_json_exclusive(output, document)
    return {**document, "report": str(output)}


def _load_candidate_package(value: str | Path) -> dict[str, Any]:
    snapshot = _load_private_json_snapshot(value, "developer review-package report")
    document = snapshot["document"]
    if (
        snapshot["path"].name != PACKAGE_REPORT_NAME
        or document.get("schema") != PACKAGE_SCHEMA
        or document.get("status") != PACKAGE_STATUS
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("readiness", {}).get("playable_review_package_complete") is not True
        or document.get("readiness", {}).get("human_review_complete") is not False
    ):
        raise ValueError("developer review-package report differs")
    root = snapshot["path"].parent
    _require_private_directory(root, "developer review-package root")
    stitch_root = root / STITCH_DIRECTORY
    _require_private_directory(stitch_root, "developer review-package stitch")
    stitch_path = stitch_root / STITCH_REPORT_NAME
    stitch = _load_stitch_report(stitch_path)
    _verify_stitch_audio(stitch_root, stitch)
    seed, seed_sha256 = _load_verified_unreviewed_seed(stitch_root, stitch)
    bindings = document["bindings"]
    if (
        bindings.get("stitch_report_sha256") != _sha256(stitch_path)
        or bindings.get("stitch_document_sha256") != stitch["document_sha256"]
        or bindings.get("review_seed_sha256") != seed_sha256
        or bindings.get("review_package_commitment") != seed["package_commitment"]
    ):
        raise ValueError("developer review-package stitch binding differs")
    return {
        **snapshot,
        "root": root,
        "stitch_root": stitch_root,
        "stitch_path": stitch_path,
        "stitch": stitch,
        "seed_sha256": seed_sha256,
    }


def _compare_pcm24_audio(reviewed: Path, candidate: Path) -> dict[str, Any]:
    import numpy as np
    import soundfile

    _require_private_regular(reviewed, "review-equivalence reviewed audio")
    _require_private_regular(candidate, "review-equivalence candidate audio")
    different = 0
    total = 0
    maximum = 0
    squared_lsb_sum = 0.0
    with soundfile.SoundFile(reviewed) as left, soundfile.SoundFile(candidate) as right:
        left_geometry = (left.samplerate, left.channels, left.frames, left.subtype)
        right_geometry = (right.samplerate, right.channels, right.frames, right.subtype)
        if left_geometry != right_geometry or left.subtype != "PCM_24":
            raise ValueError("review-equivalence PCM24 geometry differs")
        while True:
            left_block = left.read(262_144, dtype="int32", always_2d=True)
            right_block = right.read(262_144, dtype="int32", always_2d=True)
            if left_block.shape != right_block.shape:
                raise ValueError("review-equivalence PCM24 block geometry differs")
            if not left_block.size:
                break
            delta = left_block.astype(np.int64) - right_block.astype(np.int64)
            if np.any(delta % 256):
                raise ValueError("review-equivalence PCM24 sample encoding differs")
            lsb_delta = delta // 256
            absolute = np.abs(lsb_delta)
            different += int(np.count_nonzero(absolute))
            total += int(absolute.size)
            maximum = max(maximum, int(np.max(absolute)))
            squared_lsb_sum += float(np.sum(lsb_delta.astype(np.float64) ** 2))
    if total < 1:
        raise ValueError("review-equivalence audio is empty")
    return {
        "sample_rate": left_geometry[0],
        "channels": left_geometry[1],
        "frames": left_geometry[2],
        "sample_subtype": left_geometry[3],
        "total_sample_values": total,
        "different_sample_values": different,
        "different_sample_fraction": round(different / total, 12),
        "maximum_absolute_pcm24_lsb_difference": maximum,
        "rms_pcm24_lsb_difference": round(math.sqrt(squared_lsb_sum / total), 12),
    }


def _equivalence_document(
    *,
    reviewed_export: Path,
    reviewed_stitch_path: Path,
    reviewed_stitch: Mapping[str, Any],
    prior_review: Mapping[str, Any],
    candidate: Mapping[str, Any],
    comparisons: Mapping[str, Any],
) -> dict[str, Any]:
    candidate_document = candidate["document"]
    candidate_stitch = candidate["stitch"]
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "review_export_sha256": _sha256(reviewed_export),
            "reviewed_stitch_report_sha256": _sha256(reviewed_stitch_path),
            "reviewed_stitch_document_sha256": reviewed_stitch["document_sha256"],
            "prior_review_document_sha256": prior_review["document_sha256"],
            "candidate_package_report_sha256": candidate["sha256"],
            "candidate_package_document_sha256": candidate_document["document_sha256"],
            "candidate_stitch_report_sha256": _sha256(candidate["stitch_path"]),
            "candidate_stitch_document_sha256": candidate_stitch["document_sha256"],
            "source_audio_sha256": candidate_stitch["artifacts"]["source"]["sha256"],
            "candidate_review_package_commitment": candidate_document["bindings"]["review_package_commitment"],
        },
        "clock": deepcopy(candidate_stitch["clock"]),
        "thresholds": {
            "exact_source_audio_required": True,
            "exact_clock_required": True,
            "maximum_absolute_pcm24_lsb_difference": MAXIMUM_PCM24_LSB_DIFFERENCE,
        },
        "comparisons": deepcopy(dict(comparisons)),
        "prior_human_review": {
            "fresh_audition_of_candidate_exact_bytes": False,
            "review_evidence_applies_under_equivalence_policy": True,
            "full_song": deepcopy(prior_review["full_song"]),
            "boundary_summary": deepcopy(prior_review["boundary_summary"]),
            "boundaries": deepcopy(prior_review["boundaries"]),
        },
        "readiness": {
            "prior_human_review_verified": True,
            "candidate_render_pcm24_equivalence_verified": True,
            "candidate_review_evidence_available": True,
            "fresh_candidate_audition_completed": False,
            "reviewed_output_import_assessed": False,
            "private_output_import_permitted": False,
            "product_integration_permitted": False,
            "public_release_permitted": False,
        },
        "permissions": dict(_FALSE_EQUIVALENCE_PERMISSIONS),
        "effects": {
            "audio_created_or_mutated": False,
            "human_review_created_or_mutated": False,
            "model_run": False,
            "product_contract_mutated": False,
            "review_equivalence_record_created": True,
            "separator_selected_or_accepted": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "This record transfers prior listening evidence; it does not claim a fresh audition of the candidate bytes.",
            "One-LSB PCM24 equivalence is a bounded sample comparison, not separator accuracy or musical quality ground truth.",
            "The prior boundary ratings remain diagnostics and are not reinterpreted.",
            "No reviewed-stem import, Simple, Studio, TUI, source-graph, download or publication route is enabled.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _prepare_output_parent(parent: Path) -> None:
    if not os.path.lexists(parent):
        parent.mkdir(parents=True, mode=0o700)
        parent.chmod(0o700)
    _require_private_directory(parent, "review-equivalence result root")


def _candidate_identity(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        str(candidate["sha256"]),
        str(candidate["document"]["document_sha256"]),
        str(_sha256(candidate["stitch_path"])),
        str(candidate["stitch"]["document_sha256"]),
        str(candidate["seed_sha256"]),
    )


def _require_output_disjoint(
    output: Path,
    *,
    reviewed_export: Path,
    reviewed_package: Path,
    candidate_stitch_root: Path,
) -> None:
    if (
        output == reviewed_export
        or reviewed_package == output
        or reviewed_package in output.parents
        or candidate_stitch_root == output
        or candidate_stitch_root in output.parents
    ):
        raise ValueError("review-equivalence output overlaps audio evidence")


__all__: tuple[str, ...] = ()
