"""Private, explicit feedback for one exact balanced MIDI audition.

This module is intentionally independent of Workbench state and playback.  It
does not infer a preference from listening, create or alter MIDI, change a
selection, rank candidates, or update a default.  A review is one fresh JSON
artifact bound either to the exact unmastered balanced control or to an exact
listening-master challenger and its exact control.  Profiles are deterministic
summaries of explicitly named review files and are advisory only.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import stat
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import listening_master as _listening_master_contract
from .listening_master import LISTENING_MASTER_POLICY, LISTENING_MASTER_SCHEMA
from .workbench_balanced_contract import BALANCED_MIX_CONTRACT


MIX_REVIEW_SCHEMA = "sunofriend.local-mix-review.v2"
MIX_PROFILE_SCHEMA = "sunofriend.local-mix-profile.v2"
MIX_REVIEW_POLICY = "explicit-reviewed-exact-audition-v2"
MIX_PROFILE_POLICY = "explicit-reviewed-mix-history-v2"
BALANCED_MIX_RECEIPT_SCHEMA = BALANCED_MIX_CONTRACT.receipt_schema
BALANCED_CONTROL_VARIANT = "balanced_control"
LISTENING_MASTER_VARIANT = "listening_master"
ARTIFACT_VARIANTS = (BALANCED_CONTROL_VARIANT, LISTENING_MASTER_VARIANT)

RATING_AXES = (
    "overall_usefulness",
    "midi_interpretation",
    "instrumentation",
    "balance",
    "dynamics",
    "mastering",
)
RATING_VALUES = (
    "excellent",
    "good",
    "mixed",
    "poor",
    "unusable",
    "cannot_tell",
)
PROBLEM_TAGS = frozenset(
    {
        "bass_too_loud",
        "bass_too_quiet",
        "clipping_or_distortion",
        "drums_too_loud",
        "drums_too_quiet",
        "harsh",
        "inconsistent_instrument",
        "melody_masked",
        "melody_missing",
        "midi_note_density_high",
        "midi_note_density_low",
        "midi_pitch_errors",
        "midi_timing_errors",
        "muddy",
        "thin",
        "too_loud",
        "too_quiet",
        "wrong_instrument",
    }
)
MAX_PROBLEM_TAGS = 8
MAX_NOTES_CHARACTERS = 2_000
MAX_REVIEWER_SESSION_KEY_CHARACTERS = 128

_RECEIPT_MAXIMUM_BYTES = 4 * 1024 * 1024
_EVIDENCE_MAXIMUM_BYTES = 4 * 1024 * 1024 * 1024
_SHA256_LENGTH = 64
_SCORE_BY_RATING = {
    "excellent": 2,
    "good": 1,
    "mixed": 0,
    "poor": -1,
    "unusable": -2,
}
_REVIEW_POLICY = {
    "name": MIX_REVIEW_POLICY,
    "training_source": "explicit-human-review-only",
    "playback_inferred": False,
    "advisory_only": True,
    "automatic_selection": False,
    "candidate_order_changed": False,
    "default_selection_changed": False,
}
_PROFILE_POLICY = {
    "name": MIX_PROFILE_POLICY,
    "training_source": "explicit-reviewed-mix-artifacts-only",
    "advisory_only": True,
    "automatic_selection": False,
    "candidate_order_changed": False,
    "default_selection_changed": False,
}
_REVIEW_EFFECTS = {
    "feedback_artifact_created": True,
    "receipt_changed": False,
    "preview_wav_changed": False,
    "midi_changed": False,
    "selection_changed": False,
    "candidate_ranking_changed": False,
    "automatic_selection": False,
    "automatic_reordering": False,
    "default_selection_changed": False,
}
_PROFILE_EFFECTS = {
    "profile_artifact_created": True,
    "feedback_artifacts_changed": False,
    "receipt_changed": False,
    "preview_wav_changed": False,
    "midi_changed": False,
    "selection_changed": False,
    "candidate_ranking_changed": False,
    "automatic_selection": False,
    "automatic_reordering": False,
    "default_selection_changed": False,
}
_ADVISORY_EFFECTS = {
    "artifact_created": False,
    "midi_changed": False,
    "selection_changed": False,
    "candidate_ranking_changed": False,
    "automatic_selection": False,
    "automatic_reordering": False,
    "default_selection_changed": False,
}


def record_mix_feedback(
    receipt_path: str | Path,
    preview_wav_path: str | Path,
    *,
    reviewer_session_key: str,
    project_id: str,
    balanced_arrangement_cache_key: str,
    selection_manifest_sha256: str,
    overall_usefulness: str,
    midi_interpretation: str,
    instrumentation: str,
    balance: str,
    dynamics: str,
    mastering: str,
    out_path: str | Path,
    problem_tags: Sequence[str] = (),
    notes: str | None = None,
    listening_master_receipt_path: str | Path | None = None,
    listening_master_wav_path: str | Path | None = None,
) -> dict[str, Any]:
    """Record one explicit review of one exact balanced-audition artifact.

    ``receipt_path`` and ``preview_wav_path`` always identify the immutable
    unmastered balanced control.  Supplying both listening-master paths changes
    the reviewed artifact to that challenger while retaining the exact control
    binding.  The caller's bounded reviewer/session key is domain-hashed and is
    never written to disk.
    """

    expected_project_id = _bounded_text(
        project_id, label="project_id", maximum=128
    )
    cache_key = _require_sha256(
        balanced_arrangement_cache_key,
        label="balanced arrangement cache key",
    )
    expected_selection = _require_sha256(
        selection_manifest_sha256,
        label="selection manifest SHA-256",
    )
    ratings = _ratings(
        overall_usefulness=overall_usefulness,
        midi_interpretation=midi_interpretation,
        instrumentation=instrumentation,
        balance=balance,
        dynamics=dynamics,
        mastering=mastering,
    )
    normalized_tags = _problem_tags(problem_tags)
    note_text = _notes(notes)
    reviewer_session_id = _reviewer_session_id(reviewer_session_key)

    control_receipt_record, control_receipt = _read_receipt(receipt_path)
    control_preview_record, control_preview_info = _regular_wav_record(
        preview_wav_path,
        label="balanced preview WAV",
        maximum_bytes=_EVIDENCE_MAXIMUM_BYTES,
        require_pcm24=False,
    )
    if Path(control_preview_record["path"]).suffix.lower() != ".wav":
        raise ValueError("balanced preview must be a .wav file")
    if Path(control_receipt_record["path"]).suffix.lower() != ".json":
        raise ValueError("balanced receipt must be a .json file")
    if (
        Path(control_receipt_record["path"]).parent
        != Path(control_preview_record["path"]).parent
    ):
        raise ValueError("balanced receipt and preview must share one cache directory")
    if Path(control_receipt_record["path"]).parent.name != cache_key:
        raise ValueError("balanced arrangement cache key does not match artifact directory")

    control_binding = _validate_receipt_binding(
        control_receipt,
        receipt_record=control_receipt_record,
        preview_record=control_preview_record,
        expected_project_id=expected_project_id,
        expected_selection_manifest_sha256=expected_selection,
    )
    control_evidence = {
        "receipt_document_sha256": control_binding.pop(
            "receipt_document_sha256"
        ),
        "receipt": control_receipt_record,
        "preview_wav": control_preview_record,
    }
    master_paths = (
        listening_master_receipt_path,
        listening_master_wav_path,
    )
    if any(value is not None for value in master_paths) and not all(
        value is not None for value in master_paths
    ):
        raise ValueError(
            "listening-master receipt and WAV must be supplied together"
        )
    if all(value is not None for value in master_paths):
        audition_evidence = _listening_master_evidence(
            listening_master_receipt_path,
            listening_master_wav_path,
            control_preview_record=control_preview_record,
            control_preview_info=control_preview_info,
        )
    else:
        if ratings["mastering"] != "cannot_tell":
            raise ValueError(
                "mastering must be cannot_tell for the unmastered balanced control"
            )
        audition_evidence = {
            "variant": BALANCED_CONTROL_VARIANT,
            "mastered": False,
            "policy": control_binding["mix_policy"],
            "receipt_document_sha256": control_evidence[
                "receipt_document_sha256"
            ],
            "receipt": dict(control_receipt_record),
            "wav": dict(control_preview_record),
        }
    evidence = {
        **control_binding,
        "balanced_arrangement_cache_key": cache_key,
        "control": control_evidence,
        "audition": audition_evidence,
    }
    artifact_id = _artifact_id(evidence)
    review_id = _review_id(
        artifact_id=artifact_id,
        reviewer_session_id=reviewer_session_id,
    )
    document = {
        "schema": MIX_REVIEW_SCHEMA,
        "status": "reviewed",
        "policy": dict(_REVIEW_POLICY),
        "artifact_id": artifact_id,
        "review_id": review_id,
        "reviewer_session_id": reviewer_session_id,
        "evidence": evidence,
        "ratings": ratings,
        "problem_tags": normalized_tags,
        "notes": note_text,
        "privacy": _review_privacy(note_text),
        "effects": dict(_REVIEW_EFFECTS),
    }

    output_record = _write_fresh_private_json(
        out_path,
        document,
        label="mix feedback",
        protected_inputs=tuple(_evidence_paths(evidence)),
    )
    return {
        "status": "reviewed",
        "feedback": output_record,
        "artifact_id": artifact_id,
        "review_id": review_id,
        # Compatibility alias for callers that previously treated one exact
        # artifact identity as an observation identity.
        "observation_id": artifact_id,
        "artifact_variant": audition_evidence["variant"],
        "project_id": expected_project_id,
        "balanced_arrangement_cache_key": cache_key,
        "selection_manifest_sha256": expected_selection,
        "advisory_only": True,
        "automatic_selection": False,
        "candidate_order_changed": False,
        "default_selection_changed": False,
    }


def build_local_mix_profile(
    feedback_paths: Sequence[str | Path],
    *,
    out_path: str | Path,
) -> dict[str, Any]:
    """Build one fresh deterministic advisory profile from named reviews."""

    if not feedback_paths:
        raise ValueError("mix profile requires at least one feedback file")
    loaded = [_load_review(path, verify_evidence=True) for path in feedback_paths]
    profile = _profile_document(loaded)
    output_record = _write_fresh_private_json(
        out_path,
        profile,
        label="mix profile",
        protected_inputs=tuple(item[1]["path"] for item in loaded),
    )
    return {
        "status": "complete",
        "profile": output_record,
        "input_count": len(loaded),
        "review_count": profile["review_count"],
        "artifact_count": profile["artifact_count"],
        "observation_count": len(loaded),
        "axis_summaries": profile["axis_summaries"],
        "problem_tag_counts": profile["problem_tag_counts"],
        "advisory_only": True,
        "automatic_selection": False,
        "candidate_order_changed": False,
        "default_selection_changed": False,
    }


def load_local_mix_profile(
    profile_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load a profile and re-verify every review, receipt and preview byte."""

    profile_record, profile = _read_json_file(
        profile_path,
        label="mix profile",
        maximum_bytes=_RECEIPT_MAXIMUM_BYTES,
    )
    if profile.get("schema") != MIX_PROFILE_SCHEMA:
        raise ValueError("unsupported mix profile schema")
    inputs = profile.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("mix profile inputs are invalid")

    loaded: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in inputs:
        _validate_profile_input_shape(item)
        review_path = str(item["feedback"]["path"])
        document, record = _load_review(review_path, verify_evidence=True)
        if _profile_input(document, record) != item:
            raise ValueError("mix profile input changed or does not match its review")
        loaded.append((document, record))
    expected = _profile_document(loaded)
    if profile != expected:
        raise ValueError("mix profile summary does not match its reviewed inputs")
    return profile, profile_record


