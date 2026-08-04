"""Build one sealed blind review for the two follow-up remediation variants."""

from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_candidate_followup_remediation_executor import (
    CANDIDATE_REPORT_NAME,
    CANDIDATES_DIRECTORY,
    REPORT_NAME as EXECUTION_REPORT_NAME,
    SCHEMA as EXECUTION_SCHEMA,
    STATUS_COMPLETE as EXECUTION_STATUS,
    WORKER_EXECUTION_DIRECTORY,
    _EFFECTS_COMPLETE as EXECUTION_EFFECTS,
    _execution_document,
    _require_plan_identity,
    _verify_candidates,
)
from ._separation_candidate_join_remediation_review import (
    ANSWER_KEY_NAME,
    REPORT_NAME,
    _audible_clip_pair_unit,
    _load_verified_inputs,
    _verify_review_tree,
)
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_full_song_join_remediation_executor import (
    REPORT_NAME as WORKER_REPORT_NAME,
)
from ._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_join_remediation_review import (
    AUDIO_DIRECTORY,
    HTML_NAME,
    _external_pair_unit,
    _make_private_tree,
    _review_html,
    _write_json_exclusive,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
)


SCHEMA = "sunofriend.private-separation-candidate-followup-variant-review.v1"
STATUS = "unreviewed"
POLICY_ID = "blind-followup-control-versus-two-explicit-variants-v1"
TARGET_SAMPLE_RATE = 44_100
_ROLES = ("vocals", "instrumental", "reconstruction")
_FALSE_EFFECTS = {
    "candidate_accepted": False,
    "candidate_selected": False,
    "preference_inferred": False,
    "publication_state_mutated": False,
    "review_result_resolved": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
}


