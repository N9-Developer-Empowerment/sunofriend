from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mido
import numpy as np
import soundfile

from sunofriend.midi_ab_review import (
    MIDI_AB_ANSWER_KEY_SCHEMA,
    MIDI_AB_RESULT_SCHEMA,
    MIDI_AB_REVIEW_SCHEMA,
    create_midi_ab_review,
    resolve_midi_ab_review,
)


_SAMPLE_RATE = 8_000
_DURATION_SECONDS = 6.0


class MidiAbReviewTests(unittest.TestCase):
    def _fixtures(self, root: Path) -> dict[str, Path]:
        frames = round(_SAMPLE_RATE * _DURATION_SECONDS)
        time = np.arange(frames, dtype=np.float64) / _SAMPLE_RATE
        source_audio = np.column_stack(
            (
                0.12 * np.sin(2.0 * math.pi * 110.0 * time),
                0.12 * np.sin(2.0 * math.pi * 110.0 * time),
            )
        ).astype(np.float32)
        source = root / "private-source.wav"
        soundfile.write(source, source_audio, _SAMPLE_RATE, subtype="PCM_24")
        candidate_a = root / "private-candidate-a.mid"
        candidate_b = root / "private-candidate-b.mid"
        _write_midi(candidate_a, pitch=60)
        _write_midi(candidate_b, pitch=67)
        soundfont = root / "fixture.sf2"
        soundfont.write_bytes(b"deterministic-test-soundfont")
        renderer = root / "fluidsynth-fixture"
        renderer.write_text(
            "#!/bin/sh\necho 'FluidSynth fixture version 1.0'\n",
            encoding="utf-8",
        )
        renderer.chmod(0o755)
        return {
            "source": source,
            "candidate_a": candidate_a,
            "candidate_b": candidate_b,
            "soundfont": soundfont,
            "renderer": renderer,
        }

    def _render(
        self,
        fixtures: dict[str, Path],
        *,
        silent_b: bool = False,
        quiet_b_amplitude: float | None = None,
    ):
        def fake_render(midi_path, wav_path, sample_rate=44_100, **_kwargs):
            self._render_calls.append(
                {
                    "midi_path": Path(midi_path),
                    "wav_path": Path(wav_path),
                    "sample_rate": sample_rate,
                    **_kwargs,
                }
            )
            notes = [
                message.note
                for track in mido.MidiFile(midi_path).tracks
                for message in track
                if message.type == "note_on" and message.velocity > 0
            ]
            if 60 in notes:
                amplitude = 0.8
                frequency = 220.0
            elif 67 in notes:
                amplitude = (
                    0.0
                    if silent_b
                    else (quiet_b_amplitude if quiet_b_amplitude is not None else 0.2)
                )
                frequency = 330.0
            else:  # pragma: no cover - identifies an unexpected implementation call
                raise AssertionError(f"unexpected MIDI render input: {midi_path}")
            frames = round(float(sample_rate) * _DURATION_SECONDS)
            time = np.arange(frames, dtype=np.float64) / float(sample_rate)
            mono = amplitude * np.sin(2.0 * math.pi * frequency * time)
            stereo = np.column_stack((mono, mono)).astype(np.float32)
            output = Path(wav_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            soundfile.write(output, stereo, sample_rate, subtype="PCM_24")
            return output

        return fake_render

    def _create(
        self,
        fixtures: dict[str, Path],
        out_dir: Path,
        intervals: list[tuple[float, float, str]],
        *,
        silent_b: bool = False,
        quiet_b_amplitude: float | None = None,
        midi_time_at_source_start_seconds: float = 0.0,
    ) -> dict:
        self._render_calls = []
        with (
            patch(
                "sunofriend.midi_ab_review.find_fluidsynth",
                return_value=str(fixtures["renderer"]),
            ),
            patch(
                "sunofriend.midi_ab_review.render_midi_to_wav",
                side_effect=self._render(
                    fixtures,
                    silent_b=silent_b,
                    quiet_b_amplitude=quiet_b_amplitude,
                ),
            ),
        ):
            return create_midi_ab_review(
                fixtures["source"],
                fixtures["candidate_a"],
                fixtures["candidate_b"],
                intervals,
                out_dir,
                bpm=119.0,
                midi_time_at_source_start_seconds=(midi_time_at_source_start_seconds),
                gm_program=4,
                soundfont_path=fixtures["soundfont"],
            )

    def _reviewed_export(
        self,
        report: dict,
        path: Path,
        *,
        heard: dict[str, bool] | None = None,
    ) -> Path:
        review = _read(Path(report["seed"]))
        review["status"] = "reviewed"
        review["summary"]["reviewed_unit_count"] = len(review["units"])
        heard_state = heard or {
            "source": True,
            "candidate_a": True,
            "candidate_b": True,
        }
        for unit in review["units"]:
            unit["heard"] = dict(heard_state)
            unit["choice"] = "candidate_a"
            unit["notes"] = "Explicit fixture review."
        _write(path, review)
        return path

    def _tamper_private_answer_and_repin(
        self,
        report: dict,
        reviewed_path: Path,
        mutate,
    ) -> None:
        package = Path(report["out_dir"])
        answer_path = package / "midi_ab_answer_key.json"
        answer = _read(answer_path)
        mutate(answer)
        _write(answer_path, answer)
        digest = _sha256(answer_path)
        seed_path = package / "midi_ab_review.json"
        seed = _read(seed_path)
        seed["answer_key"]["sha256"] = digest
        _write(seed_path, seed)
        reviewed = _read(reviewed_path)
        reviewed["answer_key"]["sha256"] = digest
        _write(reviewed_path, reviewed)

    def test_review_has_exact_crops_level_match_blinding_and_zero_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = self._fixtures(root)
            originals = {name: _sha256(path) for name, path in fixtures.items()}
            intervals = [
                (0.125, 1.375, "Judge chord completeness without added clutter."),
                (2.0, 3.25, "Judge bass timing and octave."),
            ]

            report = self._create(fixtures, root / "review", intervals)

            review_root = Path(report["out_dir"])
            seed = _read(Path(report["seed"]))
            self.assertEqual(seed["schema"], MIDI_AB_REVIEW_SCHEMA)
            self.assertEqual(seed["status"], "unreviewed")
            self.assertTrue(seed["blind"])
            self.assertEqual(seed["effects"]["source_audio_mutated"], False)
            self.assertEqual(seed["effects"]["source_midis_mutated"], 0)
            self.assertEqual(seed["effects"]["midi_notes_changed"], 0)
            self.assertEqual(seed["effects"]["review_choices_inferred"], 0)
            self.assertFalse(seed["effects"]["selection_changed"])
            self.assertEqual(len(self._render_calls), 2)
            for call in self._render_calls:
                self.assertEqual(call["sample_rate"], _SAMPLE_RATE)
                self.assertEqual(call["gain"], 0.7)
                self.assertEqual(
                    Path(call["soundfont_path"]).resolve(),
                    fixtures["soundfont"].resolve(),
                )
                self.assertEqual(
                    Path(call["fluidsynth_path"]).resolve(),
                    fixtures["renderer"].resolve(),
                )
            self.assertEqual(len(seed["units"]), len(intervals))
            original_source = soundfile.read(
                fixtures["source"], dtype="float64", always_2d=True
            )[0]
            for unit, (start, end, focus) in zip(seed["units"], intervals):
                start_frame = round(start * _SAMPLE_RATE)
                end_frame = round(end * _SAMPLE_RATE)
                frame_count = end_frame - start_frame
                self.assertEqual(unit["frame_start"], start_frame)
                self.assertEqual(unit["frame_end"], end_frame)
                self.assertEqual(unit["frame_count"], frame_count)
                self.assertEqual(unit["sample_rate"], _SAMPLE_RATE)
                self.assertEqual(unit["listening_focus"], focus)
                self.assertIsNone(unit["choice"])
                records = (
                    unit["source"],
                    unit["candidate_a"],
                    unit["candidate_b"],
                )
                for record in records:
                    path = _record_path(review_root, record)
                    info = soundfile.info(path)
                    self.assertEqual(info.samplerate, _SAMPLE_RATE)
                    self.assertEqual(info.frames, frame_count)
                    self.assertEqual(info.channels, 2)
                    self.assertEqual(record["frames"], frame_count)
                    self.assertEqual(record["sha256"], _sha256(path))

                source_crop = soundfile.read(
                    _record_path(review_root, unit["source"]),
                    dtype="float64",
                    always_2d=True,
                )[0]
                np.testing.assert_array_equal(
                    source_crop,
                    original_source[start_frame:end_frame],
                )

                candidate_a = soundfile.read(
                    _record_path(review_root, unit["candidate_a"]),
                    dtype="float64",
                    always_2d=True,
                )[0]
                candidate_b = soundfile.read(
                    _record_path(review_root, unit["candidate_b"]),
                    dtype="float64",
                    always_2d=True,
                )[0]
                rms_a = float(np.sqrt(np.mean(np.square(candidate_a))))
                rms_b = float(np.sqrt(np.mean(np.square(candidate_b))))
                mismatch_db = abs(20.0 * math.log10(rms_a / rms_b))
                self.assertLessEqual(mismatch_db, 0.05)
                self.assertLess(float(np.max(np.abs(candidate_a))), 1.0)
                self.assertLess(float(np.max(np.abs(candidate_b))), 1.0)
                self.assertLessEqual(
                    abs(
                        unit["candidate_a"]["rms_dbfs"]
                        - unit["candidate_b"]["rms_dbfs"]
                    ),
                    0.05,
                )
                self.assertLess(unit["candidate_a"]["peak_dbfs"], 0.0)
                self.assertLess(unit["candidate_b"]["peak_dbfs"], 0.0)

            page = Path(report["html"]).read_text(encoding="utf-8")
            node = shutil.which("node")
            if node:
                script = page.split("<script>", 1)[1].split("</script>", 1)[0]
                syntax = subprocess.run(
                    [node, "--check"],
                    input=script,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(syntax.returncode, 0, syntax.stderr)
            key = _read(Path(report["answer_key"]))
            self.assertEqual(key["schema"], MIDI_AB_ANSWER_KEY_SCHEMA)
            for answer_unit in key["units"]:
                level_match = answer_unit["level_match"]
                self.assertEqual(
                    level_match["method"],
                    "pairwise-fixed-window-rms-attenuation-only-v1",
                )
                gains = [
                    level_match["inputs"][identity]["gain_db"]
                    for identity in ("input_1", "input_2")
                ]
                self.assertEqual(max(gains), 0.0)
                self.assertTrue(all(gain <= 0.0 for gain in gains))
                self.assertFalse(level_match["limiter_used"])
            serialised_seed = json.dumps(seed, sort_keys=True)
            self.assertNotIn("input_candidate_a", page)
            self.assertNotIn("input_candidate_b", page)
            self.assertNotIn(fixtures["candidate_a"].name, page)
            self.assertNotIn(fixtures["candidate_b"].name, page)
            self.assertNotIn(json.dumps(key["units"], sort_keys=True), page)
            self.assertNotIn("input_candidate_a", serialised_seed)
            self.assertNotIn("input_candidate_b", serialised_seed)
            self.assertIn("if(!complete())review.status='unreviewed'", page)
            self.assertIn("review.status!=='reviewed'||!complete()", page)
            self.assertEqual(
                {name: _sha256(path) for name, path in fixtures.items()}, originals
            )

    def test_patched_blind_nonce_is_deterministic_across_fresh_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = self._fixtures(root)
            intervals = [
                (0.25, 1.25, "Judge the melodic contour."),
                (2.25, 3.75, "Judge the rhythmic feel."),
            ]

            with patch(
                "sunofriend.midi_ab_review.secrets.token_bytes",
                return_value=b"\x11" * 32,
            ):
                first = self._create(fixtures, root / "first", intervals)
                second = self._create(fixtures, root / "second", intervals)

            first_key = _read(Path(first["answer_key"]))
            second_key = _read(Path(second["answer_key"]))
            self.assertEqual(first_key["units"], second_key["units"])
            first_seed = _read(Path(first["seed"]))
            second_seed = _read(Path(second["seed"]))
            for left, right in zip(first_seed["units"], second_seed["units"]):
                self.assertEqual(left["unit_id"], right["unit_id"])
                for name in (
                    "source",
                    "candidate_a",
                    "candidate_b",
                ):
                    self.assertEqual(left[name]["sha256"], right[name]["sha256"])

    def test_different_private_nonces_change_mapping_without_public_disclosure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = self._fixtures(root)
            intervals = [
                (0.25, 1.25, "Judge the melodic contour."),
                (2.25, 3.75, "Judge the rhythmic feel."),
            ]
            first_nonce = b"\x00" * 32
            with patch(
                "sunofriend.midi_ab_review.secrets.token_bytes",
                return_value=first_nonce,
            ):
                first = self._create(fixtures, root / "first", intervals)
            first_key = _read(Path(first["answer_key"]))
            commitment = first_key["package_commitment"]
            unit_ids = [unit["unit_id"] for unit in first_key["units"]]
            first_mapping = [unit["candidate_a"] for unit in first_key["units"]]
            second_nonce = next(
                bytes([value]) * 32
                for value in range(1, 256)
                if _candidate_a_mapping(bytes([value]) * 32, commitment, unit_ids)
                != first_mapping
            )
            with patch(
                "sunofriend.midi_ab_review.secrets.token_bytes",
                return_value=second_nonce,
            ):
                second = self._create(fixtures, root / "second", intervals)
            second_key = _read(Path(second["answer_key"]))

            self.assertNotEqual(
                first_mapping,
                [unit["candidate_a"] for unit in second_key["units"]],
            )
            for report, nonce in ((first, first_nonce), (second, second_nonce)):
                page = Path(report["html"]).read_text(encoding="utf-8")
                seed_text = Path(report["seed"]).read_text(encoding="utf-8")
                self.assertNotIn(nonce.hex(), page)
                self.assertNotIn(nonce.hex(), seed_text)
                self.assertNotIn("blind_nonce_hex", page)
                self.assertNotIn("blind_nonce_hex", seed_text)
                self.assertNotIn("input_1", page)
                self.assertNotIn("input_2", page)
                self.assertNotIn("input_1", seed_text)
                self.assertNotIn("input_2", seed_text)

    def test_resolver_preserves_all_explicit_choice_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = self._fixtures(root)
            choices = (
                "candidate_a",
                "candidate_b",
                "equivalent",
                "neither",
                "cannot_tell",
            )
            intervals = [
                (index * 1.0, index * 1.0 + 0.75, f"Review focus {index + 1}.")
                for index in range(len(choices))
            ]
            report = self._create(fixtures, root / "review", intervals)
            reviewed = _read(Path(report["seed"]))
            reviewed["status"] = "reviewed"
            reviewed["summary"]["reviewed_unit_count"] = len(choices)
            for unit, choice in zip(reviewed["units"], choices):
                unit["choice"] = choice
                unit["notes"] = f"Explicit {choice} fixture choice."
                unit["heard"] = {
                    "source": True,
                    "candidate_a": True,
                    "candidate_b": True,
                }
            review_path = root / "midi-ab.reviewed.json"
            _write(review_path, reviewed)
            output = root / "midi-ab.result.json"

            result = resolve_midi_ab_review(
                review_path, output, package_dir=report["out_dir"]
            )

            self.assertEqual(result["schema"], MIDI_AB_RESULT_SCHEMA)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(
                [unit["choice"] for unit in result["units"]], list(choices)
            )
            self.assertEqual(
                [unit["resolved_identity"] for unit in result["units"]][2:],
                ["equivalent", "neither", "cannot_tell"],
            )
            self.assertFalse(result["promotion_allowed"])
            self.assertFalse(result["default_changed"])
            self.assertEqual(result["effects"]["source_audio_mutated"], False)
            self.assertEqual(result["effects"]["source_midis_mutated"], 0)
            self.assertEqual(result["effects"]["midi_notes_changed"], 0)
            self.assertEqual(_read(output), result)
            with self.assertRaises(FileExistsError):
                resolve_midi_ab_review(
                    review_path, output, package_dir=report["out_dir"]
                )

    def test_browser_integer_number_round_trip_preserves_immutable_meaning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = self._fixtures(root)
            report = self._create(
                fixtures,
                root / "review",
                [(0.0, 1.0, "Browser numeric round-trip fixture.")],
                midi_time_at_source_start_seconds=0.0,
            )
            reviewed = _browser_number_round_trip(_read(Path(report["seed"])))
            self.assertIsInstance(
                reviewed["alignment_contract"][
                    "midi_time_at_source_start_seconds"
                ],
                int,
            )
            self.assertEqual(
                reviewed["alignment_contract"][
                    "midi_time_at_source_start_seconds"
                ],
                0,
            )
            reviewed["status"] = "reviewed"
            reviewed["summary"]["reviewed_unit_count"] = 1
            reviewed["units"][0]["heard"] = {
                "source": True,
                "candidate_a": True,
                "candidate_b": True,
            }
            reviewed["units"][0]["choice"] = "candidate_a"
            reviewed["units"][0]["notes"] = "Legitimate browser export."
            review_path = root / "browser.reviewed.json"
            _write(review_path, reviewed)

            result = resolve_midi_ab_review(
                review_path,
                root / "browser.result.json",
                package_dir=report["out_dir"],
            )

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["units"][0]["choice"], "candidate_a")

    def test_browser_round_trip_does_not_hide_real_alignment_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = self._fixtures(root)
            report = self._create(
                fixtures,
                root / "review",
                [(0.0, 1.0, "Tampered browser export fixture.")],
                midi_time_at_source_start_seconds=0.0,
            )
            reviewed = _browser_number_round_trip(_read(Path(report["seed"])))
            reviewed["status"] = "reviewed"
            reviewed["summary"]["reviewed_unit_count"] = 1
            reviewed["units"][0]["heard"] = {
                "source": True,
                "candidate_a": True,
                "candidate_b": True,
            }
            reviewed["units"][0]["choice"] = "candidate_a"
            reviewed["alignment_contract"][
                "midi_time_at_source_start_seconds"
            ] = 0.125
            review_path = root / "tampered-browser.reviewed.json"
            _write(review_path, reviewed)

            with self.assertRaisesRegex(ValueError, "immutable package fields"):
                resolve_midi_ab_review(
                    review_path,
                    root / "must-not-exist.json",
                    package_dir=report["out_dir"],
                )

    def test_browser_number_equivalence_rejects_boolean_and_string_zero(self) -> None:
        for value in (False, "0"):
            with self.subTest(value=repr(value)), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixtures = self._fixtures(root)
                report = self._create(
                    fixtures,
                    root / "review",
                    [(0.0, 1.0, "Reject non-numeric zero substitutes.")],
                    midi_time_at_source_start_seconds=0.0,
                )
                reviewed_path = self._reviewed_export(
                    report, root / "reviewed.json"
                )
                reviewed = _read(reviewed_path)
                reviewed["alignment_contract"][
                    "midi_time_at_source_start_seconds"
                ] = value
                _write(reviewed_path, reviewed)

                with self.assertRaisesRegex(
                    ValueError, "immutable package fields"
                ):
                    resolve_midi_ab_review(
                        reviewed_path,
                        root / "must-not-exist.json",
                        package_dir=report["out_dir"],
                    )

    def test_negative_zero_browser_round_trip_is_legitimate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = self._fixtures(root)
            report = self._create(
                fixtures,
                root / "review",
                [(0.5, 1.5, "Negative-zero browser fixture.")],
                midi_time_at_source_start_seconds=-0.0,
            )
            seed = _read(Path(report["seed"]))
            self.assertEqual(
                math.copysign(
                    1.0,
                    seed["alignment_contract"][
                        "midi_time_at_source_start_seconds"
                    ],
                ),
                -1.0,
            )
            reviewed = _browser_number_round_trip(seed)
            self.assertEqual(
                reviewed["alignment_contract"][
                    "midi_time_at_source_start_seconds"
                ],
                0,
            )
            reviewed["status"] = "reviewed"
            reviewed["summary"]["reviewed_unit_count"] = 1
            reviewed["units"][0]["heard"] = {
                "source": True,
                "candidate_a": True,
                "candidate_b": True,
            }
            reviewed["units"][0]["choice"] = "candidate_b"
            review_path = root / "negative-zero.reviewed.json"
            _write(review_path, reviewed)

            result = resolve_midi_ab_review(
                review_path,
                root / "negative-zero.result.json",
                package_dir=report["out_dir"],
            )

            self.assertEqual(result["status"], "complete")

    def test_numeric_equivalence_is_directional_from_seed_to_browser_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = self._fixtures(root)
            report = self._create(
                fixtures,
                root / "review",
                [(0.5, 1.5, "Directional numeric-equivalence fixture.")],
                midi_time_at_source_start_seconds=0.0,
            )
            reviewed_path = self._reviewed_export(
                report, root / "reviewed.json"
            )
            reviewed = _read(reviewed_path)
            seed_frame_start = reviewed["units"][0]["frame_start"]
            self.assertIsInstance(seed_frame_start, int)
            reviewed["units"][0]["frame_start"] = float(seed_frame_start)
            _write(reviewed_path, reviewed)

            with self.assertRaisesRegex(ValueError, "immutable package fields"):
                resolve_midi_ab_review(
                    reviewed_path,
                    root / "must-not-exist.json",
                    package_dir=report["out_dir"],
                )

    def test_rejects_invalid_or_overlapping_intervals_and_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = self._fixtures(root)
            cases = (
                ([], "interval"),
                ([(1.0, 1.0, "No duration.")], "interval|duration"),
                ([(-0.1, 1.0, "Negative start.")], "interval|start"),
                ([(0.0, 7.0, "Beyond source.")], "interval|source|duration"),
                ([(0.0, 2.0, "First."), (1.9, 3.0, "Overlap.")], "overlap"),
                ([(0.0, 1.0, "")], "focus"),
            )
            for index, (intervals, message) in enumerate(cases):
                with self.subTest(index=index):
                    with self.assertRaisesRegex(ValueError, message):
                        self._create(fixtures, root / f"invalid-{index}", intervals)

            output = root / "existing"
            output.mkdir()
            marker = output / "owner.txt"
            marker.write_text("do not replace", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                self._create(
                    fixtures,
                    output,
                    [(0.0, 1.0, "Valid but destination exists.")],
                )
            self.assertEqual(marker.read_text(encoding="utf-8"), "do not replace")
            dangling = root / "dangling-package"
            dangling.symlink_to(root / "missing-package")
            with self.assertRaises(FileExistsError):
                self._create(
                    fixtures,
                    dangling,
                    [(0.0, 1.0, "Dangling paths are owned and must not be replaced.")],
                )
            self.assertTrue(dangling.is_symlink())

    def test_resolver_rejects_incomplete_heard_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = self._fixtures(root)
            report = self._create(
                fixtures,
                root / "review",
                [(0.5, 1.5, "Hear all three references before choosing.")],
            )
            reviewed = self._reviewed_export(
                report,
                root / "incomplete-heard.reviewed.json",
                heard={
                    "source": True,
                    "candidate_a": True,
                    "candidate_b": False,
                },
            )

            with self.assertRaisesRegex(ValueError, "heard"):
                resolve_midi_ab_review(
                    reviewed,
                    root / "must-not-exist.json",
                    package_dir=report["out_dir"],
                )

    def test_resolver_rejects_tampered_review_evidence_and_input_midi(self) -> None:
        cases = (
            "public_audio",
            "audio_manifest",
            "answer_key",
            "input_midi",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixtures = self._fixtures(root)
                report = self._create(
                    fixtures,
                    root / "review",
                    [(0.5, 1.5, "Hash-pinned evidence fixture.")],
                )
                reviewed = self._reviewed_export(report, root / "reviewed.json")
                seed = _read(reviewed)
                if case == "public_audio":
                    audio = _record_path(
                        Path(report["out_dir"]),
                        seed["units"][0]["candidate_a"],
                    )
                    audio.write_bytes(audio.read_bytes() + b"tampered")
                    message = "audio changed"
                elif case == "audio_manifest":
                    manifest = Path(report["audio_manifest"])
                    manifest.write_bytes(manifest.read_bytes() + b" ")
                    message = "manifest changed"
                elif case == "answer_key":
                    answer_key = Path(report["answer_key"])
                    answer_key.write_bytes(answer_key.read_bytes() + b" ")
                    message = "answer key changed"
                else:
                    midi = fixtures["candidate_a"]
                    midi.write_bytes(midi.read_bytes() + b"tampered")
                    message = "MIDI changed"

                output = root / "must-not-exist.json"
                with self.assertRaisesRegex(ValueError, message):
                    resolve_midi_ab_review(
                        reviewed, output, package_dir=report["out_dir"]
                    )
                self.assertFalse(output.exists())

    def test_resolver_rejects_swapped_or_changed_public_unit_evidence(self) -> None:
        cases = (
            "swap_a_b",
            "cross_unit_audio",
            "interval",
            "focus",
            "geometry",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixtures = self._fixtures(root)
                report = self._create(
                    fixtures,
                    root / "review",
                    [
                        (0.5, 1.5, "First immutable focus."),
                        (2.0, 3.0, "Second immutable focus."),
                    ],
                )
                reviewed_path = self._reviewed_export(report, root / "reviewed.json")
                reviewed = _read(reviewed_path)
                first, second = reviewed["units"]
                if case == "swap_a_b":
                    first["candidate_a"], first["candidate_b"] = (
                        first["candidate_b"],
                        first["candidate_a"],
                    )
                elif case == "cross_unit_audio":
                    first["candidate_a"], second["candidate_a"] = (
                        second["candidate_a"],
                        first["candidate_a"],
                    )
                elif case == "interval":
                    first["start_seconds"] += 0.125
                elif case == "focus":
                    first["listening_focus"] = "Changed listening question."
                else:
                    first["frame_start"] += 1
                _write(reviewed_path, reviewed)

                with self.assertRaisesRegex(ValueError, "immutable package fields"):
                    resolve_midi_ab_review(
                        reviewed_path,
                        root / "must-not-exist.json",
                        package_dir=report["out_dir"],
                    )

    def test_resolver_rejects_reversed_mapping_and_bad_private_nonce(self) -> None:
        for case in ("reversed_mapping", "bad_nonce"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixtures = self._fixtures(root)
                with patch(
                    "sunofriend.midi_ab_review.secrets.token_bytes",
                    return_value=b"\x11" * 32,
                ):
                    report = self._create(
                        fixtures,
                        root / "review",
                        [(0.5, 1.5, "Private answer audit fixture.")],
                    )
                reviewed = self._reviewed_export(report, root / "reviewed.json")

                if case == "reversed_mapping":

                    def mutate(answer):
                        unit = answer["units"][0]
                        unit["candidate_a"], unit["candidate_b"] = (
                            unit["candidate_b"],
                            unit["candidate_a"],
                        )

                    message = "answer mapping"
                else:

                    def mutate(answer):
                        answer["blind_nonce_hex"] = (b"\x22" * 32).hex()

                    message = "nonce|assignment commitment"
                self._tamper_private_answer_and_repin(report, reviewed, mutate)

                with self.assertRaisesRegex(ValueError, message):
                    resolve_midi_ab_review(
                        reviewed,
                        root / "must-not-exist.json",
                        package_dir=report["out_dir"],
                    )

    def test_explicit_midi_offset_uses_candidate_time_and_rejects_bad_crops(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = self._fixtures(root)
            offset = 0.125
            with patch(
                "sunofriend.midi_ab_review.secrets.token_bytes",
                return_value=b"\x11" * 32,
            ):
                report = self._create(
                    fixtures,
                    root / "offset-review",
                    [(0.5, 1.5, "Verify the explicit common time origin.")],
                    midi_time_at_source_start_seconds=offset,
                )
            seed = _read(Path(report["seed"]))
            unit = seed["units"][0]
            self.assertEqual(
                seed["alignment_contract"]["midi_time_at_source_start_seconds"],
                offset,
            )
            self.assertFalse(seed["alignment_contract"]["time_shift_inferred"])
            self.assertEqual(unit["candidate_frame_start"], 5_000)
            self.assertEqual(unit["candidate_frame_end"], 13_000)
            answer = _read(Path(report["answer_key"]))
            identity = answer["units"][0]["candidate_a"]
            raw_record = next(
                row["raw_render"]
                for row in answer["inputs"]
                if row["identity"] == identity
            )
            raw = soundfile.read(raw_record["path"], dtype="float64", always_2d=True)[
                0
            ][5_000:13_000]
            public = soundfile.read(
                _record_path(Path(report["out_dir"]), unit["candidate_a"]),
                dtype="float64",
                always_2d=True,
            )[0]
            correlation = float(np.corrcoef(raw[:, 0], public[:, 0])[0, 1])
            self.assertGreater(correlation, 0.999999)

        invalid_offsets = (
            (0.00001, "sample frame"),
            (-1.0, "before candidate MIDI time zero"),
        )
        for index, (offset, message) in enumerate(invalid_offsets):
            with (
                self.subTest(offset=offset),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                fixtures = self._fixtures(root)
                output = root / f"invalid-offset-{index}"
                with self.assertRaisesRegex(ValueError, message):
                    self._create(
                        fixtures,
                        output,
                        [(0.5, 1.5, "Invalid alignment fixture.")],
                        midi_time_at_source_start_seconds=offset,
                    )
                self.assertFalse(output.exists())

    def test_rejects_near_silent_nonzero_render_below_minus_60_dbfs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = self._fixtures(root)
            output = root / "near-silent-review"

            with self.assertRaisesRegex(ValueError, "60|quiet|silent"):
                self._create(
                    fixtures,
                    output,
                    [(0.5, 1.5, "Reject inaudible nonzero candidates.")],
                    quiet_b_amplitude=0.0001,
                )
            self.assertFalse(output.exists())

    def test_rejects_silent_render_without_mutating_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = self._fixtures(root)
            originals = {name: _sha256(path) for name, path in fixtures.items()}
            output = root / "silent-review"

            with self.assertRaisesRegex(ValueError, "silent"):
                self._create(
                    fixtures,
                    output,
                    [(0.25, 1.25, "Silence must not be level matched.")],
                    silent_b=True,
                )

            self.assertEqual(
                {name: _sha256(path) for name, path in fixtures.items()}, originals
            )
            self.assertFalse((output / "midi_ab_review.json").exists())


def _write_midi(path: Path, *, pitch: int) -> None:
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(119), time=0))
    track.append(mido.Message("program_change", program=4, channel=0, time=0))
    track.append(mido.Message("note_on", note=pitch, velocity=96, channel=0, time=0))
    track.append(mido.Message("note_off", note=pitch, velocity=0, channel=0, time=480))
    midi.tracks.append(track)
    midi.save(path)


def _candidate_a_mapping(
    nonce: bytes, commitment: str, unit_ids: list[str]
) -> list[str]:
    commitment_bytes = bytes.fromhex(commitment)
    return [
        (
            "input_2"
            if hashlib.sha256(
                nonce + commitment_bytes + unit_id.encode("utf-8")
            ).digest()[0]
            % 2
            else "input_1"
        )
        for unit_id in unit_ids
    ]


def _browser_number_round_trip(value):
    """Model JSON.parse/JSON.stringify normalisation of integer-valued numbers."""

    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {
            key: _browser_number_round_trip(item) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_browser_number_round_trip(item) for item in value]
    return value


def _record_path(root: Path, record: dict) -> Path:
    path = Path(record["audio"])
    return path if path.is_absolute() else root / path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    unittest.main()
