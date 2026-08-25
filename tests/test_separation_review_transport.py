from __future__ import annotations

from io import BytesIO
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


def _handler(
    *,
    headers: dict[str, str] | None = None,
    payload: bytes = b"",
    command: str = "GET",
):
    handler = LocalReviewRequestHandler.__new__(LocalReviewRequestHandler)
    handler.headers = headers or {}
    handler.rfile = BytesIO(payload)
    handler.wfile = BytesIO()
    handler.command = command
    responses: list[int] = []
    response_headers: list[tuple[str, str]] = []
    ended: list[bool] = []
    handler.send_response = responses.append
    handler.send_header = lambda name, value: response_headers.append((name, value))
    handler.end_headers = lambda: ended.append(True)
    return handler, responses, response_headers, ended


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
    with pytest.raises(ValueError) as caught:
        parse_file_range(None, size=-1)
    assert str(caught.value) == "file size must be non-negative"


def test_review_request_error_preserves_status_and_message() -> None:
    error = ReviewRequestError(416, "requested byte range is not satisfiable")

    assert error.status == 416
    assert str(error) == "requested byte range is not satisfiable"


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


def test_read_review_json_accepts_one_complete_object() -> None:
    payload = b'{"answer":"present"}'
    handler, _, _, _ = _handler(
        headers={"Content-Length": str(len(payload))},
        payload=payload,
    )

    assert handler.read_review_json() == {"answer": "present"}


@pytest.mark.parametrize(
    ("headers", "payload", "status", "message"),
    [
        ({"Content-Length": "not-an-integer"}, b"", 400, "Content-Length must be an integer"),
        ({"Content-Length": "0"}, b"", 413, "review JSON size is outside the allowed range"),
        ({"Content-Length": "1000001"}, b"", 413, "review JSON size is outside the allowed range"),
        ({"Content-Length": "4"}, b"{}", 400, "review JSON body is incomplete"),
        ({"Content-Length": "1"}, b"{", 400, "invalid review JSON:"),
        ({"Content-Length": "2"}, b"[]", 400, "review JSON must be an object"),
    ],
)
def test_read_review_json_rejects_bounded_client_errors(
    headers: dict[str, str],
    payload: bytes,
    status: int,
    message: str,
) -> None:
    handler, _, _, _ = _handler(headers=headers, payload=payload)

    with pytest.raises(ReviewRequestError) as caught:
        handler.read_review_json()

    assert caught.value.status == status
    assert message in str(caught.value)


@pytest.mark.parametrize("command", ["GET", "HEAD"])
def test_send_no_store_sets_exact_headers_and_head_has_no_body(command: str) -> None:
    handler, responses, response_headers, ended = _handler(command=command)

    handler.send_no_store(201, "text/plain", b"hello")

    assert responses == [201]
    assert response_headers == [
        ("Content-Type", "text/plain"),
        ("Content-Length", "5"),
        ("Cache-Control", "no-store"),
    ]
    assert ended == [True]
    assert handler.wfile.getvalue() == (b"hello" if command == "GET" else b"")


def test_send_review_error_uses_bounded_status_and_json() -> None:
    handler, responses, response_headers, _ = _handler()

    handler.send_review_error(ReviewRequestError(413, "too large"))

    assert responses == [413]
    assert ("Content-Type", "application/json") in response_headers
    assert json.loads(handler.wfile.getvalue()) == {"error": "too large"}


@pytest.mark.parametrize("command", ["GET", "HEAD"])
def test_send_attachment_sets_exact_headers_and_head_has_no_body(command: str) -> None:
    handler, responses, response_headers, ended = _handler(command=command)

    handler.send_attachment(b"{}\n", filename="review.json")

    assert responses == [200]
    assert response_headers == [
        ("Content-Type", "application/json"),
        ("Content-Disposition", 'attachment; filename="review.json"'),
        ("Content-Length", "3"),
        ("Cache-Control", "no-store"),
    ]
    assert ended == [True]
    assert handler.wfile.getvalue() == (b"{}\n" if command == "GET" else b"")


def test_send_ranged_file_serves_exact_bytes_and_rejects_bad_range(tmp_path) -> None:
    media = tmp_path / "clip.wav"
    media.write_bytes(b"0123456789")
    handler, responses, response_headers, _ = _handler(
        headers={"Range": "bytes=2-5"}
    )

    handler.send_ranged_file(media, "audio/wav")

    assert responses == [206]
    assert response_headers == [
        ("Content-Type", "audio/wav"),
        ("Accept-Ranges", "bytes"),
        ("Content-Length", "4"),
        ("Content-Range", "bytes 2-5/10"),
        ("Cache-Control", "no-store"),
    ]
    assert handler.wfile.getvalue() == b"2345"

    invalid, invalid_responses, invalid_headers, _ = _handler(
        headers={"Range": "bytes=20-"}
    )
    invalid.send_ranged_file(media, "audio/wav")
    assert invalid_responses == [416]
    assert invalid_headers == [
        ("Content-Range", "bytes */10"),
        ("Content-Length", "0"),
        ("Cache-Control", "no-store"),
    ]
    assert invalid.wfile.getvalue() == b""


@pytest.mark.parametrize(("command", "body"), [("HEAD", True), ("GET", False)])
def test_send_ranged_file_can_suppress_body(
    tmp_path,
    command: str,
    body: bool,
) -> None:
    media = tmp_path / "clip.wav"
    media.write_bytes(b"audio")
    handler, responses, response_headers, _ = _handler(command=command)

    handler.send_ranged_file(media, "audio/wav", body=body)

    assert responses == [200]
    assert ("Content-Length", "5") in response_headers
    assert handler.wfile.getvalue() == b""
