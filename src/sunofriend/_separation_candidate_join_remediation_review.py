"""Build a blind review for a review-derived follow-up separator candidate.

The immutable v2 candidate is the control.  The follow-up candidate changes
only the ten role-boundary regions named by earlier human evidence.  This
module creates fresh, owner-only listening evidence for those boundaries,
both edges of every new patch and the three complete-song roles.  It never
resolves the sealed A/B identities or changes separator readiness.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_candidate_join_remediation_executor import (
    CANDIDATE_REPORT_NAME,
    CANDIDATES_DIRECTORY,
    REPORT_NAME as EXECUTION_REPORT_NAME,
    SCHEMA as EXECUTION_SCHEMA,
    STATUS_COMPLETE as EXECUTION_STATUS,
    _EFFECTS_COMPLETE as EXECUTION_EFFECTS,
)
from ._separation_candidate_join_remediation_plan import POLICY_ID
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_full_song_executor import (
    _require_private_directory,
    _require_private_regular,
)
from ._separation_full_song_join_remediation_executor_v2 import (
    CANDIDATES_DIRECTORY as V2_CANDIDATES_DIRECTORY,
    REPORT_NAME as V2_EXECUTION_REPORT_NAME,
    SCHEMA as V2_EXECUTION_SCHEMA,
    STATUS as V2_EXECUTION_STATUS,
    _EFFECTS as V2_EXECUTION_EFFECTS,
    _FALSE_PERMISSIONS,
    _read_pcm24_snapshot,
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_join_remediation_plan_v2 import (
    POLICY_ID as V2_POLICY_ID,
)
from ._separation_full_song_join_remediation_review import (
    AUDIO_DIRECTORY,
    HTML_NAME,
    _clip_pair_unit,
    _external_pair_unit,
    _make_private_tree,
    _review_html,
    _write_json_exclusive,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
)


SCHEMA = "sunofriend.private-separation-candidate-join-remediation-review.v1"
STATUS = "unreviewed"
POLICY = "blind-v2-control-versus-review-derived-followup-v1"
REPORT_NAME = "private-separation-candidate-join-remediation-review.json"
ANSWER_KEY_NAME = "private-separation-candidate-join-remediation-answer-key.json"
TARGET_SAMPLE_RATE = 44_100
_ROLES = ("vocals", "instrumental", "reconstruction")
_PATCH_ROLES = frozenset({"vocals", "instrumental"})
_FALSE_EFFECTS = {
    "candidate_accepted": False,
    "candidate_selected": False,
    "preference_inferred": False,
    "publication_state_mutated": False,
    "review_result_resolved": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
    "v2_candidate_mutated": False,
}


def _prepare_private_candidate_join_remediation_review(
    execution_dir: str | Path,
    *,
    v2_execution_dir: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Write one fresh blind control-versus-follow-up listening package."""

    import numpy as np
    import soundfile

    execution = Path(execution_dir).expanduser().absolute()
    v2_execution = Path(v2_execution_dir).expanduser().absolute()
    _require_private_directory(execution, "private follow-up execution root")
    _require_private_directory(v2_execution, "private v2 execution root")
    inputs = _load_verified_inputs(execution, v2_execution)

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"private candidate join-remediation review exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    _require_output_disjoint_from_inputs(
        destination,
        evidence_roots=(execution, v2_execution),
        evidence_paths=(inputs["execution_path"], inputs["candidate_path"], inputs["v2_path"]),
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
        patches = _validated_patches(
            inputs["candidate"],
            total_frames=int(inputs["execution"]["clock"]["frames"]),
            boundary_count=int(inputs["execution"]["clock"]["boundary_count"]),
        )
        for boundary_index, role in sorted(patches):
            patch = patches[(boundary_index, role)]
            boundary_frame = (
                int(patch["patch_start_frame"]) + int(patch["patch_end_frame"])
            ) // 2
            unit, answer = _audible_clip_pair_unit(
                f"boundary-{boundary_index:02d}-{role}",
                kind="boundary_role_pair",
                title=f"Boundary {boundary_index}: {role}",
                focus=(
                    "Which version has the less audible join while preserving the "
                    f"musical continuity of the {role}?"
                ),
                raw_path=inputs["v2_paths"][role],
                candidate_path=inputs["candidate_paths"][role],
                centre_frame=boundary_frame,
                half_frame_options=(2 * TARGET_SAMPLE_RATE,),
                audio_root=audio_root,
                package_root=temporary,
                soundfile=soundfile,
                np=np,
                left_identity="v2_control",
                right_identity="followup_candidate",
            )
            public_units.append(unit)
            answer_units.append(answer)
            for edge_name, edge_frame in (
                ("start", int(patch["patch_start_frame"])),
                ("end", int(patch["patch_end_frame"])),
            ):
                edge, edge_answer = _audible_clip_pair_unit(
                    f"edge-{boundary_index:02d}-{role}-{edge_name}",
                    kind="patch_edge_pair",
                    title=f"Boundary {boundary_index}: {role} patch {edge_name} edge",
                    focus=(
                        "Which version has the cleaner transition at this patch edge? "
                        "Listen for a click, level jump, cut-off sound or sudden tone change."
                    ),
                    raw_path=inputs["v2_paths"][role],
                    candidate_path=inputs["candidate_paths"][role],
                    centre_frame=edge_frame,
                    half_frame_options=tuple(
                        seconds * TARGET_SAMPLE_RATE for seconds in (1, 2, 3, 4)
                    ),
                    audio_root=audio_root,
                    package_root=temporary,
                    soundfile=soundfile,
                    np=np,
                    left_identity="v2_control",
                    right_identity="followup_candidate",
                )
                public_units.append(edge)
                answer_units.append(edge_answer)

        for role in _ROLES:
            unit, answer = _external_pair_unit(
                f"complete-song-{role}",
                role=role,
                raw_path=inputs["v2_paths"][role],
                candidate_path=inputs["candidate_paths"][role],
                review_root=temporary,
                left_identity="v2_control",
                right_identity="followup_candidate",
            )
            public_units.append(unit)
            answer_units.append(answer)

        expected_counts = {
            "boundary_role_pairs": len(patches),
            "patch_edge_pairs": 2 * len(patches),
            "complete_song_pairs": len(_ROLES),
            "total_units": 3 * len(patches) + len(_ROLES),
        }
        if len(public_units) != expected_counts["total_units"]:
            raise ValueError("private follow-up review unit count differs")
        audio_manifest = {
            "schema": "sunofriend.private-separation-candidate-join-remediation-review-audio.v1",
            "units": [
                {"unit_id": unit["unit_id"], "audio": unit["audio"]}
                for unit in public_units
            ],
        }
        audio_manifest_sha256 = hashlib.sha256(
            canonical_json_bytes(audio_manifest)
        ).hexdigest()
        answer_key: dict[str, Any] = {
            "schema": "sunofriend.private-separation-candidate-join-remediation-answer-key.v1",
            "status": "sealed_do_not_open_before_review",
            "nonce": secrets.token_hex(32),
            "bindings": {
                **_input_bindings(inputs),
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
            "policy_id": POLICY,
            "package_commitment": commitment,
            "question": (
                "Did the review-derived follow-up reduce the ten audible v2 joins "
                "without creating worse patch edges or complete-song problems?"
            ),
            "instructions": [
                "Review A and B by listening; neither letter is a recommendation.",
                "Complete all ten boundary comparisons before judging patch edges.",
                "Then hear all three complete-song pairs for broader side effects.",
                "Equivalent, neither and cannot tell are valid outcomes.",
                "Do not open the separate answer key before exporting the review.",
            ],
            "bindings": {
                **_input_bindings(inputs),
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
                "targeted_followup_review_complete": False,
                "followup_complete_song_review_complete": False,
                "followup_alignment_complete": False,
                "original_audible_joins_resolved": False,
                "publication_ready": False,
            },
            "permissions": dict(_FALSE_PERMISSIONS),
            "effects": dict(_FALSE_EFFECTS),
            "limitations": [
                "The v2 candidate is an immutable control; the follow-up remains unselected.",
                "Short-loop sample-RMS matching attenuates only the louder clip and is not LUFS matching.",
                "Complete-song A/B files are unchanged external controls and candidates.",
                "A listening preference does not select, accept or publish a separator.",
            ],
        }
        document["document_sha256"] = _document_sha256(document)
        _write_json_exclusive(temporary / REPORT_NAME, document)
        page = _review_html(document)
        if '"assignment"' in page or ANSWER_KEY_NAME in page:
            raise ValueError("private follow-up review page reveals candidate identities")
        (temporary / HTML_NAME).write_text(page, encoding="utf-8")
        (temporary / HTML_NAME).chmod(0o600)
        _verify_review_tree(temporary, document, soundfile=soundfile)
        _load_verified_inputs(execution, v2_execution)
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


def _audible_clip_pair_unit(
    unit_id: str,
    *,
    kind: str,
    title: str,
    focus: str,
    raw_path: Path,
    candidate_path: Path,
    centre_frame: int,
    half_frame_options: tuple[int, ...],
    audio_root: Path,
    package_root: Path,
    soundfile: Any,
    np: Any,
    left_identity: str,
    right_identity: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Use the shortest centred window where both candidates are audible."""

    if not half_frame_options:
        raise ValueError("private follow-up review window options differ")
    last_error: ValueError | None = None
    for half_frames in half_frame_options:
        try:
            return _clip_pair_unit(
                unit_id,
                kind=kind,
                title=title,
                focus=focus,
                raw_path=raw_path,
                candidate_path=candidate_path,
                centre_frame=centre_frame,
                half_frames=half_frames,
                audio_root=audio_root,
                package_root=package_root,
                soundfile=soundfile,
                np=np,
                left_identity=left_identity,
                right_identity=right_identity,
            )
        except ValueError as error:
            if str(error) != "private remediation review clip is too quiet":
                raise
            last_error = error
    assert last_error is not None
    raise last_error


def _load_verified_inputs(execution: Path, v2_execution: Path) -> dict[str, Any]:
    execution_path = execution / EXECUTION_REPORT_NAME
    candidate_path = execution / CANDIDATES_DIRECTORY / CANDIDATE_REPORT_NAME
    v2_path = v2_execution / V2_EXECUTION_REPORT_NAME
    execution_snapshot = _load_private_json_snapshot(
        execution_path, "private follow-up remediation execution"
    )
    candidate_snapshot = _load_private_json_snapshot(
        candidate_path, "private follow-up remediation candidate"
    )
    v2_snapshot = _load_private_json_snapshot(v2_path, "private v2 execution control")
    current = execution_snapshot["document"]
    candidate = candidate_snapshot["document"]
    v2 = v2_snapshot["document"]
    if (
        current.get("schema") != EXECUTION_SCHEMA
        or current.get("status") != EXECUTION_STATUS
        or current.get("evidence_scope") != "private_development_only"
        or current.get("policy_id") != POLICY_ID
        or current.get("document_sha256") != _document_sha256(current)
        or current.get("permissions") != _FALSE_PERMISSIONS
        or current.get("effects") != EXECUTION_EFFECTS
        or current.get("readiness", {}).get("candidate_audio_complete") is not True
        or current.get("readiness", {}).get("candidate_review_complete") is not False
        or current.get("bindings", {}).get("candidate_report_sha256")
        != candidate_snapshot["sha256"]
        or current.get("bindings", {}).get("candidate_document_sha256")
        != candidate.get("document_sha256")
    ):
        raise ValueError("private follow-up remediation execution differs")
    if (
        candidate.get("schema")
        != "sunofriend.private-separation-candidate-join-remediation-candidates.v1"
        or candidate.get("status") != "candidate_audio_complete_review_required"
        or candidate.get("policy_id") != POLICY_ID
        or candidate.get("document_sha256") != _document_sha256(candidate)
        or candidate.get("permissions") != _FALSE_PERMISSIONS
        or candidate.get("effects") != EXECUTION_EFFECTS
        or candidate.get("readiness", {}).get("candidate_integrity_verified") is not True
        or candidate.get("readiness", {}).get("candidate_review_complete") is not False
    ):
        raise ValueError("private follow-up remediation candidate differs")
    if (
        v2.get("schema") != V2_EXECUTION_SCHEMA
        or v2.get("status") != V2_EXECUTION_STATUS
        or v2.get("evidence_scope") != "private_development_only"
        or v2.get("policy_id") != V2_POLICY_ID
        or v2.get("document_sha256") != _document_sha256(v2)
        or v2.get("permissions") != _FALSE_PERMISSIONS
        or v2.get("effects") != V2_EXECUTION_EFFECTS
        or candidate.get("bindings", {}).get("v2_execution_report_sha256")
        != v2_snapshot["sha256"]
        or candidate.get("bindings", {}).get("v2_execution_document_sha256")
        != v2.get("document_sha256")
        or current.get("clock") != candidate.get("clock")
        or current.get("clock") != v2.get("clock")
    ):
        raise ValueError("private v2 execution control differs")

    total_frames = int(current["clock"]["frames"])
    candidate_paths: dict[str, Path] = {}
    v2_paths: dict[str, Path] = {}
    for role in _ROLES:
        candidate_claim = candidate["artifacts"][role]
        current_claim = current["artifacts"][role]
        v2_claim = v2["artifacts"][role]
        if (
            candidate_claim.get("path") != f"{role}.wav"
            or current_claim.get("path") != f"{CANDIDATES_DIRECTORY}/{role}.wav"
            or v2_claim.get("path") != f"{V2_CANDIDATES_DIRECTORY}/{role}.wav"
            or any(
                current_claim.get(key) != candidate_claim.get(key)
                for key in ("sha256", "bytes", "geometry", "pcm24_int32_sequence_sha256")
            )
        ):
            raise ValueError("private follow-up review audio binding differs")
        candidate_audio = execution / current_claim["path"]
        v2_audio = v2_execution / v2_claim["path"]
        for path, claim, label in (
            (candidate_audio, current_claim, f"private follow-up {role}"),
            (v2_audio, v2_claim, f"private v2 control {role}"),
        ):
            observed = _read_pcm24_snapshot(
                path, claim, expected_frames=total_frames, label=label
            )
            del observed
        candidate_paths[role] = candidate_audio
        v2_paths[role] = v2_audio
    if candidate["bindings"].get("v2_vocals_audio_sha256") != v2["artifacts"]["vocals"]["sha256"]:
        raise ValueError("private v2 vocal control binding differs")
    if candidate["bindings"].get("v2_instrumental_audio_sha256") != v2["artifacts"]["instrumental"]["sha256"]:
        raise ValueError("private v2 instrumental control binding differs")
    return {
        "execution_path": execution_path,
        "candidate_path": candidate_path,
        "v2_path": v2_path,
        "execution_snapshot": execution_snapshot,
        "candidate_snapshot": candidate_snapshot,
        "v2_snapshot": v2_snapshot,
        "execution": current,
        "candidate": candidate,
        "v2": v2,
        "candidate_paths": candidate_paths,
        "v2_paths": v2_paths,
    }


def _input_bindings(inputs: Mapping[str, Any]) -> dict[str, str]:
    return {
        "followup_execution_report_sha256": inputs["execution_snapshot"]["sha256"],
        "followup_execution_document_sha256": inputs["execution"]["document_sha256"],
        "followup_candidate_report_sha256": inputs["candidate_snapshot"]["sha256"],
        "followup_candidate_document_sha256": inputs["candidate"]["document_sha256"],
        "v2_execution_report_sha256": inputs["v2_snapshot"]["sha256"],
        "v2_execution_document_sha256": inputs["v2"]["document_sha256"],
    }


def _validated_patches(
    candidate: Mapping[str, Any], *, total_frames: int, boundary_count: int
) -> dict[tuple[int, str], Mapping[str, Any]]:
    patches = candidate.get("patches")
    summary = candidate.get("summary")
    if (
        not isinstance(patches, list)
        or not isinstance(summary, Mapping)
        or summary.get("patched_boundary_role_pair_count") != len(patches)
        or len(patches) < 1
    ):
        raise ValueError("private follow-up review patch inventory differs")
    grouped: dict[tuple[int, str], Mapping[str, Any]] = {}
    ranges: dict[str, list[tuple[int, int]]] = {role: [] for role in _PATCH_ROLES}
    for patch in patches:
        if not isinstance(patch, Mapping):
            raise ValueError("private follow-up review patch inventory differs")
        boundary_index = patch.get("boundary_index")
        role = patch.get("role")
        start = patch.get("patch_start_frame")
        end = patch.get("patch_end_frame")
        blend = patch.get("edge_blend_frames")
        if (
            not isinstance(boundary_index, int)
            or isinstance(boundary_index, bool)
            or not 1 <= boundary_index <= boundary_count
            or role not in _PATCH_ROLES
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not 0 <= start < end <= total_frames
            or not isinstance(blend, int)
            or isinstance(blend, bool)
            or blend < 1
            or 2 * blend >= end - start
        ):
            raise ValueError("private follow-up review patch bounds differ")
        key = (boundary_index, str(role))
        if key in grouped:
            raise ValueError("private follow-up review patch identity is duplicated")
        if any(start < old_end and old_start < end for old_start, old_end in ranges[str(role)]):
            raise ValueError("private follow-up review patch regions overlap")
        ranges[str(role)].append((start, end))
        grouped[key] = patch
    return grouped


def _verify_review_tree(root: Path, document: Mapping[str, Any], *, soundfile: Any) -> None:
    report = root / REPORT_NAME
    answer = root / ANSWER_KEY_NAME
    page = root / HTML_NAME
    for path in (report, answer, page):
        _require_private_regular(path, "private follow-up review artifact")
    if json.loads(report.read_text(encoding="utf-8")) != document:
        raise ValueError("private follow-up review report differs")
    if _sha256(answer) != document["bindings"]["answer_key_sha256"]:
        raise ValueError("private follow-up review answer key differs")
    page_text = page.read_text(encoding="utf-8")
    referenced = 0
    for unit in document["units"]:
        expected_frames = (
            int(unit["source_window"]["end_frame"])
            - int(unit["source_window"]["start_frame"])
            if unit["source_window"] is not None
            else int(soundfile.info(root / unit["audio"]["A"]["path"]).frames)
        )
        for record in unit["audio"].values():
            path = (root / record["path"]).resolve()
            _require_private_regular(path, "private follow-up review audio")
            if (
                _sha256(path) != record["sha256"]
                or path.stat().st_size != record["bytes"]
                or int(soundfile.info(path).samplerate) != TARGET_SAMPLE_RATE
                or int(soundfile.info(path).channels) != 2
                or int(soundfile.info(path).frames) != expected_frames
                or record["path"] not in page_text
            ):
                raise ValueError("private follow-up review audio differs")
            referenced += 1
    if referenced != 2 * int(document["expected_counts"]["total_units"]):
        raise ValueError("private follow-up review audio reference count differs")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("private follow-up review contains a symbolic link")
        expected = 0o700 if path.is_dir() else 0o600
        if stat.S_IMODE(path.stat().st_mode) != expected:
            raise ValueError("private follow-up review permissions differ")


__all__: tuple[str, ...] = ()
