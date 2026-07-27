from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import stat
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import soundfile

import sunofriend.workbench_master_review as master_review_module
from sunofriend.listening_master_contract import (
    ENCODED_ARTIFACT_LABEL,
    FFMPEG_IDENTITY_POLICY,
    LISTENING_MASTER_EFFECTS,
    LISTENING_MASTER_LABEL,
    LISTENING_MASTER_POLICY,
    LISTENING_MASTER_SCHEMA,
    LISTENING_MASTER_SCOPE,
    LISTENING_MASTER_TARGETS,
    LISTENING_MASTER_TIMING_POLICY,
)
from sunofriend.workbench_balanced_contract import BALANCED_MIX_CONTRACT
from sunofriend.workbench_listening_master import (
    WORKBENCH_LISTENING_MASTER_SCHEMA,
)
from sunofriend.workbench_master_review import (
    BALANCED_CONTROL,
    CANDIDATE_A,
    CANDIDATE_B,
    LISTENING_MASTER,
    MASTER_REVIEW_COMPARISON_SCHEMA,
    MASTER_REVIEW_RESULT_SCHEMA,
    MASTER_REVIEW_SCHEMA,
    WorkbenchMasterReviewConflictError,
    WorkbenchMasterReviewRevisionConflictError,
    WorkbenchMasterReviewService,
)