def advisory_mix_history(
    profile: Mapping[str, Any],
    *,
    mix_policy: str,
    renderer_policy: str,
    artifact_variant: str | None = None,
) -> dict[str, Any]:
    """Return matching history without selecting, ranking or reordering."""

    contexts = profile.get("contexts")
    if (
        profile.get("schema") != MIX_PROFILE_SCHEMA
        or profile.get("status") != "complete"
        or profile.get("policy") != _PROFILE_POLICY
        or profile.get("effects") != _PROFILE_EFFECTS
        or not isinstance(contexts, list)
        or any(not isinstance(value, Mapping) for value in contexts)
        or not isinstance(profile.get("axis_summaries"), Mapping)
        or not isinstance(profile.get("problem_tag_counts"), Mapping)
    ):
        raise ValueError("mix profile is invalid")
    selected_mix_policy = _bounded_text(
        mix_policy, label="mix policy", maximum=256
    )
    selected_renderer_policy = _bounded_text(
        renderer_policy, label="renderer policy", maximum=256
    )
    selected_variant = (
        _artifact_variant(artifact_variant)
        if artifact_variant is not None
        else None
    )
    matching_contexts = [
        value
        for value in contexts
        if value.get("mix_policy") == selected_mix_policy
        and value.get("renderer_policy") == selected_renderer_policy
        and (
            selected_variant is None
            or value.get("artifact_variant") == selected_variant
        )
    ]
    matching_variants = sorted(
        {
            str(value["artifact_variant"])
            for value in matching_contexts
            if value.get("artifact_variant") in ARTIFACT_VARIANTS
        }
    )
    summaries = _merge_context_axis_summaries(matching_contexts)
    tags = _merge_context_problem_tags(matching_contexts)
    observation_count = sum(
        _nonnegative_int(
            value.get("observation_count"),
            label="mix profile context observation count",
        )
        for value in matching_contexts
    )
    if not matching_contexts:
        status = "no_history"
        context_scope = "no_matching_policy_history"
    elif selected_variant is not None:
        status = "advisory"
        context_scope = "exact_policy_renderer_variant"
    elif len(matching_variants) == 1:
        status = "advisory"
        context_scope = "exact_policy_renderer"
    else:
        status = "advisory"
        context_scope = "matching_policy_renderer_variants"
    return {
        "status": status,
        "policy": MIX_PROFILE_POLICY,
        "context_match": bool(matching_contexts),
        "context_scope": context_scope,
        "artifact_variant": (
            selected_variant
            if selected_variant is not None
            else (matching_variants[0] if len(matching_variants) == 1 else None)
        ),
        "matching_variants": matching_variants,
        "observation_count": observation_count,
        "axis_summaries": deepcopy(summaries),
        "problem_tag_counts": deepcopy(tags),
        "meaning": (
            "Explicit local review history for only the requested mix and "
            "renderer policy context; not a candidate ranking, confidence "
            "score, selection or changed default."
        ),
        "effects": dict(_ADVISORY_EFFECTS),
    }


