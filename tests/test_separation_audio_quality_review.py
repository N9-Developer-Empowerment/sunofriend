from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import soundfile

from sunofriend._separation_audio_quality_review import (
    AudioQualityInput,
    RESULT_SCHEMA,
    REVIEW_SCHEMA,
    _create_private_separated_audio_quality_review,
    _resolve_private_separated_audio_quality_review,
)
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


SAMPLE_RATE = 44_100
FRAMES = SAMPLE_RATE // 2


def _all_false() -> dict[str, bool]:
    return {
        "accepted": False,
        "automatic_selection": False,
        "production_eligible": False,
    }


def _write_json(path: Path, value: dict[str, object]) -> None:
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


def _case(root: Path, track_id: str, frequency: float) -> AudioQualityInput:
    root.mkdir()
    source_path = root / "LOCAL-MODEL-INPUT" / "source-44100.wav"
    candidate_path = root / "candidate" / "vocals.wav"
    provider_path = root / "mapping" / "ROLE-GROUPS" / "moises" / "vocals.wav"
    _write_pcm24(source_path, frequency, 0.15)
    _write_pcm24(candidate_path, frequency * 1.5, 0.11)
    _write_pcm24(provider_path, frequency * 1.45, 0.07)

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

    candidate_report = root / "private-melroformer-vocal-midi-evaluation.json"
    candidate = _hashed(
        {
            "schema": MELROFORMER_MIDI_SCHEMA,
            "status": "complete_observation_not_acceptance",
            "evidence_scope": "private_development_only",
            "worker": {
                "candidate_id": "mlx-melroformer-kim-vocal-2",
                "authorisation_report_sha256": _sha256(excerpt_path),
                "pcm24_quarantine_bound_to_model_worker": True,
                "vocal_pcm24_bytes": candidate_path.stat().st_size,
                "vocal_pcm24_sha256": _sha256(candidate_path),
            },
            "candidate": {
                "primary": {
                    "independent_evaluation": {
                        "stem_path": str(candidate_path),
                    }
                }
            },
            "permissions": _all_false(),
            "effects": {
                "source_audio_mutated": False,
                "source_graph_mutated": False,
                "worker_rerun": False,
            },
        }
    )
    _write_json(candidate_report, candidate)

    mapping_path = root / "mapping" / "authorised-role-mapping.json"
    mapping = _hashed(
        {
            "schema": AUTHORISED_ROLE_MAPPING_SCHEMA,
            "status": "complete_review_required",
            "evidence_scope": "private_development_only",
            "source_excerpt": {
                "track_id": track_id,
                "start_seconds": 10.0,
                "end_seconds": 10.5,
                "report_sha256": _sha256(excerpt_path),
                "document_sha256": excerpt["document_sha256"],
            },
            "groups": {
                "moises": {
                    "vocals": {
                        "artifact": {
                            "path": "ROLE-GROUPS/moises/vocals.wav",
                            "bytes": provider_path.stat().st_size,
                            "sha256": _sha256(provider_path),
                        }
                    }
                }
            },
            "permissions": _all_false(),
            "effects": {"source_graph_mutated": False},
        }
    )
    _write_json(mapping_path, mapping)
    return AudioQualityInput(
        track_id=track_id,
        authorised_excerpt=excerpt_path,
        candidate_midi_evaluation=candidate_report,
        role_mapping=mapping_path,
    )


def _create(root: Path) -> dict[str, object]:
    cases = (
        _case(root / "one", "track-one", 220.0),
        _case(root / "two", "track-two", 330.0),
    )
    with patch(
        "sunofriend._separation_audio_quality_review.secrets.token_bytes",
        return_value=b"q" * 32,
    ):
        return _create_private_separated_audio_quality_review(
            cases, out_dir=root / "review"
        )


def _reviewed(seed: dict[str, object]) -> dict[str, object]:
    reviewed = json.loads(json.dumps(seed))
    reviewed["status"] = "reviewed"
    reviewed["summary"]["reviewed_unit_count"] = len(reviewed["units"])
    for unit in reviewed["units"]:
        unit["heard"] = {
            "source": True,
            "candidate_a": True,
            "candidate_b": True,
        }
        unit["ratings"] = {
            "candidate_a": {
                "vocal_retention": "substantially_complete",
                "non_vocal_bleed": "low",
                "artefacts": "noticeable",
            },
            "candidate_b": {
                "vocal_retention": "partially_complete",
                "non_vocal_bleed": "noticeable",
                "artefacts": "low",
            },
        }
        unit["preference"] = "candidate_a"
        unit["notes"] = "Useful private evidence."
    return reviewed


