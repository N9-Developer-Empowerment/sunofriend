from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from sunofriend.core_four_approval import (
    APPROVAL_SCHEMA,
    CONFIG_SHA256,
    PROFILE_ID,
    SCOPE_ID,
    SOURCE_REVISION,
    WEIGHTS_SHA256,
    approval_binding,
    build_core_four_approval_server,
    render_core_four_approval_html,
    resolve_core_four_approved_songs,
    validate_core_four_approval_document,
    write_core_four_approval_page,
)


ROOT = Path(__file__).resolve().parents[1]


def _complete_document() -> dict:
    return {
        "schema": APPROVAL_SCHEMA,
        "status": "approvals_complete_for_verified_delivery",
        "approval_id": "approval-test",
        "profile": {
            "scope_id": SCOPE_ID,
            "profile_id": PROFILE_ID,
            "source_revision": SOURCE_REVISION,
            "weights_sha256": WEIGHTS_SHA256,
            "config_sha256": CONFIG_SHA256,
        },
        "evidence_acknowledged": approval_binding()["synthetic_evidence"],
        "approved_by": "Test Project Owner",
        "approvals": {
            "synthetic_listen": {
                "completed": True,
                "result": "no_catastrophic_defect",
                "details": "",
            },
            "full_song_canaries": {
                "offline_processing_authorized": True,
                "songs": [
                    {
                        "coverage_id": "vocal_forward",
                        "absolute_path": "/private/vocal.wav",
                        "rights_category": "owned",
                    },
                    {
                        "coverage_id": "dense_electronic",
                        "absolute_path": "/private/dense.wav",
                        "rights_category": "licensed",
                    },
                    {
                        "coverage_id": "acoustic_mixed",
                        "absolute_path": "/private/acoustic.wav",
                        "rights_category": "authorised_private_use",
                    },
                ],
            },
            "supported_machine": {
                "decision": "verify_36_gib_first",
                "machine_details": "",
                "claim_effect": (
                    "36 GB M3 Max becomes first verified class; 16 GiB remains "
                    "accessible but unverified"
                ),
            },
            "conditional_public_activation": True,
            "repository_publication": "pr_and_deploy_after_verification",
            "downstream_midi_requires_later_approval": True,
        },
        "boundaries": {
            "local_processing_only_for_canaries": True,
            "network_model_resolution": False,
            "audio_upload": False,
            "automatic_midi_or_create": False,
            "hosted_conversion_service": False,
            "maintainer_email_required_for_local_preview": False,
        },
        "remaining_approval_blockers": [],
        "remaining_objective_work": ["run canaries"],
        "missing_fields": [],
        "audio_included": False,
        "browser_telemetry_included": False,
        "exported_at": "2026-08-06T17:00:00.000Z",
    }


def test_approval_page_is_bound_local_and_downloadable(tmp_path: Path) -> None:
    synthetic = tmp_path / "synthetic"
    for relative in (
        "SOURCE/source-reference.wav",
        "STEMS/vocals.wav",
        "STEMS/drums.wav",
        "STEMS/bass.wav",
        "STEMS/other.wav",
        "AUDIO/reconstruction-check.wav",
    ):
        path = synthetic / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not-real-audio")

    page = render_core_four_approval_html(synthetic_root=synthetic)

    assert PROFILE_ID in page
    assert WEIGHTS_SHA256 in page
    assert APPROVAL_SCHEMA in page
    assert "Download approval JSON" in page
    assert "sunofriend-core-four-approval-" in page
    assert "connect-src 'none'" in page
    assert "media-src 'self' file:" in page
    assert "No maintainer email is outstanding" in page
    assert "Poor quality is not a veto" in page
    assert synthetic.joinpath("STEMS/vocals.wav").as_uri() in page
    assert "fetch(" not in page
    assert "XMLHttpRequest" not in page
    assert "WebSocket" not in page
    assert "sendBeacon" not in page
    assert "localStorage" not in page
    assert "sessionStorage" not in page


def test_approval_page_write_is_fresh_and_plan_is_read_only(tmp_path: Path) -> None:
    target = tmp_path / "approval.html"
    written = write_core_four_approval_page(target)
    assert written == target
    assert target.read_text(encoding="utf-8").startswith("<!doctype html>")
    with pytest.raises(FileExistsError):
        write_core_four_approval_page(target)

    before = set(tmp_path.iterdir())
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/create-core-four-approval-page.py"),
            "--plan",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["effects"]["writes"] == []
    assert set(tmp_path.iterdir()) == before


