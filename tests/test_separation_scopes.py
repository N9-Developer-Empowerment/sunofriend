from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from sunofriend.audio_formats import file_sha256
from sunofriend.separation_alpha import _build_report, _validated_worker_outputs
from sunofriend.separation_review import (
    REVIEW_SCHEMA,
    render_review_html,
    render_start_here,
    validate_review_document,
)
from sunofriend.separation_scopes import (
    CAPABILITIES_SCHEMA,
    DEFAULT_SCOPE_ID,
    FULL_STEM_SCOPE_ID,
    require_executable_scope,
    separation_capabilities,
    separation_scope,
)


def test_capabilities_expose_full_stems_as_public_opt_in() -> None:
    document = separation_capabilities()
    scopes = {item["id"]: item for item in document["scopes"]}

    assert document["schema"] == CAPABILITIES_SCHEMA
    assert document["default_scope_id"] == DEFAULT_SCOPE_ID
    assert scopes[DEFAULT_SCOPE_ID]["executable"] is True
    assert [role["id"] for role in scopes[FULL_STEM_SCOPE_ID]["roles"]] == [
        "vocals",
        "drums",
        "bass",
        "other",
    ]
    assert scopes[FULL_STEM_SCOPE_ID]["executable"] is True
    assert scopes[FULL_STEM_SCOPE_ID]["worker_profile_id"] == (
        "scnet-large-musdb-release-v1"
    )
    assert scopes[FULL_STEM_SCOPE_ID]["implementation_available"] is True
    assert scopes[FULL_STEM_SCOPE_ID]["profile_status"] == "public_opt_in"
    assert scopes[FULL_STEM_SCOPE_ID]["blockers"] == []


def test_qualified_full_stem_scope_can_be_selected_explicitly() -> None:
    scope = require_executable_scope(FULL_STEM_SCOPE_ID)
    assert scope.worker_profile_id == "scnet-large-musdb-release-v1"


def test_review_handoff_renders_every_declared_role() -> None:
    scope = separation_scope(FULL_STEM_SCOPE_ID)
    report = {
        "source": {"name": "authorised & local.wav"},
        "separator": {
            "scope_id": FULL_STEM_SCOPE_ID,
            "profile_id": "demucs-mlx-htdemucs-v1",
            "role_details": [role.to_dict() for role in scope.roles],
        },
        "feedback": {"public_report_url": "https://example.test/report?a=1&b=2"},
        "document_sha256": "a" * 64,
    }

    start_here = render_start_here(report)
    page = render_review_html(report)

    for role in scope.roles:
        assert role.relative_path in start_here
        assert f"../{role.relative_path}" in page
        assert role.label in page
    assert "I heard all 6 tracks" in page
    assert "experimental-separation-review.v3" in page
    assert "stem_usefulness:stemUsefulness" in page
    assert "per_role_issues:issues" in page
    assert "Copy text-only feedback" in page
    assert "authorised &amp; local.wav" in page
    assert "https://example.test/report?a=1&amp;b=2" in page


def test_review_schema_accepts_poor_feedback_without_treating_it_as_failure() -> None:
    scope = separation_scope(FULL_STEM_SCOPE_ID)
    report = {
        "source": {"name": "private.wav"},
        "separator": {
            "scope_id": FULL_STEM_SCOPE_ID,
            "profile_id": "demucs-mlx-htdemucs-v1",
            "role_details": [role.to_dict() for role in scope.roles],
        },
        "feedback": {"public_report_url": "https://example.test"},
        "document_sha256": "b" * 64,
    }
    roles = [role.role_id for role in scope.roles]
    review = {
        "schema": REVIEW_SCHEMA,
        "binding": {
            "scope_id": FULL_STEM_SCOPE_ID,
            "profile_id": "demucs-mlx-htdemucs-v1",
            "separation_report_sha256": "b" * 64,
        },
        "heard_all_tracks": True,
        "overall_usefulness": "not_useful",
        "stem_usefulness": {role: "not_useful" for role in roles},
        "per_role_issues": {role: ["bleed"] for role in roles},
        "downstream_midi": "not_tested",
        "notes": "Poor, but valid feedback.",
        "audio_included": False,
        "telemetry_included": False,
        "filename_included": False,
    }

    assert validate_review_document(review, report=report) == review
    changed = {**review, "binding": {**review["binding"], "profile_id": "wrong"}}
    with pytest.raises(ValueError, match="binding differs"):
        validate_review_document(changed, report=report)


def test_worker_output_contract_rejects_missing_role() -> None:
    outputs = {
        role: {"bytes": 1, "sha256": role}
        for role in ("vocals", "instrumental", "source_reference")
    }
    worker = {"status": "complete_unreviewed", "outputs": outputs}

    with pytest.raises(RuntimeError, match="output contract differs"):
        _validated_worker_outputs(
            worker,
            expected_roles=(
                "vocals",
                "instrumental",
                "source_reference",
                "reconstruction_check",
            ),
        )


def test_report_builder_accepts_exact_core_four_role_contract(tmp_path: Path) -> None:
    scope = separation_scope(FULL_STEM_SCOPE_ID)
    source = tmp_path / "owned.wav"
    source.write_bytes(b"source")
    paths = {role.role_id: role.relative_path for role in scope.roles}
    paths.update(
        {
            "source_reference": "SOURCE/source-reference.wav",
            "reconstruction_check": "AUDIO/reconstruction-check.wav",
        }
    )
    outputs = {}
    for role, relative in paths.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"{role} persisted".encode())
        outputs[role] = {
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
    plan = SimpleNamespace(
        scope=scope,
        source=source,
        source_sha256=file_sha256(source),
        probe=SimpleNamespace(source_bytes=source.stat().st_size, duration_seconds=1.0),
        rights_category="owned",
        device="gpu",
    )

    report = _build_report(
        plan,
        worker={"status": "complete_unreviewed", "outputs": outputs},
        doctor={"status": "ready", "ready": True},
        root=tmp_path,
    )

    assert report["separator"]["scope_id"] == FULL_STEM_SCOPE_ID
    assert report["separator"]["roles"] == ["vocals", "drums", "bass", "other"]
    assert set(report["outputs"]) == set(paths)
    assert report["quality_status"] == "human_listening_required"
    assert report["document_sha256"]
