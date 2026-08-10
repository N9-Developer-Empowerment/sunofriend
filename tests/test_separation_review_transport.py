from __future__ import annotations

import json
import os

import pytest

from sunofriend.separation_review_transport import (
    LocalReviewRequestHandler,
    ReviewRequestError,
    atomic_write_private_json,
    encode_review_json,
    parse_file_range,
)


class _DisconnectedWriter:
    def __init__(self, error: OSError) -> None:
        self.error = error

    def write(self, _body: bytes) -> None:
        raise self.error


@pytest.mark.parametrize(
    ("header", "size", "expected"),
    [
        (None, 10, (0, 9, False, 10)),
        ("bytes=2-5", 10, (2, 5, True, 4)),
        ("bytes=7-", 10, (7, 9, True, 3)),
        ("bytes=-3", 10, (7, 9, True, 3)),
        ("bytes=-30", 10, (0, 9, True, 10)),
        ("bytes=2-50", 10, (2, 9, True, 8)),
        (None, 0, (0, -1, False, 0)),
    ],
)
def test_parse_file_range_accepts_browser_single_ranges(
    header: str | None,
    size: int,
    expected: tuple[int, int, bool, int],
) -> None:
    result = parse_file_range(header, size=size)
    assert (result.start, result.end, result.partial, result.length) == expected


@pytest.mark.parametrize(
    ("header", "size"),
    [
        ("bytes=", 10),
        ("bytes=-0", 10),
        ("bytes=10-", 10),
        ("bytes=7-3", 10),
        ("bytes=1-2,4-5", 10),
        ("items=1-2", 10),
        ("bytes=0-0", 0),
    ],
)
def test_parse_file_range_rejects_invalid_or_unsatisfiable_ranges(
    header: str,
    size: int,
) -> None:
    with pytest.raises(ReviewRequestError) as caught:
        parse_file_range(header, size=size)
    assert caught.value.status == 416


def test_parse_file_range_rejects_negative_file_size() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        parse_file_range(None, size=-1)


def test_atomic_write_private_json_is_stable_and_owner_only(tmp_path) -> None:
    destination = tmp_path / "review.json"
    value = {"schema": "example.v1", "answer": "cannot_tell"}

    payload = atomic_write_private_json(destination, value)

    assert payload == encode_review_json(value)
    assert destination.read_bytes() == payload
    assert json.loads(payload) == value
    assert os.stat(destination).st_mode & 0o777 == 0o600
    assert list(tmp_path.glob(".review.json.*.tmp")) == []

    replacement = {"schema": "example.v1", "answer": "present"}
    second = atomic_write_private_json(destination, replacement)
    assert destination.read_bytes() == second == encode_review_json(replacement)
    assert list(tmp_path.glob(".review.json.*.tmp")) == []


def test_atomic_write_private_json_refuses_to_create_evidence_tree(tmp_path) -> None:
    destination = tmp_path / "missing" / "review.json"
    with pytest.raises(ValueError, match="directory does not exist"):
        atomic_write_private_json(destination, {"answer": "present"})
    assert not destination.parent.exists()


def test_encode_review_json_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="Out of range float"):
        encode_review_json({"score": float("nan")})


@pytest.mark.parametrize("error", [BrokenPipeError(), ConnectionResetError()])
def test_review_media_stream_treats_browser_disconnect_as_normal(error: OSError) -> None:
    handler = LocalReviewRequestHandler.__new__(LocalReviewRequestHandler)
    handler.wfile = _DisconnectedWriter(error)

    assert handler._write_client_bytes(b"audio") is False
