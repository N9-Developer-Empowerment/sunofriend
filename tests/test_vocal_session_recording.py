from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import http.client
from io import BytesIO
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Mapping

import numpy as np
import pytest
import soundfile

from sunofriend.musical_state import (
    VOCAL_COMP_TIMELINE_SCHEMA,
    VOCAL_PERFORMANCE_STATE_SCHEMA_V3,
    create_vocal_musical_state,
    validate_musical_state,
)
from sunofriend.source_receipt import document_sha256
from sunofriend.vocal_session_server import create_vocal_session_server
from sunofriend.vocal_working_audition import validate_vocal_working_audition


SAMPLE_RATE = 8_000
PRE_GUARD_SECONDS = 0.5
POST_GUARD_SECONDS = 0.5
MAX_CAPTURE_JSON_BYTES = 10 * 1024 * 1024


class _RecordingHTTP:
    def __init__(
        self,
        root: Path,
        *,
        candidate_vault: bool = False,
        context_audio: bool = False,
    ) -> None:
        self.root = root
        self.state_root, self.musical_state = _create_musical_state(root)
        self.persistence_root = root / "session-state"
        self.capture_output_dir = root / "capture-states"
        self.candidate_vault_dir = root / "candidate-vault"
        original_mix, backing = (
            _create_context_audio(root) if context_audio else (None, None)
        )
        self.server = create_vocal_session_server(
            self.state_root / "musical-state.json",
            state_dir=self.persistence_root,
            recording_cue_source_id="reference-vocal-001",
            capture_output_dir=(None if candidate_vault else self.capture_output_dir),
            candidate_vault_dir=(self.candidate_vault_dir if candidate_vault else None),
            original_mix_audio=original_mix,
            backing_audio=backing,
            port=0,
            token="recording-test-token",
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
        body: Mapping[str, Any] | bytes | None = None,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        request_headers = dict(headers or {})
        payload = body
        if isinstance(body, Mapping):
            payload = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=10
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
        body: Mapping[str, Any] | bytes | None = None,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        status, response_headers, raw = self.request(
            method, path, body, headers=headers
        )
        return status, response_headers, json.loads(raw)

    def browser_state(self) -> dict[str, Any]:
        status, _, state = self.json_request("GET", f"/api/session?token={self.token}")
        assert status == 200
        return state

    def capture_request(
        self, *, phrase_id: str = "phrase-001", include_transition: bool = False
    ) -> dict[str, Any]:
        state = self.browser_state()
        plan = next(
            row
            for row in state["recording"]["phrases"]
            if row["phrase_id"] == phrase_id
        )
        wav = _capture_wav(
            sample_rate=SAMPLE_RATE,
            frame_count=plan["placement"]["expected_capture_frames"],
        )
        request = {
            "expected_musical_state_sha256": state["session"]["binding"][
                "musical_state_sha256"
            ],
            "phrase_id": phrase_id,
            "capture_id": "attempt-001",
            "cue_id": plan["cue"]["cue_id"],
            "cue_asset_sha256": plan["cue"]["audio_sha256"],
            "audio_wav_base64": base64.b64encode(wav).decode("ascii"),
            "placement": {
                key: plan["placement"][key]
                for key in (
                    "source_phrase_start_frame",
                    "source_phrase_end_frame",
                    "pre_guard_frames",
                    "post_guard_frames",
                    "destination_start_seconds",
                    "destination_end_seconds",
                )
            },
            "actual_processing": {
                "echo_cancellation": False,
                "noise_suppression": False,
                "automatic_gain_control": False,
                "sample_rate": SAMPLE_RATE,
                "channel_count": 1,
            },
        }
        if include_transition:
            request["transition"] = plan["transition"]
        return request

    def save_capture(
        self, request: Mapping[str, Any]
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        return self.json_request(
            "POST",
            f"/api/capture?token={self.token}",
            request,
            headers={"Origin": self.origin},
        )

    def keep_candidate(
        self, request: Mapping[str, Any]
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        return self.json_request(
            "POST",
            f"/api/candidate?token={self.token}",
            request,
            headers={"Origin": self.origin},
        )

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def recording_http(tmp_path: Path) -> _RecordingHTTP:
    fixture = _RecordingHTTP(tmp_path)
    try:
        yield fixture
    finally:
        fixture.close()


@pytest.fixture
def candidate_vault_http(tmp_path: Path) -> _RecordingHTTP:
    fixture = _RecordingHTTP(tmp_path, candidate_vault=True)
    try:
        yield fixture
    finally:
        fixture.close()


def test_verified_reference_cue_is_bound_to_each_reviewed_phrase_and_headphones(
    recording_http: _RecordingHTTP,
) -> None:
    fixture = recording_http
    state = fixture.browser_state()
    recording = state["recording"]

    assert recording["available"] is True
    assert recording["headphones_required"] is True
    assert "headphone" in recording["headphones_message"].casefold()
    assert recording["requested_processing"] == {
        "echo_cancellation": False,
        "noise_suppression": False,
        "automatic_gain_control": False,
    }
    assert recording["encoding"] == {
        "format": "WAV",
        "subtype": "PCM_24",
        "channels": 1,
        "description": "deterministic_pcm24_projection_of_webaudio_float32",
    }
    assert recording["placement_authority"] == (
        "intended_cue_clock_only_not_verified_microphone_latency"
    )
    assert recording["automatic_timing_correction"] is False
    assert recording["save_url"] == "/api/capture"
    assert recording["max_json_bytes"] == MAX_CAPTURE_JSON_BYTES
    assert [row["phrase_id"] for row in recording["phrases"]] == [
        "phrase-001",
        "phrase-002",
    ]
    for plan, phrase in zip(recording["phrases"], state["session"]["phrases"]):
        assert plan["cue"]["source_id"] == "reference-vocal-001"
        assert (
            plan["cue"]["audio_sha256"]
            == fixture.musical_state["vocal_performance_state"]["reference"]["audio"][
                "sha256"
            ]
        )
        assert plan["cue"]["media_url"].startswith("/media/")
        assert fixture.token not in plan["cue"]["media_url"]
        assert plan["cue"]["playback_start_seconds"] == pytest.approx(
            phrase["start_seconds"] - PRE_GUARD_SECONDS
        )
        assert plan["cue"]["playback_end_seconds"] == pytest.approx(
            phrase["end_seconds"] + POST_GUARD_SECONDS
        )
        assert plan["placement"]["destination_start_seconds"] == phrase["start_seconds"]
        assert plan["placement"]["destination_end_seconds"] == phrase["end_seconds"]
        assert plan["placement"]["pre_guard_frames"] == round(
            PRE_GUARD_SECONDS * SAMPLE_RATE
        )
        assert plan["placement"]["post_guard_frames"] == round(
            POST_GUARD_SECONDS * SAMPLE_RATE
        )

    cue_url = recording["phrases"][0]["cue"]["media_url"]
    status, headers, body = fixture.request(
        "GET", cue_url, headers={"Range": "bytes=0-31"}
    )
    assert status == 206
    assert len(body) == 32
    assert headers["cache-control"] == "no-store"
    assert (
        "microphone=(self)"
        in fixture.request("GET", f"/?token={fixture.token}")[1]["permissions-policy"]
    )
    assert not _keys_named_path(state)
    assert str(fixture.root) not in json.dumps(state)


def test_candidate_vault_keeps_attempt_without_growing_the_musical_state(
    candidate_vault_http: _RecordingHTTP,
) -> None:
    fixture = candidate_vault_http
    initial_state_sha256 = fixture.server.musical_state["document_sha256"]
    initial_tree = _tree_snapshot(fixture.state_root)
    browser = fixture.browser_state()
    assert browser["recording"]["save_url"] == "/api/candidate"
    assert browser["candidate_vault"] == {
        "available": True,
        "entries": [],
        "working_choices": None,
        "keep_url": "/api/candidate",
        "working_choices_url": "/api/working-choices",
        "working_audition_url": "/api/working-audition",
        "authority": "none",
    }

    status, _, payload = fixture.keep_candidate(fixture.capture_request())

    assert status == 201
    assert payload["candidate"]["status"] == "kept_unreviewed_candidate"
    assert payload["candidate"]["phrase"]["phrase_id"] == "phrase-001"
    assert payload["candidate"]["authority"] == {
        "source_evidence_only": True,
        "working_choice_authority": "none",
        "phrase_decision_created": False,
        "render_authorized": False,
        "training_label_created": False,
    }
    state = payload["state"]
    assert state["session"]["binding"]["musical_state_sha256"] == (initial_state_sha256)
    assert state["session"]["coverage"]["decision_count"] == 0
    assert len(state["candidate_vault"]["entries"]) == 1
    projected = state["candidate_vault"]["entries"][0]
    assert projected["source_class"] == "unreviewed_vocal_candidate"
    assert projected["bound_phrase_id"] == "phrase-001"
    assert projected["media_url"].startswith("/media/")
    assert fixture.request("GET", projected["media_url"])[0] == 200
    assert fixture.server.musical_state["document_sha256"] == initial_state_sha256
    assert _tree_snapshot(fixture.state_root) == initial_tree
    assert not fixture.capture_output_dir.exists()
    assert not _keys_named_path(payload)
    assert str(fixture.root) not in json.dumps(payload)


def test_working_choice_is_reversible_zero_authority_and_not_a_phrase_decision(
    candidate_vault_http: _RecordingHTTP,
) -> None:
    fixture = candidate_vault_http
    status, _, kept = fixture.keep_candidate(fixture.capture_request())
    assert status == 201
    source_id = kept["candidate"]["source_id"]

    status, _, saved = fixture.json_request(
        "PUT",
        f"/api/working-choices?token={fixture.token}",
        {
            "expected_revision": 0,
            "working_source_by_phrase": {"phrase-001": source_id},
        },
        headers={"Origin": fixture.origin},
    )

    assert status == 200
    assert saved["working_choices"]["revision"] == 1
    assert saved["working_choices"]["choices"] == {
        "phrase-001": {
            "source_id": source_id,
            "source_class": "unreviewed_vocal_candidate",
            "source_audio_sha256": kept["candidate"]["audio"]["sha256"],
        }
    }
    assert saved["working_choices"]["authority"] == "none"
    assert not any(saved["working_choices"]["effects"].values())
    browser = fixture.browser_state()
    assert browser["candidate_vault"]["working_choices"] == saved["working_choices"]
    assert browser["session"]["coverage"]["decision_count"] == 0
    assert all(row["decision"] is None for row in browser["session"]["phrases"])

    status, _, cleared = fixture.json_request(
        "PUT",
        f"/api/working-choices?token={fixture.token}",
        {"expected_revision": 1, "working_source_by_phrase": {}},
        headers={"Origin": fixture.origin},
    )
    assert status == 200
    assert cleared["working_choices"]["revision"] == 2
    assert cleared["working_choices"]["choices"] == {}
    assert fixture.browser_state()["session"]["coverage"]["decision_count"] == 0


def test_working_audition_uses_candidate_then_reference_without_rendering(
    candidate_vault_http: _RecordingHTTP,
) -> None:
    fixture = candidate_vault_http
    status, _, kept = fixture.keep_candidate(fixture.capture_request())
    assert status == 201
    source_id = kept["candidate"]["source_id"]
    status, _, _ = fixture.json_request(
        "PUT",
        f"/api/working-choices?token={fixture.token}",
        {
            "expected_revision": 0,
            "working_source_by_phrase": {"phrase-001": source_id},
        },
        headers={"Origin": fixture.origin},
    )
    assert status == 200

    status, _, plan = fixture.json_request(
        "GET",
        f"/api/working-audition?token={fixture.token}"
        "&scope=song&phrase_id=phrase-001",
    )

    assert status == 200
    assert plan["schema"] == "sunofriend.vocal-working-audition.v2"
    assert plan["status"] == "planned_browser_audition_only"
    assert plan["scope"] == "song"
    assert plan["window"] == {"start_seconds": 0.0, "end_seconds": 2.5}
    assert plan["original_comparison"]["source_class"] == (
        "authorised_ai_vocal_reference"
    )
    assert plan["original_comparison"]["comparison_kind"] == (
        "reference_vocal_only"
    )
    assert plan["working_mix"]["backing"] is None
    vocal_segments = plan["working_mix"]["vocal_segments"]
    assert [row["segment_kind"] for row in vocal_segments] == [
        "reference_context",
        "phrase",
        "reference_context",
        "phrase",
        "reference_context",
    ]
    assert [row["phrase_id"] for row in vocal_segments] == [
        None,
        "phrase-001",
        None,
        "phrase-002",
        None,
    ]
    lead_in, candidate, between, fallback, tail = vocal_segments
    assert lead_in["selection"] == "reference_context_preserved"
    assert lead_in["source_start_seconds"] == pytest.approx(0.0)
    assert lead_in["source_end_seconds"] == pytest.approx(0.6)
    assert between["selection"] == "reference_context_preserved"
    assert between["source_start_seconds"] == pytest.approx(1.1)
    assert between["source_end_seconds"] == pytest.approx(1.2)
    assert tail["selection"] == "reference_context_preserved"
    assert tail["source_start_seconds"] == pytest.approx(1.7)
    assert tail["source_end_seconds"] == pytest.approx(2.5)
    assert candidate["source_id"] == source_id
    assert candidate["source_class"] == "unreviewed_vocal_candidate"
    assert candidate["selection"] == "reversible_working_choice"
    assert candidate["source_start_seconds"] == pytest.approx(PRE_GUARD_SECONDS)
    assert candidate["destination_start_seconds"] == pytest.approx(0.6)
    assert fallback["source_id"] == "reference-vocal-001"
    assert fallback["selection"] == "original_reference_fallback"
    assert fallback["source_start_seconds"] == pytest.approx(1.2)
    assert fallback["destination_start_seconds"] == pytest.approx(1.2)
    assert plan["join"] == {
        "policy": "browser_scheduled_phrase_boundaries",
        "edge_fade_seconds": 0.005,
        "rendered_artifact": False,
        "join_reviewed": False,
    }
    assert plan["authority"] == "none"
    assert not any(plan["effects"].values())
    assert plan["network_used"] is False
    assert fixture.server.store.current_session(fixture.musical_state)["coverage"][
        "decision_count"
    ] == 0


def test_working_audition_separates_full_mix_backing_and_continuous_vocal(
    tmp_path: Path,
) -> None:
    fixture = _RecordingHTTP(tmp_path, candidate_vault=True, context_audio=True)
    try:
        status, _, kept = fixture.keep_candidate(fixture.capture_request())
        assert status == 201
        source_id = kept["candidate"]["source_id"]
        status, _, _ = fixture.json_request(
            "PUT",
            f"/api/working-choices?token={fixture.token}",
            {
                "expected_revision": 0,
                "working_source_by_phrase": {"phrase-001": source_id},
            },
            headers={"Origin": fixture.origin},
        )
        assert status == 200

        state = fixture.browser_state()
        context = state["context_playback"]
        assert context["original"]["source_class"] == "authorised_original_mix"
        assert context["working"]["backing_available"] is True
        assert context["working"]["reference_context_preserved"] is True
        assert fixture.request("GET", context["original"]["media_url"])[0] == 200
        assert fixture.request("GET", context["working"]["backing_media_url"])[0] == 200
        assert not _keys_named_path(state)
        assert str(tmp_path) not in json.dumps(state)

        status, _, plan = fixture.json_request(
            "GET",
            f"/api/working-audition?token={fixture.token}"
            "&scope=song&phrase_id=phrase-001",
        )
        assert status == 200
        assert plan["original_comparison"]["source_class"] == (
            "authorised_original_mix"
        )
        assert plan["original_comparison"]["comparison_kind"] == "full_mix"
        assert plan["working_mix"]["backing"]["source_class"] == (
            "authorised_instrumental_backing"
        )
        assert [
            row["selection"] for row in plan["working_mix"]["vocal_segments"]
        ] == [
            "reference_context_preserved",
            "reversible_working_choice",
            "reference_context_preserved",
            "original_reference_fallback",
            "reference_context_preserved",
        ]
        assert plan["effects"]["audio_rendered"] is False
        assert plan["authority"] == "none"
    finally:
        fixture.close()


def test_working_audition_rejects_unknown_scope_without_side_effects(
    candidate_vault_http: _RecordingHTTP,
) -> None:
    fixture = candidate_vault_http
    before = _tree_snapshot(fixture.candidate_vault_dir)

    status, _, payload = fixture.json_request(
        "GET",
        f"/api/working-audition?token={fixture.token}"
        "&scope=album&phrase_id=phrase-001",
    )

    assert status == 400
    assert payload == {"error": "working audition scope is not supported"}
    assert _tree_snapshot(fixture.candidate_vault_dir) == before


def test_working_audition_rejects_a_reference_gap_relabelled_as_a_choice(
    candidate_vault_http: _RecordingHTTP,
) -> None:
    plan = candidate_vault_http.server.working_audition_plan(
        active_phrase_id="phrase-001", scope="song"
    )
    changed = deepcopy(plan)
    changed["working_mix"]["vocal_segments"][0]["selection"] = (
        "reversible_working_choice"
    )
    changed["document_sha256"] = document_sha256(
        {key: value for key, value in changed.items() if key != "document_sha256"}
    )

    with pytest.raises(ValueError, match="selection|reference context"):
        validate_vocal_working_audition(changed)


def test_candidate_keep_and_working_choice_reject_duplicate_stale_or_wrong_binding(
    candidate_vault_http: _RecordingHTTP,
) -> None:
    fixture = candidate_vault_http
    request = fixture.capture_request()
    status, _, kept = fixture.keep_candidate(request)
    assert status == 201
    source_id = kept["candidate"]["source_id"]

    status, _, duplicate = fixture.keep_candidate(request)
    assert status == 409
    assert "already kept" in duplicate["error"]

    status, _, _ = fixture.json_request(
        "PUT",
        f"/api/working-choices?token={fixture.token}",
        {
            "expected_revision": 0,
            "working_source_by_phrase": {"phrase-001": source_id},
        },
        headers={"Origin": fixture.origin},
    )
    assert status == 200

    status, _, stale = fixture.json_request(
        "PUT",
        f"/api/working-choices?token={fixture.token}",
        {
            "expected_revision": 0,
            "working_source_by_phrase": {"phrase-001": source_id},
        },
        headers={"Origin": fixture.origin},
    )
    assert status == 409
    assert "revision conflict" in stale["error"]

    status, _, wrong_phrase = fixture.json_request(
        "PUT",
        f"/api/working-choices?token={fixture.token}",
        {
            "expected_revision": 1,
            "working_source_by_phrase": {"phrase-002": source_id},
        },
        headers={"Origin": fixture.origin},
    )
    assert status == 400
    assert "bound elsewhere" in wrong_phrase["error"]


@pytest.mark.parametrize("artifact", ("entry", "audio", "working_choices"))
def test_candidate_vault_revalidates_retained_evidence_before_projection(
    candidate_vault_http: _RecordingHTTP,
    artifact: str,
) -> None:
    fixture = candidate_vault_http
    status, _, kept = fixture.keep_candidate(fixture.capture_request())
    assert status == 201
    source_id = kept["candidate"]["source_id"]
    entry_dir = fixture.candidate_vault_dir / "entries" / kept["candidate"]["entry_id"]

    if artifact == "entry":
        path = entry_dir / "entry.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["phrase"]["lyrics"] = "changed projection"
        document.pop("document_sha256")
        document["document_sha256"] = document_sha256(document)
        path.write_text(json.dumps(document), encoding="utf-8")
        expected = "projection changed"
    elif artifact == "audio":
        path = entry_dir / "capture.wav"
        payload = bytearray(path.read_bytes())
        payload[-1] ^= 1
        path.write_bytes(payload)
        expected = "SHA-256 changed"
    else:
        saved = fixture.server.candidate_vault.save_working_choices(
            fixture.server.musical_state,
            {"phrase-001": source_id},
            expected_revision=0,
        )
        path = fixture.candidate_vault_dir / "working-choices.json"
        saved["choices"]["phrase-001"]["source_audio_sha256"] = "0" * 64
        saved.pop("document_sha256")
        saved["document_sha256"] = document_sha256(saved)
        path.write_text(json.dumps(saved), encoding="utf-8")
        expected = "projection changed"

    with pytest.raises(ValueError, match=expected):
        if artifact == "working_choices":
            fixture.server.candidate_vault.load_working_choices(
                fixture.server.musical_state
            )
        else:
            fixture.server.candidate_vault.entries(fixture.server.musical_state)


def test_recording_opt_in_requires_the_verified_reference_and_capture_output(
    tmp_path: Path,
) -> None:
    state_root, _ = _create_musical_state(tmp_path)
    manifest = state_root / "musical-state.json"
    with pytest.raises(ValueError, match="cue.*capture|supplied together"):
        create_vocal_session_server(
            manifest,
            state_dir=tmp_path / "state-a",
            recording_cue_source_id="reference-vocal-001",
        )
    with pytest.raises(ValueError, match="reference|authorised.*AI|cue"):
        create_vocal_session_server(
            manifest,
            state_dir=tmp_path / "state-b",
            recording_cue_source_id="take-001",
            capture_output_dir=tmp_path / "captures-b",
        )

    disabled = create_vocal_session_server(
        manifest,
        state_dir=tmp_path / "state-c",
    )
    try:
        assert disabled.browser_state()["recording"]["available"] is False
    finally:
        disabled.server_close()


def test_capture_save_requires_token_origin_and_is_never_created_by_playback(
    recording_http: _RecordingHTTP,
) -> None:
    fixture = recording_http
    request = fixture.capture_request()
    before_state = _tree_snapshot(fixture.persistence_root)
    before_parent = _tree_snapshot(fixture.state_root)
    cue_url = fixture.browser_state()["recording"]["phrases"][0]["cue"]["media_url"]

    for _ in range(2):
        status, _, _ = fixture.request("GET", cue_url)
        assert status == 200
    assert _tree_snapshot(fixture.persistence_root) == before_state
    assert _tree_snapshot(fixture.state_root) == before_parent
    assert not fixture.capture_output_dir.exists()

    for path, headers in (
        ("/api/capture", {"Origin": fixture.origin}),
        (f"/api/capture?token={fixture.token}", {}),
        (
            f"/api/capture?token={fixture.token}",
            {"Origin": "https://attacker.example"},
        ),
    ):
        status, _, payload = fixture.json_request(
            "POST", path, request, headers=headers
        )
        assert status == 403
        assert "token" in payload["error"] or "origin" in payload["error"].casefold()
    assert not fixture.capture_output_dir.exists()


def test_explicit_save_admits_fresh_v3_and_returns_path_free_unselected_session(
    recording_http: _RecordingHTTP,
) -> None:
    fixture = recording_http
    request = fixture.capture_request()
    parent_before = _tree_snapshot(fixture.state_root)
    parent_sha256 = fixture.musical_state["document_sha256"]

    status, _, payload = fixture.save_capture(request)

    assert status == 201
    assert payload["admission"]["parent_musical_state_sha256"] == parent_sha256
    assert payload["admission"]["phrase_id"] == "phrase-001"
    assert payload["admission"]["source_id"] == "browser-capture-attempt-001"
    assert payload["admission"]["musical_state_sha256"] != parent_sha256
    state = payload["state"]
    assert (
        state["session"]["binding"]["musical_state_sha256"]
        == payload["admission"]["musical_state_sha256"]
    )
    projected = next(
        row
        for row in state["sources"]
        if row["source_id"] == "browser-capture-attempt-001"
    )
    assert projected["source_class"] == "human_vocal_phrase_capture"
    assert projected["bound_phrase_id"] == "phrase-001"
    assert projected["playback_start_seconds"] == pytest.approx(PRE_GUARD_SECONDS)
    assert projected["playback_end_seconds"] == pytest.approx(1.0)
    assert state["session"]["coverage"]["decision_count"] == 0
    assert all(row["decision"] is None for row in state["session"]["phrases"])
    assert not any(state["session"]["effects"].values())
    assert not _keys_named_path(payload)
    assert str(fixture.root) not in json.dumps(payload)
    assert _tree_snapshot(fixture.state_root) == parent_before

    children = [path for path in fixture.capture_output_dir.iterdir() if path.is_dir()]
    assert len(children) == 1
    child = children[0]
    derived = validate_musical_state(child / "musical-state.json", root=child)
    assert derived["vocal_performance_state"]["schema"] == (
        VOCAL_PERFORMANCE_STATE_SCHEMA_V3
    )
    assert derived["lineage"]["parent"]["document_sha256"] == parent_sha256
    assert derived["training"]["explicit_labels"] == []
    assert derived["training"]["training_eligible"] is False
    assert not any(derived["effects"].values())
    assert derived["vocal_performance_state"]["explicit_phrase_decisions"] == []
    assert derived["vocal_performance_state"]["edit_maps"] == []
    assert derived["vocal_performance_state"]["correction_derivatives"] == []
    for root in (fixture.persistence_root, fixture.capture_output_dir, child):
        assert os.stat(root).st_mode & 0o777 == 0o700
    for path in child.rglob("*"):
        expected = 0o700 if path.is_dir() else 0o600
        assert os.stat(path).st_mode & 0o777 == expected

    saved_tree = _tree_snapshot(fixture.capture_output_dir)
    status, _, payload = fixture.save_capture(request)
    assert status in {400, 409}
    assert any(
        reason in payload["error"]
        for reason in ("identity changed", "exists", "source_id")
    )
    assert _tree_snapshot(fixture.capture_output_dir) == saved_tree


def test_three_consecutive_capture_saves_preserve_complete_lineage(
    recording_http: _RecordingHTTP,
) -> None:
    fixture = recording_http
    admitted_state_hashes = []
    expected_lineage_hashes = {fixture.musical_state["document_sha256"]}
    parent_sha256 = fixture.musical_state["document_sha256"]

    for index in range(1, 4):
        request = fixture.capture_request()
        request["capture_id"] = f"attempt-{index:03d}"

        status, _, payload = fixture.save_capture(request)

        assert status == 201, payload
        assert payload["admission"]["parent_musical_state_sha256"] == parent_sha256
        admitted_state_hashes.append(payload["admission"]["musical_state_sha256"])
        assert len(payload["state"]["sources"]) == 3 + index
        assert (
            payload["state"]["session"]["binding"]["musical_state_sha256"]
            == admitted_state_hashes[-1]
        )
        assert not any(payload["state"]["session"]["effects"].values())
        if index < 3:
            expected_lineage_hashes.add(admitted_state_hashes[-1])
        parent_sha256 = admitted_state_hashes[-1]

    assert len(set(admitted_state_hashes)) == 3
    assert (
        len(fixture.server.musical_state["vocal_performance_state"]["phrase_captures"])
        == 3
    )
    assert (
        validate_musical_state(
            fixture.server.musical_state_path,
            root=fixture.server.musical_state_root,
        )
        == fixture.server.musical_state
    )
    lineage_files = {
        path.name for path in (fixture.server.musical_state_root / "LINEAGE").iterdir()
    }
    assert lineage_files == {
        f"musical-state-{sha256}.json" for sha256 in expected_lineage_hashes
    }


def test_capture_save_fails_closed_when_explicit_decision_already_exists(
    recording_http: _RecordingHTTP,
) -> None:
    fixture = recording_http
    request = fixture.capture_request()
    status, _, _ = fixture.json_request(
        "POST",
        f"/api/decision?token={fixture.token}",
        {"phrase_id": "phrase-001", "outcome": "record_again"},
        headers={"Origin": fixture.origin},
    )
    assert status == 201
    original_events = fixture.server.store.events(
        fixture.server.store.current_session(fixture.musical_state)["session_id"]
    )

    status, _, payload = fixture.save_capture(request)

    assert status in {400, 409}
    assert "decision" in payload["error"].casefold()
    assert (
        fixture.server.store.events(
            fixture.server.store.current_session(fixture.musical_state)["session_id"]
        )
        == original_events
    )
    assert not fixture.capture_output_dir.exists()
    assert (
        fixture.server.musical_state["document_sha256"]
        == fixture.musical_state["document_sha256"]
    )


def test_explicit_transition_revalidates_only_unchanged_decisions(
    recording_http: _RecordingHTTP,
) -> None:
    fixture = recording_http
    status, _, decision_payload = fixture.json_request(
        "POST",
        f"/api/decision?token={fixture.token}",
        {
            "phrase_id": "phrase-001",
            "outcome": "human_take",
            "source_id": "take-001",
            "notes": "Keep this exact take choice if its identity is unchanged.",
        },
        headers={"Origin": fixture.origin},
    )
    assert status == 201
    parent_session = decision_payload["state"]["session"]
    parent_decision = parent_session["phrases"][0]["decision"]
    parent_events = fixture.server.store.events(parent_session["session_id"])

    browser_state = fixture.browser_state()
    assert browser_state["recording"]["available"] is True
    assert browser_state["recording"]["transition_required"] is True
    request = fixture.capture_request(phrase_id="phrase-002", include_transition=True)
    transition_request = request["transition"]
    assert transition_request["expected_decisions"] == [
        {"phrase_id": "phrase-001", **parent_decision}
    ]

    status, _, payload = fixture.save_capture(request)

    assert status == 201
    transition = payload["transition"]
    assert transition["status"] == "complete_explicit_transition"
    assert transition["request"] == {
        "schema": transition_request["schema"],
        "canonical_sha256": document_sha256(transition_request),
    }
    assert transition["reopened_phrase"]["phrase_id"] == "phrase-002"
    assert transition["reopened_phrase"]["selection_authority"] == "none"
    assert transition["authority"] == {
        "explicit_transition_confirmed": True,
        "silent_decision_migration_permitted": False,
        "target_phrase_reopened": True,
        "unchanged_decisions_revalidated": True,
        "playback_or_draft_authority": "none",
    }
    assert transition["training"] == {
        "pairwise_labels": [],
        "inferred_labels": [],
        "training_eligible": False,
    }
    assert transition["effects"] == {
        "capture_admitted": True,
        "target_phrase_reopened": True,
        "unchanged_decisions_revalidated": True,
        "audio_comp_rendered": False,
        "join_created": False,
        "pitch_correction_applied": False,
        "timing_correction_applied": False,
        "training_label_created": False,
    }
    lineage = transition["decision_lineage"]
    assert len(lineage) == 1
    assert (
        lineage[0]["parent_decision_document_sha256"]
        == parent_decision["decision_document_sha256"]
    )
    assert lineage[0]["disposition"] == "explicitly_revalidated"
    assert lineage[0]["selected_source_id"] == "take-001"
    assert (
        lineage[0]["selected_source_sha256"]
        == parent_decision["selected_source_sha256"]
    )
    assert (
        lineage[0]["child_decision_document_sha256"]
        != parent_decision["decision_document_sha256"]
    )
    child_session = payload["state"]["session"]
    assert child_session["coverage"]["decision_count"] == 1
    assert child_session["phrases"][0]["decision"] == {
        **parent_decision,
        "decision_document_sha256": lineage[0]["child_decision_document_sha256"],
    }
    assert child_session["phrases"][1]["decision"] is None
    assert fixture.server.store.events(parent_session["session_id"]) == parent_events
    assert fixture.server.store.transitions() == [transition]
    database = fixture.persistence_root / "vocal-session.sqlite3"
    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM vocal_session_transitions")


def test_explicit_transition_reopens_target_and_tampering_fails_before_write(
    recording_http: _RecordingHTTP,
) -> None:
    fixture = recording_http
    status, _, decision_payload = fixture.json_request(
        "POST",
        f"/api/decision?token={fixture.token}",
        {"phrase_id": "phrase-001", "outcome": "record_again"},
        headers={"Origin": fixture.origin},
    )
    assert status == 201
    parent_session = decision_payload["state"]["session"]
    request = fixture.capture_request(include_transition=True)
    tampered = json.loads(json.dumps(request))
    tampered["transition"]["expected_decisions"][0]["decision_document_sha256"] = (
        "0" * 64
    )

    status, _, payload = fixture.save_capture(tampered)

    assert status == 409
    assert "exact current decisions" in payload["error"]
    assert not fixture.capture_output_dir.exists()
    assert fixture.server.store.transitions() == []

    status, _, payload = fixture.save_capture(request)

    assert status == 201
    transition = payload["transition"]
    assert transition["decision_lineage"][0]["disposition"] == ("explicitly_reopened")
    assert transition["decision_lineage"][0]["child_decision_document_sha256"] is None
    child_session = payload["state"]["session"]
    assert child_session["coverage"]["decision_count"] == 0
    assert child_session["phrases"][0]["decision"] is None
    assert fixture.server.store.events(parent_session["session_id"])


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda request: request.update({"audio_wav_base64": "not base64!"}),
            "base64|audio|WAV",
        ),
        (
            lambda request: request.update(
                {
                    "audio_wav_base64": base64.b64encode(
                        _capture_wav(
                            sample_rate=SAMPLE_RATE,
                            frame_count=12_000,
                            subtype="PCM_16",
                        )
                    ).decode("ascii")
                }
            ),
            "PCM_24|PCM24|subtype",
        ),
        (
            lambda request: request["placement"].update(
                {"pre_guard_frames": request["placement"]["pre_guard_frames"] + 1}
            ),
            "guard|frame|geometry",
        ),
        (
            lambda request: request.update({"project_zero_padding": True}),
            "field|project.zero|padding|request",
        ),
    ),
    ids=("invalid-base64", "pcm16", "guard-drift", "project-zero-field"),
)
def test_capture_save_rejects_invalid_encoding_geometry_or_project_zero_padding(
    recording_http: _RecordingHTTP,
    mutate: Any,
    message: str,
) -> None:
    fixture = recording_http
    request = fixture.capture_request()
    mutate(request)

    status, _, payload = fixture.save_capture(request)

    assert status == 400
    assert re.search(message, payload["error"], re.IGNORECASE)
    assert not fixture.capture_output_dir.exists()


