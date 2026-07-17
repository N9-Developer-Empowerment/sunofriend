from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sunofriend.sample_ab_review import (
    SAMPLE_AB_RESULT_SCHEMA,
    SAMPLE_AB_REVIEW_SCHEMA,
    create_sample_ab_review,
    resolve_sample_ab_review,
)


class SampleAbReviewTests(unittest.TestCase):
    def test_blind_review_is_repeatable_and_resolves_explicit_choices(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snare = _write_pack(root / "snare", kind="snare", with_sweep=False)
            toms = _write_pack(root / "toms", kind="toms", with_sweep=True)

            first = create_sample_ab_review(
                [snare, toms], out_dir=root / "review-first"
            )
            second = create_sample_ab_review(
                [snare, toms], out_dir=root / "review-second"
            )

            self.assertEqual(first["schema"], SAMPLE_AB_REVIEW_SCHEMA)
            self.assertEqual(first["unit_count"], 2)
            self.assertEqual(first["velocity_sweep_unit_count"], 1)
            self.assertEqual(first["effects"]["review_choices_inferred"], 0)
            first_seed = _read(Path(first["seed"]))
            self.assertEqual(first_seed["status"], "unreviewed")
            self.assertTrue(first_seed["blind"])
            self.assertTrue(all(row["choice"] is None for row in first_seed["units"]))
            first_key = _read(Path(first["answer_key"]))
            second_key = _read(Path(second["answer_key"]))
            self.assertEqual(first_key["units"], second_key["units"])
            page = Path(first["html"]).read_text(encoding="utf-8")
            self.assertNotIn('"candidate_a": "v2"', page)
            self.assertNotIn('"candidate_a": "v3"', page)
            self.assertIn("JSON.stringify(review,null,2)+'\\n'", page)

            for unit in first_seed["units"]:
                unit["choice"] = "candidate_a"
                unit["notes"] = "explicit fixture choice"
            first_seed["status"] = "reviewed"
            first_seed["summary"]["reviewed_unit_count"] = 2
            reviewed = root / "sample_ab_review.reviewed.json"
            _write(reviewed, first_seed)
            result_path = root / "sample_ab_result.json"
            result = resolve_sample_ab_review(reviewed, out=result_path)

            expected = {
                row["unit_id"]: row["candidate_a"] for row in first_key["units"]
            }
            self.assertEqual(result["schema"], SAMPLE_AB_RESULT_SCHEMA)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(
                {row["unit_id"]: row["outcome"] for row in result["units"]},
                expected,
            )
            self.assertEqual(result["effects"]["sampler_zones_changed"], 0)
            self.assertTrue(result_path.is_file())

    def test_resolve_refuses_an_unreviewed_seed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = _write_pack(root / "pack", kind="hat", with_sweep=False)
            review = create_sample_ab_review([pack], out_dir=root / "review")

            with self.assertRaisesRegex(ValueError, "not complete"):
                resolve_sample_ab_review(
                    review["seed"], out=root / "must-not-exist.json"
                )

    def test_resolve_refuses_changed_page_audio_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = _write_pack(root / "pack", kind="snare", with_sweep=False)
            review = create_sample_ab_review([pack], out_dir=root / "review")
            exported = _read(Path(review["seed"]))
            exported["status"] = "reviewed"
            exported["summary"]["reviewed_unit_count"] = 1
            exported["units"][0]["choice"] = "candidate_a"
            exported["units"][0]["candidate_a"]["sha256"] = "changed"
            changed = root / "changed.reviewed.json"
            _write(changed, exported)

            with self.assertRaisesRegex(ValueError, "audio references changed"):
                resolve_sample_ab_review(changed, out=root / "must-not-exist.json")


def _write_pack(root: Path, *, kind: str, with_sweep: bool) -> Path:
    (root / "baseline-v2").mkdir(parents=True)
    source = root / "garageband-performance-source.wav"
    v2 = root / "baseline-v2" / "garageband-performance-v2.wav"
    v3 = root / "garageband-performance-v3.wav"
    source.write_bytes(f"{kind}-source".encode())
    v2.write_bytes(f"{kind}-v2".encode())
    v3.write_bytes(f"{kind}-v3".encode())
    sweep = None
    if with_sweep:
        sweep_v2 = root / "baseline-v2" / "garageband-velocity-sweep-v2.wav"
        sweep_v3 = root / "garageband-velocity-sweep-v3.wav"
        sweep_v2.write_bytes(f"{kind}-sweep-v2".encode())
        sweep_v3.write_bytes(f"{kind}-sweep-v3".encode())
        sweep = {
            "v2_preview_wav": "baseline-v2/garageband-velocity-sweep-v2.wav",
            "v2_preview_sha256": _hash(sweep_v2),
            "v3_preview_wav": "garageband-velocity-sweep-v3.wav",
            "v3_preview_sha256": _hash(sweep_v3),
            "units": [{"pitch": 45, "accepted_boundary": 107}],
        }
    report = {
        "schema": "sunofriend.sample-instrument-v3.v1",
        "status": "complete",
        "kind": kind,
        "instrument_name": f"Fixture {kind}",
        "review": {"sha256": f"{kind}-review"},
        "performance_audition": {
            "source_reference_wav": "garageband-performance-source.wav",
            "source_reference_sha256": _hash(source),
            "v2_preview_wav": "baseline-v2/garageband-performance-v2.wav",
            "v2_preview_sha256": _hash(v2),
            "v3_preview_wav": "garageband-performance-v3.wav",
            "v3_preview_sha256": _hash(v3),
            "source_midi_sha256": f"{kind}-midi",
            "source_midi_mutated": False,
            "bars": 8,
            "initial_bpm": 119.0,
            "note_count": 12,
            "selected_pitches": [38, 40],
            "velocity_min": 42,
            "velocity_max": 120,
        },
        "velocity_sweep": sweep,
    }
    _write(root / "sample_pack_v3.json", report)
    return root


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    unittest.main()