def _load_review(
    path: str | Path,
    *,
    verify_evidence: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    record, document = _read_json_file(
        path,
        label="mix feedback",
        maximum_bytes=_RECEIPT_MAXIMUM_BYTES,
    )
    _validate_review_document(document, verify_evidence=verify_evidence)
    return document, record


def _validate_review_document(
    document: Mapping[str, Any],
    *,
    verify_evidence: bool,
) -> None:
    expected_keys = {
        "schema",
        "status",
        "policy",
        "artifact_id",
        "review_id",
        "reviewer_session_id",
        "evidence",
        "ratings",
        "problem_tags",
        "notes",
        "privacy",
        "effects",
    }
    if set(document) != expected_keys:
        raise ValueError("mix feedback fields are invalid")
    if (
        document.get("schema") != MIX_REVIEW_SCHEMA
        or document.get("status") != "reviewed"
        or document.get("policy") != _REVIEW_POLICY
        or document.get("effects") != _REVIEW_EFFECTS
    ):
        raise ValueError("mix feedback contract is invalid")
    ratings = document.get("ratings")
    if not isinstance(ratings, Mapping) or set(ratings) != set(RATING_AXES):
        raise ValueError("mix feedback ratings are invalid")
    normalized_ratings = _ratings(
        **{axis: ratings[axis] for axis in RATING_AXES}
    )
    if dict(ratings) != normalized_ratings:
        raise ValueError("mix feedback ratings are invalid")
    tags = document.get("problem_tags")
    if not isinstance(tags, list) or tags != _problem_tags(tags):
        raise ValueError("mix feedback problem tags are invalid")
    note_text = _notes(document.get("notes"))
    if note_text != document.get("notes"):
        raise ValueError("mix feedback notes are invalid")
    if document.get("privacy") != _review_privacy(note_text):
        raise ValueError("mix feedback privacy contract is invalid")

    evidence = document.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("mix feedback evidence is invalid")
    _validate_evidence_shape(evidence)
    artifact_id = _artifact_id(evidence)
    if document.get("artifact_id") != artifact_id:
        raise ValueError("mix feedback artifact identity is invalid")
    reviewer_session_id = _require_sha256(
        document.get("reviewer_session_id"),
        label="mix feedback reviewer/session identity",
    )
    if document.get("review_id") != _review_id(
        artifact_id=artifact_id,
        reviewer_session_id=reviewer_session_id,
    ):
        raise ValueError("mix feedback review identity is invalid")
    if (
        evidence["audition"]["variant"] == BALANCED_CONTROL_VARIANT
        and normalized_ratings["mastering"] != "cannot_tell"
    ):
        raise ValueError(
            "mastering must be cannot_tell for the unmastered balanced control"
        )
    if verify_evidence:
        _verify_current_evidence(evidence)


def _verify_current_evidence(evidence: Mapping[str, Any]) -> None:
    control = evidence["control"]
    current_receipt, receipt = _read_receipt(str(control["receipt"]["path"]))
    current_preview_record = _regular_file_record(
        str(control["preview_wav"]["path"]),
        label="balanced preview WAV",
        maximum_bytes=_EVIDENCE_MAXIMUM_BYTES,
    )
    if current_preview_record != control["preview_wav"]:
        raise ValueError("balanced preview WAV changed after feedback was recorded")
    current_preview, current_preview_info = _regular_wav_record(
        str(control["preview_wav"]["path"]),
        label="balanced preview WAV",
        maximum_bytes=_EVIDENCE_MAXIMUM_BYTES,
        require_pcm24=False,
    )
    if current_receipt != control["receipt"]:
        raise ValueError("balanced receipt changed after feedback was recorded")
    if current_preview != control["preview_wav"]:
        raise ValueError("balanced preview WAV changed after feedback was recorded")
    binding = _validate_receipt_binding(
        receipt,
        receipt_record=current_receipt,
        preview_record=current_preview,
        expected_project_id=str(evidence["project_id"]),
        expected_selection_manifest_sha256=str(
            evidence["selection_manifest_sha256"]
        ),
    )
    expected_binding = {
        key: evidence[key]
        for key in (
            "project_id",
            "selection_manifest_sha256",
            "mix_policy",
            "renderer_policy",
        )
    }
    if (
        {
            key: binding[key]
            for key in expected_binding
        }
        != expected_binding
        or binding["receipt_document_sha256"]
        != control["receipt_document_sha256"]
    ):
        raise ValueError("balanced receipt evidence no longer matches feedback")
    cache_key = str(evidence["balanced_arrangement_cache_key"])
    if (
        Path(current_receipt["path"]).parent
        != Path(current_preview["path"]).parent
        or Path(current_receipt["path"]).parent.name != cache_key
    ):
        raise ValueError("balanced arrangement evidence moved or changed scope")
    audition = evidence["audition"]
    if audition["variant"] == BALANCED_CONTROL_VARIANT:
        expected_audition = {
            "variant": BALANCED_CONTROL_VARIANT,
            "mastered": False,
            "policy": binding["mix_policy"],
            "receipt_document_sha256": binding["receipt_document_sha256"],
            "receipt": current_receipt,
            "wav": current_preview,
        }
        if audition != expected_audition:
            raise ValueError("balanced control audition evidence changed")
        return
    _verify_listening_master_evidence(
        audition,
        control_preview_record=current_preview,
        control_preview_info=current_preview_info,
    )


def _validate_evidence_shape(evidence: Mapping[str, Any]) -> None:
    expected = {
        "project_id",
        "balanced_arrangement_cache_key",
        "selection_manifest_sha256",
        "mix_policy",
        "renderer_policy",
        "control",
        "audition",
    }
    if set(evidence) != expected:
        raise ValueError("mix feedback evidence fields are invalid")
    if _bounded_text(
        evidence.get("project_id"), label="project_id", maximum=128
    ) != evidence.get("project_id"):
        raise ValueError("mix feedback project_id is not canonical")
    _require_sha256(
        evidence.get("balanced_arrangement_cache_key"),
        label="balanced arrangement cache key",
    )
    _require_sha256(
        evidence.get("selection_manifest_sha256"),
        label="selection manifest SHA-256",
    )
    if _bounded_text(
        evidence.get("mix_policy"), label="mix policy", maximum=256
    ) != evidence.get("mix_policy"):
        raise ValueError("mix feedback mix policy is not canonical")
    if _bounded_text(
        evidence.get("renderer_policy"),
        label="renderer policy",
        maximum=256,
    ) != evidence.get("renderer_policy"):
        raise ValueError("mix feedback renderer policy is not canonical")
    control = evidence.get("control")
    if not isinstance(control, Mapping) or set(control) != {
        "receipt_document_sha256",
        "receipt",
        "preview_wav",
    }:
        raise ValueError("mix feedback control evidence fields are invalid")
    _require_sha256(
        control.get("receipt_document_sha256"),
        label="balanced receipt document SHA-256",
    )
    _validate_file_record(control.get("receipt"), label="balanced receipt")
    _validate_file_record(
        control.get("preview_wav"), label="balanced preview WAV"
    )
    audition = evidence.get("audition")
    _validate_audition_shape(audition)


def _validate_receipt_binding(
    receipt: Mapping[str, Any],
    *,
    receipt_record: Mapping[str, Any],
    preview_record: Mapping[str, Any],
    expected_project_id: str,
    expected_selection_manifest_sha256: str,
) -> dict[str, Any]:
    if receipt.get("schema") != BALANCED_MIX_RECEIPT_SCHEMA:
        raise ValueError("unsupported balanced mix receipt")
    if receipt.get("mastered") is not False:
        raise ValueError("balanced mix receipt must identify an unmastered control")
    unsigned = {
        key: value for key, value in receipt.items() if key != "receipt_sha256"
    }
    document_sha256 = _document_hash(unsigned)
    if receipt.get("receipt_sha256") != document_sha256:
        raise ValueError("balanced mix receipt self-hash is invalid")
    if receipt.get("project_id") != expected_project_id:
        raise ValueError("balanced mix receipt project_id does not match")
    if (
        receipt.get("selection_manifest_sha256")
        != expected_selection_manifest_sha256
    ):
        raise ValueError("balanced mix receipt selection manifest does not match")
    mix_policy = _bounded_text(
        receipt.get("policy"), label="mix policy", maximum=256
    )
    if receipt.get("policy") != mix_policy:
        raise ValueError("balanced mix receipt policy is not canonical")
    renderer = receipt.get("renderer")
    if not isinstance(renderer, Mapping):
        raise ValueError("balanced mix receipt renderer is invalid")
    renderer_policy = _bounded_text(
        renderer.get("policy"), label="renderer policy", maximum=256
    )
    if renderer.get("policy") != renderer_policy:
        raise ValueError("balanced mix receipt renderer policy is not canonical")
    preview = receipt.get("preview")
    if not isinstance(preview, Mapping) or set(preview) != {
        "filename",
        "bytes",
        "sha256",
    }:
        raise ValueError("balanced mix receipt preview record is invalid")
    if (
        preview.get("filename") != Path(str(preview_record["path"])).name
        or preview.get("bytes") != preview_record["bytes"]
        or preview.get("sha256") != preview_record["sha256"]
    ):
        raise ValueError("balanced preview WAV does not match its receipt")
    # The raw receipt record is deliberately separate from its internal
    # document hash: both exact serialized bytes and receipt semantics matter.
    _validate_file_record(receipt_record, label="balanced receipt")
    return {
        "project_id": expected_project_id,
        "selection_manifest_sha256": expected_selection_manifest_sha256,
        "mix_policy": mix_policy,
        "renderer_policy": renderer_policy,
        "receipt_document_sha256": document_sha256,
    }


def _listening_master_evidence(
    receipt_path: str | Path | None,
    wav_path: str | Path | None,
    *,
    control_preview_record: Mapping[str, Any],
    control_preview_info: Mapping[str, Any],
) -> dict[str, Any]:
    if receipt_path is None or wav_path is None:  # defensive typed boundary
        raise ValueError(
            "listening-master receipt and WAV must be supplied together"
        )
    receipt_record, receipt = _read_json_file(
        receipt_path,
        label="listening-master receipt",
        maximum_bytes=_RECEIPT_MAXIMUM_BYTES,
    )
    wav_record, wav_info = _regular_wav_record(
        wav_path,
        label="listening-master WAV",
        maximum_bytes=_EVIDENCE_MAXIMUM_BYTES,
        require_pcm24=True,
    )
    if Path(receipt_record["path"]).suffix.lower() != ".json":
        raise ValueError("listening-master receipt must be a .json file")
    if Path(wav_record["path"]).suffix.lower() != ".wav":
        raise ValueError("listening-master audition must be a .wav file")
    binding = _validate_listening_master_binding(
        receipt,
        receipt_record=receipt_record,
        wav_record=wav_record,
        wav_info=wav_info,
        control_preview_record=control_preview_record,
        control_preview_info=control_preview_info,
    )
    return {
        "variant": LISTENING_MASTER_VARIANT,
        "mastered": True,
        "policy": binding["policy"],
        "receipt_document_sha256": binding["receipt_document_sha256"],
        "receipt": receipt_record,
        "wav": wav_record,
    }


def _verify_listening_master_evidence(
    audition: Mapping[str, Any],
    *,
    control_preview_record: Mapping[str, Any],
    control_preview_info: Mapping[str, Any],
) -> None:
    current_receipt, receipt = _read_json_file(
        str(audition["receipt"]["path"]),
        label="listening-master receipt",
        maximum_bytes=_RECEIPT_MAXIMUM_BYTES,
    )
    current_wav_record = _regular_file_record(
        str(audition["wav"]["path"]),
        label="listening-master WAV",
        maximum_bytes=_EVIDENCE_MAXIMUM_BYTES,
    )
    if current_wav_record != audition["wav"]:
        raise ValueError(
            "listening-master WAV changed after feedback was recorded"
        )
    current_wav, current_wav_info = _regular_wav_record(
        str(audition["wav"]["path"]),
        label="listening-master WAV",
        maximum_bytes=_EVIDENCE_MAXIMUM_BYTES,
        require_pcm24=True,
    )
    if current_receipt != audition["receipt"]:
        raise ValueError(
            "listening-master receipt changed after feedback was recorded"
        )
    if current_wav != audition["wav"]:
        raise ValueError(
            "listening-master WAV changed after feedback was recorded"
        )
    binding = _validate_listening_master_binding(
        receipt,
        receipt_record=current_receipt,
        wav_record=current_wav,
        wav_info=current_wav_info,
        control_preview_record=control_preview_record,
        control_preview_info=control_preview_info,
    )
    expected = {
        "variant": LISTENING_MASTER_VARIANT,
        "mastered": True,
        "policy": binding["policy"],
        "receipt_document_sha256": binding["receipt_document_sha256"],
        "receipt": current_receipt,
        "wav": current_wav,
    }
    if audition != expected:
        raise ValueError(
            "listening-master audition evidence no longer matches feedback"
        )


def _validate_listening_master_binding(
    receipt: Mapping[str, Any],
    *,
    receipt_record: Mapping[str, Any],
    wav_record: Mapping[str, Any],
    wav_info: Mapping[str, Any],
    control_preview_record: Mapping[str, Any],
    control_preview_info: Mapping[str, Any],
) -> dict[str, str]:
    expected_top_level = {
        "schema",
        "status",
        "policy",
        "label",
        "mastered",
        "release_master",
        "mastering_scope",
        "source",
        "targets",
        "analysis_pass",
        "render_pass",
        "verification_pass",
        "renderer",
        "output",
        "timing",
        "processing",
        "effects",
        "receipt_sha256",
    }
    if set(receipt) != expected_top_level or (
        receipt.get("schema") != LISTENING_MASTER_SCHEMA
        or receipt.get("status") != "complete"
        or receipt.get("policy") != LISTENING_MASTER_POLICY
        or receipt.get("mastered") is not True
        or receipt.get("release_master") is not False
    ):
        raise ValueError("unsupported listening-master receipt")
    _bounded_text(receipt.get("label"), label="listening-master label", maximum=256)
    _bounded_text(
        receipt.get("mastering_scope"),
        label="listening-master scope",
        maximum=1_000,
    )
    unsigned = {
        key: value for key, value in receipt.items() if key != "receipt_sha256"
    }
    document_sha256 = _document_hash(unsigned)
    if receipt.get("receipt_sha256") != document_sha256:
        raise ValueError("listening-master receipt self-hash is invalid")

    effects = receipt.get("effects")
    expected_effects = {
        "source_audio_mutated": False,
        "source_audio_overwritten": False,
        "midi_mutated": False,
        "selection_changed": False,
        "feedback_recorded": False,
        "automatic_selection": False,
        "automatic_ranking": False,
        "default_selection_changed": False,
        "control_balance_replaced": False,
        "listening_master_created": True,
    }
    if effects != expected_effects:
        raise ValueError("listening-master receipt effects are invalid")

    source = _audio_receipt_record(
        receipt.get("source"),
        label="listening-master source",
        require_pcm24=False,
    )
    output = _audio_receipt_record(
        receipt.get("output"),
        label="listening-master output",
        require_pcm24=True,
        includes_name=True,
    )
    if (
        source["sha256"] != control_preview_record["sha256"]
        or source["bytes"] != control_preview_record["bytes"]
    ):
        raise ValueError(
            "listening-master source does not match the exact balanced control"
        )
    for key in ("format", "subtype", "sample_rate", "channels", "frames"):
        if source[key] != control_preview_info[key]:
            raise ValueError(
                "listening-master source geometry does not match the balanced control"
            )
    if output["name"] != Path(str(wav_record["path"])).name or (
        output["sha256"] != wav_record["sha256"]
        or output["bytes"] != wav_record["bytes"]
    ):
        raise ValueError("listening-master WAV does not match its exact receipt")
    for key in (
        "format",
        "subtype",
        "sample_rate",
        "channels",
        "frames",
        "duration_seconds",
    ):
        if output[key] != wav_info[key]:
            raise ValueError(
                "listening-master WAV geometry does not match its exact receipt"
            )
    for key in ("sample_rate", "channels", "frames"):
        if output[key] != source[key]:
            raise ValueError(
                "listening-master output changed the source audio horizon"
            )

    expected_targets = {
        "integrated_lufs": _listening_master_contract._TARGET_INTEGRATED_LUFS,
        "loudness_range_lu": (
            _listening_master_contract._TARGET_LOUDNESS_RANGE_LU
        ),
        "true_peak_ceiling_dbtp": (
            _listening_master_contract._TRUE_PEAK_CEILING_DBTP
        ),
        "integrated_loudness_tolerance_lu": (
            _listening_master_contract._LOUDNESS_TOLERANCE_LU
        ),
        "true_peak_tolerance_db": (
            _listening_master_contract._TRUE_PEAK_TOLERANCE_DB
        ),
    }
    if receipt.get("targets") != expected_targets:
        raise ValueError("listening-master targets are invalid")

    analysis = _loudnorm_receipt_stats(
        receipt.get("analysis_pass"),
        label="listening-master analysis pass",
    )
    rendered = _loudnorm_receipt_stats(
        receipt.get("render_pass"),
        label="listening-master render pass",
    )
    verification_value = receipt.get("verification_pass")
    verification_keys = set(_listening_master_contract._LOUDNORM_FIELDS) | {
        "measured_artifact"
    }
    if (
        not isinstance(verification_value, Mapping)
        or set(verification_value) != verification_keys
        or verification_value.get("measured_artifact")
        != "encoded_pcm24_output"
    ):
        raise ValueError(
            "listening-master encoded-artifact verification is invalid"
        )
    verification = _loudnorm_receipt_stats(
        {
            key: verification_value[key]
            for key in _listening_master_contract._LOUDNORM_FIELDS
        },
        label="listening-master encoded-artifact verification",
    )
    try:
        _listening_master_contract._require_encoded_master_targets(verification)
    except (RuntimeError, ValueError) as exc:
        raise ValueError(
            "listening-master encoded artifact missed its receipt targets"
        ) from exc

    renderer = receipt.get("renderer")
    if not isinstance(renderer, Mapping) or set(renderer) != {
        "backend",
        "executable_sha256",
        "version",
        "filter",
        "policy",
        "identity_verification",
    }:
        raise ValueError("listening-master renderer is invalid")
    if (
        renderer.get("backend") != "FFmpeg loudnorm"
        or renderer.get("filter") != "loudnorm"
        or renderer.get("policy") != LISTENING_MASTER_POLICY
        or renderer.get("identity_verification")
        != _listening_master_contract.FFMPEG_IDENTITY_POLICY
        or not _bounded_text(
            renderer.get("version"),
            label="listening-master renderer version",
            maximum=500,
        ).startswith("ffmpeg version ")
    ):
        raise ValueError("listening-master renderer is invalid")
    _require_sha256(
        renderer.get("executable_sha256"),
        label="listening-master renderer executable SHA-256",
    )

    timing = receipt.get("timing")
    expected_timing = {
        "policy": "retain-input-frame-horizon-v1",
        "input_frames": source["frames"],
        "output_frames": output["frames"],
        "sample_rate": source["sample_rate"],
        "frame_horizon_changed": False,
        "time_shift_applied": False,
        "time_stretch_applied": False,
    }
    if timing != expected_timing:
        raise ValueError("listening-master timing contract is invalid")

    processing = receipt.get("processing")
    expected_processing = {
        "integrated_loudness_normalisation": True,
        "true_peak_limiting": True,
        "normalization_type": rendered["normalization_type"],
        "encoded_artifact_verified": True,
        "equalisation": False,
        "stereo_widening": False,
        "reverb": False,
        "chorus": False,
        "saturation": False,
    }
    if processing != expected_processing:
        raise ValueError("listening-master processing contract is invalid")
    # Ensure all three passes were normalized into the generator's canonical
    # numeric representation.  The values are not otherwise used to infer a
    # review or preference.
    if (
        analysis != receipt["analysis_pass"]
        or rendered != receipt["render_pass"]
        or {
            **verification,
            "measured_artifact": "encoded_pcm24_output",
        }
        != receipt["verification_pass"]
    ):
        raise ValueError("listening-master measurement records are not canonical")
    _validate_file_record(receipt_record, label="listening-master receipt")
    return {
        "policy": LISTENING_MASTER_POLICY,
        "receipt_document_sha256": document_sha256,
    }


def _audio_receipt_record(
    value: Any,
    *,
    label: str,
    require_pcm24: bool,
    includes_name: bool = False,
) -> dict[str, Any]:
    expected = {
        "sha256",
        "bytes",
        "format",
        "subtype",
        "sample_rate",
        "channels",
        "frames",
        "duration_seconds",
    }
    if includes_name:
        expected.add("name")
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"{label} record is invalid")
    sha256 = _require_sha256(value.get("sha256"), label=f"{label} SHA-256")
    byte_count = _positive_int(value.get("bytes"), label=f"{label} bytes")
    audio_format = value.get("format")
    subtype = _bounded_text(
        value.get("subtype"), label=f"{label} subtype", maximum=64
    )
    sample_rate = _positive_int(
        value.get("sample_rate"), label=f"{label} sample rate"
    )
    channels = _positive_int(value.get("channels"), label=f"{label} channels")
    frames = _positive_int(value.get("frames"), label=f"{label} frames")
    if audio_format not in {"WAV", "WAVEX"} or channels not in {1, 2}:
        raise ValueError(f"{label} audio geometry is invalid")
    if require_pcm24 and subtype != "PCM_24":
        raise ValueError(f"{label} must be PCM24 WAV")
    expected_duration = round(frames / sample_rate, 6)
    duration = _finite_number(
        value.get("duration_seconds"), label=f"{label} duration"
    )
    if duration != expected_duration:
        raise ValueError(f"{label} duration does not match its frame horizon")
    record: dict[str, Any] = {
        "sha256": sha256,
        "bytes": byte_count,
        "format": audio_format,
        "subtype": subtype,
        "sample_rate": sample_rate,
        "channels": channels,
        "frames": frames,
        "duration_seconds": duration,
    }
    if includes_name:
        name = _bounded_text(
            value.get("name"), label=f"{label} name", maximum=512
        )
        if Path(name).name != name or Path(name).suffix.lower() != ".wav":
            raise ValueError(f"{label} name is invalid")
        record["name"] = name
    return record


