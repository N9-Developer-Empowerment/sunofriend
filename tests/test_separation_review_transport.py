from __future__ import annotations

import http.client
from io import BytesIO
import json
import os
import threading

import pytest

from sunofriend.separation_review_transport import (
    LocalReviewApplication,
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


def test_local_review_application_composes_standard_transport_routes(tmp_path) -> None:
    media = tmp_path / "clip.wav"
    media.write_bytes(b"0123456789")
    result_path = tmp_path / "review.json"
    validated_values: list[dict[str, object]] = []

    def validate_review(value: dict[str, object]) -> dict[str, object]:
        validated_values.append(value)
        if value.get("answer") == "reject":
            raise ValueError("review answer was rejected")
        return {"answer": value["answer"], "validated": True}

    application = LocalReviewApplication(
        server_version="SunofriendTestReview/1",
        page=b"<h1>Review</h1>",
        page_path="/REVIEW/test.html",
        result_path=result_path,
        download_filename="sunofriend-test-review.json",
        media_routes={"/audio/clip.wav": (media, "audio/wav")},
        validate_review=validate_review,
        download_content_type="application/vnd.sunofriend.review+json",
    )

    with pytest.raises(ValueError, match="review server must bind to localhost"):
        application.build_server(host="0.0.0.0", port=0)

    server = application.build_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)

        connection.request("GET", "/REVIEW/test.html?fresh=1")
        page = connection.getresponse()
        assert page.status == 200
        assert page.getheader("Server").startswith("SunofriendTestReview/1")
        assert page.getheader("Content-Type") == "text/html; charset=utf-8"
        assert page.getheader("Cache-Control") == "no-store"
        assert page.read() == b"<h1>Review</h1>"

        connection.request("GET", "/")
        root_page = connection.getresponse()
        assert root_page.status == 200
        assert root_page.read() == b"<h1>Review</h1>"

        connection.request("GET", "/healthz")
        health = connection.getresponse()
        assert health.status == 200
        assert health.getheader("Content-Type") == "application/json"
        assert health.getheader("Cache-Control") == "no-store"
        assert health.read() == b'{"status":"ok"}\n'

        connection.request("GET", "/saved-result")
        missing = connection.getresponse()
        assert missing.status == 404
        missing.read()

        connection.request("GET", "/download-review")
        missing_download = connection.getresponse()
        assert missing_download.status == 404
        missing_download.read()

        connection.request("HEAD", "/REVIEW/test.html")
        head_page = connection.getresponse()
        assert head_page.status == 404
        head_page.read()

        connection.request(
            "HEAD",
            "/audio/clip.wav?fresh=1",
            headers={"Range": "bytes=2-5"},
        )
        head = connection.getresponse()
        assert head.status == 206
        assert head.getheader("Content-Type") == "audio/wav"
        assert head.getheader("Content-Range") == "bytes 2-5/10"
        assert head.getheader("Content-Length") == "4"
        assert head.read() == b""

        connection.request(
            "GET",
            "/audio/clip.wav",
            headers={"Range": "bytes=2-5"},
        )
        ranged = connection.getresponse()
        assert ranged.status == 206
        assert ranged.getheader("Content-Type") == "audio/wav"
        assert ranged.read() == b"2345"

        connection.request("POST", "/not-save-review", body=b"{}")
        wrong_route = connection.getresponse()
        assert wrong_route.status == 404
        wrong_route.read()

        connection.request(
            "POST",
            "/save-review",
            body=json.dumps({"answer": "reject"}),
            headers={"Content-Type": "application/json"},
        )
        rejected = connection.getresponse()
        assert rejected.status == 400
        assert rejected.getheader("Content-Type") == "application/json"
        assert json.loads(rejected.read()) == {
            "error": "review answer was rejected"
        }

        request_value = {"answer": "present"}
        connection.request(
            "POST",
            "/save-review",
            body=json.dumps(request_value),
            headers={"Content-Type": "application/json"},
        )
        saved = connection.getresponse()
        expected = encode_review_json({"answer": "present", "validated": True})
        assert saved.status == 200
        assert saved.getheader("Content-Type") == "application/json"
        assert saved.getheader("Cache-Control") == "no-store"
        assert saved.read() == expected
        assert validated_values == [
            {"answer": "reject"},
            request_value,
        ]
        assert result_path.read_bytes() == expected
        assert os.stat(result_path).st_mode & 0o777 == 0o600

        connection.request("GET", "/saved-result")
        persisted = connection.getresponse()
        assert persisted.status == 200
        assert persisted.getheader("Content-Type") == "application/json"
        assert persisted.getheader("Cache-Control") == "no-store"
        assert persisted.read() == expected

        connection.request("GET", "/download-review")
        download = connection.getresponse()
        assert download.status == 200
        assert download.getheader("Content-Disposition") == (
            'attachment; filename="sunofriend-test-review.json"'
        )
        assert download.getheader("Content-Type") == (
            "application/vnd.sunofriend.review+json"
        )
        assert download.getheader("Cache-Control") == "no-store"
        assert download.read() == expected
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
