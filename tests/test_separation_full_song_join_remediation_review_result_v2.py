from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
from typing import Any, Mapping

import pytest

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_checkpoint_canonical import canonical_json_bytes
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    REPORT_NAME as V2_EXECUTION_REPORT_NAME,
)
from sunofriend._separation_full_song_join_remediation_review_result_v2 import (
    RESULT_SCHEMA,
    RESULT_STATUS,
    STATUS_SCHEMA,
    _resolve_private_join_remediation_review_v2,
    _status_private_join_remediation_review_v2,
)
from sunofriend._separation_full_song_join_remediation_review_v2 import (
    ANSWER_KEY_NAME,
    HTML_NAME,
    REPORT_NAME,
    _prepare_private_join_remediation_review_v2,
    _review_html,
)
from tests.test_separation_full_song_join_remediation_executor_v2 import _execute
from tests.test_separation_full_song_join_remediation_review_v2 import (
    _prepared_two_windows,
)


def test_v2_review_status_keeps_key_closed_then_resolves_absolute_evidence(
    tmp_path: Path,
) -> None:
    fixture = _completed_review(tmp_path)
    key_path = fixture["review_root"] / ANSWER_KEY_NAME
    key_bytes = key_path.read_bytes()
    key_path.write_text("deliberately unreadable during status\n", encoding="utf-8")

    status = _status_private_join_remediation_review_v2(
        fixture["reviewed"], **fixture["arguments"]
    )

    assert status["schema"] == STATUS_SCHEMA
    assert status["status"] == "complete_review_verified_key_unopened"
    assert status["reviewed_units"] == 6
    assert status["counts_by_kind"] == {
        "boundary_candidate_pair": 2,
        "v2_patch_edge": 4,
    }
    assert status["audio_references_verified"] == 8
    assert status["answer_key_opened"] is False
    assert status["identity_mapping_revealed"] is False
    assert status["document_sha256"] == _document_sha256(status)
    assert all(value is False for value in status["permissions"].values())
    assert all(value is False for value in status["effects"].values())

    key_path.write_bytes(key_bytes)
    key_path.chmod(0o600)
    answer = json.loads(key_bytes)
    result_path = tmp_path / "resolved-v2" / "result.json"
    result = _resolve_private_join_remediation_review_v2(
        fixture["reviewed"], out=result_path, **fixture["arguments"]
    )

    assert result["schema"] == RESULT_SCHEMA
    assert result["status"] == RESULT_STATUS
    assert result["reviewed_unit_count"] == 6
    assert result["readiness_evidence"]["targeted_v2_review_complete"] is True
    assert result["readiness_evidence"]["targeted_v2_absolute_cleanliness_pass"] is True
    assert (
        result["readiness_evidence"]["fresh_candidate_bound_full_song_review_eligible"]
        is True
    )
    assert result["readiness_evidence"]["original_audible_joins_resolved"] is False
    assert result["readiness_evidence"]["publication_ready"] is False
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())
    stored = json.loads(result_path.read_text(encoding="utf-8"))
    assert stored["document_sha256"] == _document_sha256(stored)
    assert stat.S_IMODE(result_path.stat().st_mode) == 0o600

    reviewed = json.loads(fixture["reviewed"].read_text(encoding="utf-8"))
    boundary = [
        unit for unit in result["units"] if unit["kind"] == "boundary_candidate_pair"
    ]
    for resolved, blind, answer_unit in zip(
        boundary,
        [
            unit
            for unit in reviewed["units"]
            if unit["kind"] == "boundary_candidate_pair"
        ],
        answer["boundary_assignments"],
    ):
        assignment = answer_unit["assignment"]
        assert resolved["identity_absolute_cleanliness"] == {
            assignment[slot]: blind["absolute_cleanliness"][slot] for slot in ("A", "B")
        }
        expected_choice = (
            f"{assignment[blind['comparative_choice']]}_preferred"
            if blind["comparative_choice"] in {"A", "B"}
            else blind["comparative_choice"]
        )
        assert resolved["resolved_comparative_choice"] == expected_choice

    stored_bytes = result_path.read_bytes()
    with pytest.raises(FileExistsError):
        _resolve_private_join_remediation_review_v2(
            fixture["reviewed"], out=result_path, **fixture["arguments"]
        )
    assert result_path.read_bytes() == stored_bytes


