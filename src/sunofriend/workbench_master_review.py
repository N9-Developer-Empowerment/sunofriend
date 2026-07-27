"""Blinded, receipt-bound review of a balanced control and Listening Master.

This module deliberately owns neither Workbench musical decisions nor product
artifacts.  It creates one bounded, level-matched listening window, stores an
anonymous explicit review in a private append-only ledger, and resolves the
hidden A/B identity only through a separate explicit operation.

The balanced control and Listening Master remain immutable.  Preparing or
playing review audio records no feedback.  Completing a review records only
the supplied human response, and resolving it creates only a path-free
resolution record.  Neither operation selects, ranks, promotes, or changes a
default.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import sqlite3
import stat
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .listening_master_contract import (
    LISTENING_MASTER_POLICY,
    verify_listening_master_artifacts,
)
from .workbench_listening_master import (
    WORKBENCH_LISTENING_MASTER_SCHEMA,
    _validated_balanced_binding,
)


MASTER_REVIEW_COMPARISON_SCHEMA = "sunofriend.workbench-listening-master-comparison.v1"
MASTER_REVIEW_AUDIO_SCHEMA = "sunofriend.workbench-listening-master-review-audio.v1"
MASTER_REVIEW_SCHEMA = "sunofriend.workbench-listening-master-review.v1"
MASTER_REVIEW_RESULT_SCHEMA = "sunofriend.workbench-listening-master-review-result.v1"
MASTER_REVIEW_POLICY = "blind-exact-window-fixed-rms-attenuation-only-v1"
MASTER_REVIEW_LEVEL_POLICY = "pairwise-fixed-window-rms-attenuation-only-v1"
MASTER_REVIEW_ASSIGNMENT_POLICY = "secret-random-per-comparison-v1"

BALANCED_CONTROL = "balanced_control"
LISTENING_MASTER = "listening_master"
CANDIDATE_A = "candidate_a"
CANDIDATE_B = "candidate_b"

MASTER_REVIEW_CHOICES = frozenset(
    {
        CANDIDATE_A,
        CANDIDATE_B,
        "equivalent",
        "neither",
        "cannot_tell",
    }
)
MASTER_REVIEW_PROBLEM_TAGS = frozenset(
    {
        "bass_too_loud",
        "bass_too_quiet",
        "clipping_or_distortion",
        "drums_too_loud",
        "drums_too_quiet",
        "dynamics_flat",
        "fatiguing",
        "harsh",
        "melody_masked",
        "muddy",
        "pumping",
        "thin",
        "too_loud",
        "too_quiet",
        "transients_dulled",
    }
)

MINIMUM_WINDOW_SECONDS = 0.5
MAXIMUM_WINDOW_SECONDS = 15.0
MINIMUM_RMS_DBFS = -60.0
MAXIMUM_ATTENUATION_DB = 18.0
MAXIMUM_FINAL_RMS_MISMATCH_DB = 0.05
MAXIMUM_NOTES_CHARACTERS = 2_000
MAXIMUM_REVIEWER_KEY_CHARACTERS = 128
MAXIMUM_PROBLEM_TAGS_PER_CANDIDATE = 8
MAXIMUM_AUDIO_BYTES = 4 * 1024 * 1024 * 1024
MAXIMUM_JSON_BYTES = 4 * 1024 * 1024
_FULL_SCALE_GUARD = 1.0
_AUDIO_DIRECTORY = "audio"
_DATABASE_NAME = "reviews.sqlite3"
_MANIFEST_NAME = "manifest.json"
_SHA256_CHARACTERS = frozenset("0123456789abcdef")

PREPARE_EFFECTS: dict[str, bool] = {
    "feedback_recorded": False,
    "review_record_created": False,
    "resolution_record_created": False,
    "source_audio_mutated": False,
    "balanced_control_mutated": False,
    "listening_master_mutated": False,
    "midi_mutated": False,
    "selection_changed": False,
    "automatic_selection": False,
    "automatic_ranking": False,
    "default_selection_changed": False,
    "pack_changed": False,
    "product_completion_changed": False,
}
REVIEW_EFFECTS: dict[str, bool] = {
    **PREPARE_EFFECTS,
    "feedback_recorded": True,
    "review_record_created": True,
}
RESOLUTION_EFFECTS: dict[str, bool] = {
    **PREPARE_EFFECTS,
    "resolution_record_created": True,
}


class WorkbenchMasterReviewConflictError(RuntimeError):
    """Raised when review state or receipt-bound evidence changed."""


class WorkbenchMasterReviewRevisionConflictError(RuntimeError):
    """Raised when an append uses a stale expected feedback revision."""

    def __init__(self, *, expected_revision: int, current_revision: int) -> None:
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        super().__init__(
            "Listening Master review revision conflict: "
            f"expected {expected_revision}, current revision is {current_revision}"
        )


class WorkbenchMasterReviewService:
    """Private local comparison, feedback, and resolution service."""

    def __init__(self, root: str | Path) -> None:
        self.root = _absolute_path(root)
        self.audio_root = self.root / _AUDIO_DIRECTORY
        self.database_path = self.root / _DATABASE_NAME
        _ensure_owner_only_directory(self.root)
        _ensure_owner_only_directory(self.audio_root)
        self._initialize()

    def prepare(
        self,
        *,
        project_id: str,
        balanced: Mapping[str, Any],
        listening_master: Mapping[str, Any],
        start_seconds: float,
        end_seconds: float,
        reviewer_session_key: str,
    ) -> dict[str, Any]:
        """Prepare one anonymous exact-frame review window.

        The returned document is path-free.  A loopback server can obtain a
        verified private media record separately with :meth:`media_record`.
        """

        reviewer_session_id = _reviewer_session_id(reviewer_session_key)
        evidence = _verified_artifact_evidence(
            project_id=project_id,
            balanced=balanced,
            listening_master=listening_master,
        )
        window = _review_window(
            start_seconds,
            end_seconds,
            sample_rate=int(evidence["geometry"]["sample_rate"]),
            total_frames=int(evidence["geometry"]["frames"]),
        )
        comparison = _comparison_document(evidence["public"], window)
        comparison_sha256 = _document_hash(comparison)
        session = self._get_or_create_session(
            project_id=str(comparison["project_id"]),
            comparison_sha256=comparison_sha256,
            binding=comparison,
        )
        manifest = self._prepare_audio(
            evidence=evidence,
            comparison=comparison,
            comparison_sha256=comparison_sha256,
            nonce=bytes(session["nonce"]),
            nonce_commitment=str(session["nonce_commitment"]),
        )
        review = self._latest_review(
            comparison_sha256=comparison_sha256,
            reviewer_session_id=reviewer_session_id,
        )
        if review is not None:
            _validate_stored_review(review)
            self._require_review_binding(review)
        return _public_prepared_document(
            comparison=comparison,
            comparison_sha256=comparison_sha256,
            nonce_commitment=str(session["nonce_commitment"]),
            manifest=manifest,
            current_review=review,
        )

    def media_record(
        self,
        comparison_sha256: str,
        candidate: str,
    ) -> dict[str, Any]:
        """Return one verified private audio record for loopback registration."""

        comparison_id = _sha256(comparison_sha256, label="comparison SHA-256")
        slot = _candidate_slot(candidate)
        session = self._session(comparison_id)
        manifest = self._load_audio_manifest(
            comparison_id,
            nonce=bytes(session["nonce"]),
            nonce_commitment=str(session["nonce_commitment"]),
        )
        record = manifest["candidates"][slot]["audio"]
        path = self.audio_root / comparison_id / str(record["name"])
        actual = _private_file_record(
            path,
            label=f"{slot} review audio",
            maximum_bytes=MAXIMUM_AUDIO_BYTES,
        )
        if _without_path(actual) != record:
            raise ValueError("Listening Master review audio changed")
        return actual

    def current(
        self,
        *,
        project_id: str,
        balanced: Mapping[str, Any],
        listening_master: Mapping[str, Any],
        comparison_sha256: str,
        reviewer_session_key: str,
    ) -> dict[str, Any]:
        """Return the latest blind review state without resolving A/B identity."""

        comparison_id = _sha256(comparison_sha256, label="comparison SHA-256")
        session = self._session(comparison_id)
        binding = _session_binding(session)
        self._require_current_binding(
            project_id=project_id,
            balanced=balanced,
            listening_master=listening_master,
            binding=binding,
            comparison_sha256=comparison_id,
        )
        manifest = self._load_audio_manifest(
            comparison_id,
            nonce=bytes(session["nonce"]),
            nonce_commitment=str(session["nonce_commitment"]),
        )
        reviewer_session_id = _reviewer_session_id(reviewer_session_key)
        review = self._latest_review(
            comparison_sha256=comparison_id,
            reviewer_session_id=reviewer_session_id,
        )
        if review is not None:
            _validate_stored_review(review)
            self._require_review_binding(review)
        return _public_prepared_document(
            comparison=binding,
            comparison_sha256=comparison_id,
            nonce_commitment=str(session["nonce_commitment"]),
            manifest=manifest,
            current_review=review,
        )

    def complete(
        self,
        *,
        project_id: str,
        balanced: Mapping[str, Any],
        listening_master: Mapping[str, Any],
        comparison_sha256: str,
        reviewer_session_key: str,
        expected_revision: int,
        heard: Mapping[str, Any],
        choice: str,
        problem_tags: Mapping[str, Sequence[str]],
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Append one complete blind review without revealing A/B identity."""

        comparison_id = _sha256(comparison_sha256, label="comparison SHA-256")
        session = self._session(comparison_id)
        binding = _session_binding(session)
        self._require_current_binding(
            project_id=project_id,
            balanced=balanced,
            listening_master=listening_master,
            binding=binding,
            comparison_sha256=comparison_id,
        )
        self._load_audio_manifest(
            comparison_id,
            nonce=bytes(session["nonce"]),
            nonce_commitment=str(session["nonce_commitment"]),
        )

        reviewer_session_id = _reviewer_session_id(reviewer_session_key)
        checked_revision = _nonnegative_int(
            expected_revision, label="expected revision"
        )
        response = {
            "heard": _heard(heard),
            "choice": _choice(choice),
            "problem_tags": _problem_tag_map(problem_tags),
            "notes": _notes(notes),
        }
        review_id = _document_hash(
            {
                "schema": MASTER_REVIEW_SCHEMA,
                "comparison_sha256": comparison_id,
                "reviewer_session_id": reviewer_session_id,
                "revision": checked_revision + 1,
                "response": response,
            }
        )
        document_without_hash = {
            "schema": MASTER_REVIEW_SCHEMA,
            "status": "reviewed",
            "blind": True,
            "policy": MASTER_REVIEW_POLICY,
            "review_id": review_id,
            "comparison_sha256": comparison_id,
            "reviewer_session_id": reviewer_session_id,
            "revision": checked_revision + 1,
            "nonce_commitment": str(session["nonce_commitment"]),
            "evidence": binding,
            "response": response,
            "privacy": {
                "local_only": True,
                "reviewer_session_key_stored": False,
                "notes_private": True,
                "notes_may_contain_identifying_material": bool(response["notes"]),
            },
            "effects": dict(REVIEW_EFFECTS),
        }
        document = {
            **document_without_hash,
            "review_sha256": _document_hash(document_without_hash),
        }
        self._append_review(
            comparison_sha256=comparison_id,
            reviewer_session_id=reviewer_session_id,
            expected_revision=checked_revision,
            review=document,
        )
        return _json_copy(document)

    def review(self, review_id: str) -> dict[str, Any]:
        """Return one verified stored blind review without resolving identity."""

        document = self._review(_sha256(review_id, label="review identity"))
        _validate_stored_review(document)
        self._require_review_binding(document)
        return _json_copy(document)

    def resolution(self, review_id: str) -> dict[str, Any] | None:
        """Return an existing verified resolution, or ``None`` before resolve."""

        checked_review_id = _sha256(review_id, label="review identity")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM review_resolutions WHERE review_id = ?",
                (checked_review_id,),
            ).fetchone()
        if row is None:
            return None
        value = json.loads(str(row[0]))
        if not isinstance(value, dict):
            raise ValueError("Listening Master review resolution is invalid")
        _validate_stored_resolution(value)
        self._require_resolution_binding(value)
        return _json_copy(value)

    def resolve(
        self,
        *,
        project_id: str,
        balanced: Mapping[str, Any],
        listening_master: Mapping[str, Any],
        review_id: str,
    ) -> dict[str, Any]:
        """Resolve one stored blind review without changing a product artifact."""

        checked_review_id = _sha256(review_id, label="review identity")
        review = self._review(checked_review_id)
        _validate_stored_review(review)
        self._require_review_binding(review)
        comparison_sha256 = str(review["comparison_sha256"])
        session = self._session(comparison_sha256)
        binding = _session_binding(session)
        if review["evidence"] != binding:
            raise ValueError("Listening Master review evidence changed")
        self._require_current_binding(
            project_id=project_id,
            balanced=balanced,
            listening_master=listening_master,
            binding=binding,
            comparison_sha256=comparison_sha256,
        )
        manifest = self._load_audio_manifest(
            comparison_sha256,
            nonce=bytes(session["nonce"]),
            nonce_commitment=str(session["nonce_commitment"]),
        )
        mapping = _blind_mapping(bytes(session["nonce"]), comparison_sha256)
        if manifest["private_assignment"] != mapping:
            raise ValueError("Listening Master review assignment changed")

        choice = str(review["response"]["choice"])
        resolved_choice = mapping[choice] if choice in mapping else choice
        slot_tags = review["response"]["problem_tags"]
        tags_by_identity = {
            mapping[CANDIDATE_A]: list(slot_tags[CANDIDATE_A]),
            mapping[CANDIDATE_B]: list(slot_tags[CANDIDATE_B]),
        }
        result_without_hash = {
            "schema": MASTER_REVIEW_RESULT_SCHEMA,
            "status": "complete",
            "blind_review": True,
            "policy": MASTER_REVIEW_POLICY,
            "review_id": checked_review_id,
            "review_sha256": review["review_sha256"],
            "comparison_sha256": comparison_sha256,
            "nonce_commitment": str(session["nonce_commitment"]),
            "assignment_nonce": bytes(session["nonce"]).hex(),
            "assignment": _json_copy(mapping),
            "resolved_choice": resolved_choice,
            "problem_tags": {
                BALANCED_CONTROL: tags_by_identity[BALANCED_CONTROL],
                LISTENING_MASTER: tags_by_identity[LISTENING_MASTER],
            },
            "notes_recorded": bool(review["response"]["notes"]),
            "promotion_allowed": False,
            "default_changed": False,
            "effects": dict(RESOLUTION_EFFECTS),
        }
        result = {
            **result_without_hash,
            "result_sha256": _document_hash(result_without_hash),
        }
        _validate_stored_resolution(result)
        self._require_resolution_binding(result)
        return self._save_or_load_resolution(result)

    def _prepare_audio(
        self,
        *,
        evidence: Mapping[str, Any],
        comparison: Mapping[str, Any],
        comparison_sha256: str,
        nonce: bytes,
        nonce_commitment: str,
    ) -> dict[str, Any]:
        existing = self._load_audio_manifest(
            comparison_sha256,
            nonce=nonce,
            nonce_commitment=nonce_commitment,
            missing_ok=True,
        )
        if existing is not None:
            return existing

        final = self.audio_root / comparison_sha256
        if final.exists():
            winner = self._load_audio_manifest(
                comparison_sha256,
                nonce=nonce,
                nonce_commitment=nonce_commitment,
            )
            if winner is None:  # pragma: no cover - missing_ok is false
                raise RuntimeError(
                    "Listening Master review audio publication disappeared"
                )
            return winner
        work = Path(
            tempfile.mkdtemp(
                prefix=f".{comparison_sha256}.building-",
                dir=self.audio_root,
            )
        )
        work.chmod(0o700)
        try:
            window = comparison["window"]
            start_frame = int(window["start_frame"])
            frame_count = int(window["frame_count"])
            control = _read_audio_window(
                Path(str(evidence["private"]["control_path"])),
                expected=evidence["private"]["control_record"],
                start_frame=start_frame,
                frame_count=frame_count,
                label="balanced control",
            )
            master = _read_audio_window(
                Path(str(evidence["private"]["master_path"])),
                expected=evidence["private"]["master_record"],
                start_frame=start_frame,
                frame_count=frame_count,
                label="Listening Master",
            )
            matched, level = _pairwise_level_match(
                {
                    BALANCED_CONTROL: control,
                    LISTENING_MASTER: master,
                }
            )
            mapping = _blind_mapping(nonce, comparison_sha256)
            candidate_rows: dict[str, Any] = {}
            for slot in (CANDIDATE_A, CANDIDATE_B):
                identity = mapping[slot]
                output = work / f"{slot.replace('_', '-')}.wav"
                _write_pcm16(
                    output,
                    matched[identity],
                    int(comparison["geometry"]["sample_rate"]),
                )
                record, audio_info = _verified_output_audio(
                    output,
                    expected_frames=frame_count,
                    expected_sample_rate=int(comparison["geometry"]["sample_rate"]),
                    expected_channels=int(comparison["geometry"]["channels"]),
                )
                candidate_rows[slot] = {
                    "identity": identity,
                    "audio": _without_path(record),
                    "sample_rate": audio_info["sample_rate"],
                    "channels": audio_info["channels"],
                    "frames": audio_info["frames"],
                    "rms_dbfs": audio_info["rms_dbfs"],
                    "sample_peak_dbfs": audio_info["sample_peak_dbfs"],
                    "applied_gain_db": level["inputs"][identity]["applied_gain_db"],
                }
            mismatch = abs(
                float(candidate_rows[CANDIDATE_A]["rms_dbfs"])
                - float(candidate_rows[CANDIDATE_B]["rms_dbfs"])
            )
            if mismatch > MAXIMUM_FINAL_RMS_MISMATCH_DB:
                raise RuntimeError(
                    "Listening Master review PCM16 level mismatch exceeds "
                    f"{MAXIMUM_FINAL_RMS_MISMATCH_DB:.2f} dB"
                )
            level["final_pcm16"] = {
                "candidate_a_rms_dbfs": candidate_rows[CANDIDATE_A]["rms_dbfs"],
                "candidate_b_rms_dbfs": candidate_rows[CANDIDATE_B]["rms_dbfs"],
                "mismatch_db": round(mismatch, 6),
                "within_tolerance": True,
            }

            # Re-verify both immutable artifact chains after decoding and before
            # publication.  A changed input leaves no review cache entry.
            current = _verified_artifact_evidence(
                project_id=str(comparison["project_id"]),
                balanced=evidence["private"]["balanced"],
                listening_master=evidence["private"]["listening_master"],
            )
            if current["public"] != evidence["public"]:
                raise WorkbenchMasterReviewConflictError(
                    "Listening Master review evidence changed during preparation"
                )

            manifest_without_hash = {
                "schema": MASTER_REVIEW_AUDIO_SCHEMA,
                "comparison_sha256": comparison_sha256,
                "comparison_binding_sha256": _document_hash(comparison),
                "nonce_commitment": nonce_commitment,
                "assignment_policy": MASTER_REVIEW_ASSIGNMENT_POLICY,
                "private_assignment": mapping,
                "window": _json_copy(comparison["window"]),
                "level_match": level,
                "candidates": candidate_rows,
                "path_free_manifest": True,
                "private_audio": True,
                "effects": dict(PREPARE_EFFECTS),
            }
            manifest = {
                **manifest_without_hash,
                "manifest_sha256": _document_hash(manifest_without_hash),
            }
            _write_private_json(work / _MANIFEST_NAME, manifest)
            try:
                os.replace(work, final)
            except OSError:
                # Another request may have published the exact same immutable
                # comparison after this worker's initial cache check.  Reuse
                # only a fully verified winner; any other publication failure
                # still fails closed.
                if not final.exists():
                    raise
                winner = self._load_audio_manifest(
                    comparison_sha256,
                    nonce=nonce,
                    nonce_commitment=nonce_commitment,
                )
                if winner is None:  # pragma: no cover - missing_ok is false
                    raise RuntimeError(
                        "Listening Master review audio publication disappeared"
                    )
                _remove_private_tree(work)
                return winner
            _fsync_directory(self.audio_root)
        except BaseException:
            _remove_private_tree(work)
            raise
        loaded = self._load_audio_manifest(
            comparison_sha256,
            nonce=nonce,
            nonce_commitment=nonce_commitment,
        )
        if loaded is None:  # pragma: no cover - defensive typed boundary
            raise RuntimeError("Listening Master review audio publication failed")
        return loaded

    def _load_audio_manifest(
        self,
        comparison_sha256: str,
        *,
        nonce: bytes,
        nonce_commitment: str,
        missing_ok: bool = False,
    ) -> dict[str, Any] | None:
        directory = self.audio_root / comparison_sha256
        if not directory.exists():
            if missing_ok:
                return None
            raise ValueError("Listening Master review audio is unavailable")
        _require_owner_only_directory(directory)
        manifest_path = directory / _MANIFEST_NAME
        manifest = _read_private_json(manifest_path)
        session_binding = _session_binding(self._session(comparison_sha256))
        expected_fields = {
            "schema",
            "comparison_sha256",
            "comparison_binding_sha256",
            "nonce_commitment",
            "assignment_policy",
            "private_assignment",
            "window",
            "level_match",
            "candidates",
            "path_free_manifest",
            "private_audio",
            "effects",
            "manifest_sha256",
        }
        unsigned = {
            key: value for key, value in manifest.items() if key != "manifest_sha256"
        }
        expected_mapping = _blind_mapping(nonce, comparison_sha256)
        if (
            set(manifest) != expected_fields
            or manifest.get("schema") != MASTER_REVIEW_AUDIO_SCHEMA
            or manifest.get("comparison_sha256") != comparison_sha256
            or manifest.get("comparison_binding_sha256") != comparison_sha256
            or manifest.get("nonce_commitment") != nonce_commitment
            or manifest.get("assignment_policy") != MASTER_REVIEW_ASSIGNMENT_POLICY
            or manifest.get("private_assignment") != expected_mapping
            or manifest.get("effects") != PREPARE_EFFECTS
            or manifest.get("path_free_manifest") is not True
            or manifest.get("private_audio") is not True
            or manifest.get("manifest_sha256") != _document_hash(unsigned)
            or _document_hash(session_binding) != comparison_sha256
            or manifest.get("window") != session_binding.get("window")
            or not _path_free_document(manifest)
        ):
            raise ValueError("Listening Master review audio manifest is invalid")
        candidates = manifest.get("candidates")
        if not isinstance(candidates, Mapping) or set(candidates) != {
            CANDIDATE_A,
            CANDIDATE_B,
        }:
            raise ValueError("Listening Master review candidates are invalid")
        for slot in (CANDIDATE_A, CANDIDATE_B):
            row = candidates[slot]
            expected_row_fields = {
                "identity",
                "audio",
                "sample_rate",
                "channels",
                "frames",
                "rms_dbfs",
                "sample_peak_dbfs",
                "applied_gain_db",
            }
            if (
                not isinstance(row, Mapping)
                or set(row) != expected_row_fields
                or row.get("identity") != expected_mapping[slot]
                or not isinstance(row.get("audio"), Mapping)
                or set(row["audio"]) != {"name", "bytes", "sha256"}
                or row["audio"].get("name") != f"{slot.replace('_', '-')}.wav"
            ):
                raise ValueError("Listening Master review candidate is invalid")
            audio_path = directory / str(row["audio"].get("name", ""))
            actual, audio_info = _verified_output_audio(
                audio_path,
                expected_frames=int(session_binding["window"]["frame_count"]),
                expected_sample_rate=int(session_binding["geometry"]["sample_rate"]),
                expected_channels=int(session_binding["geometry"]["channels"]),
            )
            if _without_path(actual) != row["audio"] or any(
                row[key] != audio_info[key]
                for key in (
                    "sample_rate",
                    "channels",
                    "frames",
                    "rms_dbfs",
                    "sample_peak_dbfs",
                )
            ):
                raise ValueError("Listening Master review audio changed")
            identity = str(row["identity"])
            level_inputs = manifest.get("level_match", {}).get("inputs", {})
            level_row = (
                level_inputs.get(identity)
                if isinstance(level_inputs, Mapping)
                else None
            )
            if (
                not isinstance(level_row, Mapping)
                or row["applied_gain_db"] != level_row.get("applied_gain_db")
                or not isinstance(row["applied_gain_db"], (int, float))
                or not -MAXIMUM_ATTENUATION_DB <= float(row["applied_gain_db"]) <= 0.0
            ):
                raise ValueError("Listening Master review level evidence is invalid")
        mismatch = abs(
            float(candidates[CANDIDATE_A]["rms_dbfs"])
            - float(candidates[CANDIDATE_B]["rms_dbfs"])
        )
        if mismatch > MAXIMUM_FINAL_RMS_MISMATCH_DB:
            raise ValueError("Listening Master review audio levels changed")
        return manifest

    def _require_current_binding(
        self,
        *,
        project_id: str,
        balanced: Mapping[str, Any],
        listening_master: Mapping[str, Any],
        binding: Mapping[str, Any],
        comparison_sha256: str,
    ) -> None:
        current = _verified_artifact_evidence(
            project_id=project_id,
            balanced=balanced,
            listening_master=listening_master,
        )
        window = binding.get("window")
        if not isinstance(window, Mapping):
            raise ValueError("Listening Master review window is invalid")
        current_comparison = _comparison_document(current["public"], window)
        if (
            current_comparison != binding
            or _document_hash(current_comparison) != comparison_sha256
        ):
            raise WorkbenchMasterReviewConflictError(
                "Listening Master review evidence is no longer current"
            )

    def _get_or_create_session(
        self,
        *,
        project_id: str,
        comparison_sha256: str,
        binding: Mapping[str, Any],
    ) -> dict[str, Any]:
        nonce = secrets.token_bytes(32)
        commitment = _nonce_commitment(nonce, comparison_sha256)
        binding_json = _canonical_json(binding)
        created_at = _utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT project_id, binding_json, nonce, nonce_commitment, created_at
                FROM comparison_sessions
                WHERE comparison_sha256 = ?
                """,
                (comparison_sha256,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO comparison_sessions (
                        comparison_sha256, project_id, binding_json, nonce,
                        nonce_commitment, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        comparison_sha256,
                        project_id,
                        binding_json,
                        nonce,
                        commitment,
                        created_at,
                    ),
                )
                row = (
                    project_id,
                    binding_json,
                    nonce,
                    commitment,
                    created_at,
                )
        result = {
            "project_id": str(row[0]),
            "binding_json": str(row[1]),
            "nonce": bytes(row[2]),
            "nonce_commitment": str(row[3]),
            "created_at": str(row[4]),
        }
        if (
            result["project_id"] != project_id
            or result["binding_json"] != binding_json
            or len(result["nonce"]) != 32
            or result["nonce_commitment"]
            != _nonce_commitment(result["nonce"], comparison_sha256)
        ):
            raise ValueError("Listening Master review session is invalid")
        return result

    def _session(self, comparison_sha256: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT project_id, binding_json, nonce, nonce_commitment, created_at
                FROM comparison_sessions
                WHERE comparison_sha256 = ?
                """,
                (comparison_sha256,),
            ).fetchone()
        if row is None:
            raise ValueError("Listening Master review was not prepared")
        result = {
            "project_id": str(row[0]),
            "binding_json": str(row[1]),
            "nonce": bytes(row[2]),
            "nonce_commitment": str(row[3]),
            "created_at": str(row[4]),
        }
        if len(result["nonce"]) != 32 or result[
            "nonce_commitment"
        ] != _nonce_commitment(result["nonce"], comparison_sha256):
            raise ValueError("Listening Master review session is invalid")
        return result

    def _append_review(
        self,
        *,
        comparison_sha256: str,
        reviewer_session_id: str,
        expected_revision: int,
        review: Mapping[str, Any],
    ) -> None:
        payload = _canonical_json(review)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT revision
                FROM review_events
                WHERE comparison_sha256 = ? AND reviewer_session_id = ?
                ORDER BY revision DESC
                LIMIT 1
                """,
                (comparison_sha256, reviewer_session_id),
            ).fetchone()
            current_revision = int(row[0]) if row is not None else 0
            if current_revision != expected_revision:
                raise WorkbenchMasterReviewRevisionConflictError(
                    expected_revision=expected_revision,
                    current_revision=current_revision,
                )
            connection.execute(
                """
                INSERT INTO review_events (
                    review_id, comparison_sha256, reviewer_session_id,
                    revision, created_at, review_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(review["review_id"]),
                    comparison_sha256,
                    reviewer_session_id,
                    int(review["revision"]),
                    _utc_now(),
                    payload,
                ),
            )

    def _review(self, review_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT comparison_sha256, reviewer_session_id, revision,
                       review_json
                FROM review_events
                WHERE review_id = ?
                """,
                (review_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Listening Master review does not exist")
        value = json.loads(str(row[3]))
        if (
            not isinstance(value, dict)
            or value.get("review_id") != review_id
            or value.get("comparison_sha256") != row[0]
            or value.get("reviewer_session_id") != row[1]
            or value.get("revision") != row[2]
        ):
            raise ValueError("Listening Master review record is invalid")
        return value

    def _latest_review(
        self,
        *,
        comparison_sha256: str,
        reviewer_session_id: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT review_id, revision, review_json
                FROM review_events
                WHERE comparison_sha256 = ? AND reviewer_session_id = ?
                ORDER BY revision DESC
                LIMIT 1
                """,
                (comparison_sha256, reviewer_session_id),
            ).fetchone()
        if row is None:
            return None
        value = json.loads(str(row[2]))
        if (
            not isinstance(value, dict)
            or value.get("review_id") != row[0]
            or value.get("comparison_sha256") != comparison_sha256
            or value.get("reviewer_session_id") != reviewer_session_id
            or value.get("revision") != row[1]
        ):
            raise ValueError("Listening Master review record is invalid")
        return value

    def _save_or_load_resolution(self, result: Mapping[str, Any]) -> dict[str, Any]:
        review_id = str(result["review_id"])
        result_json = _canonical_json(result)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT result_json FROM review_resolutions WHERE review_id = ?",
                (review_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO review_resolutions (
                        review_id, result_sha256, created_at, result_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        review_id,
                        str(result["result_sha256"]),
                        _utc_now(),
                        result_json,
                    ),
                )
                return _json_copy(result)
        existing = json.loads(str(row[0]))
        if existing != result:
            raise ValueError("Listening Master review resolution changed")
        return existing

    def _require_resolution_binding(
        self,
        result: Mapping[str, Any],
    ) -> None:
        review = self._review(str(result["review_id"]))
        _validate_stored_review(review)
        self._require_review_binding(review)
        session = self._session(str(result["comparison_sha256"]))
        mapping = _blind_mapping(
            bytes(session["nonce"]),
            str(result["comparison_sha256"]),
        )
        choice = str(review["response"]["choice"])
        resolved_choice = mapping[choice] if choice in mapping else choice
        slot_tags = review["response"]["problem_tags"]
        expected_tags = {
            mapping[CANDIDATE_A]: list(slot_tags[CANDIDATE_A]),
            mapping[CANDIDATE_B]: list(slot_tags[CANDIDATE_B]),
        }
        if (
            result["assignment"] != mapping
            or result["review_sha256"] != review["review_sha256"]
            or result["assignment_nonce"] != bytes(session["nonce"]).hex()
            or result["nonce_commitment"] != session["nonce_commitment"]
            or result["nonce_commitment"]
            != _nonce_commitment(
                bytes.fromhex(str(result["assignment_nonce"])),
                str(result["comparison_sha256"]),
            )
            or result["resolved_choice"] != resolved_choice
            or result["problem_tags"] != expected_tags
            or result["notes_recorded"] is not bool(review["response"]["notes"])
        ):
            raise ValueError("Listening Master review resolution binding is invalid")

    def _require_review_binding(self, review: Mapping[str, Any]) -> None:
        comparison_sha256 = str(review["comparison_sha256"])
        session = self._session(comparison_sha256)
        binding = _session_binding(session)
        if (
            review["evidence"] != binding
            or _document_hash(binding) != comparison_sha256
            or review["nonce_commitment"] != session["nonce_commitment"]
        ):
            raise ValueError("Listening Master review binding is invalid")

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS comparison_sessions (
                    comparison_sha256 TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    binding_json TEXT NOT NULL,
                    nonce BLOB NOT NULL,
                    nonce_commitment TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS review_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_id TEXT NOT NULL UNIQUE,
                    comparison_sha256 TEXT NOT NULL,
                    reviewer_session_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision > 0),
                    created_at TEXT NOT NULL,
                    review_json TEXT NOT NULL,
                    UNIQUE (
                        comparison_sha256, reviewer_session_id, revision
                    ),
                    FOREIGN KEY (comparison_sha256)
                        REFERENCES comparison_sessions(comparison_sha256)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS review_events_context
                ON review_events (
                    comparison_sha256, reviewer_session_id, revision
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS review_resolutions (
                    review_id TEXT PRIMARY KEY,
                    result_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    FOREIGN KEY (review_id) REFERENCES review_events(review_id)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        _ensure_owner_only_directory(self.root)
        connection = sqlite3.connect(str(self.database_path), timeout=10.0)
        try:
            self.database_path.chmod(0o600)
            _require_owner_only_regular_file(self.database_path)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
        except Exception:
            connection.close()
            raise
        return connection


def _verified_artifact_evidence(
    *,
    project_id: str,
    balanced: Mapping[str, Any],
    listening_master: Mapping[str, Any],
) -> dict[str, Any]:
    checked_project_id = _bounded_text(project_id, label="project_id", maximum=128)
    balanced_binding = _validated_balanced_binding(balanced)
    control_stored = balanced_binding["stored_balanced"]
    control_receipt = control_stored["receipt"]
    if control_receipt.get("project_id") != checked_project_id:
        raise ValueError("balanced control project_id does not match")
    preview_receipt = control_receipt.get("preview")
    if (
        not isinstance(preview_receipt, Mapping)
        or preview_receipt.get("filename") != control_stored["preview"]["name"]
        or preview_receipt.get("bytes") != control_stored["preview"]["bytes"]
        or preview_receipt.get("sha256") != control_stored["preview"]["sha256"]
    ):
        raise ValueError("balanced control preview receipt is invalid")
    control_directory = Path(str(control_stored["preview"]["path"])).parent
    if control_directory != Path(
        str(control_stored["report"]["path"])
    ).parent or control_directory.name != str(control_stored["cache_key"]):
        raise ValueError("balanced control cache scope is invalid")

    required_master_fields = {
        "schema",
        "cache_key",
        "manifest_sha256",
        "selection_manifest_sha256",
        "balanced_arrangement_manifest_sha256",
        "balanced_arrangement_cache_key",
        "balanced_preview_sha256",
        "balanced_report_sha256",
        "policy",
        "mastered",
        "release_master",
        "master",
        "receipt",
    }
    if not isinstance(listening_master, Mapping) or not required_master_fields <= set(
        listening_master
    ):
        raise ValueError("Listening Master artifact is incomplete")
    if (
        listening_master.get("schema") != WORKBENCH_LISTENING_MASTER_SCHEMA
        or listening_master.get("policy") != LISTENING_MASTER_POLICY
        or listening_master.get("mastered") is not True
        or listening_master.get("release_master") is not False
        or listening_master.get("selection_manifest_sha256")
        != control_stored["selection_manifest_sha256"]
        or listening_master.get("balanced_arrangement_manifest_sha256")
        != control_stored["manifest_sha256"]
        or listening_master.get("balanced_arrangement_cache_key")
        != control_stored["cache_key"]
        or listening_master.get("balanced_preview_sha256")
        != control_stored["preview"]["sha256"]
        or listening_master.get("balanced_report_sha256")
        != control_stored["report"]["sha256"]
    ):
        raise ValueError("Listening Master is not bound to the balanced control")
    master_cache_key = _sha256(
        listening_master.get("cache_key"), label="Listening Master cache key"
    )
    master_manifest_sha256 = _sha256(
        listening_master.get("manifest_sha256"),
        label="Listening Master manifest SHA-256",
    )
    master_record = _validated_private_record(
        listening_master.get("master"),
        label="Listening Master WAV",
    )
    receipt_record = _validated_private_record(
        listening_master.get("receipt"),
        label="Listening Master receipt",
    )
    master_path = Path(str(master_record["path"]))
    receipt_path = Path(str(receipt_record["path"]))
    if (
        master_path.suffix.lower() != ".wav"
        or receipt_path.suffix.lower() != ".json"
        or master_path.parent != receipt_path.parent
        or master_path.parent.name != master_cache_key
    ):
        raise ValueError("Listening Master cache scope is invalid")
    verification = verify_listening_master_artifacts(
        Path(str(control_stored["preview"]["path"])),
        master_path,
        receipt_path,
    )
    if (
        verification.get("policy") != LISTENING_MASTER_POLICY
        or verification.get("mastered") is not True
        or verification.get("release_master") is not False
        or verification["source"]["sha256"] != control_stored["preview"]["sha256"]
        or verification["source"]["bytes"] != control_stored["preview"]["bytes"]
        or verification["master"]["sha256"] != master_record["sha256"]
        or verification["master"]["bytes"] != master_record["bytes"]
        or verification["receipt_file"]["sha256"] != receipt_record["sha256"]
        or verification["receipt_file"]["bytes"] != receipt_record["bytes"]
    ):
        raise ValueError("Listening Master verification does not match artifacts")
    geometry = {
        key: verification["source"][key]
        for key in ("sample_rate", "channels", "frames", "duration_seconds")
    }
    if any(verification["master"][key] != value for key, value in geometry.items()):
        raise ValueError("Listening Master changed the balanced control horizon")

    public = {
        "project_id": checked_project_id,
        "selection_manifest_sha256": control_stored["selection_manifest_sha256"],
        "geometry": geometry,
        "balanced_control": {
            "schema": control_stored["schema"],
            "cache_key": control_stored["cache_key"],
            "manifest_sha256": control_stored["manifest_sha256"],
            "policy": control_stored["policy"],
            "mastered": False,
            "preview": _without_path(control_stored["preview"]),
            "report": _without_path(control_stored["report"]),
            "receipt_sha256": control_receipt["receipt_sha256"],
        },
        "listening_master": {
            "schema": listening_master["schema"],
            "cache_key": master_cache_key,
            "manifest_sha256": master_manifest_sha256,
            "policy": LISTENING_MASTER_POLICY,
            "mastered": True,
            "release_master": False,
            "wav": _without_path(master_record),
            "receipt": _without_path(receipt_record),
            "receipt_document_sha256": verification["receipt_document_sha256"],
        },
    }
    return {
        "public": public,
        "geometry": geometry,
        "private": {
            "balanced": balanced,
            "listening_master": listening_master,
            "control_path": control_stored["preview"]["path"],
            "control_record": control_stored["preview"],
            "master_path": master_record["path"],
            "master_record": master_record,
        },
    }


def _comparison_document(
    evidence: Mapping[str, Any],
    window: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": MASTER_REVIEW_COMPARISON_SCHEMA,
        "project_id": evidence["project_id"],
        "selection_manifest_sha256": evidence["selection_manifest_sha256"],
        "balanced_control": _json_copy(evidence["balanced_control"]),
        "listening_master": _json_copy(evidence["listening_master"]),
        "geometry": _json_copy(evidence["geometry"]),
        "window": _json_copy(window),
        "policy": {
            "name": MASTER_REVIEW_POLICY,
            "level_match": MASTER_REVIEW_LEVEL_POLICY,
            "assignment": MASTER_REVIEW_ASSIGNMENT_POLICY,
            "candidate_identity_hidden_until_resolution": True,
            "minimum_rms_dbfs": MINIMUM_RMS_DBFS,
            "maximum_attenuation_db": MAXIMUM_ATTENUATION_DB,
            "maximum_final_rms_mismatch_db": (MAXIMUM_FINAL_RMS_MISMATCH_DB),
            "level_claim": (
                "fixed-window sample RMS attenuation only; not LUFS, true "
                "peak, perceived-loudness matching, or mastering"
            ),
            "source_audio_rewritten": False,
            "product_audio_rewritten": False,
            "time_shift_seconds": 0.0,
            "time_stretch_ratio": 1.0,
            "limiter_used": False,
            "compression_used": False,
            "equalisation_used": False,
        },
    }


def _public_prepared_document(
    *,
    comparison: Mapping[str, Any],
    comparison_sha256: str,
    nonce_commitment: str,
    manifest: Mapping[str, Any],
    current_review: Mapping[str, Any] | None,
) -> dict[str, Any]:
    candidates = {}
    for slot in (CANDIDATE_A, CANDIDATE_B):
        row = manifest["candidates"][slot]
        candidates[slot] = {
            "audio": _json_copy(row["audio"]),
            "sample_rate": row["sample_rate"],
            "channels": row["channels"],
            "frames": row["frames"],
        }
    response = (
        _json_copy(current_review["response"]) if current_review is not None else None
    )
    current_revision = (
        int(current_review["revision"]) if current_review is not None else 0
    )
    review_state = {
        "status": "reviewed" if current_review is not None else "unreviewed",
        "reviewed": current_review is not None,
        "current_revision": current_revision,
        "review_id": (
            str(current_review["review_id"]) if current_review is not None else None
        ),
        "review_sha256": (
            str(current_review["review_sha256"]) if current_review is not None else None
        ),
        "response": response,
    }
    return {
        "schema": MASTER_REVIEW_COMPARISON_SCHEMA,
        "status": review_state["status"],
        "blind": True,
        "review_required": True,
        "comparison_sha256": comparison_sha256,
        "nonce_commitment": nonce_commitment,
        "assignment_policy": MASTER_REVIEW_ASSIGNMENT_POLICY,
        "artifact_hashes": {
            "balanced_control_preview_sha256": comparison["balanced_control"][
                "preview"
            ]["sha256"],
            "listening_master_wav_sha256": comparison["listening_master"]["wav"][
                "sha256"
            ],
            "listening_master_receipt_sha256": comparison["listening_master"][
                "receipt"
            ]["sha256"],
        },
        "window": _json_copy(comparison["window"]),
        "policy": _json_copy(comparison["policy"]),
        "candidates": candidates,
        "review_state": review_state,
        "heard": (
            _json_copy(response["heard"])
            if response is not None
            else {CANDIDATE_A: False, CANDIDATE_B: False}
        ),
        "choice": response["choice"] if response is not None else None,
        "problem_tags": (
            _json_copy(response["problem_tags"])
            if response is not None
            else {CANDIDATE_A: [], CANDIDATE_B: []}
        ),
        "notes": response["notes"] if response is not None else "",
        "current_revision": current_revision,
        "effects": dict(PREPARE_EFFECTS),
    }


def _review_window(
    start_seconds: Any,
    end_seconds: Any,
    *,
    sample_rate: int,
    total_frames: int,
) -> dict[str, Any]:
    start = _finite(start_seconds, label="review start")
    end = _finite(end_seconds, label="review end")
    if start < 0 or end <= start:
        raise ValueError("Listening Master review window is invalid")
    duration = end - start
    if not MINIMUM_WINDOW_SECONDS <= duration <= MAXIMUM_WINDOW_SECONDS:
        raise ValueError(
            "Listening Master review duration must be between "
            f"{MINIMUM_WINDOW_SECONDS:.1f} and {MAXIMUM_WINDOW_SECONDS:.1f} seconds"
        )
    start_frame = round(start * sample_rate)
    end_frame = round(end * sample_rate)
    if start_frame < 0 or end_frame > total_frames or end_frame <= start_frame:
        raise ValueError("Listening Master review window leaves the audio horizon")
    return {
        "start_frame": start_frame,
        "end_frame": end_frame,
        "frame_count": end_frame - start_frame,
        "sample_rate": sample_rate,
        "start_seconds": start_frame / sample_rate,
        "end_seconds": end_frame / sample_rate,
        "duration_seconds": (end_frame - start_frame) / sample_rate,
        "recorded_zero": True,
        "alignment_inferred": False,
    }


def _pairwise_level_match(
    audio: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    np = _numpy_module()
    if set(audio) != {BALANCED_CONTROL, LISTENING_MASTER}:
        raise ValueError("Listening Master review requires exactly two inputs")
    rms = {name: _rms(np, values) for name, values in audio.items()}
    peaks = {
        name: float(np.max(np.abs(values))) if len(values) else 0.0
        for name, values in audio.items()
    }
    if any(
        not math.isfinite(value) or _dbfs(value) < MINIMUM_RMS_DBFS
        for value in rms.values()
    ):
        raise ValueError(
            "Listening Master review audio is silent, non-finite, or below "
            f"{MINIMUM_RMS_DBFS:g} dBFS RMS"
        )
    if any(
        not math.isfinite(value) or value >= _FULL_SCALE_GUARD
        for value in peaks.values()
    ):
        raise ValueError("Listening Master review audio is clipped or non-finite")
    target = min(rms.values())
    scales = {name: target / value for name, value in rms.items()}
    gains = {name: 20.0 * math.log10(scale) for name, scale in scales.items()}
    if any(gain < -MAXIMUM_ATTENUATION_DB for gain in gains.values()):
        raise ValueError(
            "Listening Master review candidates differ by more than "
            f"{MAXIMUM_ATTENUATION_DB:g} dB"
        )
    matched = {
        name: np.asarray(values * scales[name], dtype=np.float64)
        for name, values in audio.items()
    }
    after = {name: _rms(np, values) for name, values in matched.items()}
    return matched, {
        "policy": MASTER_REVIEW_LEVEL_POLICY,
        "target_rms": round(target, 12),
        "minimum_rms_dbfs": MINIMUM_RMS_DBFS,
        "maximum_attenuation_db": MAXIMUM_ATTENUATION_DB,
        "limiter_used": False,
        "compression_used": False,
        "equalisation_used": False,
        "inputs": {
            name: {
                "rms_before": round(rms[name], 12),
                "rms_before_dbfs": round(_dbfs(rms[name]), 6),
                "sample_peak_before": round(peaks[name], 12),
                "sample_peak_before_dbfs": round(_dbfs(peaks[name]), 6),
                "linear_scale": round(scales[name], 12),
                "applied_gain_db": round(gains[name], 6),
                "rms_after": round(after[name], 12),
                "rms_after_dbfs": round(_dbfs(after[name]), 6),
            }
            for name in (BALANCED_CONTROL, LISTENING_MASTER)
        },
    }


def _read_audio_window(
    path: Path,
    *,
    expected: Mapping[str, Any],
    start_frame: int,
    frame_count: int,
    label: str,
) -> Any:
    descriptor = _open_owner_only_regular(path, label=label)
    before = os.fstat(descriptor)
    try:
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            total += len(block)
            if total > MAXIMUM_AUDIO_BYTES:
                raise ValueError(f"{label} exceeds the supported byte limit")
        if total != expected.get("bytes") or digest.hexdigest() != expected.get(
            "sha256"
        ):
            raise ValueError(f"{label} changed before review decoding")
        os.lseek(descriptor, 0, os.SEEK_SET)
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            with _soundfile_module().SoundFile(handle) as source:
                source.seek(start_frame)
                values = source.read(
                    frame_count,
                    dtype="float64",
                    always_2d=True,
                )
        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        _require_same_identity(before, after, current, total=total, label=label)
    finally:
        os.close(descriptor)
    np = _numpy_module()
    if len(values) != frame_count or not np.all(np.isfinite(values)):
        raise ValueError(f"{label} review window is incomplete or non-finite")
    return values


def _write_pcm16(path: Path, values: Any, sample_rate: int) -> None:
    _soundfile_module().write(
        str(path),
        values,
        sample_rate,
        format="WAV",
        subtype="PCM_16",
    )
    path.chmod(0o600)
    _require_owner_only_regular_file(path)


def _verified_output_audio(
    path: Path,
    *,
    expected_frames: int,
    expected_sample_rate: int,
    expected_channels: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    record = _private_file_record(
        path,
        label="review output",
        maximum_bytes=MAXIMUM_AUDIO_BYTES,
    )
    soundfile = _soundfile_module()
    info = soundfile.info(str(path))
    values, sample_rate = soundfile.read(str(path), dtype="float64", always_2d=True)
    np = _numpy_module()
    if (
        str(info.format) != "WAV"
        or str(info.subtype) != "PCM_16"
        or int(sample_rate) != expected_sample_rate
        or int(info.channels) != expected_channels
        or int(info.frames) != expected_frames
        or not np.all(np.isfinite(values))
    ):
        raise RuntimeError("Listening Master review output geometry changed")
    rms = _rms(np, values)
    peak = float(np.max(np.abs(values))) if len(values) else 0.0
    if peak >= _FULL_SCALE_GUARD:
        raise RuntimeError("Listening Master review output is clipped")
    return record, {
        "sample_rate": int(sample_rate),
        "channels": int(info.channels),
        "frames": int(info.frames),
        "rms_dbfs": round(_dbfs(rms), 6),
        "sample_peak_dbfs": round(_dbfs(peak), 6),
    }


def _validated_private_record(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} record is invalid")
    path_value = value.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"{label} path is invalid")
    actual = _private_file_record(
        _absolute_path(path_value),
        label=label,
        maximum_bytes=MAXIMUM_AUDIO_BYTES,
    )
    if (
        value.get("name") != actual["name"]
        or value.get("bytes") != actual["bytes"]
        or value.get("sha256") != actual["sha256"]
    ):
        raise ValueError(f"{label} changed")
    return actual


def _private_file_record(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
) -> dict[str, Any]:
    canonical = _absolute_path(path)
    descriptor = _open_owner_only_regular(canonical, label=label)
    before = os.fstat(descriptor)
    try:
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
        current = os.stat(canonical, follow_symlinks=False)
        _require_same_identity(before, after, current, total=total, label=label)
    finally:
        os.close(descriptor)
    return {
        "path": str(canonical),
        "name": canonical.name,
        "bytes": total,
        "sha256": digest.hexdigest(),
    }


def _open_owner_only_regular(path: Path, *, label: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{label} is not a readable regular file") from exc
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) & 0o077:
            raise ValueError(f"{label} is not an owner-only regular file")
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _require_same_identity(
    before: os.stat_result,
    after: os.stat_result,
    current: os.stat_result,
    *,
    total: int,
    label: str,
) -> None:
    identity = (
        int(before.st_dev),
        int(before.st_ino),
        int(before.st_size),
        int(before.st_mtime_ns),
        int(before.st_ctime_ns),
    )
    if total != int(before.st_size) or any(
        (
            int(value.st_dev),
            int(value.st_ino),
            int(value.st_size),
            int(value.st_mtime_ns),
            int(value.st_ctime_ns),
        )
        != identity
        for value in (after, current)
    ):
        raise ValueError(f"{label} changed while it was being read")


def _heard(value: Any) -> dict[str, bool]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {CANDIDATE_A, CANDIDATE_B}
        or value.get(CANDIDATE_A) is not True
        or value.get(CANDIDATE_B) is not True
    ):
        raise ValueError("both anonymous candidates must be marked heard")
    return {CANDIDATE_A: True, CANDIDATE_B: True}


def _choice(value: Any) -> str:
    if value not in MASTER_REVIEW_CHOICES:
        raise ValueError("unsupported Listening Master review choice")
    return str(value)


def _problem_tag_map(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, Mapping) or set(value) != {
        CANDIDATE_A,
        CANDIDATE_B,
    }:
        raise ValueError("problem tags must name Candidate A and Candidate B")
    return {
        slot: _problem_tags(value[slot], label=slot)
        for slot in (CANDIDATE_A, CANDIDATE_B)
    }


def _problem_tags(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} problem tags must be a list")
    tags = list(value)
    if len(tags) > MAXIMUM_PROBLEM_TAGS_PER_CANDIDATE or any(
        not isinstance(tag, str) or tag not in MASTER_REVIEW_PROBLEM_TAGS
        for tag in tags
    ):
        raise ValueError(f"{label} contains unsupported problem tags")
    normalized = sorted(set(tags))
    if len(normalized) != len(tags):
        raise ValueError(f"{label} problem tags must be unique")
    return normalized


def _notes(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("review notes must be text")
    text = value.strip()
    if len(text) > MAXIMUM_NOTES_CHARACTERS:
        raise ValueError(
            f"review notes are limited to {MAXIMUM_NOTES_CHARACTERS} characters"
        )
    if any(
        ord(character) < 32 and character not in {"\n", "\r", "\t"}
        for character in text
    ):
        raise ValueError("review notes contain an invalid control character")
    return text or None


def _validate_stored_review(review: Mapping[str, Any]) -> None:
    expected = {
        "schema",
        "status",
        "blind",
        "policy",
        "review_id",
        "comparison_sha256",
        "reviewer_session_id",
        "revision",
        "nonce_commitment",
        "evidence",
        "response",
        "privacy",
        "effects",
        "review_sha256",
    }
    unsigned = {key: value for key, value in review.items() if key != "review_sha256"}
    if (
        set(review) != expected
        or review.get("schema") != MASTER_REVIEW_SCHEMA
        or review.get("status") != "reviewed"
        or review.get("blind") is not True
        or review.get("policy") != MASTER_REVIEW_POLICY
        or review.get("effects") != REVIEW_EFFECTS
        or review.get("review_sha256") != _document_hash(unsigned)
    ):
        raise ValueError("stored Listening Master review is invalid")
    _sha256(review.get("review_id"), label="review identity")
    _sha256(review.get("comparison_sha256"), label="comparison SHA-256")
    _sha256(review.get("reviewer_session_id"), label="reviewer session identity")
    _sha256(review.get("nonce_commitment"), label="nonce commitment")
    if _nonnegative_int(review.get("revision"), label="review revision") < 1:
        raise ValueError("review revision must be positive")
    response = review.get("response")
    if not isinstance(response, Mapping) or set(response) != {
        "heard",
        "choice",
        "problem_tags",
        "notes",
    }:
        raise ValueError("stored Listening Master response is invalid")
    if _heard(response["heard"]) != response["heard"]:
        raise ValueError("stored Listening Master heard evidence is invalid")
    if _choice(response["choice"]) != response["choice"]:
        raise ValueError("stored Listening Master choice is invalid")
    if _problem_tag_map(response["problem_tags"]) != response["problem_tags"]:
        raise ValueError("stored Listening Master problem tags are invalid")
    if _notes(response["notes"]) != response["notes"]:
        raise ValueError("stored Listening Master notes are invalid")


def _validate_stored_resolution(result: Mapping[str, Any]) -> None:
    expected = {
        "schema",
        "status",
        "blind_review",
        "policy",
        "review_id",
        "review_sha256",
        "comparison_sha256",
        "nonce_commitment",
        "assignment_nonce",
        "assignment",
        "resolved_choice",
        "problem_tags",
        "notes_recorded",
        "promotion_allowed",
        "default_changed",
        "effects",
        "result_sha256",
    }
    unsigned = {key: value for key, value in result.items() if key != "result_sha256"}
    if (
        set(result) != expected
        or result.get("schema") != MASTER_REVIEW_RESULT_SCHEMA
        or result.get("status") != "complete"
        or result.get("blind_review") is not True
        or result.get("policy") != MASTER_REVIEW_POLICY
        or not isinstance(result.get("notes_recorded"), bool)
        or result.get("promotion_allowed") is not False
        or result.get("default_changed") is not False
        or result.get("effects") != RESOLUTION_EFFECTS
        or result.get("result_sha256") != _document_hash(unsigned)
        or not _path_free_document(result)
    ):
        raise ValueError("stored Listening Master review resolution is invalid")
    for field, label in (
        ("review_id", "review identity"),
        ("review_sha256", "review SHA-256"),
        ("comparison_sha256", "comparison SHA-256"),
        ("nonce_commitment", "nonce commitment"),
        ("assignment_nonce", "assignment nonce"),
    ):
        _sha256(result.get(field), label=label)
    assignment = result.get("assignment")
    if (
        not isinstance(assignment, Mapping)
        or set(assignment) != {CANDIDATE_A, CANDIDATE_B}
        or set(assignment.values()) != {BALANCED_CONTROL, LISTENING_MASTER}
    ):
        raise ValueError("stored Listening Master review assignment is invalid")
    if result.get("resolved_choice") not in {
        BALANCED_CONTROL,
        LISTENING_MASTER,
        "equivalent",
        "neither",
        "cannot_tell",
    }:
        raise ValueError("stored Listening Master resolution choice is invalid")
    tags = result.get("problem_tags")
    if not isinstance(tags, Mapping) or set(tags) != {
        BALANCED_CONTROL,
        LISTENING_MASTER,
    }:
        raise ValueError("stored Listening Master resolution tags are invalid")
    for identity in (BALANCED_CONTROL, LISTENING_MASTER):
        if _problem_tags(tags[identity], label=identity) != tags[identity]:
            raise ValueError("stored Listening Master resolution tags are invalid")


def _session_binding(session: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(str(session["binding_json"]))
    except (KeyError, json.JSONDecodeError) as exc:
        raise ValueError("Listening Master review session binding is invalid") from exc
    if (
        not isinstance(value, dict)
        or value.get("schema") != MASTER_REVIEW_COMPARISON_SCHEMA
    ):
        raise ValueError("Listening Master review session binding is invalid")
    return value


def _blind_mapping(nonce: bytes, comparison_sha256: str) -> dict[str, str]:
    if len(nonce) != 32:
        raise ValueError("Listening Master review nonce is invalid")
    decision = hashlib.sha256(
        nonce + bytes.fromhex(comparison_sha256) + b"\0full-song-window"
    ).digest()[0]
    if decision % 2:
        return {
            CANDIDATE_A: LISTENING_MASTER,
            CANDIDATE_B: BALANCED_CONTROL,
        }
    return {
        CANDIDATE_A: BALANCED_CONTROL,
        CANDIDATE_B: LISTENING_MASTER,
    }


def _nonce_commitment(nonce: bytes, comparison_sha256: str) -> str:
    return hashlib.sha256(nonce + bytes.fromhex(comparison_sha256)).hexdigest()


def _reviewer_session_id(value: Any) -> str:
    key = _bounded_text(
        value,
        label="reviewer/session key",
        maximum=MAXIMUM_REVIEWER_KEY_CHARACTERS,
    )
    return hashlib.sha256(
        b"sunofriend.workbench-master-reviewer.v1\0" + key.encode("utf-8")
    ).hexdigest()


def _candidate_slot(value: Any) -> str:
    if value not in {CANDIDATE_A, CANDIDATE_B}:
        raise ValueError("review candidate must be candidate_a or candidate_b")
    return str(value)


def _read_private_json(path: Path) -> dict[str, Any]:
    canonical = _absolute_path(path)
    descriptor = _open_owner_only_regular(
        canonical,
        label="private review JSON",
    )
    before = os.fstat(descriptor)
    payload = bytearray()
    try:
        if before.st_size > MAXIMUM_JSON_BYTES:
            raise ValueError("private review JSON exceeds the supported limit")
        while len(payload) <= MAXIMUM_JSON_BYTES:
            block = os.read(
                descriptor,
                min(1024 * 1024, MAXIMUM_JSON_BYTES + 1 - len(payload)),
            )
            if not block:
                break
            payload.extend(block)
        if len(payload) > MAXIMUM_JSON_BYTES:
            raise ValueError("private review JSON exceeds the supported limit")
        after = os.fstat(descriptor)
        current = os.stat(canonical, follow_symlinks=False)
        _require_same_identity(
            before,
            after,
            current,
            total=len(payload),
            label="private review JSON",
        )
    finally:
        os.close(descriptor)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("private review JSON is invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("private review JSON must contain an object")
    return value


def _write_private_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    if len(payload) > MAXIMUM_JSON_BYTES:
        raise ValueError("private review JSON exceeds the supported limit")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("short private JSON write")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _require_owner_only_regular_file(path)


def _ensure_owner_only_directory(path: Path) -> None:
    if path.exists():
        _require_owner_only_directory(path)
        return
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    path.chmod(0o700)
    _require_owner_only_directory(path)


def _require_owner_only_directory(path: Path) -> None:
    details = os.stat(path, follow_symlinks=False)
    if (
        path.is_symlink()
        or not stat.S_ISDIR(details.st_mode)
        or stat.S_IMODE(details.st_mode) & 0o077
    ):
        raise ValueError("review storage must be an owner-only directory")


def _require_owner_only_regular_file(path: Path) -> None:
    details = os.stat(path, follow_symlinks=False)
    if (
        path.is_symlink()
        or not stat.S_ISREG(details.st_mode)
        or stat.S_IMODE(details.st_mode) & 0o077
    ):
        raise ValueError("review storage must contain owner-only regular files")


def _remove_private_tree(path: Path) -> None:
    if not path.exists() or path.is_symlink():
        return
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            _remove_private_tree(child)
        else:
            child.unlink(missing_ok=True)
    path.rmdir()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _absolute_path(value: str | Path) -> Path:
    expanded = Path(value).expanduser()
    absolute = Path(os.path.abspath(os.fspath(expanded)))
    if absolute.is_symlink():
        raise ValueError("review path must not be a symlink")
    return absolute.parent.resolve() / absolute.name


def _without_path(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _json_copy(item) for key, item in value.items() if key != "path"}


def _path_free_document(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(
            (
                str(key).lower() != "path"
                and not str(key).lower().endswith("_path")
                and _path_free_document(item)
            )
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return all(_path_free_document(item) for item in value)
    return not (isinstance(value, str) and value.startswith("/"))


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _document_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _SHA256_CHARACTERS for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _bounded_text(value: Any, *, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    text = value.strip()
    if not text:
        raise ValueError(f"{label} must not be empty")
    if len(text) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters")
    if any(
        ord(character) < 32 and character not in {"\n", "\r", "\t"}
        for character in text
    ):
        raise ValueError(f"{label} contains an invalid control character")
    return text


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _nonnegative_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _rms(np: Any, values: Any) -> float:
    return float(np.sqrt(np.mean(np.square(values, dtype=np.float64))))


def _dbfs(value: float) -> float:
    return 20.0 * math.log10(max(float(value), 1e-12))


def _numpy_module() -> Any:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - dependency boundary
        raise RuntimeError(
            "Listening Master review requires NumPy; install Sunofriend audio extras"
        ) from exc
    return np


def _soundfile_module() -> Any:
    try:
        import soundfile
    except ImportError as exc:  # pragma: no cover - dependency boundary
        raise RuntimeError(
            "Listening Master review requires SoundFile; install Sunofriend audio extras"
        ) from exc
    return soundfile


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "BALANCED_CONTROL",
    "CANDIDATE_A",
    "CANDIDATE_B",
    "LISTENING_MASTER",
    "MASTER_REVIEW_AUDIO_SCHEMA",
    "MASTER_REVIEW_CHOICES",
    "MASTER_REVIEW_COMPARISON_SCHEMA",
    "MASTER_REVIEW_POLICY",
    "MASTER_REVIEW_PROBLEM_TAGS",
    "MASTER_REVIEW_RESULT_SCHEMA",
    "MASTER_REVIEW_SCHEMA",
    "WorkbenchMasterReviewConflictError",
    "WorkbenchMasterReviewRevisionConflictError",
    "WorkbenchMasterReviewService",
]
