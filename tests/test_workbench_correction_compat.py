from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sunofriend.clip import (
    ChordEvent,
    ClipNote,
    Instrument,
    KeySignature,
    MidiClip,
    Provenance,
    TempoMap,
    TempoPoint,
    TimeSignature,
)
from sunofriend.library import ClipLibrary
from sunofriend.workbench_clips import WorkbenchClipService
from sunofriend.workbench_correction import WorkbenchClipCorrectionService


_PARENT_CREATED_AT = "2026-07-22T10:00:00.000Z"
_CHILD_CREATED_AT = "2026-07-22T10:00:01.000Z"
_EXPECTED_WINDOW_SHA256 = (
    "8bfe1ee3a80fe6bde2840417fbe4d5a4ade14a419c72bc6a0381831d658d0e58"
)
_EXPECTED_PROJECTION_SHA256 = (
    "4a7e9c0eb3455650431b9a96904233ba2905488f4c0fd41fa36c83007b86ca16"
)
_EXPECTED_INTENT_SHA256 = (
    "d8ed6bfc23d5115a98af63c93d3d1c1b649c8bba2180ecafa468162eb0f860f5"
)
_EXPECTED_CHILD_CLIP_ID = (
    "sf-correction-d8ed6bfc23d5115a98af63c93d3d1c1b649c8bba2180ecafa468162eb0f860f5"
)
_EXPECTED_CHILD_CANONICAL_SHA256 = (
    "094eed8e835a25f921454a5a4bc1338e2e456190923a90cdae28a92e61a7b8a9"
)
_EXPECTED_RECIPE_PARAMETER_KEYS = (
    "changes",
    "contract_version",
    "correction",
    "intent_sha256",
    "library_state_sha256",
    "parent_object_sha256",
    "ticks_per_beat",
    "window",
    "window_sha256",
)
_EXPECTED_RESTART_SUMMARY_SHA256 = (
    "1fe64476e2e4e726639b2ea71c415dac675237ec57e08cd6d42be78d73f6108d"
)


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _set_created_at(library_root: Path, clip_id: str, created_at: str) -> None:
    with sqlite3.connect(library_root / "catalog.sqlite3") as connection:
        connection.execute(
            "UPDATE clips SET created_at = ? WHERE clip_id = ?",
            (created_at, clip_id),
        )


def _parent_clip() -> MidiClip:
    tempo = TempoMap(
        tempo_points=(TempoPoint(0.0, 120.0), TempoPoint(2.0, 96.0)),
    )
    return MidiClip(
        title="Pitch compatibility fixture",
        tempo_map=tempo,
        time_signature=TimeSignature(4, 4),
        instrument=Instrument("keys", 4, 0, ("Electric Piano",)),
        notes=(
            ClipNote(
                0.0,
                1.0,
                60,
                81,
                0.0,
                0.5,
                microtiming_seconds=0.0125,
                end_microtiming_seconds=0.00625,
                release_velocity=37,
                articulation="accent",
            ),
            ClipNote(
                1.5,
                0.5,
                64,
                96,
                0.75,
                1.0,
                microtiming_seconds=-0.00625,
            ),
            ClipNote(2.25, 0.75, 67, 104, 1.15625, 1.625),
        ),
        key=KeySignature("C", "major"),
        chords=(
            ChordEvent(0.0, 2.0, "C", 0.0, 1.0),
            ChordEvent(2.0, 2.0, "G7", 1.0, 2.25),
        ),
        provenance=Provenance(
            source_uri="/Users/private/pitch-compatibility.wav",
            source_stem="/Users/private/pitch-compatibility.wav",
            converter="compatibility-fixture",
            details={"timing_mode": "musical"},
        ),
        clip_id="phase63a-pitch-compat-parent",
        tags=("compatibility", "phase6.3a"),
    )