def test_v2_review_result_does_not_pass_when_one_v2_edge_is_audible(
    tmp_path: Path,
) -> None:
    fixture = _completed_review(tmp_path, edge_rating="audible_join")
    result = _resolve_private_join_remediation_review_v2(
        fixture["reviewed"],
        out=tmp_path / "resolved" / "result.json",
        **fixture["arguments"],
    )

    assert result["readiness_evidence"]["all_targeted_v2_boundary_versions_clean"]
    assert result["readiness_evidence"]["all_v2_patch_edges_clean"] is False
    assert (
        result["readiness_evidence"]["targeted_v2_absolute_cleanliness_pass"] is False
    )
    assert (
        result["readiness_evidence"]["fresh_candidate_bound_alignment_review_eligible"]
        is False
    )
    assert result["readiness_evidence"]["original_audible_joins_resolved"] is False


@pytest.mark.parametrize("tamper", ("title", "heard", "absolute", "comparison"))
def test_v2_review_status_rejects_changed_or_incomplete_export(
    tmp_path: Path,
    tamper: str,
) -> None:
    fixture = _completed_review(tmp_path)
    reviewed = json.loads(fixture["reviewed"].read_text(encoding="utf-8"))
    if tamper == "title":
        reviewed["units"][0]["title"] = "changed title"
        message = "changed immutable evidence"
    elif tamper == "heard":
        reviewed["units"][0]["heard"]["A"] = False
        message = "unit is incomplete"
    elif tamper == "absolute":
        reviewed["units"][0]["absolute_cleanliness"]["A"] = "unknown"
        message = "unit is incomplete"
    else:
        reviewed["units"][0]["comparative_choice"] = None
        message = "unit is incomplete"
    changed = tmp_path / f"changed-{tamper}.json"
    _write_private_json(changed, reviewed)

    with pytest.raises(ValueError, match=message):
        _status_private_join_remediation_review_v2(changed, **fixture["arguments"])


def test_v2_review_resolver_rejects_rehashed_wrong_answer_assignment(
    tmp_path: Path,
) -> None:
    fixture = _completed_review(tmp_path)
    answer_path = fixture["review_root"] / ANSWER_KEY_NAME
    answer = json.loads(answer_path.read_text(encoding="utf-8"))
    assignment = answer["boundary_assignments"][0]["assignment"]
    assignment["A"], assignment["B"] = assignment["B"], assignment["A"]
    _repin_answer_key_and_review(
        answer,
        answer_path=answer_path,
        seed_path=fixture["review_root"] / REPORT_NAME,
        reviewed_path=fixture["reviewed"],
    )

    with pytest.raises(ValueError, match="answer binding differs"):
        _resolve_private_join_remediation_review_v2(
            fixture["reviewed"],
            out=tmp_path / "resolved" / "result.json",
            **fixture["arguments"],
        )


@pytest.mark.parametrize(
    ("tamper", "message"),
    (
        ("source_commitment", "source bindings differ"),
        ("audio_geometry", "audio"),
    ),
)
def test_v2_review_status_rejects_coherently_rehashed_public_claims(
    tmp_path: Path,
    tamper: str,
    message: str,
) -> None:
    fixture = _completed_review(tmp_path)
    seed_path = fixture["review_root"] / REPORT_NAME
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    if tamper == "source_commitment":
        seed["bindings"]["source_bindings_commitment"] = "f" * 64
    else:
        seed["units"][0]["audio"]["A"]["geometry"]["frames"] -= 1
        manifest = {
            "schema": (
                "sunofriend.private-separation-full-song-join-remediation-audio.v2"
            ),
            "units": [
                {"unit_id": unit["unit_id"], "audio": unit["audio"]}
                for unit in seed["units"]
            ],
        }
        seed["bindings"]["audio_manifest_sha256"] = hashlib.sha256(
            canonical_json_bytes(manifest)
        ).hexdigest()
        seed["package_commitment"] = hashlib.sha256(
            (
                f"{seed['bindings']['answer_key_sha256']}:"
                f"{seed['bindings']['answer_key_document_sha256']}:"
                f"{seed['bindings']['audio_manifest_sha256']}"
            ).encode("ascii")
        ).hexdigest()
    _repin_public_seed(
        seed,
        seed_path=seed_path,
        reviewed_path=fixture["reviewed"],
    )

    with pytest.raises(ValueError, match=message):
        _status_private_join_remediation_review_v2(
            fixture["reviewed"], **fixture["arguments"]
        )


def test_v2_review_result_script_exposes_status_first_interface() -> None:
    script = Path(
        "scripts/private-separation-full-song-join-remediation-review-result-v2.py"
    ).read_text(encoding="utf-8")
    for option in (
        "--status",
        "--resolve",
        "--review-package-dir",
        "--v2-execution-dir",
        "--v2-plan",
        "--v1-execution-dir",
        "--package-dir",
        "--full-song-review-result",
        "--v1-plan",
        "--resolved-join-review-result",
        "--publication-readiness",
        "--out",
    ):
        assert option in script
    assert (
        '"units"'
        not in script.split("def _cli_resolution_summary", 1)[1].split(
            "def _snapshot_error_message", 1
        )[0]
    )


