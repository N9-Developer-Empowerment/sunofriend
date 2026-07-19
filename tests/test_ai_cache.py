from __future__ import annotations

import json
import hashlib
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import soundfile

from sunofriend.ai_bakeoff import AIWorkerRunError, run_ai_transcription
from sunofriend.ai_benchmark import build_ai_performance_benchmark
from sunofriend.ai_cache import (
    AI_CACHE_NAMESPACE,
    publish_muscriptor_cache_entry,
)
from sunofriend.ai_cache_benchmark import (
    build_ai_cache_benchmark,
    write_ai_cache_benchmark,
)
from sunofriend.ai_matrix import build_ai_candidate_matrix


_WORKER = r"""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--request", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
counter = Path(__file__).with_name("worker-invocations.txt")
count = int(counter.read_text(encoding="utf-8")) if counter.exists() else 0
counter.write_text(str(count + 1), encoding="utf-8")
request = json.load(open(args.request, encoding="utf-8"))
performance_path = Path(args.output).with_name("muscriptor.performance.json")
performance = {
    "schema": "sunofriend.muscriptor-performance.v1",
    "measurement_mode": "fresh-process",
    "device": "cpu",
    "timings_seconds": {
        "audio_preparation": 0.01,
        "model_load": 0.02,
        "transcription": 0.03,
        "worker_total": 0.06,
        "time_to_first_note_start": 0.04,
        "time_to_first_completed_note": 0.05,
        "time_to_first_completed_chunk": 0.03,
    },
    "chunks": {"seconds": 5.0, "planned": 1, "reported": 1},
    "note_count": 1,
    "peak_process_rss_bytes": 123456,
    "memory_scope": "process RSS high-water; accelerator allocation excluded",
    "clock": "time.perf_counter",
}
json.dump(performance, open(performance_path, "w", encoding="utf-8"))
candidate = {
    "schema": "sunofriend.ai-transcription-candidate.v1",
    "backend": "muscriptor",
    "model_version": "muscriptor-0.2.1/" + request["options"]["model_sha256"][:12],
    "notes": [{
        "start_seconds": 0.25,
        "end_seconds": 0.75,
        "pitch": 64.25,
        "confidence": None,
        "instrument": request["roles"][0] if request["roles"] else "electric_piano",
        "velocity": None,
        "source_event_id": "cache-note-0",
    }],
    "warnings": [],
    "raw_artifacts": ["muscriptor.performance.json"],
    "metadata": {
        "checkpoint_sha256": request["options"]["model_sha256"],
        "device": "cpu",
        "instruments": request["roles"],
        "source_sample_rate": 8000,
        "progress": [],
        "velocity_policy": "not supplied by MuScriptor; preserved as null",
        "excerpt": {
            "start_seconds": request["start_seconds"],
            "end_seconds": request["end_seconds"],
            "duration_seconds": (
                (request["end_seconds"] if request["end_seconds"] is not None else 1.0)
                - request["start_seconds"]
            ),
        },
        "execution": {
            "schema": "sunofriend.muscriptor-execution.v1",
            "model_size": request["options"]["model_size"],
            "model_config_sha256": request["options"]["model_config_sha256"],
            "decoding": {
                "strategy": (
                    "sampling"
                    if request["options"]["use_sampling"]
                    else (
                        "beam-search"
                        if request["options"]["beam_size"] > 1
                        else "greedy"
                    )
                ),
                "beam_size": request["options"]["beam_size"],
                "batch_size": request["options"]["batch_size"],
                "cfg_coef": request["options"]["cfg_coef"],
                "temperature": request["options"]["temperature"],
                "use_sampling": request["options"]["use_sampling"],
                "no_eos_is_ok": request["options"]["no_eos_is_ok"],
            },
            "chunking": {
                "seconds": request["options"]["chunk_seconds"],
                "policy": "independent-five-second-chunks",
                "prelude_forcing": False,
                "prelude_forcing_supported": False,
            },
        },
    },
}
json.dump(candidate, open(args.output, "w", encoding="utf-8"))
"""


