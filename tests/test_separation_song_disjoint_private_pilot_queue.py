from __future__ import annotations

import json
from pathlib import Path

import pytest

from sunofriend import _separation_song_disjoint_private_pilot_queue as queue
from sunofriend._separation_authorised_excerpt import _document_sha256


def _context(tmp_path: Path, *, suffix: str = "a") -> dict[str, object]:
    root = tmp_path / f"pipeline-{suffix}"
    root.mkdir(mode=0o700)
    evidence_path = root / "EVIDENCE" / "evidence.json"
    package_dir = root / "STITCH"
    review_html = package_dir / "BOUNDARY-REVIEW" / "review.html"
    pipeline_document = {"document_sha256": f"{suffix}" * 64}
    evidence_document = {"document_sha256": "e" * 64}
    return {
        "root": root,
        "pipeline_report": {"document": pipeline_document},
        "evidence_path": evidence_path,
        "evidence": {"document": evidence_document},
        "package_dir": package_dir,
        "review_html": review_html,
        "package_commitment": f"{suffix}" * 64,
        "track_id": f"track-{suffix}",
        "track_title": f"Track {suffix.upper()}",
        "boundary_count": 12,
        "full_song_role_count": 3,
    }


def _review(
    tmp_path: Path,
    *,
    package_commitment: str,
    suffix: str = "a",
    owner_only: bool = True,
) -> dict[str, object]:
    return {
        "path": tmp_path / f"review-{suffix}.json",
        "document": {},
        "sha256": f"{suffix}" * 64,
        "owner_only": owner_only,
        "package_commitment": package_commitment,
    }


def test_queue_reports_pending_without_inventing_a_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(queue, "_load_pipeline_context", lambda root: context)
    monkeypatch.setattr(queue, "_discover_review_exports", lambda *args, **kwargs: [])

    result = queue._build_song_disjoint_private_pilot_review_queue(
        [context["root"]]
    )

    assert result["pilots"][0]["state"] == "human_review_pending"
    assert result["summary"]["all_reviews_verified_complete"] is False
    assert result["effects"]["answer_key_opened"] is False
    assert result["effects"]["human_review_completed_or_mutated"] is False
    assert result["permissions"] == {
        **queue.PIPELINE_FALSE_PERMISSIONS,
        "bounded_private_pilot_output_use": False,
    }
    assert str(tmp_path) not in repr(result["pilots"])
    assert result["local_actions"][0]["review_html"] == str(
        context["review_html"]
    )


def test_queue_requires_owner_only_mode_before_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    review = _review(
        tmp_path,
        package_commitment=str(context["package_commitment"]),
        owner_only=False,
    )
    monkeypatch.setattr(queue, "_load_pipeline_context", lambda root: context)
    monkeypatch.setattr(
        queue,
        "_discover_review_exports",
        lambda *args, **kwargs: [review],
    )
    monkeypatch.setattr(
        queue,
        "_status_private_song_disjoint_pilot_review",
        lambda *args, **kwargs: pytest.fail("insecure export was verified"),
    )

    result = queue._build_song_disjoint_private_pilot_review_queue(
        [context["root"]]
    )

    entry = result["pilots"][0]
    assert entry["state"] == "matching_review_export_requires_owner_only_mode"
    assert result["local_actions"][0]["next_command"].startswith("chmod 600 ")


def test_queue_verifies_one_complete_export_without_resolving_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    review = _review(
        tmp_path,
        package_commitment=str(context["package_commitment"]),
    )
    monkeypatch.setattr(queue, "_load_pipeline_context", lambda root: context)
    monkeypatch.setattr(
        queue,
        "_discover_review_exports",
        lambda *args, **kwargs: [review],
    )
    monkeypatch.setattr(
        queue,
        "_status_private_song_disjoint_pilot_review",
        lambda *args, **kwargs: {
            "document_sha256": "f" * 64,
            "assessment_preview": {
                "would_authorize_bounded_private_pilot_output_use": True,
            },
        },
    )

    result = queue._build_song_disjoint_private_pilot_review_queue(
        [context["root"]]
    )

    entry = result["pilots"][0]
    assert entry["state"] == "complete_review_verified_unresolved"
    assert entry["would_authorize_bounded_private_pilot_output_use"] is True
    assert result["summary"]["all_reviews_verified_complete"] is True
    assert result["effects"]["review_resolved"] is False
    assert "private-separation-song-disjoint-pilot-review.py" in (
        result["local_actions"][0]["next_command"]
    )