def _completed_review(tmp_path: Path, *, edge_rating: str = "clean") -> dict[str, Any]:
    evidence, plan_path, _plan = _prepared_two_windows(tmp_path)
    v2_execution = tmp_path / "v2-execution"
    _execute(evidence, plan_path, v2_execution)
    assert (v2_execution / V2_EXECUTION_REPORT_NAME).is_file()
    review_root = tmp_path / "v2-review"
    _prepare_private_join_remediation_review_v2(
        v2_execution,
        v2_plan_path=plan_path,
        v1_execution_dir=evidence.execution_dir,
        stitch_package_dir=evidence.package,
        full_song_review_result_path=evidence.review,
        v1_plan_path=evidence.v1_plan,
        resolved_join_review_result_path=evidence.resolved_review,
        publication_readiness_path=evidence.readiness,
        out_dir=review_root,
    )
    reviewed_document = json.loads((review_root / REPORT_NAME).read_text())
    for index, unit in enumerate(reviewed_document["units"]):
        if unit["kind"] == "boundary_candidate_pair":
            unit["heard"] = {"A": True, "B": True}
            unit["absolute_cleanliness"] = {"A": "clean", "B": "clean"}
            unit["comparative_choice"] = "A" if index == 0 else "B"
        else:
            unit["heard"] = True
            unit["absolute_cleanliness"] = edge_rating if index == 2 else "clean"
        unit["notes"] = f"private unit {index + 1} note"
    reviewed_document["status"] = "reviewed"
    reviewed_document["summary"] = {
        "reviewed_units": 6,
        "total_units": 6,
        "complete": True,
    }
    reviewed = tmp_path / "join_remediation_review_v2.reviewed.json"
    _write_private_json(reviewed, reviewed_document)
    return {
        "review_root": review_root,
        "reviewed": reviewed,
        "arguments": {
            "review_package_dir": review_root,
            "v2_execution_dir": v2_execution,
            "v2_plan_path": plan_path,
            "v1_execution_dir": evidence.execution_dir,
            "stitch_package_dir": evidence.package,
            "full_song_review_result_path": evidence.review,
            "v1_plan_path": evidence.v1_plan,
            "resolved_join_review_result_path": evidence.resolved_review,
            "publication_readiness_path": evidence.readiness,
        },
    }


def _repin_answer_key_and_review(
    answer: dict[str, Any],
    *,
    answer_path: Path,
    seed_path: Path,
    reviewed_path: Path,
) -> None:
    answer["document_sha256"] = _document_sha256(answer)
    _write_private_json(answer_path, answer)
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    seed["bindings"]["answer_key_sha256"] = _sha256(answer_path)
    seed["bindings"]["answer_key_document_sha256"] = answer["document_sha256"]
    seed["package_commitment"] = hashlib.sha256(
        (
            f"{seed['bindings']['answer_key_sha256']}:"
            f"{seed['bindings']['answer_key_document_sha256']}:"
            f"{seed['bindings']['audio_manifest_sha256']}"
        ).encode("ascii")
    ).hexdigest()
    seed["document_sha256"] = _document_sha256(seed)
    _write_private_json(seed_path, seed)
    page_path = seed_path.parent / HTML_NAME
    page_path.write_text(_review_html(seed), encoding="utf-8")
    page_path.chmod(0o600)
    reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
    reviewed["bindings"] = dict(seed["bindings"])
    reviewed["package_commitment"] = seed["package_commitment"]
    reviewed["document_sha256"] = seed["document_sha256"]
    _write_private_json(reviewed_path, reviewed)


def _repin_public_seed(
    seed: dict[str, Any], *, seed_path: Path, reviewed_path: Path
) -> None:
    seed["document_sha256"] = _document_sha256(seed)
    _write_private_json(seed_path, seed)
    page_path = seed_path.parent / HTML_NAME
    page_path.write_text(_review_html(seed), encoding="utf-8")
    page_path.chmod(0o600)
    reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
    reviewed["bindings"] = dict(seed["bindings"])
    reviewed["package_commitment"] = seed["package_commitment"]
    reviewed["units"] = seed["units"]
    for index, unit in enumerate(reviewed["units"]):
        if unit["kind"] == "boundary_candidate_pair":
            unit["heard"] = {"A": True, "B": True}
            unit["absolute_cleanliness"] = {"A": "clean", "B": "clean"}
            unit["comparative_choice"] = "A" if index == 0 else "B"
        else:
            unit["heard"] = True
            unit["absolute_cleanliness"] = "clean"
        unit["notes"] = f"private unit {index + 1} note"
    reviewed["document_sha256"] = seed["document_sha256"]
    _write_private_json(reviewed_path, reviewed)


def _write_private_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)
