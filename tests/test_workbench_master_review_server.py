from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
import soundfile

import sunofriend.workbench_listening_master as master_service
import sunofriend.workbench_master_review as master_review
from sunofriend.workbench_master_review import (
    BALANCED_CONTROL,
    CANDIDATE_A,
    CANDIDATE_B,
    LISTENING_MASTER,
    MASTER_REVIEW_COMPARISON_SCHEMA,
    MASTER_REVIEW_RESULT_SCHEMA,
    MASTER_REVIEW_SCHEMA,
)
from sunofriend.workbench_developer import trace_response_facts
from sunofriend.workbench_server import _workbench_master_reviewer_key
from tests.test_workbench_listening_master import (
    _ListeningMasterHTTPFixture,
    _contains_path_key,
    _fake_verification,
    _master_request,
    _stable_review,
)


BROWSER_REVIEWER_KEY = "browser-reviewer-key-must-be-rejected"


def _audio_master_builder(
    source_path: str | Path,
    *,
    output_path: str | Path,
    report_path: str | Path,
    ffmpeg_path: str | Path | None = None,
) -> dict[str, Any]:
    del ffmpeg_path
    values, sample_rate = soundfile.read(
        str(source_path),
        dtype="float64",
        always_2d=True,
    )
    soundfile.write(
        str(output_path),
        values * 1.5,
        sample_rate,
        subtype="PCM_24",
    )
    Path(report_path).write_text('{"test":true}\n', encoding="utf-8")
    return {"status": "complete"}


def _review_verification(
    source_path: str | Path,
    master_path: str | Path,
    receipt_path: str | Path,
) -> dict[str, Any]:
    verification = _fake_verification(
        source_path,
        master_path,
        receipt_path,
    )
    for key, path in (
        ("source", Path(source_path)),
        ("master", Path(master_path)),
    ):
        info = soundfile.info(str(path))
        verification[key].update(
            {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
                "format": info.format,
                "subtype": info.subtype,
                "sample_rate": info.samplerate,
                "channels": info.channels,
                "frames": info.frames,
                "duration_seconds": info.duration,
            }
        )
    receipt = Path(receipt_path)
    verification["receipt_file"] = {
        "sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
        "bytes": receipt.stat().st_size,
    }
    return verification


class _ReadyReviewHTTP:
    def __init__(self, root: Path) -> None:
        self.http = _ListeningMasterHTTPFixture(root)
        self.http.server.listening_masters._builder = Mock(
            side_effect=_audio_master_builder
        )
        _project, balanced_payload = self.http.create_balanced()
        balanced = balanced_payload["balanced_arrangement"]
        status, payload = self.http.json_request(
            "POST",
            f"/api/listening-master?token={self.http.token}",
            _master_request(balanced),
        )
        assert status == 200, payload
        status, self.project = self.http.json_request(
            "GET",
            f"/api/project?token={self.http.token}",
        )
        assert status == 200
        assert self.project["balanced_arrangement"] is not None
        assert self.project["listening_master"] is not None

    def close(self) -> None:
        self.http.close()

    def prepare_request(
        self,
    ) -> dict[str, Any]:
        return {
            "selection_manifest_sha256": self.project[
                "decoded_arrangement_selection"
            ]["selection_manifest_sha256"],
            "balanced_arrangement_manifest_sha256": self.project[
                "balanced_arrangement"
            ]["manifest_sha256"],
            "listening_master_manifest_sha256": self.project[
                "listening_master"
            ]["manifest_sha256"],
            "start_seconds": 0.25,
            "end_seconds": 1.25,
        }

    def prepare(self) -> dict[str, Any]:
        status, payload = self.http.json_request(
            "POST",
            f"/api/listening-master-review/prepare?token={self.http.token}",
            self.prepare_request(),
        )
        assert status == 200, payload
        return payload["comparison"]

    def restart(self) -> None:
        self.http.restart()
        status, self.project = self.http.json_request(
            "GET",
            f"/api/project?token={self.http.token}",
        )
        assert status == 200


