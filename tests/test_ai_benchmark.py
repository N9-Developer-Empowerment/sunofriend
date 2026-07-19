from __future__ import annotations

import hashlib
import json
import math
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import numpy as np
import soundfile

from sunofriend.ai_bakeoff import run_ai_transcription
from sunofriend.ai_benchmark import (
    AI_PERFORMANCE_BENCHMARK_SCHEMA,
    build_ai_performance_benchmark,
    write_ai_performance_benchmark,
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
duration = float(options.get("fixture_actual_duration", duration))
role = request["roles"][0] if request["roles"] else "electric_piano"
pitch = float(options.get("fixture_pitch", 64.0))
legacy = bool(options.get("fixture_legacy", False))
performance_path = Path(args.output).with_name("muscriptor.performance.json")
candidate = {
    "schema": "sunofriend.ai-transcription-candidate.v1",
    "backend": "muscriptor",
    "model_version": "muscriptor-test-small",
    "notes": [{
        "start_seconds": start + 5.0,
        "end_seconds": start + 5.5,
        "pitch": pitch,
        "confidence": None,
        "instrument": role,
        "velocity": None,
        "source_event_id": "benchmark-note",
    }],
    "warnings": [],
    "raw_artifacts": [] if legacy else [performance_path.name],
    "metadata": {
        "checkpoint_sha256": options["model_sha256"],
        "device": options.get("device", "cpu"),
        "excerpt": {
            "start_seconds": start,
            "end_seconds": end,
            "duration_seconds": duration,
        },
    },
}
if not legacy:
    scale = float(options.get("fixture_scale", 1.0))
    performance = {
        "schema": "sunofriend.muscriptor-performance.v1",
        "measurement_mode": "fresh-process",
        "device": options.get("device", "cpu"),
        "timings_seconds": {
            "audio_preparation": 0.1 * scale,
            "model_load": 2.0 * scale,
            "transcription": 3.0 * scale,
            "worker_total": 5.2 * scale,
            "time_to_first_note_start": 2.5 * scale,
            "time_to_first_completed_note": 2.7 * scale,
            "time_to_first_completed_chunk": 3.1 * scale,
        },
        "chunks": {
            "seconds": 5.0,
            "planned": math.ceil(duration / 5.0),
            "reported": math.ceil(duration / 5.0),
        },
        "note_count": 1,
        "peak_process_rss_bytes": int(1000 * scale),
        "memory_scope": "process RSS high-water; accelerator allocation excluded",
        "clock": "time.perf_counter",
    }
    json.dump(performance, open(performance_path, "w", encoding="utf-8"))
json.dump(candidate, open(args.output, "w", encoding="utf-8"))
"""


def _record(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


class AIPerformanceBenchmarkTests(unittest.TestCase):
    def _fixture(self, root: Path) -> dict[str, Path]:
        sample_rate = 8_000
        audio = root / "source.wav"
        soundfile.write(audio, np.zeros(sample_rate * 16, dtype=np.float32), sample_rate)
        alternate = root / "alternate.wav"
        soundfile.write(
            alternate,
            np.full(sample_rate * 16, 0.01, dtype=np.float32),
            sample_rate,
        )
        checkpoint = root / "model.safetensors"
        checkpoint.write_bytes(b"benchmark-test-checkpoint")
        (root / "config.json").write_text(
            '{"model_type":"muscriptor","variant":"small","dim":768}',
            encoding="utf-8",
        )
        worker = root / "worker.py"
        worker.write_text(textwrap.dedent(_WORKER), encoding="utf-8")
        return {
            "audio": audio,
            "alternate": alternate,
            "checkpoint": checkpoint,
            "worker": worker,
            "runs": root / "runs",
        }

    def _run(
        self,
        fixture: dict[str, Path],
        run_id: str,
        *,
        audio: Path | None = None,
        roles: tuple[str, ...] = ("electric_piano",),
        start_seconds: float = 0.0,
        end_seconds: float = 15.0,
        bpm: float = 119.0,
        device: str = "cpu",
        beam_size: int = 1,
        scale: float = 1.0,
        pitch: float = 64.0,
        legacy: bool = False,
        actual_duration: float | None = None,
    ) -> Path:
        run_ai_transcription(
            audio_path=audio or fixture["audio"],
            out_dir=fixture["runs"],
            checkpoint_path=fixture["checkpoint"],
            bpm=bpm,
            roles=roles,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            options={
                "device": device,
                "beam_size": beam_size,
                "fixture_scale": scale,
                "fixture_pitch": pitch,
                "fixture_legacy": legacy,
                **(
                    {"fixture_actual_duration": actual_duration}
                    if actual_duration is not None
                    else {}
                ),
            },
            python=sys.executable,
            worker_path=fixture["worker"],
            run_id=run_id,
        )
        run_dir = fixture["runs"] / run_id
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run["elapsed_seconds"] = 7.0 * scale
        run["worker_subprocess_elapsed_seconds"] = 6.0 * scale
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

    def _set_wall_times(
        self, run_dir: Path, *, pipeline: float, worker: float | None
    ) -> None:
        path = run_dir / "run.json"
        run = json.loads(path.read_text(encoding="utf-8"))
        run["elapsed_seconds"] = pipeline
        run["worker_subprocess_elapsed_seconds"] = worker
        path.write_text(json.dumps(run), encoding="utf-8")

    def _rewrite_performance(self, run_dir: Path, mutate) -> None:
        performance_path = run_dir / "muscriptor.performance.json"
        performance = json.loads(performance_path.read_text(encoding="utf-8"))
        mutate(performance)
        performance_path.write_text(json.dumps(performance), encoding="utf-8")
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run["artifacts"][performance_path.name] = _record(performance_path)
        run_path.write_text(json.dumps(run), encoding="utf-8")

    def _rewrite_run(self, run_dir: Path, mutate) -> None:
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        mutate(run)
        run_path.write_text(json.dumps(run), encoding="utf-8")

    def _strip_current_execution_fields(self, run: dict[str, object]) -> None:
        for field in (
            "worker_execution_mode",
            "worker_process_started_for_run",
            "inference_executed_for_run",
            "model_loaded_for_run",
            "model_reused_from_prior_request",
            "application_cache",
            "worker_transport",
        ):
            run.pop(field, None)

    def test_report_is_deterministic_path_free_and_aggregates_repetitions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixture(root)
            first = self._run(fixture, "benchmark-001", scale=1.0)
            second = self._run(fixture, "benchmark-002", scale=0.5)
            self._set_wall_times(first, pipeline=10.0, worker=8.0)
            self._set_wall_times(second, pipeline=5.0, worker=4.0)

            report = build_ai_performance_benchmark([second, first])
            repeated = build_ai_performance_benchmark([first, second])

            self.assertEqual(report, repeated)
            self.assertEqual(report["schema"], AI_PERFORMANCE_BENCHMARK_SCHEMA)
            self.assertEqual(report["repetition_count"], 2)
            self.assertEqual(
                report["runtime_profile"],
                {
                    "platform_architecture": "testOS-1.0-arm64",
                    "python_version": "3.12.10",
                    "torch_version": "2.7.1",
                    "muscriptor_version": "0.2.1",
                },
            )
            self.assertEqual(
                report["excerpt"],
                {
                    "requested_start_seconds": 0.0,
                    "requested_end_seconds": 15.0,
                    "actual_duration_seconds": 15.0,
                },
            )
            self.assertEqual(
                report["cache_regime"],
                {
                    "worker_process": "fresh-per-repetition",
                    "model_reused": False,
                    "application_content_cache": False,
                    "operating_system_file_cache": "uncontrolled",
                    "cold_start_claimed": False,
                },
            )
            self.assertEqual(report["first_vs_later_median_wall_ratio"], 2.0)
            self.assertEqual(
                report["execution_evidence"],
                {
                    "explicit_current_count": 2,
                    "legacy_v1_count": 0,
                    "legacy_policy": (
                        "A legacy v1 run is accepted only with a successful "
                        "non-empty subprocess command and no session or "
                        "application-cache evidence."
                    ),
                },
            )
            elapsed = report["aggregates"]["pipeline_elapsed_seconds"]
            self.assertEqual(elapsed, {"count": 2, "min": 5.0, "median": 7.5, "max": 10.0})
            model_load = report["aggregates"]["performance_model_load_seconds"]
            self.assertEqual(model_load, {"count": 2, "min": 1.0, "median": 1.5, "max": 2.0})
            transcription_rtf = report["aggregates"][
                "transcription_real_time_factor"
            ]
            self.assertEqual(
                transcription_rtf,
                {"count": 2, "min": 0.1, "median": 0.15, "max": 0.2},
            )
            self.assertTrue(report["repeatability"]["candidate_json"]["all_identical"])
            self.assertTrue(report["repeatability"]["candidate_midi"]["all_identical"])
            self.assertFalse(report["promotion_allowed"])
            self.assertIn("cannot promote", report["interpretation"])
            self.assertNotIn(str(root), json.dumps(report, sort_keys=True))
            self.assertNotIn(
                "/private/runtime/path-must-not-leak",
                json.dumps(report, sort_keys=True),
            )
            self.assertEqual(
                [row["run_id"] for row in report["repetitions"]],
                ["benchmark-001", "benchmark-002"],
            )
            self.assertTrue(
                all(row["started_at"].endswith("Z") for row in report["repetitions"])
            )
            self.assertTrue(
                all(row["performance_status"] == "verified" for row in report["repetitions"])
            )
            self.assertTrue(
                all(
                    row["execution_evidence"] == "explicit-current-fields"
                    for row in report["repetitions"]
                )
            )

            output = root / "reports" / "benchmark.json"
            written = write_ai_performance_benchmark([first, second], output)
            self.assertEqual(written, report)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), report)
            with self.assertRaises(FileExistsError):
                write_ai_performance_benchmark([first, second], output)

    def test_accepts_tightly_guarded_legacy_v1_fresh_execution_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            first = self._run(fixture, "benchmark-001")
            second = self._run(fixture, "benchmark-002")
            self._rewrite_run(first, self._strip_current_execution_fields)
            self._rewrite_run(second, self._strip_current_execution_fields)

            report = build_ai_performance_benchmark([first, second])

            self.assertEqual(report["execution_evidence"]["legacy_v1_count"], 2)
            self.assertEqual(
                {row["execution_evidence"] for row in report["repetitions"]},
                {"legacy-v1-fresh-subprocess"},
            )

    def test_rejects_partial_or_cache_like_legacy_execution_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            first = self._run(fixture, "benchmark-001")
            partial = self._run(fixture, "benchmark-002")
            self._rewrite_run(
                partial,
                lambda run: run.pop("inference_executed_for_run"),
            )
            with self.assertRaisesRegex(ValueError, "incomplete execution fields"):
                build_ai_performance_benchmark([first, partial])

        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            first = self._run(fixture, "benchmark-001")
            cache_like = self._run(fixture, "benchmark-002")

            def make_cache_like(run: dict[str, object]) -> None:
                self._strip_current_execution_fields(run)
                run["command"] = []
                run["exit_code"] = None
                artifacts = run["artifacts"]
                assert isinstance(artifacts, dict)
                artifacts["cache.performance.json"] = {
                    "path": "cache.performance.json",
                    "bytes": 1,
                    "sha256": "0" * 64,
                }

            self._rewrite_run(cache_like, make_cache_like)
            with self.assertRaisesRegex(ValueError, "cache-disabled fresh-process"):
                build_ai_performance_benchmark([first, cache_like])

    def test_rejects_explicit_model_reuse_or_cache_artifact_evidence(self) -> None:
        for reused_value in (True, None):
            with self.subTest(model_reused_from_prior_request=reused_value):
                with tempfile.TemporaryDirectory() as temporary:
                    fixture = self._fixture(Path(temporary))
                    first = self._run(fixture, "benchmark-001")
                    contradictory = self._run(fixture, "benchmark-002")
                    self._rewrite_run(
                        contradictory,
                        lambda run: run.__setitem__(
                            "model_reused_from_prior_request", reused_value
                        ),
                    )

                    with self.assertRaisesRegex(
                        ValueError, "cache-disabled fresh-process"
                    ):
                        build_ai_performance_benchmark([first, contradictory])

        for artifact_name in ("cache.entry.json", "cache.performance.json"):
            with self.subTest(cache_artifact=artifact_name):
                with tempfile.TemporaryDirectory() as temporary:
                    fixture = self._fixture(Path(temporary))
                    first = self._run(fixture, "benchmark-001")
                    contradictory = self._run(fixture, "benchmark-002")

                    def declare_cache_artifact(run: dict[str, object]) -> None:
                        artifacts = run["artifacts"]
                        assert isinstance(artifacts, dict)
                        artifacts[artifact_name] = {
                            "path": artifact_name,
                            "bytes": 1,
                            "sha256": "0" * 64,
                        }

                    self._rewrite_run(contradictory, declare_cache_artifact)
                    with self.assertRaisesRegex(
                        ValueError, "cache-disabled fresh-process"
                    ):
                        build_ai_performance_benchmark([first, contradictory])

    def test_rejects_fewer_or_duplicate_runs_and_duplicate_run_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            first = self._run(fixture, "benchmark-001")
            second = self._run(fixture, "benchmark-002")
            with self.assertRaisesRegex(ValueError, "at least two"):
                build_ai_performance_benchmark([first])
            with self.assertRaisesRegex(ValueError, "directories must be unique"):
                build_ai_performance_benchmark([first, first])

            path = second / "run.json"
            run = json.loads(path.read_text(encoding="utf-8"))
            run["run_id"] = "benchmark-001"
            path.write_text(json.dumps(run), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "run_id values must be unique"):
                build_ai_performance_benchmark([first, second])

    def test_orders_by_timezone_aware_started_at_before_nonchronological_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            late = self._run(fixture, "aaa-late")
            early = self._run(fixture, "zzz-early")
            self._rewrite_run(
                late,
                lambda run: run.update(
                    {
                        "started_at": "2026-07-19T12:00:02+01:00",
                        "completed_at": "2026-07-19T12:00:03+01:00",
                    }
                ),
            )
            self._rewrite_run(
                early,
                lambda run: run.update(
                    {
                        "started_at": "2026-07-19T10:59:59Z",
                        "completed_at": "2026-07-19T11:00:01Z",
                    }
                ),
            )

            report = build_ai_performance_benchmark([late, early])

            self.assertEqual(
                [row["run_id"] for row in report["repetitions"]],
                ["zzz-early", "aaa-late"],
            )
            self.assertEqual(
                [row["started_at"] for row in report["repetitions"]],
                ["2026-07-19T10:59:59Z", "2026-07-19T11:00:02Z"],
            )
            self.assertEqual(
                [row["completed_at"] for row in report["repetitions"]],
                ["2026-07-19T11:00:01Z", "2026-07-19T11:00:03Z"],
            )

            self._rewrite_run(
                early,
                lambda run: run.__setitem__(
                    "started_at", "2026-07-19T10:59:59"
                ),
            )
            with self.assertRaisesRegex(ValueError, "timezone-aware"):
                build_ai_performance_benchmark([late, early])

    def test_rejects_invalid_completion_times_and_overlapping_repetitions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            first = self._run(fixture, "benchmark-001")
            second = self._run(fixture, "benchmark-002")
            self._rewrite_run(
                second,
                lambda run: run.__setitem__(
                    "completed_at", "2026-07-19T12:00:00"
                ),
            )
            with self.assertRaisesRegex(ValueError, "completed_at.*timezone-aware"):
                build_ai_performance_benchmark([first, second])

        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            first = self._run(fixture, "benchmark-001")
            second = self._run(fixture, "benchmark-002")
            self._rewrite_run(
                second,
                lambda run: run.update(
                    {
                        "started_at": "2026-07-19T12:00:02Z",
                        "completed_at": "2026-07-19T12:00:01Z",
                    }
                ),
            )
            with self.assertRaisesRegex(ValueError, "precedes started_at"):
                build_ai_performance_benchmark([first, second])

        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            first = self._run(fixture, "benchmark-001")
            second = self._run(fixture, "benchmark-002")
            self._rewrite_run(
                first,
                lambda run: run.update(
                    {
                        "started_at": "2026-07-19T12:00:00Z",
                        "completed_at": "2026-07-19T12:00:03Z",
                    }
                ),
            )
            self._rewrite_run(
                second,
                lambda run: run.update(
                    {
                        "started_at": "2026-07-19T12:00:02Z",
                        "completed_at": "2026-07-19T12:00:04Z",
                    }
                ),
            )
            with self.assertRaisesRegex(ValueError, "repetitions overlap"):
                build_ai_performance_benchmark([first, second])

    def test_rejects_mismatched_source_excerpt_bpm_roles_device_and_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixture(root)
            baseline = self._run(fixture, "benchmark-000")
            cases = (
                (
                    "source",
                    self._run(
                        fixture,
                        "benchmark-source",
                        audio=fixture["alternate"],
                    ),
                    "same source hash",
                ),
                (
                    "excerpt",
                    self._run(
                        fixture,
                        "benchmark-excerpt",
                        start_seconds=1.0,
                        end_seconds=16.0,
                    ),
                    "same excerpt",
                ),
                (
                    "bpm",
                    self._run(fixture, "benchmark-bpm", bpm=120.0),
                    "same BPM",
                ),
                (
                    "roles",
                    self._run(fixture, "benchmark-role", roles=("electric_bass",)),
                    "same roles",
                ),
                (
                    "device",
                    self._run(fixture, "benchmark-device", device="mps"),
                    "same device",
                ),
                (
                    "execution",
                    self._run(fixture, "benchmark-execution", beam_size=2),
                    "same execution settings",
                ),
            )
            for label, other, message in cases:
                with self.subTest(label=label):
                    with self.assertRaisesRegex(ValueError, message):
                        build_ai_performance_benchmark([baseline, other])

    def test_requires_identical_complete_path_free_runtime_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            first = self._run(fixture, "benchmark-001")
            second = self._run(fixture, "benchmark-002")
            self._rewrite_run(
                second,
                lambda run: run["runtime"]["torch"].__setitem__(
                    "version", "2.8.0"
                ),
            )
            with self.assertRaisesRegex(ValueError, "same runtime profile"):
                build_ai_performance_benchmark([first, second])

            self._rewrite_run(
                second,
                lambda run: run["runtime"]["torch"].__setitem__("version", None),
            )
            with self.assertRaisesRegex(ValueError, "torch version"):
                build_ai_performance_benchmark([first, second])

    def test_uses_same_actual_eof_short_duration_for_rtf_and_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixture(root)
            eof_short = root / "eof-short.wav"
            soundfile.write(
                eof_short,
                np.zeros(8_000 * 9, dtype=np.float32),
                8_000,
            )
            first = self._run(fixture, "benchmark-001", audio=eof_short)
            second = self._run(
                fixture, "benchmark-002", audio=eof_short, scale=0.5
            )
            self._set_wall_times(first, pipeline=9.0, worker=6.0)
            self._set_wall_times(second, pipeline=4.5, worker=3.0)

            report = build_ai_performance_benchmark([first, second])

            self.assertEqual(
                report["excerpt"],
                {
                    "requested_start_seconds": 0.0,
                    "requested_end_seconds": 15.0,
                    "actual_duration_seconds": 9.0,
                },
            )
            self.assertEqual(
                [row["pipeline_real_time_factor"] for row in report["repetitions"]],
                [1.0, 0.5],
            )
            self.assertEqual(
                [row["chunks"]["planned"] for row in report["repetitions"]],
                [2, 2],
            )

    def test_rejects_candidate_duration_that_disagrees_with_source_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            first = self._run(fixture, "benchmark-001")
            corrupt = self._run(
                fixture,
                "benchmark-002",
                actual_duration=14.5,
            )

            with self.assertRaisesRegex(ValueError, "source.*frame"):
                build_ai_performance_benchmark([first, corrupt])

    def test_rejects_tampering_and_invalid_performance_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            first = self._run(fixture, "benchmark-001")
            second = self._run(fixture, "benchmark-002")

            performance_path = second / "muscriptor.performance.json"
            performance_path.write_bytes(performance_path.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "size/SHA-256"):
                build_ai_performance_benchmark([first, second])

        invalid_values = (-0.1, math.inf, math.nan, True, "slow")
        for index, invalid in enumerate(invalid_values):
            with self.subTest(invalid=repr(invalid)), tempfile.TemporaryDirectory() as temporary:
                fixture = self._fixture(Path(temporary))
                first = self._run(fixture, "benchmark-001")
                second = self._run(fixture, "benchmark-002")
                self._rewrite_performance(
                    second,
                    lambda value, invalid=invalid: value["timings_seconds"].__setitem__(
                        "model_load", invalid
                    ),
                )
                with self.assertRaisesRegex(ValueError, "finite and non-negative"):
                    build_ai_performance_benchmark([first, second])

    def test_rejects_incomplete_or_internally_inconsistent_performance(self) -> None:
        cases = (
            (
                "legacy inference field",
                lambda value: (
                    value["timings_seconds"].__setitem__(
                        "inference", value["timings_seconds"].pop("transcription")
                    )
                ),
                "unknown timing fields",
            ),
            (
                "missing first note",
                lambda value: value["timings_seconds"].__setitem__(
                    "time_to_first_note_start", None
                ),
                "note first timings are required",
            ),
            (
                "note timing order",
                lambda value: value["timings_seconds"].update(
                    {
                        "time_to_first_note_start": 3.0,
                        "time_to_first_completed_note": 2.0,
                    }
                ),
                "note first timings are not ordered",
            ),
            (
                "missing first chunk",
                lambda value: value["timings_seconds"].__setitem__(
                    "time_to_first_completed_chunk", None
                ),
                "first chunk timing is required",
            ),
            (
                "chunk seconds",
                lambda value: value["chunks"].__setitem__("seconds", 4.0),
                "chunk seconds disagree",
            ),
            (
                "planned chunks",
                lambda value: value["chunks"].__setitem__("planned", 4),
                "planned chunks disagree",
            ),
            (
                "too many reported chunks",
                lambda value: value["chunks"].__setitem__("reported", 4),
                "reported chunks exceed",
            ),
            (
                "incomplete reported chunks",
                lambda value: value["chunks"].__setitem__("reported", 2),
                "did not report all planned chunks",
            ),
            (
                "zero reported chunks",
                lambda value: value["chunks"].__setitem__("reported", 0),
                "must be a positive integer",
            ),
            (
                "stage sum",
                lambda value: value["timings_seconds"].__setitem__(
                    "model_load", 3.0
                ),
                "stage timings exceed worker_total",
            ),
            (
                "first time exceeds total",
                lambda value: value["timings_seconds"].__setitem__(
                    "time_to_first_completed_chunk", 6.0
                ),
                "timing exceeds worker_total",
            ),
            (
                "zero peak RSS",
                lambda value: value.__setitem__("peak_process_rss_bytes", 0),
                "must be a positive integer",
            ),
            (
                "missing clock",
                lambda value: value.pop("clock"),
                "clock is invalid",
            ),
            (
                "missing memory scope",
                lambda value: value.pop("memory_scope"),
                "memory scope is invalid",
            ),
        )
        for label, mutate, message in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                fixture = self._fixture(Path(temporary))
                first = self._run(fixture, "benchmark-001")
                second = self._run(fixture, "benchmark-002")
                self._rewrite_performance(second, mutate)
                with self.assertRaisesRegex(ValueError, message):
                    build_ai_performance_benchmark([first, second])

    def test_rejects_worker_total_beyond_parent_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            first = self._run(fixture, "benchmark-001")
            second = self._run(fixture, "benchmark-002")
            self._rewrite_run(
                second,
                lambda run: run.__setitem__(
                    "worker_subprocess_elapsed_seconds", 5.0
                ),
            )
            with self.assertRaisesRegex(ValueError, "parent-observed"):
                build_ai_performance_benchmark([first, second])

    def test_rejects_nonpositive_pipeline_or_worker_beyond_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            first = self._run(fixture, "benchmark-001")
            second = self._run(fixture, "benchmark-002")
            self._set_wall_times(second, pipeline=0.0, worker=6.0)
            with self.assertRaisesRegex(ValueError, "finite and positive"):
                build_ai_performance_benchmark([first, second])

        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            first = self._run(fixture, "benchmark-001")
            second = self._run(fixture, "benchmark-002")
            self._set_wall_times(second, pipeline=6.0, worker=6.1)
            with self.assertRaisesRegex(ValueError, "exceeds pipeline elapsed"):
                build_ai_performance_benchmark([first, second])

    def test_legacy_run_is_valid_and_repeatability_reports_differences(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary))
            current = self._run(fixture, "benchmark-001")
            legacy = self._run(fixture, "benchmark-002", legacy=True)
            different = self._run(fixture, "benchmark-003", pitch=65.0)

            mixed = build_ai_performance_benchmark([current, legacy])
            statuses = [row["performance_status"] for row in mixed["repetitions"]]
            self.assertEqual(statuses, ["verified", "unavailable"])
            self.assertIsNone(mixed["repetitions"][1]["performance"])
            self.assertEqual(
                mixed["aggregates"]["performance_model_load_seconds"]["count"],
                1,
            )

            changed = build_ai_performance_benchmark([current, different])
            self.assertFalse(changed["repeatability"]["candidate_json"]["all_identical"])
            self.assertFalse(changed["repeatability"]["candidate_midi"]["all_identical"])


if __name__ == "__main__":
    unittest.main()
