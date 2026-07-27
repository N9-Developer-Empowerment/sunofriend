from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import stat
import struct
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile

from sunofriend import workbench_instrument_review as instrument_module
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_artifacts import WorkbenchArtifacts
from sunofriend.workbench_instrument_review import (
    CANDIDATE_A,
    CANDIDATE_B,
    MAXIMUM_AGGREGATE_INPUT_BYTES,
    MAXIMUM_MIDI_BYTES,
    MAXIMUM_MIDI_NOTE_ONS,
    MAXIMUM_RENDERER_BYTES,
    MAXIMUM_RENDER_HORIZON_SECONDS,
    MAXIMUM_SOURCE_AUDIO_BYTES,
    MAXIMUM_SOUNDFONT_BYTES,
    SOURCE_REFERENCE,
    SOURCE_SNAPSHOT_POLICY,
    WorkbenchInstrumentReviewRevisionConflictError,
    WorkbenchInstrumentReviewService,
    _program_proxy_evidence,
    _write_program_proxy,
)
from sunofriend.midi_transform import _parse_midi


class WorkbenchInstrumentReviewContextTests(unittest.TestCase):
    def test_context_is_selection_anchored_and_bass_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts = _fixture(root)
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            selected = selection["selected_midi"][0]

            context = artifacts.instrument_review_context(
                catalog,
                current,
                selected["track_id"],
                selection["selection_manifest_sha256"],
            )

            self.assertEqual(context["track"]["role"], "bass")
            self.assertEqual(context["track"]["midi"]["sha256"], selected["midi_sha256"])
            self.assertEqual(
                context["selection_manifest_sha256"],
                selection["selection_manifest_sha256"],
            )
            self.assertEqual(
                {row["program"] for row in context["programs"].values()},
                {38, 39},
            )
            with self.assertRaisesRegex(ValueError, "selected arrangement changed"):
                artifacts.instrument_review_context(
                    catalog,
                    current,
                    selected["track_id"],
                    "0" * 64,
                )
            changed = copy.deepcopy(current)
            changed["stems"]["bass-stem"]["role"] = "keys"
            changed_selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, changed
            )
            with self.assertRaisesRegex(ValueError, "only for selected bass"):
                artifacts.instrument_review_context(
                    catalog,
                    changed,
                    changed_selection["selected_midi"][0]["track_id"],
                    changed_selection["selection_manifest_sha256"],
                )


