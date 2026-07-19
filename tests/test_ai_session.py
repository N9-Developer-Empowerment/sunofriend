from __future__ import annotations

import json
import hashlib
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import soundfile

from sunofriend.ai_bakeoff import run_ai_transcription
from sunofriend.ai_benchmark import build_ai_performance_benchmark
from sunofriend.ai_session import MUSCRIPTOR_SESSION_SCHEMA, run_muscriptor_session
from sunofriend.ai_session_benchmark import (
    AI_SESSION_BENCHMARK_SCHEMA,
    build_ai_session_benchmark,
    write_ai_session_benchmark,
)
from sunofriend.ai_worker import (
    MUSCRIPTOR_SESSION_REQUEST_PERFORMANCE_SCHEMA,
)


_FAKE_TORCH = """
__version__ = "2.13.0-test"

class _MPS:
    @staticmethod
    def is_built():
        return False

    @staticmethod
    def is_available():
        return False

class _Backends:
    mps = _MPS()

backends = _Backends()

def from_numpy(value):
    return value
"""


_FAKE_EVENTS = """
class NoteStartEvent:
    def __init__(self, index, start_time, pitch, instrument):
        self.index = index
        self.start_time = start_time
        self.pitch = pitch
        self.instrument = instrument

class NoteEndEvent:
    def __init__(self, start_event, end_time):
        self.start_event_index = start_event.index
        self.start_event = start_event
        self.end_time = end_time

class ProgressEvent:
    def __init__(self, completed, total):
        self.completed = completed
        self.total = total
"""


_FAKE_MUSCRIPTOR = """
import json
import os
from pathlib import Path

from .events import NoteEndEvent, NoteStartEvent, ProgressEvent

def _increment(name):
    path = Path(os.environ["SUNOFRIEND_TEST_MUSCRIPTOR_COUNTER"])
    document = json.loads(path.read_text(encoding="utf-8"))
    document[name] += 1
    path.write_text(json.dumps(document), encoding="utf-8")
    return document[name]

class TranscriptionModel:
    @classmethod
    def load_model(cls, path, device):
        load_count = _increment("loads")
        if load_count == int(os.environ.get("SUNOFRIEND_TEST_FAIL_LOAD", "0")):
            raise RuntimeError("deliberate model-load failure")
        return cls()

    def transcribe(self, audio, instruments=None, **options):
        transcription_count = _increment("transcriptions")
        if transcription_count == int(
            os.environ.get("SUNOFRIEND_TEST_FAIL_TRANSCRIPTION", "0")
        ):
            raise RuntimeError("deliberate transcription failure")
        role = instruments[0] if instruments else "electric_piano"
        start = NoteStartEvent(1, 0.25, 64.0, role)
        yield start
        yield ProgressEvent(1, 1)
        yield NoteEndEvent(start, 0.75)
"""


