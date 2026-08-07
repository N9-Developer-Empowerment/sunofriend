from __future__ import annotations

import json
from pathlib import Path
import stat

import pytest

from sunofriend.separation_alpha import main as separation_main
from sunofriend.separation_other_refinement import (
    create_other_refinement_synthetic_fixture,
)
from sunofriend.separation_other_refinement_review import (
    OTHER_REFINEMENT_FEEDBACK_SCHEMA,
    record_other_refinement_review,
    validate_other_refinement_review,
)


def _legacy_review(result: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "sunofriend.other-refinement-listening.v1",
        "result_sha256": result["document_sha256"],
        "target_id": result["request"]["target_id"],
        "listened": True,
        "usefulness": "mixed",
        "notes": "Useful evidence from the original compact page.",
        "activation_choice": "none",
    }


def _detailed_review(result: dict[str, object]) -> dict[str, object]:
    return {
        **_legacy_review(result),
        "bleed": "some",
        "missing_content": "none",
        "artefacts": "cannot_tell",
        "timing_or_join_problems": "none",
        "downstream_midi": "not_tested",
        "exported_at": "2026-08-07T06:58:02.123Z",
    }


def _use_installed_result_layout(fixture: dict[str, object]) -> None:
    root = Path(str(fixture["root"]))
    technical = root / "TECHNICAL"
    technical.mkdir()
    Path(str(fixture["plan"])).rename(technical / "other-refinement-plan.json")
    Path(str(fixture["result"])).rename(technical / "other-refinement-result.json")


@pytest.mark.parametrize("detailed", [False, True])
def test_review_validator_binds_complete_legacy_and_detailed_exports(
    tmp_path: Path, detailed: bool
) -> None:
    fixture = create_other_refinement_synthetic_fixture(tmp_path / "fixture")
    result = json.loads(Path(fixture["result"]).read_text(encoding="utf-8"))
    _use_installed_result_layout(fixture)
    review = _detailed_review(result) if detailed else _legacy_review(result)

    validated = validate_other_refinement_review(review, result=result)

    assert validated["_validated_variant"] == (
        "detailed" if detailed else "legacy_minimal"
    )
    assert validated["activation_choice"] == "none"


def test_record_review_reverifies_audio_and_writes_private_no_activation_evidence(
    tmp_path: Path,
) -> None:
    fixture = create_other_refinement_synthetic_fixture(tmp_path / "fixture")
    result = json.loads(Path(fixture["result"]).read_text(encoding="utf-8"))
    _use_installed_result_layout(fixture)
    review_path = tmp_path / "review.json"
    review_path.write_text(
        json.dumps(_legacy_review(result), indent=2) + "\n", encoding="utf-8"
    )
    output = tmp_path / "evidence/feedback.json"

    record = record_other_refinement_review(fixture["root"], review_path, out=output)

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted == record
    assert record["schema"] == OTHER_REFINEMENT_FEEDBACK_SCHEMA
    assert record["review_format"] == {
        "variant": "legacy_minimal",
        "detailed_problem_fields_recorded": False,
        "omitted_fields_mean_pass": False,
    }
    assert set(record["observations"].values()) == {
        "mixed",
        "not_recorded_by_legacy_page",
    }
    assert not any(record["permissions"].values())
    assert not any(record["effects"].values())
    assert stat.S_IMODE(output.stat().st_mode) == 0o600

    with pytest.raises(FileExistsError, match="already exists"):
        record_other_refinement_review(fixture["root"], review_path, out=output)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"result_sha256": "0" * 64}, "result binding"),
        ({"target_id": "keys"}, "target binding"),
        ({"listened": False}, "confirm listening"),
        ({"activation_choice": "guitar"}, "cannot activate"),
    ],
)
def test_review_rejects_changed_binding_incomplete_listen_or_activation(
    tmp_path: Path, change: dict[str, object], message: str
) -> None:
    fixture = create_other_refinement_synthetic_fixture(tmp_path / "fixture")
    result = json.loads(Path(fixture["result"]).read_text(encoding="utf-8"))
    review = {**_legacy_review(result), **change}

    with pytest.raises(ValueError, match=message):
        validate_other_refinement_review(review, result=result)


def test_cli_records_explicit_review_without_selection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = create_other_refinement_synthetic_fixture(
        tmp_path / "fixture", target_id="keys"
    )
    result = json.loads(Path(fixture["result"]).read_text(encoding="utf-8"))
    _use_installed_result_layout(fixture)
    review_path = tmp_path / "keys-review.json"
    review_path.write_text(
        json.dumps(_detailed_review(result), indent=2) + "\n", encoding="utf-8"
    )
    output = tmp_path / "keys-feedback.json"

    exit_code = separation_main(
        [
            "review-other",
            str(fixture["root"]),
            str(review_path),
            "--out",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.is_file()
    terminal = capsys.readouterr().out
    assert "Target: keys; usefulness: mixed" in terminal
    assert "No candidate was selected" in terminal
