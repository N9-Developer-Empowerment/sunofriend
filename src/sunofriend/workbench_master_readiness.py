"""Identity-labelled native-level review after a frozen blind quality review.

This service is deliberately downstream of :class:`WorkbenchMasterReviewService`.
It may prepare a native-level comparison only when the exact current blind
quality review is complete, explicitly resolved, and still the latest review
for the supplied private reviewer key.

The two source artifacts are never changed.  The service copies the quality
review's exact frame window to private PCM24 WAVs without gain or processing,
then records at most one immutable, direct-identity response for each quality
result and reviewer.  Exact completion retries return the original record;
changed retries conflict.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .workbench_master_review import (
    BALANCED_CONTROL,
    LISTENING_MASTER,
    MASTER_REVIEW_PROBLEM_TAGS,
    MAXIMUM_NOTES_CHARACTERS,
    MAXIMUM_PROBLEM_TAGS_PER_CANDIDATE,
    WorkbenchMasterReviewService,
    _bounded_text,
    _canonical_json,
    _document_hash,
    _ensure_owner_only_directory,
    _fsync_directory,
    _json_copy,
    _notes,
    _path_free_document,
    _problem_tags,
    _read_private_json,
    _remove_private_tree,
    _require_owner_only_directory,
    _sha256,
    _utc_now,
    _verified_artifact_evidence,
    _write_private_json,
)
from .workbench_master_review_audio import (
    FULL_SCALE_GUARD,
    MAXIMUM_AUDIO_BYTES,
    absolute_path,
    dbfs,
    numpy_module,
    private_file_record,
    read_audio_window,
    require_owner_only_regular_file,
    rms,
    soundfile_module,
)


MASTER_READINESS_COMPARISON_SCHEMA = (
    "sunofriend.workbench-listening-master-native-readiness-comparison.v1"
)
MASTER_READINESS_AUDIO_SCHEMA = (
    "sunofriend.workbench-listening-master-native-readiness-audio.v1"
)
MASTER_READINESS_SOURCE_BINDING_SCHEMA = (
    "sunofriend.workbench-listening-master-native-readiness-sources.v1"
)
MASTER_READINESS_REVIEW_SCHEMA = (
    "sunofriend.workbench-listening-master-native-readiness-review.v1"
)
MASTER_READINESS_POLICY = (
    "identity-labelled-native-level-exact-window-pcm24-v1"
)
MASTER_READINESS_AUDIO_POLICY = "exact-frame-native-level-zero-gain-pcm24-v1"

MASTER_READINESS_CHOICES = frozenset(
    {
        BALANCED_CONTROL,
        LISTENING_MASTER,
        "equivalent",
        "neither",
        "cannot_tell",
    }
)
MASTER_READINESS_PROBLEM_TAGS = MASTER_REVIEW_PROBLEM_TAGS

PREPARE_EFFECTS: dict[str, bool] = {
    "feedback_recorded": False,
    "readiness_review_record_created": False,
    "quality_review_mutated": False,
    "quality_resolution_mutated": False,
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
    "readiness_review_record_created": True,
}

MAXIMUM_REVIEWER_KEY_CHARACTERS = 128
MAXIMUM_JSON_BYTES = 4 * 1024 * 1024
_AUDIO_DIRECTORY = "audio"
_DATABASE_NAME = "reviews.sqlite3"
_MANIFEST_NAME = "manifest.json"
_SOURCE_BINDING_NAME = "source-binding.json"


class WorkbenchMasterReadinessGateError(RuntimeError):
    """Raised when the required blind quality result is not a current gate."""


class WorkbenchMasterReadinessConflictError(RuntimeError):
    """Raised when immutable readiness evidence or a retry response differs."""


class WorkbenchMasterReadinessService:
    """Prepare native-level crops and store one direct response per quality gate."""

    def __init__(
        self,
        root: str | Path,
        quality_review_service: WorkbenchMasterReviewService,
    ) -> None:
        self.root = absolute_path(root)
        self.audio_root = self.root / _AUDIO_DIRECTORY
        self.database_path = self.root / _DATABASE_NAME
        self.quality_review_service = quality_review_service
        _ensure_owner_only_directory(self.root)
        _ensure_owner_only_directory(self.audio_root)
        self._initialize()

    def prepare(
        self,
        *,
        project_id: str,
        balanced: Mapping[str, Any],
        listening_master: Mapping[str, Any],
        quality_review_id: str,
        quality_review_sha256: str,
        quality_result_sha256: str,
        reviewer_session_key: str,
    ) -> dict[str, Any]:
        """Prepare or reuse the exact identity-labelled native-level window."""

        reviewer_session_id = _reviewer_session_id(reviewer_session_key)
        gate = self._verified_quality_gate(
            project_id=project_id,
            balanced=balanced,
            listening_master=listening_master,
            quality_review_id=quality_review_id,
            quality_review_sha256=quality_review_sha256,
            quality_result_sha256=quality_result_sha256,
            reviewer_session_key=reviewer_session_key,
        )
        comparison = _comparison_document(gate)
        comparison_sha256 = _document_hash(comparison)
        manifest = self._prepare_audio(
            gate=gate,
            comparison=comparison,
            comparison_sha256=comparison_sha256,
            project_id=project_id,
            balanced=balanced,
            listening_master=listening_master,
            reviewer_session_key=reviewer_session_key,
        )
        review = self._review_for_gate(
            quality_result_sha256=str(
                comparison["quality_review"]["quality_result_sha256"]
            ),
            reviewer_session_id=reviewer_session_id,
        )
        if review is not None:
            self._validate_and_bind_review(review)
            if review["comparison_sha256"] != comparison_sha256:
                raise WorkbenchMasterReadinessConflictError(
                    "native-level readiness evidence changed for this quality result"
                )
        return _public_comparison(
            comparison=comparison,
            comparison_sha256=comparison_sha256,
            manifest=manifest,
            review=review,
        )

    def complete(
        self,
        *,
        project_id: str,
        balanced: Mapping[str, Any],
        listening_master: Mapping[str, Any],
        comparison_sha256: str,
        quality_review_id: str,
        quality_review_sha256: str,
        quality_result_sha256: str,
        reviewer_session_key: str,
        heard: Mapping[str, Any],
        choice: str,
        problem_tags: Mapping[str, Sequence[str]],
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Record one immutable native-level response, or replay it exactly."""

        comparison_id = _sha256(
            comparison_sha256,
            label="native-level comparison SHA-256",
        )
        reviewer_session_id = _reviewer_session_id(reviewer_session_key)
        gate = self._verified_quality_gate(
            project_id=project_id,
            balanced=balanced,
            listening_master=listening_master,
            quality_review_id=quality_review_id,
            quality_review_sha256=quality_review_sha256,
            quality_result_sha256=quality_result_sha256,
            reviewer_session_key=reviewer_session_key,
        )
        comparison = _comparison_document(gate)
        if _document_hash(comparison) != comparison_id:
            raise WorkbenchMasterReadinessConflictError(
                "native-level readiness comparison is no longer current"
            )
        self._load_audio_manifest(
            comparison_id,
            expected_binding=comparison,
        )
        response = {
            "heard": _heard(heard),
            "choice": _choice(choice),
            "problem_tags": _problem_tag_map(problem_tags),
            "notes": _path_free_notes(notes),
        }
        readiness_review_id = _document_hash(
            {
                "schema": MASTER_READINESS_REVIEW_SCHEMA,
                "comparison_sha256": comparison_id,
                "quality_result_sha256": quality_result_sha256,
                "reviewer_session_id": reviewer_session_id,
                "response": response,
            }
        )
        document_without_hash = {
            "schema": MASTER_READINESS_REVIEW_SCHEMA,
            "status": "reviewed",
            "identity_labelled": True,
            "native_level": True,
            "policy": MASTER_READINESS_POLICY,
            "readiness_review_id": readiness_review_id,
            "comparison_sha256": comparison_id,
            "quality_review": _json_copy(comparison["quality_review"]),
            "reviewer_session_id": reviewer_session_id,
            "evidence": comparison,
            "response": response,
            "export_ready": True,
            "privacy": {
                "local_only": True,
                "reviewer_key_stored": False,
                "notes_private": True,
                "notes_may_contain_identifying_material": bool(response["notes"]),
            },
            "effects": dict(REVIEW_EFFECTS),
        }
        document = {
            **document_without_hash,
            "readiness_review_sha256": _document_hash(document_without_hash),
        }
        _validate_stored_review(document)

        # Re-read the quality gate immediately before the append.  This cannot
        # make two SQLite files one transaction, but it closes the expensive
        # preparation gap and ensures the appended response followed a latest
        # resolved quality result at the write boundary.
        final_gate = self._verified_quality_gate(
            project_id=project_id,
            balanced=balanced,
            listening_master=listening_master,
            quality_review_id=quality_review_id,
            quality_review_sha256=quality_review_sha256,
            quality_result_sha256=quality_result_sha256,
            reviewer_session_key=reviewer_session_key,
        )
        if _comparison_document(final_gate) != comparison:
            raise WorkbenchMasterReadinessConflictError(
                "native-level readiness quality evidence changed before completion"
            )
        return self._append_or_replay(
            review=document,
            reviewer_session_id=reviewer_session_id,
        )

    def media_record(
        self,
        comparison_sha256: str,
        identity: str,
    ) -> dict[str, Any]:
        """Return one verified private PCM24 record for loopback registration."""

        comparison_id = _sha256(
            comparison_sha256,
            label="native-level comparison SHA-256",
        )
        checked_identity = _identity(identity)
        manifest = self._load_audio_manifest(comparison_id)
        record = manifest["candidates"][checked_identity]["audio"]
        path = self.audio_root / comparison_id / str(record["name"])
        actual = private_file_record(
            path,
            label=f"{checked_identity} native-level review audio",
            maximum_bytes=MAXIMUM_AUDIO_BYTES,
        )
        if _without_path(actual) != record:
            raise ValueError("native-level readiness review audio changed")
        return actual

    def review(self, readiness_review_id: str) -> dict[str, Any]:
        """Return one verified path-free review document ready for local export."""

        review_id = _sha256(
            readiness_review_id,
            label="native-level readiness review identity",
        )
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT comparison_sha256, quality_result_sha256,
                       reviewer_session_id, review_json
                FROM readiness_reviews
                WHERE readiness_review_id = ?
                """,
                (review_id,),
            ).fetchone()
        if row is None:
            raise ValueError("native-level readiness review does not exist")
        try:
            value = json.loads(str(row[3]))
        except json.JSONDecodeError as exc:
            raise ValueError("native-level readiness review record is invalid") from exc
        if (
            not isinstance(value, dict)
            or value.get("readiness_review_id") != review_id
            or value.get("comparison_sha256") != row[0]
            or value.get("quality_review", {}).get("quality_result_sha256")
            != row[1]
            or value.get("reviewer_session_id") != row[2]
        ):
            raise ValueError("native-level readiness review record is invalid")
        self._validate_and_bind_review(value)
        return _json_copy(value)

    def _verified_quality_gate(
        self,
        *,
        project_id: str,
        balanced: Mapping[str, Any],
        listening_master: Mapping[str, Any],
        quality_review_id: str,
        quality_review_sha256: str,
        quality_result_sha256: str,
        reviewer_session_key: str,
    ) -> dict[str, Any]:
        checked_review_id = _sha256(
            quality_review_id,
            label="quality review identity",
        )
        checked_review_sha256 = _sha256(
            quality_review_sha256,
            label="quality review SHA-256",
        )
        checked_result_sha256 = _sha256(
            quality_result_sha256,
            label="quality result SHA-256",
        )
        try:
            quality_review = self.quality_review_service.review(checked_review_id)
        except (ValueError, RuntimeError) as exc:
            raise WorkbenchMasterReadinessGateError(
                "blind quality review could not be verified"
            ) from exc
        if quality_review.get("review_sha256") != checked_review_sha256:
            raise WorkbenchMasterReadinessGateError(
                "blind quality review SHA-256 does not match"
            )
        try:
            latest_quality_review = (
                self.quality_review_service.latest_review_for_project_reviewer(
                    project_id=project_id,
                    reviewer_session_key=reviewer_session_key,
                )
            )
        except (ValueError, RuntimeError) as exc:
            raise WorkbenchMasterReadinessGateError(
                "latest blind quality review could not be verified"
            ) from exc
        if latest_quality_review != quality_review:
            raise WorkbenchMasterReadinessGateError(
                "blind quality review is not the latest review for this reviewer"
            )
        try:
            quality_result = self.quality_review_service.resolution(
                checked_review_id
            )
        except (ValueError, RuntimeError) as exc:
            raise WorkbenchMasterReadinessGateError(
                "blind quality resolution could not be verified"
            ) from exc
        if quality_result is None:
            raise WorkbenchMasterReadinessGateError(
                "blind quality review must be explicitly resolved first"
            )
        if quality_result.get("result_sha256") != checked_result_sha256:
            raise WorkbenchMasterReadinessGateError(
                "blind quality result SHA-256 does not match"
            )

        comparison_sha256 = _sha256(
            quality_review.get("comparison_sha256"),
            label="quality comparison SHA-256",
        )
        try:
            current = self.quality_review_service.current(
                project_id=project_id,
                balanced=balanced,
                listening_master=listening_master,
                comparison_sha256=comparison_sha256,
                reviewer_session_key=reviewer_session_key,
            )
        except (ValueError, RuntimeError) as exc:
            raise WorkbenchMasterReadinessGateError(
                "blind quality review is not current for these artifacts"
            ) from exc
        state = current.get("review_state")
        if (
            not isinstance(state, Mapping)
            or state.get("status") != "reviewed"
            or state.get("review_id") != checked_review_id
            or state.get("review_sha256") != checked_review_sha256
            or state.get("current_revision") != quality_review.get("revision")
        ):
            raise WorkbenchMasterReadinessGateError(
                "blind quality review is not the latest review for this reviewer"
            )

        artifact_evidence = _verified_artifact_evidence(
            project_id=project_id,
            balanced=balanced,
            listening_master=listening_master,
        )
        quality_evidence = quality_review.get("evidence")
        if (
            not isinstance(quality_evidence, Mapping)
            or quality_evidence.get("project_id")
            != artifact_evidence["public"]["project_id"]
            or quality_evidence.get("selection_manifest_sha256")
            != artifact_evidence["public"]["selection_manifest_sha256"]
            or quality_evidence.get("balanced_control")
            != artifact_evidence["public"]["balanced_control"]
            or quality_evidence.get("listening_master")
            != artifact_evidence["public"]["listening_master"]
            or quality_evidence.get("geometry")
            != artifact_evidence["public"]["geometry"]
        ):
            raise WorkbenchMasterReadinessGateError(
                "blind quality review artifact evidence is no longer current"
            )
        window = quality_evidence.get("window")
        _validate_window(
            window,
            geometry=artifact_evidence["public"]["geometry"],
        )
        anchor = _quality_anchor(
            quality_review=quality_review,
            quality_result=quality_result,
        )
        return {
            "anchor": anchor,
            "window": _json_copy(window),
            "artifact_evidence": artifact_evidence,
        }

    def _prepare_audio(
        self,
        *,
        gate: Mapping[str, Any],
        comparison: Mapping[str, Any],
        comparison_sha256: str,
        project_id: str,
        balanced: Mapping[str, Any],
        listening_master: Mapping[str, Any],
        reviewer_session_key: str,
    ) -> dict[str, Any]:
        existing = self._load_audio_manifest(
            comparison_sha256,
            expected_binding=comparison,
            missing_ok=True,
        )
        if existing is not None:
            return existing

        final = self.audio_root / comparison_sha256
        if final.exists():
            winner = self._load_audio_manifest(
                comparison_sha256,
                expected_binding=comparison,
            )
            if winner is None:  # pragma: no cover - missing_ok is false
                raise RuntimeError("native-level audio publication disappeared")
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
            private = gate["artifact_evidence"]["private"]
            source_values = {
                BALANCED_CONTROL: read_audio_window(
                    Path(str(private["control_path"])),
                    expected=private["control_record"],
                    start_frame=start_frame,
                    frame_count=frame_count,
                    label="balanced control",
                ),
                LISTENING_MASTER: read_audio_window(
                    Path(str(private["master_path"])),
                    expected=private["master_record"],
                    start_frame=start_frame,
                    frame_count=frame_count,
                    label="Listening Master",
                ),
            }
            source_binding = _source_binding_document(
                comparison=comparison,
                private=private,
            )
            candidate_rows: dict[str, Any] = {}
            for identity in (BALANCED_CONTROL, LISTENING_MASTER):
                output = work / f"{identity.replace('_', '-')}.wav"
                _write_pcm24(
                    output,
                    source_values[identity],
                    int(comparison["geometry"]["sample_rate"]),
                )
                record, audio_info = _verified_pcm24_output(
                    output,
                    expected_values=source_values[identity],
                    expected_frames=frame_count,
                    expected_sample_rate=int(
                        comparison["geometry"]["sample_rate"]
                    ),
                    expected_channels=int(comparison["geometry"]["channels"]),
                )
                candidate_rows[identity] = {
                    "label": _identity_label(identity),
                    "audio": _without_path(record),
                    **audio_info,
                    "applied_gain_db": 0.0,
                    "processing_applied": False,
                }

            current_gate = self._verified_quality_gate(
                project_id=project_id,
                balanced=balanced,
                listening_master=listening_master,
                quality_review_id=str(
                    comparison["quality_review"]["quality_review_id"]
                ),
                quality_review_sha256=str(
                    comparison["quality_review"]["quality_review_sha256"]
                ),
                quality_result_sha256=str(
                    comparison["quality_review"]["quality_result_sha256"]
                ),
                reviewer_session_key=reviewer_session_key,
            )
            if _comparison_document(current_gate) != comparison:
                raise WorkbenchMasterReadinessConflictError(
                    "native-level readiness evidence changed during preparation"
                )

            manifest_without_hash = {
                "schema": MASTER_READINESS_AUDIO_SCHEMA,
                "comparison_sha256": comparison_sha256,
                "binding": _json_copy(comparison),
                "quality_review": _json_copy(comparison["quality_review"]),
                "window": _json_copy(comparison["window"]),
                "policy": _policy_document(),
                "candidates": candidate_rows,
                "path_free_manifest": True,
                "private_audio": True,
                "effects": dict(PREPARE_EFFECTS),
            }
            manifest = {
                **manifest_without_hash,
                "manifest_sha256": _document_hash(manifest_without_hash),
            }
            _write_private_json(work / _SOURCE_BINDING_NAME, source_binding)
            _write_private_json(work / _MANIFEST_NAME, manifest)
            try:
                os.replace(work, final)
            except OSError:
                if not final.exists():
                    raise
                winner = self._load_audio_manifest(
                    comparison_sha256,
                    expected_binding=comparison,
                )
                if winner is None:  # pragma: no cover - missing_ok is false
                    raise RuntimeError(
                        "native-level audio publication disappeared"
                    )
                _remove_private_tree(work)
                return winner
            _fsync_directory(self.audio_root)
        except BaseException:
            _remove_private_tree(work)
            raise
        loaded = self._load_audio_manifest(
            comparison_sha256,
            expected_binding=comparison,
        )
        if loaded is None:  # pragma: no cover - defensive typed boundary
            raise RuntimeError("native-level audio publication failed")
        return loaded

    def _load_audio_manifest(
        self,
        comparison_sha256: str,
        *,
        expected_binding: Mapping[str, Any] | None = None,
        missing_ok: bool = False,
    ) -> dict[str, Any] | None:
        directory = self.audio_root / comparison_sha256
        if not directory.exists():
            if missing_ok:
                return None
            raise ValueError("native-level readiness audio is unavailable")
        _require_owner_only_directory(directory)
        manifest = _read_private_json(directory / _MANIFEST_NAME)
        expected_fields = {
            "schema",
            "comparison_sha256",
            "binding",
            "quality_review",
            "window",
            "policy",
            "candidates",
            "path_free_manifest",
            "private_audio",
            "effects",
            "manifest_sha256",
        }
        unsigned = {
            key: value for key, value in manifest.items() if key != "manifest_sha256"
        }
        binding = manifest.get("binding")
        if (
            set(manifest) != expected_fields
            or manifest.get("schema") != MASTER_READINESS_AUDIO_SCHEMA
            or manifest.get("comparison_sha256") != comparison_sha256
            or not isinstance(binding, Mapping)
            or _document_hash(binding) != comparison_sha256
            or manifest.get("quality_review") != binding.get("quality_review")
            or manifest.get("window") != binding.get("window")
            or manifest.get("policy") != _policy_document()
            or binding.get("policy") != _policy_document()
            or manifest.get("effects") != PREPARE_EFFECTS
            or manifest.get("path_free_manifest") is not True
            or manifest.get("private_audio") is not True
            or manifest.get("manifest_sha256") != _document_hash(unsigned)
            or not _path_free_document(manifest)
        ):
            raise ValueError("native-level readiness audio manifest is invalid")
        _validate_comparison_binding(binding)
        if expected_binding is not None and binding != expected_binding:
            raise WorkbenchMasterReadinessConflictError(
                "native-level readiness audio binding changed"
            )
        quality_review, _quality_result = self._verify_stored_quality_anchor(
            binding["quality_review"]
        )
        quality_evidence = quality_review.get("evidence")
        if (
            not isinstance(quality_evidence, Mapping)
            or any(
                binding.get(field) != quality_evidence.get(field)
                for field in (
                    "project_id",
                    "selection_manifest_sha256",
                    "balanced_control",
                    "listening_master",
                    "geometry",
                    "window",
                )
            )
        ):
            raise ValueError(
                "native-level readiness binding changed from the quality review"
            )
        source_values = _verified_source_values(
            directory=directory,
            binding=binding,
        )

        candidates = manifest.get("candidates")
        if not isinstance(candidates, Mapping) or set(candidates) != {
            BALANCED_CONTROL,
            LISTENING_MASTER,
        }:
            raise ValueError("native-level readiness candidates are invalid")
        for identity in (BALANCED_CONTROL, LISTENING_MASTER):
            row = candidates[identity]
            expected_row_fields = {
                "label",
                "audio",
                "format",
                "subtype",
                "sample_rate",
                "channels",
                "frames",
                "rms_dbfs",
                "sample_peak_dbfs",
                "applied_gain_db",
                "processing_applied",
            }
            if (
                not isinstance(row, Mapping)
                or set(row) != expected_row_fields
                or row.get("label") != _identity_label(identity)
                or not isinstance(row.get("audio"), Mapping)
                or set(row["audio"]) != {"name", "bytes", "sha256"}
                or row["audio"].get("name")
                != f"{identity.replace('_', '-')}.wav"
                or row.get("applied_gain_db") != 0.0
                or row.get("processing_applied") is not False
            ):
                raise ValueError("native-level readiness candidate is invalid")
            actual, audio_info = _verified_pcm24_output(
                directory / str(row["audio"]["name"]),
                expected_values=source_values[identity],
                expected_frames=int(binding["window"]["frame_count"]),
                expected_sample_rate=int(binding["geometry"]["sample_rate"]),
                expected_channels=int(binding["geometry"]["channels"]),
            )
            if _without_path(actual) != row["audio"] or any(
                row.get(key) != audio_info[key]
                for key in (
                    "format",
                    "subtype",
                    "sample_rate",
                    "channels",
                    "frames",
                    "rms_dbfs",
                    "sample_peak_dbfs",
                )
            ):
                raise ValueError("native-level readiness review audio changed")
        return manifest

    def _append_or_replay(
        self,
        *,
        review: Mapping[str, Any],
        reviewer_session_id: str,
    ) -> dict[str, Any]:
        quality_result_sha256 = str(
            review["quality_review"]["quality_result_sha256"]
        )
        payload = _canonical_json(review)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT readiness_review_id, comparison_sha256, review_json
                FROM readiness_reviews
                WHERE quality_result_sha256 = ? AND reviewer_session_id = ?
                """,
                (quality_result_sha256, reviewer_session_id),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO readiness_reviews (
                        readiness_review_id, comparison_sha256,
                        quality_result_sha256, reviewer_session_id,
                        created_at, review_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(review["readiness_review_id"]),
                        str(review["comparison_sha256"]),
                        quality_result_sha256,
                        reviewer_session_id,
                        _utc_now(),
                        payload,
                    ),
                )
                return _json_copy(review)
            try:
                existing = json.loads(str(row[2]))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "native-level readiness review record is invalid"
                ) from exc
            if (
                row[0] != review["readiness_review_id"]
                or row[1] != review["comparison_sha256"]
                or existing != review
            ):
                raise WorkbenchMasterReadinessConflictError(
                    "a different native-level response already exists for "
                    "this quality result and reviewer"
                )
        self._validate_and_bind_review(existing)
        return _json_copy(existing)

    def _review_for_gate(
        self,
        *,
        quality_result_sha256: str,
        reviewer_session_id: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT review_json
                FROM readiness_reviews
                WHERE quality_result_sha256 = ? AND reviewer_session_id = ?
                """,
                (quality_result_sha256, reviewer_session_id),
            ).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(str(row[0]))
        except json.JSONDecodeError as exc:
            raise ValueError(
                "native-level readiness review record is invalid"
            ) from exc
        if not isinstance(value, dict):
            raise ValueError("native-level readiness review record is invalid")
        return value

    def _validate_and_bind_review(self, review: Mapping[str, Any]) -> None:
        _validate_stored_review(review)
        comparison_sha256 = str(review["comparison_sha256"])
        manifest = self._load_audio_manifest(
            comparison_sha256,
            expected_binding=review["evidence"],
        )
        if manifest["quality_review"] != review["quality_review"]:
            raise ValueError("native-level readiness review binding is invalid")

    def _verify_stored_quality_anchor(
        self,
        anchor: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        _validate_quality_anchor(anchor)
        try:
            quality_review = self.quality_review_service.review(
                str(anchor["quality_review_id"])
            )
            quality_result = self.quality_review_service.resolution(
                str(anchor["quality_review_id"])
            )
        except (ValueError, RuntimeError) as exc:
            raise ValueError("native-level quality anchor is invalid") from exc
        if (
            quality_result is None
            or quality_review.get("review_sha256")
            != anchor["quality_review_sha256"]
            or quality_review.get("comparison_sha256")
            != anchor["quality_comparison_sha256"]
            or quality_review.get("revision") != anchor["quality_revision"]
            or quality_result.get("result_sha256")
            != anchor["quality_result_sha256"]
            or quality_result.get("resolved_choice") != anchor["resolved_choice"]
        ):
            raise ValueError("native-level quality anchor changed")
        return quality_review, quality_result

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS readiness_reviews (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    readiness_review_id TEXT NOT NULL UNIQUE,
                    comparison_sha256 TEXT NOT NULL,
                    quality_result_sha256 TEXT NOT NULL,
                    reviewer_session_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    review_json TEXT NOT NULL,
                    UNIQUE (quality_result_sha256, reviewer_session_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS readiness_reviews_comparison
                ON readiness_reviews (comparison_sha256, reviewer_session_id)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        _ensure_owner_only_directory(self.root)
        connection = sqlite3.connect(str(self.database_path), timeout=10.0)
        try:
            self.database_path.chmod(0o600)
            require_owner_only_regular_file(self.database_path)
            connection.execute("PRAGMA trusted_schema=OFF")
        except Exception:
            connection.close()
            raise
        return connection


def _quality_anchor(
    *,
    quality_review: Mapping[str, Any],
    quality_result: Mapping[str, Any],
) -> dict[str, Any]:
    anchor = {
        "quality_review_id": quality_review["review_id"],
        "quality_review_sha256": quality_review["review_sha256"],
        "quality_result_sha256": quality_result["result_sha256"],
        "quality_comparison_sha256": quality_review["comparison_sha256"],
        "quality_revision": quality_review["revision"],
        "resolved_choice": quality_result["resolved_choice"],
        "explicitly_resolved": True,
        "latest_for_reviewer": True,
    }
    _validate_quality_anchor(anchor)
    return anchor


def _comparison_document(gate: Mapping[str, Any]) -> dict[str, Any]:
    public = gate["artifact_evidence"]["public"]
    document = {
        "schema": MASTER_READINESS_COMPARISON_SCHEMA,
        "project_id": public["project_id"],
        "selection_manifest_sha256": public["selection_manifest_sha256"],
        "identity_labelled": True,
        "native_level": True,
        "quality_review": _json_copy(gate["anchor"]),
        "balanced_control": _json_copy(public["balanced_control"]),
        "listening_master": _json_copy(public["listening_master"]),
        "geometry": _json_copy(public["geometry"]),
        "window": _json_copy(gate["window"]),
        "policy": _policy_document(),
    }
    _validate_comparison_binding(document)
    return document


def _policy_document() -> dict[str, Any]:
    return {
        "name": MASTER_READINESS_POLICY,
        "audio": MASTER_READINESS_AUDIO_POLICY,
        "identity_hidden": False,
        "quality_review_resolved": True,
        "quality_review_latest": True,
        "exact_quality_frame_window_reused": True,
        "native_level_unchanged": True,
        "output_format": "WAV",
        "output_subtype": "PCM_24",
        "applied_gain_db": 0.0,
        "gain_matching_used": False,
        "resampling_used": False,
        "limiter_used": False,
        "compression_used": False,
        "equalisation_used": False,
        "time_shift_seconds": 0.0,
        "time_stretch_ratio": 1.0,
    }


def _public_comparison(
    *,
    comparison: Mapping[str, Any],
    comparison_sha256: str,
    manifest: Mapping[str, Any],
    review: Mapping[str, Any] | None,
) -> dict[str, Any]:
    candidates = {
        identity: {
            "label": manifest["candidates"][identity]["label"],
            "audio": _json_copy(manifest["candidates"][identity]["audio"]),
            "format": manifest["candidates"][identity]["format"],
            "subtype": manifest["candidates"][identity]["subtype"],
            "sample_rate": manifest["candidates"][identity]["sample_rate"],
            "channels": manifest["candidates"][identity]["channels"],
            "frames": manifest["candidates"][identity]["frames"],
            "applied_gain_db": 0.0,
            "processing_applied": False,
        }
        for identity in (BALANCED_CONTROL, LISTENING_MASTER)
    }
    document = {
        "schema": MASTER_READINESS_COMPARISON_SCHEMA,
        "status": "reviewed" if review is not None else "unreviewed",
        "identity_labelled": True,
        "native_level": True,
        "review_required": True,
        "comparison_sha256": comparison_sha256,
        "quality_review": _json_copy(comparison["quality_review"]),
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
        "choices": sorted(MASTER_READINESS_CHOICES),
        "problem_tags": sorted(MASTER_READINESS_PROBLEM_TAGS),
        "limits": {
            "maximum_problem_tags_per_identity": (
                MAXIMUM_PROBLEM_TAGS_PER_CANDIDATE
            ),
            "maximum_notes_characters": MAXIMUM_NOTES_CHARACTERS,
        },
        "review": _json_copy(review) if review is not None else None,
        "effects": dict(PREPARE_EFFECTS),
    }
    if not _path_free_document(document):
        raise ValueError("public native-level readiness comparison contains a path")
    return document


def _validate_comparison_binding(binding: Mapping[str, Any]) -> None:
    expected = {
        "schema",
        "project_id",
        "selection_manifest_sha256",
        "identity_labelled",
        "native_level",
        "quality_review",
        "balanced_control",
        "listening_master",
        "geometry",
        "window",
        "policy",
    }
    if (
        set(binding) != expected
        or binding.get("schema") != MASTER_READINESS_COMPARISON_SCHEMA
        or binding.get("identity_labelled") is not True
        or binding.get("native_level") is not True
        or binding.get("policy") != _policy_document()
        or not _path_free_document(binding)
    ):
        raise ValueError("native-level readiness comparison binding is invalid")
    _bounded_text(binding.get("project_id"), label="project_id", maximum=128)
    _sha256(
        binding.get("selection_manifest_sha256"),
        label="selection manifest SHA-256",
    )
    _validate_quality_anchor(binding.get("quality_review"))
    geometry = binding.get("geometry")
    if (
        not isinstance(geometry, Mapping)
        or set(geometry)
        != {"sample_rate", "channels", "frames", "duration_seconds"}
        or isinstance(geometry.get("sample_rate"), bool)
        or not isinstance(geometry.get("sample_rate"), int)
        or int(geometry["sample_rate"]) <= 0
        or isinstance(geometry.get("channels"), bool)
        or not isinstance(geometry.get("channels"), int)
        or int(geometry["channels"]) <= 0
        or isinstance(geometry.get("frames"), bool)
        or not isinstance(geometry.get("frames"), int)
        or int(geometry["frames"]) <= 0
        or not _finite_positive(geometry.get("duration_seconds"))
    ):
        raise ValueError("native-level readiness geometry is invalid")
    _validate_window(binding.get("window"), geometry=geometry)


def _validate_quality_anchor(value: Any) -> None:
    expected = {
        "quality_review_id",
        "quality_review_sha256",
        "quality_result_sha256",
        "quality_comparison_sha256",
        "quality_revision",
        "resolved_choice",
        "explicitly_resolved",
        "latest_for_reviewer",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or value.get("explicitly_resolved") is not True
        or value.get("latest_for_reviewer") is not True
        or isinstance(value.get("quality_revision"), bool)
        or not isinstance(value.get("quality_revision"), int)
        or int(value["quality_revision"]) < 1
        or value.get("resolved_choice") not in MASTER_READINESS_CHOICES
    ):
        raise ValueError("native-level quality anchor is invalid")
    for field, label in (
        ("quality_review_id", "quality review identity"),
        ("quality_review_sha256", "quality review SHA-256"),
        ("quality_result_sha256", "quality result SHA-256"),
        ("quality_comparison_sha256", "quality comparison SHA-256"),
    ):
        _sha256(value.get(field), label=label)


def _validate_window(value: Any, *, geometry: Mapping[str, Any]) -> None:
    expected = {
        "start_frame",
        "end_frame",
        "frame_count",
        "sample_rate",
        "start_seconds",
        "end_seconds",
        "duration_seconds",
        "recorded_zero",
        "alignment_inferred",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("native-level readiness window is invalid")
    integer_fields = ("start_frame", "end_frame", "frame_count", "sample_rate")
    if any(
        isinstance(value.get(field), bool)
        or not isinstance(value.get(field), int)
        for field in integer_fields
    ):
        raise ValueError("native-level readiness window is invalid")
    start_frame = int(value["start_frame"])
    end_frame = int(value["end_frame"])
    frame_count = int(value["frame_count"])
    sample_rate = int(value["sample_rate"])
    if (
        start_frame < 0
        or end_frame <= start_frame
        or frame_count != end_frame - start_frame
        or end_frame > int(geometry["frames"])
        or sample_rate != int(geometry["sample_rate"])
        or value.get("recorded_zero") is not True
        or value.get("alignment_inferred") is not False
        or any(
            isinstance(value.get(field), bool)
            or not isinstance(value.get(field), (int, float))
            or not math.isfinite(float(value[field]))
            for field in ("start_seconds", "end_seconds", "duration_seconds")
        )
        or float(value["start_seconds"]) != start_frame / sample_rate
        or float(value["end_seconds"]) != end_frame / sample_rate
        or float(value["duration_seconds"]) != frame_count / sample_rate
    ):
        raise ValueError("native-level readiness window is invalid")


def _heard(value: Any) -> dict[str, bool]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {BALANCED_CONTROL, LISTENING_MASTER}
        or value.get(BALANCED_CONTROL) is not True
        or value.get(LISTENING_MASTER) is not True
    ):
        raise ValueError("both native-level identities must be marked heard")
    return {BALANCED_CONTROL: True, LISTENING_MASTER: True}


def _choice(value: Any) -> str:
    if value not in MASTER_READINESS_CHOICES:
        raise ValueError("unsupported native-level readiness choice")
    return str(value)


def _problem_tag_map(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, Mapping) or set(value) != {
        BALANCED_CONTROL,
        LISTENING_MASTER,
    }:
        raise ValueError(
            "problem tags must name balanced_control and listening_master"
        )
    return {
        identity: _problem_tags(value[identity], label=identity)
        for identity in (BALANCED_CONTROL, LISTENING_MASTER)
    }


def _path_free_notes(value: Any) -> str:
    checked = _notes(value)
    if checked is not None and not _path_free_document(checked):
        raise ValueError("native-level readiness notes must be path-free")
    return checked or ""


def _validate_stored_review(review: Mapping[str, Any]) -> None:
    expected = {
        "schema",
        "status",
        "identity_labelled",
        "native_level",
        "policy",
        "readiness_review_id",
        "comparison_sha256",
        "quality_review",
        "reviewer_session_id",
        "evidence",
        "response",
        "export_ready",
        "privacy",
        "effects",
        "readiness_review_sha256",
    }
    unsigned = {
        key: value
        for key, value in review.items()
        if key != "readiness_review_sha256"
    }
    if (
        set(review) != expected
        or review.get("schema") != MASTER_READINESS_REVIEW_SCHEMA
        or review.get("status") != "reviewed"
        or review.get("identity_labelled") is not True
        or review.get("native_level") is not True
        or review.get("policy") != MASTER_READINESS_POLICY
        or review.get("export_ready") is not True
        or review.get("effects") != REVIEW_EFFECTS
        or review.get("readiness_review_sha256") != _document_hash(unsigned)
        or not _path_free_document(review)
    ):
        raise ValueError("stored native-level readiness review is invalid")
    for field, label in (
        ("readiness_review_id", "native-level readiness review identity"),
        ("comparison_sha256", "native-level comparison SHA-256"),
        ("reviewer_session_id", "native-level reviewer identity"),
    ):
        _sha256(review.get(field), label=label)
    _validate_quality_anchor(review.get("quality_review"))
    evidence = review.get("evidence")
    if (
        not isinstance(evidence, Mapping)
        or _document_hash(evidence) != review["comparison_sha256"]
        or evidence.get("quality_review") != review["quality_review"]
    ):
        raise ValueError("stored native-level readiness evidence is invalid")
    _validate_comparison_binding(evidence)
    response = review.get("response")
    if not isinstance(response, Mapping) or set(response) != {
        "heard",
        "choice",
        "problem_tags",
        "notes",
    }:
        raise ValueError("stored native-level readiness response is invalid")
    if _heard(response["heard"]) != response["heard"]:
        raise ValueError("stored native-level heard evidence is invalid")
    if _choice(response["choice"]) != response["choice"]:
        raise ValueError("stored native-level choice is invalid")
    if _problem_tag_map(response["problem_tags"]) != response["problem_tags"]:
        raise ValueError("stored native-level problem tags are invalid")
    if _path_free_notes(response["notes"]) != response["notes"]:
        raise ValueError("stored native-level notes are invalid")
    privacy = review.get("privacy")
    if (
        not isinstance(privacy, Mapping)
        or set(privacy)
        != {
            "local_only",
            "reviewer_key_stored",
            "notes_private",
            "notes_may_contain_identifying_material",
        }
        or privacy.get("local_only") is not True
        or privacy.get("reviewer_key_stored") is not False
        or privacy.get("notes_private") is not True
        or privacy.get("notes_may_contain_identifying_material")
        is not bool(response["notes"])
    ):
        raise ValueError("stored native-level privacy evidence is invalid")
    expected_review_id = _document_hash(
        {
            "schema": MASTER_READINESS_REVIEW_SCHEMA,
            "comparison_sha256": review["comparison_sha256"],
            "quality_result_sha256": review["quality_review"][
                "quality_result_sha256"
            ],
            "reviewer_session_id": review["reviewer_session_id"],
            "response": response,
        }
    )
    if review["readiness_review_id"] != expected_review_id:
        raise ValueError("stored native-level readiness identity is invalid")


def _source_binding_document(
    *,
    comparison: Mapping[str, Any],
    private: Mapping[str, Any],
) -> dict[str, Any]:
    comparison_sha256 = _document_hash(comparison)
    specifications = {
        BALANCED_CONTROL: (
            "control_path",
            "control_record",
            comparison["balanced_control"]["preview"],
        ),
        LISTENING_MASTER: (
            "master_path",
            "master_record",
            comparison["listening_master"]["wav"],
        ),
    }
    sources: dict[str, Any] = {}
    for identity, (path_key, record_key, public_record) in specifications.items():
        record = private.get(record_key)
        path_value = private.get(path_key)
        if (
            not isinstance(record, Mapping)
            or not isinstance(path_value, str)
            or not isinstance(public_record, Mapping)
            or set(public_record) != {"name", "bytes", "sha256"}
        ):
            raise ValueError("native-level readiness source binding is invalid")
        canonical = absolute_path(path_value)
        source = {
            "path": str(canonical),
            "name": public_record["name"],
            "bytes": public_record["bytes"],
            "sha256": public_record["sha256"],
        }
        if (
            record.get("path") != source["path"]
            or _without_path(record) != _without_path(source)
            or canonical.name != source["name"]
        ):
            raise ValueError("native-level readiness source binding is invalid")
        sources[identity] = source
    unsigned = {
        "schema": MASTER_READINESS_SOURCE_BINDING_SCHEMA,
        "comparison_sha256": comparison_sha256,
        "sources": sources,
    }
    return {
        **unsigned,
        "source_binding_sha256": _document_hash(unsigned),
    }


def _verified_source_values(
    *,
    directory: Path,
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    source_binding = _read_private_json(directory / _SOURCE_BINDING_NAME)
    expected_fields = {
        "schema",
        "comparison_sha256",
        "sources",
        "source_binding_sha256",
    }
    unsigned = {
        key: value
        for key, value in source_binding.items()
        if key != "source_binding_sha256"
    }
    sources = source_binding.get("sources")
    if (
        set(source_binding) != expected_fields
        or source_binding.get("schema") != MASTER_READINESS_SOURCE_BINDING_SCHEMA
        or source_binding.get("comparison_sha256") != _document_hash(binding)
        or source_binding.get("source_binding_sha256") != _document_hash(unsigned)
        or not isinstance(sources, Mapping)
        or set(sources) != {BALANCED_CONTROL, LISTENING_MASTER}
    ):
        raise ValueError("native-level readiness source binding is invalid")

    public_records = {
        BALANCED_CONTROL: binding["balanced_control"]["preview"],
        LISTENING_MASTER: binding["listening_master"]["wav"],
    }
    window = binding["window"]
    values: dict[str, Any] = {}
    for identity in (BALANCED_CONTROL, LISTENING_MASTER):
        record = sources[identity]
        public_record = public_records[identity]
        if (
            not isinstance(record, Mapping)
            or set(record) != {"path", "name", "bytes", "sha256"}
            or not isinstance(public_record, Mapping)
            or set(public_record) != {"name", "bytes", "sha256"}
            or _without_path(record) != public_record
            or not isinstance(record.get("path"), str)
        ):
            raise ValueError("native-level readiness source binding is invalid")
        canonical = absolute_path(str(record["path"]))
        if str(canonical) != record["path"] or canonical.name != record["name"]:
            raise ValueError("native-level readiness source binding is invalid")
        values[identity] = read_audio_window(
            canonical,
            expected=record,
            start_frame=int(window["start_frame"]),
            frame_count=int(window["frame_count"]),
            label=f"{_identity_label(identity)} native-level source",
        )
    return values


def _verified_pcm24_output(
    path: Path,
    *,
    expected_frames: int,
    expected_sample_rate: int,
    expected_channels: int,
    expected_values: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    record = private_file_record(
        path,
        label="native-level readiness output",
        maximum_bytes=MAXIMUM_AUDIO_BYTES,
    )
    soundfile = soundfile_module()
    info = soundfile.info(str(path))
    values, sample_rate = soundfile.read(
        str(path),
        dtype="float64",
        always_2d=True,
    )
    np = numpy_module()
    peak = float(np.max(np.abs(values))) if len(values) else 0.0
    if (
        str(info.format) != "WAV"
        or str(info.subtype) != "PCM_24"
        or int(sample_rate) != expected_sample_rate
        or int(info.channels) != expected_channels
        or int(info.frames) != expected_frames
        or not np.all(np.isfinite(values))
        or not math.isfinite(peak)
        or peak >= FULL_SCALE_GUARD
    ):
        raise RuntimeError("native-level readiness output geometry changed")
    if expected_values is not None and not np.array_equal(values, expected_values):
        raise RuntimeError("native-level readiness PCM24 crop changed source samples")
    rms_value = rms(np, values)
    return record, {
        "format": "WAV",
        "subtype": "PCM_24",
        "sample_rate": int(sample_rate),
        "channels": int(info.channels),
        "frames": int(info.frames),
        "rms_dbfs": round(dbfs(rms_value), 6),
        "sample_peak_dbfs": round(dbfs(peak), 6),
    }


def _write_pcm24(path: Path, values: Any, sample_rate: int) -> None:
    soundfile_module().write(
        str(path),
        values,
        sample_rate,
        format="WAV",
        subtype="PCM_24",
    )
    path.chmod(0o600)
    require_owner_only_regular_file(path)


def _reviewer_session_id(value: Any) -> str:
    key = _bounded_text(
        value,
        label="reviewer/session key",
        maximum=MAXIMUM_REVIEWER_KEY_CHARACTERS,
    )
    return hashlib.sha256(
        b"sunofriend.workbench-master-readiness-reviewer.v1\0"
        + key.encode("utf-8")
    ).hexdigest()


def _identity(value: Any) -> str:
    if value not in {BALANCED_CONTROL, LISTENING_MASTER}:
        raise ValueError(
            "native-level identity must be balanced_control or listening_master"
        )
    return str(value)


def _identity_label(identity: str) -> str:
    if identity == BALANCED_CONTROL:
        return "Balanced control"
    if identity == LISTENING_MASTER:
        return "Listening Master"
    raise ValueError("unsupported native-level identity")


def _without_path(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): _json_copy(item)
        for key, item in value.items()
        if key != "path"
    }


def _finite_positive(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


__all__ = [
    "MASTER_READINESS_AUDIO_POLICY",
    "MASTER_READINESS_AUDIO_SCHEMA",
    "MASTER_READINESS_CHOICES",
    "MASTER_READINESS_COMPARISON_SCHEMA",
    "MASTER_READINESS_POLICY",
    "MASTER_READINESS_PROBLEM_TAGS",
    "MASTER_READINESS_REVIEW_SCHEMA",
    "PREPARE_EFFECTS",
    "REVIEW_EFFECTS",
    "WorkbenchMasterReadinessConflictError",
    "WorkbenchMasterReadinessGateError",
    "WorkbenchMasterReadinessService",
]