def test_local_server_exposes_only_form_health_and_exact_audio(tmp_path: Path) -> None:
    synthetic = tmp_path / "synthetic"
    audio_values = {
        "SOURCE/source-reference.wav": b"source-audio",
        "STEMS/vocals.wav": b"vocals-audio",
        "STEMS/drums.wav": b"drums-audio",
        "STEMS/bass.wav": b"bass-audio",
        "STEMS/other.wav": b"other-audio",
        "AUDIO/reconstruction-check.wav": b"reconstruction-audio",
    }
    for relative, value in audio_values.items():
        path = synthetic / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    server = build_core_four_approval_server(synthetic, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/", timeout=5) as response:
            page = response.read().decode("utf-8")
            assert response.headers["Cache-Control"] == "no-store"
            assert '/audio/vocals.wav' in page
            assert "file://" not in page
            assert "media-src 'self' file:" in page
        with urlopen(base + "/healthz", timeout=5) as response:
            assert json.loads(response.read())["network_scope"] == "localhost_only"
        request = Request(
            base + "/audio/vocals.wav",
            headers={"Range": "bytes=1-5"},
        )
        with urlopen(request, timeout=5) as response:
            assert response.status == 206
            assert response.headers["Content-Range"] == "bytes 1-5/12"
            assert response.read() == b"ocals"
        with pytest.raises(HTTPError) as missing:
            urlopen(base + "/audio/", timeout=5)
        assert missing.value.code == 404
        with pytest.raises(HTTPError) as posted:
            urlopen(Request(base + "/", data=b"private"), timeout=5)
        assert posted.value.code == 405
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_local_server_rejects_non_localhost_binding(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="localhost"):
        build_core_four_approval_server(tmp_path, host="0.0.0.0", port=0)


def test_completed_approval_document_validates() -> None:
    document = _complete_document()
    assert validate_core_four_approval_document(document) == document


def test_approved_song_resolution_records_exact_duplicate_paste(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / f"song-{index}.wav" for index in range(3)]
    for path in paths:
        path.write_bytes(b"local-audio")
    document = _complete_document()
    songs = document["approvals"]["full_song_canaries"]["songs"]
    songs[0]["absolute_path"] = str(paths[0])
    songs[1]["absolute_path"] = str(paths[1]) * 2
    songs[2]["absolute_path"] = str(paths[2])

    resolved = resolve_core_four_approved_songs(document)

    assert resolved[1]["approved_absolute_path"] == str(paths[1]) * 2
    assert resolved[1]["resolved_absolute_path"] == str(paths[1])
    assert resolved[1]["path_normalization"] == {
        "applied": True,
        "policy": "identical_absolute_path_halves_v1",
        "reason": "user_confirmed_accidental_duplicate_paste",
    }
    assert resolved[0]["path_normalization"]["applied"] is False


def test_approved_song_resolution_rejects_unapproved_missing_path(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / f"song-{index}.wav" for index in range(3)]
    paths[0].write_bytes(b"local-audio")
    paths[2].write_bytes(b"local-audio")
    document = _complete_document()
    songs = document["approvals"]["full_song_canaries"]["songs"]
    for song, path in zip(songs, paths):
        song["absolute_path"] = str(path)

    with pytest.raises(FileNotFoundError, match="receipt-safe normalization"):
        resolve_core_four_approved_songs(document)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(schema="wrong"), "schema"),
        (
            lambda value: value["approvals"]["full_song_canaries"]["songs"][0].update(
                absolute_path="relative.wav"
            ),
            "not absolute",
        ),
        (
            lambda value: value["approvals"].update(
                conditional_public_activation=False
            ),
            "not approved",
        ),
        (lambda value: value["missing_fields"].append("missing"), "incomplete"),
        (lambda value: value.update(status="incomplete"), "status differs"),
    ],
)
def test_invalid_approval_document_is_rejected(mutation, message: str) -> None:
    document = _complete_document()
    mutation(document)
    with pytest.raises(ValueError, match=message):
        validate_core_four_approval_document(document)
