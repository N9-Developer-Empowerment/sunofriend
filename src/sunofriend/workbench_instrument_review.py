"""Blind fixed-MIDI review of complete bass instruments.

The review changes only General MIDI Program Change data in private audition
proxies.  Every note event, tempo event, controller, pitch bend, and other MIDI
byte stays untouched.  The selected MIDI, Workbench decisions, arrangement,
packs, and defaults remain immutable.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import shutil
import sqlite3
import stat
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .clip import read_midi_clips
from .midi_transform import _parse_midi
from .render import find_fluidsynth, render_midi_to_wav
from .workbench_artifacts import INSTRUMENT_REVIEW_CONTEXT_SCHEMA


INSTRUMENT_REVIEW_COMPARISON_SCHEMA = (
    "sunofriend.workbench-instrument-review.comparison.v1"
)
INSTRUMENT_REVIEW_AUDIO_SCHEMA = "sunofriend.workbench-instrument-review.audio.v1"
INSTRUMENT_REVIEW_SCHEMA = "sunofriend.workbench-instrument-review.review.v1"
INSTRUMENT_REVIEW_RESULT_SCHEMA = "sunofriend.workbench-instrument-review.result.v1"
INSTRUMENT_REVIEW_POLICY = "blind-fixed-midi-complete-gm-patch-rms-v1"
INSTRUMENT_REVIEW_ASSIGNMENT_POLICY = "secret-random-per-comparison-v1"
INSTRUMENT_REVIEW_LEVEL_POLICY = (
    "source-and-candidates-common-rms-attenuation-only-v1"
)
INSTRUMENT_REVIEW_RENDER_POLICY = (
    "same-midi-same-soundfont-fluidsynth-dry-program-only-v1"
)

SOURCE_REFERENCE = "source_reference"
CANDIDATE_A = "candidate_a"
CANDIDATE_B = "candidate_b"
CONTROL = "control"
CHALLENGER = "challenger"

INSTRUMENT_REVIEW_CHOICES = frozenset(
    {
        CANDIDATE_A,
        CANDIDATE_B,
        "equivalent",
        "none_usable",
        "cannot_tell",
    }
)
INSTRUMENT_REVIEW_PROBLEM_TAGS = frozenset(
    {
        "abrupt_tone_change",
        "harsh",
        "inconsistent_tone",
        "masked",
        "muddy",
        "silent_or_missing_notes",
        "thin",
        "too_buzzy",
        "too_plucky",
        "weak_sustain",
        "wrong_timbre_family",
    }
)

MINIMUM_WINDOW_SECONDS = 0.5
MAXIMUM_WINDOW_SECONDS = 15.0
MAXIMUM_NOTES_CHARACTERS = 2_000
MAXIMUM_REVIEWER_KEY_CHARACTERS = 128
MAXIMUM_PROBLEM_TAGS_PER_CANDIDATE = 8
MAXIMUM_JSON_BYTES = 4 * 1024 * 1024
MAXIMUM_AUDIO_BYTES = 256 * 1024 * 1024
MAXIMUM_MIDI_BYTES = 64 * 1024 * 1024
MAXIMUM_SOURCE_AUDIO_BYTES = 2 * 1024 * 1024 * 1024
MAXIMUM_SOUNDFONT_BYTES = 2 * 1024 * 1024 * 1024
MAXIMUM_RENDERER_BYTES = 256 * 1024 * 1024
MAXIMUM_AGGREGATE_INPUT_BYTES = 3 * 1024 * 1024 * 1024
MAXIMUM_MIDI_NOTE_ONS = 250_000
MAXIMUM_RENDER_HORIZON_SECONDS = 20 * 60
MINIMUM_RMS_DBFS = -60.0
MAXIMUM_ATTENUATION_DB = 18.0
MAXIMUM_FINAL_RMS_MISMATCH_DB = 0.05
SAMPLE_PEAK_CEILING_DBFS = -1.0
SOURCE_SNAPSHOT_POLICY = (
    "decode-exact-requested-frame-window-to-private-float32-v1"
)

_DATABASE_NAME = "reviews.sqlite3"
_AUDIO_DIRECTORY = "audio"
_MANIFEST_NAME = "manifest.json"
_EXPECTED_PROGRAMS = {
    CONTROL: {
        "program": 38,
        "general_midi_number": 39,
        "label": "Synth Bass 1",
    },
    CHALLENGER: {
        "program": 39,
        "general_midi_number": 40,
        "label": "Synth Bass 2",
    },
}
_NO_PRODUCT_EFFECTS = {
    "midi_mutated": False,
    "selection_changed": False,
    "automatic_selection": False,
    "automatic_ranking": False,
    "default_selection_changed": False,
    "pack_changed": False,
    "product_completion_changed": False,
}
PREPARE_EFFECTS = {
    **_NO_PRODUCT_EFFECTS,
    "feedback_recorded": False,
    "review_record_created": False,
    "resolution_record_created": False,
}
REVIEW_EFFECTS = {
    **PREPARE_EFFECTS,
    "feedback_recorded": True,
    "review_record_created": True,
}
RESOLUTION_EFFECTS = {
    **PREPARE_EFFECTS,
    "resolution_record_created": True,
}


class WorkbenchInstrumentReviewConflictError(RuntimeError):
    """The selected MIDI, source, renderer, or SoundFont is no longer current."""


class WorkbenchInstrumentReviewRevisionConflictError(RuntimeError):
    """A review append used a stale expected revision."""

    def __init__(self, *, expected_revision: int, current_revision: int) -> None:
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        super().__init__(
            "Instrument review revision conflict: "
            f"expected {expected_revision}, current revision is {current_revision}"
        )


class WorkbenchInstrumentReviewService:
    """Private local fixed-MIDI comparison, review, and resolution service."""

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
        context: Mapping[str, Any],
        start_seconds: float,
        end_seconds: float,
        reviewer_session_key: str,
    ) -> dict[str, Any]:
        """Prepare a blind, exact-frame source/A/B bass review."""

        evidence = _verified_context_evidence(context)
        window = _review_window(
            start_seconds,
            end_seconds,
            sample_rate=int(evidence["public"]["geometry"]["sample_rate"]),
            total_frames=int(evidence["public"]["geometry"]["frames"]),
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
        reviewer_id = _reviewer_session_id(reviewer_session_key)
        current_review = self._latest_review(
            comparison_sha256=comparison_sha256,
            reviewer_session_id=reviewer_id,
        )
        return _prepared_document(
            comparison=comparison,
            comparison_sha256=comparison_sha256,
            nonce_commitment=str(session["nonce_commitment"]),
            manifest=manifest,
            current_review=current_review,
        )

    def media_record(
        self,
        comparison_sha256: str,
        candidate: str,
    ) -> dict[str, Any]:
        """Return one verified private audio record for loopback registration."""

        comparison_id = _sha256_text(
            comparison_sha256, label="comparison SHA-256"
        )
        slot = _media_slot(candidate)
        session = self._session(comparison_id)
        manifest = self._load_audio_manifest(
            comparison_id,
            nonce=bytes(session["nonce"]),
            nonce_commitment=str(session["nonce_commitment"]),
        )
        row = (
            manifest["source_reference"]
            if slot == SOURCE_REFERENCE
            else manifest["candidates"][slot]
        )
        record = row["audio"]
        path = self.audio_root / comparison_id / str(record["name"])
        actual = _private_file_record(path, label=f"{slot} review audio")
        if _without_path(actual) != record:
            raise ValueError("instrument review audio changed")
        return actual

    def comparison_binding(self, comparison_sha256: str) -> dict[str, Any]:
        """Return the verified path-free pins stored for a prepared comparison."""

        comparison_id = _sha256_text(
            comparison_sha256, label="comparison SHA-256"
        )
        binding = _session_binding(self._session(comparison_id))
        if (
            binding.get("schema") != INSTRUMENT_REVIEW_COMPARISON_SCHEMA
            or binding.get("effects") != PREPARE_EFFECTS
            or _document_hash(binding) != comparison_id
        ):
            raise ValueError("instrument comparison binding is invalid")
        _require_path_free(binding, label="instrument comparison binding")
        return _json_copy(binding)

    def current(
        self,
        *,
        context: Mapping[str, Any],
        comparison_sha256: str,
        reviewer_session_key: str,
    ) -> dict[str, Any]:
        """Return current blind state after re-verifying all input anchors."""

        comparison_id = _sha256_text(
            comparison_sha256, label="comparison SHA-256"
        )
        session = self._session(comparison_id)
        binding = _session_binding(session)
        self._require_current_context(
            context=context,
            binding=binding,
            comparison_sha256=comparison_id,
        )
        manifest = self._load_audio_manifest(
            comparison_id,
            nonce=bytes(session["nonce"]),
            nonce_commitment=str(session["nonce_commitment"]),
        )
        current_review = self._latest_review(
            comparison_sha256=comparison_id,
            reviewer_session_id=_reviewer_session_id(reviewer_session_key),
        )
        return _prepared_document(
            comparison=binding,
            comparison_sha256=comparison_id,
            nonce_commitment=str(session["nonce_commitment"]),
            manifest=manifest,
            current_review=current_review,
        )

    def complete(
        self,
        *,
        context: Mapping[str, Any],
        comparison_sha256: str,
        reviewer_session_key: str,
        expected_revision: int,
        heard: Mapping[str, Any],
        choice: str,
        problem_tags: Mapping[str, Sequence[str]],
        notes: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Append one durable blind review with CAS and exact-retry semantics."""

        comparison_id = _sha256_text(
            comparison_sha256, label="comparison SHA-256"
        )
        session = self._session(comparison_id)
        binding = _session_binding(session)
        self._require_current_context(
            context=context,
            binding=binding,
            comparison_sha256=comparison_id,
        )
        self._load_audio_manifest(
            comparison_id,
            nonce=bytes(session["nonce"]),
            nonce_commitment=str(session["nonce_commitment"]),
        )
        checked_revision = _nonnegative_int(
            expected_revision, label="expected revision"
        )
        reviewer_id = _reviewer_session_id(reviewer_session_key)
        response = {
            "heard": _heard(heard),
            "choice": _choice(choice),
            "problem_tags": _problem_tag_map(problem_tags),
            "notes": _notes_map(notes),
        }
        revision = checked_revision + 1
        review_id = _document_hash(
            {
                "schema": INSTRUMENT_REVIEW_SCHEMA,
                "comparison_sha256": comparison_id,
                "reviewer_session_id": reviewer_id,
                "revision": revision,
                "response": response,
            }
        )
        unsigned = {
            "schema": INSTRUMENT_REVIEW_SCHEMA,
            "status": "reviewed",
            "blind": True,
            "policy": INSTRUMENT_REVIEW_POLICY,
            "review_id": review_id,
            "comparison_sha256": comparison_id,
            "reviewer_session_id": reviewer_id,
            "revision": revision,
            "nonce_commitment": str(session["nonce_commitment"]),
            "evidence": binding,
            "response": response,
            "privacy": {
                "local_only": True,
                "reviewer_session_key_stored": False,
                "notes_private": True,
                "notes_may_contain_identifying_material": any(
                    bool(value) for value in response["notes"].values()
                ),
            },
            "effects": dict(REVIEW_EFFECTS),
        }
        document = {**unsigned, "review_sha256": _document_hash(unsigned)}
        _require_path_free(document, label="instrument review")
        return self._append_review_idempotent(
            comparison_sha256=comparison_id,
            reviewer_session_id=reviewer_id,
            expected_revision=checked_revision,
            review=document,
        )

    def review(self, review_id: str) -> dict[str, Any]:
        """Return one verified stored blind review."""

        value = self._review(_sha256_text(review_id, label="review identity"))
        self._require_review_binding(value)
        return _json_copy(value)

    def resolve(
        self,
        *,
        context: Mapping[str, Any],
        comparison_sha256: str,
        review_id: str,
        review_sha256: str,
    ) -> dict[str, Any]:
        """Reveal one review's A/B program identities without promoting either."""

        comparison_id = _sha256_text(
            comparison_sha256, label="comparison SHA-256"
        )
        checked_review_id = _sha256_text(review_id, label="review identity")
        checked_review_sha = _sha256_text(
            review_sha256, label="review SHA-256"
        )
        review = self._review(checked_review_id)
        self._require_review_binding(review)
        if (
            review["comparison_sha256"] != comparison_id
            or review["review_sha256"] != checked_review_sha
        ):
            raise WorkbenchInstrumentReviewConflictError(
                "instrument review identity or receipt changed"
            )
        session = self._session(comparison_id)
        binding = _session_binding(session)
        self._require_current_context(
            context=context,
            binding=binding,
            comparison_sha256=comparison_id,
        )
        manifest = self._load_audio_manifest(
            comparison_id,
            nonce=bytes(session["nonce"]),
            nonce_commitment=str(session["nonce_commitment"]),
        )
        assignment = _blind_mapping(bytes(session["nonce"]), comparison_id)
        if manifest["private_assignment"] != assignment:
            raise ValueError("instrument review assignment changed")
        identities = manifest["private_identities"]
        revealed_assignment = {
            slot: {
                "identity": identity,
                **identities[identity],
            }
            for slot, identity in assignment.items()
        }
        response = review["response"]
        choice_value = str(response["choice"])
        resolved_choice = (
            assignment[choice_value]
            if choice_value in assignment
            else choice_value
        )
        tags = {
            assignment[CANDIDATE_A]: list(
                response["problem_tags"][CANDIDATE_A]
            ),
            assignment[CANDIDATE_B]: list(
                response["problem_tags"][CANDIDATE_B]
            ),
        }
        notes = {
            assignment[CANDIDATE_A]: str(response["notes"][CANDIDATE_A]),
            assignment[CANDIDATE_B]: str(response["notes"][CANDIDATE_B]),
        }
        unsigned = {
            "schema": INSTRUMENT_REVIEW_RESULT_SCHEMA,
            "status": "complete",
            "blind_review": True,
            "policy": INSTRUMENT_REVIEW_POLICY,
            "review_id": checked_review_id,
            "review_sha256": checked_review_sha,
            "comparison_sha256": comparison_id,
            "nonce_commitment": str(session["nonce_commitment"]),
            "assignment_nonce": bytes(session["nonce"]).hex(),
            "assignment": revealed_assignment,
            "resolved_choice": resolved_choice,
            "problem_tags": {
                CONTROL: tags[CONTROL],
                CHALLENGER: tags[CHALLENGER],
            },
            "notes": {
                CONTROL: notes[CONTROL],
                CHALLENGER: notes[CHALLENGER],
            },
            "promotion_allowed": False,
            "default_changed": False,
            "effects": dict(RESOLUTION_EFFECTS),
        }
        result = {**unsigned, "result_sha256": _document_hash(unsigned)}
        _require_path_free(result, label="instrument review resolution")
        return self._save_or_load_resolution(result)

    def resolution(self, review_id: str) -> dict[str, Any] | None:
        """Return an existing separate identity resolution."""

        checked_review_id = _sha256_text(review_id, label="review identity")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM review_resolutions WHERE review_id = ?",
                (checked_review_id,),
            ).fetchone()
        if row is None:
            return None
        value = _json_object(str(row[0]), label="instrument review resolution")
        self._require_resolution_binding(value)
        return _json_copy(value)

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
        work = Path(
            tempfile.mkdtemp(
                prefix=f".{comparison_sha256}.building-",
                dir=self.audio_root,
            )
        )
        work.chmod(0o700)
        try:
            private = evidence["private"]
            window = comparison["window"]
            start_frame = int(window["start_frame"])
            frame_count = int(window["frame_count"])
            sample_rate = int(comparison["geometry"]["sample_rate"])
            channels = int(comparison["geometry"]["channels"])
            source_snapshot = _verified_source_window_snapshot(
                Path(private["source_path"]),
                private["source_record"],
                work / "source-window-float32.wav",
                start_frame=start_frame,
                frame_count=frame_count,
                sample_rate=sample_rate,
                channels=channels,
                label="bass source stem",
            )
            selected_snapshot = _verified_snapshot(
                Path(private["midi_path"]),
                private["midi_record"],
                work / "selected-midi.mid",
                label="selected bass MIDI",
            )
            soundfont_snapshot = _verified_snapshot(
                Path(private["soundfont_path"]),
                private["soundfont_record"],
                work / "render-bank.sf2",
                label="SoundFont",
            )
            original_selected_sha = _file_sha256(selected_snapshot)
            program_evidence: dict[str, Any] = {}
            raw_audio: dict[str, Path] = {}
            for identity in (CONTROL, CHALLENGER):
                program = int(private["programs"][identity]["program"])
                proxy = work / f"{identity}-proxy.mid"
                program_evidence[identity] = _write_program_proxy(
                    selected_snapshot,
                    proxy,
                    program=program,
                )
                rendered = work / f"{identity}-raw.wav"
                render_midi_to_wav(
                    proxy,
                    rendered,
                    sample_rate=int(comparison["geometry"]["sample_rate"]),
                    gain=0.7,
                    soundfont_path=soundfont_snapshot,
                    fluidsynth_path=str(private["renderer_path"]),
                )
                rendered.chmod(0o600)
                raw_audio[identity] = rendered
            if (
                _file_sha256(selected_snapshot) != original_selected_sha
                or original_selected_sha
                != comparison["selected_midi"]["sha256"]
            ):
                raise RuntimeError("selected MIDI changed while rendering instruments")

            source_audio = _read_exact_audio_window(
                source_snapshot,
                start_frame=0,
                frame_count=frame_count,
                expected_sample_rate=sample_rate,
                expected_channels=channels,
                pad=False,
                label="source reference",
            )
            candidate_audio = {
                identity: _read_exact_audio_window(
                    raw_audio[identity],
                    start_frame=start_frame,
                    frame_count=frame_count,
                    expected_sample_rate=sample_rate,
                    expected_channels=channels,
                    pad=True,
                    label=f"{identity} rendered instrument",
                )
                for identity in (CONTROL, CHALLENGER)
            }
            matched, level_match = _common_level_match(
                {
                    SOURCE_REFERENCE: source_audio,
                    **candidate_audio,
                }
            )

            source_output = work / "source-reference.wav"
            _write_pcm16(source_output, matched[SOURCE_REFERENCE], sample_rate)
            source_record, source_info = _verified_output_audio(
                source_output,
                expected_frames=frame_count,
                expected_sample_rate=sample_rate,
                expected_channels=channels,
            )
            assignment = _blind_mapping(nonce, comparison_sha256)
            candidate_rows: dict[str, Any] = {}
            for slot in (CANDIDATE_A, CANDIDATE_B):
                identity = assignment[slot]
                output = work / f"{slot.replace('_', '-')}.wav"
                _write_pcm16(output, matched[identity], sample_rate)
                record, info = _verified_output_audio(
                    output,
                    expected_frames=frame_count,
                    expected_sample_rate=sample_rate,
                    expected_channels=channels,
                )
                candidate_rows[slot] = {
                    "identity": identity,
                    "audio": _without_path(record),
                    **info,
                    "applied_gain_db": level_match["inputs"][identity][
                        "applied_gain_db"
                    ],
                }
            final_levels = {
                SOURCE_REFERENCE: float(source_info["rms_dbfs"]),
                CANDIDATE_A: float(candidate_rows[CANDIDATE_A]["rms_dbfs"]),
                CANDIDATE_B: float(candidate_rows[CANDIDATE_B]["rms_dbfs"]),
            }
            final_mismatch = max(final_levels.values()) - min(
                final_levels.values()
            )
            if final_mismatch > MAXIMUM_FINAL_RMS_MISMATCH_DB:
                raise RuntimeError(
                    "instrument review PCM16 level mismatch exceeds "
                    f"{MAXIMUM_FINAL_RMS_MISMATCH_DB:.2f} dB"
                )
            if any(
                float(value["sample_peak_dbfs"])
                > SAMPLE_PEAK_CEILING_DBFS + 0.001
                for value in [source_info, *candidate_rows.values()]
            ):
                raise RuntimeError(
                    "instrument review PCM16 peak exceeds the disclosed ceiling"
                )
            level_match["final_pcm16"] = {
                "source_reference_rms_dbfs": source_info["rms_dbfs"],
                "candidate_a_rms_dbfs": candidate_rows[CANDIDATE_A]["rms_dbfs"],
                "candidate_b_rms_dbfs": candidate_rows[CANDIDATE_B]["rms_dbfs"],
                "mismatch_db": round(final_mismatch, 6),
                "within_tolerance": True,
            }

            # Re-verify every original input after rendering.  Only the private
            # proxy Program Change bytes are permitted to differ.
            current = _verified_context_evidence(private["context"])
            if current["public"] != evidence["public"]:
                raise WorkbenchInstrumentReviewConflictError(
                    "instrument review evidence changed during preparation"
                )
            if _file_sha256(selected_snapshot) != comparison["selected_midi"][
                "sha256"
            ]:
                raise RuntimeError("selected MIDI snapshot was mutated")

            for path in (
                source_snapshot,
                soundfont_snapshot,
                raw_audio[CONTROL],
                raw_audio[CHALLENGER],
            ):
                path.unlink()
            source_row = {
                "audio": _without_path(source_record),
                **source_info,
                "label": "Original bass stem reference",
                "level_policy": INSTRUMENT_REVIEW_LEVEL_POLICY,
                "level_matched_to_candidates": True,
                "applied_gain_db": level_match["inputs"][SOURCE_REFERENCE][
                    "applied_gain_db"
                ],
            }
            private_identities = {
                identity: {
                    **private["programs"][identity],
                    "proxy_midi": _without_path(
                        _private_file_record(
                            work / f"{identity}-proxy.mid",
                            label=f"{identity} proxy MIDI",
                        )
                    ),
                    "proxy_evidence": program_evidence[identity],
                }
                for identity in (CONTROL, CHALLENGER)
            }
            selected_record = _private_file_record(
                selected_snapshot, label="selected MIDI snapshot"
            )
            unsigned = {
                "schema": INSTRUMENT_REVIEW_AUDIO_SCHEMA,
                "comparison_sha256": comparison_sha256,
                "comparison_binding_sha256": _document_hash(comparison),
                "nonce_commitment": nonce_commitment,
                "assignment_policy": INSTRUMENT_REVIEW_ASSIGNMENT_POLICY,
                "private_assignment": assignment,
                "private_identities": private_identities,
                "selected_midi_snapshot": _without_path(selected_record),
                "window": _json_copy(comparison["window"]),
                "source_reference": source_row,
                "level_match": level_match,
                "candidates": candidate_rows,
                "path_free_manifest": True,
                "private_audio": True,
                "effects": dict(PREPARE_EFFECTS),
            }
            manifest = {**unsigned, "manifest_sha256": _document_hash(unsigned)}
            _require_path_free(manifest, label="private instrument review manifest")
            _write_private_json(work / _MANIFEST_NAME, manifest)
            try:
                os.replace(work, final)
            except OSError:
                if not final.exists():
                    raise
                winner = self._load_audio_manifest(
                    comparison_sha256,
                    nonce=nonce,
                    nonce_commitment=nonce_commitment,
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
        if loaded is None:  # pragma: no cover - defensive
            raise RuntimeError("instrument review publication failed")
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
            raise ValueError("instrument review audio is unavailable")
        _require_owner_only_directory(directory)
        manifest = _read_private_json(directory / _MANIFEST_NAME)
        unsigned = {
            key: value for key, value in manifest.items() if key != "manifest_sha256"
        }
        binding = _session_binding(self._session(comparison_sha256))
        assignment = _blind_mapping(nonce, comparison_sha256)
        if (
            manifest.get("schema") != INSTRUMENT_REVIEW_AUDIO_SCHEMA
            or manifest.get("comparison_sha256") != comparison_sha256
            or manifest.get("comparison_binding_sha256") != comparison_sha256
            or manifest.get("nonce_commitment") != nonce_commitment
            or manifest.get("assignment_policy")
            != INSTRUMENT_REVIEW_ASSIGNMENT_POLICY
            or manifest.get("private_assignment") != assignment
            or manifest.get("window") != binding.get("window")
            or manifest.get("path_free_manifest") is not True
            or manifest.get("private_audio") is not True
            or manifest.get("effects") != PREPARE_EFFECTS
            or manifest.get("manifest_sha256") != _document_hash(unsigned)
        ):
            raise ValueError("instrument review audio manifest is invalid")
        _require_path_free(manifest, label="private instrument review manifest")
        source = manifest.get("source_reference")
        candidates = manifest.get("candidates")
        identities = manifest.get("private_identities")
        if (
            not isinstance(source, Mapping)
            or not isinstance(candidates, Mapping)
            or set(candidates) != {CANDIDATE_A, CANDIDATE_B}
            or not isinstance(identities, Mapping)
            or set(identities) != {CONTROL, CHALLENGER}
        ):
            raise ValueError("instrument review audio manifest is incomplete")
        if (
            source.get("label") != "Original bass stem reference"
            or source.get("level_policy") != INSTRUMENT_REVIEW_LEVEL_POLICY
            or source.get("level_matched_to_candidates") is not True
        ):
            raise ValueError("instrument review source disclosure is invalid")
        geometry = binding["geometry"]
        frame_count = int(binding["window"]["frame_count"])
        for slot, row in [(SOURCE_REFERENCE, source), *candidates.items()]:
            if not isinstance(row, Mapping) or not isinstance(
                row.get("audio"), Mapping
            ):
                raise ValueError("instrument review media record is invalid")
            record = row["audio"]
            actual, info = _verified_output_audio(
                directory / str(record.get("name", "")),
                expected_frames=frame_count,
                expected_sample_rate=int(geometry["sample_rate"]),
                expected_channels=int(geometry["channels"]),
            )
            if _without_path(actual) != record or any(
                row.get(key) != info[key]
                for key in (
                    "sample_rate",
                    "channels",
                    "frames",
                    "rms_dbfs",
                    "sample_peak_dbfs",
                )
            ):
                raise ValueError(f"{slot} instrument review audio changed")
        selected = manifest.get("selected_midi_snapshot")
        if not isinstance(selected, Mapping):
            raise ValueError("selected MIDI snapshot record is invalid")
        selected_actual = _private_file_record(
            directory / str(selected.get("name", "")),
            label="selected MIDI snapshot",
        )
        if (
            _without_path(selected_actual) != selected
            or selected.get("sha256") != binding["selected_midi"]["sha256"]
        ):
            raise ValueError("selected MIDI snapshot changed")
        for identity in (CONTROL, CHALLENGER):
            row = identities[identity]
            if (
                not isinstance(row, Mapping)
                or {
                    key: row.get(key)
                    for key in ("program", "general_midi_number", "label")
                }
                != _EXPECTED_PROGRAMS[identity]
                or not isinstance(row.get("proxy_midi"), Mapping)
            ):
                raise ValueError("instrument identity evidence is invalid")
            proxy_record = row["proxy_midi"]
            proxy_path = directory / str(proxy_record.get("name", ""))
            actual = _private_file_record(
                proxy_path, label=f"{identity} proxy MIDI"
            )
            if _without_path(actual) != proxy_record:
                raise ValueError("instrument proxy MIDI changed")
            verified = _program_proxy_evidence(
                directory / str(selected["name"]),
                proxy_path,
                expected_program=int(row["program"]),
            )
            if verified != row.get("proxy_evidence"):
                raise ValueError("instrument proxy note invariants changed")
        final_levels = (
            float(source["rms_dbfs"]),
            float(candidates[CANDIDATE_A]["rms_dbfs"]),
            float(candidates[CANDIDATE_B]["rms_dbfs"]),
        )
        mismatch = max(final_levels) - min(final_levels)
        if mismatch > MAXIMUM_FINAL_RMS_MISMATCH_DB:
            raise ValueError("instrument review audio levels changed")
        if any(
            float(row["sample_peak_dbfs"])
            > SAMPLE_PEAK_CEILING_DBFS + 0.001
            for row in [source, *candidates.values()]
        ):
            raise ValueError("instrument review audio peak ceiling changed")
        _validate_level_manifest(
            manifest.get("level_match"),
            source=source,
            candidates=candidates,
            final_mismatch=mismatch,
        )
        return manifest

    def _require_current_context(
        self,
        *,
        context: Mapping[str, Any],
        binding: Mapping[str, Any],
        comparison_sha256: str,
    ) -> None:
        current = _verified_context_evidence(context)
        window = binding.get("window")
        if not isinstance(window, Mapping):
            raise ValueError("instrument review window is invalid")
        current_comparison = _comparison_document(current["public"], window)
        if (
            current_comparison != binding
            or _document_hash(current_comparison) != comparison_sha256
        ):
            raise WorkbenchInstrumentReviewConflictError(
                "instrument review evidence is no longer current"
            )

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
                CREATE TABLE IF NOT EXISTS review_resolutions (
                    review_id TEXT PRIMARY KEY,
                    result_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    FOREIGN KEY (review_id) REFERENCES review_events(review_id)
                )
                """
            )
        self.database_path.chmod(0o600)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = DELETE")
        if self.database_path.exists():
            self.database_path.chmod(0o600)
        return connection

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
        _require_path_free(binding, label="instrument comparison binding")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT project_id, binding_json, nonce, nonce_commitment
                FROM comparison_sessions WHERE comparison_sha256 = ?
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
                        _utc_now(),
                    ),
                )
                row = (project_id, binding_json, nonce, commitment)
        result = {
            "project_id": str(row[0]),
            "binding_json": str(row[1]),
            "nonce": bytes(row[2]),
            "nonce_commitment": str(row[3]),
        }
        if (
            result["project_id"] != project_id
            or result["binding_json"] != binding_json
            or len(result["nonce"]) != 32
            or result["nonce_commitment"]
            != _nonce_commitment(result["nonce"], comparison_sha256)
        ):
            raise ValueError("instrument review session is invalid")
        return result

    def _session(self, comparison_sha256: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT project_id, binding_json, nonce, nonce_commitment
                FROM comparison_sessions WHERE comparison_sha256 = ?
                """,
                (comparison_sha256,),
            ).fetchone()
        if row is None:
            raise ValueError("instrument review was not prepared")
        result = {
            "project_id": str(row[0]),
            "binding_json": str(row[1]),
            "nonce": bytes(row[2]),
            "nonce_commitment": str(row[3]),
        }
        if (
            len(result["nonce"]) != 32
            or result["nonce_commitment"]
            != _nonce_commitment(result["nonce"], comparison_sha256)
        ):
            raise ValueError("instrument review session is invalid")
        return result

    def _append_review_idempotent(
        self,
        *,
        comparison_sha256: str,
        reviewer_session_id: str,
        expected_revision: int,
        review: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = _canonical_json(review)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT revision, review_json
                FROM review_events
                WHERE comparison_sha256 = ? AND reviewer_session_id = ?
                ORDER BY revision DESC LIMIT 1
                """,
                (comparison_sha256, reviewer_session_id),
            ).fetchone()
            current_revision = int(row[0]) if row is not None else 0
            if current_revision == expected_revision + 1 and row is not None:
                existing = _json_object(
                    str(row[1]), label="instrument review record"
                )
                if existing == review:
                    return existing
            if current_revision != expected_revision:
                raise WorkbenchInstrumentReviewRevisionConflictError(
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
        return _json_copy(review)

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
                ORDER BY revision DESC LIMIT 1
                """,
                (comparison_sha256, reviewer_session_id),
            ).fetchone()
        if row is None:
            return None
        value = _json_object(str(row[2]), label="instrument review record")
        if (
            value.get("review_id") != row[0]
            or value.get("revision") != row[1]
            or value.get("comparison_sha256") != comparison_sha256
            or value.get("reviewer_session_id") != reviewer_session_id
        ):
            raise ValueError("instrument review record is invalid")
        self._require_review_binding(value)
        return value

    def _review(self, review_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT comparison_sha256, reviewer_session_id, revision,
                       review_json
                FROM review_events WHERE review_id = ?
                """,
                (review_id,),
            ).fetchone()
        if row is None:
            raise ValueError("instrument review does not exist")
        value = _json_object(str(row[3]), label="instrument review record")
        if (
            value.get("review_id") != review_id
            or value.get("comparison_sha256") != row[0]
            or value.get("reviewer_session_id") != row[1]
            or value.get("revision") != row[2]
        ):
            raise ValueError("instrument review record is invalid")
        return value

    def _require_review_binding(self, review: Mapping[str, Any]) -> None:
        comparison_sha256 = _sha256_text(
            review.get("comparison_sha256"), label="comparison SHA-256"
        )
        session = self._session(comparison_sha256)
        binding = _session_binding(session)
        response = review.get("response")
        if not isinstance(response, Mapping):
            raise ValueError("instrument review response is invalid")
        normalized_response = {
            "heard": _heard(response.get("heard", {})),
            "choice": _choice(response.get("choice")),
            "problem_tags": _problem_tag_map(
                response.get("problem_tags", {})
            ),
            "notes": _notes_map(response.get("notes", {})),
        }
        revision = _positive_int(review.get("revision"), label="review revision")
        reviewer_session_id = _sha256_text(
            review.get("reviewer_session_id"),
            label="reviewer session identity",
        )
        expected_review_id = _document_hash(
            {
                "schema": INSTRUMENT_REVIEW_SCHEMA,
                "comparison_sha256": comparison_sha256,
                "reviewer_session_id": reviewer_session_id,
                "revision": revision,
                "response": normalized_response,
            }
        )
        unsigned = {
            key: value for key, value in review.items() if key != "review_sha256"
        }
        if (
            review.get("schema") != INSTRUMENT_REVIEW_SCHEMA
            or review.get("status") != "reviewed"
            or review.get("blind") is not True
            or review.get("policy") != INSTRUMENT_REVIEW_POLICY
            or review.get("review_id") != expected_review_id
            or review.get("evidence") != binding
            or response != normalized_response
            or _document_hash(binding) != comparison_sha256
            or review.get("nonce_commitment") != session["nonce_commitment"]
            or review.get("review_sha256") != _document_hash(unsigned)
            or review.get("effects") != REVIEW_EFFECTS
        ):
            raise ValueError("instrument review binding is invalid")
        _require_path_free(review, label="instrument review")

    def _save_or_load_resolution(
        self, result: Mapping[str, Any]
    ) -> dict[str, Any]:
        review_id = str(result["review_id"])
        payload = _canonical_json(result)
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
                        payload,
                    ),
                )
                return _json_copy(result)
        existing = _json_object(
            str(row[0]), label="instrument review resolution"
        )
        if existing != result:
            raise ValueError("instrument review resolution changed")
        return existing

    def _require_resolution_binding(self, result: Mapping[str, Any]) -> None:
        unsigned = {
            key: value for key, value in result.items() if key != "result_sha256"
        }
        review = self._review(str(result.get("review_id", "")))
        self._require_review_binding(review)
        session = self._session(str(result.get("comparison_sha256", "")))
        assignment = _blind_mapping(
            bytes(session["nonce"]), str(result["comparison_sha256"])
        )
        manifest = self._load_audio_manifest(
            str(result["comparison_sha256"]),
            nonce=bytes(session["nonce"]),
            nonce_commitment=str(session["nonce_commitment"]),
        )
        identities = manifest["private_identities"]
        expected_revealed = {
            slot: {
                "identity": identity,
                **identities[identity],
            }
            for slot, identity in assignment.items()
        }
        revealed = result.get("assignment")
        if not isinstance(revealed, Mapping):
            raise ValueError("instrument resolution assignment is invalid")
        compact_assignment = {
            slot: row.get("identity") if isinstance(row, Mapping) else None
            for slot, row in revealed.items()
        }
        response = review["response"]
        choice = str(response["choice"])
        expected_choice = assignment[choice] if choice in assignment else choice
        expected_tags = {
            assignment[CANDIDATE_A]: list(
                response["problem_tags"][CANDIDATE_A]
            ),
            assignment[CANDIDATE_B]: list(
                response["problem_tags"][CANDIDATE_B]
            ),
        }
        expected_notes = {
            assignment[CANDIDATE_A]: str(response["notes"][CANDIDATE_A]),
            assignment[CANDIDATE_B]: str(response["notes"][CANDIDATE_B]),
        }
        if (
            result.get("schema") != INSTRUMENT_REVIEW_RESULT_SCHEMA
            or result.get("status") != "complete"
            or result.get("blind_review") is not True
            or result.get("policy") != INSTRUMENT_REVIEW_POLICY
            or result.get("review_sha256") != review["review_sha256"]
            or result.get("nonce_commitment") != session["nonce_commitment"]
            or result.get("assignment_nonce") != bytes(session["nonce"]).hex()
            or compact_assignment != assignment
            or revealed != expected_revealed
            or result.get("resolved_choice") != expected_choice
            or result.get("problem_tags")
            != {
                CONTROL: expected_tags[CONTROL],
                CHALLENGER: expected_tags[CHALLENGER],
            }
            or result.get("notes")
            != {
                CONTROL: expected_notes[CONTROL],
                CHALLENGER: expected_notes[CHALLENGER],
            }
            or result.get("promotion_allowed") is not False
            or result.get("default_changed") is not False
            or result.get("effects") != RESOLUTION_EFFECTS
            or result.get("result_sha256") != _document_hash(unsigned)
        ):
            raise ValueError("instrument review resolution binding is invalid")
        _require_path_free(result, label="instrument review resolution")


def _verified_context_evidence(
    context: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(context, Mapping):
        raise ValueError("instrument review context is required")
    if context.get("schema") != INSTRUMENT_REVIEW_CONTEXT_SCHEMA:
        raise ValueError("instrument review context schema is invalid")
    project_id = _bounded_text(
        context.get("project_id"), label="project_id", maximum=128
    )
    selection_sha = _sha256_text(
        context.get("selection_manifest_sha256"),
        label="selection manifest SHA-256",
    )
    bpm = _finite_number(context.get("bpm"), label="BPM")
    if not 1.0 <= bpm <= 1_000.0:
        raise ValueError("instrument review BPM must be between 1 and 1000")
    track = context.get("track")
    if not isinstance(track, Mapping) or track.get("role") != "bass":
        raise ValueError("instrument review v1 accepts only selected bass MIDI")
    programs = context.get("programs")
    if programs != _EXPECTED_PROGRAMS:
        raise ValueError(
            "instrument review programs must be Synth Bass 1 and Synth Bass 2"
        )
    effects = context.get("effects")
    if not isinstance(effects, Mapping) or any(
        effects.get(key) is not False for key in _NO_PRODUCT_EFFECTS
    ):
        raise ValueError("instrument review context effects are invalid")

    midi_record = _checked_input_record(
        track.get("midi"),
        label="selected bass MIDI",
        maximum_bytes=MAXIMUM_MIDI_BYTES,
    )
    source_record = _checked_input_record(
        context.get("source"),
        label="bass source stem",
        maximum_bytes=MAXIMUM_SOURCE_AUDIO_BYTES,
    )
    soundfont_record = _checked_input_record(
        context.get("soundfont"),
        label="SoundFont",
        maximum_bytes=MAXIMUM_SOUNDFONT_BYTES,
    )
    source_info = _audio_info(
        Path(source_record["path"]), label="bass source stem"
    )
    renderer_path = Path(find_fluidsynth()).expanduser().resolve()
    if (
        not renderer_path.is_file()
        or renderer_path.is_symlink()
        or renderer_path.stat().st_size > MAXIMUM_RENDERER_BYTES
    ):
        raise ValueError("FluidSynth renderer exceeds the safe file-size limit")
    renderer_record = _checked_input_record(
        {
            "path": str(renderer_path),
            "name": renderer_path.name,
            "bytes": renderer_path.stat().st_size,
            "sha256": _file_sha256(renderer_path),
        },
        label="FluidSynth renderer",
        maximum_bytes=MAXIMUM_RENDERER_BYTES,
    )
    aggregate_input_bytes = sum(
        int(record["bytes"])
        for record in (
            midi_record,
            source_record,
            soundfont_record,
            renderer_record,
        )
    )
    if aggregate_input_bytes > MAXIMUM_AGGREGATE_INPUT_BYTES:
        raise ValueError(
            "instrument review inputs exceed the safe aggregate size limit"
        )
    note_evidence = _selected_midi_evidence(Path(midi_record["path"]))
    public = {
        "project_id": project_id,
        "role": "bass",
        "selection_manifest_sha256": selection_sha,
        "bpm": bpm,
        "track": {
            "track_id": _bounded_text(
                track.get("track_id"), label="track_id", maximum=128
            ),
            "stem_id": _bounded_text(
                track.get("stem_id"), label="stem_id", maximum=128
            ),
            "candidate_id": _bounded_text(
                track.get("candidate_id"), label="candidate_id", maximum=128
            ),
            "decision": _bounded_text(
                track.get("decision"), label="decision", maximum=32
            ),
            "selection_index": _positive_int(
                track.get("selection_index"), label="selection index"
            ),
        },
        "selected_midi": {
            "sha256": midi_record["sha256"],
            "bytes": midi_record["bytes"],
            **note_evidence,
        },
        "source_reference": {
            "sha256": source_record["sha256"],
            "bytes": source_record["bytes"],
            "label": "Original bass stem reference",
            "level_policy": INSTRUMENT_REVIEW_LEVEL_POLICY,
        },
        "soundfont": {
            "sha256": soundfont_record["sha256"],
            "bytes": soundfont_record["bytes"],
        },
        "renderer": {
            "sha256": renderer_record["sha256"],
            "bytes": renderer_record["bytes"],
            "policy": INSTRUMENT_REVIEW_RENDER_POLICY,
            "gain": 0.7,
            "reverb": False,
            "chorus": False,
        },
        "input_limits": {
            "midi_bytes": MAXIMUM_MIDI_BYTES,
            "source_audio_bytes": MAXIMUM_SOURCE_AUDIO_BYTES,
            "soundfont_bytes": MAXIMUM_SOUNDFONT_BYTES,
            "renderer_bytes": MAXIMUM_RENDERER_BYTES,
            "aggregate_bytes": MAXIMUM_AGGREGATE_INPUT_BYTES,
            "midi_note_ons": MAXIMUM_MIDI_NOTE_ONS,
            "render_horizon_seconds": MAXIMUM_RENDER_HORIZON_SECONDS,
            "declared_aggregate_bytes": aggregate_input_bytes,
            "source_snapshot_policy": SOURCE_SNAPSHOT_POLICY,
            "full_source_snapshot_created": False,
        },
        "candidate_identity_set_commitment": _document_hash(
            {"identities": _EXPECTED_PROGRAMS}
        ),
        "geometry": source_info,
    }
    _require_path_free(public, label="instrument context evidence")
    return {
        "public": public,
        "private": {
            "context": context,
            "midi_path": midi_record["path"],
            "midi_record": midi_record,
            "source_path": source_record["path"],
            "source_record": source_record,
            "soundfont_path": soundfont_record["path"],
            "soundfont_record": soundfont_record,
            "renderer_path": renderer_record["path"],
            "renderer_record": renderer_record,
            "programs": _EXPECTED_PROGRAMS,
        },
    }


def _comparison_document(
    public: Mapping[str, Any], window: Mapping[str, Any]
) -> dict[str, Any]:
    value = {
        "schema": INSTRUMENT_REVIEW_COMPARISON_SCHEMA,
        "status": "prepared",
        "blind": True,
        "policy": INSTRUMENT_REVIEW_POLICY,
        **_json_copy(public),
        "window": _json_copy(window),
        "candidate_count": 2,
        "candidate_identities_hidden": True,
        "source_reference_is_candidate": False,
        "level_match": {
            "policy": INSTRUMENT_REVIEW_LEVEL_POLICY,
            "candidate_only": False,
            "source_reference_matched": True,
            "maximum_attenuation_db": MAXIMUM_ATTENUATION_DB,
            "maximum_final_mismatch_db": MAXIMUM_FINAL_RMS_MISMATCH_DB,
            "sample_peak_ceiling_dbfs": SAMPLE_PEAK_CEILING_DBFS,
            "peak_guard": "common-attenuation-only-no-limiter-v1",
        },
        "effects": dict(PREPARE_EFFECTS),
    }
    _require_path_free(value, label="instrument comparison")
    return value


def _prepared_document(
    *,
    comparison: Mapping[str, Any],
    comparison_sha256: str,
    nonce_commitment: str,
    manifest: Mapping[str, Any],
    current_review: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source = manifest["source_reference"]
    candidates = manifest["candidates"]
    document = {
        "schema": INSTRUMENT_REVIEW_COMPARISON_SCHEMA,
        "status": "prepared",
        "blind": True,
        "comparison_sha256": comparison_sha256,
        "nonce_commitment": nonce_commitment,
        "comparison": _json_copy(comparison),
        "audio": {
            "schema": INSTRUMENT_REVIEW_AUDIO_SCHEMA,
            "source_reference": _public_media_row(source),
            CANDIDATE_A: _public_media_row(candidates[CANDIDATE_A]),
            CANDIDATE_B: _public_media_row(candidates[CANDIDATE_B]),
            "level_match": _public_level_match(manifest),
            "candidate_identities_hidden": True,
            "source_reference_level_disclosure": (
                "The source stem and candidates share the quietest input's "
                "fixed-window RMS. Matching attenuates only and never boosts."
            ),
        },
        "current_review": (
            None if current_review is None else _json_copy(current_review)
        ),
        "allowed": {
            "choices": sorted(INSTRUMENT_REVIEW_CHOICES),
            "problem_tags": sorted(INSTRUMENT_REVIEW_PROBLEM_TAGS),
            "maximum_problem_tags_per_candidate": (
                MAXIMUM_PROBLEM_TAGS_PER_CANDIDATE
            ),
            "maximum_notes_characters": MAXIMUM_NOTES_CHARACTERS,
        },
        "effects": dict(PREPARE_EFFECTS),
    }
    _require_path_free(document, label="prepared instrument review")
    return document


def _public_media_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _json_copy(value) if isinstance(value, Mapping) else value
        for key, value in row.items()
        if key != "identity"
    }


def _public_level_match(manifest: Mapping[str, Any]) -> dict[str, Any]:
    level = manifest["level_match"]
    private_inputs = level["inputs"]
    candidates = manifest["candidates"]
    result = {
        key: _json_copy(value) if isinstance(value, Mapping) else value
        for key, value in level.items()
        if key != "inputs"
    }
    result["inputs"] = {
        SOURCE_REFERENCE: _json_copy(private_inputs[SOURCE_REFERENCE]),
        CANDIDATE_A: _json_copy(
            private_inputs[candidates[CANDIDATE_A]["identity"]]
        ),
        CANDIDATE_B: _json_copy(
            private_inputs[candidates[CANDIDATE_B]["identity"]]
        ),
    }
    return result


def _midi_program_state_evidence(
    layout: Any,
    *,
    expected_program: int | None,
) -> dict[str, Any]:
    playable_notes = [
        (track, event)
        for track in layout.tracks
        for event in track.events
        if event.category == "channel"
        and event.event_type == 0x90
        and len(event.data) == 2
        and event.data[1] > 0
        and event.channel is not None
    ]
    if not playable_notes:
        raise ValueError("selected bass MIDI contains no playable note events")
    note_channels = {int(event.channel) for _track, event in playable_notes}
    if 9 in note_channels:
        raise ValueError("selected bass MIDI must not use the drum channel")

    note_tracks: dict[int, set[int]] = {channel: set() for channel in note_channels}
    relevant_tracks: dict[int, set[int]] = {
        channel: set() for channel in note_channels
    }
    bank_events: list[Any] = []
    program_events: list[Any] = []
    for track in layout.tracks:
        for event in track.events:
            channel = event.channel
            if event.category != "channel" or channel not in note_channels:
                continue
            if (
                event.event_type == 0x90
                and len(event.data) == 2
                and event.data[1] > 0
            ):
                note_tracks[int(channel)].add(int(track.index))
                relevant_tracks[int(channel)].add(int(track.index))
            elif event.event_type == 0xC0:
                program_events.append(event)
                relevant_tracks[int(channel)].add(int(track.index))
            elif (
                event.event_type == 0xB0
                and len(event.data) == 2
                and event.data[0] in {0, 32}
            ):
                bank_events.append(event)
                relevant_tracks[int(channel)].add(int(track.index))
                if event.data[1] != 0:
                    raise ValueError(
                        "selected bass MIDI uses a nonzero CC0/CC32 bank; "
                        "General MIDI program identity would be ambiguous"
                    )

    channel_tracks: dict[int, int] = {}
    for channel in sorted(note_channels):
        tracks = note_tracks[channel]
        relevant = relevant_tracks[channel]
        if len(tracks) != 1 or relevant != tracks:
            raise ValueError(
                "selected bass MIDI has ambiguous cross-track bank, program, "
                "or Note On ordering"
            )
        channel_tracks[channel] = next(iter(tracks))

    effective_program: dict[int, int | None] = {
        channel: None for channel in note_channels
    }
    for track in layout.tracks:
        relevant_channels = {
            channel
            for channel, track_index in channel_tracks.items()
            if track_index == track.index
        }
        if not relevant_channels:
            continue
        # ``track.events`` is raw SMF order, including events that share a
        # tick. A Note On before its Program Change therefore fails closed.
        for event in track.events:
            channel = event.channel
            if event.category != "channel" or channel not in relevant_channels:
                continue
            if event.event_type == 0xC0:
                effective_program[int(channel)] = int(event.data[0])
            elif (
                event.event_type == 0x90
                and len(event.data) == 2
                and event.data[1] > 0
            ):
                current = effective_program[int(channel)]
                if current is None:
                    raise ValueError(
                        "selected bass MIDI needs an effective Program Change "
                        "before every playable Note On"
                    )
                if expected_program is not None and current != expected_program:
                    raise ValueError(
                        "instrument proxy does not establish the target Program "
                        "Change before every playable Note On"
                    )
    return {
        "playable_note_on_count": len(playable_notes),
        "note_channels": sorted(note_channels),
        "note_channel_tracks": {
            str(channel): channel_tracks[channel] for channel in sorted(note_channels)
        },
        "program_change_event_count": len(program_events),
        "bank_select_event_count": len(bank_events),
        "bank_select_all_zero": True,
        "cross_track_order_unambiguous": True,
        "same_tick_raw_event_order_checked": True,
        "effective_program_before_every_note_on": True,
        "effective_target_program_before_every_note_on": (
            expected_program is not None
        ),
    }


def _write_program_proxy(
    source: Path,
    destination: Path,
    *,
    program: int,
) -> dict[str, Any]:
    if source.stat().st_size > MAXIMUM_MIDI_BYTES:
        raise ValueError("selected bass MIDI exceeds the safe file-size limit")
    data = source.read_bytes()
    layout = _parse_midi(data)
    state = _midi_program_state_evidence(layout, expected_program=None)
    note_channels = set(state["note_channels"])
    program_events = [
        event
        for track in layout.tracks
        for event in track.events
        if event.category == "channel"
        and event.event_type == 0xC0
        and event.channel in note_channels
    ]
    covered_channels = {int(event.channel) for event in program_events}
    if covered_channels != note_channels:
        raise ValueError(
            "each selected bass MIDI note channel needs an explicit Program Change"
        )
    output = bytearray(data)
    changed_offsets: list[int] = []
    for event in program_events:
        offset = int(event.data_offsets[0])
        if output[offset] != program:
            changed_offsets.append(offset)
            output[offset] = program
    destination.write_bytes(bytes(output))
    destination.chmod(0o600)
    evidence = _program_proxy_evidence(
        source, destination, expected_program=program
    )
    if evidence["changed_byte_count"] != len(changed_offsets):
        raise RuntimeError("instrument proxy byte-diff evidence changed")
    return evidence


def _program_proxy_evidence(
    source: Path,
    proxy: Path,
    *,
    expected_program: int,
) -> dict[str, Any]:
    if (
        source.stat().st_size > MAXIMUM_MIDI_BYTES
        or proxy.stat().st_size > MAXIMUM_MIDI_BYTES
    ):
        raise ValueError("instrument proxy MIDI exceeds the safe file-size limit")
    source_data = source.read_bytes()
    proxy_data = proxy.read_bytes()
    if len(source_data) != len(proxy_data):
        raise ValueError("instrument proxy changed the selected MIDI byte length")
    source_layout = _parse_midi(source_data)
    proxy_layout = _parse_midi(proxy_data)
    source_state = _midi_program_state_evidence(
        source_layout,
        expected_program=None,
    )
    proxy_state = _midi_program_state_evidence(
        proxy_layout,
        expected_program=expected_program,
    )
    if any(
        source_state[key] != proxy_state[key]
        for key in (
            "playable_note_on_count",
            "note_channels",
            "note_channel_tracks",
            "program_change_event_count",
            "bank_select_event_count",
            "bank_select_all_zero",
            "cross_track_order_unambiguous",
            "effective_program_before_every_note_on",
        )
    ):
        raise ValueError("instrument proxy changed MIDI program-state topology")
    source_signature = _note_event_signature(source_layout)
    proxy_signature = _note_event_signature(proxy_layout)
    if source_signature != proxy_signature:
        raise ValueError("instrument proxy changed fixed MIDI note events")
    source_events = [
        event
        for track in source_layout.tracks
        for event in track.events
        if event.category == "channel" and event.event_type == 0xC0
    ]
    proxy_events = [
        event
        for track in proxy_layout.tracks
        for event in track.events
        if event.category == "channel" and event.event_type == 0xC0
    ]
    if len(source_events) != len(proxy_events):
        raise ValueError("instrument proxy changed Program Change event count")
    permitted = {int(event.data_offsets[0]) for event in source_events}
    differences = [
        index
        for index, (before, after) in enumerate(zip(source_data, proxy_data))
        if before != after
    ]
    if any(offset not in permitted for offset in differences):
        raise ValueError(
            "instrument proxy changed bytes outside Program Change data"
        )
    signature_sha = _document_hash({"note_events": source_signature})
    return {
        "source_midi_sha256": _file_sha256(source),
        "proxy_midi_sha256": _file_sha256(proxy),
        "note_event_count": len(source_signature),
        "note_signature_sha256": signature_sha,
        "note_signatures_match": True,
        "byte_length_unchanged": True,
        "only_program_change_data_changed": True,
        "changed_byte_count": len(differences),
        "program_change_event_count": proxy_state["program_change_event_count"],
        "bank_select_event_count": proxy_state["bank_select_event_count"],
        "bank_select_all_zero": True,
        "cross_track_order_unambiguous": True,
        "same_tick_raw_event_order_checked": True,
        "effective_program_before_every_note_on": True,
        "effective_target_program_before_every_note_on": True,
        "expected_program": expected_program,
    }


def _selected_midi_evidence(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAXIMUM_MIDI_BYTES:
        raise ValueError("selected bass MIDI exceeds the safe file-size limit")
    layout = _parse_midi(path.read_bytes())
    state = _midi_program_state_evidence(layout, expected_program=None)
    clips = read_midi_clips(path, max_notes=MAXIMUM_MIDI_NOTE_ONS)
    if not clips:
        raise ValueError("selected bass MIDI contains no note-bearing clips")
    maximum_tick = max(
        (
            int(event.tick)
            for track in layout.tracks
            for event in track.events
        ),
        default=0,
    )
    render_horizon_seconds = float(
        clips[0].tempo_map.musical_seconds_at(
            maximum_tick / int(layout.ticks_per_beat)
        )
    )
    if (
        not math.isfinite(render_horizon_seconds)
        or render_horizon_seconds < 0.0
        or render_horizon_seconds > MAXIMUM_RENDER_HORIZON_SECONDS
    ):
        raise ValueError(
            "selected bass MIDI exceeds the 20-minute render horizon"
        )
    signature = _note_event_signature(layout)
    if not signature:
        raise ValueError("selected bass MIDI contains no playable notes")
    if any(row[3] == 9 for row in signature):
        raise ValueError("selected bass MIDI contains drum-channel notes")
    return {
        "note_event_count": len(signature),
        "note_signature_sha256": _document_hash({"note_events": signature}),
        "program_state": state,
        "maximum_event_tick": maximum_tick,
        "render_horizon_seconds": render_horizon_seconds,
        "maximum_render_horizon_seconds": MAXIMUM_RENDER_HORIZON_SECONDS,
        "maximum_note_ons": MAXIMUM_MIDI_NOTE_ONS,
    }


def _note_event_signature(layout: Any) -> list[tuple[int, int, int, int, list[int]]]:
    return [
        (
            int(track.index),
            int(event.tick),
            int(event.event_type),
            int(event.channel),
            [int(value) for value in event.data],
        )
        for track in layout.tracks
        for event in track.events
        if event.category == "channel"
        and event.event_type in {0x80, 0x90}
        and event.channel is not None
    ]


def _validate_level_manifest(
    value: Any,
    *,
    source: Mapping[str, Any],
    candidates: Mapping[str, Any],
    final_mismatch: float,
) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("instrument review level evidence is invalid")
    inputs = value.get("inputs")
    if (
        value.get("policy") != INSTRUMENT_REVIEW_LEVEL_POLICY
        or value.get("candidate_only") is not False
        or value.get("source_reference_matched") is not True
        or value.get("maximum_attenuation_db") != MAXIMUM_ATTENUATION_DB
        or value.get("sample_peak_ceiling_dbfs") != SAMPLE_PEAK_CEILING_DBFS
        or value.get("limiting_applied") is not False
        or value.get("compression_applied") is not False
        or not isinstance(inputs, Mapping)
        or set(inputs) != {SOURCE_REFERENCE, CONTROL, CHALLENGER}
    ):
        raise ValueError("instrument review level policy changed")
    common_gain = _finite_number(
        value.get("common_peak_guard_gain_db"),
        label="common peak guard gain",
    )
    if not -60.0 <= common_gain <= 0.0:
        raise ValueError("instrument review common peak guard is invalid")
    for identity in (SOURCE_REFERENCE, CONTROL, CHALLENGER):
        row = inputs[identity]
        if not isinstance(row, Mapping):
            raise ValueError("instrument review input level evidence is invalid")
        rms_gain = _finite_number(
            row.get("rms_match_gain_db"),
            label="RMS-match gain",
        )
        row_common = _finite_number(
            row.get("common_peak_guard_gain_db"),
            label="input peak-guard gain",
        )
        applied = _finite_number(
            row.get("applied_gain_db"),
            label="input applied gain",
        )
        if (
            not -MAXIMUM_ATTENUATION_DB <= rms_gain <= 0.0
            or row_common != common_gain
            or abs(applied - (rms_gain + common_gain)) > 0.000002
            or applied > 0.0
            or row.get("boost_applied") is not False
        ):
            raise ValueError("instrument review attenuation evidence is invalid")
    if source.get("applied_gain_db") != inputs[SOURCE_REFERENCE][
        "applied_gain_db"
    ]:
        raise ValueError("source reference gain evidence changed")
    for slot in (CANDIDATE_A, CANDIDATE_B):
        row = candidates[slot]
        identity = row["identity"]
        if row.get("applied_gain_db") != inputs[identity]["applied_gain_db"]:
            raise ValueError("candidate gain evidence changed")
    final = value.get("final_pcm16")
    if (
        not isinstance(final, Mapping)
        or final.get("within_tolerance") is not True
        or abs(float(final.get("mismatch_db", -1.0)) - final_mismatch) > 0.000002
    ):
        raise ValueError("instrument review final level evidence changed")


def _common_level_match(
    inputs_audio: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    import numpy as np

    measured: dict[str, float] = {}
    identities = (SOURCE_REFERENCE, CONTROL, CHALLENGER)
    for identity in identities:
        audio = np.asarray(inputs_audio[identity], dtype="float64")
        value = float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))
        level = _dbfs(value)
        if level < MINIMUM_RMS_DBFS:
            raise ValueError(f"{identity} is too quiet for a fair review")
        measured[identity] = value
    target = min(measured.values())
    matched: dict[str, Any] = {}
    inputs: dict[str, Any] = {}
    for identity in identities:
        gain = target / measured[identity]
        gain_db = 20.0 * math.log10(gain)
        if gain_db < -MAXIMUM_ATTENUATION_DB:
            raise ValueError(
                "review inputs differ by more than the allowed "
                f"{MAXIMUM_ATTENUATION_DB:.1f} dB"
            )
        matched[identity] = (
            np.asarray(inputs_audio[identity], dtype="float32") * gain
        ).astype("float32")
        inputs[identity] = {
            "original_rms_dbfs": round(_dbfs(measured[identity]), 6),
            "rms_match_gain_db": round(gain_db, 6),
            "boost_applied": False,
        }
    peak_ceiling = 10.0 ** (SAMPLE_PEAK_CEILING_DBFS / 20.0)
    matched_peak = max(
        float(np.max(np.abs(audio))) if audio.size else 0.0
        for audio in matched.values()
    )
    common_peak_gain = (
        min(1.0, peak_ceiling / matched_peak)
        if matched_peak > 0.0
        else 1.0
    )
    common_peak_gain_db = 20.0 * math.log10(common_peak_gain)
    for identity in identities:
        matched[identity] = (
            np.asarray(matched[identity], dtype="float32") * common_peak_gain
        ).astype("float32")
        inputs[identity]["common_peak_guard_gain_db"] = round(
            common_peak_gain_db, 6
        )
        inputs[identity]["applied_gain_db"] = round(
            float(inputs[identity]["rms_match_gain_db"])
            + common_peak_gain_db,
            6,
        )
    return matched, {
        "policy": INSTRUMENT_REVIEW_LEVEL_POLICY,
        "candidate_only": False,
        "source_reference_matched": True,
        "pre_peak_guard_target_rms_dbfs": round(_dbfs(target), 6),
        "target_rms_dbfs": round(_dbfs(target * common_peak_gain), 6),
        "inputs": inputs,
        "maximum_attenuation_db": MAXIMUM_ATTENUATION_DB,
        "sample_peak_ceiling_dbfs": SAMPLE_PEAK_CEILING_DBFS,
        "common_peak_guard_gain_db": round(common_peak_gain_db, 6),
        "peak_guard_applied": common_peak_gain < 1.0,
        "limiting_applied": False,
        "compression_applied": False,
    }


def _read_exact_audio_window(
    path: Path,
    *,
    start_frame: int,
    frame_count: int,
    expected_sample_rate: int,
    expected_channels: int,
    pad: bool,
    label: str,
):
    import numpy as np
    import soundfile

    try:
        with soundfile.SoundFile(path) as source:
            if int(source.samplerate) != expected_sample_rate:
                raise ValueError(f"{label} sample rate changed")
            source.seek(min(start_frame, len(source)))
            audio = source.read(
                frames=frame_count,
                dtype="float32",
                always_2d=True,
            )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if audio.shape[1] != expected_channels:
        if expected_channels == 1:
            audio = np.mean(audio, axis=1, keepdims=True)
        elif audio.shape[1] == 1:
            audio = np.repeat(audio, expected_channels, axis=1)
        else:
            mono = np.mean(audio, axis=1, keepdims=True)
            audio = np.repeat(mono, expected_channels, axis=1)
    if audio.shape[0] != frame_count:
        if not pad:
            raise ValueError(f"{label} no longer covers the exact review window")
        output = np.zeros((frame_count, expected_channels), dtype="float32")
        output[: audio.shape[0], :] = audio
        audio = output
    return np.asarray(audio, dtype="float32")


def _write_pcm16(path: Path, audio: Any, sample_rate: int) -> None:
    import soundfile

    soundfile.write(path, audio, sample_rate, subtype="PCM_16")
    path.chmod(0o600)


def _verified_output_audio(
    path: Path,
    *,
    expected_frames: int,
    expected_sample_rate: int,
    expected_channels: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    import numpy as np
    import soundfile

    record = _private_file_record(path, label="instrument review output")
    if record["bytes"] > MAXIMUM_AUDIO_BYTES:
        raise ValueError("instrument review output is too large")
    with soundfile.SoundFile(path) as source:
        if (
            int(source.frames) != expected_frames
            or int(source.samplerate) != expected_sample_rate
            or int(source.channels) != expected_channels
        ):
            raise ValueError("instrument review output geometry changed")
        audio = source.read(dtype="float32", always_2d=True)
    rms_value = float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    return record, {
        "sample_rate": expected_sample_rate,
        "channels": expected_channels,
        "frames": expected_frames,
        "rms_dbfs": round(_dbfs(rms_value), 6),
        "sample_peak_dbfs": round(_dbfs(peak), 6),
    }


def _audio_info(path: Path, *, label: str) -> dict[str, int]:
    import soundfile

    try:
        info = soundfile.info(path)
    except Exception as exc:
        raise ValueError(f"{label} is not readable audio") from exc
    if (
        not 8_000 <= int(info.samplerate) <= 192_000
        or not 1 <= int(info.channels) <= 8
        or int(info.frames) <= 0
    ):
        raise ValueError(f"{label} has unsupported audio geometry")
    return {
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "frames": int(info.frames),
    }


def _review_window(
    start_seconds: Any,
    end_seconds: Any,
    *,
    sample_rate: int,
    total_frames: int,
) -> dict[str, Any]:
    start = _finite_number(start_seconds, label="start seconds")
    end = _finite_number(end_seconds, label="end seconds")
    if start < 0.0 or end <= start:
        raise ValueError("instrument review window must have a positive start/end")
    start_frame = int(round(start * sample_rate))
    end_frame = int(round(end * sample_rate))
    frame_count = end_frame - start_frame
    minimum_frames = int(math.ceil(MINIMUM_WINDOW_SECONDS * sample_rate))
    maximum_frames = int(math.floor(MAXIMUM_WINDOW_SECONDS * sample_rate))
    if frame_count < minimum_frames or frame_count > maximum_frames:
        raise ValueError(
            "instrument review window must be between "
            f"{MINIMUM_WINDOW_SECONDS:.1f} and {MAXIMUM_WINDOW_SECONDS:.1f} seconds"
        )
    if start_frame < 0 or end_frame > total_frames:
        raise ValueError("instrument review window is outside the source stem")
    return {
        "requested_start_seconds": start,
        "requested_end_seconds": end,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "frame_count": frame_count,
        "start_seconds": start_frame / sample_rate,
        "end_seconds": end_frame / sample_rate,
        "duration_seconds": frame_count / sample_rate,
        "sample_rate": sample_rate,
    }


def _heard(value: Mapping[str, Any]) -> dict[str, bool]:
    expected = {SOURCE_REFERENCE, CANDIDATE_A, CANDIDATE_B}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("heard must name the source reference and both candidates")
    result = {key: value[key] is True for key in sorted(expected)}
    if not all(result.values()):
        raise ValueError("hear the source reference and both candidates first")
    return result


def _choice(value: Any) -> str:
    choice = str(value)
    if choice not in INSTRUMENT_REVIEW_CHOICES:
        raise ValueError("instrument review choice is invalid")
    return choice


def _problem_tag_map(
    value: Mapping[str, Sequence[str]],
) -> dict[str, list[str]]:
    expected = {CANDIDATE_A, CANDIDATE_B}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("problem_tags must name candidate_a and candidate_b")
    result: dict[str, list[str]] = {}
    for slot in (CANDIDATE_A, CANDIDATE_B):
        tags = value[slot]
        if isinstance(tags, (str, bytes)) or not isinstance(tags, Sequence):
            raise ValueError(f"{slot} problem tags must be a list")
        checked = [str(tag) for tag in tags]
        if (
            len(checked) > MAXIMUM_PROBLEM_TAGS_PER_CANDIDATE
            or len(set(checked)) != len(checked)
            or any(tag not in INSTRUMENT_REVIEW_PROBLEM_TAGS for tag in checked)
        ):
            raise ValueError(f"{slot} problem tags are invalid")
        result[slot] = sorted(checked)
    return result


def _notes_map(value: Mapping[str, Any]) -> dict[str, str]:
    expected = {CANDIDATE_A, CANDIDATE_B}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("notes must name candidate_a and candidate_b")
    result: dict[str, str] = {}
    for slot in (CANDIDATE_A, CANDIDATE_B):
        text = "" if value[slot] is None else str(value[slot]).strip()
        if len(text) > MAXIMUM_NOTES_CHARACTERS:
            raise ValueError(
                f"{slot} notes exceed {MAXIMUM_NOTES_CHARACTERS} characters"
            )
        result[slot] = text
    return result


def _media_slot(value: Any) -> str:
    slot = str(value)
    if slot not in {SOURCE_REFERENCE, CANDIDATE_A, CANDIDATE_B}:
        raise ValueError("unknown instrument review media slot")
    return slot


def _blind_mapping(nonce: bytes, comparison_sha256: str) -> dict[str, str]:
    bit = hashlib.sha256(
        b"sunofriend-instrument-review-assignment-v1\0"
        + nonce
        + bytes.fromhex(comparison_sha256)
    ).digest()[0] & 1
    order = (CONTROL, CHALLENGER) if bit == 0 else (CHALLENGER, CONTROL)
    return {CANDIDATE_A: order[0], CANDIDATE_B: order[1]}


def _nonce_commitment(nonce: bytes, comparison_sha256: str) -> str:
    return hashlib.sha256(
        b"sunofriend-instrument-review-nonce-v1\0"
        + bytes.fromhex(comparison_sha256)
        + nonce
    ).hexdigest()


def _session_binding(session: Mapping[str, Any]) -> dict[str, Any]:
    return _json_object(
        str(session["binding_json"]), label="instrument comparison binding"
    )


def _reviewer_session_id(value: Any) -> str:
    key = _bounded_text(
        value,
        label="reviewer_session_key",
        maximum=MAXIMUM_REVIEWER_KEY_CHARACTERS,
    )
    return hashlib.sha256(
        b"sunofriend-instrument-reviewer-v1\0" + key.encode("utf-8")
    ).hexdigest()


def _checked_input_record(
    value: Any,
    *,
    label: str,
    maximum_bytes: int,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} record is required")
    path = Path(str(value.get("path", ""))).expanduser().resolve()
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} does not exist as a regular file")
    expected_bytes = _nonnegative_int(value.get("bytes"), label=f"{label} bytes")
    expected_sha = _sha256_text(value.get("sha256"), label=f"{label} SHA-256")
    if (
        expected_bytes > maximum_bytes
        or path.stat().st_size > maximum_bytes
    ):
        raise ValueError(
            f"{label} exceeds the safe {maximum_bytes}-byte file-size limit"
        )
    if path.stat().st_size != expected_bytes or _file_sha256(path) != expected_sha:
        raise WorkbenchInstrumentReviewConflictError(f"{label} changed")
    return {
        "path": str(path),
        "name": path.name,
        "bytes": expected_bytes,
        "sha256": expected_sha,
    }


def _verified_snapshot(
    source: Path,
    expected: Mapping[str, Any],
    destination: Path,
    *,
    label: str,
) -> Path:
    digest = hashlib.sha256()
    written = 0
    try:
        with source.open("rb") as input_file, destination.open("xb") as output:
            for block in iter(lambda: input_file.read(1024 * 1024), b""):
                output.write(block)
                digest.update(block)
                written += len(block)
        destination.chmod(0o600)
        if (
            written != int(expected["bytes"])
            or digest.hexdigest() != expected["sha256"]
        ):
            raise WorkbenchInstrumentReviewConflictError(
                f"{label} changed while taking a private snapshot"
            )
        return destination
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def _verified_source_window_snapshot(
    source: Path,
    expected: Mapping[str, Any],
    destination: Path,
    *,
    start_frame: int,
    frame_count: int,
    sample_rate: int,
    channels: int,
    label: str,
) -> Path:
    """Decode only the requested source frames into a private float snapshot.

    A source stem can be hundreds of megabytes while a review is at most
    fifteen seconds.  libsndfile's integer frame seek gives the exact requested
    window; a second bounded full-file identity check closes source drift before
    the decoded frames are published.
    """

    import soundfile

    try:
        audio = _read_exact_audio_window(
            source,
            start_frame=start_frame,
            frame_count=frame_count,
            expected_sample_rate=sample_rate,
            expected_channels=channels,
            pad=False,
            label=label,
        )
        _checked_input_record(
            expected,
            label=label,
            maximum_bytes=MAXIMUM_SOURCE_AUDIO_BYTES,
        )
        soundfile.write(
            destination,
            audio,
            sample_rate,
            format="WAV",
            subtype="FLOAT",
        )
        destination.chmod(0o600)
        with soundfile.SoundFile(destination) as snapshot:
            if (
                int(snapshot.frames) != frame_count
                or int(snapshot.samplerate) != sample_rate
                or int(snapshot.channels) != channels
                or str(snapshot.subtype) != "FLOAT"
            ):
                raise RuntimeError("source review-window snapshot geometry changed")
        return destination
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def _private_file_record(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is not a private regular file")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError(f"{label} must be owner-only")
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
    }


def _without_path(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "path"}


def _write_private_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if len(payload.encode("utf-8")) > MAXIMUM_JSON_BYTES:
        raise ValueError("private instrument review JSON is too large")
    path.write_text(payload, encoding="utf-8")
    path.chmod(0o600)


def _read_private_json(path: Path) -> dict[str, Any]:
    record = _private_file_record(path, label="instrument review manifest")
    if record["bytes"] > MAXIMUM_JSON_BYTES:
        raise ValueError("instrument review manifest is too large")
    return _json_object(
        path.read_text(encoding="utf-8"),
        label="instrument review manifest",
    )


def _ensure_owner_only_directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("private instrument review directory cannot be a symlink")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _require_owner_only_directory(path: Path) -> None:
    if (
        not path.is_dir()
        or path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != 0o700
    ):
        raise ValueError("instrument review directory is not owner-only")


def _remove_private_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_path_free(value: Any, *, label: str) -> None:
    if not _path_free(value):
        raise ValueError(f"{label} must not contain filesystem paths")


def _path_free(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered == "path" or lowered.endswith("_path"):
                return False
            if not _path_free(item):
                return False
        return True
    if isinstance(value, (list, tuple)):
        return all(_path_free(item) for item in value)
    if isinstance(value, str):
        return not value.startswith(("/", "~/", "file://"))
    return True


def _absolute_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _document_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _json_object(payload: str, *, label: str) -> dict[str, Any]:
    if len(payload.encode("utf-8")) > MAXIMUM_JSON_BYTES:
        raise ValueError(f"{label} is too large")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _sha256_text(value: Any, *, label: str) -> str:
    text = str(value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{label} is invalid")
    return text


def _bounded_text(value: Any, *, label: str, maximum: int) -> str:
    text = str(value).strip()
    if not text or len(text) > maximum or "\x00" in text:
        raise ValueError(f"{label} is invalid")
    return text


def _finite_number(value: Any, *, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _nonnegative_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a non-negative integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a non-negative integer") from exc
    if number != value or number < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return number


def _positive_int(value: Any, *, label: str) -> int:
    number = _nonnegative_int(value, label=label)
    if number < 1:
        raise ValueError(f"{label} must be positive")
    return number


def _dbfs(value: float) -> float:
    if value <= 0.0:
        return -200.0
    return 20.0 * math.log10(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