class WorkbenchMasterReviewTests(unittest.TestCase):
    def test_prepare_is_blind_level_matched_private_and_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _evidence(root)
            state = root / "state"
            service = WorkbenchMasterReviewService(state)

            prepared = _prepare(service, evidence)

            self.assertEqual(prepared["schema"], MASTER_REVIEW_COMPARISON_SCHEMA)
            self.assertEqual(prepared["status"], "unreviewed")
            self.assertTrue(prepared["blind"])
            self.assertEqual(len(prepared["nonce_commitment"]), 64)
            self.assertNotIn("assignment", prepared)
            self.assertNotIn("assignment_nonce", prepared)
            self.assertEqual(set(prepared["candidates"]), {CANDIDATE_A, CANDIDATE_B})
            self.assertFalse(_contains_path(prepared))
            candidate_json = _canonical_json(prepared["candidates"])
            self.assertNotIn(BALANCED_CONTROL, candidate_json)
            self.assertNotIn(LISTENING_MASTER, candidate_json)
            for candidate in prepared["candidates"].values():
                self.assertEqual(
                    set(candidate),
                    {"audio", "sample_rate", "channels", "frames"},
                )
                self.assertNotIn("rms_dbfs", candidate)
                self.assertNotIn("sample_peak_dbfs", candidate)
                self.assertNotIn("applied_gain_db", candidate)
            self.assertEqual(
                set(prepared["artifact_hashes"]),
                {
                    "balanced_control_preview_sha256",
                    "listening_master_wav_sha256",
                    "listening_master_receipt_sha256",
                },
            )
            self.assertTrue(
                all(value is False for value in prepared["effects"].values())
            )

            records = {
                slot: service.media_record(prepared["comparison_sha256"], slot)
                for slot in (CANDIDATE_A, CANDIDATE_B)
            }
            rms_dbfs = {}
            for slot, record in records.items():
                path = Path(record["path"])
                audio, sample_rate = soundfile.read(
                    str(path), dtype="float64", always_2d=True
                )
                rms = float(np.sqrt(np.mean(np.square(audio))))
                rms_dbfs[slot] = 20.0 * math.log10(rms)
                self.assertEqual(sample_rate, 8_000)
                self.assertEqual(len(audio), 8_000)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertLessEqual(
                abs(rms_dbfs[CANDIDATE_A] - rms_dbfs[CANDIDATE_B]),
                0.05,
            )
            private_manifest = json.loads(
                (
                    state
                    / "audio"
                    / prepared["comparison_sha256"]
                    / "manifest.json"
                ).read_text(encoding="utf-8")
            )
            gains = sorted(
                candidate["applied_gain_db"]
                for candidate in private_manifest["candidates"].values()
            )
            self.assertAlmostEqual(gains[-1], 0.0, places=5)
            self.assertAlmostEqual(gains[0], -6.0206, places=3)

            current = service.current(
                project_id=evidence["project_id"],
                balanced=evidence["balanced"],
                listening_master=evidence["listening_master"],
                comparison_sha256=prepared["comparison_sha256"],
                reviewer_session_key="private-browser-session",
            )
            self.assertEqual(current["schema"], MASTER_REVIEW_COMPARISON_SCHEMA)
            self.assertEqual(current["status"], "unreviewed")
            self.assertEqual(current["current_revision"], 0)
            self.assertIsNone(current["review_state"]["response"])
            self.assertTrue(
                all(value is False for value in current["effects"].values())
            )

            again = _prepare(service, evidence)
            restarted = _prepare(
                WorkbenchMasterReviewService(state),
                evidence,
            )
            self.assertEqual(again, prepared)
            self.assertEqual(restarted, prepared)
            self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((state / "audio").stat().st_mode), 0o700)
            self.assertEqual(
                stat.S_IMODE((state / "reviews.sqlite3").stat().st_mode),
                0o600,
            )
            comparison_audio = state / "audio" / prepared["comparison_sha256"]
            self.assertEqual(stat.S_IMODE(comparison_audio.stat().st_mode), 0o700)
            self.assertEqual(_row_count(state, "review_events"), 0)
            self.assertEqual(_row_count(state, "review_resolutions"), 0)

    def test_sub_frame_equivalent_requests_reuse_exact_frame_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _evidence(root)
            state = root / "state"
            service = WorkbenchMasterReviewService(state)
            common = {
                "project_id": evidence["project_id"],
                "balanced": evidence["balanced"],
                "listening_master": evidence["listening_master"],
                "reviewer_session_key": "private-browser-session",
            }

            first = service.prepare(
                **common,
                start_seconds=0.25,
                end_seconds=1.25,
            )
            equivalent = service.prepare(
                **common,
                start_seconds=0.25000000001,
                end_seconds=1.25000000001,
            )

            self.assertEqual(first["window"], equivalent["window"])
            self.assertEqual(
                first["window"],
                {
                    "start_frame": 2_000,
                    "end_frame": 10_000,
                    "frame_count": 8_000,
                    "sample_rate": 8_000,
                    "start_seconds": 0.25,
                    "end_seconds": 1.25,
                    "duration_seconds": 1.0,
                    "recorded_zero": True,
                    "alignment_inferred": False,
                },
            )
            self.assertEqual(
                first["comparison_sha256"],
                equivalent["comparison_sha256"],
            )
            self.assertEqual(first["candidates"], equivalent["candidates"])
            cache_directories = [
                path
                for path in (state / "audio").iterdir()
                if path.is_dir() and not path.name.startswith(".")
            ]
            self.assertEqual(
                [path.name for path in cache_directories],
                [first["comparison_sha256"]],
            )

    def test_parallel_prepare_verifies_and_reuses_publication_winner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _evidence(root)
            state = root / "state"
            service = WorkbenchMasterReviewService(state)
            barrier = threading.Barrier(2)
            original_level_match = master_review_module._pairwise_level_match

            def synchronized_level_match(audio: dict[str, Any]) -> tuple[Any, Any]:
                barrier.wait(timeout=10)
                return original_level_match(audio)

            with (
                patch.object(
                    master_review_module,
                    "_pairwise_level_match",
                    side_effect=synchronized_level_match,
                ),
                ThreadPoolExecutor(max_workers=2) as executor,
            ):
                futures = [
                    executor.submit(_prepare, service, evidence)
                    for _ in range(2)
                ]
                prepared = [future.result(timeout=20) for future in futures]

            self.assertEqual(prepared[0], prepared[1])
            comparison_sha256 = prepared[0]["comparison_sha256"]
            self.assertEqual(
                [
                    path.name
                    for path in (state / "audio").iterdir()
                    if path.is_dir() and not path.name.startswith(".")
                ],
                [comparison_sha256],
            )
            self.assertEqual(
                [
                    path.name
                    for path in (state / "audio").iterdir()
                    if path.name.startswith(".")
                ],
                [],
            )
            self.assertEqual(
                service.current(
                    project_id=evidence["project_id"],
                    balanced=evidence["balanced"],
                    listening_master=evidence["listening_master"],
                    comparison_sha256=comparison_sha256,
                    reviewer_session_key="private-browser-session",
                ),
                prepared[0],
            )

    def test_complete_stays_blind_and_resolution_is_separate_path_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _evidence(root)
            state = root / "state"
            service = WorkbenchMasterReviewService(state)
            prepared = _prepare(
                service,
                evidence,
                reviewer_key="raw-private-reviewer-key",
            )

            review = _complete(
                service,
                evidence,
                prepared,
                reviewer_key="raw-private-reviewer-key",
                expected_revision=0,
                choice=CANDIDATE_A,
                problem_tags={
                    CANDIDATE_A: ["muddy"],
                    CANDIDATE_B: ["harsh", "thin"],
                },
                notes="A is clearer in the bass phrase.",
            )

            self.assertEqual(review["schema"], MASTER_REVIEW_SCHEMA)
            self.assertEqual(review["status"], "reviewed")
            self.assertTrue(review["blind"])
            self.assertEqual(review["revision"], 1)
            self.assertEqual(review["response"]["choice"], CANDIDATE_A)
            self.assertNotIn("assignment", review)
            self.assertNotIn("assignment_nonce", review)
            response_json = _canonical_json(review["response"])
            self.assertNotIn(BALANCED_CONTROL, response_json)
            self.assertNotIn(LISTENING_MASTER, response_json)
            self.assertTrue(review["effects"]["feedback_recorded"])
            self.assertTrue(review["effects"]["review_record_created"])
            self.assertFalse(review["effects"]["resolution_record_created"])
            self.assertTrue(
                all(
                    value is False
                    for key, value in review["effects"].items()
                    if key not in {"feedback_recorded", "review_record_created"}
                )
            )
            self.assertEqual(_row_count(state, "review_events"), 1)
            self.assertEqual(_row_count(state, "review_resolutions"), 0)
            self.assertEqual(service.review(review["review_id"]), review)
            self.assertIsNone(service.resolution(review["review_id"]))
            self.assertNotIn(
                b"raw-private-reviewer-key",
                (state / "reviews.sqlite3").read_bytes(),
            )

            current = service.current(
                project_id=evidence["project_id"],
                balanced=evidence["balanced"],
                listening_master=evidence["listening_master"],
                comparison_sha256=prepared["comparison_sha256"],
                reviewer_session_key="raw-private-reviewer-key",
            )
            self.assertEqual(current["status"], "reviewed")
            self.assertEqual(current["current_revision"], 1)
            self.assertEqual(current["review_state"]["review_id"], review["review_id"])
            self.assertEqual(current["review_state"]["response"], review["response"])
            self.assertNotIn("assignment", current)
            self.assertNotIn("assignment_nonce", current)
            self.assertEqual(_row_count(state, "review_resolutions"), 0)
            restarted = _prepare(
                WorkbenchMasterReviewService(state),
                evidence,
                reviewer_key="raw-private-reviewer-key",
            )
            self.assertEqual(restarted, current)

            result = service.resolve(
                project_id=evidence["project_id"],
                balanced=evidence["balanced"],
                listening_master=evidence["listening_master"],
                review_id=review["review_id"],
            )

            self.assertEqual(result["schema"], MASTER_REVIEW_RESULT_SCHEMA)
            self.assertEqual(result["status"], "complete")
            self.assertIn(
                result["resolved_choice"],
                {BALANCED_CONTROL, LISTENING_MASTER},
            )
            self.assertEqual(
                set(result["assignment"]),
                {CANDIDATE_A, CANDIDATE_B},
            )
            self.assertEqual(
                set(result["assignment"].values()),
                {BALANCED_CONTROL, LISTENING_MASTER},
            )
            self.assertEqual(
                result["assignment"][CANDIDATE_A],
                result["resolved_choice"],
            )
            self.assertEqual(
                hashlib.sha256(
                    bytes.fromhex(result["assignment_nonce"])
                    + bytes.fromhex(result["comparison_sha256"])
                ).hexdigest(),
                result["nonce_commitment"],
            )
            assignment_bit = hashlib.sha256(
                bytes.fromhex(result["assignment_nonce"])
                + bytes.fromhex(result["comparison_sha256"])
                + b"\0full-song-window"
            ).digest()[0]
            expected_a = LISTENING_MASTER if assignment_bit % 2 else BALANCED_CONTROL
            self.assertEqual(result["assignment"][CANDIDATE_A], expected_a)
            selected_identity = result["resolved_choice"]
            other_identity = (
                LISTENING_MASTER
                if selected_identity == BALANCED_CONTROL
                else BALANCED_CONTROL
            )
            self.assertEqual(result["problem_tags"][selected_identity], ["muddy"])
            self.assertEqual(result["problem_tags"][other_identity], ["harsh", "thin"])
            self.assertNotIn("notes", result)
            self.assertTrue(result["notes_recorded"])
            self.assertFalse(result["promotion_allowed"])
            self.assertFalse(result["default_changed"])
            self.assertFalse(_contains_path(result))
            self.assertTrue(result["effects"]["resolution_record_created"])
            self.assertFalse(result["effects"]["feedback_recorded"])
            self.assertTrue(
                all(
                    value is False
                    for key, value in result["effects"].items()
                    if key != "resolution_record_created"
                )
            )
            self.assertEqual(_row_count(state, "review_resolutions"), 1)
            self.assertEqual(service.resolution(review["review_id"]), result)
            self.assertEqual(
                service.resolve(
                    project_id=evidence["project_id"],
                    balanced=evidence["balanced"],
                    listening_master=evidence["listening_master"],
                    review_id=review["review_id"],
                ),
                result,
            )
            self.assertEqual(_row_count(state, "review_resolutions"), 1)

    def test_revision_cas_and_bounded_feedback_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _evidence(root)
            service = WorkbenchMasterReviewService(root / "state")
            prepared = _prepare(service, evidence, reviewer_key="reviewer")
            kwargs = {
                "service": service,
                "evidence": evidence,
                "prepared": prepared,
                "reviewer_key": "reviewer",
                "expected_revision": 0,
                "choice": CANDIDATE_A,
                "problem_tags": {
                    CANDIDATE_A: [],
                    CANDIDATE_B: [],
                },
            }

            with self.assertRaisesRegex(ValueError, "marked heard"):
                service.complete(
                    project_id=evidence["project_id"],
                    balanced=evidence["balanced"],
                    listening_master=evidence["listening_master"],
                    comparison_sha256=prepared["comparison_sha256"],
                    reviewer_session_key="reviewer",
                    expected_revision=0,
                    heard={CANDIDATE_A: True, CANDIDATE_B: False},
                    choice=CANDIDATE_A,
                    problem_tags={
                        CANDIDATE_A: [],
                        CANDIDATE_B: [],
                    },
                )
            with self.assertRaisesRegex(ValueError, "unsupported problem tags"):
                _complete(
                    **{
                        **kwargs,
                        "problem_tags": {
                            CANDIDATE_A: ["custom_unbounded_tag"],
                            CANDIDATE_B: [],
                        },
                    }
                )
            with self.assertRaisesRegex(ValueError, "duration must be"):
                service.prepare(
                    project_id=evidence["project_id"],
                    balanced=evidence["balanced"],
                    listening_master=evidence["listening_master"],
                    start_seconds=0.0,
                    end_seconds=0.25,
                    reviewer_session_key="reviewer",
                )
            self.assertEqual(_row_count(root / "state", "review_events"), 0)

            first = _complete(**kwargs)
            self.assertEqual(first["revision"], 1)
            with self.assertRaises(
                WorkbenchMasterReviewRevisionConflictError
            ) as conflict:
                _complete(**kwargs)
            self.assertEqual(conflict.exception.expected_revision, 0)
            self.assertEqual(conflict.exception.current_revision, 1)
            second = _complete(
                **{
                    **kwargs,
                    "expected_revision": 1,
                    "choice": CANDIDATE_B,
                }
            )
            self.assertEqual(second["revision"], 2)
            current = service.current(
                project_id=evidence["project_id"],
                balanced=evidence["balanced"],
                listening_master=evidence["listening_master"],
                comparison_sha256=prepared["comparison_sha256"],
                reviewer_session_key="reviewer",
            )
            self.assertEqual(current["status"], "reviewed")
            self.assertEqual(current["current_revision"], 2)
            self.assertEqual(current["review_state"]["review_id"], second["review_id"])
            self.assertEqual(current["review_state"]["response"], second["response"])
            self.assertEqual(_row_count(root / "state", "review_events"), 2)

    def test_artifact_and_private_manifest_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _evidence(root)
            state = root / "state"
            service = WorkbenchMasterReviewService(state)
            prepared = _prepare(service, evidence)

            manifest = state / "audio" / prepared["comparison_sha256"] / "manifest.json"
            tampered = json.loads(manifest.read_text(encoding="utf-8"))
            tampered["level_match"]["limiter_used"] = True
            manifest.write_text(
                json.dumps(tampered, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            manifest.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "manifest is invalid"):
                service.media_record(prepared["comparison_sha256"], CANDIDATE_A)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _evidence(root)
            service = WorkbenchMasterReviewService(root / "state")
            prepared = _prepare(service, evidence)
            master = Path(evidence["listening_master"]["master"]["path"])
            master.write_bytes(master.read_bytes() + b"tamper")
            master.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "changed"):
                _complete(
                    service,
                    evidence,
                    prepared,
                    reviewer_key="reviewer",
                    expected_revision=0,
                    choice=CANDIDATE_A,
                    problem_tags={
                        CANDIDATE_A: [],
                        CANDIDATE_B: [],
                    },
                )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _evidence(root)
            service = WorkbenchMasterReviewService(root / "state")
            prepared = _prepare(service, evidence)
            changed_master = dict(evidence["listening_master"])
            changed_master["balanced_preview_sha256"] = _digest("other-preview")
            with self.assertRaisesRegex(
                ValueError, "not bound to the balanced control"
            ):
                service.current(
                    project_id=evidence["project_id"],
                    balanced=evidence["balanced"],
                    listening_master=changed_master,
                    comparison_sha256=prepared["comparison_sha256"],
                    reviewer_session_key="reviewer",
                )

    def test_evidence_drift_and_excessive_level_delta_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _evidence(root)
            service = WorkbenchMasterReviewService(root / "state")
            prepared = _prepare(service, evidence)
            changed = dict(evidence)
            changed["project_id"] = "different-project"
            with self.assertRaisesRegex(ValueError, "project_id does not match"):
                _complete(
                    service,
                    changed,
                    prepared,
                    reviewer_key="reviewer",
                    expected_revision=0,
                    choice=CANDIDATE_A,
                    problem_tags={
                        CANDIDATE_A: [],
                        CANDIDATE_B: [],
                    },
                )
            replacement = _evidence(
                root / "replacement",
                control_amplitude=0.11,
                master_amplitude=0.22,
            )
            with self.assertRaises(WorkbenchMasterReviewConflictError):
                service.current(
                    project_id=replacement["project_id"],
                    balanced=replacement["balanced"],
                    listening_master=replacement["listening_master"],
                    comparison_sha256=prepared["comparison_sha256"],
                    reviewer_session_key="reviewer",
                )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _evidence(
                root,
                control_amplitude=0.2,
                master_amplitude=0.02,
            )
            service = WorkbenchMasterReviewService(root / "state")
            with self.assertRaisesRegex(ValueError, "more than 18"):
                _prepare(service, evidence)


