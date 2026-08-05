from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path

import pytest

import sunofriend._separation_reviewed_output_import_assessment as assessment


def test_assesses_two_reviewed_stems_without_importing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)

    result = _run(context)

    assert result["status"] == assessment.STATUS
    assert [asset["candidate_role"] for asset in result["reviewed_assets"]] == [
        "vocals",
        "instrumental",
    ]
    assert result["reviewed_assets"][1]["source_role"] == "other"
    assert result["reviewed_assets"][1]["declared_role"] == "instrumental"
    assert result["future_import_contract"]["original_mix_retained"] is True
    assert result["future_import_contract"]["initial_activation_mode"] == "unchanged"
    assert result["readiness"]["private_import_implementation_eligible"] is True
    assert result["readiness"]["private_output_import_permitted"] is False
    assert result["permissions"]["private_import_implementation_may_be_designed"] is True
    assert result["permissions"]["source_graph_activation"] is False
    assert result["effects"]["source_graph_mutated"] is False
    assert context["output"].stat().st_mode & 0o777 == 0o600


def test_rejects_non_useful_full_song_role(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    context["equivalence"]["document"]["prior_human_review"]["full_song"][
        "ratings"
    ]["instrumental"] = "noticeable_problems"

    with pytest.raises(ValueError, match="prerequisites are incomplete"):
        _run(context)

    assert not context["output"].exists()


def test_rejects_candidate_audio_not_bound_to_equivalence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    context["equivalence"]["document"]["comparisons"]["vocals"][
        "candidate_audio_sha256"
    ] = "f" * 64

    with pytest.raises(ValueError, match="audio binding differs"):
        _run(context)

    assert not context["output"].exists()


def _run(context: dict[str, object]) -> dict[str, object]:
    return assessment._assess_reviewed_output_import(
        context["equivalence_path"],
        reviewed_export_path=context["reviewed_export"],
        reviewed_package_dir=context["reviewed_package"],
        candidate_package_report_path=context["candidate_report"],
        out=context["output"],
    )


def _context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    os.chmod(tmp_path, 0o700)
    output_root = tmp_path / "ASSESSMENT"
    output_root.mkdir(mode=0o700)
    clock = {
        "sample_rate": 44_100,
        "channels": 2,
        "frames": 100,
        "boundary_count": 2,
    }
    artifacts = {
        "source": _artifact("1", clock),
        "vocals": _artifact("2", clock, pcm="6"),
        "instrumental": _artifact("3", clock, pcm="7"),
        "reconstruction": _artifact("4", clock),
    }
    candidate_document = {
        "document_sha256": "8" * 64,
        "bindings": {"review_package_commitment": "9" * 64},
        "readiness": {
            "alignment_gate_passed": True,
            "exact_stitch_complete": True,
        },
    }
    stitch = {
        "document_sha256": "a" * 64,
        "clock": clock,
        "artifacts": artifacts,
    }
    candidate = {
        "sha256": "b" * 64,
        "document": candidate_document,
        "stitch": stitch,
        "stitch_root": tmp_path / "candidate" / "STITCH",
    }
    comparisons = {
        role: {
            "candidate_audio_sha256": artifacts[role]["sha256"],
            "sample_rate": clock["sample_rate"],
            "channels": clock["channels"],
            "frames": clock["frames"],
            "maximum_absolute_pcm24_lsb_difference": 1,
        }
        for role in ("vocals", "instrumental", "reconstruction")
    }
    equivalence_document = {
        "document_sha256": "c" * 64,
        "bindings": {"candidate_stitch_report_sha256": "d" * 64},
        "clock": clock,
        "comparisons": comparisons,
        "prior_human_review": {
            "review_evidence_applies_under_equivalence_policy": True,
            "full_song": {
                "heard_all": True,
                "ratings": {
                    "vocals": "useful",
                    "instrumental": "useful",
                    "reconstruction": "useful",
                },
            },
            "boundary_summary": {"reviewed_boundaries": 2},
        },
        "readiness": {
            "prior_human_review_verified": True,
            "candidate_render_pcm24_equivalence_verified": True,
        },
    }
    equivalence = {
        "sha256": "e" * 64,
        "document": equivalence_document,
    }
    context: dict[str, object] = {
        "equivalence_path": tmp_path / "equivalence.json",
        "reviewed_export": tmp_path / "reviewed.json",
        "reviewed_package": tmp_path / "reviewed",
        "candidate_report": tmp_path / "candidate" / "package.json",
        "output": output_root / assessment.REPORT_NAME,
        "candidate": candidate,
        "equivalence": equivalence,
    }
    monkeypatch.setattr(
        assessment,
        "_load_candidate_package",
        lambda *_args, **_kwargs: deepcopy(context["candidate"]),
    )
    monkeypatch.setattr(
        assessment,
        "_load_verified_render_review_equivalence",
        lambda *_args, **_kwargs: deepcopy(context["equivalence"]),
    )
    monkeypatch.setattr(assessment, "_require_output_disjoint", lambda *_args, **_kwargs: None)
    return context


def _artifact(seed: str, clock: dict[str, int], *, pcm: str | None = None) -> dict[str, object]:
    return {
        "sha256": seed * 64,
        "pcm24_int32_sequence_sha256": (pcm or seed) * 64,
        "geometry": {
            "sample_rate": clock["sample_rate"],
            "channels": clock["channels"],
            "frames": clock["frames"],
            "sample_width_bytes": 3,
        },
    }
