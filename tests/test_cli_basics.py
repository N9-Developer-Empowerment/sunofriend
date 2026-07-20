from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sunofriend import __version__
from sunofriend.cli import build_parser, main


class CliBasicsTests(unittest.TestCase):
    def test_version_uses_the_package_version(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"sunofriend {__version__}")

    def test_workbench_command_is_loopback_local_and_inspectable(self) -> None:
        parser = build_parser()

        args = parser.parse_args(
            [
                "workbench",
                "song-stems",
                "--candidate-root",
                "candidate-a",
                "--candidate-root",
                "candidate-b",
                "--state-dir",
                "state",
                "--port",
                "8123",
                "--open",
                "--inspect",
            ]
        )

        self.assertEqual(args.project, "song-stems")
        self.assertEqual(args.candidate_root, ["candidate-a", "candidate-b"])
        self.assertEqual(args.state_dir, "state")
        self.assertEqual(args.port, 8123)
        self.assertTrue(args.open)
        self.assertTrue(args.inspect)

    def test_ai_benchmark_requires_explicit_runs_and_fresh_output(self) -> None:
        args = build_parser().parse_args(
            [
                "ai-benchmark",
                "--run",
                "repetition-01",
                "--run",
                "repetition-02",
                "--out",
                "benchmark.json",
            ]
        )

        self.assertEqual(args.run, ["repetition-01", "repetition-02"])
        self.assertEqual(args.out, "benchmark.json")

    def test_ai_setting_compare_requires_two_explicit_arms(self) -> None:
        args = build_parser().parse_args(
            [
                "ai-setting-compare",
                "--control-run",
                "beam1-01",
                "--control-run",
                "beam1-02",
                "--challenger-run",
                "beam2-01",
                "--challenger-run",
                "beam2-02",
                "--out",
                "setting-comparison.json",
            ]
        )

        self.assertEqual(args.control_run, ["beam1-01", "beam1-02"])
        self.assertEqual(args.challenger_run, ["beam2-01", "beam2-02"])
        self.assertEqual(args.setting, "beam-size")
        self.assertEqual(args.out, "setting-comparison.json")

        batch = build_parser().parse_args(
            [
                "ai-setting-compare",
                "--setting",
                "batch-size",
                "--control-run",
                "batch1-01",
                "--control-run",
                "batch1-02",
                "--challenger-run",
                "batch2-01",
                "--challenger-run",
                "batch2-02",
                "--out",
                "batch-comparison.json",
            ]
        )
        self.assertEqual(batch.setting, "batch-size")

    def test_hybrid_report_requires_named_candidates_and_evidence(self) -> None:
        args = build_parser().parse_args(
            [
                "hybrid-report",
                "source.wav",
                "--role",
                "lead",
                "--bpm",
                "119",
                "--candidate",
                "S0=specialist.mid",
                "--candidate",
                "M1=full-mix.mid",
                "--candidate",
                "M3=conditioned.mid",
                "--evidence",
                "S0=provenance.json",
                "--evidence",
                "M1=label-split.json",
                "--evidence",
                "M3=projection.json",
                "--phrase-review",
                "phrase-review.json",
                "--out",
                "hybrid-report.json",
            ]
        )

        self.assertEqual(args.source_wav, "source.wav")
        self.assertEqual(args.role, "lead")
        self.assertEqual(args.bpm, 119.0)
        self.assertEqual(
            args.candidate,
            ["S0=specialist.mid", "M1=full-mix.mid", "M3=conditioned.mid"],
        )
        self.assertEqual(
            args.evidence,
            ["S0=provenance.json", "M1=label-split.json", "M3=projection.json"],
        )
        self.assertEqual(args.phrase_review, "phrase-review.json")
        self.assertEqual(args.out, "hybrid-report.json")

    def test_midi_ab_review_accepts_explicit_short_windows(self) -> None:
        parser = build_parser()
        review = parser.parse_args(
            [
                "midi-ab-review",
                "source.wav",
                "beam1.mid",
                "beam2.mid",
                "--interval",
                "0.2",
                "3.5",
                "Judge chord fullness without clutter.",
                "--interval",
                "11.6",
                "15.0",
                "Judge bass timing and octave.",
                "--bpm",
                "119",
                "--midi-time-at-source-start",
                "0.0",
                "--gm-program",
                "4",
                "--soundfont",
                "neutral.sf2",
                "--out-dir",
                "blind-review",
            ]
        )
        resolve = parser.parse_args(
            [
                "midi-ab-resolve",
                "midi-ab.reviewed.json",
                "--package-dir",
                "blind-review",
                "--out",
                "midi-ab.result.json",
            ]
        )

        self.assertEqual(review.source_audio, "source.wav")
        self.assertEqual(review.first_midi, "beam1.mid")
        self.assertEqual(review.second_midi, "beam2.mid")
        self.assertEqual(
            review.interval,
            [
                ["0.2", "3.5", "Judge chord fullness without clutter."],
                ["11.6", "15.0", "Judge bass timing and octave."],
            ],
        )
        self.assertEqual(review.bpm, 119.0)
        self.assertEqual(review.midi_time_at_source_start, 0.0)
        self.assertEqual(review.gm_program, 4)
        self.assertEqual(review.soundfont, "neutral.sf2")
        self.assertEqual(resolve.review, "midi-ab.reviewed.json")
        self.assertEqual(resolve.package_dir, "blind-review")
        self.assertEqual(resolve.out, "midi-ab.result.json")

    def test_ai_transcribe_session_is_bounded_and_muscriptor_only(self) -> None:
        args = build_parser().parse_args(
            [
                "ai-transcribe-session",
                "source.wav",
                "--checkpoint",
                "model.safetensors",
                "--out-dir",
                "session",
                "--bpm",
                "119",
                "--instrument",
                "electric_piano",
                "--repetitions",
                "3",
                "--device",
                "cpu",
            ]
        )

        self.assertEqual(args.audio, "source.wav")
        self.assertEqual(args.repetitions, 3)
        self.assertEqual(args.instrument, ["electric_piano"])
        self.assertEqual(args.device, "cpu")

    def test_ai_session_benchmark_accepts_separate_fresh_controls(self) -> None:
        args = build_parser().parse_args(
            [
                "ai-session-benchmark",
                "session",
                "--fresh-run",
                "fresh-001",
                "--fresh-run",
                "fresh-002",
                "--out",
                "session-benchmark.json",
            ]
        )

        self.assertEqual(args.session, "session")
        self.assertEqual(args.fresh_run, ["fresh-001", "fresh-002"])
        self.assertEqual(args.out, "session-benchmark.json")

    def test_ai_cache_options_are_explicit_and_separately_benchmarked(self) -> None:
        transcribe = build_parser().parse_args(
            [
                "ai-transcribe",
                "source.wav",
                "--out-dir",
                "runs",
                "--bpm",
                "119",
                "--application-cache-dir",
                "private-cache",
            ]
        )
        benchmark = build_parser().parse_args(
            [
                "ai-cache-benchmark",
                "--miss-run",
                "miss",
                "--hit-run",
                "hit-1",
                "--hit-run",
                "hit-2",
                "--out",
                "cache-benchmark.json",
            ]
        )

        self.assertEqual(transcribe.application_cache_dir, "private-cache")
        self.assertEqual(benchmark.miss_run, "miss")
        self.assertEqual(benchmark.hit_run, ["hit-1", "hit-2"])

    @patch("sunofriend.ai_cache_benchmark.write_ai_cache_benchmark")
    def test_ai_cache_benchmark_routes_without_inference(self, write) -> None:
        write.return_value = {
            "schema": "sunofriend.ai-cache-benchmark.v1",
            "hit_count": 2,
        }
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            result = main(
                [
                    "ai-cache-benchmark",
                    "--miss-run",
                    "miss",
                    "--hit-run",
                    "hit-1",
                    "--hit-run",
                    "hit-2",
                    "--out",
                    "cache-benchmark.json",
                ]
            )

        self.assertEqual(result, 0)
        write.assert_called_once_with(
            "miss", ["hit-1", "hit-2"], "cache-benchmark.json"
        )
        document = json.loads(stdout.getvalue())
        self.assertTrue(document["application_cache_hit"])
        self.assertFalse(document["model_reused"])
        self.assertFalse(document["promotion_allowed"])

    @patch("sunofriend.ai_benchmark.write_ai_performance_benchmark")
    def test_ai_benchmark_routes_completed_runs_without_inference(self, write) -> None:
        write.return_value = {
            "schema": "sunofriend.ai-performance-benchmark.v1",
            "repetition_count": 2,
        }
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            result = main(
                [
                    "ai-benchmark",
                    "--run",
                    "repetition-01",
                    "--run",
                    "repetition-02",
                    "--out",
                    "benchmark.json",
                ]
            )

        self.assertEqual(result, 0)
        write.assert_called_once_with(
            ["repetition-01", "repetition-02"], "benchmark.json"
        )
        self.assertEqual(
            json.loads(stdout.getvalue()),
            {
                "output": str(Path("benchmark.json").absolute()),
                "repetition_count": 2,
                "schema": "sunofriend.ai-performance-benchmark.v1",
                "status": "complete",
            },
        )

    @patch("sunofriend.ai_setting_compare.write_ai_setting_comparison")
    def test_ai_setting_compare_routes_completed_runs_without_inference(
        self, write
    ) -> None:
        write.return_value = {
            "schema": "sunofriend.ai-setting-comparison.v1",
            "setting_change": {"semantic_setting": "batch_size"},
            "arms": {
                "control": {"repetition_count": 2},
                "challenger": {"repetition_count": 2},
            },
            "comparison": {
                "outputs": {
                    "musical_output_identical": False,
                }
            },
            "effects": {
                "listening_review_required_before_default_change": True,
            },
        }
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            result = main(
                [
                    "ai-setting-compare",
                    "--setting",
                    "batch-size",
                    "--control-run",
                    "beam1-01",
                    "--control-run",
                    "beam1-02",
                    "--challenger-run",
                    "beam2-01",
                    "--challenger-run",
                    "beam2-02",
                    "--out",
                    "setting-comparison.json",
                ]
            )

        self.assertEqual(result, 0)
        write.assert_called_once_with(
            ["beam1-01", "beam1-02"],
            ["beam2-01", "beam2-02"],
            "setting-comparison.json",
            setting="batch_size",
        )
        document = json.loads(stdout.getvalue())
        self.assertTrue(document["listening_review_required"])
        self.assertFalse(document["promotion_allowed"])

    @patch("sunofriend.hybrid_report.write_hybrid_report")
    def test_hybrid_report_routes_named_evidence_without_creating_midi(
        self, write
    ) -> None:
        write.return_value = {
            "schema": "sunofriend.hybrid-candidate-report.v1",
            "status": "diagnostic-only",
            "role": "lead",
            "candidates": [
                {"lane": "S0", "note_count": 23},
                {"lane": "M1", "note_count": 38},
                {"lane": "M3", "note_count": 39},
            ],
            "phrases": [{"phrase_index": 1}, {"phrase_index": 2}],
            "lineage": {
                "M1_full_mix_association": {
                    "status": "caller-supplied-derivation-unverified"
                },
                "M3_original_source_midi": {
                    "status": "manifest-claimed-payload-unverified"
                },
            },
            "effects": {
                "midi_files_created": 0,
                "automatic_selection": False,
            },
        }
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            result = main(
                [
                    "hybrid-report",
                    "source.wav",
                    "--role",
                    "lead",
                    "--bpm",
                    "119",
                    "--candidate",
                    "S0=specialist.mid",
                    "--candidate",
                    "M1=full=mix.mid",
                    "--candidate",
                    "M3=conditioned.mid",
                    "--evidence",
                    "S0=provenance.json",
                    "--evidence",
                    "M1=label-split.json",
                    "--evidence",
                    "M3=projection.json",
                    "--phrase-review",
                    "phrase-review.json",
                    "--out",
                    "hybrid-report.json",
                ]
            )

        self.assertEqual(result, 0)
        write.assert_called_once_with(
            "source.wav",
            role="lead",
            bpm=119.0,
            candidates={
                "S0": "specialist.mid",
                "M1": "full=mix.mid",
                "M3": "conditioned.mid",
            },
            evidence={
                "S0": "provenance.json",
                "M1": "label-split.json",
                "M3": "projection.json",
            },
            phrase_review="phrase-review.json",
            output_path="hybrid-report.json",
        )
        document = json.loads(stdout.getvalue())
        self.assertEqual(
            document["candidate_note_counts"], {"S0": 23, "M1": 38, "M3": 39}
        )
        self.assertEqual(document["phrase_count"], 2)
        self.assertEqual(
            document["lineage_status"],
            {
                "M1_full_mix_association": ("caller-supplied-derivation-unverified"),
                "M3_original_source_midi": ("manifest-claimed-payload-unverified"),
            },
        )
        self.assertEqual(document["midi_files_created"], 0)
        self.assertFalse(document["automatic_selection"])

    def test_hybrid_report_rejects_duplicate_named_lanes(self) -> None:
        stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(
                    [
                        "hybrid-report",
                        "source.wav",
                        "--role",
                        "lead",
                        "--bpm",
                        "119",
                        "--candidate",
                        "S0=first.mid",
                        "--candidate",
                        "S0=second.mid",
                        "--evidence",
                        "S0=provenance.json",
                        "--phrase-review",
                        "phrase-review.json",
                        "--out",
                        "hybrid-report.json",
                    ]
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--candidate repeats lane S0", stderr.getvalue())

    @patch("sunofriend.midi_ab_review.create_midi_ab_review")
    def test_midi_ab_review_routes_without_selecting_a_winner(self, create) -> None:
        create.return_value = {
            "schema": "sunofriend.midi-ab-review.v1",
            "status": "complete",
            "out_dir": "/tmp/blind-review",
            "effects": {"promotion_allowed": False},
        }
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            result = main(
                [
                    "midi-ab-review",
                    "source.wav",
                    "beam1.mid",
                    "beam2.mid",
                    "--interval",
                    "0.2",
                    "3.5",
                    "Judge useful musical detail.",
                    "--bpm",
                    "119",
                    "--midi-time-at-source-start",
                    "0.0",
                    "--gm-program",
                    "4",
                    "--soundfont",
                    "neutral.sf2",
                    "--out-dir",
                    "blind-review",
                ]
            )

        self.assertEqual(result, 0)
        create.assert_called_once_with(
            "source.wav",
            "beam1.mid",
            "beam2.mid",
            [(0.2, 3.5, "Judge useful musical detail.")],
            "blind-review",
            bpm=119.0,
            midi_time_at_source_start_seconds=0.0,
            gm_program=4,
            soundfont_path="neutral.sf2",
        )
        self.assertFalse(json.loads(stdout.getvalue())["effects"]["promotion_allowed"])

    @patch("sunofriend.midi_ab_review.resolve_midi_ab_review")
    def test_midi_ab_resolve_routes_explicit_review(self, resolve) -> None:
        resolve.return_value = {
            "schema": "sunofriend.midi-ab-result.v1",
            "status": "complete",
            "promotion_allowed": False,
        }
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            result = main(
                [
                    "midi-ab-resolve",
                    "midi-ab.reviewed.json",
                    "--package-dir",
                    "blind-review",
                    "--out",
                    "midi-ab.result.json",
                ]
            )

        self.assertEqual(result, 0)
        resolve.assert_called_once_with(
            "midi-ab.reviewed.json",
            "midi-ab.result.json",
            package_dir="blind-review",
        )
        self.assertFalse(json.loads(stdout.getvalue())["promotion_allowed"])

    @patch("sunofriend.ai_session.run_muscriptor_session")
    @patch("sunofriend.ai_runtime.resolve_muscriptor_checkpoint")
    def test_ai_transcribe_session_routes_one_bounded_operation(
        self, resolve_checkpoint, run_session
    ) -> None:
        resolve_checkpoint.return_value = Path("/models/model.safetensors")
        run_session.return_value = {
            "schema": "sunofriend.muscriptor-transcription-session.v1",
            "session_id": "session-test",
            "status": "complete",
            "repetitions_completed": 3,
            "cache_regime": {"model_loaded_once": True},
        }
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            result = main(
                [
                    "ai-transcribe-session",
                    "source.wav",
                    "--checkpoint",
                    "model.safetensors",
                    "--out-dir",
                    "session",
                    "--bpm",
                    "119",
                    "--instrument",
                    "electric_piano",
                    "--repetitions",
                    "3",
                    "--device",
                    "cpu",
                ]
            )

        self.assertEqual(result, 0)
        self.assertEqual(run_session.call_count, 1)
        call = run_session.call_args.kwargs
        self.assertEqual(call["repetitions"], 3)
        self.assertEqual(call["roles"], ["electric_piano"])
        self.assertEqual(call["options"]["device"], "cpu")
        self.assertFalse(json.loads(stdout.getvalue())["promotion_allowed"])

    @patch("sunofriend.ai_session_benchmark.write_ai_session_benchmark")
    def test_ai_session_benchmark_routes_without_inference(self, write) -> None:
        write.return_value = {
            "schema": "sunofriend.ai-session-performance-benchmark.v1",
            "request_count": 3,
            "warm_request_count": 2,
            "fresh_control": {"status": "verified"},
        }
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            result = main(
                [
                    "ai-session-benchmark",
                    "session",
                    "--fresh-run",
                    "fresh-001",
                    "--fresh-run",
                    "fresh-002",
                    "--out",
                    "benchmark.json",
                ]
            )

        self.assertEqual(result, 0)
        write.assert_called_once_with(
            "session", ["fresh-001", "fresh-002"], "benchmark.json"
        )
        self.assertEqual(
            json.loads(stdout.getvalue())["fresh_control_status"], "verified"
        )

    def test_instrument_commands_accept_an_explicit_embedding_model(self) -> None:
        parser = build_parser()
        match = parser.parse_args(
            [
                "instrument-match",
                "stem.wav",
                "part.mid",
                "--kind",
                "bass",
                "--out-dir",
                "match",
                "--embedding-model",
                "openl3.onnx",
            ]
        )
        bundle = parser.parse_args(
            [
                "instrument-bundle",
                "stem.wav",
                "part.mid",
                "--kind",
                "bass",
                "--out-dir",
                "bundle",
                "--embedding-model",
                "openl3.onnx",
            ]
        )
        sample_pack = parser.parse_args(
            [
                "sample-pack",
                "stem.wav",
                "part.mid",
                "--kind",
                "bass",
                "--out-dir",
                "samples",
                "--embedding-model",
                "openl3.onnx",
            ]
        )

        self.assertEqual(match.embedding_model, "openl3.onnx")
        self.assertEqual(bundle.embedding_model, "openl3.onnx")
        self.assertEqual(sample_pack.embedding_model, "openl3.onnx")

    def test_instrument_preference_commands_are_explicit_and_advisory(self) -> None:
        parser = build_parser()

        feedback = parser.parse_args(
            [
                "instrument-feedback",
                "bundle",
                "--patch",
                "Small Time Piano",
                "--compared-with",
                "sunofriend-instrument",
                "--out",
                "feedback.json",
            ]
        )
        profile = parser.parse_args(
            [
                "instrument-profile",
                "feedback.json",
                "--out",
                "profile.json",
            ]
        )
        bundle = parser.parse_args(
            [
                "instrument-bundle",
                "stem.wav",
                "part.mid",
                "--kind",
                "keys",
                "--out-dir",
                "bundle-v2",
                "--preference-profile",
                "profile.json",
            ]
        )

        self.assertEqual(feedback.patch, "Small Time Piano")
        self.assertEqual(feedback.decision, "preferred")
        self.assertEqual(feedback.context, "full-mix")
        self.assertEqual(profile.feedback, ["feedback.json"])
        self.assertEqual(bundle.preference_profile, "profile.json")

    def test_preview_accepts_a_source_derived_soundfont(self) -> None:
        parser = build_parser()

        preview = parser.parse_args(
            [
                "preview",
                "performance.mid",
                "--out",
                "performance.wav",
                "--soundfont",
                "sunofriend-instrument.sf2",
            ]
        )

        self.assertEqual(preview.midi, "performance.mid")
        self.assertEqual(preview.out, "performance.wav")
        self.assertEqual(preview.soundfont, "sunofriend-instrument.sf2")

        stdout = io.StringIO()
        with (
            patch(
                "sunofriend.render.render_midi_to_wav",
                return_value=Path("performance.wav"),
            ) as render,
            redirect_stdout(stdout),
        ):
            result = main(
                [
                    "preview",
                    "performance.mid",
                    "--out",
                    "performance.wav",
                    "--soundfont",
                    "sunofriend-instrument.sf2",
                ]
            )

        self.assertEqual(result, 0)
        render.assert_called_once_with(
            Path("performance.mid"),
            Path("performance.wav"),
            soundfont_path="sunofriend-instrument.sf2",
        )
        self.assertEqual(stdout.getvalue().strip(), "performance.wav")

    def test_midi_role_split_requires_an_explicit_body_cluster(self) -> None:
        parser = build_parser()

        split = parser.parse_args(
            [
                "midi-role-split",
                "primary.mid",
                "source_event_clusters.json",
                "--body-cluster",
                "I1",
                "--secondary-midi",
                "residual.mid",
                "--out-dir",
                "role-split",
            ]
        )

        self.assertEqual(split.body_cluster, "I1")
        self.assertEqual(split.secondary_midi, "residual.mid")
        self.assertEqual(split.body_program, 39)
        self.assertEqual(split.pluck_program, 28)

        resolve = parser.parse_args(
            [
                "midi-role-split-resolve",
                "reviewed.json",
                "role-split",
                "--out-dir",
                "resolved",
            ]
        )
        self.assertEqual(resolve.review, "reviewed.json")
        self.assertEqual(resolve.role_split_dir, "role-split")

    def test_timbre_resynthesis_keeps_sound_controls_explicit(self) -> None:
        parser = build_parser()

        args = parser.parse_args(
            [
                "timbre-resynthesis",
                "source.wav",
                "fixed.mid",
                "--gm-program",
                "39",
                "--source-soundfont",
                "source.sf2",
                "--source-soundfont-program",
                "0",
                "--harmonics",
                "20",
                "--attack-ms",
                "9",
                "--release-ms",
                "50",
                "--out-dir",
                "review",
            ]
        )

        self.assertEqual(args.source_audio, "source.wav")
        self.assertEqual(args.midi, "fixed.mid")
        self.assertEqual(args.gm_program, 39)
        self.assertEqual(args.source_soundfont, "source.sf2")
        self.assertEqual(args.harmonics, 20)
        self.assertEqual(args.attack_ms, 9.0)
        self.assertEqual(args.release_ms, 50.0)

    def test_sample_pack_review_commands_keep_review_and_apply_separate(self) -> None:
        parser = build_parser()
        review = parser.parse_args(
            [
                "sample-pack-review",
                "sample-pack-v2",
                "--out-dir",
                "review",
            ]
        )
        apply = parser.parse_args(
            [
                "sample-pack-apply",
                "reviewed.json",
                "--out-dir",
                "sample-pack-v3",
                "--name",
                "Reviewed Bass",
                "--no-preview",
            ]
        )

        self.assertEqual(review.sample_pack, "sample-pack-v2")
        self.assertEqual(review.out_dir, "review")
        self.assertEqual(apply.review, "reviewed.json")
        self.assertEqual(apply.name, "Reviewed Bass")
        self.assertTrue(apply.no_preview)

        boundary_review = parser.parse_args(
            [
                "sample-pack-boundary-review",
                "sample-pack-v3",
                "--out-dir",
                "boundary-review",
            ]
        )
        boundary_apply = parser.parse_args(
            [
                "sample-pack-boundary-apply",
                "boundary.reviewed.json",
                "--out-dir",
                "boundary-v3",
                "--name",
                "Reviewed Boundary Bass",
                "--no-preview",
            ]
        )

        self.assertEqual(boundary_review.sample_pack_v3, "sample-pack-v3")
        self.assertEqual(boundary_review.out_dir, "boundary-review")
        self.assertEqual(boundary_apply.review, "boundary.reviewed.json")
        self.assertEqual(boundary_apply.name, "Reviewed Boundary Bass")
        self.assertTrue(boundary_apply.no_preview)

        ab_review = parser.parse_args(
            [
                "sample-pack-ab-review",
                "snare-v3",
                "toms-v3",
                "--out-dir",
                "blind-review",
            ]
        )
        ab_resolve = parser.parse_args(
            [
                "sample-pack-ab-resolve",
                "blind.reviewed.json",
                "--out",
                "blind.result.json",
            ]
        )

        self.assertEqual(ab_review.sample_pack_v3, ["snare-v3", "toms-v3"])
        self.assertEqual(ab_review.out_dir, "blind-review")
        self.assertEqual(ab_resolve.review, "blind.reviewed.json")
        self.assertEqual(ab_resolve.out, "blind.result.json")


if __name__ == "__main__":
    unittest.main()
