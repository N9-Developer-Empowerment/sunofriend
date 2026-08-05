from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_candidate_followup_remediation_executor import (
    CANDIDATE_REPORT_NAME,
    CANDIDATES_DIRECTORY,
    REPORT_NAME as EXECUTION_REPORT_NAME,
    SCHEMA as EXECUTION_SCHEMA,
    STATUS_COMPLETE as EXECUTION_STATUS,
)
from sunofriend._separation_candidate_followup_variant_private_pilot_handoff import (
    REPORT_NAME,
    STATUS,
    _prepare_private_candidate_followup_variant_pilot_handoff,
)
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
)
from tests.test_separation_candidate_followup_variant_final_readiness_reassessment import (
    _reassess,
    _resolved_acceptance,
)
from tests.test_separation_candidate_followup_variant_full_song_review import (
    VARIANTS,
    _private_dir,
    _write,
)


def test_plans_one_ready_reference_without_execution_selection_or_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, arguments, acceptance = _resolved_acceptance(
        tmp_path,
        monkeypatch,
        eligible=list(VARIANTS),
        decisions=("accept", "needs_more_work"),
    )
    readiness = _reassess(
        tmp_path,
        acceptance=acceptance,
        reviews=reviews,
        arguments=arguments,
    )
    _write_candidate_evidence(fixture)
    result = _handoff(
        tmp_path,
        readiness=Path(readiness["report"]),
        acceptance=acceptance,
        reviews=reviews,
        arguments=arguments,
    )

    assert result["status"] == STATUS
    assert result["ready_variant_ids"] == [VARIANTS[0]]
    assert [item["variant_id"] for item in result["handoff_variants"]] == [VARIANTS[0]]
    assert result["private_pilot_handoff"] == {
        "handoff_plan_complete": True,
        "ready_variant_count": 1,
        "all_ready_variants_included": True,
        "caller_subset_allowed": False,
        "caller_preferred_order_allowed": False,
        "variant_selected": False,
        "reference_candidate_audio_bound_by_hash": True,
        "reference_candidate_audio_copied": False,
        "new_source_bound": False,
        "new_track_id_bound": False,
        "pilot_request_schema_implemented": False,
        "pilot_execution_authorised": False,
        "model_or_worker_execution_permitted": False,
        "reusable_separator_strategy_established": False,
        "separator_accepted_as_product_default": False,
        "product_route_enabled": False,
        "publication_ready": False,
    }
    assert result["effects"]["handoff_plan_created"] is True
    assert result["effects"]["model_run"] is False
    assert result["permissions"] == _FALSE_PERMISSIONS
    assert result["next_action"] == (
        "design_source_bound_song_disjoint_private_pilot_request"
    )
    assert not _contains_key(result, "path")
    report = Path(result["report"])
    assert report.name == REPORT_NAME
    assert report.stat().st_mode & 0o077 == 0


def test_zero_ready_candidates_fail_closed_and_two_remain_canonical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, arguments, acceptance = _resolved_acceptance(
        tmp_path / "zero",
        monkeypatch,
        eligible=[VARIANTS[0]],
        decisions=("cannot_tell",),
    )
    readiness = _reassess(
        tmp_path / "zero",
        acceptance=acceptance,
        reviews=reviews,
        arguments=arguments,
    )
    _write_candidate_evidence(fixture)
    output_root = _private_dir(tmp_path / "zero-handoff")
    output = output_root / REPORT_NAME
    with pytest.raises(ValueError, match="no candidate is ready"):
        _prepare_private_candidate_followup_variant_pilot_handoff(
            readiness["report"],
            final_acceptance_result_path=acceptance,
            final_acceptance_review_export_paths=reviews,
            out=output,
            **arguments,
        )
    assert not output.exists()

    fixture, reviews, arguments, acceptance = _resolved_acceptance(
        tmp_path / "two",
        monkeypatch,
        eligible=list(VARIANTS),
        decisions=("accept", "accept"),
    )
    readiness = _reassess(
        tmp_path / "two",
        acceptance=acceptance,
        reviews=reviews,
        arguments=arguments,
    )
    _write_candidate_evidence(fixture)
    result = _handoff(
        tmp_path / "two",
        readiness=Path(readiness["report"]),
        acceptance=acceptance,
        reviews=reviews,
        arguments=arguments,
    )
    assert result["ready_variant_ids"] == list(VARIANTS)
    assert [item["canonical_index"] for item in result["handoff_variants"]] == [
        1,
        2,
    ]
    assert result["private_pilot_handoff"]["variant_selected"] is False


