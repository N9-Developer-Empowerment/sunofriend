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

import sunofriend.workbench_master_readiness as readiness_module
from sunofriend.workbench_master_readiness import (
    MASTER_READINESS_AUDIO_SCHEMA,
    MASTER_READINESS_COMPARISON_SCHEMA,
    MASTER_READINESS_POLICY,
    MASTER_READINESS_REVIEW_SCHEMA,
    PREPARE_EFFECTS,
    REVIEW_EFFECTS,
    WorkbenchMasterReadinessConflictError,
    WorkbenchMasterReadinessGateError,
    WorkbenchMasterReadinessService,
)
from sunofriend.workbench_master_review import (
    BALANCED_CONTROL,
    CANDIDATE_A,
    CANDIDATE_B,
    LISTENING_MASTER,
    WorkbenchMasterReviewService,
)
from tests.test_workbench_master_review import (
    _complete as _complete_quality,
)
from tests.test_workbench_master_review import (
    _contains_path,
    _evidence,
    _prepare as _prepare_quality,
)


class WorkbenchMasterReadinessTests(unittest.TestCase):
    def test_prepare_reuses_quality_frames_at_unprocessed_native_pcm24_levels(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate = _resolved_quality_gate(root)
            state = root / "readiness"
            service = WorkbenchMasterReadinessService(
                state,
                gate["quality_service"],
            )

            prepared = _prepare_readiness(service, gate)

            self.assertEqual(
                prepared["schema"],
                MASTER_READINESS_COMPARISON_SCHEMA,
            )
            self.assertEqual(prepared["status"], "unreviewed")
            self.assertTrue(prepared["identity_labelled"])
            self.assertTrue(prepared["native_level"])
            self.assertIsNone(prepared["review"])
            self.assertEqual(prepared["effects"], PREPARE_EFFECTS)
            self.assertFalse(_contains_path(prepared))
            self.assertEqual(
                prepared["window"],
                gate["quality_prepared"]["window"],
            )
            self.assertEqual(
                prepared["quality_review"],
                {
                    "quality_review_id": gate["quality_review"]["review_id"],
                    "quality_review_sha256": gate["quality_review"][
                        "review_sha256"
                    ],
                    "quality_result_sha256": gate["quality_result"][
                        "result_sha256"
                    ],
                    "quality_comparison_sha256": gate["quality_review"][
                        "comparison_sha256"
                    ],
                    "quality_revision": 1,
                    "resolved_choice": gate["quality_result"]["resolved_choice"],
                    "explicitly_resolved": True,
                    "latest_for_reviewer": True,
                },
            )
            self.assertEqual(
                set(prepared["candidates"]),
                {BALANCED_CONTROL, LISTENING_MASTER},
            )
            self.assertEqual(
                prepared["problem_tags"],
                sorted(readiness_module.MASTER_READINESS_PROBLEM_TAGS),
            )
            self.assertEqual(
                prepared["limits"],
                {
                    "maximum_problem_tags_per_identity": 8,
                    "maximum_notes_characters": 2_000,
                },
            )

            window = prepared["window"]
            source_paths = {
                BALANCED_CONTROL: Path(
                    gate["evidence"]["balanced"]["preview"]["path"]
                ),
                LISTENING_MASTER: Path(
                    gate["evidence"]["listening_master"]["master"]["path"]
                ),
            }
            rms_dbfs: dict[str, float] = {}
            for identity in (BALANCED_CONTROL, LISTENING_MASTER):
                record = service.media_record(
                    prepared["comparison_sha256"],
                    identity,
                )
                crop_path = Path(record["path"])
                crop, sample_rate = soundfile.read(
                    str(crop_path),
                    dtype="float64",
                    always_2d=True,
                )
                source, source_rate = soundfile.read(
                    str(source_paths[identity]),
                    dtype="float64",
                    always_2d=True,
                )
                expected = source[
                    window["start_frame"] : window["end_frame"]
                ]
                self.assertEqual(sample_rate, source_rate)
                np.testing.assert_array_equal(crop, expected)
                info = soundfile.info(str(crop_path))
                self.assertEqual(str(info.format), "WAV")
                self.assertEqual(str(info.subtype), "PCM_24")
                self.assertEqual(
                    stat.S_IMODE(crop_path.stat().st_mode),
                    0o600,
                )
                self.assertEqual(
                    prepared["candidates"][identity]["applied_gain_db"],
                    0.0,
                )
                self.assertFalse(
                    prepared["candidates"][identity]["processing_applied"]
                )
                crop_rms = float(np.sqrt(np.mean(np.square(crop))))
                rms_dbfs[identity] = 20.0 * math.log10(crop_rms)
            self.assertAlmostEqual(
                rms_dbfs[LISTENING_MASTER] - rms_dbfs[BALANCED_CONTROL],
                6.0206,
                places=3,
            )

            manifest_path = (
                state
                / "audio"
                / prepared["comparison_sha256"]
                / "manifest.json"
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], MASTER_READINESS_AUDIO_SCHEMA)
            self.assertEqual(manifest["policy"]["applied_gain_db"], 0.0)
            self.assertFalse(manifest["policy"]["gain_matching_used"])
            self.assertFalse(manifest["policy"]["limiter_used"])
            self.assertFalse(manifest["policy"]["compression_used"])
            self.assertFalse(manifest["policy"]["equalisation_used"])
            self.assertNotIn(str(root), json.dumps(manifest, sort_keys=True))
            self.assertEqual(
                stat.S_IMODE(
                    (
                        state / "audio" / prepared["comparison_sha256"]
                    ).stat().st_mode
                ),
                0o700,
            )
            self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o700)
            self.assertEqual(
                stat.S_IMODE((state / "reviews.sqlite3").stat().st_mode),
                0o600,
            )
            self.assertEqual(_readiness_row_count(state), 0)

            again = _prepare_readiness(service, gate)
            restarted = _prepare_readiness(
                WorkbenchMasterReadinessService(
                    state,
                    gate["quality_service"],
                ),
                gate,
            )
            self.assertEqual(again, prepared)
            self.assertEqual(restarted, prepared)
            self.assertEqual(
                gate["quality_service"].review(
                    gate["quality_review"]["review_id"]
                ),
                gate["quality_review"],
            )
            self.assertEqual(
                gate["quality_service"].resolution(
                    gate["quality_review"]["review_id"]
                ),
                gate["quality_result"],
            )

    def test_gate_requires_verified_resolved_latest_quality_for_reviewer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate = _resolved_quality_gate(root)
            state = root / "readiness"
            service = WorkbenchMasterReadinessService(
                state,
                gate["quality_service"],
            )

            wrong_hash = dict(gate)
            wrong_hash["quality_result"] = {
                **gate["quality_result"],
                "result_sha256": "f" * 64,
            }
            with self.assertRaisesRegex(
                WorkbenchMasterReadinessGateError,
                "result SHA-256",
            ):
                _prepare_readiness(service, wrong_hash)

            wrong_reviewer = dict(gate)
            wrong_reviewer["reviewer_key"] = "different-private-reviewer"
            with self.assertRaisesRegex(
                WorkbenchMasterReadinessGateError,
                "not the latest|not current",
            ):
                _prepare_readiness(service, wrong_reviewer)

            second = _complete_quality(
                gate["quality_service"],
                gate["evidence"],
                gate["quality_prepared"],
                reviewer_key=gate["reviewer_key"],
                expected_revision=1,
                choice=CANDIDATE_B,
                problem_tags={
                    CANDIDATE_A: [],
                    CANDIDATE_B: [],
                },
            )
            self.assertEqual(second["revision"], 2)
            with self.assertRaisesRegex(
                WorkbenchMasterReadinessGateError,
                "not the latest",
            ):
                _prepare_readiness(service, gate)
            self.assertEqual(_readiness_row_count(state), 0)
            self.assertEqual(
                [
                    path
                    for path in (state / "audio").iterdir()
                    if not path.name.startswith(".")
                ],
                [],
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _evidence(root / "evidence")
            reviewer_key = "private-readiness-reviewer"
            quality = WorkbenchMasterReviewService(root / "quality")
            quality_prepared = _prepare_quality(
                quality,
                evidence,
                reviewer_key=reviewer_key,
            )
            quality_review = _complete_quality(
                quality,
                evidence,
                quality_prepared,
                reviewer_key=reviewer_key,
                expected_revision=0,
                choice=CANDIDATE_A,
                problem_tags={
                    CANDIDATE_A: [],
                    CANDIDATE_B: [],
                },
            )
            service = WorkbenchMasterReadinessService(
                root / "readiness",
                quality,
            )
            unresolved = {
                "evidence": evidence,
                "reviewer_key": reviewer_key,
                "quality_service": quality,
                "quality_prepared": quality_prepared,
                "quality_review": quality_review,
                "quality_result": {"result_sha256": "a" * 64},
            }
            with self.assertRaisesRegex(
                WorkbenchMasterReadinessGateError,
                "explicitly resolved",
            ):
                _prepare_readiness(service, unresolved)

    def test_gate_rejects_resolved_review_superseded_by_another_window(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = _evidence(root / "evidence")
            reviewer_key = "private-cross-window-reviewer"
            quality = WorkbenchMasterReviewService(root / "quality")

            def resolved_window(start_seconds: float, end_seconds: float) -> dict[str, Any]:
                prepared = quality.prepare(
                    project_id=evidence["project_id"],
                    balanced=evidence["balanced"],
                    listening_master=evidence["listening_master"],
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    reviewer_session_key=reviewer_key,
                )
                review = _complete_quality(
                    quality,
                    evidence,
                    prepared,
                    reviewer_key=reviewer_key,
                    expected_revision=0,
                    choice=CANDIDATE_A,
                    problem_tags={
                        CANDIDATE_A: [],
                        CANDIDATE_B: [],
                    },
                )
                result = quality.resolve(
                    project_id=evidence["project_id"],
                    balanced=evidence["balanced"],
                    listening_master=evidence["listening_master"],
                    review_id=review["review_id"],
                )
                return {
                    "evidence": evidence,
                    "reviewer_key": reviewer_key,
                    "quality_service": quality,
                    "quality_prepared": prepared,
                    "quality_review": review,
                    "quality_result": result,
                }

            earlier = resolved_window(0.25, 1.25)
            latest = resolved_window(0.50, 1.50)
            self.assertNotEqual(
                earlier["quality_prepared"]["comparison_sha256"],
                latest["quality_prepared"]["comparison_sha256"],
            )
            self.assertEqual(
                quality.latest_review_for_project_reviewer(
                    project_id=evidence["project_id"],
                    reviewer_session_key=reviewer_key,
                ),
                latest["quality_review"],
            )

            state = root / "readiness"
            service = WorkbenchMasterReadinessService(state, quality)
            with self.assertRaisesRegex(
                WorkbenchMasterReadinessGateError,
                "not the latest",
            ):
                _prepare_readiness(service, earlier)
            self.assertEqual(_readiness_row_count(state), 0)
            self.assertEqual(
                [
                    path
                    for path in (state / "audio").iterdir()
                    if not path.name.startswith(".")
                ],
                [],
            )

            prepared = _prepare_readiness(service, latest)
            self.assertEqual(
                prepared["quality_review"]["quality_review_id"],
                latest["quality_review"]["review_id"],
            )

    def test_complete_is_immutable_direct_export_ready_and_idempotent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate = _resolved_quality_gate(root)
            state = root / "readiness"
            service = WorkbenchMasterReadinessService(
                state,
                gate["quality_service"],
            )
            prepared = _prepare_readiness(service, gate)

            review = _complete_readiness(
                service,
                gate,
                prepared,
                choice=LISTENING_MASTER,
                problem_tags={
                    BALANCED_CONTROL: ["muddy"],
                    LISTENING_MASTER: ["harsh", "thin"],
                },
                notes="The challenger is easier to continue working from.",
            )

            self.assertEqual(review["schema"], MASTER_READINESS_REVIEW_SCHEMA)
            self.assertEqual(review["status"], "reviewed")
            self.assertTrue(review["identity_labelled"])
            self.assertTrue(review["native_level"])
            self.assertEqual(review["policy"], MASTER_READINESS_POLICY)
            self.assertTrue(review["export_ready"])
            self.assertEqual(
                review["response"],
                {
                    "heard": {
                        BALANCED_CONTROL: True,
                        LISTENING_MASTER: True,
                    },
                    "choice": LISTENING_MASTER,
                    "problem_tags": {
                        BALANCED_CONTROL: ["muddy"],
                        LISTENING_MASTER: ["harsh", "thin"],
                    },
                    "notes": (
                        "The challenger is easier to continue working from."
                    ),
                },
            )
            self.assertEqual(review["effects"], REVIEW_EFFECTS)
            self.assertTrue(review["effects"]["feedback_recorded"])
            self.assertTrue(
                review["effects"]["readiness_review_record_created"]
            )
            self.assertTrue(
                all(
                    value is False
                    for key, value in review["effects"].items()
                    if key
                    not in {
                        "feedback_recorded",
                        "readiness_review_record_created",
                    }
                )
            )
            self.assertFalse(_contains_path(review))
            self.assertEqual(
                service.review(review["readiness_review_id"]),
                review,
            )
            self.assertEqual(_readiness_row_count(state), 1)
            self.assertNotIn(
                gate["reviewer_key"].encode("utf-8"),
                (state / "reviews.sqlite3").read_bytes(),
            )

            exact_retry = _complete_readiness(
                service,
                gate,
                prepared,
                choice=LISTENING_MASTER,
                problem_tags={
                    BALANCED_CONTROL: ["muddy"],
                    LISTENING_MASTER: ["harsh", "thin"],
                },
                notes="The challenger is easier to continue working from.",
            )
            self.assertEqual(exact_retry, review)
            self.assertEqual(_readiness_row_count(state), 1)

            with self.assertRaisesRegex(
                WorkbenchMasterReadinessConflictError,
                "different native-level response",
            ):
                _complete_readiness(
                    service,
                    gate,
                    prepared,
                    choice=BALANCED_CONTROL,
                    problem_tags={
                        BALANCED_CONTROL: ["muddy"],
                        LISTENING_MASTER: ["harsh", "thin"],
                    },
                    notes="The challenger is easier to continue working from.",
                )
            self.assertEqual(_readiness_row_count(state), 1)

            restored = _prepare_readiness(
                WorkbenchMasterReadinessService(
                    state,
                    gate["quality_service"],
                ),
                gate,
            )
            self.assertEqual(restored["status"], "reviewed")
            self.assertEqual(restored["review"], review)
            self.assertEqual(restored["effects"], PREPARE_EFFECTS)

    def test_completion_validation_writes_nothing_until_both_are_heard(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate = _resolved_quality_gate(root)
            state = root / "readiness"
            service = WorkbenchMasterReadinessService(
                state,
                gate["quality_service"],
            )
            prepared = _prepare_readiness(service, gate)
            common = _completion_kwargs(service, gate, prepared)

            with self.assertRaisesRegex(ValueError, "marked heard"):
                service.complete(
                    **common,
                    heard={
                        BALANCED_CONTROL: True,
                        LISTENING_MASTER: False,
                    },
                    choice=BALANCED_CONTROL,
                    problem_tags={
                        BALANCED_CONTROL: [],
                        LISTENING_MASTER: [],
                    },
                )
            with self.assertRaisesRegex(ValueError, "unsupported"):
                service.complete(
                    **common,
                    heard=_heard_both(),
                    choice=CANDIDATE_A,
                    problem_tags={
                        BALANCED_CONTROL: [],
                        LISTENING_MASTER: [],
                    },
                )
            with self.assertRaisesRegex(ValueError, "unsupported problem tags"):
                service.complete(
                    **common,
                    heard=_heard_both(),
                    choice=BALANCED_CONTROL,
                    problem_tags={
                        BALANCED_CONTROL: ["unbounded_custom_tag"],
                        LISTENING_MASTER: [],
                    },
                )
            with self.assertRaisesRegex(ValueError, "must be unique"):
                service.complete(
                    **common,
                    heard=_heard_both(),
                    choice=BALANCED_CONTROL,
                    problem_tags={
                        BALANCED_CONTROL: ["muddy", "muddy"],
                        LISTENING_MASTER: [],
                    },
                )
            with self.assertRaisesRegex(ValueError, "limited to 2000"):
                service.complete(
                    **common,
                    heard=_heard_both(),
                    choice=BALANCED_CONTROL,
                    problem_tags={
                        BALANCED_CONTROL: [],
                        LISTENING_MASTER: [],
                    },
                    notes="x" * 2_001,
                )
            self.assertEqual(_readiness_row_count(state), 0)

            completed = service.complete(
                **common,
                heard=_heard_both(),
                choice="equivalent",
                problem_tags={
                    BALANCED_CONTROL: [],
                    LISTENING_MASTER: [],
                },
                notes=None,
            )
            self.assertEqual(completed["response"]["notes"], "")
            self.assertEqual(_readiness_row_count(state), 1)

    def test_parallel_prepare_and_complete_publish_one_verified_winner(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate = _resolved_quality_gate(root)
            state = root / "readiness"
            service = WorkbenchMasterReadinessService(
                state,
                gate["quality_service"],
            )
            barrier = threading.Barrier(2)
            original_write = readiness_module._write_pcm24

            def synchronized_write(
                path: Path,
                values: Any,
                sample_rate: int,
            ) -> None:
                barrier.wait(timeout=10)
                original_write(path, values, sample_rate)

            with (
                patch.object(
                    readiness_module,
                    "_write_pcm24",
                    side_effect=synchronized_write,
                ),
                ThreadPoolExecutor(max_workers=2) as executor,
            ):
                futures = [
                    executor.submit(_prepare_readiness, service, gate)
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

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [
                    executor.submit(
                        _complete_readiness,
                        service,
                        gate,
                        prepared[0],
                        choice="cannot_tell",
                        problem_tags={
                            BALANCED_CONTROL: [],
                            LISTENING_MASTER: [],
                        },
                    )
                    for _ in range(4)
                ]
                reviews = [future.result(timeout=20) for future in futures]
            self.assertTrue(all(review == reviews[0] for review in reviews))
            self.assertEqual(_readiness_row_count(state), 1)
            self.assertEqual(
                service.review(reviews[0]["readiness_review_id"]),
                reviews[0],
            )

    def test_audio_manifest_review_and_quality_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate = _resolved_quality_gate(root)
            state = root / "readiness"
            service = WorkbenchMasterReadinessService(
                state,
                gate["quality_service"],
            )
            prepared = _prepare_readiness(service, gate)
            audio_path = Path(
                service.media_record(
                    prepared["comparison_sha256"],
                    BALANCED_CONTROL,
                )["path"]
            )
            audio_path.write_bytes(audio_path.read_bytes() + b"tamper")
            audio_path.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "audio changed"):
                service.media_record(
                    prepared["comparison_sha256"],
                    BALANCED_CONTROL,
                )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate = _resolved_quality_gate(root)
            state = root / "readiness"
            service = WorkbenchMasterReadinessService(
                state,
                gate["quality_service"],
            )
            prepared = _prepare_readiness(service, gate)
            manifest_path = (
                state
                / "audio"
                / prepared["comparison_sha256"]
                / "manifest.json"
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["policy"]["gain_matching_used"] = True
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            manifest_path.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "manifest is invalid"):
                service.media_record(
                    prepared["comparison_sha256"],
                    LISTENING_MASTER,
                )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate = _resolved_quality_gate(root)
            state = root / "readiness"
            service = WorkbenchMasterReadinessService(
                state,
                gate["quality_service"],
            )
            prepared = _prepare_readiness(service, gate)
            directory = state / "audio" / prepared["comparison_sha256"]
            audio_path = directory / "balanced-control.wav"
            values, sample_rate = soundfile.read(
                str(audio_path),
                dtype="float64",
                always_2d=True,
            )
            original_sha256 = hashlib.sha256(audio_path.read_bytes()).hexdigest()
            soundfile.write(
                str(audio_path),
                -values,
                sample_rate,
                format="WAV",
                subtype="PCM_24",
            )
            audio_path.chmod(0o600)
            changed_sha256 = hashlib.sha256(audio_path.read_bytes()).hexdigest()
            self.assertNotEqual(changed_sha256, original_sha256)

            manifest_path = directory / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            record = manifest["candidates"][BALANCED_CONTROL]["audio"]
            record["bytes"] = audio_path.stat().st_size
            record["sha256"] = changed_sha256
            unsigned = {
                key: value
                for key, value in manifest.items()
                if key != "manifest_sha256"
            }
            manifest["manifest_sha256"] = readiness_module._document_hash(unsigned)
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            manifest_path.chmod(0o600)

            restarted = WorkbenchMasterReadinessService(
                state,
                gate["quality_service"],
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "crop changed source samples",
            ):
                _prepare_readiness(restarted, gate)
            with self.assertRaisesRegex(
                RuntimeError,
                "crop changed source samples",
            ):
                restarted.media_record(
                    prepared["comparison_sha256"],
                    BALANCED_CONTROL,
                )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate = _resolved_quality_gate(root)
            state = root / "readiness"
            service = WorkbenchMasterReadinessService(
                state,
                gate["quality_service"],
            )
            prepared = _prepare_readiness(service, gate)
            review = _complete_readiness(
                service,
                gate,
                prepared,
                choice="neither",
                problem_tags={
                    BALANCED_CONTROL: [],
                    LISTENING_MASTER: [],
                },
            )
            with sqlite3.connect(str(state / "reviews.sqlite3")) as connection:
                stored = json.loads(
                    connection.execute(
                        """
                        SELECT review_json FROM readiness_reviews
                        WHERE readiness_review_id = ?
                        """,
                        (review["readiness_review_id"],),
                    ).fetchone()[0]
                )
                stored["response"]["choice"] = "equivalent"
                connection.execute(
                    """
                    UPDATE readiness_reviews SET review_json = ?
                    WHERE readiness_review_id = ?
                    """,
                    (
                        json.dumps(stored, sort_keys=True),
                        review["readiness_review_id"],
                    ),
                )
            (state / "reviews.sqlite3").chmod(0o600)
            with self.assertRaisesRegex(ValueError, "stored native-level"):
                service.review(review["readiness_review_id"])


def _resolved_quality_gate(root: Path) -> dict[str, Any]:
    evidence = _evidence(root / "evidence")
    reviewer_key = "private-readiness-reviewer"
    quality_service = WorkbenchMasterReviewService(root / "quality")
    quality_prepared = _prepare_quality(
        quality_service,
        evidence,
        reviewer_key=reviewer_key,
    )
    quality_review = _complete_quality(
        quality_service,
        evidence,
        quality_prepared,
        reviewer_key=reviewer_key,
        expected_revision=0,
        choice=CANDIDATE_A,
        problem_tags={
            CANDIDATE_A: ["muddy"],
            CANDIDATE_B: ["harsh"],
        },
        notes="Blind quality judgment.",
    )
    quality_result = quality_service.resolve(
        project_id=evidence["project_id"],
        balanced=evidence["balanced"],
        listening_master=evidence["listening_master"],
        review_id=quality_review["review_id"],
    )
    return {
        "evidence": evidence,
        "reviewer_key": reviewer_key,
        "quality_service": quality_service,
        "quality_prepared": quality_prepared,
        "quality_review": quality_review,
        "quality_result": quality_result,
    }


def _prepare_readiness(
    service: WorkbenchMasterReadinessService,
    gate: dict[str, Any],
) -> dict[str, Any]:
    return service.prepare(
        project_id=gate["evidence"]["project_id"],
        balanced=gate["evidence"]["balanced"],
        listening_master=gate["evidence"]["listening_master"],
        quality_review_id=gate["quality_review"]["review_id"],
        quality_review_sha256=gate["quality_review"]["review_sha256"],
        quality_result_sha256=gate["quality_result"]["result_sha256"],
        reviewer_session_key=gate["reviewer_key"],
    )


def _completion_kwargs(
    service: WorkbenchMasterReadinessService,
    gate: dict[str, Any],
    prepared: dict[str, Any],
) -> dict[str, Any]:
    return {
        "project_id": gate["evidence"]["project_id"],
        "balanced": gate["evidence"]["balanced"],
        "listening_master": gate["evidence"]["listening_master"],
        "comparison_sha256": prepared["comparison_sha256"],
        "quality_review_id": gate["quality_review"]["review_id"],
        "quality_review_sha256": gate["quality_review"]["review_sha256"],
        "quality_result_sha256": gate["quality_result"]["result_sha256"],
        "reviewer_session_key": gate["reviewer_key"],
    }


def _complete_readiness(
    service: WorkbenchMasterReadinessService,
    gate: dict[str, Any],
    prepared: dict[str, Any],
    *,
    choice: str,
    problem_tags: dict[str, list[str]],
    notes: str | None = None,
) -> dict[str, Any]:
    return service.complete(
        **_completion_kwargs(service, gate, prepared),
        heard=_heard_both(),
        choice=choice,
        problem_tags=problem_tags,
        notes=notes,
    )


def _heard_both() -> dict[str, bool]:
    return {
        BALANCED_CONTROL: True,
        LISTENING_MASTER: True,
    }


def _readiness_row_count(root: Path) -> int:
    with sqlite3.connect(str(root / "reviews.sqlite3")) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM readiness_reviews"
        ).fetchone()
    if row is None:
        raise AssertionError("missing readiness_reviews table")
    return int(row[0])


if __name__ == "__main__":
    unittest.main()
