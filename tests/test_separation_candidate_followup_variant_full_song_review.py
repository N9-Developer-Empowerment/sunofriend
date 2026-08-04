from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_candidate_followup_variant_full_song_review import (
    REPORT_NAME,
    STATUS,
    _build_private_candidate_followup_variant_full_song_review,
    _verified_exact_variant_result,
)
from sunofriend._separation_candidate_followup_variant_review import (
    _FALSE_EFFECTS as VARIANT_REVIEW_FALSE_EFFECTS,
)
from sunofriend._separation_candidate_followup_variant_review_result import (
    RESULT_SCHEMA as VARIANT_RESULT_SCHEMA,
    RESULT_STATUS as VARIANT_RESULT_STATUS,
)
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _read_pcm24_snapshot,
)
from sunofriend._separation_full_song_stitch import _write_boundary_review


SAMPLE_RATE = 44_100
VARIANTS = (
    "shifted-context-standard-edge",
    "preserved-centre-extended-edge",
)


def test_exact_gate_rederives_result_before_accepting_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tmp_path.chmod(0o700)
    package = _private_dir(tmp_path / "review")
    result = {
        "schema": VARIANT_RESULT_SCHEMA,
        "status": VARIANT_RESULT_STATUS,
        "readiness_evidence": {},
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(VARIANT_REVIEW_FALSE_EFFECTS),
    }
    result["document_sha256"] = _document_sha256(result)
    result_path = _write(tmp_path / "result/resolved.json", result)
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_variant_full_song_review._resolve_private_candidate_followup_variant_review",
        lambda *args, **kwargs: {**result, "report": str(kwargs["out"])},
    )

    verified = _verified_exact_variant_result(
        result_path,
        reviewed_export_path=tmp_path / "reviewed.json",
        variant_review_package_dir=package,
        plan_path=tmp_path / "plan.json",
        execution_dir=tmp_path / "execution",
        v2_execution_dir=tmp_path / "v2",
        variant_execution_dir=tmp_path / "variants",
    )
    assert verified == result

    changed = dict(result)
    changed["status"] = "changed"
    changed["document_sha256"] = _document_sha256(changed)
    _write(result_path, changed)
    with pytest.raises(ValueError, match="result differs"):
        _verified_exact_variant_result(
            result_path,
            reviewed_export_path=tmp_path / "reviewed.json",
            variant_review_package_dir=package,
            plan_path=tmp_path / "plan.json",
            execution_dir=tmp_path / "execution",
            v2_execution_dir=tmp_path / "v2",
            variant_execution_dir=tmp_path / "variants",
        )


def test_builds_one_independent_review_for_one_eligible_variant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch, eligible=[VARIANTS[0]])
    result = _build(fixture)
    out = fixture["out"]

    assert result["status"] == STATUS
    assert result["eligible_variant_ids"] == [VARIANTS[0]]
    assert result["eligible_variant_count"] == 1
    assert result["required_review_count"] == 1
    assert result["permissions"] == _FALSE_PERMISSIONS
    assert result["effects"]["candidate_selected"] is False
    assert result["interpretation"]["automatic_winner_selected"] is False
    assert len(result["review_html"]) == 1
    assert (out / REPORT_NAME).is_file()
    package = result["variant_packages"][0]
    assert package["variant_id"] == VARIANTS[0]
    assert package["readiness"]["selected"] is False
    assert (out / package["directory"] / package["boundary_review"]["html"]).is_file()
    assert len(list((out / package["directory"] / "BOUNDARY-REVIEW/audio").glob("*.wav"))) == 4


def test_builds_both_eligible_variants_without_selecting_between_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch, eligible=list(reversed(VARIANTS)))
    result = _build(fixture)
    out = fixture["out"]

    assert result["eligible_variant_ids"] == list(VARIANTS)
    assert result["eligible_variant_count"] == 2
    assert result["required_review_count"] == 2
    assert len(result["variant_packages"]) == 2
    assert len(result["review_html"]) == 2
    assert all(item["readiness"]["selected"] is False for item in result["variant_packages"])
    assert all(item["readiness"]["accepted"] is False for item in result["variant_packages"])
    assert all(
        (out / item["directory"] / item["boundary_review"]["html"]).is_file()
        for item in result["variant_packages"]
    )