def test_queue_rejects_distinct_exports_for_one_commitment_as_a_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    reviews = [
        _review(
            tmp_path,
            package_commitment=str(context["package_commitment"]),
            suffix=suffix,
        )
        for suffix in ("b", "c")
    ]
    monkeypatch.setattr(queue, "_load_pipeline_context", lambda root: context)
    monkeypatch.setattr(
        queue,
        "_discover_review_exports",
        lambda *args, **kwargs: reviews,
    )

    result = queue._build_song_disjoint_private_pilot_review_queue(
        [context["root"]]
    )

    assert result["pilots"][0]["state"] == "matching_review_export_conflict"
    assert result["effects"]["review_resolved"] is False


def test_queue_counts_duplicate_unmatched_exports_as_one_content_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    unmatched = _review(
        tmp_path,
        package_commitment="f" * 64,
        suffix="z",
    )
    duplicate = {**unmatched, "path": tmp_path / "duplicate.json"}
    monkeypatch.setattr(queue, "_load_pipeline_context", lambda root: context)
    monkeypatch.setattr(
        queue,
        "_discover_review_exports",
        lambda *args, **kwargs: [unmatched, duplicate],
    )

    result = queue._build_song_disjoint_private_pilot_review_queue(
        [context["root"]]
    )

    assert result["summary"]["reviewed_export_candidate_count"] == 2
    assert result["summary"]["unmatched_reviewed_export_content_count"] == 1


def test_review_directory_discovery_is_non_recursive_and_marks_permissions(
    tmp_path: Path,
) -> None:
    review_dir = tmp_path / "reviews"
    review_dir.mkdir()
    payload = {
        "schema": queue.REVIEW_SCHEMA,
        "status": "reviewed",
        "evidence_scope": "private_development_only",
        "package_commitment": "a" * 64,
    }
    insecure = review_dir / "review.json"
    insecure.write_text(json.dumps(payload), encoding="utf-8")
    insecure.chmod(0o644)
    unrelated = review_dir / "other.json"
    unrelated.write_text("{}\n", encoding="utf-8")
    nested = review_dir / "nested"
    nested.mkdir()
    (nested / "hidden.json").write_text(json.dumps(payload), encoding="utf-8")

    discovered = queue._discover_review_exports(
        [],
        review_directories=[review_dir],
    )

    assert len(discovered) == 1
    assert discovered[0]["path"] == insecure
    assert discovered[0]["owner_only"] is False


def test_queue_report_is_fresh_owner_only_and_path_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(queue, "_load_pipeline_context", lambda root: context)
    monkeypatch.setattr(queue, "_discover_review_exports", lambda *args, **kwargs: [])
    output_parent = tmp_path / "output"
    output_parent.mkdir(mode=0o700)
    output_parent.chmod(0o700)
    output = output_parent / queue.REPORT_NAME

    result = queue._build_song_disjoint_private_pilot_review_queue(
        [context["root"]],
        out=output,
    )

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert result["report"] == str(output)
    assert output.stat().st_mode & 0o777 == 0o600
    assert persisted["effects"]["queue_report_created"] is True
    assert persisted["document_sha256"] == _document_sha256(persisted)
    assert str(tmp_path) not in repr(persisted)
    assert "local_actions" not in persisted


def test_queue_rejects_duplicate_pipeline_commitments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _context(tmp_path, suffix="a")
    second = _context(tmp_path, suffix="b")
    second["package_commitment"] = first["package_commitment"]
    contexts = iter((first, second))
    monkeypatch.setattr(queue, "_load_pipeline_context", lambda root: next(contexts))
    monkeypatch.setattr(queue, "_discover_review_exports", lambda *args, **kwargs: [])

    with pytest.raises(ValueError, match="commitments must be distinct"):
        queue._build_song_disjoint_private_pilot_review_queue(
            [first["root"], second["root"]]
        )