class WorkbenchInstrumentReviewServiceTests(unittest.TestCase):
    def test_fixed_midi_blind_review_is_level_matched_durable_and_separate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts = _fixture(root)
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            context = artifacts.instrument_review_context(
                catalog,
                current,
                selection["selected_midi"][0]["track_id"],
                selection["selection_manifest_sha256"],
            )
            original_midi = Path(context["track"]["midi"]["path"])
            original_bytes = original_midi.read_bytes()
            renderer = root / "fluidsynth"
            renderer.write_bytes(b"private-test-renderer")
            service = WorkbenchInstrumentReviewService(root / "review")

            with (
                patch(
                    "sunofriend.workbench_instrument_review.find_fluidsynth",
                    return_value=str(renderer),
                ),
                patch(
                    "sunofriend.workbench_instrument_review.render_midi_to_wav",
                    side_effect=_render_program,
                ),
            ):
                prepared = service.prepare(
                    context=context,
                    start_seconds=0.25,
                    end_seconds=1.25,
                    reviewer_session_key="browser-session",
                )

                serialized = json.dumps(prepared, sort_keys=True)
                self.assertNotIn(str(root), serialized)
                self.assertNotIn("Synth Bass", serialized)
                self.assertNotIn('"program"', serialized)
                self.assertNotIn('"control"', serialized)
                self.assertNotIn('"challenger"', serialized)
                self.assertTrue(prepared["blind"])
                self.assertIsNone(prepared["current_review"])
                self.assertEqual(
                    prepared["comparison"]["selected_midi"]["sha256"],
                    _sha256(original_midi),
                )
                self.assertEqual(
                    prepared["comparison"]["window"]["frame_count"],
                    8_000,
                )
                levels = [
                    prepared["audio"][slot]["rms_dbfs"]
                    for slot in (SOURCE_REFERENCE, CANDIDATE_A, CANDIDATE_B)
                ]
                self.assertLessEqual(max(levels) - min(levels), 0.05)
                gains = prepared["audio"]["level_match"]["inputs"]
                self.assertEqual(
                    set(gains),
                    {SOURCE_REFERENCE, CANDIDATE_A, CANDIDATE_B},
                )
                self.assertTrue(
                    all(float(row["applied_gain_db"]) <= 0.0 for row in gains.values())
                )
                self.assertTrue(
                    all(row["boost_applied"] is False for row in gains.values())
                )

                comparison_sha = prepared["comparison_sha256"]
                for slot in (SOURCE_REFERENCE, CANDIDATE_A, CANDIDATE_B):
                    media = service.media_record(comparison_sha, slot)
                    self.assertEqual(stat.S_IMODE(Path(media["path"]).stat().st_mode), 0o600)
                    info = soundfile.info(media["path"])
                    self.assertEqual(info.frames, 8_000)
                    self.assertEqual(info.samplerate, 8_000)

                review = service.complete(
                    context=context,
                    comparison_sha256=comparison_sha,
                    reviewer_session_key="browser-session",
                    expected_revision=0,
                    heard={
                        SOURCE_REFERENCE: True,
                        CANDIDATE_A: True,
                        CANDIDATE_B: True,
                    },
                    choice=CANDIDATE_B,
                    problem_tags={
                        CANDIDATE_A: ["too_plucky"],
                        CANDIDATE_B: [],
                    },
                    notes={
                        CANDIDATE_A: "shorter sustain",
                        CANDIDATE_B: "more continuous",
                    },
                )
                replay = service.complete(
                    context=context,
                    comparison_sha256=comparison_sha,
                    reviewer_session_key="browser-session",
                    expected_revision=0,
                    heard={
                        SOURCE_REFERENCE: True,
                        CANDIDATE_A: True,
                        CANDIDATE_B: True,
                    },
                    choice=CANDIDATE_B,
                    problem_tags={
                        CANDIDATE_A: ["too_plucky"],
                        CANDIDATE_B: [],
                    },
                    notes={
                        CANDIDATE_A: "shorter sustain",
                        CANDIDATE_B: "more continuous",
                    },
                )
                self.assertEqual(replay, review)
                with self.assertRaises(WorkbenchInstrumentReviewRevisionConflictError):
                    service.complete(
                        context=context,
                        comparison_sha256=comparison_sha,
                        reviewer_session_key="browser-session",
                        expected_revision=0,
                        heard={
                            SOURCE_REFERENCE: True,
                            CANDIDATE_A: True,
                            CANDIDATE_B: True,
                        },
                        choice=CANDIDATE_A,
                        problem_tags={CANDIDATE_A: [], CANDIDATE_B: []},
                        notes={CANDIDATE_A: "", CANDIDATE_B: ""},
                    )

                resolved = service.resolve(
                    context=context,
                    comparison_sha256=comparison_sha,
                    review_id=review["review_id"],
                    review_sha256=review["review_sha256"],
                )
                self.assertEqual(
                    {
                        row["program"]
                        for row in resolved["assignment"].values()
                    },
                    {38, 39},
                )
                self.assertFalse(resolved["promotion_allowed"])
                self.assertFalse(resolved["default_changed"])
                self.assertEqual(service.resolution(review["review_id"]), resolved)

                restarted = WorkbenchInstrumentReviewService(root / "review")
                current_state = restarted.current(
                    context=context,
                    comparison_sha256=comparison_sha,
                    reviewer_session_key="browser-session",
                )
                self.assertEqual(current_state["current_review"], review)
                binding = restarted.comparison_binding(comparison_sha)
                self.assertEqual(binding, prepared["comparison"])
                self.assertNotIn(str(root), json.dumps(binding, sort_keys=True))
                with sqlite3.connect(restarted.database_path) as connection:
                    connection.execute(
                        """
                        UPDATE comparison_sessions SET binding_json = ?
                        WHERE comparison_sha256 = ?
                        """,
                        ("{}", comparison_sha),
                    )
                with self.assertRaisesRegex(
                    ValueError, "comparison binding is invalid"
                ):
                    restarted.comparison_binding(comparison_sha)

            self.assertEqual(original_midi.read_bytes(), original_bytes)
            private_root = service.audio_root / prepared["comparison_sha256"]
            selected_snapshot = private_root / "selected-midi.mid"
            self.assertEqual(selected_snapshot.read_bytes(), original_bytes)
            evidence = [
                _program_proxy_evidence(
                    selected_snapshot,
                    private_root / f"{identity}-proxy.mid",
                    expected_program=program,
                )
                for identity, program in (("control", 38), ("challenger", 39))
            ]
            self.assertTrue(all(row["note_signatures_match"] for row in evidence))
            self.assertTrue(
                all(row["only_program_change_data_changed"] for row in evidence)
            )

    def test_heard_gate_window_and_current_input_tamper_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts = _fixture(root)
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            context = artifacts.instrument_review_context(
                catalog,
                current,
                selection["selected_midi"][0]["track_id"],
                selection["selection_manifest_sha256"],
            )
            renderer = root / "fluidsynth"
            renderer.write_bytes(b"private-test-renderer")
            service = WorkbenchInstrumentReviewService(root / "review")
            with (
                patch(
                    "sunofriend.workbench_instrument_review.find_fluidsynth",
                    return_value=str(renderer),
                ),
                patch(
                    "sunofriend.workbench_instrument_review.render_midi_to_wav",
                    side_effect=_render_program,
                ),
            ):
                with self.assertRaisesRegex(ValueError, "between 0.5 and 15.0"):
                    service.prepare(
                        context=context,
                        start_seconds=0.0,
                        end_seconds=0.49,
                        reviewer_session_key="reviewer",
                    )
                prepared = service.prepare(
                    context=context,
                    start_seconds=0.0,
                    end_seconds=1.0,
                    reviewer_session_key="reviewer",
                )
                with self.assertRaisesRegex(ValueError, "hear the source"):
                    service.complete(
                        context=context,
                        comparison_sha256=prepared["comparison_sha256"],
                        reviewer_session_key="reviewer",
                        expected_revision=0,
                        heard={
                            SOURCE_REFERENCE: False,
                            CANDIDATE_A: True,
                            CANDIDATE_B: True,
                        },
                        choice="none_usable",
                        problem_tags={CANDIDATE_A: [], CANDIDATE_B: []},
                        notes={CANDIDATE_A: "", CANDIDATE_B: ""},
                    )
                Path(context["track"]["midi"]["path"]).write_bytes(b"changed")
                with self.assertRaisesRegex(RuntimeError, "selected bass MIDI changed"):
                    service.current(
                        context=context,
                        comparison_sha256=prepared["comparison_sha256"],
                        reviewer_session_key="reviewer",
                    )

    def test_prepare_and_review_are_concurrent_idempotent_with_cas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts = _fixture(root)
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            context = artifacts.instrument_review_context(
                catalog,
                current,
                selection["selected_midi"][0]["track_id"],
                selection["selection_manifest_sha256"],
            )
            renderer = root / "fluidsynth"
            renderer.write_bytes(b"private-test-renderer")
            service = WorkbenchInstrumentReviewService(root / "review")

            def prepare() -> dict:
                return service.prepare(
                    context=context,
                    start_seconds=0.0,
                    end_seconds=1.0,
                    reviewer_session_key="same-reviewer",
                )

            with (
                patch(
                    "sunofriend.workbench_instrument_review.find_fluidsynth",
                    return_value=str(renderer),
                ),
                patch(
                    "sunofriend.workbench_instrument_review.render_midi_to_wav",
                    side_effect=_render_program,
                ),
                ThreadPoolExecutor(max_workers=2) as executor,
            ):
                prepared = list(executor.map(lambda _index: prepare(), range(2)))
                self.assertEqual(prepared[0], prepared[1])
                comparison_sha = prepared[0]["comparison_sha256"]
                payload = {
                    "context": context,
                    "comparison_sha256": comparison_sha,
                    "reviewer_session_key": "same-reviewer",
                    "expected_revision": 0,
                    "heard": {
                        SOURCE_REFERENCE: True,
                        CANDIDATE_A: True,
                        CANDIDATE_B: True,
                    },
                    "choice": CANDIDATE_A,
                    "problem_tags": {CANDIDATE_A: [], CANDIDATE_B: []},
                    "notes": {CANDIDATE_A: "", CANDIDATE_B: ""},
                }
                exact = list(
                    executor.map(
                        lambda _index: service.complete(**payload),
                        range(2),
                    )
                )
                self.assertEqual(exact[0], exact[1])

                def conflicting(choice: str) -> dict:
                    return service.complete(
                        **{
                            **payload,
                            "reviewer_session_key": "cas-reviewer",
                            "choice": choice,
                        }
                    )

                futures = [
                    executor.submit(conflicting, CANDIDATE_A),
                    executor.submit(conflicting, CANDIDATE_B),
                ]
                outcomes: list[object] = []
                for future in futures:
                    try:
                        outcomes.append(future.result())
                    except Exception as exc:  # noqa: BLE001 - asserted below
                        outcomes.append(exc)
                self.assertEqual(
                    sum(isinstance(value, dict) for value in outcomes),
                    1,
                )
                conflicts = [
                    value
                    for value in outcomes
                    if isinstance(
                        value, WorkbenchInstrumentReviewRevisionConflictError
                    )
                ]
                self.assertEqual(len(conflicts), 1)
                self.assertEqual(conflicts[0].expected_revision, 0)
                self.assertEqual(conflicts[0].current_revision, 1)

    def test_source_dependency_and_private_artifact_tamper_fail_closed(self) -> None:
        cases = ("source", "soundfont", "proxy", "audio", "manifest")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                catalog, current, artifacts = _fixture(root)
                selection = artifacts.decoded_arrangement_selection_manifest(
                    catalog, current
                )
                context = artifacts.instrument_review_context(
                    catalog,
                    current,
                    selection["selected_midi"][0]["track_id"],
                    selection["selection_manifest_sha256"],
                )
                renderer = root / "fluidsynth"
                renderer.write_bytes(b"private-test-renderer")
                service = WorkbenchInstrumentReviewService(root / "review")
                with (
                    patch(
                        "sunofriend.workbench_instrument_review.find_fluidsynth",
                        return_value=str(renderer),
                    ),
                    patch(
                        "sunofriend.workbench_instrument_review.render_midi_to_wav",
                        side_effect=_render_program,
                    ),
                ):
                    prepared = service.prepare(
                        context=context,
                        start_seconds=0.0,
                        end_seconds=1.0,
                        reviewer_session_key="reviewer",
                    )
                    comparison_sha = prepared["comparison_sha256"]
                    private = service.audio_root / comparison_sha
                    if case == "source":
                        Path(context["source"]["path"]).write_bytes(b"changed")
                    elif case == "soundfont":
                        Path(context["soundfont"]["path"]).write_bytes(b"changed")
                    elif case == "proxy":
                        proxy = private / "control-proxy.mid"
                        proxy.write_bytes(proxy.read_bytes() + b"x")
                    elif case == "audio":
                        audio = private / "candidate-a.wav"
                        audio.write_bytes(audio.read_bytes() + b"x")
                    else:
                        manifest_path = private / "manifest.json"
                        manifest = json.loads(
                            manifest_path.read_text(encoding="utf-8")
                        )
                        manifest["path_free_manifest"] = False
                        manifest_path.write_text(
                            json.dumps(manifest),
                            encoding="utf-8",
                        )
                        manifest_path.chmod(0o600)
                    with self.assertRaises(
                        (RuntimeError, ValueError),
                    ):
                        if case in {"source", "soundfont"}:
                            service.current(
                                context=context,
                                comparison_sha256=comparison_sha,
                                reviewer_session_key="reviewer",
                            )
                        else:
                            service.media_record(
                                comparison_sha,
                                CANDIDATE_A,
                            )

    def test_common_level_policy_rejects_silence_and_source_divergence(
        self,
    ) -> None:
        renderers = (
            ("silence", _render_silent_challenger, "too quiet"),
            ("source-divergence", _render_too_quiet_pair, "allowed 18.0 dB"),
        )
        for name, render, message in renderers:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                catalog, current, artifacts = _fixture(root)
                selection = artifacts.decoded_arrangement_selection_manifest(
                    catalog, current
                )
                context = artifacts.instrument_review_context(
                    catalog,
                    current,
                    selection["selected_midi"][0]["track_id"],
                    selection["selection_manifest_sha256"],
                )
                renderer = root / "fluidsynth"
                renderer.write_bytes(b"private-test-renderer")
                service = WorkbenchInstrumentReviewService(root / "review")
                with (
                    patch(
                        "sunofriend.workbench_instrument_review.find_fluidsynth",
                        return_value=str(renderer),
                    ),
                    patch(
                        "sunofriend.workbench_instrument_review.render_midi_to_wav",
                        side_effect=render,
                    ),
                ):
                    with self.assertRaisesRegex(ValueError, message):
                        service.prepare(
                            context=context,
                            start_seconds=0.0,
                            end_seconds=1.0,
                            reviewer_session_key="reviewer",
                        )

    def test_common_peak_guard_attenuates_all_inputs_without_limiting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts = _fixture(root)
            source = Path(catalog["stems"][0]["source_path"])
            hot = np.full((16_000, 1), 0.01, dtype="float32")
            hot[100, 0] = 0.99
            hot[8_100, 0] = 0.99
            soundfile.write(source, hot, 8_000, subtype="PCM_16")
            catalog["stems"][0]["source"] = _record(source)
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            context = artifacts.instrument_review_context(
                catalog,
                current,
                selection["selected_midi"][0]["track_id"],
                selection["selection_manifest_sha256"],
            )
            renderer = root / "fluidsynth"
            renderer.write_bytes(b"private-test-renderer")
            service = WorkbenchInstrumentReviewService(root / "review")
            with (
                patch(
                    "sunofriend.workbench_instrument_review.find_fluidsynth",
                    return_value=str(renderer),
                ),
                patch(
                    "sunofriend.workbench_instrument_review.render_midi_to_wav",
                    side_effect=_render_low_pair,
                ),
            ):
                prepared = service.prepare(
                    context=context,
                    start_seconds=0.0,
                    end_seconds=1.0,
                    reviewer_session_key="reviewer",
                )
            level = prepared["audio"]["level_match"]
            self.assertTrue(level["peak_guard_applied"])
            self.assertLess(level["common_peak_guard_gain_db"], 0.0)
            self.assertFalse(level["limiting_applied"])
            self.assertFalse(level["compression_applied"])
            common_gains = {
                row["common_peak_guard_gain_db"]
                for row in level["inputs"].values()
            }
            self.assertEqual(len(common_gains), 1)
            peaks = [
                prepared["audio"][slot]["sample_peak_dbfs"]
                for slot in (SOURCE_REFERENCE, CANDIDATE_A, CANDIDATE_B)
            ]
            self.assertLessEqual(max(peaks), -0.999)

    def test_private_persistence_is_owner_only_and_json_path_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts = _fixture(root)
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            context = artifacts.instrument_review_context(
                catalog,
                current,
                selection["selected_midi"][0]["track_id"],
                selection["selection_manifest_sha256"],
            )
            renderer = root / "fluidsynth"
            renderer.write_bytes(b"private-test-renderer")
            service = WorkbenchInstrumentReviewService(root / "review")
            with (
                patch(
                    "sunofriend.workbench_instrument_review.find_fluidsynth",
                    return_value=str(renderer),
                ),
                patch(
                    "sunofriend.workbench_instrument_review.render_midi_to_wav",
                    side_effect=_render_program,
                ),
            ):
                prepared = service.prepare(
                    context=context,
                    start_seconds=0.0,
                    end_seconds=1.0,
                    reviewer_session_key="reviewer",
                )
                review = service.complete(
                    context=context,
                    comparison_sha256=prepared["comparison_sha256"],
                    reviewer_session_key="reviewer",
                    expected_revision=0,
                    heard={
                        SOURCE_REFERENCE: True,
                        CANDIDATE_A: True,
                        CANDIDATE_B: True,
                    },
                    choice="none_usable",
                    problem_tags={CANDIDATE_A: [], CANDIDATE_B: []},
                    notes={CANDIDATE_A: "", CANDIDATE_B: ""},
                )
                service.resolve(
                    context=context,
                    comparison_sha256=prepared["comparison_sha256"],
                    review_id=review["review_id"],
                    review_sha256=review["review_sha256"],
                )
            self.assertEqual(stat.S_IMODE(service.root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(service.audio_root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(service.database_path.stat().st_mode), 0o600)
            private = service.audio_root / prepared["comparison_sha256"]
            self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o700)
            for path in private.iterdir():
                if path.is_file():
                    self.assertEqual(
                        stat.S_IMODE(path.stat().st_mode),
                        0o600,
                        path.name,
                    )
            with sqlite3.connect(service.database_path) as connection:
                payloads = [
                    row[0]
                    for table, column in (
                        ("comparison_sessions", "binding_json"),
                        ("review_events", "review_json"),
                        ("review_resolutions", "result_json"),
                    )
                    for row in connection.execute(
                        f"SELECT {column} FROM {table}"  # noqa: S608 - fixed names
                    )
                ]
            manifest = (private / "manifest.json").read_text(encoding="utf-8")
            for payload in [*payloads, manifest]:
                document = json.loads(payload)
                self.assertNotIn(str(root), json.dumps(document, sort_keys=True))
                self.assertFalse(_contains_path_key(document))


class WorkbenchInstrumentReviewResourceBoundTests(unittest.TestCase):
    def test_per_file_limits_reject_before_hashing(self) -> None:
        cases = (
            ("selected bass MIDI", MAXIMUM_MIDI_BYTES),
            ("bass source stem", MAXIMUM_SOURCE_AUDIO_BYTES),
            ("SoundFont", MAXIMUM_SOUNDFONT_BYTES),
            ("FluidSynth renderer", MAXIMUM_RENDERER_BYTES),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (label, maximum) in enumerate(cases):
                with self.subTest(label=label):
                    path = root / f"oversized-{index}.bin"
                    with path.open("wb") as handle:
                        handle.truncate(maximum + 1)
                    record = {
                        "path": str(path),
                        "name": path.name,
                        "bytes": maximum + 1,
                        "sha256": "0" * 64,
                    }
                    with patch.object(
                        instrument_module,
                        "_file_sha256",
                        side_effect=AssertionError(
                            "oversized input must fail before hashing"
                        ),
                    ) as hasher:
                        with self.assertRaisesRegex(
                            ValueError, "file-size limit"
                        ):
                            instrument_module._checked_input_record(
                                record,
                                label=label,
                                maximum_bytes=maximum,
                            )
                    hasher.assert_not_called()

    def test_aggregate_limit_fails_before_midi_parse_or_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts = _fixture(root)
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            context = artifacts.instrument_review_context(
                catalog,
                current,
                selection["selected_midi"][0]["track_id"],
                selection["selection_manifest_sha256"],
            )
            renderer = root / "fluidsynth"
            renderer.write_bytes(b"renderer")
            sizes = {
                "selected bass MIDI": MAXIMUM_MIDI_BYTES,
                "bass source stem": MAXIMUM_SOURCE_AUDIO_BYTES,
                "SoundFont": MAXIMUM_SOUNDFONT_BYTES,
                "FluidSynth renderer": 8,
            }

            def checked(_value: object, *, label: str, maximum_bytes: int) -> dict:
                size = sizes[label]
                self.assertLessEqual(size, maximum_bytes)
                return {
                    "path": str(renderer),
                    "name": label,
                    "bytes": size,
                    "sha256": hashlib.sha256(label.encode()).hexdigest(),
                }

            with (
                patch.object(
                    instrument_module,
                    "_checked_input_record",
                    side_effect=checked,
                ),
                patch.object(
                    instrument_module,
                    "_audio_info",
                    return_value={
                        "sample_rate": 8_000,
                        "channels": 1,
                        "frames": 16_000,
                    },
                ),
                patch.object(
                    instrument_module,
                    "find_fluidsynth",
                    return_value=str(renderer),
                ),
                patch.object(
                    instrument_module,
                    "_file_sha256",
                    return_value="f" * 64,
                ),
                patch.object(
                    instrument_module,
                    "_selected_midi_evidence",
                    side_effect=AssertionError(
                        "aggregate limit must fail before MIDI parsing"
                    ),
                ) as midi_parser,
                patch.object(
                    instrument_module,
                    "_verified_snapshot",
                    side_effect=AssertionError(
                        "aggregate limit must fail before snapshots"
                    ),
                ) as snapshot,
            ):
                with self.assertRaisesRegex(ValueError, "aggregate size limit"):
                    instrument_module._verified_context_evidence(context)
            midi_parser.assert_not_called()
            snapshot.assert_not_called()
            self.assertGreater(
                sum(sizes.values()),
                MAXIMUM_AGGREGATE_INPUT_BYTES,
            )

    def test_prepared_binding_discloses_exact_window_snapshot_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts = _fixture(root)
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            context = artifacts.instrument_review_context(
                catalog,
                current,
                selection["selected_midi"][0]["track_id"],
                selection["selection_manifest_sha256"],
            )
            renderer = root / "fluidsynth"
            renderer.write_bytes(b"private-test-renderer")
            service = WorkbenchInstrumentReviewService(root / "review")
            with (
                patch(
                    "sunofriend.workbench_instrument_review.find_fluidsynth",
                    return_value=str(renderer),
                ),
                patch(
                    "sunofriend.workbench_instrument_review.render_midi_to_wav",
                    side_effect=_render_program,
                ),
            ):
                prepared = service.prepare(
                    context=context,
                    start_seconds=0.25,
                    end_seconds=1.25,
                    reviewer_session_key="reviewer",
                )
            limits = prepared["comparison"]["input_limits"]
            self.assertEqual(
                limits["source_snapshot_policy"],
                SOURCE_SNAPSHOT_POLICY,
            )
            self.assertFalse(limits["full_source_snapshot_created"])
            self.assertEqual(limits["midi_bytes"], 64 * 1024 * 1024)
            self.assertEqual(limits["source_audio_bytes"], 2 * 1024 * 1024 * 1024)
            self.assertEqual(limits["soundfont_bytes"], 2 * 1024 * 1024 * 1024)
            self.assertEqual(limits["renderer_bytes"], 256 * 1024 * 1024)
            self.assertEqual(limits["aggregate_bytes"], 3 * 1024 * 1024 * 1024)
            self.assertEqual(limits["midi_note_ons"], MAXIMUM_MIDI_NOTE_ONS)
            self.assertEqual(
                limits["render_horizon_seconds"],
                MAXIMUM_RENDER_HORIZON_SECONDS,
            )
            private = service.audio_root / prepared["comparison_sha256"]
            self.assertFalse((private / "source-input.wav").exists())
            self.assertFalse((private / "source-window-float32.wav").exists())
            self.assertTrue((private / "source-reference.wav").is_file())

    def test_midi_render_horizon_fails_before_snapshot_or_fluidsynth(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts = _fixture(root)
            long_midi = root / "long-horizon.mid"
            maximum_tick = int(
                (MAXIMUM_RENDER_HORIZON_SECONDS + 1) * 120 / 60 * 480
            )
            _write_raw_midi(
                long_midi,
                [
                    [
                        (0, bytes((0xC0, 38))),
                        (0, bytes((0x90, 40, 90))),
                        (480, bytes((0x80, 40, 0))),
                        (maximum_tick - 480, b"\xff\x01\x00"),
                    ]
                ],
            )
            candidate = catalog["stems"][0]["candidates"][0]
            candidate["midi_path"] = str(long_midi.resolve())
            candidate["midi"] = _record(long_midi)
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            context = artifacts.instrument_review_context(
                catalog,
                current,
                selection["selected_midi"][0]["track_id"],
                selection["selection_manifest_sha256"],
            )
            renderer = root / "fluidsynth"
            renderer.write_bytes(b"private-test-renderer")
            service = WorkbenchInstrumentReviewService(root / "review")
            with (
                patch(
                    "sunofriend.workbench_instrument_review.find_fluidsynth",
                    return_value=str(renderer),
                ),
                patch.object(
                    instrument_module,
                    "_verified_snapshot",
                    side_effect=AssertionError(
                        "render horizon must fail before snapshots"
                    ),
                ) as snapshot,
                patch(
                    "sunofriend.workbench_instrument_review.render_midi_to_wav",
                    side_effect=AssertionError(
                        "render horizon must fail before FluidSynth"
                    ),
                ) as renderer_call,
            ):
                with self.assertRaisesRegex(ValueError, "20-minute render horizon"):
                    service.prepare(
                        context=context,
                        start_seconds=0.0,
                        end_seconds=1.0,
                        reviewer_session_key="reviewer",
                    )
            snapshot.assert_not_called()
            renderer_call.assert_not_called()


class WorkbenchInstrumentProxyInvariantTests(unittest.TestCase):
    def test_bank_selection_and_same_tick_program_order_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for controller in (0, 32):
                with self.subTest(nonzero_bank_controller=controller):
                    source = root / f"bank-{controller}.mid"
                    _write_raw_midi(
                        source,
                        [
                            [
                                (0, bytes((0xB0, controller, 1))),
                                (0, bytes((0xC0, 38))),
                                (0, bytes((0x90, 40, 90))),
                                (480, bytes((0x80, 40, 0))),
                            ]
                        ],
                    )
                    with self.assertRaisesRegex(ValueError, "nonzero CC0/CC32"):
                        _write_program_proxy(
                            source,
                            root / f"bank-{controller}-proxy.mid",
                            program=39,
                        )

            note_before_program = root / "note-before-program.mid"
            _write_raw_midi(
                note_before_program,
                [
                    [
                        (0, bytes((0x90, 40, 90))),
                        (0, bytes((0xC0, 38))),
                        (480, bytes((0x80, 40, 0))),
                    ]
                ],
            )
            with self.assertRaisesRegex(
                ValueError, "effective Program Change before every playable Note On"
            ):
                _write_program_proxy(
                    note_before_program,
                    root / "late-program-proxy.mid",
                    program=39,
                )

            ambiguous = root / "cross-track-bank.mid"
            _write_raw_midi(
                ambiguous,
                [
                    [(0, bytes((0xB0, 0, 0)))],
                    [
                        (0, bytes((0xC0, 38))),
                        (0, bytes((0x90, 40, 90))),
                        (480, bytes((0x80, 40, 0))),
                    ],
                ],
            )
            with self.assertRaisesRegex(ValueError, "ambiguous cross-track"):
                _write_program_proxy(
                    ambiguous,
                    root / "ambiguous-proxy.mid",
                    program=39,
                )

            ordered = root / "ordered.mid"
            _write_raw_midi(
                ordered,
                [
                    [
                        (0, bytes((0xB0, 0, 0))),
                        (0, bytes((0xB0, 32, 0))),
                        (0, bytes((0xC0, 38))),
                        (0, bytes((0x90, 40, 90))),
                        (480, bytes((0x80, 40, 0))),
                    ]
                ],
            )
            evidence = _write_program_proxy(
                ordered,
                root / "ordered-proxy.mid",
                program=39,
            )
            self.assertEqual(evidence["bank_select_event_count"], 2)
            self.assertTrue(evidence["bank_select_all_zero"])
            self.assertTrue(evidence["same_tick_raw_event_order_checked"])
            self.assertTrue(
                evidence["effective_target_program_before_every_note_on"]
            )

    def test_missing_program_and_non_program_byte_change_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mid"
            write_midi_file(
                source,
                [
                    MidiTrack(
                        "Bass",
                        0,
                        38,
                        [NoteEvent(0.0, 1.0, 40, 90)],
                    )
                ],
                bpm=120.0,
            )
            layout = _parse_midi(source.read_bytes())
            program = next(
                event
                for track in layout.tracks
                for event in track.events
                if event.category == "channel" and event.event_type == 0xC0
            )
            without_program = root / "without-program.mid"
            data = bytearray(source.read_bytes())
            data[program.data_offsets[0] - 1] = 0xD0
            without_program.write_bytes(bytes(data))
            with self.assertRaisesRegex(ValueError, "effective Program Change"):
                _write_program_proxy(
                    without_program,
                    root / "invalid-proxy.mid",
                    program=39,
                )

            proxy = root / "proxy.mid"
            _write_program_proxy(source, proxy, program=39)
            proxy_layout = _parse_midi(proxy.read_bytes())
            note = next(
                event
                for track in proxy_layout.tracks
                for event in track.events
                if event.category == "channel"
                and event.event_type == 0x90
                and event.data[1] > 0
            )
            changed = bytearray(proxy.read_bytes())
            changed[note.data_offsets[0]] += 1
            proxy.write_bytes(bytes(changed))
            with self.assertRaisesRegex(ValueError, "fixed MIDI note events"):
                _program_proxy_evidence(
                    source,
                    proxy,
                    expected_program=39,
                )


def _fixture(root: Path) -> tuple[dict, dict, WorkbenchArtifacts]:
    source = root / "bass.wav"
    soundfile.write(
        source,
        np.full((16_000, 1), 0.4, dtype="float32"),
        8_000,
        subtype="PCM_16",
    )
    midi = root / "bass.mid"
    write_midi_file(
        midi,
        [
            MidiTrack(
                "Bass",
                0,
                38,
                [
                    NoteEvent(0.0, 0.75, 40, 91),
                    NoteEvent(0.75, 2.0, 43, 86),
                ],
            )
        ],
        bpm=120.0,
    )
    soundfont = root / "test.sf2"
    soundfont.write_bytes(b"instrument-review-test-bank")
    catalog = {
        "project_id": "instrument-review-project",
        "setup": {"bpm": 120.0},
        "stems": [
            {
                "stem_id": "bass-stem",
                "role": "bass",
                "source_path": str(source.resolve()),
                "source": _record(source),
                "candidates": [
                    {
                        "candidate_id": "bass-candidate",
                        "midi_path": str(midi.resolve()),
                        "midi": _record(midi),
                        "audition_blocked": False,
                        "process": "test",
                    }
                ],
            }
        ],
    }
    current = {
        "stems": {
            "bass-stem": {
                "role": "bass",
                "main_candidate_id": "bass-candidate",
                "candidates": {
                    "bass-candidate": {
                        "decision": "main",
                        "context": "full_mix",
                    }
                },
            }
        }
    }
    return (
        catalog,
        current,
        WorkbenchArtifacts(
            root / "artifacts",
            soundfont_path=soundfont,
        ),
    )


def _render_program(midi_path: Path, wav_path: Path, **kwargs: object) -> None:
    layout = _parse_midi(Path(midi_path).read_bytes())
    programs = [
        event.data[0]
        for track in layout.tracks
        for event in track.events
        if event.category == "channel" and event.event_type == 0xC0
    ]
    program = programs[-1]
    amplitude = {38: 0.1, 39: 0.2}[program]
    sample_rate = int(kwargs["sample_rate"])
    soundfile.write(
        wav_path,
        np.full((sample_rate * 2, 2), amplitude, dtype="float32"),
        sample_rate,
        subtype="PCM_16",
    )


def _render_silent_challenger(
    midi_path: Path, wav_path: Path, **kwargs: object
) -> None:
    _render_with_amplitudes(
        midi_path,
        wav_path,
        amplitudes={38: 0.1, 39: 0.0},
        sample_rate=int(kwargs["sample_rate"]),
    )


def _render_too_quiet_pair(
    midi_path: Path, wav_path: Path, **kwargs: object
) -> None:
    _render_with_amplitudes(
        midi_path,
        wav_path,
        amplitudes={38: 0.005, 39: 0.005},
        sample_rate=int(kwargs["sample_rate"]),
    )


def _render_low_pair(
    midi_path: Path, wav_path: Path, **kwargs: object
) -> None:
    _render_with_amplitudes(
        midi_path,
        wav_path,
        amplitudes={38: 0.02, 39: 0.02},
        sample_rate=int(kwargs["sample_rate"]),
    )


def _render_with_amplitudes(
    midi_path: Path,
    wav_path: Path,
    *,
    amplitudes: dict[int, float],
    sample_rate: int,
) -> None:
    layout = _parse_midi(Path(midi_path).read_bytes())
    programs = [
        event.data[0]
        for track in layout.tracks
        for event in track.events
        if event.category == "channel" and event.event_type == 0xC0
    ]
    soundfile.write(
        wav_path,
        np.full(
            (sample_rate * 2, 2),
            amplitudes[programs[-1]],
            dtype="float32",
        ),
        sample_rate,
        subtype="PCM_16",
    )


def _contains_path_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower() == "path"
            or str(key).lower().endswith("_path")
            or _contains_path_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_path_key(item) for item in value)
    return False


def _write_raw_midi(
    path: Path,
    tracks: list[list[tuple[int, bytes]]],
) -> None:
    chunks: list[bytes] = []
    for events in tracks:
        body = bytearray()
        for delta, payload in events:
            body.extend(_midi_varlen(delta))
            body.extend(payload)
        body.extend(b"\x00\xff\x2f\x00")
        chunks.append(b"MTrk" + struct.pack(">I", len(body)) + bytes(body))
    midi_format = 0 if len(chunks) == 1 else 1
    path.write_bytes(
        b"MThd"
        + struct.pack(">IHHH", 6, midi_format, len(chunks), 480)
        + b"".join(chunks)
    )


def _midi_varlen(value: int) -> bytes:
    buffer = value & 0x7F
    output = bytearray((buffer,))
    value >>= 7
    while value:
        buffer = (value & 0x7F) | 0x80
        output.insert(0, buffer)
        value >>= 7
    return bytes(output)


def _record(path: Path) -> dict:
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
