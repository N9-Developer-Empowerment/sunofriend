from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path
import threading
from typing import Any, Mapping
from urllib.parse import quote, urlparse

import numpy as np
import pytest
import soundfile

from sunofriend.musical_state import (
    VOCAL_COMP_TIMELINE_SCHEMA,
    create_vocal_musical_state,
)
from sunofriend.vocal_session import VOCAL_SESSION_SCHEMA
from sunofriend.vocal_session_server import create_vocal_session_server


class _VocalSessionHTTP:
    def __init__(self, root: Path, *, token: str | None = None) -> None:
        self.root = root
        self.state_root, self.musical_state = _create_musical_state(root)
        self.persistence_root = root / "vocal-session-state"
        self.server = create_vocal_session_server(
            self.state_root / "musical-state.json",
            state_dir=self.persistence_root,
            port=0,
            token=token,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def token(self) -> str:
        return self.server.token

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def request(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        request_headers = dict(headers or {})
        payload: bytes | None = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=5
        )
        try:
            connection.request(
                method,
                path,
                body=payload,
                headers=request_headers,
            )
            response = connection.getresponse()
            return (
                response.status,
                {key.casefold(): value for key, value in response.getheaders()},
                response.read(),
            )
        finally:
            connection.close()

    def json_request(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        status, response_headers, raw = self.request(
            method, path, body, headers=headers
        )
        return status, response_headers, json.loads(raw)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def vocal_http(tmp_path: Path) -> _VocalSessionHTTP:
    fixture = _VocalSessionHTTP(tmp_path)
    try:
        yield fixture
    finally:
        fixture.close()


def test_launch_is_loopback_only_uses_a_fresh_token_and_returns_path_free_state(
    tmp_path: Path,
) -> None:
    first = _VocalSessionHTTP(tmp_path / "first")
    second = _VocalSessionHTTP(tmp_path / "second")
    try:
        assert first.server.server_address[0] == "127.0.0.1"
        assert second.server.server_address[0] == "127.0.0.1"
        assert first.token != second.token
        assert len(first.token) >= 32
        assert len(second.token) >= 32

        status, _, payload = first.json_request("GET", "/api/session")
        assert status == 403
        assert "token" in payload["error"]

        status, _, payload = first.json_request(
            "GET", f"/api/session?token={first.token}", headers={"Host": "example.test"}
        )
        assert status == 403
        assert "loopback" in payload["error"]

        status, headers, browser_state = first.json_request(
            "GET", f"/api/session?token={first.token}"
        )
        assert status == 200
        session = browser_state["session"]
        assert browser_state["ai_fallback_available"] is False
        assert session["schema"] == VOCAL_SESSION_SCHEMA
        assert (
            session["binding"]["musical_state_sha256"]
            == first.musical_state["document_sha256"]
        )
        assert headers["cache-control"] == "no-store"
        assert headers["cross-origin-resource-policy"] == "same-origin"
        assert "default-src 'self'" in headers["content-security-policy"]
        assert not _keys_named_path(session)
        assert not _keys_named_path(browser_state)
        assert str(first.root) not in json.dumps(browser_state)
        assert first.token not in json.dumps(session)
    finally:
        first.close()
        second.close()


def test_mutation_requires_token_same_origin_and_an_explicit_decision(
    vocal_http: _VocalSessionHTTP,
) -> None:
    fixture = vocal_http
    request = {
        "phrase_id": "phrase-001",
        "outcome": "human_take",
        "source_id": "take-001",
        "notes": "Chosen after listening in phrase context.",
    }

    for path, headers in (
        ("/api/decision", {"Origin": fixture.origin}),
        (f"/api/decision?token={fixture.token}", {}),
        (
            f"/api/decision?token={fixture.token}",
            {"Origin": "https://attacker.example"},
        ),
        (f"/api/decision?token={fixture.token}", {"Origin": "null"}),
    ):
        status, _, payload = fixture.json_request(
            "POST", path, request, headers=headers
        )
        assert status == 403
        assert "token" in payload["error"] or "origin" in payload["error"].casefold()
    session_id = fixture.server.store.current_session(fixture.musical_state)[
        "session_id"
    ]
    assert fixture.server.store.events(session_id) == []

    status, _, payload = fixture.json_request(
        "POST",
        f"/api/decision?token={fixture.token}",
        {
            "event_type": "playback",
            "source_id": "take-001",
            "seconds": 180.0,
        },
        headers={"Origin": fixture.origin},
    )
    assert status == 400
    assert "phrase_id" in payload["error"] or "outcome" in payload["error"]
    assert fixture.server.store.events(session_id) == []

    status, _, payload = fixture.json_request(
        "POST",
        f"/api/decision?token={fixture.token}",
        request,
        headers={"Origin": fixture.origin},
    )
    assert status == 201
    assert payload["event"]["decision"]["outcome"] == "human_take"
    assert payload["event"]["decision"]["selected_source_id"] == "take-001"
    assert payload["state"]["session"]["coverage"]["decision_count"] == 1
    assert not _keys_named_path(payload)


def test_explicit_reopen_retains_history_and_allows_a_new_phrase_choice(
    vocal_http: _VocalSessionHTTP,
) -> None:
    fixture = vocal_http
    decision_request = {
        "phrase_id": "phrase-001",
        "outcome": "human_take",
        "source_id": "take-001",
        "notes": "First explicit choice.",
    }
    status, _, first = fixture.json_request(
        "POST",
        f"/api/decision?token={fixture.token}",
        decision_request,
        headers={"Origin": fixture.origin},
    )
    assert status == 201
    first_hash = first["event"]["decision_document_sha256"]

    status, _, reopened = fixture.json_request(
        "POST",
        f"/api/reopen?token={fixture.token}",
        {
            "phrase_id": "phrase-001",
            "expected_decision_document_sha256": first_hash,
            "reason": "change_source",
        },
        headers={"Origin": fixture.origin},
    )
    assert status == 201
    assert reopened["reopen"]["reopened_decision_document_sha256"] == first_hash
    assert reopened["reopen"]["authority"] == {
        "explicit_human_reopen": True,
        "prior_decision_deleted": False,
        "new_phrase_decision_created": False,
        "playback_or_draft_authority": "none",
    }
    assert reopened["state"]["session"]["phrases"][0]["decision"] is None
    assert reopened["state"]["session"]["coverage"]["decision_count"] == 0
    assert (
        len(fixture.server.store.events(reopened["state"]["session"]["session_id"]))
        == 1
    )
    assert (
        len(fixture.server.store.reopens(reopened["state"]["session"]["session_id"]))
        == 1
    )

    decision_request.update({"source_id": "take-002", "notes": "Revised choice."})
    status, _, second = fixture.json_request(
        "POST",
        f"/api/decision?token={fixture.token}",
        decision_request,
        headers={"Origin": fixture.origin},
    )
    assert status == 201
    assert (
        second["state"]["session"]["phrases"][0]["decision"]["selected_source_id"]
        == "take-002"
    )
    assert (
        len(fixture.server.store.events(second["state"]["session"]["session_id"])) == 2
    )


def test_draft_put_is_same_origin_non_authoritative_and_revision_checked(
    vocal_http: _VocalSessionHTTP,
) -> None:
    fixture = vocal_http
    request = {
        "expected_revision": 0,
        "draft": {
            "active_phrase_id": "phrase-002",
            "notes_by_phrase": {"phrase-002": "Try a stronger final word."},
        },
    }

    status, _, payload = fixture.json_request(
        "PUT",
        f"/api/draft?token={fixture.token}",
        request,
    )
    assert status == 403
    assert "origin" in payload["error"].casefold()

    status, _, payload = fixture.json_request(
        "PUT",
        f"/api/draft?token={fixture.token}",
        request,
        headers={"Origin": fixture.origin},
    )
    assert status == 200
    assert payload["draft"]["revision"] == 1
    assert payload["draft"]["authority"] == "none"
    assert not any(payload["draft"]["effects"].values())
    assert not _keys_named_path(payload)
    session = fixture.server.store.current_session(fixture.musical_state)
    assert session["coverage"]["decision_count"] == 0

    status, _, payload = fixture.json_request(
        "PUT",
        f"/api/draft?token={fixture.token}",
        request,
        headers={"Origin": fixture.origin},
    )
    assert status == 409
    assert "revision" in payload["error"]


def test_allowlisted_audio_supports_ranges_and_rejects_unknown_or_traversal_ids(
    vocal_http: _VocalSessionHTTP,
) -> None:
    fixture = vocal_http
    source = fixture.state_root / "SOURCES" / "takes" / "take-001.wav"
    expected = source.read_bytes()
    browser_state = fixture.server.browser_state()
    source_projection = next(
        row for row in browser_state["sources"] if row["source_id"] == "take-001"
    )
    route = source_projection["media_url"]
    capability = urlparse(route).path.removeprefix("/media/")
    assert capability
    assert capability != "take-001"
    assert "take-001" not in capability
    assert str(fixture.state_root) not in json.dumps(browser_state)

    status, headers, body = fixture.request("GET", route)
    assert status == 200
    assert body == expected
    assert headers["accept-ranges"] == "bytes"
    assert headers["cache-control"] == "no-store"

    status, headers, body = fixture.request(
        "GET", route, headers={"Range": "bytes=4-15"}
    )
    assert status == 206
    assert body == expected[4:16]
    assert headers["content-range"] == f"bytes 4-15/{len(expected)}"

    for source_id in ("not-admitted", quote("../SOURCES/takes/take-001.wav", safe="")):
        status, _, payload = fixture.json_request(
            "GET", f"/media/{source_id}?token={fixture.token}"
        )
        assert status in {400, 404}
        assert str(fixture.state_root) not in json.dumps(payload)

    status, headers, body = fixture.request(
        "GET", route, headers={"Range": "bytes=0-1,4-5"}
    )
    assert status == 416
    assert body
    assert headers["content-range"] == f"bytes */{len(expected)}"


@pytest.mark.parametrize("tamper", ("same-size", "changed-size"))
def test_audio_is_hash_and_size_verified_against_the_admitted_state(
    vocal_http: _VocalSessionHTTP,
    tamper: str,
) -> None:
    fixture = vocal_http
    source = fixture.state_root / "SOURCES" / "takes" / "take-001.wav"
    route = next(
        row["media_url"]
        for row in fixture.server.browser_state()["sources"]
        if row["source_id"] == "take-001"
    )
    original = source.read_bytes()
    if tamper == "same-size":
        changed = bytearray(original)
        changed[-1] ^= 0x01
        source.write_bytes(changed)
    else:
        source.write_bytes(original + b"changed-size")

    status, _, payload = fixture.json_request("GET", route)

    assert status == 409
    assert "audio" in payload["error"].casefold()
    assert "changed" in payload["error"].casefold()
    assert str(source) not in json.dumps(payload)


def test_playback_gets_are_zero_write_and_decisions_persist_owner_only(
    vocal_http: _VocalSessionHTTP,
) -> None:
    fixture = vocal_http
    media_by_source = {
        row["source_id"]: row["media_url"]
        for row in fixture.server.browser_state()["sources"]
    }
    before = _tree_snapshot(fixture.persistence_root)
    for route, headers in (
        (f"/api/session?token={fixture.token}", {}),
        (media_by_source["reference-vocal-001"], {}),
        (media_by_source["take-001"], {"Range": "bytes=0-31"}),
        (media_by_source["take-002"], {"Range": "bytes=-32"}),
    ):
        status, _, _ = fixture.request("GET", route, headers=headers)
        assert status in {200, 206}
    assert _tree_snapshot(fixture.persistence_root) == before

    status, _, _ = fixture.request(
        "POST",
        f"/api/decision?token={fixture.token}",
        {"phrase_id": "phrase-001", "outcome": "ai_fallback"},
        headers={"Origin": fixture.origin},
    )
    assert status == 201
    assert os.stat(fixture.persistence_root).st_mode & 0o777 == 0o700
    for path in fixture.persistence_root.rglob("*"):
        if path.is_dir():
            assert os.stat(path).st_mode & 0o777 == 0o700
        elif path.is_file():
            assert os.stat(path).st_mode & 0o777 == 0o600


def _create_musical_state(root: Path) -> tuple[Path, dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    takes = root / "takes"
    takes.mkdir()
    sample_rate = 8_000
    seconds = 1.25
    time = np.arange(round(sample_rate * seconds), dtype=np.float64) / sample_rate
    for index, frequency in enumerate((196.0, 220.0), 1):
        audio = (0.15 * np.sin(2.0 * np.pi * frequency * time)).astype(np.float32)
        soundfile.write(
            takes / f"attempt-{index:02d}.wav",
            audio,
            sample_rate,
            subtype="PCM_24",
        )
    reference = root / "reference.wav"
    soundfile.write(
        reference,
        (0.1 * np.sin(2.0 * np.pi * 233.08 * time)).astype(np.float32),
        sample_rate,
        subtype="PCM_24",
    )
    lyrics = root / "lyrics.txt"
    lyrics.write_text("One phrase\nSecond phrase\n", encoding="utf-8")
    timeline = root / "timeline.json"
    timeline.write_text(
        json.dumps(
            {
                "schema": VOCAL_COMP_TIMELINE_SCHEMA,
                "status": "reviewed",
                "phrases": [
                    {
                        "phrase_id": "phrase-001",
                        "start_seconds": 0.10,
                        "end_seconds": 0.55,
                        "lyrics": "One phrase",
                    },
                    {
                        "phrase_id": "phrase-002",
                        "start_seconds": 0.65,
                        "end_seconds": 1.10,
                        "lyrics": "Second phrase",
                    },
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    state_root = root / "musical-state"
    state = create_vocal_musical_state(
        takes,
        out_dir=state_root,
        lyrics=lyrics,
        phrase_timeline=timeline,
        reference_vocal=reference,
        rights_category="owned",
        processing_chain="dry",
        bpm=96.0,
        confirm_common_recorded_zero=True,
        confirm_timeline_reviewed=True,
    )
    return state_root, state


def _tree_snapshot(root: Path) -> dict[str, tuple[int, int, int, str]]:
    result = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        payload = path.read_bytes()
        result[path.relative_to(root).as_posix()] = (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            path.stat().st_mode & 0o777,
            hashlib.sha256(payload).hexdigest(),
        )
    return result


def _keys_named_path(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            "path" in str(key).casefold() or _keys_named_path(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_keys_named_path(item) for item in value)
    return False
