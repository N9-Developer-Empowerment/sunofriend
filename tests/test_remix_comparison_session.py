from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import stat
from threading import Thread
from typing import Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import soundfile as sf

from sunofriend.remix_delta import inspect_remix_audio
from sunofriend.remix_comparison_session import (
    REMIX_COMPARISON_REOPEN_SCHEMA,
    REMIX_COMPARISON_REVIEW_SCHEMA,
    REMIX_COMPARISON_SESSION_SCHEMA,
    create_remix_comparison_server,
)
from sunofriend.remix_source_anchor import (
    confirm_remix_source_anchor_preflight,
    create_remix_source_anchor_preflight,
)
from sunofriend.remix_source_state import create_remix_source_state


def test_review_only_session_binds_hidden_pair_and_has_no_downstream_authority(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    server = _server(fixture, tmp_path / "session", seed=20260822)
    with _running(server):
        state = _get_json(server, "/api/session")
        assert state["schema"] == REMIX_COMPARISON_SESSION_SCHEMA
        assert state["status"] == "open_for_review"
        assert state["revision"] == 1
        assert state["draft"] is None
        assert state["saved_review"] is None
        assert state["anchors"] == ["Keep the instrumental hook recognisable"]
        assert set(state["media"]) == {"original", "a", "b"}
        assert "candidate-control" not in json.dumps(state)
        assert "candidate-change" not in json.dumps(state)
        assert fixture["candidate_records"]["candidate-control"][
            "audio_sha256"
        ] not in json.dumps(state)
        assert not any(state["authority"].values())
        assert not any(state["effects"].values())

        request = Request(
            _url(server, state["media"]["a"]["media_url"]),
            headers={"Range": "bytes=0-31"},
        )
        with urlopen(request) as response:
            assert response.status == 206
            assert len(response.read()) == 32

        html = _get_bytes(server, "/").decode()
        script = _get_bytes(server, "/remix_comparison_session.js").decode()
        assert "One shared playhead" in html
        assert "I heard Version A" in html and "I heard Version B" in html
        assert "Save this review locally" in html
        assert "Reopen this review" in html
        assert "training" in html
        assert 'api("/api/review"' in script
        assert 'api("/api/draft"' in script
        assert 'api("/api/reopen"' in script

    session_path = tmp_path / "session" / "SESSION.json"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert set(session["hidden_mapping"].values()) == {
        "candidate-control",
        "candidate-change",
    }
    assert stat.S_IMODE(session_path.stat().st_mode) == 0o600
    assert not (tmp_path / "session" / "LABELS").exists()


def test_draft_resumes_and_hidden_mapping_is_stable_across_restart(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    state_dir = tmp_path / "resume"
    server = _server(fixture, state_dir, seed=7)
    payload = _answers(fixture, complete=False)
    payload["explicitly_heard"] = {"original": True, "a": True, "b": False}
    payload["outcome"] = "a"
    payload["identity_retention"] = {"a": "preserved", "b": ""}
    with _running(server):
        mapping = dict(server.display_candidate_ids)
        with _post(server, "/api/draft", payload) as response:
            assert response.status == 200
    restarted = _server(fixture, state_dir, seed=999)
    try:
        state = restarted.browser_state()
        assert restarted.display_candidate_ids == mapping
        assert state["draft"]["answers"]["outcome"] == "a"
        assert state["draft"]["answers"]["explicitly_heard"]["b"] is False
        assert state["revision"] == 1
    finally:
        restarted.server_close()


def test_review_and_reopen_are_append_only_and_keep_exact_audio_mapping(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    state_dir = tmp_path / "history"
    server = _server(fixture, state_dir, seed=19)
    payload = _answers(fixture, complete=True)
    with _running(server):
        with _post(server, "/api/review", payload) as response:
            assert response.status == 201
            saved = json.loads(response.read())
        state = saved["state"]
        assert state["status"] == "review_saved"
        assert state["saved_review"]["revision"] == 1
        assert not any(state["authority"].values())

        review_paths = list((state_dir / "REVIEWS").glob("*.json"))
        assert len(review_paths) == 1
        first_bytes = review_paths[0].read_bytes()
        review = json.loads(first_bytes)
        assert review["schema"] == REMIX_COMPARISON_REVIEW_SCHEMA
        assert review["answers"]["outcome"] == "a"
        assert review["answers"]["goal_usefulness"] == {
            "a": "useful",
            "b": "not_useful",
        }
        assert not any(review["authority"].values())
        assert not any(review["effects"].values())
        for display_id in ("a", "b"):
            candidate_id = server.display_candidate_ids[display_id]
            assert review["presentation"][display_id] == {
                "candidate_id": candidate_id,
                "audio": fixture["candidate_records"][candidate_id],
            }

        reopen = {
            "expected_comparison_sha256": state["comparison_sha256"],
            "expected_review_sha256": state["saved_review"]["document_sha256"],
            "reason_code": "listen_again",
        }
        with _post(server, "/api/reopen", reopen) as response:
            reopened = json.loads(response.read())
        assert reopened["reopen"]["schema"] == REMIX_COMPARISON_REOPEN_SCHEMA
        assert reopened["state"]["status"] == "open_for_review"
        assert reopened["state"]["revision"] == 2
        assert reopened["state"]["draft"]["answers"] == review["answers"]

        payload["outcome"] = "equivalent"
        with _post(server, "/api/review", payload) as response:
            second = json.loads(response.read())
        assert second["state"]["saved_review"]["revision"] == 2
        assert len(list((state_dir / "REVIEWS").glob("*.json"))) == 2
        assert len(list((state_dir / "HISTORY").glob("*.json"))) == 1
        assert review_paths[0].read_bytes() == first_bytes
        assert not (state_dir / "LABELS").exists()


def test_review_requires_exact_binding_explicit_listening_and_same_origin(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    server = _server(fixture, tmp_path / "guards", seed=2)
    payload = _answers(fixture, complete=True)
    with _running(server):
        payload["expected_comparison_sha256"] = "0" * 64
        with _error(400):
            _post(server, "/api/review", payload)
        payload["expected_comparison_sha256"] = server.comparison["document_sha256"]
        payload["explicitly_heard"]["b"] = False
        with _error(400):
            _post(server, "/api/review", payload)
        payload["explicitly_heard"]["b"] = True
        with _error(403):
            _post(server, "/api/review", payload, origin="https://example.invalid")
        assert not list((tmp_path / "guards" / "REVIEWS").glob("*.json"))


def test_media_change_after_launch_is_refused(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    server = _server(fixture, tmp_path / "changed", seed=6)
    with _running(server):
        state = server.browser_state()
        changed_id = server.display_candidate_ids["a"]
        fixture["candidate_paths"][changed_id].write_bytes(b"changed")
        with _error(409):
            urlopen(_url(server, state["media"]["a"]["media_url"]))


def _fixture(root: Path) -> dict:
    root.chmod(0o700)
    rate = 8_000
    frames = 16_000
    time = np.arange(frames, dtype=np.float64) / rate
    original_path = root / "synthetic-original.wav"
    control_path = root / "synthetic-control.wav"
    change_path = root / "synthetic-change.wav"
    estimate_path = root / "synthetic-estimate.wav"
    sf.write(
        original_path, 0.2 * np.sin(2 * np.pi * 220 * time), rate, subtype="PCM_24"
    )
    sf.write(control_path, 0.2 * np.sin(2 * np.pi * 220 * time), rate, subtype="PCM_24")
    sf.write(change_path, 0.16 * np.sin(2 * np.pi * 220 * time), rate, subtype="PCM_24")
    sf.write(
        estimate_path, 0.12 * np.sin(2 * np.pi * 330 * time), rate, subtype="PCM_24"
    )
    original = inspect_remix_audio(original_path)
    estimate_audio = inspect_remix_audio(estimate_path)
    state = create_remix_source_state(
        state_id="synthetic-source-state",
        composition_id="synthetic-composition",
        group_id="synthetic-group",
        source_control=original,
        rights_category="owned",
        source_start_seconds=12.0,
        source_end_seconds=14.0,
        owner_local_training_approved=True,
    )
    estimate = {
        "source_estimate_id": "synthetic-estimate",
        "estimated_role": "grouped_other",
        **estimate_audio,
    }
    preflight = create_remix_source_anchor_preflight(
        state,
        separation_estimate=estimate,
        owner_label="Keep the instrumental hook recognisable",
        anchor_kind="motif",
        start_frame=2_000,
        end_frame=10_000,
        preservation_requirement="must_remain_recognisable",
        heard_source=True,
        heard_estimate=True,
    )
    confirmed = confirm_remix_source_anchor_preflight(
        preflight,
        state,
        identity_state_id="synthetic-identity",
        registry_id="synthetic-registry",
    )
    candidate_paths = {
        "candidate-control": control_path,
        "candidate-change": change_path,
    }
    return {
        "state": state,
        "preflight": preflight,
        "identity": confirmed["identity_state"],
        "registry": confirmed["owner_registry"],
        "confirmation": confirmed["confirmation"],
        "original_path": original_path,
        "candidate_paths": candidate_paths,
        "candidate_records": {
            candidate_id: inspect_remix_audio(path)
            for candidate_id, path in candidate_paths.items()
        },
    }


def _server(fixture: dict, state_dir: Path, *, seed: int):
    return create_remix_comparison_server(
        fixture["state"],
        fixture["preflight"],
        fixture["identity"],
        fixture["registry"],
        fixture["confirmation"],
        original_audio=fixture["original_path"],
        candidate_audio=fixture["candidate_paths"],
        state_dir=state_dir,
        title="Synthetic controlled remix review",
        goal="Make the change useful while keeping the hook recognisable.",
        token="t" * 40,
        presentation_seed=seed,
    )


def _answers(fixture: dict, *, complete: bool) -> dict:
    return {
        "expected_comparison_sha256": "placeholder",
        "explicitly_heard": {
            "original": complete,
            "a": complete,
            "b": complete,
        },
        "outcome": "a" if complete else "",
        "identity_retention": {
            "a": "preserved" if complete else "",
            "b": "partly_preserved" if complete else "",
        },
        "goal_usefulness": {
            "a": "useful" if complete else "",
            "b": "not_useful" if complete else "",
        },
        "reason_codes": ["musical_change"] if complete else [],
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


@contextmanager
def _error(code: int) -> Iterator[None]:
    try:
        yield
        raise AssertionError(f"expected HTTP {code}")
    except HTTPError as exc:
        assert exc.code == code


def _url(server, path: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"http://127.0.0.1:{server.server_port}{path}{separator}token={server.token}"


def _get_bytes(server, path: str) -> bytes:
    with urlopen(_url(server, path)) as response:
        return response.read()


def _get_json(server, path: str) -> dict:
    return json.loads(_get_bytes(server, path))


def _post(server, path: str, payload: dict, *, origin: str | None = None):
    if payload.get("expected_comparison_sha256") == "placeholder":
        payload["expected_comparison_sha256"] = server.comparison["document_sha256"]
    if origin is None:
        origin = f"http://127.0.0.1:{server.server_port}"
    return urlopen(
        Request(
            _url(server, path),
            method="POST",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Origin": origin},
        )
    )