def test_changed_readiness_candidate_binding_and_existing_output_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, arguments, acceptance = _resolved_acceptance(
        tmp_path,
        monkeypatch,
        eligible=[VARIANTS[0]],
        decisions=("accept",),
    )
    readiness = _reassess(
        tmp_path,
        acceptance=acceptance,
        reviews=reviews,
        arguments=arguments,
    )
    _, execution_path = _write_candidate_evidence(fixture)

    changed = json.loads(Path(readiness["report"]).read_text(encoding="utf-8"))
    changed["private_pilot_readiness"]["variant_selected"] = True
    changed["document_sha256"] = _document_sha256(changed)
    changed_path = _write(tmp_path / "changed/readiness.json", changed)
    output_root = _private_dir(tmp_path / "changed-output")
    with pytest.raises(ValueError, match="readiness reassessment differs"):
        _prepare_private_candidate_followup_variant_pilot_handoff(
            changed_path,
            final_acceptance_result_path=acceptance,
            final_acceptance_review_export_paths=reviews,
            out=output_root / REPORT_NAME,
            **arguments,
        )

    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    execution["bindings"]["candidate_report_sha256"] = "0" * 64
    execution["document_sha256"] = _document_sha256(execution)
    _write(execution_path, execution)
    candidate_output = _private_dir(tmp_path / "candidate-output") / REPORT_NAME
    with pytest.raises(ValueError, match="candidate evidence differs"):
        _prepare_private_candidate_followup_variant_pilot_handoff(
            readiness["report"],
            final_acceptance_result_path=acceptance,
            final_acceptance_review_export_paths=reviews,
            out=candidate_output,
            **arguments,
        )
    assert not candidate_output.exists()

    existing = _write(_private_dir(tmp_path / "existing") / REPORT_NAME, {"keep": True})
    with pytest.raises(FileExistsError):
        _prepare_private_candidate_followup_variant_pilot_handoff(
            readiness["report"],
            final_acceptance_result_path=acceptance,
            final_acceptance_review_export_paths=reviews,
            out=existing,
            **arguments,
        )
    assert json.loads(existing.read_text(encoding="utf-8")) == {"keep": True}


def test_post_publish_evidence_change_removes_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, reviews, arguments, acceptance = _resolved_acceptance(
        tmp_path,
        monkeypatch,
        eligible=[VARIANTS[0]],
        decisions=("accept",),
    )
    readiness = _reassess(
        tmp_path,
        acceptance=acceptance,
        reviews=reviews,
        arguments=arguments,
    )
    _write_candidate_evidence(fixture)

    import sunofriend._separation_candidate_followup_variant_private_pilot_handoff as subject

    original = subject._derive_final_readiness_result
    calls = 0

    def fail_after_publish(*args: object, **kwargs: object) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("evidence changed after publication")
        return original(*args, **kwargs)

    monkeypatch.setattr(subject, "_derive_final_readiness_result", fail_after_publish)
    output_root = _private_dir(tmp_path / "unstable-handoff")
    output = output_root / REPORT_NAME
    with pytest.raises(ValueError, match="evidence changed"):
        _prepare_private_candidate_followup_variant_pilot_handoff(
            readiness["report"],
            final_acceptance_result_path=acceptance,
            final_acceptance_review_export_paths=reviews,
            out=output,
            **arguments,
        )
    assert not output.exists()


def _handoff(
    tmp_path: Path,
    *,
    readiness: Path,
    acceptance: Path,
    reviews: list[Path],
    arguments: dict[str, object],
) -> dict[str, Any]:
    output_root = _private_dir(tmp_path / "pilot-handoff")
    return _prepare_private_candidate_followup_variant_pilot_handoff(
        readiness,
        final_acceptance_result_path=acceptance,
        final_acceptance_review_export_paths=reviews,
        out=output_root / REPORT_NAME,
        **arguments,
    )


def _write_candidate_evidence(fixture: dict[str, object]) -> tuple[Path, Path]:
    root = Path(fixture["variant_root"])
    context = fixture["context"]
    clock = fixture["stitch_document"]["clock"]
    definitions = context["plan"]["protocol"]["candidate_variants"]
    source_variants = context["candidates"]["variants"]
    variants = []
    for index, (source, definition) in enumerate(
        zip(source_variants, definitions), start=1
    ):
        variants.append(
            {
                "variant_id": source["variant_id"],
                "definition": {
                    **definition,
                    "failed_edge_blend_frames": 100 * index,
                    "failed_edge_source": "fixture",
                    "reinference_source": "fixture",
                },
                "artifacts": source["artifacts"],
                "patches": [],
                "review_status": "not_reviewed",
                "selected": False,
            }
        )
    candidate = {
        "schema": "sunofriend.private-separation-candidate-followup-remediation-candidates.v1",
        "status": "candidate_variants_complete_review_required",
        "evidence_scope": "private_development_only",
        "policy_id": "fixture",
        "bindings": {},
        "clock": clock,
        "protocol": {"candidate_variants": [item["definition"] for item in variants]},
        "variants": variants,
        "summary": {"candidate_variant_count": len(variants)},
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {},
    }
    candidate["document_sha256"] = _document_sha256(candidate)
    candidate_path = _write(
        root / CANDIDATES_DIRECTORY / CANDIDATE_REPORT_NAME, candidate
    )
    execution = {
        "schema": EXECUTION_SCHEMA,
        "status": EXECUTION_STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "candidate_report_sha256": _sha256(candidate_path),
            "candidate_document_sha256": candidate["document_sha256"],
        },
        "clock": clock,
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {},
    }
    execution["document_sha256"] = _document_sha256(execution)
    execution_path = _write(root / EXECUTION_REPORT_NAME, execution)
    return candidate_path, execution_path


def _contains_key(value: Any, needle: str) -> bool:
    if isinstance(value, dict):
        return needle in value or any(
            _contains_key(item, needle) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_key(item, needle) for item in value)
    return False