def test_zero_eligible_variants_fails_before_creating_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch, eligible=[])
    with pytest.raises(ValueError, match="no verified variant"):
        _build(fixture)
    assert not fixture["out"].exists()


def test_gate_inventory_mismatch_and_existing_destination_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch, eligible=[VARIANTS[0]])
    fixture["result"]["candidate_gate_evidence"][VARIANTS[0]][
        "eligible_for_fresh_all_boundary_review"
    ] = False
    with pytest.raises(ValueError, match="gate evidence"):
        _build(fixture)
    assert not fixture["out"].exists()

    fixture["out"].mkdir(mode=0o700)
    with pytest.raises(FileExistsError):
        _build(fixture)
    assert not (fixture["out"] / REPORT_NAME).exists()


def _build(fixture: dict[str, object]) -> dict[str, object]:
    return _build_private_candidate_followup_variant_full_song_review(
        fixture["result_path"],
        reviewed_export_path=fixture["reviewed_export"],
        variant_review_package_dir=fixture["review_package"],
        plan_path=fixture["plan_path"],
        execution_dir=fixture["base_root"],
        v2_execution_dir=fixture["v2_root"],
        variant_execution_dir=fixture["variant_root"],
        stitch_package_dir=fixture["stitch_root"],
        out_dir=fixture["out"],
    )


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    eligible: list[str],
) -> dict[str, object]:
    tmp_path.chmod(0o700)
    frames = SAMPLE_RATE * 6
    time = np.arange(frames, dtype="float64") / SAMPLE_RATE
    vocals = _stereo(0.08 * np.sin(2 * np.pi * 220 * time))
    instrumental = _stereo(0.11 * np.sin(2 * np.pi * 110 * time))
    source = vocals + instrumental
    values = {
        "vocals": vocals,
        "instrumental": instrumental,
        "reconstruction": source,
    }

    base_root = _private_dir(tmp_path / "followup-control")
    v2_root = _private_dir(tmp_path / "v2")
    variant_root = _private_dir(tmp_path / "variant-execution")
    review_package = _private_dir(tmp_path / "variant-review")
    stitch_root = _private_dir(tmp_path / "stitch")
    variant_paths: dict[str, dict[str, Path]] = {}
    variants = []
    for index, variant_id in enumerate(VARIANTS, start=1):
        root = _private_dir(variant_root / f"candidate-{index}")
        role_paths = {
            role: _audio(root / f"{role}.wav", audio * (1.0 - index * 0.03))[0]
            for role, audio in values.items()
        }
        variant_paths[variant_id] = role_paths
        variants.append(
            {
                "variant_id": variant_id,
                "artifacts": {
                    role: _audio_claim(path) for role, path in role_paths.items()
                },
            }
        )

    source_path, source_claim = _audio(
        stitch_root / "SOURCE/source-44100.wav", source, relative="SOURCE/source-44100.wav"
    )
    original_paths = {"source": source_path}
    for role, audio in values.items():
        original_paths[role] = _audio(
            stitch_root / f"STEMS/{role}.wav", audio, relative=f"STEMS/{role}.wav"
        )[0]
    boundary_review = _write_boundary_review(
        stitch_root,
        title="Synthetic original",
        boundaries=[SAMPLE_RATE * 3],
        role_paths=original_paths,
        soundfile=soundfile,
        np=np,
    )
    clock = {
        "sample_rate": SAMPLE_RATE,
        "channels": 2,
        "frames": frames,
        "duration_seconds": 6.0,
        "chunk_count": 2,
        "boundary_count": 1,
        "gap_frames": 0,
        "overlap_frames": 0,
        "crossfade_frames": 0,
    }
    stitch = {
        "clock": clock,
        "artifacts": {"source": source_claim},
        "boundary_review": boundary_review,
        "document_sha256": "a" * 64,
    }
    stitch_path = _write(
        stitch_root / "private-separation-full-song-stitch.json", {"fixture": True}
    )

    snapshots = {
        name: _snapshot(tmp_path / f"evidence/{name}.json", {"name": name})
        for name in ("plan", "execution", "candidates", "base-execution", "base-candidate", "v2")
    }
    plan = {
        "document_sha256": "9" * 64,
        "protocol": {
            "candidate_variants": [{"variant_id": variant_id} for variant_id in VARIANTS]
        }
    }
    inputs = {
        "execution_snapshot": snapshots["base-execution"],
        "candidate_snapshot": snapshots["base-candidate"],
        "v2_snapshot": snapshots["v2"],
        "execution": {"document_sha256": "b" * 64},
        "candidate": {"document_sha256": "c" * 64},
        "v2": {"document_sha256": "d" * 64, "clock": clock},
    }
    context = {
        "plan_snapshot": snapshots["plan"],
        "plan": plan,
        "inputs": inputs,
        "execution_snapshot": snapshots["execution"],
        "execution": {"document_sha256": "e" * 64},
        "candidates_snapshot": snapshots["candidates"],
        "candidates": {"document_sha256": "f" * 64, "variants": variants},
        "base_root": base_root,
        "v2_root": v2_root,
        "variant_root": variant_root,
        "variant_paths": variant_paths,
    }
    result = {
        "bindings": {"review_export_sha256": "1" * 64},
        "fresh_all_boundary_review_eligible_variant_ids": eligible,
        "readiness_evidence": {
            "variant_review_complete": True,
            "one_or_more_variants_eligible_for_fresh_all_boundary_review": bool(eligible),
            "variant_selected": False,
            "fresh_all_boundary_review_complete": False,
            "alignment_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "candidate_gate_evidence": {
            variant_id: {
                "eligible_for_fresh_all_boundary_review": variant_id in eligible,
                "selected": False,
            }
            for variant_id in VARIANTS
        },
    }
    result["document_sha256"] = _document_sha256(result)
    result_path = _write(tmp_path / "result/resolved.json", result)
    reviewed_export = _write(tmp_path / "export/reviewed.json", {"reviewed": True})

    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_variant_full_song_review._load_verified_variant_inputs",
        lambda *args, **kwargs: context,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_variant_full_song_review._verified_exact_variant_result",
        lambda *args, **kwargs: result,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_variant_full_song_review._load_stitch_report",
        lambda path: stitch,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_variant_full_song_review._verify_stitch_audio",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_variant_full_song_review._verify_stitch_bound_to_v2",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_variant_full_song_review._reverify_inputs",
        lambda *args, **kwargs: None,
    )
    return {
        "base_root": base_root,
        "v2_root": v2_root,
        "variant_root": variant_root,
        "review_package": review_package,
        "stitch_root": stitch_root,
        "stitch_path": stitch_path,
        "plan_path": snapshots["plan"]["path"],
        "result_path": result_path,
        "reviewed_export": reviewed_export,
        "result": result,
        "out": tmp_path / "eligible-full-song-reviews",
    }


