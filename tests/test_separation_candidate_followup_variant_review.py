from __future__ import annotations

import json
from pathlib import Path
import stat

import numpy as np
import soundfile

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_candidate_followup_variant_review import (
    POLICY_ID,
    SCHEMA,
    _prepare_private_candidate_followup_variant_review,
)
from sunofriend._separation_candidate_join_remediation_review import (
    ANSWER_KEY_NAME,
    REPORT_NAME,
)
from sunofriend._separation_full_song_join_remediation_review import HTML_NAME


SAMPLE_RATE = 44_100


def test_builds_one_sealed_review_for_both_followup_variants(
    tmp_path: Path, monkeypatch
) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(
        "sunofriend._separation_candidate_followup_variant_review."
        "_load_verified_variant_inputs",
        lambda *args, **kwargs: context,
    )
    output = tmp_path / "review"

    result = _prepare_private_candidate_followup_variant_review(
        context["plan_snapshot"]["path"],
        execution_dir=context["base_root"],
        v2_execution_dir=context["v2_root"],
        variant_execution_dir=context["variant_root"],
        out_dir=output,
    )

    assert result["schema"] == SCHEMA
    assert result["status"] == "unreviewed"
    assert result["policy_id"] == POLICY_ID
    assert result["expected_counts"] == {
        "boundary_role_pairs": 3,
        "patch_edge_pairs": 6,
        "complete_song_pairs": 6,
        "total_units": 15,
    }
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())
    assert all(value is False for value in result["readiness"].values())

    report = _read(output / REPORT_NAME)
    answer = _read(output / ANSWER_KEY_NAME)
    assert report["document_sha256"] == _document_sha256(report)
    assert answer["document_sha256"] == _document_sha256(answer)
    assert report["bindings"]["answer_key_sha256"] == _sha256(
        output / ANSWER_KEY_NAME
    )
    assert len(report["units"]) == len(answer["units"]) == 15
    identities = {
        identity
        for unit in answer["units"]
        for identity in unit["assignment"].values()
    }
    assert identities == {
        "followup_control",
        "shifted-context-standard-edge",
        "preserved-centre-extended-edge",
    }

    page = (output / HTML_NAME).read_text(encoding="utf-8")
    assert '"assignment"' not in page
    assert ANSWER_KEY_NAME not in page
    assert "shifted-context-standard-edge" not in page
    assert "preserved-centre-extended-edge" not in page
    assert "6 complete-song comparisons" in page
    referenced = 0
    for unit in report["units"]:
        for record in unit["audio"].values():
            path = (output / record["path"]).resolve()
            assert path.is_file()
            assert path.stat().st_size == record["bytes"]
            assert _sha256(path) == record["sha256"]
            assert soundfile.info(path).frames > 0
            assert record["path"] in page
            referenced += 1
    assert referenced == 30
    for path in output.rglob("*"):
        expected = 0o700 if path.is_dir() else 0o600
        assert stat.S_IMODE(path.stat().st_mode) == expected


def _context(tmp_path: Path) -> dict[str, object]:
    tmp_path.chmod(0o700)
    frames = 6 * SAMPLE_RATE
    time = np.arange(frames, dtype="float64") / SAMPLE_RATE
    base_values = {
        "vocals": _stereo(0.08 * np.sin(2 * np.pi * 220 * time)),
        "instrumental": _stereo(0.11 * np.sin(2 * np.pi * 110 * time)),
    }
    base_values["reconstruction"] = (
        base_values["vocals"] + base_values["instrumental"]
    )
    base_root = _private_directory(tmp_path / "followup-control")
    v2_root = _private_directory(tmp_path / "v2")
    variant_root = _private_directory(tmp_path / "variants")
    standard_root = _private_directory(variant_root / "standard")
    preserved_root = _private_directory(variant_root / "preserved")
    base_paths = {
        role: _write_audio(base_root / f"{role}.wav", values)
        for role, values in base_values.items()
    }
    variant_paths: dict[str, dict[str, Path]] = {}
    for variant_id, root, scale in (
        ("shifted-context-standard-edge", standard_root, 0.92),
        ("preserved-centre-extended-edge", preserved_root, 0.86),
    ):
        variant_paths[variant_id] = {
            role: _write_audio(root / f"{role}.wav", values * scale)
            for role, values in base_values.items()
        }

    plan_path = _write_json(tmp_path / "plan.json", {"kind": "plan"})
    execution_path = _write_json(variant_root / "execution.json", {"kind": "run"})
    candidates_path = _write_json(
        variant_root / "candidates.json", {"kind": "candidates"}
    )
    control_execution_path = _write_json(
        base_root / "execution.json", {"kind": "control-run"}
    )
    control_candidate_path = _write_json(
        base_root / "candidate.json", {"kind": "control-candidate"}
    )
    v2_path = _write_json(v2_root / "execution.json", {"kind": "v2"})
    plan = {
        "document_sha256": "plan-document",
        "protocol": {
            "candidate_variants": [
                {
                    "variant_id": "shifted-context-standard-edge",
                    "failed_edge_source": "shifted_context_worker",
                },
                {
                    "variant_id": "preserved-centre-extended-edge",
                    "failed_edge_source": "exact_followup_candidate_patch",
                },
            ]
        },
        "windows": [
            {
                "boundary_index": 4,
                "role_actions": {
                    "vocals": {
                        "action": "edge_aware_reinference_and_blend_search",
                        "patch_start_frame": 2 * SAMPLE_RATE,
                        "patch_end_frame": 4 * SAMPLE_RATE,
                    },
                    "instrumental": {
                        "action": "fresh_window_reinference_and_blend_search",
                        "patch_start_frame": 2 * SAMPLE_RATE,
                        "patch_end_frame": 4 * SAMPLE_RATE,
                    },
                },
            }
        ],
    }
    return {
        "plan_snapshot": {
            "path": plan_path,
            "sha256": _sha256(plan_path),
        },
        "plan": plan,
        "inputs": {
            "execution_snapshot": {
                "path": control_execution_path,
                "sha256": _sha256(control_execution_path),
            },
            "candidate_snapshot": {
                "path": control_candidate_path,
                "sha256": _sha256(control_candidate_path),
            },
            "v2_snapshot": {"path": v2_path, "sha256": _sha256(v2_path)},
        },
        "execution_snapshot": {
            "path": execution_path,
            "sha256": _sha256(execution_path),
        },
        "execution": {"document_sha256": "execution-document"},
        "candidates_snapshot": {
            "path": candidates_path,
            "sha256": _sha256(candidates_path),
        },
        "candidates": {"document_sha256": "candidate-document"},
        "base_root": base_root,
        "v2_root": v2_root,
        "variant_root": variant_root,
        "base_paths": base_paths,
        "variant_paths": variant_paths,
    }


def _stereo(values: np.ndarray) -> np.ndarray:
    return np.column_stack((values, values))


def _private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def _write_audio(path: Path, values: np.ndarray) -> Path:
    soundfile.write(path, values, SAMPLE_RATE, subtype="PCM_24")
    path.chmod(0o600)
    return path


def _write_json(path: Path, value: dict[str, object]) -> Path:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