class AISessionTests(unittest.TestCase):
    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _write_json(path: Path, document: dict) -> None:
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _complete_session(
        self, root: Path, fixture: dict[str, Path], *, name: str, repetitions: int = 2
    ) -> Path:
        session_root = root / name
        worker = Path(__file__).parents[1] / "src" / "sunofriend" / "ai_worker.py"
        with self._environment(fixture):
            run_muscriptor_session(
                audio_path=fixture["audio"],
                out_dir=session_root,
                checkpoint_path=fixture["checkpoint"],
                bpm=119.0,
                repetitions=repetitions,
                roles=("electric_piano",),
                start_seconds=0.0,
                end_seconds=1.0,
                options={
                    "device": "cpu",
                    "beam_size": 1,
                    "batch_size": 1,
                    "cfg_coef": 1.0,
                    "model_size": "small",
                    "prelude_forcing": False,
                },
                python=sys.executable,
                worker_path=worker,
            )
        return session_root

    def _refresh_run_record(self, session_root: Path, index: int) -> None:
        run_dir = session_root / f"repetition-{index:03d}"
        run_path = run_dir / "run.json"
        session_path = session_root / "session.json"
        session = json.loads(session_path.read_text(encoding="utf-8"))
        run_hash = self._sha256(run_path)
        session["runs"][index - 1]["run_json_sha256"] = run_hash
        session["attempts"][index - 1]["run_json_sha256"] = run_hash
        self._write_json(session_path, session)

    def _fixture(self, root: Path) -> dict[str, Path]:
        sample_rate = 8_000
        audio = root / "source.wav"
        times = np.arange(sample_rate, dtype=np.float32) / sample_rate
        soundfile.write(
            audio,
            0.1 * np.sin(2.0 * np.pi * 220.0 * times),
            sample_rate,
        )
        checkpoint = root / "model.safetensors"
        checkpoint.write_bytes(b"session-test-checkpoint")
        (root / "config.json").write_text(
            '{"model_type":"muscriptor","variant":"small","dim":768}',
            encoding="utf-8",
        )
        modules = root / "fake-modules"
        torch = modules / "torch"
        torch.mkdir(parents=True)
        (torch / "__init__.py").write_text(
            textwrap.dedent(_FAKE_TORCH), encoding="utf-8"
        )
        torch_dist = modules / "torch-2.13.0.dist-info"
        torch_dist.mkdir()
        (torch_dist / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: torch\nVersion: 2.13.0\n",
            encoding="utf-8",
        )
        muscriptor = modules / "muscriptor"
        muscriptor.mkdir()
        (muscriptor / "__init__.py").write_text(
            textwrap.dedent(_FAKE_MUSCRIPTOR), encoding="utf-8"
        )
        (muscriptor / "events.py").write_text(
            textwrap.dedent(_FAKE_EVENTS), encoding="utf-8"
        )
        dist = modules / "muscriptor-0.2.1.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: muscriptor\nVersion: 0.2.1\n",
            encoding="utf-8",
        )
        counter = root / "counter.json"
        counter.write_text(
            json.dumps({"loads": 0, "transcriptions": 0}), encoding="utf-8"
        )
        return {
            "audio": audio,
            "checkpoint": checkpoint,
            "modules": modules,
            "counter": counter,
        }

    def _environment(self, fixture: dict[str, Path]):
        old_pythonpath = os.environ.get("PYTHONPATH")
        pythonpath = str(fixture["modules"])
        if old_pythonpath:
            pythonpath += os.pathsep + old_pythonpath
        return mock.patch.dict(
            os.environ,
            {
                "PYTHONPATH": pythonpath,
                "SUNOFRIEND_TEST_MUSCRIPTOR_COUNTER": str(fixture["counter"]),
            },
        )

    def test_bounded_session_loads_once_and_matches_new_fresh_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixture(root)
            session_root = root / "session"
            fresh_root = root / "fresh"
            worker = Path(__file__).parents[1] / "src" / "sunofriend" / "ai_worker.py"
            options = {
                "device": "cpu",
                "beam_size": 1,
                "batch_size": 1,
                "cfg_coef": 1.0,
                "model_size": "small",
                "prelude_forcing": False,
            }
            with self._environment(fixture):
                session = run_muscriptor_session(
                    audio_path=fixture["audio"],
                    out_dir=session_root,
                    checkpoint_path=fixture["checkpoint"],
                    bpm=119.0,
                    repetitions=3,
                    roles=("electric_piano",),
                    start_seconds=0.0,
                    end_seconds=1.0,
                    options=options,
                    python=sys.executable,
                    worker_path=worker,
                )
                self.assertEqual(
                    json.loads(fixture["counter"].read_text(encoding="utf-8")),
                    {"loads": 1, "transcriptions": 3},
                )
                fresh = []
                for index in range(1, 3):
                    run_ai_transcription(
                        audio_path=fixture["audio"],
                        out_dir=fresh_root,
                        checkpoint_path=fixture["checkpoint"],
                        bpm=119.0,
                        roles=("electric_piano",),
                        start_seconds=0.0,
                        end_seconds=1.0,
                        options=options,
                        python=sys.executable,
                        worker_path=worker,
                        run_id=f"fresh-{index:03d}",
                    )
                    fresh.append(fresh_root / f"fresh-{index:03d}")

            self.assertEqual(session["schema"], MUSCRIPTOR_SESSION_SCHEMA)
            self.assertEqual(session["status"], "complete")
            self.assertEqual(session["repetitions_completed"], 3)
            self.assertEqual(
                json.loads(fixture["counter"].read_text(encoding="utf-8")),
                {"loads": 3, "transcriptions": 5},
            )
            hashes = []
            midi_hashes = []
            for index in range(1, 4):
                run_dir = session_root / f"repetition-{index:03d}"
                performance = json.loads(
                    (run_dir / "muscriptor.performance.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(
                    performance["schema"],
                    MUSCRIPTOR_SESSION_REQUEST_PERFORMANCE_SCHEMA,
                )
                self.assertNotIn("model_load", performance["timings_seconds"])
                self.assertEqual(
                    performance["session"]["warm_model_request"], index > 1
                )
                self.assertEqual(
                    performance["session"]["prior_completed_requests"], index - 1
                )
                run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
                self.assertIsNone(run["worker_subprocess_elapsed_seconds"])
                self.assertGreater(run["worker_request_elapsed_seconds"], 0)
                hashes.append(run["artifacts"]["candidate.json"]["sha256"])
                midi_hashes.append(run["artifacts"]["candidate.mid"]["sha256"])
            self.assertEqual(len(set(hashes)), 1)
            self.assertEqual(len(set(midi_hashes)), 1)
            fresh_run = json.loads(
                (fresh[0] / "run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(hashes[0], fresh_run["artifacts"]["candidate.json"]["sha256"])
            self.assertEqual(midi_hashes[0], fresh_run["artifacts"]["candidate.mid"]["sha256"])

            report = build_ai_session_benchmark(session_root, fresh)
            self.assertEqual(report["schema"], AI_SESSION_BENCHMARK_SCHEMA)
            self.assertEqual(report["request_count"], 3)
            self.assertEqual(report["warm_request_count"], 2)
            self.assertFalse(report["requests"][0]["warm_model_request"])
            self.assertTrue(report["requests"][1]["warm_model_request"])
            self.assertEqual(report["fresh_control"]["status"], "verified")
            self.assertTrue(report["fresh_control"]["same_candidate_json"])
            self.assertTrue(report["fresh_control"]["same_candidate_midi"])
            self.assertFalse(report["cache_regime"]["application_content_cache"])
            self.assertEqual(report["cache_regime"]["cache_hits"], 0)
            self.assertFalse(report["promotion_allowed"])
            encoded = json.dumps(report, sort_keys=True)
            self.assertNotIn(str(root), encoded)
            output = root / "session-benchmark.json"
            self.assertEqual(
                write_ai_session_benchmark(session_root, fresh, output), report
            )
            with self.assertRaises(FileExistsError):
                write_ai_session_benchmark(session_root, fresh, output)
            with self.assertRaisesRegex(ValueError, "fresh-process runs"):
                build_ai_performance_benchmark(
                    [
                        session_root / "repetition-001",
                        session_root / "repetition-002",
                    ]
                )

    def test_session_requires_a_fresh_output_and_bounded_repetition_count(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixture(root)
            existing = root / "existing"
            existing.mkdir()
            with self.assertRaisesRegex(ValueError, "between 2 and 20"):
                run_muscriptor_session(
                    audio_path=fixture["audio"],
                    out_dir=root / "invalid",
                    checkpoint_path=fixture["checkpoint"],
                    bpm=119.0,
                    repetitions=1,
                    python=sys.executable,
                )
            unsafe = root / "unsafe-role"
            with self.assertRaisesRegex(ValueError, "unknown MuScriptor instrument"):
                run_muscriptor_session(
                    audio_path=fixture["audio"],
                    out_dir=unsafe,
                    checkpoint_path=fixture["checkpoint"],
                    bpm=119.0,
                    repetitions=2,
                    roles=(str(root / "private-stem.wav"),),
                    python=sys.executable,
                )
            self.assertFalse(unsafe.exists())
            with self.assertRaises(FileExistsError):
                run_muscriptor_session(
                    audio_path=fixture["audio"],
                    out_dir=existing,
                    checkpoint_path=fixture["checkpoint"],
                    bpm=119.0,
                    repetitions=2,
                    python=sys.executable,
                )

    def test_failed_second_request_is_pinned_and_poisoned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixture(root)
            session_root = root / "failed-session"
            worker = Path(__file__).parents[1] / "src" / "sunofriend" / "ai_worker.py"
            options = {
                "device": "cpu",
                "beam_size": 1,
                "batch_size": 1,
                "cfg_coef": 1.0,
                "model_size": "small",
                "prelude_forcing": False,
            }
            with self._environment(fixture), mock.patch.dict(
                os.environ,
                {"SUNOFRIEND_TEST_FAIL_TRANSCRIPTION": "2"},
            ):
                with self.assertRaisesRegex(RuntimeError, "session failed"):
                    run_muscriptor_session(
                        audio_path=fixture["audio"],
                        out_dir=session_root,
                        checkpoint_path=fixture["checkpoint"],
                        bpm=119.0,
                        repetitions=3,
                        roles=("electric_piano",),
                        start_seconds=0.0,
                        end_seconds=1.0,
                        options=options,
                        python=sys.executable,
                        worker_path=worker,
                    )

            self.assertEqual(
                json.loads(fixture["counter"].read_text(encoding="utf-8")),
                {"loads": 1, "transcriptions": 2},
            )
            session = json.loads(
                (session_root / "session.json").read_text(encoding="utf-8")
            )
            self.assertEqual(session["status"], "failed")
            self.assertEqual(session["repetitions_attempted"], 2)
            self.assertEqual(session["repetitions_completed"], 1)
            self.assertEqual(
                [attempt["status"] for attempt in session["attempts"]],
                ["complete", "failed"],
            )
            self.assertTrue(session["cache_regime"]["model_loaded_once"])
            failed_run = session_root / "repetition-002"
            response = json.loads(
                (failed_run / "worker.response.json").read_text(encoding="utf-8")
            )
            run = json.loads((failed_run / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(response["status"], "failed")
            self.assertEqual(response["sequence"], 2)
            self.assertIn("worker.response.json", run["artifacts"])
            self.assertFalse((session_root / "repetition-003").exists())
            with self.assertRaisesRegex(ValueError, "completed session"):
                build_ai_session_benchmark(session_root)

    def test_failed_startup_does_not_claim_a_loaded_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixture(root)
            session_root = root / "failed-startup"
            worker = Path(__file__).parents[1] / "src" / "sunofriend" / "ai_worker.py"
            with self._environment(fixture), mock.patch.dict(
                os.environ,
                {"SUNOFRIEND_TEST_FAIL_LOAD": "1"},
            ):
                with self.assertRaisesRegex(RuntimeError, "session failed"):
                    run_muscriptor_session(
                        audio_path=fixture["audio"],
                        out_dir=session_root,
                        checkpoint_path=fixture["checkpoint"],
                        bpm=119.0,
                        repetitions=2,
                        roles=("electric_piano",),
                        options={"device": "cpu", "model_size": "small"},
                        python=sys.executable,
                        worker_path=worker,
                    )
            session = json.loads(
                (session_root / "session.json").read_text(encoding="utf-8")
            )
            self.assertFalse(session["cache_regime"]["model_loaded_once"])
            self.assertEqual(session["repetitions_attempted"], 0)
            self.assertFalse((session_root / "session.ready.json").exists())

            absent_root = root / "missing-worker-session"
            with self.assertRaises(FileNotFoundError):
                run_muscriptor_session(
                    audio_path=fixture["audio"],
                    out_dir=absent_root,
                    checkpoint_path=fixture["checkpoint"],
                    bpm=119.0,
                    repetitions=2,
                    python=sys.executable,
                    worker_path=root / "missing-worker.py",
                )
            self.assertFalse(absent_root.exists())

    def test_path_free_benchmark_rejects_private_field_injection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixture(root)
            session_root = self._complete_session(
                root, fixture, name="private-field-session"
            )
            run_dir = session_root / "repetition-001"
            performance_path = run_dir / "muscriptor.performance.json"
            performance = json.loads(performance_path.read_text(encoding="utf-8"))
            performance["session"]["private_path"] = str(root / "secret.wav")
            self._write_json(performance_path, performance)

            response_path = run_dir / "worker.response.json"
            response = json.loads(response_path.read_text(encoding="utf-8"))
            response["performance_sha256"] = self._sha256(performance_path)
            self._write_json(response_path, response)

            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            for name, path in (
                ("muscriptor.performance.json", performance_path),
                ("worker.response.json", response_path),
            ):
                run["artifacts"][name]["bytes"] = path.stat().st_size
                run["artifacts"][name]["sha256"] = self._sha256(path)
            self._write_json(run_path, run)
            self._refresh_run_record(session_root, 1)

            with self.assertRaisesRegex(ValueError, "reuse evidence"):
                build_ai_session_benchmark(session_root)

    def test_benchmark_rejects_coherent_provenance_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixture(root)
            session_root = self._complete_session(
                root, fixture, name="tampered-session"
            )
            session_path = session_root / "session.json"
            original_session = json.loads(session_path.read_text(encoding="utf-8"))

            unsafe_identity = json.loads(json.dumps(original_session))
            unsafe_identity["session_id"] = str(root / "private-session")
            self._write_json(session_path, unsafe_identity)
            with self.assertRaisesRegex(ValueError, "unsafe session_id"):
                build_ai_session_benchmark(session_root)

            contradictory = json.loads(json.dumps(original_session))
            contradictory["error"] = "hidden failure"
            self._write_json(session_path, contradictory)
            with self.assertRaisesRegex(ValueError, "snapshots contradict"):
                build_ai_session_benchmark(session_root)

            impossible_timing = json.loads(json.dumps(original_session))
            impossible_timing["parent_timings_seconds"]["request_phase"] = 0.000001
            self._write_json(session_path, impossible_timing)
            with self.assertRaisesRegex(ValueError, "parent timing"):
                build_ai_session_benchmark(session_root)

            unaccounted_timing = json.loads(json.dumps(original_session))
            unaccounted_timing["parent_timings_seconds"]["session_total"] += 1.0
            self._write_json(session_path, unaccounted_timing)
            with self.assertRaisesRegex(ValueError, "do not account for total"):
                build_ai_session_benchmark(session_root)

            self._write_json(session_path, original_session)
            run_dir = session_root / "repetition-001"
            raw_path = run_dir / "candidate.raw.json"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["private_unknown_field"] = "must not disappear"
            self._write_json(raw_path, raw)
            response_path = run_dir / "worker.response.json"
            response = json.loads(response_path.read_text(encoding="utf-8"))
            response["candidate_sha256"] = self._sha256(raw_path)
            self._write_json(response_path, response)
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            for name, path in (
                ("candidate.raw.json", raw_path),
                ("worker.response.json", response_path),
            ):
                run["artifacts"][name]["bytes"] = path.stat().st_size
                run["artifacts"][name]["sha256"] = self._sha256(path)
            self._write_json(run_path, run)
            self._refresh_run_record(session_root, 1)
            with self.assertRaisesRegex(ValueError, "differs from worker raw output"):
                build_ai_session_benchmark(session_root)

    def test_benchmark_requires_exact_startup_request_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixture(root)
            session_root = self._complete_session(
                root, fixture, name="request-byte-session"
            )
            for index in (1, 2):
                run_dir = session_root / f"repetition-{index:03d}"
                request_path = run_dir / "request.json"
                request = json.loads(request_path.read_text(encoding="utf-8"))
                request_path.write_text(
                    json.dumps(request, sort_keys=True) + "\n", encoding="utf-8"
                )
                response_path = run_dir / "worker.response.json"
                response = json.loads(response_path.read_text(encoding="utf-8"))
                response["request_sha256"] = self._sha256(request_path)
                self._write_json(response_path, response)
                run_path = run_dir / "run.json"
                run = json.loads(run_path.read_text(encoding="utf-8"))
                for name, path in (
                    ("request.json", request_path),
                    ("worker.response.json", response_path),
                ):
                    run["artifacts"][name]["bytes"] = path.stat().st_size
                    run["artifacts"][name]["sha256"] = self._sha256(path)
                self._write_json(run_path, run)
                self._refresh_run_record(session_root, index)

            with self.assertRaisesRegex(ValueError, "exact startup template"):
                build_ai_session_benchmark(session_root)


if __name__ == "__main__":
    unittest.main()