def _prepare(
    service: WorkbenchMasterReviewService,
    evidence: dict[str, Any],
    *,
    reviewer_key: str = "private-browser-session",
) -> dict[str, Any]:
    return service.prepare(
        project_id=evidence["project_id"],
        balanced=evidence["balanced"],
        listening_master=evidence["listening_master"],
        start_seconds=0.25,
        end_seconds=1.25,
        reviewer_session_key=reviewer_key,
    )


def _complete(
    service: WorkbenchMasterReviewService,
    evidence: dict[str, Any],
    prepared: dict[str, Any],
    *,
    reviewer_key: str,
    expected_revision: int,
    choice: str,
    problem_tags: dict[str, list[str]],
    notes: str | None = None,
) -> dict[str, Any]:
    return service.complete(
        project_id=evidence["project_id"],
        balanced=evidence["balanced"],
        listening_master=evidence["listening_master"],
        comparison_sha256=prepared["comparison_sha256"],
        reviewer_session_key=reviewer_key,
        expected_revision=expected_revision,
        heard={CANDIDATE_A: True, CANDIDATE_B: True},
        choice=choice,
        problem_tags=problem_tags,
        notes=notes,
    )


def _evidence(
    root: Path,
    *,
    control_amplitude: float = 0.1,
    master_amplitude: float = 0.2,
) -> dict[str, Any]:
    sample_rate = 8_000
    frames = sample_rate * 2
    project_id = "private-test-project"
    selection_sha256 = _digest("selection")
    balanced_cache_key = _digest("balanced-cache")
    balanced_manifest_sha256 = _digest("balanced-manifest")
    balanced_directory = root / "balanced-arrangements" / balanced_cache_key
    balanced_directory.mkdir(parents=True)
    control_path = balanced_directory / "balanced-selected-midi-preview.wav"
    _write_pcm24(
        control_path,
        amplitude=control_amplitude,
        frames=frames,
        sample_rate=sample_rate,
        frequency=110.0,
    )
    control_file = _file_record(control_path)
    balanced_receipt = {
        "schema": BALANCED_MIX_CONTRACT.receipt_schema,
        "project_id": project_id,
        "selection_manifest_sha256": selection_sha256,
        "policy": BALANCED_MIX_CONTRACT.policy,
        "renderer": {
            "policy": "role-neutral-general-midi-v3",
            "backend": BALANCED_MIX_CONTRACT.renderer_backend,
            "soundfont_sha256": _digest("soundfont"),
            "soundfont_bytes": 123,
        },
        "preview": {
            "filename": control_path.name,
            "bytes": control_file["bytes"],
            "sha256": control_file["sha256"],
        },
        "mastered": False,
    }
    balanced_receipt["receipt_sha256"] = _document_hash(balanced_receipt)
    balanced_report_path = balanced_directory / "balanced-mix-receipt.json"
    _write_private_json(balanced_report_path, balanced_receipt)
    balanced_report = _file_record(balanced_report_path)
    balanced = {
        "schema": BALANCED_MIX_CONTRACT.arrangement_schema,
        "cache_key": balanced_cache_key,
        "manifest_sha256": balanced_manifest_sha256,
        "selection_manifest_sha256": selection_sha256,
        "policy": BALANCED_MIX_CONTRACT.policy,
        "mastered": False,
        "preview": control_file,
        "report": balanced_report,
        "receipt": balanced_receipt,
    }

    master_cache_key = _digest("master-cache")
    master_directory = root / "listening-masters" / master_cache_key
    master_directory.mkdir(parents=True)
    master_path = master_directory / "listening-master.wav"
    _write_pcm24(
        master_path,
        amplitude=master_amplitude,
        frames=frames,
        sample_rate=sample_rate,
        frequency=110.0,
    )
    master_file = _file_record(master_path)
    stats = {
        "input_i": -16.0,
        "input_tp": -1.0,
        "input_lra": 4.0,
        "input_thresh": -26.0,
        "output_i": -16.0,
        "output_tp": -1.0,
        "output_lra": 4.0,
        "output_thresh": -26.0,
        "normalization_type": "dynamic",
        "target_offset": 0.0,
    }
    source_audio = _audio_record(control_path)
    output_audio = {
        "name": master_path.name,
        **_audio_record(master_path),
    }
    master_receipt = {
        "schema": LISTENING_MASTER_SCHEMA,
        "status": "complete",
        "policy": LISTENING_MASTER_POLICY,
        "label": LISTENING_MASTER_LABEL,
        "mastered": True,
        "release_master": False,
        "mastering_scope": LISTENING_MASTER_SCOPE,
        "source": source_audio,
        "targets": dict(LISTENING_MASTER_TARGETS),
        "analysis_pass": dict(stats),
        "render_pass": dict(stats),
        "verification_pass": {
            **stats,
            "measured_artifact": ENCODED_ARTIFACT_LABEL,
        },
        "renderer": {
            "backend": "FFmpeg loudnorm",
            "executable_sha256": _digest("ffmpeg"),
            "version": "ffmpeg version test",
            "filter": "loudnorm",
            "policy": LISTENING_MASTER_POLICY,
            "identity_verification": FFMPEG_IDENTITY_POLICY,
        },
        "output": output_audio,
        "timing": {
            "policy": LISTENING_MASTER_TIMING_POLICY,
            "input_frames": frames,
            "output_frames": frames,
            "sample_rate": sample_rate,
            "frame_horizon_changed": False,
            "time_shift_applied": False,
            "time_stretch_applied": False,
        },
        "processing": {
            "integrated_loudness_normalisation": True,
            "true_peak_limiting": True,
            "normalization_type": "dynamic",
            "encoded_artifact_verified": True,
            "equalisation": False,
            "stereo_widening": False,
            "reverb": False,
            "chorus": False,
            "saturation": False,
        },
        "effects": dict(LISTENING_MASTER_EFFECTS),
    }
    master_receipt["receipt_sha256"] = _document_hash(master_receipt)
    master_receipt_path = master_directory / "listening-master-receipt.json"
    _write_private_json(master_receipt_path, master_receipt)
    master_receipt_file = _file_record(master_receipt_path)
    listening_master = {
        "schema": WORKBENCH_LISTENING_MASTER_SCHEMA,
        "cache_key": master_cache_key,
        "manifest_sha256": _digest("master-manifest"),
        "selection_manifest_sha256": selection_sha256,
        "balanced_arrangement_manifest_sha256": balanced_manifest_sha256,
        "balanced_arrangement_cache_key": balanced_cache_key,
        "balanced_preview_sha256": control_file["sha256"],
        "balanced_report_sha256": balanced_report["sha256"],
        "policy": LISTENING_MASTER_POLICY,
        "mastered": True,
        "release_master": False,
        "master": master_file,
        "receipt": master_receipt_file,
    }
    return {
        "project_id": project_id,
        "balanced": balanced,
        "listening_master": listening_master,
    }


