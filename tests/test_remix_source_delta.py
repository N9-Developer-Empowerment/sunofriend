from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
import json
from pathlib import Path
from threading import Thread
from typing import Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pytest
import soundfile as sf

from sunofriend.remix_delta import inspect_remix_audio
from sunofriend.remix_source_anchor import (
    confirm_remix_source_anchor_preflight,
    create_remix_source_anchor_preflight,
)
from sunofriend.remix_source_delta import (
    REMIX_SOURCE_DELTA_PLAN_SCHEMA,
    create_remix_source_delta_plan,
    create_remix_source_delta_render_authorization,
    render_remix_source_delta,
    validate_remix_source_delta_plan,
    verify_remix_source_delta_result,
)
from sunofriend.remix_source_delta_audition import (
    REMIX_SOURCE_DELTA_AUDITION_SCHEMA,
    create_remix_source_delta_audition_server,
)
from sunofriend.remix_source_state import create_remix_source_state
from sunofriend.source_receipt import document_sha256


def test_two_variant_plan_edits_rhythm_not_confirmed_melody_anchor(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    plan = _plan(fixture)

    assert plan["schema"] == REMIX_SOURCE_DELTA_PLAN_SCHEMA
    assert plan["preserved_anchor"]["owner_label"] == "Keep the melody recognisable"
    assert plan["preserved_anchor"]["policy"] == "anchor_estimate_not_directly_edited"
    assert plan["target_estimate"]["musical_function"] == "rhythm"
    assert plan["target_estimate"]["estimated_role"] == "drums"
    assert [row["variant_id"] for row in plan["variant_family"]["variants"]] == [
        "gentle-rhythm-restraint",
        "strong-rhythm-restraint",
    ]
    assert not any(plan["effects"].values())
    assert plan["authority"]["render_authorized"] is False
    assert plan["authority"]["training_execution_authorized"] is False
    assert (
        validate_remix_source_delta_plan(
            plan,
            fixture["state"],
            fixture["preflight"],
            fixture["identity"],
            fixture["registry"],
            fixture["confirmation"],
        )
        == plan
    )


def test_render_is_exact_source_control_two_deltas_and_stays_unreviewed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    plan = _plan(fixture)
    with pytest.raises(ValueError, match="explicit owner authorization"):
        create_remix_source_delta_render_authorization(plan)
    authorization = create_remix_source_delta_render_authorization(
        plan, confirm_private_ab_preview=True
    )
    output = tmp_path / "render"
    with pytest.raises(ValueError, match="separate exact render"):
        render_remix_source_delta(
            plan,
            authorization,
            source_audio=fixture["source_path"],
            target_estimate_audio=fixture["drums_path"],
            out_dir=output,
            expected_plan_sha256=plan["document_sha256"],
        )

    verification = render_remix_source_delta(
        plan,
        authorization,
        source_audio=fixture["source_path"],
        target_estimate_audio=fixture["drums_path"],
        out_dir=output,
        expected_plan_sha256=plan["document_sha256"],
        confirm_render=True,
    )
    assert verification["status"] == "complete_unreviewed_two_variant_private_preview"
    assert (output / "AUDIO/original-context.wav").read_bytes() == fixture[
        "source_path"
    ].read_bytes()
    assert verification["authority"]["human_review_created"] is False
    assert verification["authority"]["training_label_created"] is False
    assert verification["effects"]["two_audio_derivatives_rendered"] is True
    assert verify_remix_source_delta_result(output) == verification

    first, _ = sf.read(output / "AUDIO/candidate-1.wav", always_2d=True)
    second, _ = sf.read(output / "AUDIO/candidate-2.wav", always_2d=True)
    assert not np.array_equal(first, second)


def test_target_anchor_alias_tamper_and_artifact_change_fail_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    anchor_target = dict(fixture["drums"])
    anchor_target["audio_sha256"] = fixture["other"]["audio_sha256"]
    with pytest.raises(ValueError, match="distinct from the anchor"):
        create_remix_source_delta_plan(
            fixture["state"],
            fixture["preflight"],
            fixture["identity"],
            fixture["registry"],
            fixture["confirmation"],
            target_estimate=anchor_target,
            variants=_variants(fixture["frames"]),
        )

    plan = _plan(fixture)
    changed = deepcopy(plan)
    changed["preserved_anchor"]["owner_label"] = "Anything may change"
    _rehash(changed)
    with pytest.raises(ValueError, match="preserved remix anchor"):
        validate_remix_source_delta_plan(
            changed,
            fixture["state"],
            fixture["preflight"],
            fixture["identity"],
            fixture["registry"],
            fixture["confirmation"],
        )

    authorization = create_remix_source_delta_render_authorization(
        plan, confirm_private_ab_preview=True
    )
    output = tmp_path / "render"
    render_remix_source_delta(
        plan,
        authorization,
        source_audio=fixture["source_path"],
        target_estimate_audio=fixture["drums_path"],
        out_dir=output,
        expected_plan_sha256=plan["document_sha256"],
        confirm_render=True,
    )
    (output / "AUDIO/candidate-1.wav").write_bytes(b"changed")
    with pytest.raises(ValueError, match="identity changed"):
        verify_remix_source_delta_result(output)


def test_render_opens_as_hidden_playback_only_ab_without_writes(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    plan = _plan(fixture)
    authorization = create_remix_source_delta_render_authorization(
        plan, confirm_private_ab_preview=True
    )
    output = tmp_path / "render"
    render_remix_source_delta(
        plan,
        authorization,
        source_audio=fixture["source_path"],
        target_estimate_audio=fixture["drums_path"],
        out_dir=output,
        expected_plan_sha256=plan["document_sha256"],
        confirm_render=True,
    )
    before = _file_roster(output)
    server = create_remix_source_delta_audition_server(
        output,
        title="Private rhythm-restraint A/B",
        token="a" * 40,
        presentation_seed=20260827,
    )

    with _running(server):
        state = _get_json(server, "/api/session")
        assert state["schema"] == REMIX_SOURCE_DELTA_AUDITION_SCHEMA
        assert state["status"] == "private_hidden_ab_audition_only"
        assert state["title"] == "Private rhythm-restraint A/B"
        assert state["authority"] == {
            "playback_creates_review": False,
            "preference_can_be_saved": False,
            "training_label_created": False,
            "training_execution_authorized": False,
            "product_selection_authorized": False,
        }
        assert set(server.display_variant_ids) == {"a", "b"}
        assert set(server.display_variant_ids.values()) == {
            "gentle-rhythm-restraint",
            "strong-rhythm-restraint",
        }
        assert str(tmp_path) not in json.dumps(state)

        for name in ("control", "a", "b"):
            media_url = state["media"][name]["media_url"]
            request = Request(_url(server, media_url), headers={"Range": "bytes=0-31"})
            with urlopen(request) as response:
                assert response.status == 206
                assert len(response.read()) == 32

        html = _get_bytes(server, "/").decode()
        script = _get_bytes(server, "/remix_source_delta_audition.js").decode()
        assert "Audition only" in html
        assert "cannot save" in html
        assert 'data-play="a"' in html and 'data-play="b"' in html
        assert "/api/label" not in html + script

        request = Request(
            _url(server, "/api/label"),
            method="POST",
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request)
        assert error.value.code == 405

    assert _file_roster(output) == before


def test_audition_rechecks_audio_after_launch(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    plan = _plan(fixture)
    authorization = create_remix_source_delta_render_authorization(
        plan, confirm_private_ab_preview=True
    )
    output = tmp_path / "render"
    render_remix_source_delta(
        plan,
        authorization,
        source_audio=fixture["source_path"],
        target_estimate_audio=fixture["drums_path"],
        out_dir=output,
        expected_plan_sha256=plan["document_sha256"],
        confirm_render=True,
    )
    server = create_remix_source_delta_audition_server(
        output, token="b" * 40, presentation_seed=4
    )
    selected = server.display_variant_ids["a"]
    row = next(
        item
        for item in server.verified_result["artifacts"]["candidates"]
        if item["variant_id"] == selected
    )
    with _running(server):
        state = _get_json(server, "/api/session")
        (output / row["path"]).write_bytes(b"changed")
        with pytest.raises(HTTPError) as error:
            urlopen(_url(server, state["media"]["a"]["media_url"]))
        assert error.value.code == 409


def _fixture(root: Path) -> dict:
    rate = 8_000
    frames = 16_000
    time = np.arange(frames, dtype=np.float64) / rate
    inputs = root / "inputs"
    inputs.mkdir()
    source_path = inputs / "source.wav"
    other_path = inputs / "other.wav"
    drums_path = inputs / "drums.wav"
    source = 0.20 * np.sin(2 * np.pi * 220 * time) + 0.08 * np.sin(2 * np.pi * 3 * time)
    other = 0.12 * np.sin(2 * np.pi * 220 * time)
    drums = 0.08 * np.sin(2 * np.pi * 3 * time)
    for path, values in (
        (source_path, source),
        (other_path, other),
        (drums_path, drums),
    ):
        sf.write(path, values, rate, subtype="PCM_24")
    source_record = inspect_remix_audio(source_path)
    other_record = inspect_remix_audio(other_path)
    drums_record = inspect_remix_audio(drums_path)
    state = create_remix_source_state(
        state_id="source-state",
        composition_id="composition",
        group_id="group",
        source_control=source_record,
        rights_category="owned",
        source_start_seconds=10.0,
        source_end_seconds=12.0,
        owner_local_training_approved=True,
    )
    other_estimate = {
        "source_estimate_id": "grouped-other-estimate",
        "estimated_role": "grouped accompaniment estimate",
        **other_record,
    }
    preflight = create_remix_source_anchor_preflight(
        state,
        separation_estimate=other_estimate,
        owner_label="Keep the melody recognisable",
        anchor_kind="motif",
        start_frame=0,
        end_frame=8_000,
        preservation_requirement="must_remain_recognisable",
        heard_source=True,
        heard_estimate=True,
    )
    confirmed = confirm_remix_source_anchor_preflight(
        preflight,
        state,
        identity_state_id="identity",
        registry_id="registry",
    )
    drums_estimate = {
        "source_estimate_id": "drums-estimate",
        "source_kind": "separation_estimate",
        "role_interpretation": "estimate_not_ground_truth",
        "estimated_role": "drums",
        "musical_function": "rhythm",
        **drums_record,
    }
    return {
        "state": state,
        "preflight": preflight,
        "identity": confirmed["identity_state"],
        "registry": confirmed["owner_registry"],
        "confirmation": confirmed["confirmation"],
        "source_path": source_path,
        "drums_path": drums_path,
        "other": other_record,
        "drums": drums_estimate,
        "frames": frames,
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


def _file_roster(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes().hex()
        for path in root.rglob("*")
        if path.is_file()
    }


def _plan(fixture: dict) -> dict:
    return create_remix_source_delta_plan(
        fixture["state"],
        fixture["preflight"],
        fixture["identity"],
        fixture["registry"],
        fixture["confirmation"],
        target_estimate=fixture["drums"],
        variants=_variants(fixture["frames"]),
    )


def _variants(frames: int) -> list[dict]:
    return [
        {
            "variant_id": "gentle-rhythm-restraint",
            "points": [
                {"frame": 0, "delta_db": -2.0},
                {"frame": frames // 2, "delta_db": -2.0},
                {"frame": frames, "delta_db": 0.0},
            ],
        },
        {
            "variant_id": "strong-rhythm-restraint",
            "points": [
                {"frame": 0, "delta_db": -5.0},
                {"frame": frames // 2, "delta_db": -5.0},
                {"frame": frames, "delta_db": 0.0},
            ],
        },
    ]


def _rehash(document: dict) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)