def _loudnorm_receipt_stats(value: Any, *, label: str) -> dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or set(value) != set(_listening_master_contract._LOUDNORM_FIELDS)
    ):
        raise ValueError(f"{label} measurements are invalid")
    try:
        return _listening_master_contract._validated_loudnorm_stats(value)
    except ValueError as exc:
        raise ValueError(f"{label} measurements are invalid") from exc


def _validate_audition_shape(value: Any) -> None:
    expected = {
        "variant",
        "mastered",
        "policy",
        "receipt_document_sha256",
        "receipt",
        "wav",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("mix feedback audition evidence fields are invalid")
    variant = _artifact_variant(value.get("variant"))
    if value.get("mastered") is not (variant == LISTENING_MASTER_VARIANT):
        raise ValueError("mix feedback audition mastering flag is invalid")
    expected_policy = (
        LISTENING_MASTER_POLICY
        if variant == LISTENING_MASTER_VARIANT
        else value.get("policy")
    )
    if _bounded_text(
        value.get("policy"), label="audition policy", maximum=256
    ) != expected_policy:
        raise ValueError("mix feedback audition policy is invalid")
    _require_sha256(
        value.get("receipt_document_sha256"),
        label="audition receipt document SHA-256",
    )
    _validate_file_record(value.get("receipt"), label="audition receipt")
    _validate_file_record(value.get("wav"), label="audition WAV")


def _profile_document(
    loaded: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> dict[str, Any]:
    if not loaded:
        raise ValueError("mix profile requires at least one feedback file")
    review_ids = [str(document["review_id"]) for document, _ in loaded]
    if len(review_ids) != len(set(review_ids)):
        raise ValueError(
            "mix profile review IDs must be unique per reviewer and artifact"
        )
    feedback_hashes = [str(record["sha256"]) for _, record in loaded]
    if len(feedback_hashes) != len(set(feedback_hashes)):
        raise ValueError("mix profile feedback files must be unique by hash")

    ordered = sorted(
        loaded,
        key=lambda item: (
            str(item[0]["artifact_id"]),
            str(item[0]["review_id"]),
            str(item[1]["sha256"]),
            str(item[1]["path"]),
        ),
    )
    documents = [document for document, _ in ordered]
    inputs = [_profile_input(document, record) for document, record in ordered]
    contexts: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for document in documents:
        evidence = document["evidence"]
        key = (
            str(evidence["mix_policy"]),
            str(evidence["renderer_policy"]),
            str(evidence["audition"]["variant"]),
        )
        contexts.setdefault(key, []).append(document)
    context_rows = []
    for (
        mix_policy,
        renderer_policy,
        artifact_variant,
    ), values in sorted(contexts.items()):
        context_rows.append(
            {
                "context_id": _document_hash(
                    {
                        "mix_policy": mix_policy,
                        "renderer_policy": renderer_policy,
                        "artifact_variant": artifact_variant,
                    }
                ),
                "mix_policy": mix_policy,
                "renderer_policy": renderer_policy,
                "artifact_variant": artifact_variant,
                "observation_count": len(values),
                "axis_summaries": _axis_summaries(values),
                "problem_tag_counts": _problem_tag_counts(values),
            }
        )
    return {
        "schema": MIX_PROFILE_SCHEMA,
        "status": "complete",
        "policy": dict(_PROFILE_POLICY),
        "inputs": inputs,
        "input_count": len(inputs),
        "review_count": len(inputs),
        "artifact_count": len(
            {str(document["artifact_id"]) for document in documents}
        ),
        "observation_count": len(inputs),
        "axis_summaries": _axis_summaries(documents),
        "problem_tag_counts": _problem_tag_counts(documents),
        "contexts": context_rows,
        "context_count": len(context_rows),
        "privacy": {
            "local_only": True,
            "contains_absolute_paths": True,
            "contains_free_text": False,
            "network_transmission": False,
        },
        "effects": dict(_PROFILE_EFFECTS),
    }


def _profile_input(
    document: Mapping[str, Any],
    record: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = document["evidence"]
    return {
        "feedback": dict(record),
        "artifact_id": document["artifact_id"],
        "review_id": document["review_id"],
        "reviewer_session_id": document["reviewer_session_id"],
        "artifact_variant": evidence["audition"]["variant"],
        "project_id": evidence["project_id"],
        "balanced_arrangement_cache_key": evidence[
            "balanced_arrangement_cache_key"
        ],
        "selection_manifest_sha256": evidence["selection_manifest_sha256"],
        "control_receipt_sha256": evidence["control"]["receipt"]["sha256"],
        "control_preview_wav_sha256": evidence["control"]["preview_wav"][
            "sha256"
        ],
        "audition_receipt_sha256": evidence["audition"]["receipt"]["sha256"],
        "audition_wav_sha256": evidence["audition"]["wav"]["sha256"],
        "mix_policy": evidence["mix_policy"],
        "renderer_policy": evidence["renderer_policy"],
        "ratings": dict(document["ratings"]),
        "problem_tags": list(document["problem_tags"]),
    }


def _validate_profile_input_shape(value: Any) -> None:
    expected = {
        "feedback",
        "artifact_id",
        "review_id",
        "reviewer_session_id",
        "artifact_variant",
        "project_id",
        "balanced_arrangement_cache_key",
        "selection_manifest_sha256",
        "control_receipt_sha256",
        "control_preview_wav_sha256",
        "audition_receipt_sha256",
        "audition_wav_sha256",
        "mix_policy",
        "renderer_policy",
        "ratings",
        "problem_tags",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("mix profile input is invalid")
    _validate_file_record(value.get("feedback"), label="mix profile feedback")
    for name in (
        "artifact_id",
        "review_id",
        "reviewer_session_id",
        "balanced_arrangement_cache_key",
        "selection_manifest_sha256",
        "control_receipt_sha256",
        "control_preview_wav_sha256",
        "audition_receipt_sha256",
        "audition_wav_sha256",
    ):
        _require_sha256(value.get(name), label=f"mix profile {name}")
    _artifact_variant(value.get("artifact_variant"))


def _axis_summaries(
    documents: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for axis in RATING_AXES:
        counts = Counter(str(document["ratings"][axis]) for document in documents)
        result[axis] = _axis_summary(counts)
    return result


def _axis_summary(counts: Mapping[str, int]) -> dict[str, Any]:
    normalized = Counter(
        {
            value: _nonnegative_int(
                counts.get(value, 0),
                label=f"mix feedback {value} rating count",
            )
            for value in RATING_VALUES
        }
    )
    observation_count = sum(normalized.values())
    directional_count = sum(normalized[value] for value in _SCORE_BY_RATING)
    score_total = sum(
        normalized[value] * score for value, score in _SCORE_BY_RATING.items()
    )
    mean_score = (
        round(score_total / directional_count, 6)
        if directional_count
        else None
    )
    if mean_score is None:
        signal = "no_directional_evidence"
    elif mean_score >= 0.5:
        signal = "positive"
    elif mean_score <= -0.5:
        signal = "negative"
    else:
        signal = "mixed"
    return {
        "rating_counts": {
            value: int(normalized.get(value, 0)) for value in RATING_VALUES
        },
        "observation_count": observation_count,
        "directional_observation_count": directional_count,
        "cannot_tell_count": int(normalized.get("cannot_tell", 0)),
        "mean_score": mean_score,
        "history_signal": signal,
        "score_meaning": (
            "Ordinal summary of explicit local reviews; not confidence, "
            "a candidate ranking or an automatic decision."
        ),
    }


def _merge_context_axis_summaries(
    contexts: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, Counter[str]] = {
        axis: Counter() for axis in RATING_AXES
    }
    for context in contexts:
        summaries = context.get("axis_summaries")
        if not isinstance(summaries, Mapping) or set(summaries) != set(RATING_AXES):
            raise ValueError("mix profile context axis summaries are invalid")
        for axis in RATING_AXES:
            summary = summaries[axis]
            if not isinstance(summary, Mapping):
                raise ValueError("mix profile context axis summary is invalid")
            counts = summary.get("rating_counts")
            if not isinstance(counts, Mapping) or set(counts) != set(RATING_VALUES):
                raise ValueError("mix profile context rating counts are invalid")
            for rating in RATING_VALUES:
                merged[axis][rating] += _nonnegative_int(
                    counts[rating],
                    label="mix profile context rating count",
                )
    return {axis: _axis_summary(merged[axis]) for axis in RATING_AXES}


def _merge_context_problem_tags(
    contexts: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    merged: Counter[str] = Counter()
    for context in contexts:
        counts = context.get("problem_tag_counts")
        if not isinstance(counts, Mapping):
            raise ValueError("mix profile context problem tags are invalid")
        for tag, count in counts.items():
            if tag not in PROBLEM_TAGS:
                raise ValueError("mix profile context problem tag is invalid")
            merged[str(tag)] += _nonnegative_int(
                count, label="mix profile context problem tag count"
            )
    return {key: merged[key] for key in sorted(merged)}


def _problem_tag_counts(
    documents: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for document in documents:
        counts.update(str(value) for value in document["problem_tags"])
    return {key: counts[key] for key in sorted(counts)}


def _ratings(**values: Any) -> dict[str, str]:
    if set(values) != set(RATING_AXES):
        raise ValueError("all mix feedback rating axes are required")
    result = {}
    for axis in RATING_AXES:
        value = str(values[axis]).strip().lower()
        if value not in RATING_VALUES:
            raise ValueError(
                f"{axis} must be one of: " + ", ".join(RATING_VALUES)
            )
        result[axis] = value
    return result


def _problem_tags(values: Sequence[str]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise ValueError("problem tags must be a sequence of category names")
    normalized = [str(value).strip().lower() for value in values]
    if len(normalized) > MAX_PROBLEM_TAGS:
        raise ValueError(f"at most {MAX_PROBLEM_TAGS} problem tags are allowed")
    if any(value not in PROBLEM_TAGS for value in normalized):
        raise ValueError(
            "problem tags must be selected from the published bounded vocabulary"
        )
    if len(normalized) != len(set(normalized)):
        raise ValueError("problem tags must not contain duplicates")
    return sorted(normalized)


def _notes(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("mix feedback notes must be text")
    text = value.strip()
    if not text:
        return None
    if len(text) > MAX_NOTES_CHARACTERS:
        raise ValueError(
            f"mix feedback notes are limited to {MAX_NOTES_CHARACTERS} characters"
        )
    if any(ord(character) == 0 for character in text):
        raise ValueError("mix feedback notes contain an invalid control character")
    return text


def _review_privacy(notes: str | None) -> dict[str, bool]:
    return {
        "local_only": True,
        "contains_absolute_paths": True,
        "contains_free_text": notes is not None,
        "reviewer_session_key_stored": False,
        "reviewer_session_key_domain_hashed": True,
        "network_transmission": False,
    }


def _artifact_id(evidence: Mapping[str, Any]) -> str:
    """Identify one exact audition independently of its reviewer or wording."""

    control = evidence.get("control")
    audition = evidence.get("audition")
    control_identity = (
        {
            "receipt_document_sha256": control.get(
                "receipt_document_sha256"
            ),
            "receipt": _path_free_file_identity(control.get("receipt")),
            "preview_wav": _path_free_file_identity(
                control.get("preview_wav")
            ),
        }
        if isinstance(control, Mapping)
        else None
    )
    audition_identity = (
        {
            "variant": audition.get("variant"),
            "mastered": audition.get("mastered"),
            "policy": audition.get("policy"),
            "receipt_document_sha256": audition.get(
                "receipt_document_sha256"
            ),
            "receipt": _path_free_file_identity(audition.get("receipt")),
            "wav": _path_free_file_identity(audition.get("wav")),
        }
        if isinstance(audition, Mapping)
        else None
    )
    return _document_hash(
        {
            "project_id": evidence.get("project_id"),
            "balanced_arrangement_cache_key": evidence.get(
                "balanced_arrangement_cache_key"
            ),
            "selection_manifest_sha256": evidence.get(
                "selection_manifest_sha256"
            ),
            "control": control_identity,
            "audition": audition_identity,
            "mix_policy": evidence.get("mix_policy"),
            "renderer_policy": evidence.get("renderer_policy"),
        }
    )


def _path_free_file_identity(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return {
        "bytes": value.get("bytes"),
        "sha256": value.get("sha256"),
    }


def _review_id(*, artifact_id: str, reviewer_session_id: str) -> str:
    return _document_hash(
        {
            "artifact_id": _require_sha256(
                artifact_id, label="mix feedback artifact identity"
            ),
            "reviewer_session_id": _require_sha256(
                reviewer_session_id,
                label="mix feedback reviewer/session identity",
            ),
        }
    )


def _reviewer_session_id(value: Any) -> str:
    key = _bounded_text(
        value,
        label="reviewer/session key",
        maximum=MAX_REVIEWER_SESSION_KEY_CHARACTERS,
    )
    return hashlib.sha256(
        b"sunofriend.mix-reviewer-session.v1\0" + key.encode("utf-8")
    ).hexdigest()


def _artifact_variant(value: Any) -> str:
    if not isinstance(value, str) or value not in ARTIFACT_VARIANTS:
        raise ValueError(
            "artifact variant must be one of: " + ", ".join(ARTIFACT_VARIANTS)
        )
    return value


def _evidence_paths(evidence: Mapping[str, Any]) -> list[str]:
    paths: list[str] = []
    for section_name, file_names in (
        ("control", ("receipt", "preview_wav")),
        ("audition", ("receipt", "wav")),
    ):
        section = evidence.get(section_name)
        if not isinstance(section, Mapping):
            continue
        for file_name in file_names:
            record = section.get(file_name)
            if isinstance(record, Mapping) and isinstance(record.get("path"), str):
                paths.append(str(record["path"]))
    return sorted(set(paths))


def _read_receipt(
    path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    record, document = _read_json_file(
        path,
        label="balanced mix receipt",
        maximum_bytes=_RECEIPT_MAXIMUM_BYTES,
    )
    return record, document


def _read_json_file(
    path: str | Path,
    *,
    label: str,
    maximum_bytes: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    canonical = _canonical_file_path(path)
    data, record = _read_regular_bytes(
        canonical,
        label=label,
        maximum_bytes=maximum_bytes,
    )
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON: {canonical}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return record, document


def _regular_file_record(
    path: str | Path,
    *,
    label: str,
    maximum_bytes: int,
) -> dict[str, Any]:
    canonical = _canonical_file_path(path)
    descriptor = _open_regular_file(canonical, label=label)
    try:
        before = os.fstat(descriptor)
        if before.st_size > maximum_bytes:
            raise ValueError(f"{label} exceeds the supported byte limit")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > maximum_bytes:
                raise ValueError(f"{label} exceeds the supported byte limit")
            digest.update(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    _require_unchanged_stat(before, after, total=total, label=label)
    return {
        "path": str(canonical),
        "bytes": total,
        "sha256": digest.hexdigest(),
    }


def _regular_wav_record(
    path: str | Path,
    *,
    label: str,
    maximum_bytes: int,
    require_pcm24: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    canonical = _canonical_file_path(path)
    descriptor = _open_regular_file(canonical, label=label)
    try:
        before = os.fstat(descriptor)
        if before.st_size > maximum_bytes:
            raise ValueError(f"{label} exceeds the supported byte limit")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > maximum_bytes:
                raise ValueError(f"{label} exceeds the supported byte limit")
            digest.update(block)
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            with os.fdopen(os.dup(descriptor), "rb") as handle:
                info = _listening_master_contract._soundfile_module().info(handle)
        except Exception as exc:
            raise ValueError(f"{label} is not readable audio") from exc
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    _require_unchanged_stat(before, after, total=total, label=label)
    sample_rate = int(info.samplerate)
    frames = int(info.frames)
    channels = int(info.channels)
    audio_info = {
        "format": str(info.format),
        "subtype": str(info.subtype),
        "sample_rate": sample_rate,
        "channels": channels,
        "frames": frames,
        "duration_seconds": (
            round(frames / sample_rate, 6) if sample_rate > 0 else 0.0
        ),
    }
    if (
        audio_info["format"] not in {"WAV", "WAVEX"}
        or sample_rate <= 0
        or frames <= 0
        or channels not in {1, 2}
        or (require_pcm24 and audio_info["subtype"] != "PCM_24")
    ):
        raise ValueError(f"{label} audio geometry is invalid")
    return {
        "path": str(canonical),
        "bytes": total,
        "sha256": digest.hexdigest(),
    }, audio_info


def _read_regular_bytes(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
) -> tuple[bytes, dict[str, Any]]:
    descriptor = _open_regular_file(path, label=label)
    chunks = []
    total = 0
    digest = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        if before.st_size > maximum_bytes:
            raise ValueError(f"{label} exceeds the supported byte limit")
        while True:
            block = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > maximum_bytes:
                raise ValueError(f"{label} exceeds the supported byte limit")
            digest.update(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    _require_unchanged_stat(before, after, total=total, label=label)
    return b"".join(chunks), {
        "path": str(path),
        "bytes": total,
        "sha256": digest.hexdigest(),
    }


def _canonical_file_path(value: str | Path) -> Path:
    expanded = Path(value).expanduser()
    absolute = Path(os.path.abspath(os.fspath(expanded)))
    try:
        if absolute.is_symlink():
            raise ValueError(f"evidence path must not be a symlink: {absolute}")
    except OSError as exc:
        raise ValueError(f"cannot inspect evidence path: {absolute}") from exc
    return absolute.parent.resolve() / absolute.name


def _open_regular_file(path: Path, *, label: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{label} is not a readable regular file: {path}") from exc
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ValueError(f"{label} is not a regular file: {path}")
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _require_unchanged_stat(
    before: os.stat_result,
    after: os.stat_result,
    *,
    total: int,
    label: str,
) -> None:
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after or total != after.st_size:
        raise ValueError(f"{label} changed while it was being read")


def _validate_file_record(value: Any, *, label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "path",
        "bytes",
        "sha256",
    }:
        raise ValueError(f"{label} record is invalid")
    path = value.get("path")
    byte_count = value.get("bytes")
    if (
        not isinstance(path, str)
        or not os.path.isabs(path)
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 0
    ):
        raise ValueError(f"{label} record is invalid")
    _require_sha256(value.get("sha256"), label=f"{label} SHA-256")


def _write_fresh_private_json(
    path: str | Path,
    document: Mapping[str, Any],
    *,
    label: str,
    protected_inputs: Sequence[str],
) -> dict[str, Any]:
    destination = _fresh_json_destination(path, label=label)
    protected = {Path(value) for value in protected_inputs}
    if destination in protected:
        raise ValueError(f"{label} output must not overwrite evidence")
    payload = (
        json.dumps(document, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    temporary_name = f".{destination.name}.{secrets.token_hex(12)}.tmp"
    parent_fd = _open_output_directory(destination.parent, label=label)
    published = False
    descriptor: int | None = None
    identity: tuple[int, int] | None = None
    try:
        try:
            descriptor = os.open(
                temporary_name,
                os.O_RDWR
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_fd,
            )
        except FileExistsError as exc:  # cryptographically unlikely
            raise RuntimeError(f"could not create private {label} output") from exc
        created = os.fstat(descriptor)
        identity = _file_identity(created)
        if not stat.S_ISREG(created.st_mode):
            raise RuntimeError(f"{label} temporary output is not a regular file")
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        output_record = _record_open_private_json(
            descriptor,
            destination=destination,
            identity=identity,
            maximum_bytes=_RECEIPT_MAXIMUM_BYTES,
            label=label,
        )
        try:
            os.link(
                temporary_name,
                destination.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise FileExistsError(f"{label} already exists: {destination}") from exc
        published = True
        _require_entry_identity(
            parent_fd,
            destination.name,
            identity,
            label=f"published {label}",
        )
        os.fsync(parent_fd)
        return output_record
    except Exception:
        if published and identity is not None:
            _unlink_if_identity(parent_fd, destination.name, identity)
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if identity is not None:
            _unlink_if_identity(parent_fd, temporary_name, identity)
        os.close(parent_fd)


def _fresh_json_destination(value: str | Path, *, label: str) -> Path:
    expanded = Path(value).expanduser()
    absolute = Path(os.path.abspath(os.fspath(expanded)))
    if absolute.suffix.lower() != ".json":
        raise ValueError(f"{label} output must end in .json")
    absolute.parent.mkdir(parents=True, exist_ok=True)
    destination = absolute.parent.resolve() / absolute.name
    return destination


def _open_output_directory(directory: Path, *, label: str) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(directory, flags)
    except OSError as exc:
        raise ValueError(f"{label} output directory is unsafe") from exc
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise ValueError(f"{label} output directory is invalid")
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _file_identity(value: os.stat_result) -> tuple[int, int]:
    return int(value.st_dev), int(value.st_ino)


def _require_entry_identity(
    directory_fd: int,
    name: str,
    identity: tuple[int, int],
    *,
    label: str,
) -> None:
    try:
        details = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeError(f"{label} disappeared") from exc
    if (
        _file_identity(details) != identity
        or not stat.S_ISREG(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o600
    ):
        raise RuntimeError(f"{label} identity or privacy changed")


def _unlink_if_identity(
    directory_fd: int,
    name: str,
    identity: tuple[int, int],
) -> None:
    try:
        details = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError:
        return
    if _file_identity(details) != identity:
        return
    try:
        os.unlink(name, dir_fd=directory_fd)
    except FileNotFoundError:
        return


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("could not write private JSON artifact")
        view = view[written:]


def _record_open_private_json(
    descriptor: int,
    *,
    destination: Path,
    identity: tuple[int, int],
    maximum_bytes: int,
    label: str,
) -> dict[str, Any]:
    before = os.fstat(descriptor)
    if (
        _file_identity(before) != identity
        or not stat.S_ISREG(before.st_mode)
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_size > maximum_bytes
    ):
        raise RuntimeError(f"{label} private output identity is invalid")
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    total = 0
    while True:
        block = os.read(descriptor, 1024 * 1024)
        if not block:
            break
        total += len(block)
        if total > maximum_bytes:
            raise ValueError(f"{label} exceeds the supported byte limit")
        digest.update(block)
    after = os.fstat(descriptor)
    _require_unchanged_stat(before, after, total=total, label=label)
    if _file_identity(after) != identity:
        raise RuntimeError(f"{label} private output identity changed")
    return {
        "path": str(destination),
        "bytes": total,
        "sha256": digest.hexdigest(),
    }


def _bounded_text(value: Any, *, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    text = value.strip()
    if (
        not text
        or len(text) > maximum
        or any(ord(character) < 32 for character in text)
    ):
        raise ValueError(f"{label} is missing or outside its supported bounds")
    return text


def _nonnegative_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _positive_int(value: Any, *, label: str) -> int:
    result = _nonnegative_int(value, label=label)
    if result <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return result


def _finite_number(value: Any, *, label: str) -> float | int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{label} must be a finite number")
    return value


def _require_sha256(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _document_hash(document: Mapping[str, Any]) -> str:
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "ARTIFACT_VARIANTS",
    "BALANCED_MIX_RECEIPT_SCHEMA",
    "BALANCED_CONTROL_VARIANT",
    "LISTENING_MASTER_VARIANT",
    "MAX_NOTES_CHARACTERS",
    "MAX_PROBLEM_TAGS",
    "MAX_REVIEWER_SESSION_KEY_CHARACTERS",
    "MIX_PROFILE_POLICY",
    "MIX_PROFILE_SCHEMA",
    "MIX_REVIEW_POLICY",
    "MIX_REVIEW_SCHEMA",
    "PROBLEM_TAGS",
    "RATING_AXES",
    "RATING_VALUES",
    "advisory_mix_history",
    "build_local_mix_profile",
    "load_local_mix_profile",
    "record_mix_feedback",
]
