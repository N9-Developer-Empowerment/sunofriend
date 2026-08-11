"""Record the musical outcome of one recovered full-song six-role review.

The outcome is deliberately separate from profile qualification.  It reduces
only already-validated JSON evidence, never opens audio, and preserves the
recovery report's missing guitar receipt and resource measurements.
"""

from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from ._private_atomic_directory import (
    open_absolute_directory_nofollow,
    rename_directory_no_replace_at,
    require_safe_directory_entry_name,
)
from .separation_fine_stem_full_song_execution_review import (
    review_document_sha256,
    validate_full_song_review,
)
from .separation_fine_stem_full_song_plan_contract import (
    validate_fine_stem_full_song_plan,
)
from .separation_fine_stem_full_song_recovery import validate_recovery_report


OUTCOME_SCHEMA = "sunofriend.fine-stem-full-song-six-role-outcome.v1"
OUTCOME_STATUS = (
    "private_full_song_six_role_listening_evidence_recorded_resource_gate_incomplete"
)
OUTCOME_DIRECTORY_NAME = "fine-stem-full-song-six-role-outcome-v1"
OUTCOME_FILE_NAME = "FULL-SONG-SIX-ROLE-OUTCOME.json"
ROLE_ORDER = ("vocals", "drums", "bass", "synth", "guitar", "other")

_CATASTROPHIC_VALUES = (
    "not_tested",
    "no_catastrophic_defect",
    "catastrophic_defect",
    "cannot_tell",
)
_USEFULNESS_VALUES = (
    "not_tested",
    "cannot_tell",
    "not_useful",
    "partly_useful",
    "useful",
)
_ISSUE_VALUES = ("not_tested", "cannot_tell", "none", "some", "severe")
_ISSUE_FIELDS = (
    "bleed",
    "missing_content",
    "artefacts",
    "timing_or_join_problems",
)
_MAX_JSON_BYTES = 16 * 1024 * 1024


