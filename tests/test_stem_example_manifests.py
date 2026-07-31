from __future__ import annotations

import json
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1] / "stem_examples"


def _document(name: str) -> dict:
    return json.loads((_ROOT / name).read_text(encoding="utf-8"))


def test_private_reference_manifest_cannot_imply_processing_authority() -> None:
    document = _document("private-reference-corpus.json")

    assert document["schema"] == ("sunofriend.private-reference-separation-corpus.v1")
    assert document["status"] == "local_audio_not_committed_inventory_only"
    assert document["permission"] == {
        "status": "not_recorded_in_manifest",
        "directory_presence_is_not_processing_authority": True,
        "repository_distribution": False,
        "public_demo_use": False,
        "required_before_evaluation": (
            "record track-specific authority for private local processing"
        ),
    }
    assert document["provider_derived_audio"]["local_evaluation_enabled"] is False
    assert document["inventory"]["tracks"] == len(document["tracks"])
    assert document["inventory"]["audio_files"] == 90
    assert document["inventory"]["audio_bytes"] == 3022887544
    assert document["inventory"]["original_files"] == 5
    assert document["inventory"]["moises_files"] == 85
    assert document["inventory"]["suno_packs"] == 0

    ids = [track["id"] for track in document["tracks"]]
    directories = [track["directory"] for track in document["tracks"]]
    assert len(ids) == len(set(ids))
    assert len(directories) == len(set(directories))
    assert all(
        track["evaluation_state"].startswith(("awaiting_", "blocked_"))
        or (
            track["evaluation_state"]
            in {"ready_for_private_excerpt_selection", "private_excerpt_staged"}
            and track.get("private_processing_authority", {}).get("status")
            == "user_authorised"
        )
        for track in document["tracks"]
    )
    assert all(
        "evaluation_excerpt" not in track
        or track.get("private_processing_authority", {}).get("status")
        == "user_authorised"
        for track in document["tracks"]
    )

    mauvais = next(
        track for track in document["tracks"] if track["id"] == "mauvais-djo-pile"
    )
    assert mauvais["directory"] == "Mauvais djo - 06. Pilé-Bb minor-130bpm-440hz"
    assert mauvais["bpm"] == 130
    assert mauvais["original"]["duration_seconds"] == 156.076916
    assert mauvais["moises"]["musical_stem_duration_seconds"] == 156.076916
    assert mauvais["evaluation_state"] == "private_excerpt_staged"
    assert mauvais["private_processing_authority"] == {
        "status": "user_authorised",
        "scope": "private_local_evaluation_only",
        "recorded_on": "2026-07-31",
        "repository_distribution": False,
        "public_demo_use": False,
    }
    assert mauvais["evaluation_excerpt"]["start_seconds"] == 33.0
    assert mauvais["evaluation_excerpt"]["end_seconds"] == 48.0
    assert mauvais["evaluation_excerpt"]["selection_evidence"] == {
        "activity_score": 0.644693,
        "lower_quartile_activity": 0.553807,
        "median_activity": 0.81348,
        "group_mean_activity": {
            "bass": 0.433445,
            "drums": 0.787232,
            "other": 0.801165,
            "vocals": 0.885918,
        },
        "human_listening_selection": False,
    }
    assert mauvais["evaluation_excerpt"]["provider_packs"] == [
        {
            "id": "moises",
            "directory": "MOISES",
            "exclude_filename_contains": ["metronome"],
        }
    ]
    assert mauvais["read_only_alignment_audit"] == {
        "checked_on": "2026-07-31",
        "musical_stems_geometry_matches_original": True,
        "recorded_zero_sum_correlation": 0.997537,
        "best_10ms_envelope_lag_seconds": 0.0,
        "best_10ms_envelope_correlation": 0.998738,
        "stem_sum_level_delta_db": -0.059,
        "source_minus_sum_snr_db": 23.064,
        "metronome_is_timing_evidence_only": True,
    }


def test_authorised_and_private_reference_manifests_are_disjoint() -> None:
    authorised = _document("corpus.json")
    private = _document("private-reference-corpus.json")

    authorised_directories = {track["directory"] for track in authorised["tracks"]}
    private_directories = {track["directory"] for track in private["tracks"]}
    assert authorised_directories.isdisjoint(private_directories)
    assert authorised["permission"]["authority"] == "creator_and_copyright_holder"
    assert private["permission"]["status"] == "not_recorded_in_manifest"
