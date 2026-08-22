from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import stat
import sys
from threading import Thread
from typing import Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
from remix_learning_contract_fixtures import remix_fixture
from sunofriend.remix_delta import inspect_remix_audio
from sunofriend.remix_identity import create_remix_result
from sunofriend.remix_learning_contract import (
    create_remix_controlled_variant_set,
    create_remix_owner_registry,
    validate_remix_pairwise_label,
)
from sunofriend.remix_pairwise_session import (
    REMIX_PAIRWISE_SESSION_SCHEMA,
    create_remix_pairwise_review_server,
)


def test_private_ab_session_creates_only_one_explicit_exact_label(
    tmp_path: Path,
) -> None:
    fixture = _session_fixture(tmp_path)
    server = create_remix_pairwise_review_server(
        fixture["state"],
        fixture["registry"],
        fixture["variant_set"],
        fixture["identity"],
        control_audio=fixture["control_path"],
        variant_audio=fixture["variant_paths"],
        state_dir=tmp_path / "state",
        title="Owner remix comparison",
        token="t" * 40,
        presentation_seed=20260821,
    )
    with _running(server):
        state = _get_json(server, "/api/session")
        assert state["schema"] == REMIX_PAIRWISE_SESSION_SCHEMA
        assert state["status"] == "awaiting_explicit_owner_label"
        assert state["title"] == "Owner remix comparison"
        assert state["saved_label"] is None
        assert set(server.display_variant_ids) == {"a", "b"}
        assert set(server.display_variant_ids.values()) == {"delta-3db", "delta-5db"}
        assert state["authority"] == {
            "playback_creates_label": False,
            "automatic_preference": False,
            "selected_for_product": False,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
        }
        assert str(tmp_path) not in json.dumps(state)
        assert not list((tmp_path / "state" / "LABELS").glob("*.json"))

        control_url = state["media"]["control"]["media_url"]
        request = Request(_url(server, control_url), headers={"Range": "bytes=0-31"})
        with urlopen(request) as response:
            assert response.status == 206
            assert len(response.read()) == 32
        assert not list((tmp_path / "state" / "LABELS").glob("*.json"))

        payload = {
            "expected_variant_set_sha256": fixture["variant_set"]["document_sha256"],
            "explicitly_heard": {"control": True, "a": True, "b": True},
            "outcome": "a",
            "identity_relationships": {
                "a": "preserved",
                "b": "partly_preserved",
            },
            "reason_codes": ["change_more_useful", "identity_better_preserved"],
            "admit_owner_local_training": True,
        }
        with _post(server, payload) as response:
            assert response.status == 201
            saved = json.loads(response.read())
        assert saved["label"]["training_eligible"] is False
        assert saved["label"]["training_execution_authorized"] is False
        assert saved["label"]["selected_for_product"] is False

        label_paths = list((tmp_path / "state" / "LABELS").glob("*.json"))
        assert len(label_paths) == 1
        assert stat.S_IMODE(label_paths[0].stat().st_mode) == 0o600
        label = json.loads(label_paths[0].read_text(encoding="utf-8"))
        assert label["left"]["variant_id"] == server.display_variant_ids["a"]
        assert label["right"]["variant_id"] == server.display_variant_ids["b"]
        assert label["outcome"] == "left"
        assert label["presentation"]["seed"] == 20260821
        assert (
            validate_remix_pairwise_label(
                label,
                fixture["registry"],
                fixture["variant_set"],
                fixture["identity"],
            )
            == label
        )

        try:
            with _post(server, payload):
                raise AssertionError("duplicate label unexpectedly saved")
        except HTTPError as exc:
            assert exc.code == 409
        assert len(list((tmp_path / "state" / "LABELS").glob("*.json"))) == 1


def test_mutation_requires_same_origin_and_explicit_admission(tmp_path: Path) -> None:
    fixture = _session_fixture(tmp_path)
    server = create_remix_pairwise_review_server(
        fixture["state"],
        fixture["registry"],
        fixture["variant_set"],
        fixture["identity"],
        control_audio=fixture["control_path"],
        variant_audio=fixture["variant_paths"],
        state_dir=tmp_path / "state",
        token="u" * 40,
        presentation_seed=8,
    )
    payload = {
        "expected_variant_set_sha256": fixture["variant_set"]["document_sha256"],
        "explicitly_heard": {"control": True, "a": True, "b": True},
        "outcome": "equivalent",
        "identity_relationships": {"a": "preserved", "b": "preserved"},
        "reason_codes": ["change_inaudible"],
        "admit_owner_local_training": True,
    }
    with _running(server):
        try:
            with _post(server, payload, origin="https://example.invalid"):
                raise AssertionError("cross-origin label unexpectedly saved")
        except HTTPError as exc:
            assert exc.code == 403
        payload["admit_owner_local_training"] = False
        try:
            with _post(server, payload):
                raise AssertionError("unadmitted label unexpectedly saved")
        except HTTPError as exc:
            assert exc.code == 400
        assert not list((tmp_path / "state" / "LABELS").glob("*.json"))


