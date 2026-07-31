from __future__ import annotations

import json
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1] / "stem_examples"


def _document(name: str) -> dict:
    return json.loads((_ROOT / name).read_text(encoding="utf-8"))


def test_private_reference_manifest_cannot_imply_processing_authority() -> None:
    document = _document("private-reference-corpus.json")

    assert document["schema"] == (
        "sunofriend.private-reference-separation-corpus.v1"
    )
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
    assert document["inventory"]["original_files"] == 5
    assert document["inventory"]["moises_files"] == 85
    assert document["inventory"]["suno_packs"] == 0

    ids = [track["id"] for track in document["tracks"]]
    directories = [track["directory"] for track in document["tracks"]]
    assert len(ids) == len(set(ids))
    assert len(directories) == len(set(directories))
    assert all(
        track["evaluation_state"].startswith(("awaiting_", "blocked_"))
        for track in document["tracks"]
    )
    assert all("evaluation_excerpt" not in track for track in document["tracks"])


def test_authorised_and_private_reference_manifests_are_disjoint() -> None:
    authorised = _document("corpus.json")
    private = _document("private-reference-corpus.json")

    authorised_directories = {track["directory"] for track in authorised["tracks"]}
    private_directories = {track["directory"] for track in private["tracks"]}
    assert authorised_directories.isdisjoint(private_directories)
    assert authorised["permission"]["authority"] == "creator_and_copyright_holder"
    assert private["permission"]["status"] == "not_recorded_in_manifest"
