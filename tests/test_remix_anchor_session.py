from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import re
import stat
import sys
from threading import Thread
from typing import Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
from remix_learning_contract_fixtures import musical_state
from sunofriend.remix_anchor_preflight import (
    validate_remix_anchor_confirmation,
    validate_remix_anchor_preflight_state,
)
from sunofriend.remix_source_anchor import (
    REMIX_SOURCE_ANCHOR_CONFIRMATION_SCHEMA,
    validate_remix_source_anchor_confirmation,
    validate_remix_source_anchor_preflight,
    validate_remix_source_identity_state,
    validate_remix_source_owner_registry,
)
from sunofriend.remix_source_state import create_remix_source_state
from sunofriend.remix_anchor_session import (
    REMIX_ANCHOR_SESSION_SCHEMA,
    create_remix_anchor_server,
)
from sunofriend.remix_identity import (
    validate_remix_identity_state,
)
from sunofriend.remix_delta import inspect_remix_audio
from sunofriend.remix_learning_contract import validate_remix_owner_registry


def test_anchor_session_saves_one_explicit_confirmation_only(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    server = _server(fixture, tmp_path / "state")
    with _running(server):
        state = _get_json(server, "/api/session")
        assert state["schema"] == REMIX_ANCHOR_SESSION_SCHEMA
        assert state["status"] == "awaiting_explicit_owner_anchor"
        assert state["saved_confirmation"] is None
        assert str(tmp_path) not in json.dumps(state)
        assert state["authority"] == {
            "playback_creates_anchor": False,
            "automatic_anchor_inference": False,
            "remix_render_authorized": False,
            "pairwise_label_created": False,
            "training_execution_authorized": False,
            "product_selection_authorized": False,
        }

        media_url = state["media"]["source"]["media_url"]
        request = Request(_url(server, media_url), headers={"Range": "bytes=0-31"})
        with urlopen(request) as response:
            assert response.status == 206
            assert len(response.read()) == 32
        assert not (tmp_path / "state" / "CONFIRMED").exists()

        with _post(server, _payload(fixture["state"])) as response:
            assert response.status == 201
            saved = json.loads(response.read())
        assert saved["confirmation"] == {
            "schema": "sunofriend.remix-anchor-confirmation.v0",
            "status": "complete_explicit_owner_anchor_no_remix",
            "document_sha256": saved["confirmation"]["document_sha256"],
            "remix_render_authorized": False,
            "training_execution_authorized": False,
            "product_selection_authorized": False,
        }

        confirmed = tmp_path / "state" / "CONFIRMED"
        assert stat.S_IMODE(confirmed.stat().st_mode) == 0o700
        assert {path.name for path in confirmed.iterdir()} == {
            "anchor-preflight.json",
            "remix-identity-state.json",
            "owner-registry.json",
            "anchor-confirmation.json",
        }
        for path in confirmed.iterdir():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600

        pending = _read(confirmed / "anchor-preflight.json")
        identity = _read(confirmed / "remix-identity-state.json")
        registry = _read(confirmed / "owner-registry.json")
        receipt = _read(confirmed / "anchor-confirmation.json")
        assert (
            validate_remix_anchor_preflight_state(pending, fixture["state"]) == pending
        )
        assert validate_remix_identity_state(identity, fixture["state"]) == identity
        assert (
            validate_remix_owner_registry(
                registry,
                musical_states=[fixture["state"]],
                identity_states=[identity],
            )
            == registry
        )
        assert (
            validate_remix_anchor_confirmation(
                receipt, pending, fixture["state"], identity, registry
            )
            == receipt
        )

        try:
            with _post(server, _payload(fixture["state"])):
                raise AssertionError("duplicate anchor unexpectedly saved")
        except HTTPError as exc:
            assert exc.code == 409


def test_anchor_mutation_requires_same_origin_and_explicit_hearing(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    server = _server(fixture, tmp_path / "state")
    with _running(server):
        try:
            with _post(
                server,
                _payload(fixture["state"]),
                origin="https://example.invalid",
            ):
                raise AssertionError("cross-origin anchor unexpectedly saved")
        except HTTPError as exc:
            assert exc.code == 403

        payload = _payload(fixture["state"])
        payload["explicitly_heard"]["selected_estimate"] = False
        try:
            with _post(server, payload):
                raise AssertionError("unheard estimate unexpectedly confirmed")
        except HTTPError as exc:
            assert exc.code == 400
        assert not (tmp_path / "state" / "CONFIRMED").exists()


def test_anchor_media_is_rechecked_and_page_separates_playback_from_confirmation(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    server = _server(fixture, tmp_path / "state")
    with _running(server):
        html = _get_bytes(server, "/").decode()
        script = _get_bytes(server, "/remix_anchor_session.js").decode()
        assert "Define what must stay recognisable" in html
        assert "Listening alone saves nothing and chooses nothing" in html
        assert "Confirm this musical anchor" in html
        assert "data-play-source" in html
        assert "data-play-diagnostic" in script
        assert "complete mix" in html.casefold()
        assert "melody" in html.casefold()
        assert "rhythm" in html.casefold()
        assert "harmony" in html.casefold()
        assert "loadedmetadata" in script
        assert 'api("/api/confirm"' in script

        state = _get_json(server, "/api/session")
        fixture["estimate_path"].write_bytes(b"changed")
        try:
            with urlopen(_url(server, state["media"]["diagnostics"][0]["media_url"])):
                raise AssertionError("changed estimate unexpectedly served")
        except HTTPError as exc:
            assert exc.code == 409
        assert not (tmp_path / "state" / "CONFIRMED").exists()


def test_page_asset_urls_carry_the_session_token_like_a_browser_request(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    server = _server(fixture, tmp_path / "state")
    with _running(server):
        html = _get_bytes(server, "/").decode()
        asset_paths = re.findall(
            r'(?:href|src)="(/remix_anchor_session\.(?:css|js)[^"]*)"', html
        )

        assert len(asset_paths) == 2
        assert all(f"token={server.token}" in path for path in asset_paths)
        for path in asset_paths:
            with urlopen(f"http://127.0.0.1:{server.server_port}{path}") as response:
                assert response.status == 200
                assert response.read()


def test_anchor_session_refuses_unsynchronised_audio(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    sf.write(
        fixture["estimate_path"],
        np.zeros(31_999, dtype=np.float64),
        8_000,
        subtype="PCM_24",
    )
    with pytest.raises(ValueError, match="geometry differ"):
        _server(fixture, tmp_path / "state")


def test_semantic_diagnostic_views_bind_the_selected_estimate_only(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    server = create_remix_anchor_server(
        fixture["state"],
        source_control=fixture["source_path"],
        separation_estimate=fixture["estimate_path"],
        source_estimate_id="grouped-other-estimate-001",
        estimated_role="grouped other estimate",
        diagnostic_estimates={
            "vocals": fixture["estimate_path"],
            "drums": fixture["estimate_path"],
            "bass": fixture["estimate_path"],
            "grouped_other": fixture["estimate_path"],
        },
        state_dir=tmp_path / "semantic-session",
        identity_state_id="identity-state-001",
        registry_id="registry-001",
        composition_id="composition-001",
        group_id="recording-group-001",
        token="t" * 40,
    )
    with _running(server):
        state = _get_json(server, "/api/session")
        assert state["schema"] == REMIX_ANCHOR_SESSION_SCHEMA
        assert [row["diagnostic_id"] for row in state["media"]["diagnostics"]] == [
            "vocals",
            "drums",
            "bass",
            "grouped_other",
        ]
        assert state["media"]["source"]["label"] == "Complete original mix"
        assert state["media"]["diagnostics"][0]["musical_functions"] == [
            "melody",
            "rhythm",
            "harmony",
        ]
        payload = _payload(fixture["state"])
        payload["selected_estimate_id"] = "vocals"
        with _post(server, payload) as response:
            assert response.status == 201

    pending = _read(
        tmp_path / "semantic-session" / "CONFIRMED" / "anchor-preflight.json"
    )
    assert pending["separation_estimate"]["source_estimate_id"].startswith("vocals-")
    assert pending["separation_estimate"]["estimated_role"] == "vocal estimate"


def test_source_state_session_creates_v1_anchor_without_vocal_evidence(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    source = fixture["source_path"]
    source_state = create_remix_source_state(
        state_id="owner-source-001",
        composition_id="composition-source-001",
        group_id="recording-source-001",
        source_control=inspect_remix_audio(source),
        rights_category="owned",
        source_start_seconds=191.0,
        source_end_seconds=195.0,
        owner_local_training_approved=True,
    )
    fixture["state"] = source_state
    server = create_remix_anchor_server(
        source_state,
        source_control=source,
        separation_estimate=fixture["estimate_path"],
        source_estimate_id="grouped-other-estimate-001",
        estimated_role="grouped other estimate",
        state_dir=tmp_path / "source-state-session",
        identity_state_id="identity-source-001",
        registry_id="registry-source-001",
        token="s" * 40,
    )
    with _running(server):
        state = _get_json(server, "/api/session")
        assert state["project_state"] == {
            "schema": "sunofriend.remix-source-state.v0",
            "document_sha256": source_state["document_sha256"],
        }
        with _post(server, _payload(source_state)) as response:
            saved = json.loads(response.read())
        assert (
            saved["confirmation"]["schema"] == REMIX_SOURCE_ANCHOR_CONFIRMATION_SCHEMA
        )

    confirmed = tmp_path / "source-state-session" / "CONFIRMED"
    pending = _read(confirmed / "anchor-preflight.json")
    identity = _read(confirmed / "remix-identity-state.json")
    registry = _read(confirmed / "owner-registry.json")
    receipt = _read(confirmed / "anchor-confirmation.json")
    assert validate_remix_source_anchor_preflight(pending, source_state) == pending
    assert validate_remix_source_identity_state(identity, source_state) == identity
    assert (
        validate_remix_source_owner_registry(registry, source_state, identity)
        == registry
    )
    assert (
        validate_remix_source_anchor_confirmation(
            receipt, pending, source_state, identity, registry
        )
        == receipt
    )
    assert "lyrics" not in json.dumps(source_state)


def _fixture(root: Path) -> dict:
    root.chmod(0o700)
    rate = 8_000
    frames = 32_000
    time = np.arange(frames, dtype=np.float64) / rate
    source_path = root / "source.wav"
    estimate_path = root / "estimate.wav"
    sf.write(source_path, 0.2 * np.sin(2 * np.pi * 220 * time), rate, subtype="PCM_24")
    sf.write(
        estimate_path, 0.1 * np.sin(2 * np.pi * 110 * time), rate, subtype="PCM_24"
    )
    return {
        "state": musical_state("anchor-session"),
        "source_path": source_path,
        "estimate_path": estimate_path,
    }


def _server(fixture: dict, state_dir: Path):
    return create_remix_anchor_server(
        fixture["state"],
        source_control=fixture["source_path"],
        separation_estimate=fixture["estimate_path"],
        source_estimate_id="grouped-other-estimate-001",
        estimated_role="grouped other estimate",
        state_dir=state_dir,
        identity_state_id="identity-state-001",
        registry_id="registry-001",
        composition_id="composition-001",
        group_id="recording-group-001",
        token="t" * 40,
    )


def _payload(state: dict) -> dict:
    return {
        "expected_project_state_sha256": state["document_sha256"],
        "explicitly_heard": {
            "source_control": True,
            "selected_estimate": True,
        },
        "owner_label": "Keep the repeating accompaniment hook recognisable",
        "anchor_kind": "motif",
        "selected_estimate_id": "estimate",
        "start_frame": 8_000,
        "end_frame": 16_000,
        "preservation_requirement": "must_remain_recognisable",
    }


@contextmanager
def _running(server) -> Iterator[None]:
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _url(server, path: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"http://127.0.0.1:{server.server_port}{path}{separator}token={server.token}"


def _get_bytes(server, path: str) -> bytes:
    with urlopen(_url(server, path)) as response:
        return response.read()


def _get_json(server, path: str) -> dict:
    return json.loads(_get_bytes(server, path))


def _post(server, payload: dict, *, origin: str | None = None):
    if origin is None:
        origin = f"http://127.0.0.1:{server.server_port}"
    return urlopen(
        Request(
            _url(server, "/api/confirm"),
            method="POST",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Origin": origin},
        )
    )


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