def _write_pcm24(
    path: Path,
    *,
    amplitude: float,
    frames: int,
    sample_rate: int,
    frequency: float,
) -> None:
    timeline = np.arange(frames, dtype=np.float64) / sample_rate
    mono = amplitude * np.sin(2.0 * np.pi * frequency * timeline)
    stereo = np.column_stack((mono, mono * 0.97))
    soundfile.write(
        str(path),
        stereo,
        sample_rate,
        format="WAV",
        subtype="PCM_24",
    )
    path.chmod(0o600)


def _audio_record(path: Path) -> dict[str, Any]:
    info = soundfile.info(str(path))
    record = _file_record(path)
    return {
        "sha256": record["sha256"],
        "bytes": record["bytes"],
        "format": str(info.format),
        "subtype": str(info.subtype),
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "frames": int(info.frames),
        "duration_seconds": round(int(info.frames) / int(info.samplerate), 6),
    }


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _write_private_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _row_count(root: Path, table: str) -> int:
    with sqlite3.connect(str(root / "reviews.sqlite3")) as connection:
        row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    if row is None:
        raise AssertionError(f"missing table {table}")
    return int(row[0])


def _contains_path(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            "path" in str(key).lower() or _contains_path(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_path(item) for item in value)
    return isinstance(value, str) and value.startswith("/")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _document_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    unittest.main()
