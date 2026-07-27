from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

import sunofriend.workbench_listening_master as master_service
import sunofriend.workbench_master_review as master_review
from sunofriend.workbench_master_readiness import (
    MASTER_READINESS_COMPARISON_SCHEMA,
    MASTER_READINESS_REVIEW_SCHEMA,
)
from sunofriend.workbench_server import _workbench_master_reviewer_key
from tests.test_workbench_master_review_server import (
    BROWSER_REVIEWER_KEY,
    _ReadyReviewHTTP,
    _complete_request,
    _product_snapshot,
    _review_verification,
)


@pytest.fixture
def readiness_http(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> _ReadyReviewHTTP:
    monkeypatch.setattr(
        master_service,
        "verify_listening_master_artifacts",
        _review_verification,
    )
    monkeypatch.setattr(
        master_review,
        "verify_listening_master_artifacts",
        _review_verification,
    )
    fixture = _ReadyReviewHTTP(tmp_path)
    try:
        yield fixture
    finally:
        fixture.close()


def _complete_quality(
    fixture: _ReadyReviewHTTP,
    *,
    resolve: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    comparison = fixture.prepare()
    status, payload = fixture.http.json_request(
        "POST",
        f"/api/listening-master-review?token={fixture.http.token}",
        _complete_request(comparison),
    )
    assert status == 200, payload
    reviewed = payload["comparison"]
    if not resolve:
        return reviewed, None
    status, payload = fixture.http.json_request(
        "POST",
        f"/api/listening-master-review/resolve?token={fixture.http.token}",
        {
            "comparison_sha256": reviewed["comparison_sha256"],
            "review_id": reviewed["review"]["review_id"],
            "review_sha256": reviewed["review"]["review_sha256"],
        },
    )
    assert status == 200, payload
    return reviewed, payload["comparison"]


def _readiness_anchors(
    reviewed: dict[str, Any],
    resolved: dict[str, Any],
) -> dict[str, str]:
    return {
        "quality_review_id": reviewed["review"]["review_id"],
        "quality_review_sha256": reviewed["review"]["review_sha256"],
        "quality_result_sha256": resolved["result"]["result_sha256"],
    }


def _readiness_response(readiness: dict[str, Any]) -> dict[str, Any]:
    quality = readiness["quality_review"]
    return {
        "comparison_sha256": readiness["comparison_sha256"],
        "quality_review_id": quality["quality_review_id"],
        "quality_review_sha256": quality["quality_review_sha256"],
        "quality_result_sha256": quality["quality_result_sha256"],
        "heard": {
            "balanced_control": True,
            "listening_master": True,
        },
        "choice": "listening_master",
        "problem_tags": {
            "balanced_control": [],
            "listening_master": ["harsh"],
        },
        "notes": "The native master is more immediately usable.",
    }


def _row_count(root: Path) -> int:
    with sqlite3.connect(root / "reviews.sqlite3") as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM readiness_reviews"
        ).fetchone()
    assert row is not None
    return int(row[0])


def test_readiness_is_gated_on_explicit_quality_resolution(
    readiness_http: _ReadyReviewHTTP,
) -> None:
    fixture = readiness_http
    reviewed, _ = _complete_quality(fixture, resolve=False)
    request = {
        "quality_review_id": reviewed["review"]["review_id"],
        "quality_review_sha256": reviewed["review"]["review_sha256"],
        "quality_result_sha256": "0" * 64,
    }
    status, payload = fixture.http.json_request(
        "POST",
        f"/api/listening-master-readiness/prepare?token={fixture.http.token}",
        request,
    )
    assert status == 409
    assert "resolved" in payload["error"]
    root = fixture.http.state_dir / "listening-master-readiness"
    assert _row_count(root) == 0
    assert not any(
        path.is_dir() and not path.name.startswith(".")
        for path in (root / "audio").iterdir()
    )


def test_native_readiness_reuses_exact_window_and_preserves_identity_levels(
    readiness_http: _ReadyReviewHTTP,
) -> None:
    fixture = readiness_http
    reviewed, resolved = _complete_quality(fixture, resolve=True)
    assert resolved is not None
    product_before = _product_snapshot(fixture)
    anchors = _readiness_anchors(reviewed, resolved)

    for invalid in (
        {**anchors, "start_seconds": 0},
        {**anchors, "reviewer_session_key": BROWSER_REVIEWER_KEY},
        {**anchors, "gain_db": -2.0},
    ):
        status, _payload = fixture.http.json_request(
            "POST",
            f"/api/listening-master-readiness/prepare?token={fixture.http.token}",
            invalid,
        )
        assert status == 400

    status, payload = fixture.http.json_request(
        "POST",
        f"/api/listening-master-readiness/prepare?token={fixture.http.token}",
        anchors,
    )
    assert status == 200, payload
    readiness = payload["readiness"]
    assert readiness["schema"] == MASTER_READINESS_COMPARISON_SCHEMA
    assert readiness["status"] == "unreviewed"
    assert readiness["identity_labelled"] is True
    assert readiness["native_level"] is True
    assert readiness["window"] == reviewed["window"]
    assert readiness["quality_review"] == {
        "quality_review_id": anchors["quality_review_id"],
        "quality_review_sha256": anchors["quality_review_sha256"],
        "quality_result_sha256": anchors["quality_result_sha256"],
        "quality_comparison_sha256": reviewed["comparison_sha256"],
        "quality_revision": reviewed["review"]["revision"],
        "resolved_choice": resolved["result"]["resolved_choice"],
        "explicitly_resolved": True,
        "latest_for_reviewer": True,
    }
    assert set(readiness["candidates"]) == {
        "balanced_control",
        "listening_master",
    }
    hashes: dict[str, str] = {}
    for identity, candidate in readiness["candidates"].items():
        assert candidate["subtype"] == "PCM_24"
        assert candidate["applied_gain_db"] == 0.0
        assert candidate["processing_applied"] is False
        assert candidate["frames"] == readiness["window"]["frame_count"]
        status, _headers, body = fixture.http.request(
            "GET",
            candidate["audio_url"],
        )
        assert status == 200
        assert len(body) == candidate["audio"]["bytes"]
        assert hashlib.sha256(body).hexdigest() == candidate["audio"]["sha256"]
        hashes[identity] = candidate["audio"]["sha256"]
    assert hashes["balanced_control"] != hashes["listening_master"]
    assert _product_snapshot(fixture) == product_before

    fixture.restart()
    status, payload = fixture.http.json_request(
        "POST",
        f"/api/listening-master-readiness/prepare?token={fixture.http.token}",
        anchors,
    )
    assert status == 200, payload
    restarted = payload["readiness"]
    assert restarted["comparison_sha256"] == readiness["comparison_sha256"]
    assert {
        identity: row["audio"]["sha256"]
        for identity, row in restarted["candidates"].items()
    } == hashes
    assert _product_snapshot(fixture) == product_before


def test_prepare_rechecks_latest_quality_review_before_publication(
    readiness_http: _ReadyReviewHTTP,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = readiness_http
    reviewed, resolved = _complete_quality(fixture, resolve=True)
    assert resolved is not None
    anchors = _readiness_anchors(reviewed, resolved)

    server = fixture.http.server
    state = server.store.current_state(fixture.http.catalog)
    balanced = server.artifacts.cached_balanced_arrangement(
        fixture.http.catalog,
        state,
    )
    assert balanced is not None
    listening_master = server.listening_masters.cached(balanced)
    assert listening_master is not None
    reviewer_key = _workbench_master_reviewer_key(
        fixture.http.catalog["project_id"]
    )
    newer = server.master_reviews.prepare(
        project_id=str(fixture.http.catalog["project_id"]),
        balanced=balanced,
        listening_master=listening_master,
        start_seconds=0.50,
        end_seconds=1.50,
        reviewer_session_key=reviewer_key,
    )
    newer_request = _complete_request(
        {**newer, "expected_revision": newer["current_revision"]}
    )
    original_prepare = server.master_readiness.prepare

    def prepare_then_supersede(**kwargs: Any) -> dict[str, Any]:
        prepared = original_prepare(**kwargs)
        server.master_reviews.complete(
            project_id=str(fixture.http.catalog["project_id"]),
            balanced=balanced,
            listening_master=listening_master,
            comparison_sha256=newer["comparison_sha256"],
            reviewer_session_key=reviewer_key,
            expected_revision=newer_request["expected_revision"],
            heard=newer_request["heard"],
            choice=newer_request["choice"],
            problem_tags=newer_request["problem_tags"],
            notes=newer_request["notes"],
        )
        return prepared

    monkeypatch.setattr(
        server.master_readiness,
        "prepare",
        prepare_then_supersede,
    )
    status, payload = fixture.http.json_request(
        "POST",
        f"/api/listening-master-readiness/prepare?token={fixture.http.token}",
        anchors,
    )
    assert status == 409
    assert "changed while native-level readiness was being prepared" in payload[
        "error"
    ]
    assert _row_count(
        fixture.http.state_dir / "listening-master-readiness"
    ) == 0


def test_readiness_requires_explicit_hearing_and_exports_one_immutable_response(
    readiness_http: _ReadyReviewHTTP,
) -> None:
    fixture = readiness_http
    reviewed, resolved = _complete_quality(fixture, resolve=True)
    assert resolved is not None
    anchors = _readiness_anchors(reviewed, resolved)
    status, payload = fixture.http.json_request(
        "POST",
        f"/api/listening-master-readiness/prepare?token={fixture.http.token}",
        anchors,
    )
    assert status == 200, payload
    readiness = payload["readiness"]
    request = _readiness_response(readiness)
    product_before = _product_snapshot(fixture)

    status, payload = fixture.http.json_request(
        "POST",
        f"/api/listening-master-readiness?token={fixture.http.token}",
        {
            **request,
            "heard": {
                "balanced_control": True,
                "listening_master": False,
            },
        },
    )
    assert status == 400
    assert "marked heard" in payload["error"]

    status, payload = fixture.http.json_request(
        "POST",
        f"/api/listening-master-readiness?token={fixture.http.token}",
        request,
    )
    assert status == 200, payload
    completed = payload["readiness"]
    assert completed["status"] == "reviewed"
    assert completed["review"]["choice"] == "listening_master"
    assert completed["review"]["response"]["heard"] == {
        "balanced_control": True,
        "listening_master": True,
    }
    assert completed["effects"]["feedback_recorded"] is True
    assert (
        completed["effects"]["readiness_review_record_created"] is True
    )
    assert all(
        value is False
        for key, value in completed["effects"].items()
        if key
        not in {
            "feedback_recorded",
            "readiness_review_record_created",
        }
    )
    assert _row_count(
        fixture.http.state_dir / "listening-master-readiness"
    ) == 1
    assert _product_snapshot(fixture) == product_before

    status, repeated = fixture.http.json_request(
        "POST",
        f"/api/listening-master-readiness?token={fixture.http.token}",
        request,
    )
    assert status == 200, repeated
    assert (
        repeated["readiness"]["review"]["readiness_review_id"]
        == completed["review"]["readiness_review_id"]
    )
    assert _row_count(
        fixture.http.state_dir / "listening-master-readiness"
    ) == 1

    status, changed = fixture.http.json_request(
        "POST",
        f"/api/listening-master-readiness?token={fixture.http.token}",
        {**request, "choice": "balanced_control"},
    )
    assert status == 409
    assert "different native-level response" in changed["error"]
    assert _row_count(
        fixture.http.state_dir / "listening-master-readiness"
    ) == 1

    status, headers, body = fixture.http.request(
        "GET",
        completed["review"]["review_url"],
    )
    assert status == 200
    assert "attachment" in headers["content-disposition"]
    document = json.loads(body)
    assert document["schema"] == MASTER_READINESS_REVIEW_SCHEMA
    assert (
        document["readiness_review_id"]
        == completed["review"]["readiness_review_id"]
    )
    encoded = json.dumps(document)
    assert "reviewer_session_key" not in encoded
    assert "/Users/" not in encoded
    assert _product_snapshot(fixture) == product_before


def test_readiness_routes_and_media_require_the_loopback_token(
    readiness_http: _ReadyReviewHTTP,
) -> None:
    fixture = readiness_http
    reviewed, resolved = _complete_quality(fixture, resolve=True)
    assert resolved is not None
    anchors = _readiness_anchors(reviewed, resolved)
    status, payload = fixture.http.json_request(
        "POST",
        "/api/listening-master-readiness/prepare",
        anchors,
    )
    assert status == 403
    assert "token" in payload["error"]

    status, payload = fixture.http.json_request(
        "POST",
        f"/api/listening-master-readiness/prepare?token={fixture.http.token}",
        anchors,
    )
    assert status == 200, payload
    audio_url = payload["readiness"]["candidates"]["balanced_control"][
        "audio_url"
    ]
    path = audio_url.split("?", 1)[0]
    status, _headers, _body = fixture.http.request("GET", path)
    assert status == 403