def _private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def _write(path: Path, document: dict[str, object]) -> Path:
    _private_dir(path.parent)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _snapshot(path: Path, document: dict[str, object]) -> dict[str, object]:
    _write(path, document)
    return {"path": path, "sha256": _sha256(path), "document": document}


def _audio(
    path: Path, values: np.ndarray, *, relative: str | None = None
) -> tuple[Path, dict[str, object]]:
    _private_dir(path.parent)
    soundfile.write(path, values, SAMPLE_RATE, subtype="PCM_24")
    path.chmod(0o600)
    claim = _audio_claim(path)
    if relative is not None:
        claim["path"] = relative
    return path, claim


def _audio_claim(path: Path) -> dict[str, object]:
    info = soundfile.info(path)
    snapshot = _read_pcm24_snapshot(
        path, None, expected_frames=int(info.frames), label="test variant audio"
    )
    return {
        "path": path.name,
        "sha256": snapshot["sha256"],
        "bytes": snapshot["bytes"],
        "geometry": {
            "sample_rate": int(info.samplerate),
            "channels": int(info.channels),
            "frames": int(info.frames),
            "sample_width_bytes": 3,
        },
        "pcm24_int32_sequence_sha256": snapshot["pcm24_int32_sequence_sha256"],
    }


def _stereo(values: np.ndarray) -> np.ndarray:
    return np.column_stack((values, values))
