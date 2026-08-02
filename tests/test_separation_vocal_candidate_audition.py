from __future__ import annotations

import copy
import hashlib
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import sunofriend._separation_vocal_candidate_audition as audition
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def test_review_seed_is_path_free_and_does_not_rank_or_choose(tmp_path: Path) -> None:
    inventory, excerpt, media = _evidence(tmp_path)

    seed = audition._review_seed(
        inventory,
        candidate_set_file_sha256="a" * 64,
        excerpt=excerpt,
        excerpt_file_sha256="b" * 64,
        focus="Follow the intended lead melody",
        candidate_media=media,
    )

    assert seed["status"] == "unreviewed"
    assert seed["policy"]["ordering_has_rank_semantics"] is False
    assert seed["policy"]["multiple_useful_candidates_allowed"] is True
    assert seed["policy"]["winner_required"] is False
    assert seed["effects"]["candidate_selected"] is False
    assert seed["choices"][0]["heard_candidate"] is False
    assert seed["choices"][1]["disposition"] == "unavailable"
    assert not _contains_key(seed, "path")
    assert str(tmp_path) not in json.dumps(seed)


def test_complete_review_keeps_multiple_useful_candidates() -> None:
    seed = _three_available_seed()
    review = copy.deepcopy(seed)
    review["status"] = "reviewed"
    review["reviewed_at"] = "2026-08-02T12:00:00+00:00"
    for index, row in enumerate(review["choices"]):
        row["heard_reference"] = True
        row["heard_candidate"] = True
        row["disposition"] = (
            "useful_for_focus" if index < 2 else "cannot_tell"
        )

    result = audition._verify_review_document(seed, review)

    assert result == {
        "useful_for_focus": ["candidate-1", "candidate-2"],
        "not_useful_for_focus": [],
        "cannot_tell": ["candidate-3"],
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda review: review.update(focus="changed"), "immutable evidence"),
        (
            lambda review: review["choices"][0].update(heard_candidate=False),
            "must be heard",
        ),
        (
            lambda review: review["choices"][0].update(disposition="winner"),
            "one disposition",
        ),
        (
            lambda review: review["choices"][0].update(candidate_id="swapped"),
            "order or identity",
        ),
    ],
)
def test_review_rejects_incomplete_or_changed_evidence(mutation, message: str) -> None:
    seed = _three_available_seed()
    review = copy.deepcopy(seed)
    review["status"] = "reviewed"
    review["reviewed_at"] = "2026-08-02T12:00:00Z"
    for row in review["choices"]:
        row.update(
            heard_reference=True,
            heard_candidate=True,
            disposition="not_useful_for_focus",
        )
    mutation(review)

    with pytest.raises(ValueError, match=message):
        audition._verify_review_document(seed, review)


def test_no_note_candidate_cannot_be_turned_into_a_choice(tmp_path: Path) -> None:
    inventory, excerpt, media = _evidence(tmp_path)
    seed = audition._review_seed(
        inventory,
        candidate_set_file_sha256="a" * 64,
        excerpt=excerpt,
        excerpt_file_sha256="b" * 64,
        focus="Follow the intended lead melody",
        candidate_media=media,
    )
    review = copy.deepcopy(seed)
    review["status"] = "reviewed"
    review["reviewed_at"] = "2026-08-02T12:00:00+00:00"
    review["choices"][0].update(
        heard_reference=True,
        heard_candidate=True,
        disposition="useful_for_focus",
    )
    review["choices"][1]["disposition"] = "cannot_tell"

    with pytest.raises(ValueError, match="no-note candidate"):
        audition._verify_review_document(seed, review)


