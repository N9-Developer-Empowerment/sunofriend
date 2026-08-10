"""Shared, side-effect-bounded transport for localhost separation reviews.

Review schemas and musical decisions belong to their individual review modules.
This module owns only the repeated HTTP and atomic-file mechanics needed to
serve already-verified local artifacts and persist validated JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping


MAX_REVIEW_JSON_BYTES = 1_000_000
_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


class ReviewRequestError(ValueError):
    """A bounded client error that can be returned without a server traceback."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class FileRange:
    """One validated inclusive byte range for a local file response."""

    start: int
    end: int
    partial: bool

    @property
    def length(self) -> int:
        return max(0, self.end - self.start + 1)


def parse_file_range(header: str | None, *, size: int) -> FileRange:
    """Parse the single-range subset used by browser audio elements.

    Multiple ranges are deliberately unsupported. Invalid or unsatisfiable
    values raise ``ReviewRequestError`` with HTTP status 416.
    """

    if size < 0:
        raise ValueError("file size must be non-negative")
    if header is None:
        return FileRange(start=0, end=size - 1, partial=False)
    match = _RANGE.fullmatch(header.strip())
    if match is None or (not match.group(1) and not match.group(2)) or size == 0:
        raise ReviewRequestError(416, "requested byte range is not satisfiable")

    first, last = match.groups()
    if first:
        start = int(first)
        end = int(last) if last else size - 1
        if start >= size or end < start:
            raise ReviewRequestError(416, "requested byte range is not satisfiable")
        end = min(end, size - 1)
    else:
        suffix = int(last)
        if suffix <= 0:
            raise ReviewRequestError(416, "requested byte range is not satisfiable")
        start = max(0, size - suffix)
        end = size - 1
    return FileRange(start=start, end=end, partial=True)


def encode_review_json(value: Mapping[str, Any]) -> bytes:
    """Return the stable private-review JSON representation used by all pages."""

    return (
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def atomic_write_private_json(path: Path, value: Mapping[str, Any]) -> bytes:
    """Atomically persist validated JSON with owner-only permissions.

    A unique temporary file avoids concurrent autosave collisions. The target
    directory must already exist so this helper cannot expand publication
    scope by creating a new evidence tree.
    """

    destination = Path(path)
    if not destination.parent.is_dir():
        raise ValueError("review destination directory does not exist")
    payload = encode_review_json(value)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            os.chmod(handle.name, 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return payload


class LocalReviewRequestHandler(BaseHTTPRequestHandler):
    """Reusable no-cache HTTP mechanics for localhost-only review servers."""

    def read_review_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError as error:
            raise ReviewRequestError(400, "Content-Length must be an integer") from error
        if length <= 0 or length > MAX_REVIEW_JSON_BYTES:
            raise ReviewRequestError(413, "review JSON size is outside the allowed range")
        payload = self.rfile.read(length)
        if len(payload) != length:
            raise ReviewRequestError(400, "review JSON body is incomplete")
        try:
            value = json.loads(payload)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ReviewRequestError(400, f"invalid review JSON: {error}") from error
        if not isinstance(value, dict):
            raise ReviewRequestError(400, "review JSON must be an object")
        return value

    def send_no_store(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_review_error(self, error: Exception, *, status: int = 400) -> None:
        if isinstance(error, ReviewRequestError):
            status = error.status
        body = json.dumps({"error": str(error)}, allow_nan=False).encode("utf-8")
        self.send_no_store(status, "application/json", body)

    def send_attachment(
        self,
        body: bytes,
        *,
        filename: str,
        content_type: str = "application/json",
    ) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_ranged_file(
        self,
        path: Path,
        content_type: str,
        *,
        body: bool = True,
    ) -> None:
        size = path.stat().st_size
        try:
            selected = parse_file_range(self.headers.get("Range"), size=size)
        except ReviewRequestError as error:
            self.send_response(error.status)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return

        self.send_response(206 if selected.partial else 200)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(selected.length))
        if selected.partial:
            self.send_header(
                "Content-Range",
                f"bytes {selected.start}-{selected.end}/{size}",
            )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not body or self.command == "HEAD" or selected.length == 0:
            return
        with path.open("rb") as handle:
            handle.seek(selected.start)
            remaining = selected.length
            while remaining:
                block = handle.read(min(1024 * 1024, remaining))
                if not block:
                    break
                if not self._write_client_bytes(block):
                    return
                remaining -= len(block)

    def _write_client_bytes(self, body: bytes) -> bool:
        """Return false when a browser abandons an in-flight media range."""

        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return False
        return True

    def log_message(self, _format: str, *_args: Any) -> None:
        return


__all__ = [
    "FileRange",
    "LocalReviewRequestHandler",
    "MAX_REVIEW_JSON_BYTES",
    "ReviewRequestError",
    "atomic_write_private_json",
    "encode_review_json",
    "parse_file_range",
]
