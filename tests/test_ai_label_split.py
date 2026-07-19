from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import soundfile

from sunofriend.ai_bakeoff import run_ai_transcription
from sunofriend.ai_label_split import (
    AI_LABEL_PARTITION_SCHEMA,
    AI_LABEL_SPLIT_SCHEMA,
    split_ai_candidate_label,
)
from sunofriend.cli import build_parser
from sunofriend.clip import read_midi_clips


_WORKER = r"""
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument("--request", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
request = json.load(open(args.request, encoding="utf-8"))
notes = [
    {
        "start_seconds": 0.10,
        "end_seconds": 0.40,
        "pitch": 59.0,
        "confidence": None,
        "instrument": "clean_electric_guitar",
        "velocity": None,
        "source_event_id": "guitar-1",
    },
    {
        "start_seconds": 0.45,
        "end_seconds": 0.90,
        "pitch": 35.0,
        "confidence": None,
        "instrument": "electric_bass",
        "velocity": None,
        "source_event_id": "bass-1",
    },
    {
        "start_seconds": 1.00,
        "end_seconds": 1.35,
        "pitch": 62.0,
        "confidence": None,
        "instrument": "clean_electric_guitar",
        "velocity": None,
        "source_event_id": "guitar-2",
    },
]
candidate = {
    "schema": "sunofriend.ai-transcription-candidate.v1",
    "backend": "muscriptor",
    "model_version": "muscriptor-test-small",
    "notes": notes,
    "warnings": [],
    "raw_artifacts": [],
    "metadata": {
        "checkpoint_sha256": request["options"]["model_sha256"],
        "excerpt": {
            "start_seconds": 0.0,
            "end_seconds": 2.0,
            "duration_seconds": 2.0,
        },
        "execution": {
            "model_size": request["options"]["model_size"],
            "decoding": {
                "strategy": "greedy",
                "beam_size": request["options"]["beam_size"],
                "batch_size": request["options"]["batch_size"],
                "cfg_coef": request["options"]["cfg_coef"],
                "temperature": request["options"]["temperature"],
                "use_sampling": request["options"]["use_sampling"],
                "no_eos_is_ok": request["options"]["no_eos_is_ok"],
            },
            "chunking": {
                "seconds": request["options"]["chunk_seconds"],
                "prelude_forcing": request["options"]["prelude_forcing"],
                "prelude_forcing_supported": request["options"]["prelude_forcing_supported"],
            },
            "strategy": "fixture-greedy",
            "cwd": request["audio_path"],
            "nested": {
                "cache_value": "/private/cache/model.safetensors",
                "safe_value": "retained",
            },
            "argv": ["/private/python", "worker.py", "safe-token"],
        },
    },
}
json.dump(candidate, open(args.output, "w", encoding="utf-8"))
"""


def _worker_with_notes(notes: list[dict[str, object]]) -> str:
    return f"""
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument("--request", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
request = json.load(open(args.request, encoding="utf-8"))
candidate = {{
    "schema": "sunofriend.ai-transcription-candidate.v1",
    "backend": "muscriptor",
    "model_version": "muscriptor-test-small",
    "notes": json.loads({json.dumps(json.dumps(notes, sort_keys=True))}),
    "warnings": [],
    "raw_artifacts": [],
    "metadata": {{
        "checkpoint_sha256": request["options"]["model_sha256"],
        "excerpt": {{
            "start_seconds": 0.0,
            "end_seconds": 2.0,
            "duration_seconds": 2.0,
        }},
    }},
}}
json.dump(candidate, open(args.output, "w", encoding="utf-8"))
"""