def test_loopback_server_serves_verified_range_and_writes_nothing(
    tmp_path: Path,
) -> None:
    inventory, excerpt, media = _evidence(tmp_path)
    seed = audition._review_seed(
        inventory,
        candidate_set_file_sha256="a" * 64,
        excerpt=excerpt,
        excerpt_file_sha256="b" * 64,
        focus="Follow the intended lead melody",
        candidate_media=media,
    )
    context = audition._AuditionContext(
        candidate_set_path=tmp_path / "inventory.json",
        candidate_set_file_sha256="a" * 64,
        candidate_set=inventory,
        excerpt_path=tmp_path / "excerpt.json",
        excerpt_file_sha256="b" * 64,
        excerpt=excerpt,
        focus="Follow the intended lead melody",
        seed=seed,
        candidate_media=media,
    )
    server = audition._VocalCandidateAuditionServer(context)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(server.url) as response:
            html = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Cache-Control"] == "no-store"
            assert "Private local developer audition" in html
            assert "Playback, seeking, looping and dwell time" in html
            assert "Export reviewed JSON" in html
            assert "localStorage" not in html
            assert str(tmp_path) not in html

        media_url = (
            f"http://127.0.0.1:{server.server_port}"
            + server.candidate_urls["candidate-1"]["candidate"]
        )
        request = urllib.request.Request(media_url, headers={"Range": "bytes=2-5"})
        with urllib.request.urlopen(request) as response:
            assert response.status == 206
            assert response.headers["Content-Range"] == "bytes 2-5/13"
            assert response.read() == b"FFND"

        with pytest.raises(urllib.error.HTTPError) as forbidden:
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/?token=wrong"
            )
        assert forbidden.value.code == 403

        post = urllib.request.Request(server.url, data=b"ignored", method="POST")
        with pytest.raises(urllib.error.HTTPError) as not_allowed:
            urllib.request.urlopen(post)
        assert not_allowed.value.code == 405
        assert set(tmp_path.rglob("*")) == {
            tmp_path / "preview.wav",
            tmp_path / "reference.wav",
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_loopback_server_fails_closed_after_media_change(tmp_path: Path) -> None:
    inventory, excerpt, media = _evidence(tmp_path)
    seed = audition._review_seed(
        inventory,
        candidate_set_file_sha256="a" * 64,
        excerpt=excerpt,
        excerpt_file_sha256="b" * 64,
        focus="Follow the intended lead melody",
        candidate_media=media,
    )
    context = audition._AuditionContext(
        candidate_set_path=tmp_path / "inventory.json",
        candidate_set_file_sha256="a" * 64,
        candidate_set=inventory,
        excerpt_path=tmp_path / "excerpt.json",
        excerpt_file_sha256="b" * 64,
        excerpt=excerpt,
        focus="Follow the intended lead melody",
        seed=seed,
        candidate_media=media,
    )
    server = audition._VocalCandidateAuditionServer(context)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        (tmp_path / "preview.wav").write_bytes(b"changed bytes")
        url = (
            f"http://127.0.0.1:{server.server_port}"
            + server.candidate_urls["candidate-1"]["candidate"]
        )
        with pytest.raises(urllib.error.HTTPError) as changed:
            urllib.request.urlopen(url)
        assert changed.value.code == 409
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_descriptor_walk_rejects_intermediate_symlink(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    outside = tmp_path / "outside"
    trusted.mkdir()
    outside.mkdir()
    payload = outside / "candidate.wav"
    payload.write_bytes(b"RIFFoutside")
    (trusted / "nested").symlink_to(outside, target_is_directory=True)
    media = audition._VerifiedMedia(
        root=trusted,
        relative_path="nested/candidate.wav",
        sha256=hashlib.sha256(payload.read_bytes()).hexdigest(),
        size=payload.stat().st_size,
        label="candidate preview",
    )

    with pytest.raises(OSError):
        audition._open_verified_media(media)


@pytest.mark.parametrize(
    ("raw", "size", "expected"),
    [
        ("bytes=0-3", 10, (0, 3)),
        ("bytes=4-", 10, (4, 9)),
        ("bytes=-3", 10, (7, 9)),
        ("bytes=9-99", 10, (9, 9)),
        ("bytes=10-", 10, None),
        ("items=0-1", 10, None),
        ("bytes=0-1,4-5", 10, None),
    ],
)
def test_single_byte_range(raw: str, size: int, expected) -> None:
    assert audition._single_byte_range(raw, size) == expected


def test_resolution_is_fresh_private_and_never_selects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = _three_available_seed()
    review = copy.deepcopy(seed)
    review["status"] = "reviewed"
    review["reviewed_at"] = "2026-08-02T12:00:00+00:00"
    for index, row in enumerate(review["choices"]):
        row.update(
            heard_reference=True,
            heard_candidate=True,
            disposition="useful_for_focus" if index == 0 else "not_useful_for_focus",
        )
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    inventory = {"document_sha256": "c" * 64}
    excerpt = {"document_sha256": "d" * 64}
    context = audition._AuditionContext(
        candidate_set_path=tmp_path / "inventory.json",
        candidate_set_file_sha256="a" * 64,
        candidate_set=inventory,
        excerpt_path=tmp_path / "excerpt.json",
        excerpt_file_sha256="b" * 64,
        excerpt=excerpt,
        focus=seed["focus"],
        seed=seed,
        candidate_media={},
    )
    monkeypatch.setattr(audition, "_load_audition_context", lambda *a, **k: context)
    monkeypatch.setattr(audition, "_reverify_context", lambda _: None)
    output = tmp_path / "resolution.json"

    result = audition._resolve_vocal_candidate_review(
        review_path,
        tmp_path / "inventory.json",
        tmp_path / "mel.json",
        tmp_path / "leaf.json",
        tmp_path / "phrase.json",
        tmp_path / "excerpt.json",
        focus=seed["focus"],
        out=output,
    )

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["document_sha256"] == audition._document_sha256(persisted)
    assert persisted["results"]["useful_for_focus"] == ["candidate-1"]
    assert persisted["policy"]["winner_selected"] is False
    assert persisted["effects"]["candidate_selected"] is False
    assert result["report"] == str(output)
    assert output.stat().st_mode & 0o777 == 0o600

    with pytest.raises(FileExistsError):
        audition._resolve_vocal_candidate_review(
            review_path,
            tmp_path / "inventory.json",
            tmp_path / "mel.json",
            tmp_path / "leaf.json",
            tmp_path / "phrase.json",
            tmp_path / "excerpt.json",
            focus=seed["focus"],
            out=output,
        )


def test_private_audition_has_no_public_route() -> None:
    command = "private-vocal-candidate-audition"
    assert command not in PUBLIC_COMMANDS
    assert command not in DIRECT_TUI_COMMANDS
    assert audition.__all__ == ()


def _evidence(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[str, str], dict[str, tuple[object, object | None]]]:
    preview_path = tmp_path / "preview.wav"
    reference_path = tmp_path / "reference.wav"
    preview_path.write_bytes(b"RIFFNDID-TEST")
    reference_path.write_bytes(b"RIFFREFERENCE")
    preview = audition._VerifiedMedia(
        root=tmp_path,
        relative_path=preview_path.name,
        sha256=hashlib.sha256(preview_path.read_bytes()).hexdigest(),
        size=preview_path.stat().st_size,
        label="candidate preview",
    )
    reference = audition._VerifiedMedia(
        root=tmp_path,
        relative_path=reference_path.name,
        sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
        size=reference_path.stat().st_size,
        label="source reference",
    )
    inventory = {
        "document_sha256": "c" * 64,
        "summary": {
            "candidate_count": 2,
            "audition_available_count": 1,
            "no_note_evidence_count": 1,
            "family_counts": {"kim_primary": 2},
            "provider_leaf_counts": {},
        },
        "candidates": [
            {
                "candidate_id": "candidate-1",
                "family": "kim_primary",
                "provider_group": None,
                "leaf_id": None,
                "adapter": None,
                "variant": "primary",
                "note_count": 4,
                "audition_state": "available",
            },
            {
                "candidate_id": "candidate-zero",
                "family": "kim_primary",
                "provider_group": None,
                "leaf_id": None,
                "adapter": None,
                "variant": "zero",
                "note_count": 0,
                "audition_state": "no_note_evidence",
            },
        ],
    }
    excerpt = {"document_sha256": "d" * 64}
    media = {
        "candidate-1": (preview, reference),
        "candidate-zero": (None, None),
    }
    return inventory, excerpt, media


def _three_available_seed() -> dict[str, object]:
    choices = []
    for index in range(1, 4):
        choices.append(
            {
                "candidate_id": f"candidate-{index}",
                "family": "kim_register",
                "provider_group": None,
                "leaf_id": None,
                "adapter": None,
                "variant": f"variant-{index}",
                "note_count": index,
                "audition_state": "available",
                "candidate_render": {"sha256": str(index) * 64, "bytes": index},
                "source_reference": {
                    "kind": "original_mixed_excerpt",
                    "sha256": "f" * 64,
                    "bytes": 10,
                },
                "heard_reference": False,
                "heard_candidate": False,
                "disposition": "",
                "notes": "",
            }
        )
    seed = {
        "schema": audition.REVIEW_SCHEMA,
        "status": "unreviewed",
        "reviewed_at": None,
        "evidence_scope": "private_development_only",
        "inputs": {},
        "focus": "Follow the intended lead melody",
        "policy": {},
        "summary": {"candidate_count": 3, "audition_available_count": 3},
        "choices": choices,
        "effects": {},
    }
    seed["document_sha256"] = audition._document_sha256(seed)
    return seed


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False