def _acceptance(root: Path) -> tuple[Path, Path]:
    pack = root / "accepted-pack.zip"
    pack.write_bytes(b"phase-6.3a-pitch-compatibility-pack")
    pack_sha256 = hashlib.sha256(pack.read_bytes()).hexdigest()
    result = root / "acceptance.json"
    result.write_text(
        json.dumps(
            {
                "schema": (
                    "sunofriend.workbench-garageband-pack-acceptance-result.v1"
                ),
                "operation": "garageband-pack-acceptance-resolve",
                "status": "passed",
                "phase6_read_only_clip_entry_ready": True,
                "explicit_hybrid_construction_ready": False,
                "pack": {
                    "name": "sunofriend-garageband-pack.zip",
                    "bytes": pack.stat().st_size,
                    "sha256": pack_sha256,
                },
                "developer_evidence": {"code_binding_sha256": "a" * 64},
                "tutorial": {"completed": True, "slide_count": 8},
                "quiz": {
                    "question_count": 10,
                    "score": 10,
                    "pass_score": 10,
                    "passed": True,
                },
                "acceptance_checks": [
                    {
                        "check_id": "garageband-pack",
                        "outcome": "passed",
                        "pass_count": 6,
                        "issue_count": 0,
                        "cannot_tell_count": 0,
                    },
                    {
                        "check_id": "local-usability",
                        "outcome": "passed",
                        "pass_count": 6,
                        "issue_count": 0,
                        "cannot_tell_count": 0,
                    },
                ],
                "remaining_local_studio_acceptance_gates": [],
                "effects": {
                    "tutorial_changed_project": False,
                    "quiz_selected_candidate": False,
                    "feedback_recorded": False,
                    "musical_selection_changed": False,
                    "pack_basket_changed": False,
                    "midi_mutated": False,
                    "candidate_promoted": False,
                    "default_changed": False,
                    "data_submitted": False,
                    "phase6_started_automatically": False,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return pack, result


def _open_services(
    *,
    root: Path,
    library_root: Path,
    cache_name: str,
) -> tuple[WorkbenchClipService, WorkbenchClipCorrectionService]:
    pack, result = _acceptance(root)
    clip_service = WorkbenchClipService.open(
        acceptance_result_path=result,
        garageband_pack_path=pack,
        library_root=library_root,
        cache_root=root / cache_name,
    )
    correction_service = WorkbenchClipCorrectionService.open(
        clip_service=clip_service,
        library_root=library_root,
    )
    return clip_service, correction_service


def _capture_published_pitch_v1() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        library_root = root / "library"
        parent = _parent_clip()
        ClipLibrary(library_root).add(parent)
        _set_created_at(library_root, parent.clip_id, _PARENT_CREATED_AT)

        with patch(
            "sunofriend.workbench_clips.verify_garageband_pack_archive",
            return_value={"status": "verified"},
        ):
            clip_service, corrections = _open_services(
                root=root,
                library_root=library_root,
                cache_name="first-cache",
            )
            detail = clip_service.detail(parent.clip_id)
            window_request = {
                "parent_clip_id": parent.clip_id,
                "parent_object_sha256": detail["clip"]["object_sha256"],
                "library_state_sha256": detail["library_state_sha256"],
                "window": {"start_tick": 0, "end_tick": 1440},
            }
            window = corrections.window(window_request)
            preview_request = {
                **window_request,
                "window_sha256": window["window_sha256"],
                "correction": {
                    "kind": "pitch_patch",
                    "changes": [
                        {
                            "note_ref": window["notes"][0]["note_ref"],
                            "target_pitch": 62,
                        }
                    ],
                },
            }
            preview = corrections.preview(preview_request)
            result = corrections.create(
                {
                    "action": "create",
                    **preview_request,
                    "projection_sha256": preview["projection_sha256"],
                }
            )
            child = ClipLibrary(library_root, read_only=True).get(
                result["child"]["clip_id"]
            )

        _set_created_at(library_root, child.clip_id, _CHILD_CREATED_AT)
        with patch(
            "sunofriend.workbench_clips.verify_garageband_pack_archive",
            return_value={"status": "verified"},
        ):
            _restarted_clips, restarted_corrections = _open_services(
                root=root,
                library_root=library_root,
                cache_name="restart-cache",
            )
            restart_summary = restarted_corrections.correction_summary(child.clip_id)

        assert child.transform_recipe is not None
        assert restart_summary is not None
        return {
            "window_sha256": window["window_sha256"],
            "projection_sha256": preview["projection_sha256"],
            "intent_sha256": preview["intent_sha256"],
            "child_clip_id": child.clip_id,
            "child_canonical_sha256": hashlib.sha256(
                child.canonical_bytes()
            ).hexdigest(),
            "recipe_parameter_keys": sorted(
                child.transform_recipe.parameters_dict
            ),
            "restart_summary": restart_summary,
            "restart_summary_sha256": _canonical_sha256(restart_summary),
        }


class WorkbenchClipCorrectionCompatibilityTests(unittest.TestCase):
    def test_published_pitch_v1_bytes_and_restart_projection_are_frozen(self) -> None:
        captured = _capture_published_pitch_v1()
        self.assertEqual(captured["window_sha256"], _EXPECTED_WINDOW_SHA256)
        self.assertEqual(
            captured["projection_sha256"], _EXPECTED_PROJECTION_SHA256
        )
        self.assertEqual(captured["intent_sha256"], _EXPECTED_INTENT_SHA256)
        self.assertEqual(captured["child_clip_id"], _EXPECTED_CHILD_CLIP_ID)
        self.assertEqual(
            captured["child_canonical_sha256"],
            _EXPECTED_CHILD_CANONICAL_SHA256,
        )
        self.assertEqual(
            tuple(captured["recipe_parameter_keys"]),
            _EXPECTED_RECIPE_PARAMETER_KEYS,
        )
        self.assertEqual(
            captured["restart_summary_sha256"],
            _EXPECTED_RESTART_SUMMARY_SHA256,
        )
        self.assertEqual(
            _canonical_sha256(captured["restart_summary"]),
            _EXPECTED_RESTART_SUMMARY_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