class AILabelSplitTests(unittest.TestCase):
    def _run(
        self,
        root: Path,
        *,
        roles: tuple[str, ...] = ("clean_electric_guitar",),
        worker_source: str = _WORKER,
    ) -> Path:
        sample_rate = 8_000
        audio = root / "source.wav"
        soundfile.write(
            audio,
            np.sin(np.linspace(0.0, 30.0, sample_rate * 2)).astype(np.float32),
            sample_rate,
        )
        checkpoint = root / "model.safetensors"
        checkpoint.write_bytes(b"label-split-test-checkpoint")
        (root / "config.json").write_text(
            '{"model_type":"muscriptor","variant":"small","dim":768}',
            encoding="utf-8",
        )
        worker = root / "worker.py"
        worker.write_text(textwrap.dedent(worker_source), encoding="utf-8")
        run_ai_transcription(
            audio_path=audio,
            out_dir=root / "runs",
            checkpoint_path=checkpoint,
            bpm=113.0,
            roles=roles,
            start_seconds=0.0,
            end_seconds=2.0,
            python=sys.executable,
            worker_path=worker,
            run_id="split-run",
        )
        return root / "runs" / "split-run"

    def test_exact_partition_is_path_free_repeatable_and_does_not_mutate_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = self._run(root)
            before = _tree_hashes(run)

            first_dir = root / "first"
            first = split_ai_candidate_label(
                run,
                label="clean_electric_guitar",
                out_dir=first_dir,
            )
            second_dir = root / "second"
            second = split_ai_candidate_label(
                run,
                label="clean_electric_guitar",
                out_dir=second_dir,
            )

            self.assertEqual(first["schema"], AI_LABEL_SPLIT_SCHEMA)
            self.assertEqual(first["status"], "review-required")
            self.assertEqual(first["evidence"]["selected_note_count"], 2)
            self.assertEqual(first["evidence"]["complement_note_count"], 1)
            self.assertEqual(first, second)
            self.assertNotIn(str(root), json.dumps(first, sort_keys=True))
            self.assertNotIn("/private", json.dumps(first, sort_keys=True))
            partition = json.loads(
                (first_dir / "label-partition.json").read_text(encoding="utf-8")
            )
            self.assertEqual(partition["schema"], AI_LABEL_PARTITION_SCHEMA)
            self.assertEqual(
                [row["source_index"] for row in partition["selected"]], [0, 2]
            )
            self.assertEqual(
                [row["source_index"] for row in partition["complement"]], [1]
            )
            self.assertTrue(partition["partition"]["disjoint"])
            self.assertTrue(partition["partition"]["exhaustive"])
            self.assertEqual(_midi_note_count(first_dir / "requested-label.mid"), 2)
            self.assertEqual(
                _midi_note_count(first_dir / "unexpected-label-complement.mid"), 1
            )
            for name in (
                "source-request.json",
                "source-candidate.json",
                "unchanged-full-candidate.mid",
                "requested-label.mid",
                "unexpected-label-complement.mid",
                "label-partition.json",
                "ai_label_split.json",
            ):
                self.assertEqual(
                    (first_dir / name).read_bytes(), (second_dir / name).read_bytes()
                )
            self.assertEqual(_tree_hashes(run), before)
            self.assertFalse(first["effects"]["automatic_promotion"])
            self.assertFalse(first["effects"]["raw_candidate_mutated"])
            self.assertTrue(first["effects"]["unchanged_control_byte_identical"])
            self.assertEqual(
                (first_dir / "source-request.json").read_bytes(),
                (run / "request.json").read_bytes(),
            )
            self.assertEqual(
                (first_dir / "source-candidate.json").read_bytes(),
                (run / "candidate.json").read_bytes(),
            )
            self.assertEqual(
                (first_dir / "unchanged-full-candidate.mid").read_bytes(),
                (run / "candidate.mid").read_bytes(),
            )
            self.assertEqual(
                first["artifacts"]["source-request.json"]["sha256"],
                first["source_run"]["request"]["sha256"],
            )
            self.assertEqual(
                first["artifacts"]["source-candidate.json"]["sha256"],
                first["source_run"]["candidate"]["sha256"],
            )
            self.assertEqual(
                first["artifacts"]["unchanged-full-candidate.mid"]["sha256"],
                first["source_run"]["candidate_midi"]["sha256"],
            )
            candidate_execution = first["source_run"]["execution"]["candidate"]
            self.assertEqual(
                candidate_execution["nested"], {"safe_value": "retained"}
            )
            self.assertEqual(candidate_execution["strategy"], "fixture-greedy")
            self.assertIn("decoding", candidate_execution)
            self.assertNotIn("cwd", json.dumps(first["source_run"]["execution"]))
            self.assertNotIn(
                str(root),
                (first_dir / "ai_label_split.json").read_text(encoding="utf-8"),
            )
            self.assertIn(
                str(root),
                (first_dir / "source-request.json").read_text(encoding="utf-8"),
            )

    def test_mutable_run_execution_cannot_override_pinned_candidate_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = self._run(root)
            run_path = run / "run.json"
            document = json.loads(run_path.read_text(encoding="utf-8"))
            document["execution"]["diagnostic"] = {
                "cwd": str(root / "private-working-directory"),
                "safe_value": "untrusted",
            }
            run_path.write_text(json.dumps(document), encoding="utf-8")
            output = root / "execution-tampered"

            with self.assertRaisesRegex(
                ValueError, "execution differs from pinned candidate metadata"
            ):
                split_ai_candidate_label(
                    run,
                    label="clean_electric_guitar",
                    out_dir=output,
                )
            self.assertFalse(output.exists())

    def test_unconditioned_completed_run_can_be_partitioned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = self._run(root, roles=())

            report = split_ai_candidate_label(
                run,
                label="clean_electric_guitar",
                out_dir=root / "unconditioned-split",
            )

            self.assertEqual(report["source_run"]["request"]["roles"], [])
            self.assertEqual(report["evidence"]["selected_note_count"], 2)
            self.assertEqual(report["evidence"]["complement_note_count"], 1)

    def test_missing_label_is_retained_as_no_evidence_with_full_complement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = self._run(root)
            output = root / "missing"
            report = split_ai_candidate_label(
                run,
                label="synth_lead",
                out_dir=output,
            )

            self.assertEqual(report["status"], "no-evidence")
            self.assertEqual(report["evidence"]["selected_note_count"], 0)
            self.assertEqual(report["evidence"]["complement_note_count"], 3)
            self.assertEqual(_midi_note_count(output / "requested-label.mid"), 0)
            self.assertEqual(
                _midi_note_count(output / "unexpected-label-complement.mid"), 3
            )

    def test_tampered_immutable_run_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = self._run(root)
            candidate = run / "candidate.json"
            candidate.write_bytes(candidate.read_bytes() + b" ")

            with self.assertRaisesRegex(ValueError, "size/SHA-256"):
                split_ai_candidate_label(
                    run,
                    label="clean_electric_guitar",
                    out_dir=root / "rejected",
                )

    def test_invalid_bpm_is_rejected_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = self._run(root)
            run_path = run / "run.json"
            run_document = json.loads(run_path.read_text(encoding="utf-8"))
            run_document["bpm"] = 0.0
            run_path.write_text(json.dumps(run_document), encoding="utf-8")
            output = root / "invalid-bpm"

            with self.assertRaisesRegex(ValueError, "no valid BPM"):
                split_ai_candidate_label(
                    run,
                    label="clean_electric_guitar",
                    out_dir=output,
                )
            self.assertFalse(output.exists())

    def test_positive_tampered_bpm_is_rejected_against_pinned_midi(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = self._run(root)
            run_path = run / "run.json"
            document = json.loads(run_path.read_text(encoding="utf-8"))
            document["bpm"] = 114.0
            run_path.write_text(json.dumps(document), encoding="utf-8")
            output = root / "tampered-bpm"

            with self.assertRaisesRegex(
                ValueError, "BPM .*pinned candidate MIDI"
            ):
                split_ai_candidate_label(
                    run,
                    label="clean_electric_guitar",
                    out_dir=output,
                )
            self.assertFalse(output.exists())

    def test_output_equal_to_or_nested_in_source_run_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = self._run(root)

            for output in (run, run / "derived", run / "nested" / "derived"):
                with self.subTest(output=output):
                    with self.assertRaisesRegex(
                        ValueError, "output must be outside the source run"
                    ):
                        split_ai_candidate_label(
                            run,
                            label="clean_electric_guitar",
                            out_dir=output,
                        )
                    self.assertFalse((run / "derived").exists())
                    self.assertFalse((run / "nested").exists())

    def test_failed_render_cleans_staging_and_does_not_publish_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = self._run(root)
            output = root / "atomic-output"

            with mock.patch(
                "sunofriend.ai_label_split.write_midi_file",
                side_effect=RuntimeError("synthetic render failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "synthetic render failure"):
                    split_ai_candidate_label(
                        run,
                        label="clean_electric_guitar",
                        out_dir=output,
                    )

            self.assertFalse(output.exists())
            self.assertEqual(
                list(root.glob(".atomic-output.label-split-*")), []
            )

    def test_render_audit_uses_the_writer_operation_at_half_tick_boundaries(self) -> None:
        seconds_per_tick = 60.0 / 113.0 / 480.0
        start_seconds = 12.5 * seconds_per_tick
        worker = _worker_with_notes(
            [
                {
                    "start_seconds": start_seconds,
                    "end_seconds": 30.25 * seconds_per_tick,
                    "pitch": 60.0,
                    "confidence": None,
                    "instrument": "clean_electric_guitar",
                    "velocity": 90,
                    "source_event_id": "half-tick",
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = self._run(root, worker_source=worker)
            output = root / "half-tick"
            report = split_ai_candidate_label(
                run,
                label="clean_electric_guitar",
                out_dir=output,
            )

            render = report["effects"]["midi_rendering"]["requested-label.mid"]
            self.assertEqual(render["rendered_midi_note_count"], 1)
            signature = render["rendered_midi_note_signatures"][0]
            self.assertEqual(signature["start_tick"], 12)
            clip = read_midi_clips(output / "requested-label.mid")[0]
            self.assertEqual(round(clip.notes[0].start_beat * 480), 12)

    def test_fractional_duplicate_and_overlapping_events_are_exact_in_json_but_audited_in_midi(self) -> None:
        worker = _worker_with_notes(
            [
                {
                    "start_seconds": 0.10,
                    "end_seconds": 0.50,
                    "pitch": 59.4,
                    "confidence": None,
                    "instrument": "clean_electric_guitar",
                    "velocity": 70,
                    "source_event_id": "fractional-1",
                },
                {
                    "start_seconds": 0.10,
                    "end_seconds": 0.70,
                    "pitch": 59.4,
                    "confidence": None,
                    "instrument": "clean_electric_guitar",
                    "velocity": 90,
                    "source_event_id": "duplicate-2",
                },
                {
                    "start_seconds": 0.30,
                    "end_seconds": 0.80,
                    "pitch": 59.4,
                    "confidence": None,
                    "instrument": "clean_electric_guitar",
                    "velocity": 80,
                    "source_event_id": "overlap-3",
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = self._run(root, worker_source=worker)
            first_dir = root / "fractional-first"
            report = split_ai_candidate_label(
                run,
                label="clean_electric_guitar",
                out_dir=first_dir,
            )
            second_dir = root / "fractional-second"
            repeated = split_ai_candidate_label(
                run,
                label="clean_electric_guitar",
                out_dir=second_dir,
            )

            partition = json.loads(
                (first_dir / "label-partition.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [row["source_index"] for row in partition["selected"]], [0, 1, 2]
            )
            self.assertEqual(
                [row["note"]["pitch"] for row in partition["selected"]],
                [59.4, 59.4, 59.4],
            )
            render = report["effects"]["midi_rendering"]["requested-label.mid"]
            self.assertEqual(render["source_event_count"], 3)
            self.assertEqual(render["rendered_midi_note_count"], 2)
            self.assertEqual(render["integer_pitch_quantized_event_count"], 3)
            self.assertEqual(
                render["duplicate_same_pitch_tick_onset_collapsed_event_count"], 1
            )
            self.assertEqual(render["same_pitch_overlap_truncated_event_count"], 1)
            self.assertEqual(render["source_event_to_midi_note_count_delta"], -1)
            self.assertFalse(render["lossless_event_render"])
            self.assertNotIn("selected_pitches_changed", report["effects"])
            self.assertEqual(report, repeated)
            for name in (
                "source-request.json",
                "source-candidate.json",
                "unchanged-full-candidate.mid",
                "requested-label.mid",
                "unexpected-label-complement.mid",
                "label-partition.json",
                "ai_label_split.json",
            ):
                self.assertEqual(
                    (first_dir / name).read_bytes(), (second_dir / name).read_bytes()
                )

    def test_cli_shape(self) -> None:
        args = build_parser().parse_args(
            [
                "ai-label-split",
                "/tmp/run",
                "--label",
                "clean_electric_guitar",
                "--out-dir",
                "/tmp/out",
            ]
        )
        self.assertEqual(args.command, "ai-label-split")
        self.assertEqual(args.label, "clean_electric_guitar")


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _midi_note_count(path: Path) -> int:
    return sum(len(clip.notes) for clip in read_midi_clips(path))


if __name__ == "__main__":
    unittest.main()