def outcome_document_sha256(value: Mapping[str, Any]) -> str:
    """Return the canonical digest while excluding its own field."""

    payload = {key: item for key, item in value.items() if key != "document_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _counts(values: list[str], allowed: tuple[str, ...]) -> dict[str, int]:
    observed = Counter(values)
    return {value: observed.get(value, 0) for value in allowed}


def _role_summary(role: str, cases: list[Mapping[str, Any]]) -> dict[str, Any]:
    scored = [case for case in cases if role in case["role_usefulness"]]
    usefulness = _counts(
        [case["role_usefulness"][role] for case in scored],
        _USEFULNESS_VALUES,
    )
    issue_counts = {
        field: _counts(
            [case["issues"][role][field] for case in scored],
            _ISSUE_VALUES,
        )
        for field in _ISSUE_FIELDS
    }
    return {
        "role": role,
        "scoring_basis": (
            "all reviewed songs"
            if role in {"vocals", "drums", "bass", "other"}
            else "confirmed-present source cases only"
        ),
        "scored_case_count": len(scored),
        "usefulness_counts": usefulness,
        "issue_counts": issue_counts,
        "useful_or_partly_useful_count": (
            usefulness["useful"] + usefulness["partly_useful"]
        ),
        "all_scored_cases_useful": usefulness["useful"] == len(scored),
    }


def build_full_song_six_role_outcome(
    *,
    plan: Mapping[str, Any],
    recovery_request: Mapping[str, Any],
    recovery_report: Mapping[str, Any],
    review: Mapping[str, Any],
    review_file: Mapping[str, Any],
) -> dict[str, Any]:
    """Reduce one completed review without qualifying or selecting anything."""

    validated_plan = validate_fine_stem_full_song_plan(plan)
    objective = validate_recovery_report(
        recovery_report,
        validated_plan,
        recovery_request,
    )
    listening = validate_full_song_review(review, objective, validated_plan)
    if listening["status"] != "human_listening_complete_no_selection":
        raise ValueError("full-song six-role listening is incomplete")
    if review.get("document_sha256") != listening["document_sha256"]:
        raise ValueError("full-song six-role review is not sealed")
    if (
        not isinstance(review_file.get("bytes"), int)
        or isinstance(review_file.get("bytes"), bool)
        or review_file["bytes"] <= 0
        or not isinstance(review_file.get("sha256"), str)
        or len(review_file["sha256"]) != 64
        or any(
            character not in "0123456789abcdef" for character in review_file["sha256"]
        )
    ):
        raise ValueError("full-song six-role review file identity differs")
    if (
        objective["full_objective_qualification"] is not False
        or objective["resources"]["guitar_resource_gate_complete"] is not False
        or objective["resources"]["full_resource_gate_complete"] is not False
        or objective["resources"]["within_known_ceilings"] is not None
        or objective["workers"]["guitar"]["result_receipt_persisted"] is not False
        or objective["workers"]["guitar"]["guard_counters_persisted"] is not False
        or objective["workers"]["guitar"]["peak_memory_bytes"] is not None
    ):
        raise ValueError("full-song recovery qualification boundary differs")

    cases = listening["cases"]
    catastrophic = _counts(
        [case["catastrophic_result"] for case in cases],
        _CATASTROPHIC_VALUES,
    )
    overall = _counts(
        [case["overall_usefulness"] for case in cases],
        _USEFULNESS_VALUES,
    )
    roles = [_role_summary(role, cases) for role in ROLE_ORDER]
    all_roles_useful = all(role["all_scored_cases_useful"] for role in roles)
    positive = (
        catastrophic["catastrophic_defect"] == 0
        and catastrophic["no_catastrophic_defect"] == len(cases)
        and overall["useful"] == len(cases)
        and all_roles_useful
    )
    specialist_missing_content = sum(
        role["issue_counts"]["missing_content"]["some"]
        + role["issue_counts"]["missing_content"]["severe"]
        for role in roles
        if role["role"] in {"synth", "guitar"}
    )
    specialist_missing_by_role = {
        role["role"]: (
            role["issue_counts"]["missing_content"]["some"]
            + role["issue_counts"]["missing_content"]["severe"]
        )
        for role in roles
        if role["role"] in {"synth", "guitar"}
    }
    specialist_limitation = (
        "confirmed-present specialist missing-content ratings: "
        + ", ".join(
            f"{role} {specialist_missing_by_role[role]}" for role in ("synth", "guitar")
        )
    )
    next_bounded_step = (
        "investigate the recorded catastrophic defect before any further "
        "objective run; do not activate, select or retry automatically"
        if catastrophic["catastrophic_defect"]
        else (
            "define a fresh objective-only repaired guitar-worker run to capture "
            "the missing receipt and memory evidence; keep private Studio "
            "integration and public admission as separate decisions"
        )
    )

    document: dict[str, Any] = {
        "schema": OUTCOME_SCHEMA,
        "document_sha256": "",
        "status": OUTCOME_STATUS,
        "plan_sha256": validated_plan["document_sha256"],
        "recovery_request_sha256": objective["recovery_request_sha256"],
        "recovery_report_sha256": objective["report_sha256"],
        "review_document_sha256": listening["document_sha256"],
        "review_file": {
            "bytes": review_file["bytes"],
            "sha256": review_file["sha256"],
        },
        "review_snapshot": copy.deepcopy(listening),
        "musical_result": (
            "catastrophic_private_full_song_six_role_evidence"
            if catastrophic["catastrophic_defect"]
            else (
                "positive_private_full_song_six_role_evidence_with_"
                "specialist_missing_content_reported"
                if positive and specialist_missing_content
                else (
                    "positive_private_full_song_six_role_evidence"
                    if positive
                    else "mixed_private_full_song_six_role_evidence"
                )
            )
        ),
        "review_summary": {
            "reviewed_song_count": len(cases),
            "played_item_count": sum(len(case["played_items"]) for case in cases),
            "confirmed_window_replay_count": sum(
                len(case["confirmed_windows_played"]) for case in cases
            ),
            "all_songs_fully_played": all(case["listened"] for case in cases),
            "all_confirmed_windows_replayed": all(
                case["confirmed_windows_replayed"] for case in cases
            ),
            "catastrophic_counts": catastrophic,
            "overall_usefulness_counts": overall,
            "roles": roles,
            "all_scored_roles_useful": all_roles_useful,
            "specialist_missing_content_rating_count": specialist_missing_content,
            "cannot_tell_or_not_tested_rating_count": sum(
                role["usefulness_counts"]["cannot_tell"]
                + role["usefulness_counts"]["not_tested"]
                for role in roles
            ),
        },
        "objective_gaps": {
            "full_objective_qualification": False,
            "guitar_worker_result_receipt_persisted": False,
            "guitar_guard_counters_persisted": False,
            "guitar_peak_memory_bytes": None,
            "guitar_resource_gate_complete": False,
            "full_resource_gate_complete": False,
            "within_known_ceilings": None,
        },
        "decisions": {
            "private_six_role_audio_evidence": "retain",
            "public_six_role_profile": "not_qualified",
            "public_core_four_profile": "unchanged",
            "next_bounded_step": next_bounded_step,
        },
        "known_limitations": [
            specialist_limitation,
            (
                "three owner-authorised songs are limited private evidence, "
                "not broad catalogue validation"
            ),
            (
                "the missing guitar worker receipt, guard counters and peak "
                "memory prevent objective and resource qualification"
            ),
            "exact reconstruction proves accounting, not separation accuracy",
        ],
        "boundaries": {
            "private_review_only": True,
            "full_objective_qualification": False,
            "resource_qualification": False,
            "profile_qualification": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
            "automatic_retry": False,
            "poor_feedback_disables_core_four": False,
        },
        "effects": {
            "input_json_reads": 4,
            "output_json_writes": 1,
            "audio_reads": 0,
            "audio_writes": 0,
            "checkpoint_loads": 0,
            "model_constructions": 0,
            "model_loads": 0,
            "inference_attempts": 0,
            "network_attempts": 0,
        },
    }
    document["document_sha256"] = outcome_document_sha256(document)
    return document


def validate_full_song_six_role_outcome(
    value: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    recovery_request: Mapping[str, Any],
    recovery_report: Mapping[str, Any],
    review: Mapping[str, Any],
    review_file: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one self-contained private outcome document."""

    document = copy.deepcopy(dict(value))
    expected_keys = {
        "schema",
        "document_sha256",
        "status",
        "plan_sha256",
        "recovery_request_sha256",
        "recovery_report_sha256",
        "review_document_sha256",
        "review_file",
        "review_snapshot",
        "musical_result",
        "review_summary",
        "objective_gaps",
        "decisions",
        "known_limitations",
        "boundaries",
        "effects",
    }
    if set(document) != expected_keys:
        raise ValueError("full-song six-role outcome fields differ")
    if (
        document["schema"] != OUTCOME_SCHEMA
        or document["status"] != OUTCOME_STATUS
        or document["document_sha256"] != outcome_document_sha256(document)
    ):
        raise ValueError("full-song six-role outcome identity differs")
    for key in (
        "plan_sha256",
        "recovery_request_sha256",
        "recovery_report_sha256",
        "review_document_sha256",
    ):
        digest = document.get(key)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("full-song six-role outcome binding differs")
    review_file_identity = document.get("review_file", {})
    if (
        set(review_file_identity) != {"bytes", "sha256"}
        or not isinstance(review_file_identity.get("bytes"), int)
        or isinstance(review_file_identity.get("bytes"), bool)
        or review_file_identity["bytes"] <= 0
        or not isinstance(review_file_identity.get("sha256"), str)
        or len(review_file_identity["sha256"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in review_file_identity["sha256"]
        )
    ):
        raise ValueError("full-song six-role outcome review file differs")
    snapshot = document.get("review_snapshot", {})
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("document_sha256") != document.get("review_document_sha256")
        or review_document_sha256(snapshot) != snapshot.get("document_sha256")
        or snapshot.get("status") != "human_listening_complete_no_selection"
        or snapshot.get("boundaries")
        != {
            "review_selects_source": False,
            "review_starts_midi": False,
            "review_activates_profile": False,
            "poor_feedback_disables_core_four": False,
            "unconfirmed_specialist_roles_scored": False,
            "audio_included": False,
            "paths_or_filenames_included": False,
            "telemetry_included": False,
        }
    ):
        raise ValueError("full-song six-role outcome review snapshot differs")
    summary = document.get("review_summary", {})
    if set(summary) != {
        "reviewed_song_count",
        "played_item_count",
        "confirmed_window_replay_count",
        "all_songs_fully_played",
        "all_confirmed_windows_replayed",
        "catastrophic_counts",
        "overall_usefulness_counts",
        "roles",
        "all_scored_roles_useful",
        "specialist_missing_content_rating_count",
        "cannot_tell_or_not_tested_rating_count",
    }:
        raise ValueError("full-song six-role outcome summary fields differ")
    roles = summary.get("roles", [])
    catastrophic = summary.get("catastrophic_counts", {})
    overall = summary.get("overall_usefulness_counts", {})
    if (
        summary.get("reviewed_song_count") != 3
        or summary.get("played_item_count") != 24
        or summary.get("confirmed_window_replay_count") != 4
        or summary.get("all_songs_fully_played") is not True
        or summary.get("all_confirmed_windows_replayed") is not True
        or [role.get("role") for role in roles] != list(ROLE_ORDER)
        or [role.get("scored_case_count") for role in roles] != [3, 3, 3, 2, 2, 3]
        or set(catastrophic) != set(_CATASTROPHIC_VALUES)
        or any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for count in catastrophic.values()
        )
        or sum(catastrophic.values()) != 3
        or set(overall) != set(_USEFULNESS_VALUES)
        or any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for count in overall.values()
        )
        or sum(overall.values()) != 3
    ):
        raise ValueError("full-song six-role outcome review summary differs")
    for role in roles:
        if set(role) != {
            "role",
            "scoring_basis",
            "scored_case_count",
            "usefulness_counts",
            "issue_counts",
            "useful_or_partly_useful_count",
            "all_scored_cases_useful",
        }:
            raise ValueError("full-song six-role outcome role fields differ")
        count = role["scored_case_count"]
        usefulness = role.get("usefulness_counts", {})
        issues = role.get("issue_counts", {})
        expected_basis = (
            "all reviewed songs"
            if role["role"] in {"vocals", "drums", "bass", "other"}
            else "confirmed-present source cases only"
        )
        if (
            role.get("scoring_basis") != expected_basis
            or set(usefulness) != set(_USEFULNESS_VALUES)
            or any(
                not isinstance(rating_count, int)
                or isinstance(rating_count, bool)
                or rating_count < 0
                for rating_count in usefulness.values()
            )
            or sum(usefulness.values()) != count
            or set(issues) != set(_ISSUE_FIELDS)
            or any(
                set(ratings) != set(_ISSUE_VALUES) or sum(ratings.values()) != count
                for ratings in issues.values()
            )
            or any(
                not isinstance(rating_count, int)
                or isinstance(rating_count, bool)
                or rating_count < 0
                for ratings in issues.values()
                for rating_count in ratings.values()
            )
            or role.get("useful_or_partly_useful_count")
            != usefulness["useful"] + usefulness["partly_useful"]
            or role.get("all_scored_cases_useful")
            is not (usefulness["useful"] == count)
        ):
            raise ValueError("full-song six-role outcome role summary differs")
    all_roles_useful = all(role["all_scored_cases_useful"] for role in roles)
    specialist_missing_content = sum(
        role["issue_counts"]["missing_content"]["some"]
        + role["issue_counts"]["missing_content"]["severe"]
        for role in roles
        if role["role"] in {"synth", "guitar"}
    )
    cannot_tell_or_not_tested = sum(
        role["usefulness_counts"]["cannot_tell"]
        + role["usefulness_counts"]["not_tested"]
        for role in roles
    )
    positive = (
        catastrophic["catastrophic_defect"] == 0
        and catastrophic["no_catastrophic_defect"] == 3
        and overall["useful"] == 3
        and all_roles_useful
    )
    expected_musical_result = (
        "catastrophic_private_full_song_six_role_evidence"
        if catastrophic["catastrophic_defect"]
        else (
            "positive_private_full_song_six_role_evidence_with_"
            "specialist_missing_content_reported"
            if positive and specialist_missing_content
            else (
                "positive_private_full_song_six_role_evidence"
                if positive
                else "mixed_private_full_song_six_role_evidence"
            )
        )
    )
    if (
        summary.get("all_scored_roles_useful") is not all_roles_useful
        or summary.get("specialist_missing_content_rating_count")
        != specialist_missing_content
        or summary.get("cannot_tell_or_not_tested_rating_count")
        != cannot_tell_or_not_tested
        or document.get("musical_result") != expected_musical_result
    ):
        raise ValueError("full-song six-role outcome aggregate differs")
    if document.get("objective_gaps") != {
        "full_objective_qualification": False,
        "guitar_worker_result_receipt_persisted": False,
        "guitar_guard_counters_persisted": False,
        "guitar_peak_memory_bytes": None,
        "guitar_resource_gate_complete": False,
        "full_resource_gate_complete": False,
        "within_known_ceilings": None,
    }:
        raise ValueError("full-song six-role outcome objective gap differs")
    if document.get("boundaries") != {
        "private_review_only": True,
        "full_objective_qualification": False,
        "resource_qualification": False,
        "profile_qualification": False,
        "public_activation": False,
        "source_selection": False,
        "midi_created": False,
        "hosting": False,
        "redistribution": False,
        "audio_upload": False,
        "automatic_retry": False,
        "poor_feedback_disables_core_four": False,
    }:
        raise ValueError("full-song six-role outcome boundary differs")
    if document.get("effects") != {
        "input_json_reads": 4,
        "output_json_writes": 1,
        "audio_reads": 0,
        "audio_writes": 0,
        "checkpoint_loads": 0,
        "model_constructions": 0,
        "model_loads": 0,
        "inference_attempts": 0,
        "network_attempts": 0,
    }:
        raise ValueError("full-song six-role outcome effects differ")
    expected_next_step = (
        "investigate the recorded catastrophic defect before any further "
        "objective run; do not activate, select or retry automatically"
        if catastrophic["catastrophic_defect"]
        else (
            "define a fresh objective-only repaired guitar-worker run to capture "
            "the missing receipt and memory evidence; keep private Studio "
            "integration and public admission as separate decisions"
        )
    )
    if document.get("decisions") != {
        "private_six_role_audio_evidence": "retain",
        "public_six_role_profile": "not_qualified",
        "public_core_four_profile": "unchanged",
        "next_bounded_step": expected_next_step,
    }:
        raise ValueError("full-song six-role outcome decision differs")
    specialist_missing_by_role = {
        role["role"]: (
            role["issue_counts"]["missing_content"]["some"]
            + role["issue_counts"]["missing_content"]["severe"]
        )
        for role in roles
        if role["role"] in {"synth", "guitar"}
    }
    specialist_limitation = (
        "confirmed-present specialist missing-content ratings: "
        + ", ".join(
            f"{role} {specialist_missing_by_role[role]}" for role in ("synth", "guitar")
        )
    )
    if document.get("known_limitations") != [
        specialist_limitation,
        (
            "three owner-authorised songs are limited private evidence, not "
            "broad catalogue validation"
        ),
        (
            "the missing guitar worker receipt, guard counters and peak memory "
            "prevent objective and resource qualification"
        ),
        "exact reconstruction proves accounting, not separation accuracy",
    ]:
        raise ValueError("full-song six-role outcome limitations differ")
    rebuilt = build_full_song_six_role_outcome(
        plan=plan,
        recovery_request=recovery_request,
        recovery_report=recovery_report,
        review=review,
        review_file=review_file,
    )
    if document != rebuilt:
        raise ValueError("full-song six-role outcome source binding differs")
    return document


def _read_private_json(
    path: Path, *, label: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = path.expanduser().absolute()
    parent_descriptor = open_absolute_directory_nofollow(resolved.parent)
    descriptor = -1
    try:
        descriptor = os.open(
            require_safe_directory_entry_name(resolved.name),
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_descriptor,
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.geteuid()
            or before.st_mode & 0o077
            or not 0 < before.st_size <= _MAX_JSON_BYTES
        ):
            raise ValueError(f"{label} private JSON identity differs")
        chunks = []
        remaining = before.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                raise ValueError(f"{label} changed while reading")
            chunks.append(block)
            remaining -= len(block)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError(f"{label} changed while reading")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)
    payload = b"".join(chunks)
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value, {
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _verify_outcome_file(
    staging_descriptor: int,
    outcome_descriptor: int,
    payload: bytes,
    *,
    expected_identity: tuple[int, ...] | None = None,
) -> tuple[int, ...]:
    metadata = os.fstat(outcome_descriptor)
    identity = (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_nlink,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )
    attached = os.stat(
        OUTCOME_FILE_NAME,
        dir_fd=staging_descriptor,
        follow_symlinks=False,
    )
    if (
        os.listdir(staging_descriptor) != [OUTCOME_FILE_NAME]
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or metadata.st_size != len(payload)
        or (attached.st_dev, attached.st_ino) != (metadata.st_dev, metadata.st_ino)
        or (expected_identity is not None and identity != expected_identity)
    ):
        raise RuntimeError("outcome staged file identity differs")
    os.lseek(outcome_descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    remaining = metadata.st_size
    while remaining:
        block = os.read(outcome_descriptor, min(1024 * 1024, remaining))
        if not block:
            raise RuntimeError("outcome staged file changed while hashing")
        digest.update(block)
        remaining -= len(block)
    if digest.digest() != hashlib.sha256(payload).digest():
        raise RuntimeError("outcome staged file content differs")
    after = os.fstat(outcome_descriptor)
    if identity != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mode,
        after.st_uid,
        after.st_nlink,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise RuntimeError("outcome staged file changed while hashing")
    return identity


def _quarantine_failed_publication(
    parent_descriptor: int,
    output_name: str,
    staging_identity: os.stat_result,
) -> str:
    visible = os.stat(
        output_name,
        dir_fd=parent_descriptor,
        follow_symlinks=False,
    )
    if (visible.st_dev, visible.st_ino) != (
        staging_identity.st_dev,
        staging_identity.st_ino,
    ):
        raise RuntimeError("failed outcome publication identity changed")
    for _attempt in range(128):
        quarantine_name = f"{output_name}-FAILED-{secrets.token_hex(8)}"
        try:
            rename_directory_no_replace_at(
                parent_descriptor,
                output_name,
                quarantine_name,
            )
        except FileExistsError:
            continue
        break
    else:
        raise RuntimeError("could not quarantine failed outcome publication")
    try:
        os.stat(output_name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise RuntimeError("failed outcome remained at its canonical name")
    quarantined = os.stat(
        quarantine_name,
        dir_fd=parent_descriptor,
        follow_symlinks=False,
    )
    if (quarantined.st_dev, quarantined.st_ino) != (
        staging_identity.st_dev,
        staging_identity.st_ino,
    ):
        raise RuntimeError("failed outcome quarantine identity differs")
    os.fsync(parent_descriptor)
    return quarantine_name


def record_full_song_six_role_outcome(
    recovery_root: str | Path,
    *,
    plan_path: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Read four exact JSON files and atomically publish one private outcome."""

    root = Path(recovery_root).expanduser().resolve(strict=True)
    output = Path(out_dir).expanduser().absolute()
    if output.name != OUTCOME_DIRECTORY_NAME:
        raise ValueError(f"outcome root must be named {OUTCOME_DIRECTORY_NAME}")
    if output != root.parent / OUTCOME_DIRECTORY_NAME:
        raise ValueError("outcome root must be an exact recovery-package sibling")
    if os.path.lexists(output):
        raise FileExistsError(f"fresh full-song six-role outcome required: {output}")
    plan, _plan_file = _read_private_json(Path(plan_path), label="full-song plan")
    request, _request_file = _read_private_json(
        root / "TECHNICAL/RECOVERY-REQUEST.json",
        label="full-song recovery request",
    )
    report, _report_file = _read_private_json(
        root / "TECHNICAL/FULL-SONG-SIX-ROLE-RECOVERY-REPORT.json",
        label="full-song recovery report",
    )
    review, review_file = _read_private_json(
        root / "REVIEW/FULL-SONG-SIX-ROLE-LISTENING.json",
        label="full-song listening review",
    )
    outcome = validate_full_song_six_role_outcome(
        build_full_song_six_role_outcome(
            plan=plan,
            recovery_request=request,
            recovery_report=report,
            review=review,
            review_file=review_file,
        ),
        plan=plan,
        recovery_request=request,
        recovery_report=report,
        review=review,
        review_file=review_file,
    )

    parent_descriptor = open_absolute_directory_nofollow(output.parent)
    parent_metadata = os.fstat(parent_descriptor)
    if parent_metadata.st_uid != os.geteuid() or parent_metadata.st_mode & 0o022:
        os.close(parent_descriptor)
        raise ValueError("outcome parent must not be group- or world-writable")
    previous_umask = os.umask(0o077)
    staging_name: str | None = None
    staging_descriptor = -1
    staging_identity: os.stat_result | None = None
    outcome_descriptor = -1
    renamed = False
    published = False
    try:
        for _attempt in range(128):
            candidate = f".{OUTCOME_DIRECTORY_NAME}-{secrets.token_hex(8)}"
            try:
                os.mkdir(candidate, mode=0o700, dir_fd=parent_descriptor)
            except FileExistsError:
                continue
            staging_name = candidate
            break
        if staging_name is None:
            raise RuntimeError("could not allocate a fresh outcome staging root")
        staging_descriptor = os.open(
            staging_name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_descriptor,
        )
        staging_identity = os.fstat(staging_descriptor)
        if (
            staging_identity.st_uid != os.geteuid()
            or staging_identity.st_mode & 0o777 != 0o700
        ):
            raise RuntimeError("outcome staging identity differs")
        payload = (
            json.dumps(outcome, indent=2, sort_keys=True, allow_nan=False) + "\n"
        ).encode("utf-8")
        outcome_descriptor = os.open(
            OUTCOME_FILE_NAME,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=staging_descriptor,
        )
        view = memoryview(payload)
        while view:
            written = os.write(outcome_descriptor, view)
            if written <= 0:
                raise RuntimeError("outcome JSON write made no progress")
            view = view[written:]
        os.fsync(outcome_descriptor)
        outcome_identity = _verify_outcome_file(
            staging_descriptor,
            outcome_descriptor,
            payload,
        )
        os.fsync(staging_descriptor)
        attached = os.stat(
            staging_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (attached.st_dev, attached.st_ino) != (
            staging_identity.st_dev,
            staging_identity.st_ino,
        ):
            raise RuntimeError("outcome staging attachment differs")
        rename_directory_no_replace_at(
            parent_descriptor,
            staging_name,
            output.name,
        )
        renamed = True
        visible = os.stat(
            output.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (visible.st_dev, visible.st_ino) != (
            staging_identity.st_dev,
            staging_identity.st_ino,
        ):
            raise RuntimeError("outcome publication identity differs")
        _verify_outcome_file(
            staging_descriptor,
            outcome_descriptor,
            payload,
            expected_identity=outcome_identity,
        )
        rebound_parent = open_absolute_directory_nofollow(output.parent)
        try:
            rebound_metadata = os.fstat(rebound_parent)
            if (rebound_metadata.st_dev, rebound_metadata.st_ino) != (
                parent_metadata.st_dev,
                parent_metadata.st_ino,
            ):
                raise RuntimeError("outcome parent attachment differs")
        finally:
            os.close(rebound_parent)
        _verify_outcome_file(
            staging_descriptor,
            outcome_descriptor,
            payload,
            expected_identity=outcome_identity,
        )
        os.fsync(parent_descriptor)
        published = True
    finally:
        os.umask(previous_umask)
        quarantine_failure: BaseException | None = None
        if renamed and not published:
            try:
                if staging_identity is None:
                    raise RuntimeError("failed outcome publication identity is missing")
                _quarantine_failed_publication(
                    parent_descriptor,
                    output.name,
                    staging_identity,
                )
            except BaseException as error:
                quarantine_failure = error
        if outcome_descriptor >= 0:
            os.close(outcome_descriptor)
        if staging_descriptor >= 0:
            if not renamed:
                try:
                    os.unlink(OUTCOME_FILE_NAME, dir_fd=staging_descriptor)
                except FileNotFoundError:
                    pass
            os.close(staging_descriptor)
        if staging_name is not None and not published and not renamed:
            try:
                os.rmdir(staging_name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)
        if quarantine_failure is not None:
            raise RuntimeError(
                "failed outcome publication could not be quarantined"
            ) from quarantine_failure
    return outcome


__all__ = [
    "OUTCOME_DIRECTORY_NAME",
    "OUTCOME_FILE_NAME",
    "OUTCOME_SCHEMA",
    "OUTCOME_STATUS",
    "ROLE_ORDER",
    "build_full_song_six_role_outcome",
    "outcome_document_sha256",
    "record_full_song_six_role_outcome",
    "validate_full_song_six_role_outcome",
]