def test_creates_blind_two_song_audio_review_and_resolves(tmp_path: Path) -> None:
    created = _create(tmp_path)
    package = Path(str(created["out_dir"]))
    seed = json.loads(Path(str(created["seed"])).read_text())
    answer = json.loads(Path(str(created["answer_key"])).read_text())
    html = Path(str(created["html"])).read_text()

    assert created["schema"] == REVIEW_SCHEMA
    assert seed["summary"] == {"unit_count": 2, "reviewed_unit_count": 0}
    assert len(seed["units"]) == 2
    assert "kim-vocal-2" not in html
    assert "provider-moises-broad-vocals" not in html
    assert set(answer["units"][0]["mapping"]) == {
        "candidate_a",
        "candidate_b",
    }
    assert package.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o077 == 0 for path in package.rglob("*"))
    for unit in seed["units"]:
        assert abs(
            unit["candidate_a"]["rms_dbfs"]
            - unit["candidate_b"]["rms_dbfs"]
        ) <= 0.05
        assert unit["source"]["rms_dbfs"] != unit["candidate_a"]["rms_dbfs"]

    reviewed_path = tmp_path / "reviewed.json"
    _write_json(reviewed_path, _reviewed(seed))
    result = _resolve_private_separated_audio_quality_review(
        reviewed_path,
        package_dir=package,
        out=tmp_path / "resolved.json",
    )

    assert result["schema"] == RESULT_SCHEMA
    assert result["status"] == "complete_review_no_activation"
    assert result["unit_count"] == 2
    assert {unit["resolved_preference"] for unit in result["units"]} <= {
        "kim-vocal-2",
        "provider-moises-broad-vocals",
    }
    assert not any(result["permissions"].values())
    assert not any(result["effects"].values())


def test_rejects_incomplete_review_and_changed_audio(tmp_path: Path) -> None:
    created = _create(tmp_path)
    package = Path(str(created["out_dir"]))
    seed = json.loads(Path(str(created["seed"])).read_text())
    incomplete = tmp_path / "incomplete.json"
    _write_json(incomplete, seed)
    with pytest.raises(ValueError, match="incomplete"):
        _resolve_private_separated_audio_quality_review(
            incomplete,
            package_dir=package,
            out=tmp_path / "not-created.json",
        )

    audio = package / seed["units"][0]["candidate_a"]["audio"]
    audio.write_bytes(audio.read_bytes() + b"changed")
    reviewed = tmp_path / "reviewed.json"
    _write_json(reviewed, _reviewed(seed))
    with pytest.raises(ValueError, match="listening evidence changed"):
        _resolve_private_separated_audio_quality_review(
            reviewed,
            package_dir=package,
            out=tmp_path / "also-not-created.json",
        )


def test_rejects_changed_immutable_review_and_duplicate_cases(tmp_path: Path) -> None:
    created = _create(tmp_path)
    package = Path(str(created["out_dir"]))
    seed = json.loads(Path(str(created["seed"])).read_text())
    reviewed = _reviewed(seed)
    reviewed["units"][0]["source_seconds"] = [0.0, 0.5]
    reviewed_path = tmp_path / "changed.json"
    _write_json(reviewed_path, reviewed)
    with pytest.raises(ValueError, match="immutable evidence"):
        _resolve_private_separated_audio_quality_review(
            reviewed_path,
            package_dir=package,
            out=tmp_path / "not-created.json",
        )

    duplicate = _case(tmp_path / "duplicate", "track-one", 440.0)
    with pytest.raises(ValueError, match="track IDs must be unique"):
        _create_private_separated_audio_quality_review(
            [duplicate, duplicate], out_dir=tmp_path / "duplicate-review"
        )


def test_rejects_source_binding_mismatch(tmp_path: Path) -> None:
    first = _case(tmp_path / "one", "track-one", 220.0)
    second = _case(tmp_path / "two", "track-two", 330.0)
    mismatched = AudioQualityInput(
        track_id="track-three",
        authorised_excerpt=first.authorised_excerpt,
        candidate_midi_evaluation=second.candidate_midi_evaluation,
        role_mapping=first.role_mapping,
    )
    with pytest.raises(ValueError, match="candidate evaluation contract"):
        _create_private_separated_audio_quality_review(
            [first, mismatched], out_dir=tmp_path / "review"
        )


def test_persisted_review_contract_contains_no_source_paths(tmp_path: Path) -> None:
    created = _create(tmp_path)
    package = Path(str(created["out_dir"]))
    for name in (
        "separated_audio_quality_review.json",
        "separated_audio_quality_answer_key.json",
        "separated_audio_quality_manifest.json",
        "separated_audio_quality_review.html",
    ):
        assert str(tmp_path) not in (package / name).read_text()
    assert hashlib.sha256(b"q" * 32 + bytes.fromhex(
        json.loads((package / "separated_audio_quality_review.json").read_text())[
            "package_commitment"
        ]
    )).hexdigest() in (
        package / "separated_audio_quality_answer_key.json"
    ).read_text()