def test_capture_request_body_and_duration_are_bounded(
    recording_http: _RecordingHTTP,
) -> None:
    fixture = recording_http
    oversized = fixture.capture_request()
    oversized["audio_wav_base64"] = "A" * (MAX_CAPTURE_JSON_BYTES + 1)
    with pytest.raises(ValueError, match="audio_wav_base64"):
        fixture.server.admit_capture(oversized)

    request = fixture.capture_request()
    full_song_frames = round(2.5 * SAMPLE_RATE)
    request["audio_wav_base64"] = base64.b64encode(
        _capture_wav(sample_rate=SAMPLE_RATE, frame_count=full_song_frames)
    ).decode("ascii")
    request["placement"].update(
        {
            "source_phrase_start_frame": round(0.6 * SAMPLE_RATE),
            "source_phrase_end_frame": round(1.1 * SAMPLE_RATE),
            "pre_guard_frames": round(0.6 * SAMPLE_RATE),
            "post_guard_frames": round(1.4 * SAMPLE_RATE),
        }
    )
    status, _, payload = fixture.save_capture(request)
    assert status == 400
    assert "bounded" in payload["error"] or "guard" in payload["error"]
    assert not fixture.capture_output_dir.exists()


def test_browser_records_float32_but_only_explicit_save_posts_pcm24() -> None:
    source = Path(__file__).parents[1] / "src" / "sunofriend" / "vocal_session.js"
    page = Path(__file__).parents[1] / "src" / "sunofriend" / "vocal_session.html"
    javascript = source.read_text(encoding="utf-8")
    html = page.read_text(encoding="utf-8")

    assert "navigator.mediaDevices.getUserMedia" in javascript
    for setting in ("echoCancellation", "noiseSuppression", "autoGainControl"):
        assert setting in javascript
    assert "encodePcm24Wav" in javascript
    assert "encodePcm16PreviewWav" in javascript
    assert "previewBlob: encodePcm16PreviewWav" in javascript
    assert "URL.createObjectURL(recordedAttempt.previewBlob)" in javascript
    assert "audio_wav_base64: await blobBase64(recordedAttempt.blob)" in javascript
    assert "attemptPlayer.load()" in javascript
    assert "attemptPlayer.onloadedmetadata" in javascript
    assert "attemptPlayer.onerror" in javascript
    assert "plan.working_mix.vocal_segments" in javascript
    assert "if (plan.working_mix.backing)" in javascript
    assert "saveButton.disabled = true" in javascript
    assert "saveButton.disabled = false" in javascript
    assert 'appState.recording.save_url === "/api/candidate"' in javascript
    assert "api(appState.recording.save_url" in javascript
    assert 'querySelector("#save-recording")' in javascript
    assert 'querySelector("#record-attempt")' in javascript
    assert 'querySelector("#stop-recording")' in javascript
    assert "payload.transition = phrasePlan.transition" in javascript
    assert "Earlier decisions remain immutable" in javascript
    assert "Save this recording" in html
    assert 'id="save-recording"' in html
    assert 'id="record-attempt"' in html
    assert 'id="stop-recording"' in html
    assert "headphones" in html.casefold()
    assert "localStorage" not in javascript