@pytest.fixture
def review_http(
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


def _complete_request(
    comparison: Mapping[str, Any],
    *,
    heard_a: bool = True,
    heard_b: bool = True,
) -> dict[str, Any]:
    return {
        "comparison_sha256": comparison["comparison_sha256"],
        "expected_revision": comparison["expected_revision"],
        "heard": {
            CANDIDATE_A: heard_a,
            CANDIDATE_B: heard_b,
        },
        "choice": CANDIDATE_A,
        "problem_tags": {
            CANDIDATE_A: ["muddy"],
            CANDIDATE_B: ["harsh"],
        },
        "notes": "Candidate A is easier to hear.",
    }


def _row_count(root: Path, table: str) -> int:
    with sqlite3.connect(root / "reviews.sqlite3") as connection:
        row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    assert row is not None
    return int(row[0])


def _artifact_bytes(
    fixture: _ReadyReviewHTTP,
) -> dict[str, tuple[int, str]]:
    state = fixture.http.server.store.current_state(fixture.http.catalog)
    balanced = fixture.http.server.artifacts.cached_balanced_arrangement(
        fixture.http.catalog,
        state,
    )
    assert balanced is not None
    listening_master = fixture.http.server.listening_masters.cached(balanced)
    assert listening_master is not None
    records = {
        "balanced_preview": balanced["preview"],
        "balanced_report": balanced["report"],
        "listening_master": listening_master["master"],
        "listening_master_receipt": listening_master["receipt"],
    }
    result = {}
    for key, record in records.items():
        path = Path(record["path"])
        payload = path.read_bytes()
        result[key] = (len(payload), hashlib.sha256(payload).hexdigest())
    return result


def _product_snapshot(fixture: _ReadyReviewHTTP) -> dict[str, Any]:
    status, project = fixture.http.json_request(
        "GET",
        f"/api/project?token={fixture.http.token}",
    )
    assert status == 200
    status, pack = fixture.http.json_request(
        "GET",
        f"/api/garageband-pack-plan?token={fixture.http.token}",
    )
    assert status == 200
    state = fixture.http.server.store.current_state(fixture.http.catalog)
    return {
        "product_outputs": project["product_outputs"],
        "selection": project["decoded_arrangement_selection"],
        "workbench_state": state,
        "workbench_review": _stable_review(
            fixture.http.server.store.export_review(fixture.http.catalog)
        ),
        "pack_basket": pack["plan"]["basket"],
        "artifact_bytes": _artifact_bytes(fixture),
    }


def _assert_raw_reviewer_key_absent(
    fixture: _ReadyReviewHTTP,
    *documents: object,
) -> None:
    raw_keys = (
        BROWSER_REVIEWER_KEY,
        _workbench_master_reviewer_key(
            fixture.http.catalog["project_id"]
        ),
    )
    encoded_documents = json.dumps(documents, sort_keys=True).encode("utf-8")
    for key in raw_keys:
        assert key.encode("utf-8") not in encoded_documents
    for path in fixture.http.state_dir.rglob("*"):
        if path.is_file() and not path.is_symlink():
            payload = path.read_bytes()
            for key in raw_keys:
                assert key.encode("utf-8") not in payload, path


def _assert_blind_candidate_projection(
    comparison: Mapping[str, Any],
) -> None:
    candidates = comparison["candidates"]
    assert set(candidates) == {CANDIDATE_A, CANDIDATE_B}
    for slot in (CANDIDATE_A, CANDIDATE_B):
        candidate = candidates[slot]
        assert set(candidate) == {
            "sample_rate",
            "channels",
            "frames",
            "audio",
            "audio_url",
        }
        assert "identity" not in candidate
        assert "applied_gain_db" not in candidate
        assert "rms_dbfs" not in candidate
        assert "sample_peak_dbfs" not in candidate
        assert _contains_path_key(candidate) is False
    encoded = json.dumps(candidates, sort_keys=True)
    assert BALANCED_CONTROL not in encoded
    assert LISTENING_MASTER not in encoded
    for forbidden in ("applied_gain_db", "rms_dbfs", "sample_peak_dbfs"):
        assert forbidden not in encoded


def test_static_module_is_public_but_review_routes_require_token(
    review_http: _ReadyReviewHTTP,
) -> None:
    fixture = review_http
    status, headers, body = fixture.http.request(
        "GET",
        "/workbench-master-review.js",
    )
    assert status == 200
    assert headers["content-type"].startswith("text/javascript")
    assert b"createMasterReview" in body
    assert b"reviewer_session_key" not in body
    assert b"localStorage" not in body

    for method, path, value in (
        (
            "POST",
            "/api/listening-master-review/prepare",
            fixture.prepare_request(),
        ),
        (
            "GET",
            "/api/listening-master-review-export?kind=review&review_id="
            f"{'0' * 64}",
            None,
        ),
    ):
        if value is None:
            status, _headers, payload = fixture.http.request(method, path)
            parsed = json.loads(payload)
        else:
            status, parsed = fixture.http.json_request(method, path, value)
        assert status == 403
        assert "token" in parsed["error"]


def test_prepare_requires_exact_hashes_and_exposes_anonymous_frozen_media(
    review_http: _ReadyReviewHTTP,
) -> None:
    fixture = review_http
    request = fixture.prepare_request()
    state_before = fixture.http.server.store.current_state(fixture.http.catalog)
    review_before = _stable_review(
        fixture.http.server.store.export_review(fixture.http.catalog)
    )

    cases = (
        ({}, 400),
        ({key: value for key, value in request.items() if key != "end_seconds"}, 400),
        ({**request, "unexpected": True}, 400),
        (
            {
                **request,
                "reviewer_session_key": BROWSER_REVIEWER_KEY,
            },
            400,
        ),
        (
            {
                **request,
                "selection_manifest_sha256": request[
                    "selection_manifest_sha256"
                ].upper(),
            },
            400,
        ),
        ({**request, "selection_manifest_sha256": "0" * 64}, 409),
        (
            {
                **request,
                "balanced_arrangement_manifest_sha256": "0" * 64,
            },
            409,
        ),
        (
            {
                **request,
                "listening_master_manifest_sha256": "0" * 64,
            },
            409,
        ),
    )
    for body, expected_status in cases:
        status, payload = fixture.http.json_request(
            "POST",
            f"/api/listening-master-review/prepare?token={fixture.http.token}",
            body,
        )
        assert status == expected_status
        assert "error" in payload

    comparison = fixture.prepare()
    assert comparison["schema"] == MASTER_REVIEW_COMPARISON_SCHEMA
    assert comparison["status"] == "unreviewed"
    assert comparison["blind"] is True
    assert comparison["expected_revision"] == 0
    assert "assignment" not in comparison
    assert "assignment_nonce" not in comparison
    assert _contains_path_key(comparison) is False
    assert BROWSER_REVIEWER_KEY not in json.dumps(comparison, sort_keys=True)
    _assert_blind_candidate_projection(comparison)
    assert all(value is False for value in comparison["effects"].values())
    trace_facts = trace_response_facts(
        "/api/listening-master-review/prepare",
        {"comparison": comparison},
    )
    assert trace_facts == {
        "schema": MASTER_REVIEW_COMPARISON_SCHEMA,
        "status": "unreviewed",
    }
    encoded_trace = json.dumps(trace_facts, sort_keys=True)
    for forbidden in (
        CANDIDATE_A,
        CANDIDATE_B,
        BALANCED_CONTROL,
        LISTENING_MASTER,
        "applied_gain_db",
        "rms_dbfs",
        "sample_peak_dbfs",
    ):
        assert forbidden not in encoded_trace

    for slot in (CANDIDATE_A, CANDIDATE_B):
        candidate = comparison["candidates"][slot]
        url = candidate["audio_url"]
        media_id = url.split("/media/", 1)[1].split("?", 1)[0]
        assert fixture.http.server.media[media_id]["_freeze_on_serve"] is True
        status, headers, body = fixture.http.request(
            "GET",
            url,
            headers={"Range": "bytes=10-29"},
        )
        assert status == 206
        assert len(body) == 20
        assert headers["content-range"].startswith("bytes 10-29/")
        assert headers["accept-ranges"] == "bytes"
        status, _headers, body = fixture.http.request("GET", url)
        assert status == 200
        assert len(body) == candidate["audio"]["bytes"]
        assert hashlib.sha256(body).hexdigest() == candidate["audio"]["sha256"]

    assert _row_count(
        fixture.http.state_dir / "listening-master-reviews",
        "review_events",
    ) == 0
    assert fixture.http.server.store.current_state(fixture.http.catalog) == (
        state_before
    )
    assert _stable_review(
        fixture.http.server.store.export_review(fixture.http.catalog)
    ) == review_before
    _assert_raw_reviewer_key_absent(fixture, comparison)


def test_complete_requires_both_heard_then_downloads_blind_review_and_resolution(
    review_http: _ReadyReviewHTTP,
) -> None:
    fixture = review_http
    comparison = fixture.prepare()
    review_root = fixture.http.state_dir / "listening-master-reviews"
    product_before = _product_snapshot(fixture)

    status, payload = fixture.http.json_request(
        "POST",
        f"/api/listening-master-review?token={fixture.http.token}",
        {
            **_complete_request(comparison),
            "reviewer_session_key": BROWSER_REVIEWER_KEY,
        },
    )
    assert status == 400
    assert "reviewer_session_key" in payload["error"]
    assert _row_count(review_root, "review_events") == 0

    status, payload = fixture.http.json_request(
        "POST",
        f"/api/listening-master-review?token={fixture.http.token}",
        _complete_request(comparison, heard_b=False),
    )
    assert status == 400
    assert "marked heard" in payload["error"]
    assert _row_count(review_root, "review_events") == 0
    assert _row_count(review_root, "review_resolutions") == 0

    status, payload = fixture.http.json_request(
        "POST",
        f"/api/listening-master-review?token={fixture.http.token}",
        _complete_request(comparison),
    )
    assert status == 200
    completed = payload["comparison"]
    assert completed["schema"] == MASTER_REVIEW_COMPARISON_SCHEMA
    assert completed["status"] == "reviewed"
    assert completed["blind"] is True
    assert "assignment" not in completed
    assert "assignment_nonce" not in completed
    _assert_blind_candidate_projection(completed)
    review = completed["review"]
    assert review["response"]["heard"] == {
        CANDIDATE_A: True,
        CANDIDATE_B: True,
    }
    assert review["choice"] == CANDIDATE_A
    assert _row_count(review_root, "review_events") == 1
    assert _row_count(review_root, "review_resolutions") == 0
    assert _product_snapshot(fixture) == product_before

    fixture.restart()
    reloaded = fixture.prepare()
    assert reloaded["comparison_sha256"] == completed["comparison_sha256"]
    assert reloaded["status"] == "reviewed"
    assert reloaded["expected_revision"] == 1
    assert reloaded["review"]["review_id"] == review["review_id"]
    assert reloaded["review"]["review_sha256"] == review["review_sha256"]
    assert reloaded["review"]["response"] == review["response"]
    assert _row_count(review_root, "review_events") == 1
    assert _row_count(review_root, "review_resolutions") == 0
    assert _product_snapshot(fixture) == product_before

    status, unresolved = fixture.http.json_request(
        "GET",
        "/api/listening-master-review-export?kind=result"
        f"&review_id={review['review_id']}&token={fixture.http.token}",
    )
    assert status == 400
    assert "not been resolved" in unresolved["error"]

    status, headers, body = fixture.http.request(
        "GET",
        review["review_url"],
    )
    assert status == 200
    assert "attachment" in headers["content-disposition"]
    blind_document = json.loads(body)
    assert blind_document["schema"] == MASTER_REVIEW_SCHEMA
    assert blind_document["blind"] is True
    assert "assignment" not in blind_document
    assert "assignment_nonce" not in blind_document
    response_json = json.dumps(blind_document["response"], sort_keys=True)
    assert BALANCED_CONTROL not in response_json
    assert LISTENING_MASTER not in response_json

    status, payload = fixture.http.json_request(
        "POST",
        f"/api/listening-master-review/resolve?token={fixture.http.token}",
        {
            "comparison_sha256": completed["comparison_sha256"],
            "review_id": review["review_id"],
            "review_sha256": review["review_sha256"],
        },
    )
    assert status == 200
    resolved = payload["comparison"]
    assert resolved["schema"] == MASTER_REVIEW_RESULT_SCHEMA
    assert resolved["status"] == "resolved"
    assert resolved["blind"] is False
    assert resolved["result"]["assignment"] in (
        {
            CANDIDATE_A: BALANCED_CONTROL,
            CANDIDATE_B: LISTENING_MASTER,
        },
        {
            CANDIDATE_A: LISTENING_MASTER,
            CANDIDATE_B: BALANCED_CONTROL,
        },
    )
    assert resolved["result"]["resolved_choice"] in {
        BALANCED_CONTROL,
        LISTENING_MASTER,
    }
    assert len(resolved["result"]["assignment_nonce"]) == 64
    assert _row_count(review_root, "review_events") == 1
    assert _row_count(review_root, "review_resolutions") == 1

    status, headers, body = fixture.http.request(
        "GET",
        resolved["result"]["result_url"],
    )
    assert status == 200
    assert "attachment" in headers["content-disposition"]
    result_document = json.loads(body)
    assert result_document["schema"] == MASTER_REVIEW_RESULT_SCHEMA
    assert set(result_document["assignment"].values()) == {
        BALANCED_CONTROL,
        LISTENING_MASTER,
    }
    assert result_document["resolved_choice"] in {
        BALANCED_CONTROL,
        LISTENING_MASTER,
    }

    product_after = _product_snapshot(fixture)
    assert product_after == product_before
    _assert_raw_reviewer_key_absent(
        fixture,
        comparison,
        completed,
        blind_document,
        resolved,
        result_document,
    )


@pytest.mark.parametrize("drift", ["selection", "control", "master"])
def test_complete_rejects_selection_control_or_master_drift(
    review_http: _ReadyReviewHTTP,
    drift: str,
) -> None:
    fixture = review_http
    comparison = fixture.prepare()
    review_root = fixture.http.state_dir / "listening-master-reviews"

    if drift == "selection":
        stem = fixture.http.catalog["stems"][0]
        candidate = stem["candidates"][0]
        fixture.http.server.store.append(
            fixture.http.catalog,
            {
                "event_type": "candidate_decision",
                "stem_id": stem["stem_id"],
                "candidate_id": candidate["candidate_id"],
                "decision": "reject",
                "context": "full_mix",
                "problem_tags": [],
            },
        )
        context = nullcontext()
    elif drift == "control":
        state = fixture.http.server.store.current_state(fixture.http.catalog)
        balanced = fixture.http.server.artifacts.cached_balanced_arrangement(
            fixture.http.catalog,
            state,
        )
        assert balanced is not None
        changed = {**balanced, "manifest_sha256": "f" * 64}
        context = patch.object(
            fixture.http.server.artifacts,
            "cached_balanced_arrangement",
            return_value=changed,
        )
    else:
        state = fixture.http.server.store.current_state(fixture.http.catalog)
        balanced = fixture.http.server.artifacts.cached_balanced_arrangement(
            fixture.http.catalog,
            state,
        )
        assert balanced is not None
        current_master = fixture.http.server.listening_masters.cached(balanced)
        assert current_master is not None
        changed = {**current_master, "manifest_sha256": "e" * 64}
        context = patch.object(
            fixture.http.server.listening_masters,
            "cached",
            return_value=changed,
        )

    with context:
        status, payload = fixture.http.json_request(
            "POST",
            f"/api/listening-master-review?token={fixture.http.token}",
            _complete_request(comparison),
        )
    assert status == 409
    assert "error" in payload
    assert _row_count(review_root, "review_events") == 0
    assert _row_count(review_root, "review_resolutions") == 0
