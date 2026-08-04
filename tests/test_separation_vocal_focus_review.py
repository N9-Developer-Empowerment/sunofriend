from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import soundfile

from sunofriend._separation_authorised_excerpt import AUTHORISED_EXCERPT_SCHEMA
from sunofriend._separation_authorised_midi_comparison import (
    _document_sha256,
    _sha256,
)
from sunofriend._separation_authorised_role_mapping import (
    AUTHORISED_ROLE_MAPPING_SCHEMA,
)
from sunofriend._separation_melroformer_midi_evaluation import (
    SCHEMA as MELROFORMER_MIDI_SCHEMA,
)
from sunofriend._separation_vocal_focus_review import (
    RESULT_SCHEMA,
    REVIEW_SCHEMA,
    VocalFocusInput,
    _create_private_separated_vocal_focus_review,
    _resolve_private_separated_vocal_focus_review,
)


SAMPLE_RATE = 44_100
FRAMES = SAMPLE_RATE // 2


def _all_false() -> dict[str, bool]:
    return {
        "accepted": False,
        "automatic_selection": False,
        "production_eligible": False,
    }


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _write_pcm24(path: Path, frequency: float, gain: float) -> None:
    timeline = np.arange(FRAMES, dtype=np.float32) / np.float32(SAMPLE_RATE)
    mono = gain * np.sin(2.0 * np.pi * frequency * timeline)
    values = np.stack((mono, mono * np.float32(0.97)), axis=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(path, values, SAMPLE_RATE, subtype="PCM_24")


def _hashed(document: dict[str, object]) -> dict[str, object]:
    document["document_sha256"] = _document_sha256(document)
    return document


def _source(root: Path) -> VocalFocusInput:
    source_path = root / "LOCAL-MODEL-INPUT" / "source-44100.wav"
    kim_path = root / "kim" / "vocals.wav"
    _write_pcm24(source_path, 220.0, 0.18)
    _write_pcm24(kim_path, 330.0, 0.11)

    excerpt_path = root / "authorised-separation-excerpt.json"
    excerpt = _hashed(
        {
            "schema": AUTHORISED_EXCERPT_SCHEMA,
            "status": "complete_review_required",
            "evidence_scope": "private_development_only",
            "excerpt": {
                "start_seconds": 10.0,
                "end_seconds": 10.5,
                "geometry": {
                    "channels": 2,
                    "duration_seconds": 0.5,
                    "frames": FRAMES,
                    "sample_rate": SAMPLE_RATE,
                },
            },
            "artifacts": {
                "LOCAL-MODEL-INPUT/source-44100.wav": {
                    "bytes": source_path.stat().st_size,
                    "sha256": _sha256(source_path),
                }
            },
            "permissions": _all_false(),
            "effects": {"source_audio_mutated": False},
        }
    )
    _write_json(excerpt_path, excerpt)

    evaluation_path = root / "private-melroformer-vocal-midi-evaluation.json"
    evaluation = _hashed(
        {
            "schema": MELROFORMER_MIDI_SCHEMA,
            "status": "complete_observation_not_acceptance",
            "evidence_scope": "private_development_only",
            "worker": {
                "candidate_id": "mlx-melroformer-kim-vocal-2",
                "authorisation_report_sha256": _sha256(excerpt_path),
                "pcm24_quarantine_bound_to_model_worker": True,
                "vocal_pcm24_bytes": kim_path.stat().st_size,
                "vocal_pcm24_sha256": _sha256(kim_path),
            },
            "candidate": {
                "primary": {"independent_evaluation": {"stem_path": str(kim_path)}}
            },
            "permissions": _all_false(),
            "effects": {
                "source_audio_mutated": False,
                "source_graph_mutated": False,
                "worker_rerun": False,
            },
        }
    )
    _write_json(evaluation_path, evaluation)

    mapping_root = root / "mapping"
    groups: dict[str, object] = {}
    for index, provider_id in enumerate(("moises", "suno-a", "suno-b"), start=1):
        path = mapping_root / "ROLE-GROUPS" / provider_id / "vocals.wav"
        _write_pcm24(path, 400.0 + index * 50.0, 0.05 + index * 0.015)
        groups[provider_id] = {
            "vocals": {
                "artifact": {
                    "path": f"ROLE-GROUPS/{provider_id}/vocals.wav",
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            }
        }
    mapping_path = mapping_root / "authorised-role-mapping.json"
    mapping = _hashed(
        {
            "schema": AUTHORISED_ROLE_MAPPING_SCHEMA,
            "status": "complete_review_required",
            "evidence_scope": "private_development_only",
            "source_excerpt": {
                "track_id": "track-one",
                "start_seconds": 10.0,
                "end_seconds": 10.5,
                "report_sha256": _sha256(excerpt_path),
                "document_sha256": excerpt["document_sha256"],
            },
            "groups": groups,
            "permissions": _all_false(),
            "effects": {"source_graph_mutated": False},
        }
    )
    _write_json(mapping_path, mapping)
    return VocalFocusInput(
        track_id="track-one",
        authorised_excerpt=excerpt_path,
        candidate_midi_evaluation=evaluation_path,
        role_mapping=mapping_path,
        provider_ids=("moises", "suno-a", "suno-b"),
    )


def _create(root: Path) -> dict[str, object]:
    with patch(
        "sunofriend._separation_vocal_focus_review.secrets.token_bytes",
        return_value=b"v" * 32,
    ):
        return _create_private_separated_vocal_focus_review(
            _source(root / "inputs"),
            focus="The extended robotic held vocal note near the end of the excerpt.",
            out_dir=root / "review",
        )


def _reviewed(seed: dict[str, object]) -> dict[str, object]:
    reviewed = json.loads(json.dumps(seed))
    reviewed["status"] = "reviewed"
    unit = reviewed["unit"]
    unit["heard"] = {key: True for key in unit["heard"]}
    for index, slot in enumerate(unit["candidate_slots"]):
        unit["ratings"][slot] = {
            "focus_retention": (
                "substantially_complete" if index == 0 else "partially_complete"
            ),
            "non_vocal_bleed": "low",
            "artefacts": "noticeable",
            "useful_for_focus": "yes" if index < 2 else "no",
        }
    unit["notes"] = "The held sound survives in two candidates."
    reviewed["summary"]["reviewed_candidate_count"] = len(unit["candidate_slots"])
    return reviewed


def test_creates_and_resolves_blind_multi_candidate_focus_review(
    tmp_path: Path,
) -> None:
    created = _create(tmp_path)
    package = Path(str(created["out_dir"]))
    seed = json.loads(Path(str(created["seed"])).read_text())
    answer = json.loads(Path(str(created["answer_key"])).read_text())
    html = Path(str(created["html"])).read_text()

    assert created["schema"] == REVIEW_SCHEMA
    assert seed["summary"] == {
        "candidate_count": 4,
        "reviewed_candidate_count": 0,
    }
    assert len(seed["unit"]["candidate_slots"]) == 4
    assert len(list((package / "audio").glob("*.wav"))) == 5
    assert "kim-vocal-2" not in html
    assert "provider-suno-b-broad-vocals" not in html
    assert set(answer["mapping"].values()) == {
        "kim-vocal-2",
        "provider-moises-broad-vocals",
        "provider-suno-a-broad-vocals",
        "provider-suno-b-broad-vocals",
    }
    rms = [
        seed["unit"]["candidates"][slot]["rms_dbfs"]
        for slot in seed["unit"]["candidate_slots"]
    ]
    assert max(rms) - min(rms) <= 0.05

    reviewed_path = tmp_path / "reviewed.json"
    _write_json(reviewed_path, _reviewed(seed))
    result = _resolve_private_separated_vocal_focus_review(
        reviewed_path,
        package_dir=package,
        out=tmp_path / "resolved.json",
    )

    assert result["schema"] == RESULT_SCHEMA
    assert result["status"] == "complete_review_no_activation"
    assert len(result["ratings_by_method"]) == 4
    assert len(result["results"]["useful_for_focus"]) == 2
    assert result["source_binding"]["source_track_id"] == "track-one"
    assert result["interpretation"]["winner_selected"] is False
    assert not any(result["permissions"].values())
    assert not any(result["effects"].values())


def test_rejects_incomplete_or_changed_focus_review(tmp_path: Path) -> None:
    created = _create(tmp_path)
    package = Path(str(created["out_dir"]))
    seed = json.loads(Path(str(created["seed"])).read_text())
    reviewed = _reviewed(seed)

    reviewed["unit"]["heard"]["candidate_a"] = False
    incomplete = tmp_path / "incomplete.json"
    _write_json(incomplete, reviewed)
    with pytest.raises(ValueError, match="incomplete"):
        _resolve_private_separated_vocal_focus_review(
            incomplete,
            package_dir=package,
            out=tmp_path / "not-written.json",
        )

    reviewed = _reviewed(seed)
    reviewed["focus"] = "A different event."
    changed = tmp_path / "changed.json"
    _write_json(changed, reviewed)
    with pytest.raises(ValueError, match="immutable evidence"):
        _resolve_private_separated_vocal_focus_review(
            changed,
            package_dir=package,
            out=tmp_path / "also-not-written.json",
        )


def test_rejects_changed_audio_and_answer_key(tmp_path: Path) -> None:
    created = _create(tmp_path)
    package = Path(str(created["out_dir"]))
    seed = json.loads(Path(str(created["seed"])).read_text())
    reviewed_path = tmp_path / "reviewed.json"
    _write_json(reviewed_path, _reviewed(seed))

    candidate = package / seed["unit"]["candidates"]["candidate_a"]["audio"]
    candidate.write_bytes(candidate.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="audio changed"):
        _resolve_private_separated_vocal_focus_review(
            reviewed_path,
            package_dir=package,
            out=tmp_path / "not-written.json",
        )

    created = _create(tmp_path / "second")
    package = Path(str(created["out_dir"]))
    seed = json.loads(Path(str(created["seed"])).read_text())
    reviewed_path = tmp_path / "second-reviewed.json"
    _write_json(reviewed_path, _reviewed(seed))
    answer_path = Path(str(created["answer_key"]))
    answer = json.loads(answer_path.read_text())
    original = answer["mapping"]["candidate_a"]
    answer["mapping"]["candidate_a"] = next(
        method for method in answer["mapping"].values() if method != original
    )
    _write_json(answer_path, answer)
    with pytest.raises(ValueError, match="answer key changed"):
        _resolve_private_separated_vocal_focus_review(
            reviewed_path,
            package_dir=package,
            out=tmp_path / "second-not-written.json",
        )


def test_rejects_invalid_focus_and_duplicate_providers(tmp_path: Path) -> None:
    source = _source(tmp_path / "inputs")
    with pytest.raises(ValueError, match="1-500"):
        _create_private_separated_vocal_focus_review(
            source,
            focus=" ",
            out_dir=tmp_path / "review",
        )
    duplicate = VocalFocusInput(
        track_id=source.track_id,
        authorised_excerpt=source.authorised_excerpt,
        candidate_midi_evaluation=source.candidate_midi_evaluation,
        role_mapping=source.role_mapping,
        provider_ids=("moises", "moises"),
    )
    with pytest.raises(ValueError, match="unique provider"):
        _create_private_separated_vocal_focus_review(
            duplicate,
            focus="A held vocal note.",
            out_dir=tmp_path / "other-review",
        )