def _create_musical_state(root: Path) -> tuple[Path, dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    takes = root / "takes"
    takes.mkdir()
    seconds = 2.5
    time = np.arange(round(SAMPLE_RATE * seconds), dtype=np.float64) / SAMPLE_RATE
    for index, frequency in enumerate((196.0, 220.0), 1):
        soundfile.write(
            takes / f"attempt-{index:02d}.wav",
            (0.1 * np.sin(2.0 * np.pi * frequency * time)).astype(np.float32),
            SAMPLE_RATE,
            subtype="PCM_24",
        )
    reference = root / "reference.wav"
    soundfile.write(
        reference,
        (0.1 * np.sin(2.0 * np.pi * 233.08 * time)).astype(np.float32),
        SAMPLE_RATE,
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
                        "start_seconds": 0.6,
                        "end_seconds": 1.1,
                        "lyrics": "One phrase",
                    },
                    {
                        "phrase_id": "phrase-002",
                        "start_seconds": 1.2,
                        "end_seconds": 1.7,
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


def _capture_wav(
    *, sample_rate: int, frame_count: int, subtype: str = "PCM_24"
) -> bytes:
    time = np.arange(frame_count, dtype=np.float64) / sample_rate
    audio = (0.08 * np.sin(2.0 * np.pi * 210.0 * time)).astype(np.float32)
    output = BytesIO()
    soundfile.write(output, audio, sample_rate, format="WAV", subtype=subtype)
    return output.getvalue()


def _create_context_audio(root: Path) -> tuple[Path, Path]:
    seconds = 2.5
    time = np.arange(round(SAMPLE_RATE * seconds), dtype=np.float64) / SAMPLE_RATE
    original = root / "original-mix.wav"
    backing = root / "instrumental-backing.wav"
    soundfile.write(
        original,
        (0.08 * np.sin(2.0 * np.pi * 146.83 * time)).astype(np.float32),
        SAMPLE_RATE,
        subtype="PCM_24",
    )
    soundfile.write(
        backing,
        (0.06 * np.sin(2.0 * np.pi * 130.81 * time)).astype(np.float32),
        SAMPLE_RATE,
        subtype="PCM_24",
    )
    return original, backing


def _tree_snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    if not root.exists():
        return {}
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            payload = path.read_bytes()
            result[path.relative_to(root).as_posix()] = (
                path.stat().st_mode & 0o777,
                path.stat().st_size,
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