def _runtime() -> dict[str, object]:
    return {
        "schema": "sunofriend.ai-runtime.v1",
        "python": "3.12.10",
        "platform": "macOS-15-arm64",
        "runtime_ready": True,
        "packages": {
            "einops": "0.8.1",
            "numpy": "2.2.0",
            "soundfile": "0.13.1",
            "safetensors": "0.5.3",
        },
        "torch": {
            "version": "2.13.0",
            "mps_built": True,
            "mps_available": False,
        },
        "torch_ready": True,
        "preferred_device": "cpu",
        "backends": {"muscriptor": {"software_ready": True, "version": "0.2.1"}},
    }


class AICacheTests(unittest.TestCase):
    def _fixture(self, root: Path) -> dict[str, Path]:
        sample_rate = 8_000
        audio = root / "source.wav"
        times = np.arange(sample_rate, dtype=np.float32) / sample_rate
        soundfile.write(audio, 0.2 * np.sin(2 * np.pi * 220 * times), sample_rate)
        checkpoint = root / "model.safetensors"
        checkpoint.write_bytes(b"cache checkpoint")
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
            "cache": root / "private-cache",
            "runs": root / "runs",
        }

    def _run(
        self,
        fixture: dict[str, Path],
        run_id: str,
        *,
        audio: Path | None = None,
        checkpoint: Path | None = None,
        worker: Path | None = None,
        bpm: float = 119,
        roles: tuple[str, ...] = ("electric_piano",),
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
        runtime: dict[str, object] | None = None,
        options: dict[str, object] | None = None,
    ) -> dict[str, object]:
        requested_options: dict[str, object] = {
            "device": "cpu",
            "beam_size": 1,
            "batch_size": 1,
            "cfg_coef": 1.0,
            "model_size": "small",
            "prelude_forcing": False,
        }
        requested_options.update(options or {})
        with mock.patch(
            "sunofriend.ai_bakeoff.collect_ai_runtime_fingerprint",
            return_value=runtime or _runtime(),
        ):
            return run_ai_transcription(
                audio_path=audio or fixture["audio"],
                out_dir=fixture["runs"],
                checkpoint_path=checkpoint or fixture["checkpoint"],
                bpm=bpm,
                roles=roles,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                options=requested_options,
                python=sys.executable,
                worker_path=worker or fixture["worker"],
                application_cache_dir=fixture["cache"],
                run_id=run_id,
            )

    @staticmethod
    def _rewrite_run_artifact(run_dir: Path, label: str) -> None:
        artifact = run_dir / label
        manifest_path = run_dir / "run.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"][label]["bytes"] = artifact.stat().st_size
        manifest["artifacts"][label]["sha256"] = hashlib.sha256(
            artifact.read_bytes()
        ).hexdigest()
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _cache_entry_path(fixture: dict[str, Path], key: str) -> Path:
        return fixture["cache"] / AI_CACHE_NAMESPACE / "sha256" / key[:2] / key

    def test_miss_stores_and_exact_hits_start_no_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            miss = self._run(fixture, "cache-miss")
            hit_1 = self._run(fixture, "cache-hit-1")
            self._run(fixture, "cache-hit-2")

            self.assertEqual(
                miss["application_cache"]["application_cache_status"],
                "miss-stored",
            )
            self.assertEqual(
                hit_1["application_cache"]["application_cache_status"],
                "verified-hit",
            )
            self.assertTrue(miss["inference_executed_for_run"])
            self.assertTrue(miss["worker_process_started_for_run"])
            self.assertFalse(hit_1["inference_executed_for_run"])
            self.assertFalse(hit_1["worker_process_started_for_run"])
            self.assertFalse(hit_1["model_loaded_for_run"])
            self.assertEqual(hit_1["command"], [])
            self.assertIsNone(hit_1["exit_code"])
            self.assertEqual(
                fixture["worker"].with_name("worker-invocations.txt").read_text(),
                "1",
            )

            for name in (
                "candidate.raw.json",
                "muscriptor.performance.json",
                "candidate.json",
                "candidate.mid",
                "candidate.expression.mid",
                "cache.entry.json",
            ):
                expected = (fixture["runs"] / "cache-miss" / name).read_bytes()
                self.assertEqual(
                    (fixture["runs"] / "cache-hit-1" / name).read_bytes(), expected
                )
                self.assertEqual(
                    (fixture["runs"] / "cache-hit-2" / name).read_bytes(), expected
                )

            event = json.loads(
                (fixture["runs"] / "cache-hit-1" / "cache.performance.json").read_text()
            )
            self.assertTrue(event["application_cache_hit"])
            self.assertFalse(event["inference_executed_for_run"])
            self.assertTrue(event["run_origin_performance_matches_entry"])
            self.assertFalse(event["muscriptor_performance_is_current_run_inference"])

            key = hit_1["application_cache"]["key_sha256"]
            cached_raw = (
                fixture["cache"]
                / AI_CACHE_NAMESPACE
                / "sha256"
                / key[:2]
                / key
                / "payload"
                / "candidate.raw.json"
            )
            hit_raw = fixture["runs"] / "cache-hit-1" / "candidate.raw.json"
            self.assertNotEqual(cached_raw.stat().st_ino, hit_raw.stat().st_ino)

            report = build_ai_cache_benchmark(
                fixture["runs"] / "cache-miss",
                [
                    fixture["runs"] / "cache-hit-1",
                    fixture["runs"] / "cache-hit-2",
                ],
            )
            self.assertEqual(report["status"], "verified")
            self.assertEqual(report["hit_count"], 2)
            self.assertTrue(report["repeatability"]["candidate_raw"]["all_identical"])
            self.assertTrue(report["repeatability"]["candidate_midi"]["all_identical"])
            self.assertFalse(report["cache_regime"]["resident_model_reused"])
            self.assertNotIn(str(Path(directory)), json.dumps(report, sort_keys=True))

    def test_identical_bytes_at_new_source_and_checkpoint_paths_hit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self._fixture(root)
            self._run(fixture, "origin")
            moved = root / "moved"
            moved.mkdir()
            audio = moved / "renamed.wav"
            checkpoint = moved / "renamed.safetensors"
            worker = moved / "renamed-worker.py"
            shutil.copyfile(fixture["audio"], audio)
            shutil.copyfile(fixture["checkpoint"], checkpoint)
            shutil.copyfile(root / "config.json", moved / "config.json")
            shutil.copyfile(fixture["worker"], worker)

            hit = self._run(
                fixture,
                "moved-hit",
                audio=audio,
                checkpoint=checkpoint,
                worker=worker,
            )
            self.assertEqual(
                hit["application_cache"]["application_cache_status"], "verified-hit"
            )
            self.assertFalse(worker.with_name("worker-invocations.txt").exists())
            self.assertEqual(
                fixture["worker"].with_name("worker-invocations.txt").read_text(),
                "1",
            )

    def test_bpm_and_ordered_roles_are_bound_to_the_exact_cache_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            first = self._run(
                fixture, "first", roles=("electric_piano", "electric_bass")
            )
            bpm_change = self._run(
                fixture,
                "bpm-change",
                bpm=120,
                roles=("electric_piano", "electric_bass"),
            )
            role_order = self._run(
                fixture,
                "role-order",
                roles=("electric_bass", "electric_piano"),
            )
            keys = {
                first["application_cache"]["key_sha256"],
                bpm_change["application_cache"]["key_sha256"],
                role_order["application_cache"]["key_sha256"],
            }
            self.assertEqual(len(keys), 3)
            self.assertEqual(
                fixture["worker"].with_name("worker-invocations.txt").read_text(),
                "3",
            )

    def test_content_excerpt_and_decode_changes_each_miss_the_exact_cache(self) -> None:
        cases: tuple[tuple[str, dict[str, object], dict[str, object]], ...] = (
            ("source", {"mutation": "source"}, {}),
            ("checkpoint", {"mutation": "checkpoint"}, {}),
            ("config", {"mutation": "config"}, {}),
            ("worker", {"mutation": "worker"}, {}),
            (
                "excerpt",
                {},
                {"start_seconds": 0.1, "end_seconds": 0.9},
            ),
            ("beam-size", {}, {"options": {"beam_size": 2}}),
            ("batch-size", {}, {"options": {"batch_size": 2}}),
            ("cfg-coef", {}, {"options": {"cfg_coef": 1.25}}),
            ("temperature", {}, {"options": {"temperature": 0.8}}),
            ("eos", {}, {"options": {"no_eos_is_ok": False}}),
        )
        for label, setup, request_changes in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                fixture = self._fixture(Path(directory))
                origin = self._run(fixture, "origin")
                mutation = setup.get("mutation")
                if mutation == "source":
                    sample_rate = 8_000
                    times = np.arange(sample_rate, dtype=np.float32) / sample_rate
                    soundfile.write(
                        fixture["audio"],
                        0.2 * np.sin(2 * np.pi * 330 * times),
                        sample_rate,
                    )
                elif mutation == "checkpoint":
                    fixture["checkpoint"].write_bytes(b"different checkpoint")
                elif mutation == "config":
                    config = fixture["checkpoint"].with_name("config.json")
                    config.write_text(
                        config.read_text(encoding="utf-8") + "\n",
                        encoding="utf-8",
                    )
                elif mutation == "worker":
                    fixture["worker"].write_text(
                        fixture["worker"].read_text(encoding="utf-8")
                        + "\n# changed worker identity\n",
                        encoding="utf-8",
                    )
                changed = self._run(fixture, "changed", **request_changes)
                self.assertNotEqual(
                    origin["application_cache"]["key_sha256"],
                    changed["application_cache"]["key_sha256"],
                )
                self.assertEqual(
                    changed["application_cache"]["application_cache_status"],
                    "miss-stored",
                )

    def test_corrupt_entry_fails_closed_without_worker_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            miss = self._run(fixture, "origin")
            key = miss["application_cache"]["key_sha256"]
            performance = (
                fixture["cache"]
                / AI_CACHE_NAMESPACE
                / "sha256"
                / key[:2]
                / key
                / "payload"
                / "muscriptor.performance.json"
            )
            performance.write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(AIWorkerRunError, "artifact hash changed"):
                self._run(fixture, "corrupt-hit")
            self.assertEqual(
                fixture["worker"].with_name("worker-invocations.txt").read_text(),
                "1",
            )
            failed = json.loads(
                (fixture["runs"] / "corrupt-hit" / "run.json").read_text()
            )
            self.assertEqual(failed["status"], "failed")
            self.assertFalse(failed["worker_process_started_for_run"])
            self.assertEqual(
                failed["worker_execution_mode"], "application-cache-read-failed"
            )
            self.assertEqual(failed["command"], [])
            event = json.loads(
                (fixture["runs"] / "corrupt-hit" / "cache.performance.json").read_text()
            )
            self.assertEqual(event["application_cache_status"], "failed")
            self.assertFalse(event["fallback_to_inference_on_invalid_entry"])
            self.assertFalse(event["inference_executed_for_run"])
            self.assertFalse(event["muscriptor_performance_is_current_run_inference"])

    def test_cache_modes_are_not_admitted_to_fresh_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            self._run(fixture, "origin")
            self._run(fixture, "hit")
            self._run(fixture, "hit-2")
            self._run(fixture, "second-miss", bpm=120)
            with self.assertRaisesRegex(ValueError, "cache-disabled fresh-process"):
                build_ai_performance_benchmark(
                    [
                        fixture["runs"] / "origin",
                        fixture["runs"] / "second-miss",
                    ]
                )
            with self.assertRaisesRegex(ValueError, "cache-disabled fresh-process"):
                build_ai_performance_benchmark(
                    [fixture["runs"] / "hit", fixture["runs"] / "hit-2"]
                )
            matrix = build_ai_candidate_matrix(
                [("M3-cache-miss", fixture["runs"] / "origin")]
            )
            self.assertEqual(matrix["lanes"][0]["lane"], "M3-cache-miss")
            with self.assertRaisesRegex(ValueError, "application-cache hit"):
                build_ai_candidate_matrix([("M3-cache-hit", fixture["runs"] / "hit")])

    def test_symbolic_link_entry_is_rejected_without_worker_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            miss = self._run(fixture, "origin")
            key = miss["application_cache"]["key_sha256"]
            cached = (
                fixture["cache"]
                / AI_CACHE_NAMESPACE
                / "sha256"
                / key[:2]
                / key
                / "payload"
                / "muscriptor.performance.json"
            )
            cached.unlink()
            cached.symlink_to(
                fixture["runs"] / "origin" / "muscriptor.performance.json"
            )

            with self.assertRaisesRegex(AIWorkerRunError, "missing or linked"):
                self._run(fixture, "linked-hit")
            self.assertEqual(
                fixture["worker"].with_name("worker-invocations.txt").read_text(),
                "1",
            )

    def test_failed_inference_never_populates_the_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            fixture["worker"].write_text("raise SystemExit(7)\n", encoding="utf-8")
            with self.assertRaisesRegex(AIWorkerRunError, "status 7"):
                self._run(fixture, "failed-origin")
            self.assertEqual(list(fixture["cache"].rglob("entry.json")), [])
            run = json.loads(
                (fixture["runs"] / "failed-origin" / "run.json").read_text(
                    encoding="utf-8"
                )
            )
            event = json.loads(
                (
                    fixture["runs"]
                    / "failed-origin"
                    / "cache.performance.json"
                ).read_text(encoding="utf-8")
            )
            self.assertTrue(run["worker_process_started_for_run"])
            self.assertFalse(run["inference_executed_for_run"])
            self.assertFalse(run["model_loaded_for_run"])
            self.assertTrue(event["worker_process_started_for_run"])
            self.assertFalse(event["inference_executed_for_run"])
            self.assertFalse(event["model_loaded_for_run"])

    def test_cache_benchmark_requires_untampered_evidence_and_fresh_output(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            self._run(fixture, "origin")
            self._run(fixture, "hit-1")
            self._run(fixture, "hit-2")
            output = Path(directory) / "report.json"
            report = write_ai_cache_benchmark(
                fixture["runs"] / "origin",
                [fixture["runs"] / "hit-1", fixture["runs"] / "hit-2"],
                output,
            )
            self.assertEqual(report["status"], "verified")
            self.assertNotIn("run_id", report["miss"])
            self.assertTrue(
                all("run_id" not in hit for hit in report["hits"])
            )
            with self.assertRaises(FileExistsError):
                write_ai_cache_benchmark(
                    fixture["runs"] / "origin",
                    [fixture["runs"] / "hit-1", fixture["runs"] / "hit-2"],
                    output,
                )

            event_path = fixture["runs"] / "hit-2" / "cache.performance.json"
            event = json.loads(event_path.read_text())
            event["inference_executed_for_run"] = True
            event_path.write_text(json.dumps(event), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash changed"):
                build_ai_cache_benchmark(
                    fixture["runs"] / "origin",
                    [fixture["runs"] / "hit-1", fixture["runs"] / "hit-2"],
                )

    def test_cache_benchmark_regenerates_midi_and_checks_timing_nesting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            self._run(fixture, "origin")
            self._run(fixture, "hit-1")
            self._run(fixture, "hit-2")
            hit_2 = fixture["runs"] / "hit-2"
            midi = hit_2 / "candidate.mid"
            midi.write_bytes(midi.read_bytes() + b"coherent-manifest-tamper")
            self._rewrite_run_artifact(hit_2, "candidate.mid")
            with self.assertRaisesRegex(ValueError, "MIDI is not reproducible"):
                build_ai_cache_benchmark(
                    fixture["runs"] / "origin",
                    [fixture["runs"] / "hit-1", hit_2],
                )

        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            self._run(fixture, "origin")
            self._run(fixture, "hit-1")
            self._run(fixture, "hit-2")
            hit_2 = fixture["runs"] / "hit-2"
            event_path = hit_2 / "cache.performance.json"
            event = json.loads(event_path.read_text(encoding="utf-8"))
            event["timings_seconds"]["identity_and_preflight"] = (
                event["timings_seconds"]["pipeline_before_final_evidence"] + 10.0
            )
            event_path.write_text(
                json.dumps(event, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self._rewrite_run_artifact(hit_2, "cache.performance.json")
            with self.assertRaisesRegex(ValueError, "serial stages exceed"):
                build_ai_cache_benchmark(
                    fixture["runs"] / "origin",
                    [fixture["runs"] / "hit-1", hit_2],
                )

    def test_runtime_dependencies_change_key_without_requiring_torchaudio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            baseline = _runtime()
            first = self._run(fixture, "origin", runtime=baseline)
            exact_hit = self._run(fixture, "hit", runtime=baseline)
            safetensors_change = json.loads(json.dumps(baseline))
            safetensors_change["packages"]["safetensors"] = "0.6.0"
            second = self._run(
                fixture,
                "safetensors-change",
                runtime=safetensors_change,
            )
            einops_change = json.loads(json.dumps(baseline))
            einops_change["packages"]["einops"] = "0.9.0"
            third = self._run(fixture, "einops-change", runtime=einops_change)

            self.assertEqual(
                exact_hit["application_cache"]["application_cache_status"],
                "verified-hit",
            )
            keys = {
                first["application_cache"]["key_sha256"],
                second["application_cache"]["key_sha256"],
                third["application_cache"]["key_sha256"],
            }
            self.assertEqual(len(keys), 3)
            self.assertEqual(
                fixture["worker"].with_name("worker-invocations.txt").read_text(),
                "3",
            )

    def test_concurrent_publication_keeps_one_identical_winner_and_no_debris(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self._fixture(root)
            origin_run = self._run(fixture, "origin")
            key = origin_run["application_cache"]["key_sha256"]
            entry_dir = self._cache_entry_path(fixture, key)
            entry_document = json.loads(
                (entry_dir / "entry.json").read_text(encoding="utf-8")
            )
            identity = {
                "scope": entry_document["scope"],
                "key_sha256": entry_document["key_sha256"],
                "document": entry_document["key"],
            }
            race_run = root / "race-run"
            race_run.mkdir()
            shutil.copyfile(
                fixture["runs"] / "origin" / "candidate.raw.json",
                race_run / "candidate.raw.json",
            )
            performance = json.loads(
                (fixture["runs"] / "origin" / "muscriptor.performance.json").read_text()
            )
            performance["timings_seconds"]["transcription"] = 0.031
            (race_run / "muscriptor.performance.json").write_text(
                json.dumps(performance), encoding="utf-8"
            )
            winner, published = publish_muscriptor_cache_entry(
                cache_dir=fixture["cache"],
                identity=identity,
                run_dir=race_run,
                origin=entry_document["origin"],
            )
            self.assertFalse(published)
            self.assertEqual(
                winner.manifest_sha256,
                hashlib.sha256((entry_dir / "entry.json").read_bytes()).hexdigest(),
            )

            different = json.loads(
                (race_run / "candidate.raw.json").read_text(encoding="utf-8")
            )
            different["notes"][0]["pitch"] = 67.0
            (race_run / "candidate.raw.json").write_text(
                json.dumps(different), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "different raw candidates"):
                publish_muscriptor_cache_entry(
                    cache_dir=fixture["cache"],
                    identity=identity,
                    run_dir=race_run,
                    origin=entry_document["origin"],
                )
            self.assertEqual(
                list(entry_dir.parent.glob(f".{key}.*.tmp")),
                [],
            )

    def test_entry_manifest_self_consistency_is_enforced(self) -> None:
        mutations = {
            "scope": lambda document: document.__setitem__("scope", "wrong"),
            "effects": lambda document: document["effects"].__setitem__(
                "midi_cached", True
            ),
            "candidate": lambda document: document["candidate"].__setitem__(
                "note_count", 999
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                fixture = self._fixture(Path(directory))
                origin = self._run(fixture, "origin")
                key = origin["application_cache"]["key_sha256"]
                entry_path = self._cache_entry_path(fixture, key) / "entry.json"
                document = json.loads(entry_path.read_text(encoding="utf-8"))
                mutate(document)
                entry_path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaises(AIWorkerRunError):
                    self._run(fixture, f"invalid-{label}")
                self.assertEqual(
                    fixture["worker"].with_name("worker-invocations.txt").read_text(),
                    "1",
                )

    def test_wrong_candidate_identity_and_changed_input_never_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            fixture["worker"].write_text(
                textwrap.dedent(_WORKER).replace(
                    '"instruments": request["roles"],',
                    '"instruments": ["electric_bass"],',
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AIWorkerRunError, "instruments changed"):
                self._run(fixture, "wrong-instruments")
            self.assertEqual(list(fixture["cache"].rglob("entry.json")), [])

        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            fixture["worker"].write_text(
                textwrap.dedent(_WORKER)
                + '\nPath(request["audio_path"]).write_bytes(b"changed")\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AIWorkerRunError, "source changed"):
                self._run(fixture, "changed-source")
            self.assertEqual(list(fixture["cache"].rglob("entry.json")), [])

    def test_private_path_role_and_nested_roots_are_rejected_before_a_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            private_role = "/Users/private/Music/song.wav"
            with self.assertRaisesRegex(ValueError, "exact MuScriptor role"):
                self._run(fixture, "path-role", roles=(private_role,))
            self.assertFalse(fixture["runs"].exists())
            self.assertNotIn(
                private_role,
                json.dumps(_runtime(), sort_keys=True),
            )
            with self.assertRaisesRegex(ValueError, "must not contain"):
                run_ai_transcription(
                    audio_path=fixture["audio"],
                    out_dir=fixture["cache"] / "runs",
                    checkpoint_path=fixture["checkpoint"],
                    bpm=119,
                    roles=("electric_piano",),
                    python=sys.executable,
                    worker_path=fixture["worker"],
                    application_cache_dir=fixture["cache"],
                    run_id="nested",
                )

    def test_cache_requires_private_permissions_and_excludes_worker_sessions(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            fixture["cache"].mkdir(mode=0o755)
            fixture["cache"].chmod(0o755)
            with self.assertRaisesRegex(AIWorkerRunError, "group or other permissions"):
                self._run(fixture, "insecure-cache")
            self.assertFalse(
                fixture["worker"].with_name("worker-invocations.txt").exists()
            )

        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            session = mock.Mock(
                worker_path=fixture["worker"],
                python=Path(sys.executable),
                worker_sha256=hashlib.sha256(
                    fixture["worker"].read_bytes()
                ).hexdigest(),
                bpm=119.0,
            )
            with self.assertRaisesRegex(ValueError, "separate execution regimes"):
                run_ai_transcription(
                    audio_path=fixture["audio"],
                    out_dir=fixture["runs"],
                    checkpoint_path=fixture["checkpoint"],
                    bpm=119,
                    roles=("electric_piano",),
                    python=sys.executable,
                    worker_path=fixture["worker"],
                    worker_session=session,
                    application_cache_dir=fixture["cache"],
                    run_id="cache-session",
                )

    def test_non_muscriptor_and_sampling_are_rejected_before_a_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory))
            rmvpe = Path(directory) / "model.onnx"
            rmvpe.write_bytes(b"rmvpe")
            with self.assertRaisesRegex(ValueError, "supports MuScriptor only"):
                run_ai_transcription(
                    audio_path=fixture["audio"],
                    out_dir=fixture["runs"],
                    checkpoint_path=rmvpe,
                    bpm=119,
                    backend="rmvpe",
                    python=sys.executable,
                    worker_path=fixture["worker"],
                    application_cache_dir=fixture["cache"],
                    run_id="rmvpe-cache",
                )
            with (
                mock.patch(
                    "sunofriend.ai_bakeoff.collect_ai_runtime_fingerprint",
                    return_value=_runtime(),
                ),
                self.assertRaisesRegex(ValueError, "does not accept stochastic"),
            ):
                run_ai_transcription(
                    audio_path=fixture["audio"],
                    out_dir=fixture["runs"],
                    checkpoint_path=fixture["checkpoint"],
                    bpm=119,
                    options={"device": "cpu", "use_sampling": True},
                    python=sys.executable,
                    worker_path=fixture["worker"],
                    application_cache_dir=fixture["cache"],
                    run_id="sampling-cache",
                )
            self.assertFalse(fixture["runs"].exists())


if __name__ == "__main__":
    unittest.main()
