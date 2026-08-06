from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from sunofriend.core_four_approval import SCOPE_ID
from sunofriend.separation_profiles import SCNET_RELEASE_PROFILE_ID
from sunofriend.separation_scnet_full_song_canaries import (
    LISTEN_SCHEMA,
    OUTPUT_PATHS,
    RUN_SCHEMA,
    build_canary_review_server,
    record_no_failure_canary_listen,
    render_canary_listen_html,
    validate_canary_listen_document,
)


def _run() -> dict:
    return {
        "schema": RUN_SCHEMA,
        "status": "technical_pass_listening_pending",
        "approval": {
            "approval_id": "approval-test",
            "sha256": "a" * 64,
        },
        "profile_id": SCNET_RELEASE_PROFILE_ID,
        "scope_id": SCOPE_ID,
        "objective_gates_passed": True,
        "canaries": [
            {"coverage_id": coverage}
            for coverage in (
                "vocal_forward",
                "dense_electronic",
                "acoustic_mixed",
            )
        ],
    }


def _evidence(tmp_path: Path) -> tuple[Path, dict]:
    run = _run()
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "CANARY-RUN.json").write_text(json.dumps(run), encoding="utf-8")
    review = root / "REVIEW"
    review.mkdir()
    (review / "canary-listen.html").write_text(
        render_canary_listen_html(run), encoding="utf-8"
    )
    for canary in run["canaries"]:
        for relative in OUTPUT_PATHS.values():
            path = root / "CANARIES" / canary["coverage_id"] / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test-audio")
    return root, run


def _complete_review(run: dict) -> dict:
    return {
        "schema": LISTEN_SCHEMA,
        "run_schema": RUN_SCHEMA,
        "approval_id": "approval-test",
        "approval_sha256": "a" * 64,
        "profile_id": SCNET_RELEASE_PROFILE_ID,
        "scope_id": SCOPE_ID,
        "status": "complete",
        "songs": [
            {
                "coverage_id": item["coverage_id"],
                "complete": True,
                "result": "no_catastrophic_defect",
                "details": "",
                "minimum_usefulness_rating": None,
            }
            for item in run["canaries"]
        ],
        "missing_fields": [],
        "audio_included": False,
        "telemetry_included": False,
        "exported_at": "2026-08-06T18:00:00Z",
    }


def test_canary_review_server_exposes_only_exact_local_audio_and_saves_review(
    tmp_path: Path,
) -> None:
    root, run = _evidence(tmp_path)
    server = build_canary_review_server(root, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/", timeout=5) as response:
            page = response.read().decode("utf-8")
            assert response.headers["Cache-Control"] == "no-store"
            assert "/audio/vocal_forward/vocals.wav" in page
            assert "Nothing is uploaded" in page
            assert "Save locally + download JSON" in page
            assert "Copy listening JSON" in page
            assert "Listening JSON fallback" in page
            assert "connect-src 'self'" in page
            assert r"JSON.stringify(value,null,2)+'\n'" in page
            assert "+'\n'" not in page
        request = Request(
            base + "/audio/acoustic_mixed/other.wav",
            headers={"Range": "bytes=1-4"},
        )
        with urlopen(request, timeout=5) as response:
            assert response.status == 206
            assert response.read() == b"est-"
        with pytest.raises(HTTPError) as missing:
            urlopen(base + "/CANARY-RUN.json", timeout=5)
        assert missing.value.code == 404
        with pytest.raises(HTTPError) as posted:
            urlopen(Request(base + "/", data=b"private"), timeout=5)
        assert posted.value.code == 405
        review = _complete_review(run)
        request = Request(
            base + "/review",
            data=json.dumps(review).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            receipt = json.loads(response.read())
            assert response.status == 201
            assert receipt["status"] == "recorded_and_validated"
            assert receipt["path"] == "REVIEW/canary-listen-complete.json"
            assert receipt["audio_included"] is False
            assert receipt["telemetry_included"] is False
        saved = json.loads(
            (root / "REVIEW/canary-listen-complete.json").read_text(encoding="utf-8")
        )
        assert validate_canary_listen_document(saved, run=run) == review
        with pytest.raises(HTTPError) as repeated:
            urlopen(request, timeout=5)
        assert repeated.value.code == 409
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_canary_review_server_rejects_public_binding(tmp_path: Path) -> None:
    root, _ = _evidence(tmp_path)
    with pytest.raises(ValueError, match="localhost"):
        build_canary_review_server(root, host="0.0.0.0", port=0)


def test_canary_review_server_does_not_persist_incomplete_review(
    tmp_path: Path,
) -> None:
    root, run = _evidence(tmp_path)
    server = build_canary_review_server(root, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    review = _complete_review(run)
    review["status"] = "incomplete"
    review["songs"][0]["complete"] = False
    review["missing_fields"] = ["vocal_forward listen"]
    request = Request(
        f"http://127.0.0.1:{server.server_port}/review",
        data=json.dumps(review).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with pytest.raises(HTTPError) as rejected:
            urlopen(request, timeout=5)
        assert rejected.value.code == 422
        assert not (root / "REVIEW/canary-listen-complete.json").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_complete_canary_listen_document_is_bound_and_valid(tmp_path: Path) -> None:
    _, run = _evidence(tmp_path)
    document = _complete_review(run)
    assert validate_canary_listen_document(document, run=run) == document

    document["songs"][0]["result"] = "catastrophic_defect_reported"
    with pytest.raises(ValueError, match="requires details"):
        validate_canary_listen_document(document, run=run)


def test_explicit_no_failure_statement_records_fresh_bound_review(
    tmp_path: Path,
) -> None:
    root, run = _evidence(tmp_path)
    output = root / "REVIEW/canary-listen-complete.json"

    receipt = record_no_failure_canary_listen(
        root,
        output,
        reviewed_by="Test Reviewer",
        explicit_statement="I reviewed all stems and found no failures.",
    )

    document = json.loads(output.read_text(encoding="utf-8"))
    assert validate_canary_listen_document(document, run=run) == document
    assert receipt["catastrophic_listens_complete"] is True
    assert set(receipt["results"].values()) == {"no_catastrophic_defect"}
    assert document["recording_method"] == (
        "explicit_user_statement_after_local_web_review"
    )
    assert document["browser_download_succeeded"] is False
    with pytest.raises(FileExistsError):
        record_no_failure_canary_listen(
            root,
            output,
            reviewed_by="Test Reviewer",
            explicit_statement="I reviewed all stems and found no failures.",
        )