def test_media_is_rechecked_and_ui_keeps_playback_separate_from_save(
    tmp_path: Path,
) -> None:
    fixture = _session_fixture(tmp_path)
    server = create_remix_pairwise_review_server(
        fixture["state"],
        fixture["registry"],
        fixture["variant_set"],
        fixture["identity"],
        control_audio=fixture["control_path"],
        variant_audio=fixture["variant_paths"],
        state_dir=tmp_path / "state",
        token="v" * 40,
        presentation_seed=9,
    )
    with _running(server):
        html = _get_bytes(server, "/").decode()
        script = _get_bytes(server, "/remix_pairwise_session.js").decode()
        assert "Listening chooses nothing" in html
        assert "Save explicit A/B label" in html
        assert 'data-play="a"' in html and 'data-play="b"' in html
        assert "heardByPlayback" in script
        assert 'api("/api/label"' in script
        assert "playback_creates_label" not in script

        state = _get_json(server, "/api/session")
        fixture["variant_paths"][server.display_variant_ids["a"]].write_bytes(
            b"changed"
        )
        try:
            with urlopen(_url(server, state["media"]["a"]["media_url"])):
                raise AssertionError("changed media unexpectedly served")
        except HTTPError as exc:
            assert exc.code == 409


def _session_fixture(root: Path) -> dict:
    root.chmod(0o700)
    fixture = remix_fixture()
    rate = 8_000
    frames = 32_000
    time = np.arange(frames, dtype=np.float64) / rate
    control_path = root / "control.wav"
    left_path = root / "left.wav"
    right_path = root / "right.wav"
    sf.write(control_path, 0.2 * np.sin(2 * np.pi * 220 * time), rate, subtype="PCM_24")
    sf.write(left_path, 0.18 * np.sin(2 * np.pi * 220 * time), rate, subtype="PCM_24")
    sf.write(right_path, 0.16 * np.sin(2 * np.pi * 220 * time), rate, subtype="PCM_24")
    control = inspect_remix_audio(control_path)
    left_result = create_remix_result(
        fixture["left_request"],
        fixture["identity"],
        output_audio_sha256=inspect_remix_audio(left_path)["audio_sha256"],
        output_audio_bytes=inspect_remix_audio(left_path)["audio_bytes"],
        output_geometry=inspect_remix_audio(left_path)["geometry"],
    )
    right_result = create_remix_result(
        fixture["right_request"],
        fixture["identity"],
        output_audio_sha256=inspect_remix_audio(right_path)["audio_sha256"],
        output_audio_bytes=inspect_remix_audio(right_path)["audio_bytes"],
        output_geometry=inspect_remix_audio(right_path)["geometry"],
    )
    registry = create_remix_owner_registry(
        registry_id="owner-remix-registry-session",
        entries=[
            {
                "composition_id": "composition-001",
                "group_id": "recording-group-001",
                "musical_state": fixture["state"],
                "identity_state": fixture["identity"],
                "source_control": control,
                "rights_scope": "owner_local_training",
                "cloud_training_approved": False,
            }
        ],
    )
    variant_set = create_remix_controlled_variant_set(
        registry,
        fixture["identity"],
        variant_set_id="variant-set-session",
        variant_family_id="same-anchor-gain-envelope-session",
        source_control=control,
        variants=[
            {
                "variant_id": "delta-3db",
                "remix_request": fixture["left_request"],
                "remix_result": left_result,
            },
            {
                "variant_id": "delta-5db",
                "remix_request": fixture["right_request"],
                "remix_result": right_result,
            },
        ],
    )
    return {
        "state": fixture["state"],
        "identity": fixture["identity"],
        "registry": registry,
        "variant_set": variant_set,
        "control_path": control_path,
        "variant_paths": {"delta-3db": left_path, "delta-5db": right_path},
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
            _url(server, "/api/label"),
            method="POST",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Origin": origin},
        )
    )
