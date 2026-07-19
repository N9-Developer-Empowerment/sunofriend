from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import mido
import numpy as np
import soundfile

from sunofriend.ai_bakeoff import run_ai_transcription
from sunofriend.ai_setting_compare import (
    build_ai_setting_comparison,
    write_ai_setting_comparison,
)


_WORKER = r"""
import argparse
import json
import math
from pathlib import Path

import soundfile

parser = argparse.ArgumentParser()
parser.add_argument("--request", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
request = json.load(open(args.request, encoding="utf-8"))
options = request["options"]
start = float(request["start_seconds"])
end = request["end_seconds"]
info = soundfile.info(request["audio_path"])
start_frame = round(start * info.samplerate)
end_frame = (
    info.frames
    if end is None
    else min(info.frames, round(float(end) * info.samplerate))
)
duration = (end_frame - start_frame) / info.samplerate
role = request["roles"][0] if request["roles"] else "electric_piano"
pitch = float(options.get("fixture_pitch", 64.0))
if options.get("fixture_change_with_beam") and int(options["beam_size"]) > 1:
    pitch += 2.0
if "different-output" in str(Path(args.output)):
    pitch += 3.0
onset = start + 5.0
if options.get("fixture_onset_shift_with_beam") and int(options["beam_size"]) > 1:
    onset += 0.05
execution = {
    "schema": "sunofriend.muscriptor-execution.v1",
    "model_size": options["model_size"],
    "model_config_sha256": options["model_config_sha256"],
    "decoding": {
        "strategy": "beam-search" if int(options["beam_size"]) > 1 else "greedy",
        "beam_size": options["beam_size"],
        "batch_size": options["batch_size"],
        "cfg_coef": options["cfg_coef"],
        "temperature": options["temperature"],
        "use_sampling": options["use_sampling"],
        "no_eos_is_ok": options["no_eos_is_ok"],
    },
    "chunking": {
        "seconds": options["chunk_seconds"],
        "policy": "independent-five-second-chunks",
        "prelude_forcing": options["prelude_forcing"],
        "prelude_forcing_supported": options["prelude_forcing_supported"],
    },
}
performance_path = Path(args.output).with_name("muscriptor.performance.json")
performance = {
    "schema": "sunofriend.muscriptor-performance.v1",
    "measurement_mode": "fresh-process",
    "device": options.get("device", "cpu"),
    "timings_seconds": {
        "audio_preparation": 0.1,
        "model_load": 2.0,
        "transcription": 3.0,
        "worker_total": 5.2,
        "time_to_first_note_start": 2.5,
        "time_to_first_completed_note": 2.7,
        "time_to_first_completed_chunk": 3.1,
    },
    "chunks": {
        "seconds": 5.0,
        "planned": math.ceil(duration / 5.0),
        "reported": math.ceil(duration / 5.0),
    },
    "note_count": 1,
    "peak_process_rss_bytes": 1000,
    "memory_scope": "process RSS high-water; accelerator allocation excluded",
    "clock": "time.perf_counter",
}
json.dump(performance, open(performance_path, "w", encoding="utf-8"))
candidate = {
    "schema": "sunofriend.ai-transcription-candidate.v1",
    "backend": "muscriptor",
    "model_version": "muscriptor-test-small",
    "notes": [{
        "start_seconds": onset,
        "end_seconds": onset + 0.5,
        "pitch": pitch,
        "confidence": None,
        "instrument": role,
        "velocity": None,
        "source_event_id": "setting-comparison-note",
    }],
    "warnings": [],
    "raw_artifacts": [performance_path.name],
    "metadata": {
        "checkpoint_sha256": options["model_sha256"],
        "device": options.get("device", "cpu"),
        "execution": execution,
        "excerpt": {
            "start_seconds": start,
            "end_seconds": end,
            "duration_seconds": duration,
        },
    },
}
json.dump(candidate, open(args.output, "w", encoding="utf-8"))
"""


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class AISettingComparisonTests(unittest.TestCase):
    def _fixture(self, root: Path) -> dict[str, Path]:
        sample_rate = 8_000
        audio = root / "source.wav"
        soundfile.write(
            audio, np.zeros(sample_rate * 16, dtype=np.float32), sample_rate
        )
        checkpoint = root / "model.safetensors"
        checkpoint.write_bytes(b"setting-comparison-test-checkpoint")
        (root / "config.json").write_text(
            '{"model_type":"muscriptor","variant":"small","dim":768}',
            encoding="utf-8",
        )
        worker = root / "worker.py"
        worker.write_text(textwrap.dedent(_WORKER), encoding="utf-8")
        return {
            "audio": audio,
            "checkpoint": checkpoint,
            "worker": worker,
            "runs": root / "runs",
        }

    def _run(
        self,
        fixture: dict[str, Path],
        run_id: str,
        *,
        beam_size: int,
        batch_size: int = 1,
        pitch: float = 64.0,
        change_with_beam: bool = False,
        onset_shift_with_beam: bool = False,
    ) -> Path:
        run_ai_transcription(
            audio_path=fixture["audio"],
            out_dir=fixture["runs"],
            checkpoint_path=fixture["checkpoint"],
            bpm=119.0,
            roles=("electric_piano",),
            start_seconds=0.0,
            end_seconds=15.0,
            options={
                "device": "cpu",
                "beam_size": beam_size,
                "batch_size": batch_size,
                "fixture_pitch": pitch,
                "fixture_change_with_beam": change_with_beam,
                "fixture_onset_shift_with_beam": onset_shift_with_beam,
            },
            python=sys.executable,
            worker_path=fixture["worker"],
            run_id=run_id,
        )
        run_dir = fixture["runs"] / run_id
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run["elapsed_seconds"] = 7.0
        run["worker_subprocess_elapsed_seconds"] = 6.0
        run["runtime"] = {
            "schema": "sunofriend.ai-runtime.v1",
            "platform": "testOS-1.0-arm64",
            "python": "3.12.10",
            "torch": {"version": "2.7.1"},
            "backends": {"muscriptor": {"version": "0.2.1"}},
            "python_executable": "/private/runtime/path-must-not-leak",
        }
        run_path.write_text(json.dumps(run), encoding="utf-8")
        return run_dir

    def _rewrite_run(self, run_dir: Path, mutate) -> None:
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        mutate(run)
        run_path.write_text(json.dumps(run), encoding="utf-8")

    def _refresh_artifact_record(self, run_dir: Path, name: str) -> None:
        path = run_dir / name

        def refresh(run: dict[str, object]) -> None:
            artifacts = run["artifacts"]
            assert isinstance(artifacts, dict)
            record = artifacts[name]
            assert isinstance(record, dict)
            record["bytes"] = path.stat().st_size
            record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()

        self._rewrite_run(run_dir, refresh)

    def _add_artifact(self, run_dir: Path, name: str, data: bytes) -> None:
        path = run_dir / name
        path.write_bytes(data)

        def add(run: dict[str, object]) -> None:
            artifacts = run["artifacts"]
            assert isinstance(artifacts, dict)
            artifacts[name] = {
                "path": name,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }

        self._rewrite_run(run_dir, add)

    def _add_execution_field(self, run_dir: Path, name: str, value: object) -> None:
        for candidate_name in ("candidate.raw.json", "candidate.json"):
            candidate_path = run_dir / candidate_name
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            candidate["metadata"]["execution"][name] = value
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            self._refresh_artifact_record(run_dir, candidate_name)
        self._rewrite_run(
            run_dir,
            lambda run: run["execution"].__setitem__(name, value),
        )

    def _set_times(self, run_dir: Path, *, started_at: str, completed_at: str) -> None:
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run["started_at"] = started_at
        run["completed_at"] = completed_at
        run_path.write_text(json.dumps(run), encoding="utf-8")

    def _make_legacy_fresh_manifest(self, run_dir: Path) -> None:
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        for field in (
            "worker_execution_mode",
            "worker_process_started_for_run",
            "inference_executed_for_run",
            "model_loaded_for_run",
            "application_cache",
            "worker_transport",
        ):
            run.pop(field, None)
        run_path.write_text(json.dumps(run), encoding="utf-8")

    def _four_runs(
        self,
        root: Path,
        *,
        changed: bool = False,
        onset_shift: bool = False,
    ) -> tuple[dict[str, Path], list[Path], list[Path]]:
        fixture = self._fixture(root)
        controls = [
            self._run(
                fixture,
                f"private-control-{index}",
                beam_size=1,
                change_with_beam=changed,
                onset_shift_with_beam=onset_shift,
            )
            for index in (1, 2)
        ]
        challengers = [
            self._run(
                fixture,
                f"private-challenger-{index}",
                beam_size=2,
                change_with_beam=changed,
                onset_shift_with_beam=onset_shift,
            )
            for index in (1, 2)
        ]
        for index, run in enumerate((*controls, *challengers)):
            second = index * 2
            self._set_times(
                run,
                started_at=f"2026-07-19T12:00:{second:02d}Z",
                completed_at=f"2026-07-19T12:00:{second + 1:02d}Z",
            )
        return fixture, controls, challengers

    def test_equal_outputs_are_verified_without_selecting_or_promoting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture, controls, challengers = self._four_runs(root)

            report = build_ai_setting_comparison(controls, challengers)

            self.assertEqual(report["schema"], "sunofriend.ai-setting-comparison.v1")
            outputs = report["comparison"]["outputs"]
            self.assertFalse(outputs["output_changed"])
            self.assertFalse(outputs["candidate_json_identical"])
            self.assertTrue(outputs["note_payload_identical"])
            self.assertTrue(outputs["candidate_midi_identical"])
            self.assertFalse(report["effects"]["promotion_allowed"])
            self.assertFalse(report["effects"]["selection_changed"])
            self.assertFalse(report["effects"]["raw_candidates_mutated"])
            self.assertEqual(report["effects"]["midi_notes_mutated"], 0)
            self.assertFalse(
                report["effects"]["listening_review_required_before_default_change"]
            )

    def test_changed_outputs_require_listening_but_do_not_promote(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture, controls, challengers = self._four_runs(root, changed=True)

            report = build_ai_setting_comparison(controls, challengers)

            outputs = report["comparison"]["outputs"]
            self.assertTrue(outputs["output_changed"])
            self.assertFalse(outputs["candidate_json_identical"])
            self.assertFalse(outputs["note_payload_identical"])
            self.assertFalse(outputs["candidate_midi_identical"])
            self.assertFalse(report["effects"]["promotion_allowed"])
            self.assertTrue(
                report["effects"]["listening_review_required_before_default_change"]
            )

    def test_rejects_fewer_than_two_runs_per_arm(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _fixture, controls, challengers = self._four_runs(Path(temporary))
            with self.assertRaisesRegex(ValueError, "at least two.*control"):
                build_ai_setting_comparison(controls[:1], challengers)
            with self.assertRaisesRegex(ValueError, "at least two.*challenger"):
                build_ai_setting_comparison(controls, challengers[:1])
            with self.assertRaisesRegex(ValueError, "at least two.*control"):
                build_ai_setting_comparison(str(controls[0]), challengers)
            with self.assertRaisesRegex(ValueError, "at least two.*challenger"):
                build_ai_setting_comparison(controls, challengers[0])

    def test_rejects_duplicate_and_cross_arm_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _fixture, controls, challengers = self._four_runs(Path(temporary))
            with self.assertRaisesRegex(ValueError, "control.*unique"):
                build_ai_setting_comparison([controls[0], controls[0]], challengers)
            with self.assertRaisesRegex(ValueError, "challenger.*unique"):
                build_ai_setting_comparison(controls, [challengers[0], challengers[0]])
            with self.assertRaisesRegex(ValueError, "arms.*overlap|both arms"):
                build_ai_setting_comparison(
                    controls,
                    [controls[0], challengers[0]],
                )

    def test_rejects_nonrepeatable_arm(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture, controls, challengers = self._four_runs(root)
            replacement = self._run(
                fixture,
                "private-control-different-output",
                beam_size=1,
            )
            self._set_times(
                replacement,
                started_at="2026-07-19T12:00:10Z",
                completed_at="2026-07-19T12:00:11Z",
            )

            with self.assertRaisesRegex(ValueError, "control.*repeat"):
                build_ai_setting_comparison([controls[0], replacement], challengers)

    def test_rejects_legacy_fresh_execution_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _fixture, controls, challengers = self._four_runs(Path(temporary))
            self._make_legacy_fresh_manifest(controls[0])

            with self.assertRaisesRegex(ValueError, "explicit.*current|legacy"):
                build_ai_setting_comparison(controls, challengers)

    def test_rejects_unknown_full_execution_field_difference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _fixture, controls, challengers = self._four_runs(Path(temporary))
            for challenger in challengers:
                self._add_execution_field(
                    challenger,
                    "future_decoder_policy",
                    "challenger-only",
                )

            with self.assertRaisesRegex(ValueError, "execution.*other than|outside"):
                build_ai_setting_comparison(controls, challengers)

    def test_rejects_resident_model_reuse_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _fixture, controls, challengers = self._four_runs(Path(temporary))
            self._rewrite_run(
                controls[0],
                lambda run: run.__setitem__("model_reused_from_prior_request", True),
            )

            with self.assertRaisesRegex(ValueError, "reused|fresh"):
                build_ai_setting_comparison(controls, challengers)

    def test_rejects_application_cache_artifact_evidence(self) -> None:
        for name in ("cache.entry.json", "cache.performance.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                _fixture, controls, challengers = self._four_runs(Path(temporary))
                self._add_artifact(controls[0], name, b"{}\n")

                with self.assertRaisesRegex(ValueError, "cache"):
                    build_ai_setting_comparison(controls, challengers)

    def test_nondefault_boundary_tolerance_is_reported_and_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _fixture, controls, challengers = self._four_runs(
                Path(temporary), onset_shift=True
            )

            report = build_ai_setting_comparison(
                controls,
                challengers,
                boundary_tolerance_ms=10.0,
            )

            boundary = report["comparison"]["five_second_boundaries"]
            overlap = report["comparison"]["outputs"]["same_pitch_label_onset_overlap"]
            self.assertEqual(boundary["tolerance_ms"], 10.0)
            self.assertEqual(overlap["tolerance_ms"], 10.0)
            self.assertEqual(overlap["matched_notes"], 0)

    def test_expression_midi_only_difference_requires_listening(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _fixture, controls, challengers = self._four_runs(Path(temporary))
            for challenger in challengers:
                midi_path = challenger / "candidate.expression.mid"
                midi = mido.MidiFile(midi_path)
                changed = False
                for track in midi.tracks:
                    for message in track:
                        if message.type == "note_on" and message.velocity > 0:
                            message.velocity = min(127, message.velocity + 7)
                            changed = True
                self.assertTrue(changed)
                midi.save(midi_path)
                self._refresh_artifact_record(challenger, "candidate.expression.mid")

            report = build_ai_setting_comparison(controls, challengers)
            outputs = report["comparison"]["outputs"]

            self.assertTrue(outputs["note_payload_identical"])
            self.assertTrue(outputs["candidate_midi_identical"])
            self.assertFalse(
                outputs["tracked_artifacts"]["candidate.expression.mid"]["identical"]
            )
            self.assertTrue(outputs["output_changed"])
            self.assertTrue(
                report["effects"]["listening_review_required_before_default_change"]
            )

    def test_rejects_wrong_beam_contract_and_extra_setting_difference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixture(root)
            wrong_controls = [
                self._run(fixture, f"wrong-control-{index}", beam_size=2)
                for index in (1, 2)
            ]
            wrong_challengers = [
                self._run(fixture, f"wrong-challenger-{index}", beam_size=1)
                for index in (1, 2)
            ]
            for index, run in enumerate((*wrong_controls, *wrong_challengers)):
                self._set_times(
                    run,
                    started_at=f"2026-07-19T12:01:{index * 2:02d}Z",
                    completed_at=f"2026-07-19T12:01:{index * 2 + 1:02d}Z",
                )
            with self.assertRaisesRegex(ValueError, "beam.*1.*2|control.*beam"):
                build_ai_setting_comparison(wrong_controls, wrong_challengers)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixture(root)
            controls = [
                self._run(fixture, f"control-{index}", beam_size=1, batch_size=1)
                for index in (1, 2)
            ]
            challengers = [
                self._run(fixture, f"challenger-{index}", beam_size=2, batch_size=2)
                for index in (1, 2)
            ]
            for index, run in enumerate((*controls, *challengers)):
                self._set_times(
                    run,
                    started_at=f"2026-07-19T12:02:{index * 2:02d}Z",
                    completed_at=f"2026-07-19T12:02:{index * 2 + 1:02d}Z",
                )
            with self.assertRaisesRegex(ValueError, "only.*beam|setting.*differ"):
                build_ai_setting_comparison(controls, challengers)

    def test_rejects_execution_windows_that_overlap_across_arms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _fixture, controls, challengers = self._four_runs(Path(temporary))
            self._set_times(
                controls[0],
                started_at="2026-07-19T12:00:00Z",
                completed_at="2026-07-19T12:00:03Z",
            )
            self._set_times(
                controls[1],
                started_at="2026-07-19T12:00:06Z",
                completed_at="2026-07-19T12:00:07Z",
            )
            self._set_times(
                challengers[0],
                started_at="2026-07-19T12:00:02Z",
                completed_at="2026-07-19T12:00:04Z",
            )
            self._set_times(
                challengers[1],
                started_at="2026-07-19T12:00:08Z",
                completed_at="2026-07-19T12:00:09Z",
            )

            with self.assertRaisesRegex(ValueError, "overlap"):
                build_ai_setting_comparison(controls, challengers)

    def test_write_is_fresh_path_free_and_does_not_mutate_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture, controls, challengers = self._four_runs(root, changed=True)
            before = _tree_hashes(fixture["runs"])
            output = root / "reports" / "setting-comparison.json"

            report = write_ai_setting_comparison(controls, challengers, output)

            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), report)
            self.assertEqual(_tree_hashes(fixture["runs"]), before)
            serialised = json.dumps(report, sort_keys=True)
            self.assertNotIn(str(root), serialised)
            self.assertNotIn("private-control", serialised)
            self.assertNotIn("private-challenger", serialised)
            self.assertNotIn("/private/runtime/path-must-not-leak", serialised)
            banned_keys = {
                "path",
                "audio_path",
                "model_path",
                "command",
                "run_id",
                "started_at",
                "completed_at",
            }

            def assert_path_free(value) -> None:
                if isinstance(value, dict):
                    self.assertTrue(banned_keys.isdisjoint(value))
                    for item in value.values():
                        assert_path_free(item)
                elif isinstance(value, list):
                    for item in value:
                        assert_path_free(item)

            assert_path_free(report)
            with self.assertRaises(FileExistsError):
                write_ai_setting_comparison(controls, challengers, output)
            with self.assertRaisesRegex(ValueError, "inside an input run"):
                write_ai_setting_comparison(
                    controls,
                    challengers,
                    controls[0] / "nested-report.json",
                )
            broken = root / "broken-report.json"
            broken.symlink_to(root / "missing-target.json")
            with self.assertRaises(FileExistsError):
                write_ai_setting_comparison(controls, challengers, broken)
            self.assertEqual(_tree_hashes(fixture["runs"]), before)

    def test_atomic_publish_race_keeps_competing_output_and_cleans_temporary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture, controls, challengers = self._four_runs(root)
            before = _tree_hashes(fixture["runs"])
            output = root / "reports" / "setting-comparison.json"
            competing = b'{"publisher":"other-process"}\n'

            def race(_source: str | Path, destination: str | Path) -> None:
                Path(destination).write_bytes(competing)
                raise FileExistsError(destination)

            with mock.patch("sunofriend.ai_setting_compare.os.link", side_effect=race):
                with self.assertRaises(FileExistsError):
                    write_ai_setting_comparison(controls, challengers, output)

            self.assertEqual(output.read_bytes(), competing)
            self.assertEqual(list(output.parent.glob(f".{output.name}.*.tmp")), [])
            self.assertEqual(_tree_hashes(fixture["runs"]), before)

    def test_report_is_invariant_to_input_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _fixture, controls, challengers = self._four_runs(Path(temporary))

            forward = build_ai_setting_comparison(controls, challengers)
            reversed_inputs = build_ai_setting_comparison(
                list(reversed(controls)), list(reversed(challengers))
            )

            self.assertEqual(forward, reversed_inputs)


if __name__ == "__main__":
    unittest.main()