def _prepare_private_candidate_followup_variant_review(
    plan_path: str | Path,
    *,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Create one fresh owner-only page without revealing variant identities."""

    import numpy as np
    import soundfile

    context = _load_verified_variant_inputs(
        plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"private follow-up variant review exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _require_output_disjoint_from_inputs(
        destination,
        evidence_roots=(
            context["base_root"],
            context["v2_root"],
            context["variant_root"],
        ),
        evidence_paths=(
            context["plan_snapshot"]["path"],
            context["execution_snapshot"]["path"],
            context["candidates_snapshot"]["path"],
            context["inputs"]["execution_snapshot"]["path"],
            context["inputs"]["candidate_snapshot"]["path"],
            context["inputs"]["v2_snapshot"]["path"],
        ),
    )
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=destination.parent)
    )
    temporary.chmod(0o700)
    try:
        audio_root = temporary / AUDIO_DIRECTORY
        audio_root.mkdir(mode=0o700)
        public_units: list[dict[str, Any]] = []
        answer_units: list[dict[str, Any]] = []
        complete_song_assets: dict[Path, Path] = {}
        standard, preserved = _variant_definitions(context["plan"])
        comparison_count = 0
        for window in context["plan"]["windows"]:
            for role, action in sorted(window["role_actions"].items()):
                comparison_count += 1
                _append_region_comparison(
                    public_units,
                    answer_units,
                    set_index=1,
                    comparison_index=comparison_count,
                    window=window,
                    role=role,
                    raw_path=context["base_paths"][role],
                    candidate_path=context["variant_paths"][standard["variant_id"]][
                        role
                    ],
                    right_identity=standard["variant_id"],
                    audio_root=audio_root,
                    package_root=temporary,
                    soundfile=soundfile,
                    np=np,
                )
                if action["action"] == "edge_aware_reinference_and_blend_search":
                    comparison_count += 1
                    _append_region_comparison(
                        public_units,
                        answer_units,
                        set_index=2,
                        comparison_index=comparison_count,
                        window=window,
                        role=role,
                        raw_path=context["base_paths"][role],
                        candidate_path=context["variant_paths"][
                            preserved["variant_id"]
                        ][role],
                        right_identity=preserved["variant_id"],
                        audio_root=audio_root,
                        package_root=temporary,
                        soundfile=soundfile,
                        np=np,
                    )

        for set_index, definition in enumerate((standard, preserved), start=1):
            for role in _ROLES:
                unit, answer = _opaque_external_pair_unit(
                    f"set-{set_index:02d}-complete-song-{role}",
                    role=role,
                    raw_path=context["base_paths"][role],
                    candidate_path=context["variant_paths"][definition["variant_id"]][
                        role
                    ],
                    audio_root=audio_root,
                    asset_cache=complete_song_assets,
                    review_root=temporary,
                    left_identity="followup_control",
                    right_identity=definition["variant_id"],
                )
                unit["title"] = f"Complete song set {set_index}: {role}"
                public_units.append(unit)
                answer_units.append(answer)

        expected_counts = {
            "boundary_role_pairs": comparison_count,
            "patch_edge_pairs": 2 * comparison_count,
            "complete_song_pairs": 2 * len(_ROLES),
            "total_units": 3 * comparison_count + 2 * len(_ROLES),
        }
        if len(public_units) != expected_counts["total_units"]:
            raise ValueError("private follow-up variant review unit count differs")
        audio_manifest = {
            "schema": "sunofriend.private-separation-candidate-followup-variant-review-audio.v1",
            "units": [
                {"unit_id": unit["unit_id"], "audio": unit["audio"]}
                for unit in public_units
            ],
        }
        audio_manifest_sha256 = hashlib.sha256(
            canonical_json_bytes(audio_manifest)
        ).hexdigest()
        answer_key: dict[str, Any] = {
            "schema": "sunofriend.private-separation-candidate-followup-variant-answer-key.v1",
            "status": "sealed_do_not_open_before_review",
            "nonce": secrets.token_hex(32),
            "bindings": {
                **_input_bindings(context),
                "audio_manifest_sha256": audio_manifest_sha256,
            },
            "units": answer_units,
            "permissions": dict(_FALSE_PERMISSIONS),
        }
        answer_key["document_sha256"] = _document_sha256(answer_key)
        _write_json_exclusive(temporary / ANSWER_KEY_NAME, answer_key)
        answer_key_sha256 = _sha256(temporary / ANSWER_KEY_NAME)
        commitment = hashlib.sha256(
            (
                f"{answer_key_sha256}:{answer_key['document_sha256']}:"
                f"{audio_manifest_sha256}"
            ).encode("ascii")
        ).hexdigest()
        document: dict[str, Any] = {
            "schema": SCHEMA,
            "status": STATUS,
            "evidence_scope": "private_development_only",
            "policy_id": POLICY_ID,
            "package_commitment": commitment,
            "question": (
                "Do either of the two explicit second-remediation hypotheses improve "
                "the failed joins and edges without making the complete song worse?"
            ),
            "bindings": {
                **_input_bindings(context),
                "audio_manifest_sha256": audio_manifest_sha256,
                "answer_key_sha256": answer_key_sha256,
                "answer_key_document_sha256": answer_key["document_sha256"],
            },
            "expected_counts": expected_counts,
            "units": public_units,
            "summary": {
                "reviewed_units": 0,
                "total_units": len(public_units),
                "complete": False,
            },
            "readiness": {
                "variant_review_complete": False,
                "variant_preferred": False,
                "original_audible_joins_resolved": False,
                "publication_ready": False,
            },
            "permissions": dict(_FALSE_PERMISSIONS),
            "effects": dict(_FALSE_EFFECTS),
            "limitations": [
                "Candidate A/B identities are randomised independently per unit.",
                "The second edge hypothesis is repeated only where its PCM24 differs from the first.",
                "Short clips attenuate only the louder whole-window sample RMS.",
                "Complete-song files are byte-identical opaque package-local clones.",
                "A listening preference does not select, accept or publish a separator.",
            ],
        }
        document["document_sha256"] = _document_sha256(document)
        _write_json_exclusive(temporary / REPORT_NAME, document)
        page = _review_html(document)
        if any(
            secret in page
            for secret in (
                standard["variant_id"],
                preserved["variant_id"],
                ANSWER_KEY_NAME,
                '"assignment"',
            )
        ):
            raise ValueError("private follow-up variant page reveals identities")
        (temporary / HTML_NAME).write_text(page, encoding="utf-8")
        (temporary / HTML_NAME).chmod(0o600)
        _verify_review_tree(temporary, document, soundfile=soundfile)
        _load_verified_variant_inputs(
            plan_path,
            execution_dir=execution_dir,
            v2_execution_dir=v2_execution_dir,
            variant_execution_dir=variant_execution_dir,
        )
        _make_private_tree(temporary)
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        **document,
        "report": str(destination / REPORT_NAME),
        "review_html": str(destination / HTML_NAME),
        "output_directory": str(destination),
    }


def _append_region_comparison(
    public_units: list[dict[str, Any]],
    answer_units: list[dict[str, Any]],
    *,
    set_index: int,
    comparison_index: int,
    window: Mapping[str, Any],
    role: str,
    raw_path: Path,
    candidate_path: Path,
    right_identity: str,
    audio_root: Path,
    package_root: Path,
    soundfile: Any,
    np: Any,
) -> None:
    action = window["role_actions"][role]
    boundary = int(window["boundary_index"])
    start = int(action["patch_start_frame"])
    end = int(action["patch_end_frame"])
    prefix = f"set-{set_index:02d}-trial-{comparison_index:02d}"
    for kind, suffix, title, centre, focus in (
        (
            "boundary_role_pair",
            "boundary",
            f"Set {set_index}, comparison {comparison_index}: boundary {boundary} {role}",
            (start + end) // 2,
            f"Which version has the less audible join while preserving {role} continuity?",
        ),
        (
            "patch_edge_pair",
            "start-edge",
            f"Set {set_index}, comparison {comparison_index}: start edge {role}",
            start,
            "Which version has the cleaner start transition without a click, jump or cut-off?",
        ),
        (
            "patch_edge_pair",
            "end-edge",
            f"Set {set_index}, comparison {comparison_index}: end edge {role}",
            end,
            "Which version has the cleaner end transition without a click, jump or cut-off?",
        ),
    ):
        unit, answer = _audible_clip_pair_unit(
            f"{prefix}-{boundary:02d}-{role}-{suffix}",
            kind=kind,
            title=title,
            focus=focus,
            raw_path=raw_path,
            candidate_path=candidate_path,
            centre_frame=centre,
            half_frame_options=tuple(
                seconds * TARGET_SAMPLE_RATE for seconds in (1, 2, 3, 4)
            ),
            audio_root=audio_root,
            package_root=package_root,
            soundfile=soundfile,
            np=np,
            left_identity="followup_control",
            right_identity=right_identity,
        )
        public_units.append(unit)
        answer_units.append(answer)


def _opaque_external_pair_unit(
    unit_id: str,
    *,
    role: str,
    raw_path: Path,
    candidate_path: Path,
    audio_root: Path,
    asset_cache: dict[Path, Path],
    review_root: Path,
    left_identity: str,
    right_identity: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Expose complete songs through sealed package-local names without copying."""

    unit, answer = _external_pair_unit(
        unit_id,
        role=role,
        raw_path=raw_path,
        candidate_path=candidate_path,
        review_root=review_root,
        left_identity=left_identity,
        right_identity=right_identity,
    )
    identities = {left_identity: raw_path, right_identity: candidate_path}
    for slot, identity in answer["assignment"].items():
        source = identities[identity].resolve(strict=True)
        destination = asset_cache.get(source)
        if destination is None:
            destination = audio_root / f"complete-song-asset-{len(asset_cache) + 1:02d}.wav"
            _clone_or_copy_private_regular(source, destination)
            asset_cache[source] = destination
        unit["audio"][slot] = {
            "path": destination.relative_to(review_root).as_posix(),
            "sha256": _sha256(destination),
            "bytes": destination.stat().st_size,
        }
    unit["level_policy"] = "unchanged-full-song-files-package-local-byte-clones"
    return unit, answer


def _clone_or_copy_private_regular(source: Path, destination: Path) -> None:
    """Create an independent inode, using an APFS copy-on-write clone on macOS."""

    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        clonefile = libc.clonefile
        clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        clonefile.restype = ctypes.c_int
        result = clonefile(os.fsencode(source), os.fsencode(destination), 0)
        if result != 0:
            error_number = ctypes.get_errno()
            raise OSError(
                error_number,
                os.strerror(error_number),
                str(destination),
            )
    else:
        with source.open("rb") as input_stream, destination.open("xb") as output_stream:
            shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
    destination.chmod(0o600)


def _variant_definitions(
    plan: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    definitions = plan["protocol"]["candidate_variants"]
    standard = [
        item for item in definitions if item["failed_edge_source"] == "shifted_context_worker"
    ]
    preserved = [
        item
        for item in definitions
        if item["failed_edge_source"] == "exact_followup_candidate_patch"
    ]
    if len(standard) != 1 or len(preserved) != 1:
        raise ValueError("private follow-up variant definitions differ")
    return standard[0], preserved[0]


def _load_verified_variant_inputs(
    plan_path: str | Path,
    *,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
) -> dict[str, Any]:
    plan_snapshot = _load_private_json_snapshot(
        plan_path, "private follow-up variant plan"
    )
    plan = plan_snapshot["document"]
    _require_plan_identity(plan)
    base_root = Path(execution_dir).expanduser().absolute()
    v2_root = Path(v2_execution_dir).expanduser().absolute()
    variant_root = Path(variant_execution_dir).expanduser().absolute()
    inputs = _load_verified_inputs(base_root, v2_root)
    execution_snapshot = _load_private_json_snapshot(
        variant_root / EXECUTION_REPORT_NAME,
        "private follow-up variant execution",
    )
    candidates_snapshot = _load_private_json_snapshot(
        variant_root / CANDIDATES_DIRECTORY / CANDIDATE_REPORT_NAME,
        "private follow-up variant candidates",
    )
    worker_root = variant_root / WORKER_EXECUTION_DIRECTORY
    worker_state = _load_private_json_snapshot(
        worker_root / WORKER_REPORT_NAME,
        "private follow-up variant worker execution",
    )["document"]
    candidates = _verify_candidates(
        variant_root / CANDIDATES_DIRECTORY,
        plan=plan,
        plan_snapshot=plan_snapshot,
        inputs=inputs,
        worker_root=worker_root,
        worker_state=worker_state,
    )
    expected_execution = _execution_document(
        plan=plan,
        plan_snapshot=plan_snapshot,
        inputs=inputs,
        destination=variant_root,
        worker_root=worker_root,
        worker_state=worker_state,
        candidates=candidates,
    )
    execution = execution_snapshot["document"]
    if (
        execution != expected_execution
        or execution.get("schema") != EXECUTION_SCHEMA
        or execution.get("status") != EXECUTION_STATUS
        or execution.get("effects") != EXECUTION_EFFECTS
        or execution.get("permissions") != _FALSE_PERMISSIONS
        or candidates_snapshot["document"] != candidates
        or execution["bindings"]["candidate_report_sha256"]
        != candidates_snapshot["sha256"]
    ):
        raise ValueError("private follow-up variant execution evidence differs")
    variant_paths: dict[str, dict[str, Path]] = {}
    for variant in candidates["variants"]:
        variant_paths[variant["variant_id"]] = {
            role: variant_root
            / CANDIDATES_DIRECTORY
            / variant["variant_id"]
            / variant["artifacts"][role]["path"]
            for role in _ROLES
        }
    if set(variant_paths) != {
        item["variant_id"] for item in plan["protocol"]["candidate_variants"]
    }:
        raise ValueError("private follow-up variant path inventory differs")
    return {
        "plan_snapshot": plan_snapshot,
        "plan": plan,
        "inputs": inputs,
        "execution_snapshot": execution_snapshot,
        "execution": execution,
        "candidates_snapshot": candidates_snapshot,
        "candidates": candidates,
        "base_root": base_root,
        "v2_root": v2_root,
        "variant_root": variant_root,
        "base_paths": inputs["candidate_paths"],
        "variant_paths": variant_paths,
    }


def _input_bindings(context: Mapping[str, Any]) -> dict[str, str]:
    return {
        "followup_remediation_plan_sha256": context["plan_snapshot"]["sha256"],
        "followup_remediation_plan_document_sha256": context["plan"][
            "document_sha256"
        ],
        "variant_execution_report_sha256": context["execution_snapshot"]["sha256"],
        "variant_execution_document_sha256": context["execution"]["document_sha256"],
        "variant_candidate_report_sha256": context["candidates_snapshot"]["sha256"],
        "variant_candidate_document_sha256": context["candidates"]["document_sha256"],
        "followup_control_report_sha256": context["inputs"]["candidate_snapshot"][
            "sha256"
        ],
        "v2_execution_report_sha256": context["inputs"]["v2_snapshot"]["sha256"],
    }


__all__: tuple[str, ...] = ()
