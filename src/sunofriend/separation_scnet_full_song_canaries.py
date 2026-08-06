"""Run the three approval-bound, local-only SCNet full-song canaries."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import time
from typing import Any, Mapping, Sequence

from .audio_formats import (
    DEFAULT_AUDIO_IMPORT_LIMITS,
    file_sha256,
    resolve_executable,
    validate_local_source_path,
)
from .core_four_approval import (
    PROFILE_ID,
    SCOPE_ID,
    resolve_core_four_approved_songs,
    validate_core_four_approval_document,
)
from .separation_profiles import SCNET_RELEASE_PROFILE_ID, separation_profile
from .separation_scnet_canary import DEFAULT_PROFILE_ROOT
from .separation_scnet_worker import (
    MAXIMUM_SECONDS_PER_AUDIO_MINUTE,
    MAXIMUM_SECONDS_PER_SONG,
)


RUN_SCHEMA = "sunofriend.scnet-approved-full-song-canaries.v1"
CANARY_SCHEMA = "sunofriend.scnet-approved-full-song-canary.v1"
LISTEN_SCHEMA = "sunofriend.scnet-canary-catastrophic-listen.v1"
MAXIMUM_LISTEN_DOCUMENT_BYTES = 64 * 1024
OUTPUT_PATHS = {
    "source_reference": "SOURCE/source-reference.wav",
    "vocals": "STEMS/vocals.wav",
    "drums": "STEMS/drums.wav",
    "bass": "STEMS/bass.wav",
    "other": "STEMS/other.wav",
    "reconstruction_check": "AUDIO/reconstruction-check.wav",
}


def build_canary_review_server(
    root: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8766,
) -> ThreadingHTTPServer:
    """Serve the exact canary page and audio set on localhost only."""

    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("SCNet canary review server must bind to localhost")
    evidence = Path(root).expanduser().resolve(strict=True)
    run = json.loads((evidence / "CANARY-RUN.json").read_text(encoding="utf-8"))
    if (
        run.get("schema") != RUN_SCHEMA
        or run.get("profile_id") != SCNET_RELEASE_PROFILE_ID
        or run.get("objective_gates_passed") is not True
    ):
        raise ValueError("SCNet canary run receipt is invalid")
    page = render_canary_listen_html(run).encode("utf-8")
    audio_paths: dict[str, Path] = {}
    for canary in run.get("canaries", []):
        coverage = canary.get("coverage_id")
        if coverage not in {"vocal_forward", "dense_electronic", "acoustic_mixed"}:
            raise ValueError("SCNet canary coverage set differs")
        canary_root = evidence / "CANARIES" / coverage
        for role, relative in OUTPUT_PATHS.items():
            path = canary_root / relative
            if not path.is_file():
                raise FileNotFoundError(f"SCNet canary audio is missing: {path}")
            audio_paths[f"{coverage}/{role}.wav"] = path
    if len(audio_paths) != 18:
        raise ValueError("SCNet canary review must expose exactly 18 audio files")

    class ReviewHandler(BaseHTTPRequestHandler):
        server_version = "SunofriendCanaryReview/1"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            self._serve(send_body=True)

        def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
            self._serve(send_body=False)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            route = self.path.partition("?")[0]
            if route != "/review":
                self.send_error(405, "This local review accepts no submission here")
                return
            self._save_review()

        def _save_review(self) -> None:
            if self.headers.get("Transfer-Encoding"):
                self.send_error(400, "Chunked review documents are not accepted")
                return
            content_type = self.headers.get("Content-Type", "").partition(";")[0]
            try:
                content_length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                content_length = -1
            if content_type.strip().lower() != "application/json":
                self.send_error(415, "Review document must be JSON")
                return
            if content_length < 2 or content_length > MAXIMUM_LISTEN_DOCUMENT_BYTES:
                self.send_error(413, "Review document size is invalid")
                return
            raw = self.rfile.read(content_length)
            if len(raw) != content_length:
                self.send_error(400, "Review document is incomplete")
                return
            try:
                document = json.loads(
                    raw,
                    parse_constant=lambda value: (_ for _ in ()).throw(
                        ValueError(f"invalid JSON constant: {value}")
                    ),
                )
                if not isinstance(document, Mapping):
                    raise ValueError("review document must be an object")
                validated = validate_canary_listen_document(document, run=run)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self._json_response(
                    status=422,
                    value={"status": "not_saved", "error": str(exc)},
                )
                return

            target = evidence / "REVIEW" / "canary-listen-complete.json"
            if os.path.lexists(target):
                self._json_response(
                    status=409,
                    value={
                        "status": "already_recorded",
                        "path": "REVIEW/canary-listen-complete.json",
                        "sha256": file_sha256(target) if target.is_file() else None,
                    },
                )
                return
            temporary = target.with_name(
                f".{target.name}.browser-save-{os.getpid()}-{id(self)}"
            )
            try:
                descriptor = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
                    json.dump(
                        validated,
                        destination,
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    destination.write("\n")
                    destination.flush()
                    os.fsync(destination.fileno())
                os.link(temporary, target)
            except FileExistsError:
                self._json_response(
                    status=409,
                    value={
                        "status": "already_recorded",
                        "path": "REVIEW/canary-listen-complete.json",
                    },
                )
                return
            finally:
                temporary.unlink(missing_ok=True)
            self._json_response(
                status=201,
                value={
                    "status": "recorded_and_validated",
                    "path": "REVIEW/canary-listen-complete.json",
                    "sha256": file_sha256(target),
                    "audio_included": False,
                    "telemetry_included": False,
                },
            )

        def _json_response(self, *, status: int, value: Mapping[str, Any]) -> None:
            body = (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode(
                "utf-8"
            )
            self._headers(
                status=status,
                content_type="application/json; charset=utf-8",
                content_length=len(body),
            )
            self.wfile.write(body)

        def _serve(self, *, send_body: bool) -> None:
            route = self.path.partition("?")[0]
            if route in {"/", "/index.html"}:
                self._headers(
                    status=200,
                    content_type="text/html; charset=utf-8",
                    content_length=len(page),
                )
                if send_body:
                    self.wfile.write(page)
                return
            if route == "/healthz":
                body = b'{"status":"ok","network_scope":"localhost_only"}\n'
                self._headers(
                    status=200,
                    content_type="application/json; charset=utf-8",
                    content_length=len(body),
                )
                if send_body:
                    self.wfile.write(body)
                return
            audio_route = route.removeprefix("/audio/")
            path = audio_paths.get(audio_route) if route.startswith("/audio/") else None
            if path is None:
                self.send_error(404, "Not found")
                return
            self._serve_audio(path, send_body=send_body)

        def _serve_audio(self, path: Path, *, send_body: bool) -> None:
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            range_header = self.headers.get("Range")
            if range_header:
                import re

                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
                if match is None or (not match.group(1) and not match.group(2)):
                    self.send_error(416, "Invalid byte range")
                    return
                if match.group(1):
                    start = int(match.group(1))
                    end = int(match.group(2)) if match.group(2) else end
                else:
                    start = max(0, size - int(match.group(2)))
                if start >= size or end < start:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                end, status = min(end, size - 1), 206
            length = end - start + 1
            self._headers(
                status=status,
                content_type="audio/wav",
                content_length=length,
                content_range=(
                    f"bytes {start}-{end}/{size}" if status == 206 else None
                ),
            )
            if not send_body:
                return
            with path.open("rb") as source:
                source.seek(start)
                remaining = length
                while remaining:
                    chunk = source.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    remaining -= len(chunk)

        def _headers(
            self,
            *,
            status: int,
            content_type: str,
            content_length: int,
            content_range: str | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(content_length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Accept-Ranges", "bytes")
            if content_range is not None:
                self.send_header("Content-Range", content_range)
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), ReviewHandler)


def validate_canary_listen_document(
    document: Mapping[str, Any], *, run: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate a downloaded three-song catastrophic-listen record."""

    expected = {
        "schema": LISTEN_SCHEMA,
        "run_schema": run.get("schema"),
        "approval_id": run.get("approval", {}).get("approval_id"),
        "approval_sha256": run.get("approval", {}).get("sha256"),
        "profile_id": run.get("profile_id"),
        "scope_id": run.get("scope_id"),
    }
    if any(document.get(key) != value for key, value in expected.items()):
        raise ValueError("SCNet canary listen binding differs")
    songs = document.get("songs")
    if not isinstance(songs, list) or len(songs) != 3:
        raise ValueError("SCNet canary listen must contain three songs")
    expected_coverage = {item["coverage_id"] for item in run.get("canaries", [])}
    observed: set[str] = set()
    for song in songs:
        if not isinstance(song, Mapping):
            raise ValueError("SCNet canary listen song is invalid")
        coverage = song.get("coverage_id")
        details = song.get("details")
        if (
            coverage not in expected_coverage
            or song.get("complete") is not True
            or song.get("result")
            not in {"no_catastrophic_defect", "catastrophic_defect_reported"}
            or not isinstance(details, str)
            or len(details) > 5_000
            or song.get("minimum_usefulness_rating") is not None
        ):
            raise ValueError("SCNet canary listen song decision is invalid")
        if song["result"] == "catastrophic_defect_reported" and not details.strip():
            raise ValueError("SCNet catastrophic defect requires details")
        observed.add(str(coverage))
    if observed != expected_coverage:
        raise ValueError("SCNet canary listen coverage differs")
    if (
        document.get("status") != "complete"
        or document.get("missing_fields") != []
        or document.get("audio_included") is not False
        or document.get("telemetry_included") is not False
        or not isinstance(document.get("exported_at"), str)
        or not document["exported_at"]
    ):
        raise ValueError("SCNet canary listen export is incomplete")
    return dict(document)


def record_no_failure_canary_listen(
    root: str | Path,
    output: str | Path,
    *,
    reviewed_by: str,
    explicit_statement: str,
) -> dict[str, Any]:
    """Record an explicit human no-failure report when browser export failed."""

    evidence = Path(root).expanduser().resolve(strict=True)
    run = json.loads((evidence / "CANARY-RUN.json").read_text(encoding="utf-8"))
    target = Path(output).expanduser().absolute()
    identity = reviewed_by.strip()
    statement = explicit_statement.strip()
    if not identity or len(identity) > 200:
        raise ValueError("SCNet canary reviewer identity is missing or invalid")
    if not statement or len(statement) > 5_000:
        raise ValueError("SCNet explicit review statement is missing or invalid")
    if os.path.lexists(target):
        raise FileExistsError(f"SCNet canary listen record already exists: {target}")
    document = {
        "schema": LISTEN_SCHEMA,
        "run_schema": run["schema"],
        "approval_id": run["approval"]["approval_id"],
        "approval_sha256": run["approval"]["sha256"],
        "profile_id": run["profile_id"],
        "scope_id": run["scope_id"],
        "status": "complete",
        "reviewed_by": identity,
        "recording_method": "explicit_user_statement_after_local_web_review",
        "explicit_statement": statement,
        "browser_download_succeeded": False,
        "songs": [
            {
                "coverage_id": item["coverage_id"],
                "complete": True,
                "result": "no_catastrophic_defect",
                "details": "Recorded from the reviewer's explicit no-failure statement.",
                "minimum_usefulness_rating": None,
            }
            for item in run["canaries"]
        ],
        "missing_fields": [],
        "audio_included": False,
        "telemetry_included": False,
        "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    validated = validate_canary_listen_document(document, run=run)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.building-{os.getpid()}")
    try:
        _write_json(temporary, validated)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "status": "recorded_and_validated",
        "path": str(target),
        "sha256": file_sha256(target),
        "reviewed_by": identity,
        "results": {item["coverage_id"]: item["result"] for item in validated["songs"]},
        "catastrophic_listens_complete": True,
        "subjective_usefulness_gate": None,
    }


def load_approved_full_song_plan(
    approval: str | Path,
    output: str | Path,
    *,
    model_root: str | Path | None = None,
    ffmpeg: str | Path = "ffmpeg",
    ffprobe: str | Path = "ffprobe",
) -> dict[str, Any]:
    """Build a read-only, hash-bound execution plan."""

    approval_path, document, approval_sha256 = _load_approval(approval)
    if document["status"] != "approvals_complete_for_verified_delivery":
        raise PermissionError("approval does not authorize verified delivery")
    songs = resolve_core_four_approved_songs(document)
    ffmpeg_path = resolve_executable(ffmpeg)
    ffprobe_path = resolve_executable(ffprobe)
    root = (
        Path(model_root).expanduser().absolute()
        if model_root is not None
        else DEFAULT_PROFILE_ROOT
    )
    destination = Path(output).expanduser().absolute()
    source_rows: list[dict[str, Any]] = []
    for song in songs:
        probe = _probe_approved_source(
            Path(song["resolved_absolute_path"]), ffprobe=ffprobe_path
        )
        source_rows.append({**song, **probe})
    hashes = {row["source_sha256"] for row in source_rows}
    if len(hashes) != 3:
        raise ValueError("full-song canaries must be content-disjoint")
    projected_audio = sum(
        math.ceil(row["duration_seconds"] * 44_100) * 6 * 6 for row in source_rows
    )
    required_free = (
        projected_audio
        + max(math.ceil(row["duration_seconds"] * 44_100) * 6 for row in source_rows)
        + DEFAULT_AUDIO_IMPORT_LIMITS.minimum_free_space_headroom_bytes
    )
    parent = _nearest_existing_parent(destination.parent)
    available_free = shutil.disk_usage(parent).free
    return {
        "schema": RUN_SCHEMA,
        "status": (
            "ready_explicit_execution_required"
            if (
                root.is_dir()
                and (root / "runtime/bin/python").is_file()
                and not os.path.lexists(destination)
                and available_free >= required_free
            )
            else "blocked"
        ),
        "read_only": True,
        "approval": {
            "path": str(approval_path),
            "sha256": approval_sha256,
            "approval_id": document["approval_id"],
            "approved_by": document["approved_by"],
            "profile_id": document["profile"]["profile_id"],
        },
        "profile_id": SCNET_RELEASE_PROFILE_ID,
        "scope_id": SCOPE_ID,
        "model_root": str(root),
        "model_root_present": root.is_dir(),
        "output": str(destination),
        "output_fresh": not os.path.lexists(destination),
        "ffmpeg": _executable_identity(ffmpeg_path),
        "ffprobe": _executable_identity(ffprobe_path),
        "songs": source_rows,
        "resources": {
            "seconds_per_audio_minute": MAXIMUM_SECONDS_PER_AUDIO_MINUTE,
            "maximum_seconds_per_song": MAXIMUM_SECONDS_PER_SONG,
            "maximum_peak_unified_memory_bytes": 12 * 1024**3,
            "projected_persisted_audio_bytes": projected_audio,
            "required_free_bytes": required_free,
            "available_free_bytes": available_free,
        },
        "effects_if_executed": {
            "writes": [str(destination)],
            "network": [],
            "uploads": [],
            "installs": [],
            "model_resolution": "explicit_installed_local_profile_only",
            "profile_status_changes": [],
            "automatic_midi_or_create": False,
        },
    }


def execute_approved_full_song_canaries(
    approval: str | Path,
    output: str | Path,
    *,
    execute: bool,
    model_root: str | Path | None = None,
    ffmpeg: str | Path = "ffmpeg",
    ffprobe: str | Path = "ffprobe",
) -> dict[str, Any]:
    """Execute exactly the approved three-song set and publish atomically."""

    if execute is not True:
        raise PermissionError("full-song canaries require --execute")
    plan = load_approved_full_song_plan(
        approval,
        output,
        model_root=model_root,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
    )
    if plan["status"] != "ready_explicit_execution_required":
        raise RuntimeError("approved full-song canary plan is not ready")
    destination = Path(plan["output"])
    root = Path(plan["model_root"])
    _verify_installed_profile(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-", dir=destination.parent
        )
    )
    canonical_root = staging / ".canonical-inputs"
    canonical_root.mkdir(mode=0o700)
    started = time.perf_counter()
    canary_receipts: list[dict[str, Any]] = []
    try:
        approval_root = staging / "APPROVAL"
        approval_root.mkdir(mode=0o700)
        approval_copy = approval_root / "approved.json"
        shutil.copy2(plan["approval"]["path"], approval_copy)
        if file_sha256(approval_copy) != plan["approval"]["sha256"]:
            raise ValueError("approval copy changed")

        for index, song in enumerate(plan["songs"], start=1):
            coverage = song["coverage_id"]
            print(
                f"[{index}/3] {coverage}: canonicalizing approved local source",
                flush=True,
            )
            source = Path(song["resolved_absolute_path"])
            if file_sha256(source) != song["source_sha256"]:
                raise ValueError(f"approved source changed before {coverage}")
            canonical = canonical_root / f"{coverage}.wav"
            _canonicalize(
                source,
                canonical,
                ffmpeg=Path(plan["ffmpeg"]["path"]),
                duration_seconds=float(song["duration_seconds"]),
            )
            canonical_identity = _verify_canonical(
                canonical, python=root / "runtime/bin/python"
            )
            canary_root = staging / "CANARIES" / coverage
            canary_root.mkdir(parents=True, mode=0o700)
            result = canary_root / "worker-result.json"
            print(
                f"[{index}/3] {coverage}: running network-denied SCNet inference",
                flush=True,
            )
            worker = _run_worker(
                source=canonical,
                destination=canary_root,
                result=result,
                model_root=root,
                duration_seconds=canonical_identity["duration_seconds"],
            )
            _validate_worker(worker, root=canary_root)
            if file_sha256(source) != song["source_sha256"]:
                raise ValueError(f"approved source changed during {coverage}")
            receipt = {
                "schema": CANARY_SCHEMA,
                "status": "technical_pass_listening_pending",
                "coverage_id": coverage,
                "approval": {
                    "approval_id": plan["approval"]["approval_id"],
                    "approval_sha256": plan["approval"]["sha256"],
                    "approved_absolute_path": song["approved_absolute_path"],
                    "resolved_absolute_path": song["resolved_absolute_path"],
                    "path_normalization": song["path_normalization"],
                    "rights_category": song["rights_category"],
                },
                "source": {
                    "bytes": song["source_bytes"],
                    "sha256": song["source_sha256"],
                    "probe": {
                        key: song[key]
                        for key in (
                            "stream_index",
                            "codec",
                            "sample_format",
                            "sample_rate",
                            "channels",
                            "channel_layout",
                            "duration_seconds",
                            "omitted_non_audio_streams",
                        )
                    },
                    "unchanged_before_and_after": True,
                },
                "canonical_input": canonical_identity,
                "profile_id": PROFILE_ID,
                "scope_id": SCOPE_ID,
                "objective_gates": {
                    "offline_execution": True,
                    "exact_profile_identity": True,
                    "exact_four_roles": True,
                    "matching_clocks": True,
                    "finite_bounded_audio": True,
                    "reconstruction_accounting": True,
                    "resource_ceiling": True,
                    "source_preserved": True,
                },
                "subjective_quality_gate": None,
                "human_catastrophic_listen": {
                    "complete": False,
                    "mislabelled_corrupt_silent_or_grossly_mistimed": None,
                    "minimum_usefulness_rating": None,
                },
                "worker_report": "worker-result.json",
                "worker_summary": {
                    "elapsed_seconds": worker["resources"]["elapsed_seconds"],
                    "peak_unified_memory_bytes": worker["resources"][
                        "peak_unified_memory_bytes"
                    ],
                    "maximum_reconstruction_error_lsb": worker["additive_accounting"][
                        "maximum_absolute_error_lsb"
                    ],
                    "native_other_correction": worker["native_other_correction"],
                },
                "profile_status_changed": False,
                "public_access_changed": False,
            }
            _write_json(canary_root / "CANARY.json", receipt)
            (canary_root / "START-HERE.txt").write_text(
                _canary_start_here(coverage), encoding="utf-8"
            )
            canary_receipts.append(receipt)
            canonical.unlink()
            print(
                f"[{index}/3] {coverage}: objective gates passed; listening pending",
                flush=True,
            )

        canonical_root.rmdir()
        run_receipt = {
            "schema": RUN_SCHEMA,
            "status": "technical_pass_listening_pending",
            "approval": plan["approval"],
            "profile_id": SCNET_RELEASE_PROFILE_ID,
            "scope_id": SCOPE_ID,
            "machine": {
                "system": platform.system(),
                "machine": platform.machine(),
                "verified_class": "Apple M3 Max with 36 GB unified memory",
                "sixteen_gib_status": "accessible_but_unverified",
            },
            "canaries": [
                {
                    "coverage_id": item["coverage_id"],
                    "receipt": f"CANARIES/{item['coverage_id']}/CANARY.json",
                    "status": item["status"],
                    "worker_summary": item["worker_summary"],
                }
                for item in canary_receipts
            ],
            "objective_gates_passed": True,
            "subjective_quality_gate": None,
            "catastrophic_listens_complete": False,
            "profile_status_changed": False,
            "public_access_changed": False,
            "automatic_midi_or_create": False,
            "audio_uploaded": False,
            "elapsed_seconds": time.perf_counter() - started,
            "next_gate": "one complete catastrophic-output listen per canary",
        }
        _write_json(staging / "CANARY-RUN.json", run_receipt)
        review_root = staging / "REVIEW"
        review_root.mkdir(mode=0o700)
        (review_root / "canary-listen.html").write_text(
            render_canary_listen_html(run_receipt), encoding="utf-8"
        )
        (staging / "START-HERE.txt").write_text(
            "SCNet approval-bound full-song canaries\n\n"
            "All three objective runs passed. No audio was uploaded and the "
            "profile was not activated.\n"
            "Serve REVIEW/canary-listen.html with the exact local review server, "
            "then complete one catastrophic-output listen for each song.\n"
            "Poor or mixed musical quality is not a preview veto.\n",
            encoding="utf-8",
        )
        os.replace(staging, destination)
        return {**run_receipt, "root": str(destination)}
    except BaseException:
        failed = Path(f"{destination}.failed.{os.getpid()}.evidence")
        if staging.exists() and not os.path.lexists(failed):
            os.replace(staging, failed)
        raise


def render_canary_listen_html(run: Mapping[str, Any]) -> str:
    """Render a local-only listen form; audio routes are supplied by its server."""

    cards: list[str] = []
    for canary in run["canaries"]:
        coverage = str(canary["coverage_id"])
        label = html.escape(coverage.replace("_", " ").title())
        audio = "".join(
            f"<article><h3>{html.escape(role.replace('_', ' ').title())}</h3>"
            f'<audio controls preload="metadata" src="/audio/{coverage}/{role}.wav"></audio></article>'
            for role in OUTPUT_PATHS
        )
        cards.append(
            f'<section class="song" data-coverage="{coverage}"><h2>{label}</h2>'
            f'<div class="audio-grid">{audio}</div>'
            '<label class="check"><input type="checkbox" class="listened"> '
            "I listened to the source, all four stems and reconstruction check.</label>"
            '<label>Catastrophic result<select class="result"><option value="">Choose…</option>'
            '<option value="no_catastrophic_defect">No catastrophic defect</option>'
            '<option value="catastrophic_defect_reported">Catastrophic defect found</option>'
            "</select></label><label>Details (required only for a defect)"
            '<textarea class="details" maxlength="5000"></textarea></label></section>'
        )
    binding = json.dumps(
        {
            "schema": LISTEN_SCHEMA,
            "run_schema": run["schema"],
            "approval_id": run["approval"]["approval_id"],
            "approval_sha256": run["approval"]["sha256"],
            "profile_id": run["profile_id"],
            "scope_id": run["scope_id"],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).replace("<", "\\u003c")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src data:">
<title>SCNet full-song canary listen</title><style>
:root{{--bg:#07101c;--panel:#101d2c;--line:#2b465f;--ink:#f6f8fb;--muted:#aeb9c8;--cyan:#4fe2ee}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:17px/1.5 system-ui}}main{{max-width:1180px;margin:auto;padding:32px 20px 80px}}h1{{font-size:clamp(2.4rem,7vw,5rem);line-height:1;margin:.2em 0}}.eyebrow{{color:var(--cyan);font-weight:800;letter-spacing:.12em}}.song{{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:24px;margin:20px 0}}.audio-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}article{{border:1px solid var(--line);border-radius:14px;padding:14px}}audio{{width:100%}}label{{display:block;margin:16px 0}}select,textarea{{display:block;width:100%;margin-top:7px;padding:10px}}textarea{{min-height:90px}}button{{background:var(--cyan);border:0;border-radius:999px;padding:13px 20px;font-weight:800}}.muted{{color:var(--muted)}}@media(max-width:720px){{.audio-grid{{grid-template-columns:1fr}}}}
</style></head><body><main><div class="eyebrow">LOCAL · CATASTROPHIC CHECK ONLY</div><h1>Listen without creating a quality veto.</h1><p>Check only corruption, mislabelling, silence across all roles or gross timing. Bleed, artefacts or poor usefulness are feedback, not automatic preview blockers. Nothing is uploaded.</p>{"".join(cards)}<button id="save">Save locally + download JSON</button> <button id="copy">Copy listening JSON</button><p id="status" class="muted"></p><label>Listening JSON fallback<textarea id="json" readonly></textarea></label></main><script>
const binding={binding};
function reviewValue(){{const songs=[];const missing=[];document.querySelectorAll('.song').forEach(section=>{{const coverage=section.dataset.coverage;const complete=section.querySelector('.listened').checked;const result=section.querySelector('.result').value;const details=section.querySelector('.details').value.trim();if(!complete)missing.push(coverage+' listen');if(!result)missing.push(coverage+' result');if(result==='catastrophic_defect_reported'&&!details)missing.push(coverage+' details');songs.push({{coverage_id:coverage,complete,result,details,minimum_usefulness_rating:null}})}});const value={{...binding,status:missing.length?'incomplete':'complete',songs,missing_fields:missing,audio_included:false,telemetry_included:false,exported_at:new Date().toISOString()}};document.getElementById('json').value=JSON.stringify(value,null,2)+'\\n';return value;}}
function downloadValue(value){{const blob=new Blob([JSON.stringify(value,null,2)+'\\n'],{{type:'application/json'}});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='sunofriend-scnet-full-song-listen-'+(value.missing_fields.length?'draft':'complete')+'.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}}
document.getElementById('save').addEventListener('click',async()=>{{const value=reviewValue();const status=document.getElementById('status');downloadValue(value);if(value.missing_fields.length){{status.textContent='Draft download requested; complete '+value.missing_fields.join(', ')+' before the local evidence record can be saved.';return;}}const button=document.getElementById('save');button.disabled=true;try{{const response=await fetch('/review',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(value)}});const receipt=await response.json();if(response.ok){{status.textContent='Saved and validated locally as '+receipt.path+'. A Downloads copy was also requested.';}}else if(response.status===409&&receipt.status==='already_recorded'){{status.textContent='A validated review is already saved as '+receipt.path+'; it was not overwritten. A Downloads copy was also requested.';}}else{{status.textContent='Local save failed: '+(receipt.error||response.status)+'. Use Copy listening JSON or the fallback text below.';}}}}catch(error){{status.textContent='Local save could not be reached. Use Copy listening JSON or the fallback text below.';}}finally{{button.disabled=false;}}}});
document.getElementById('copy').addEventListener('click',async()=>{{const value=reviewValue();try{{await navigator.clipboard.writeText(JSON.stringify(value,null,2)+'\\n');document.getElementById('status').textContent=value.missing_fields.length?'Draft JSON copied: '+value.missing_fields.join(', '):'Complete listening JSON copied.';}}catch(error){{document.getElementById('status').textContent='Clipboard access failed. Select and copy the JSON fallback text below.';}}}});
reviewValue();
</script></body></html>"""


def _load_approval(path: str | Path) -> tuple[Path, dict[str, Any], str]:
    approval = Path(path).expanduser().absolute()
    if approval.is_symlink() or not approval.is_file():
        raise FileNotFoundError("approval JSON must be an existing regular file")
    raw = approval.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("approval JSON is invalid") from exc
    if not isinstance(document, Mapping):
        raise ValueError("approval JSON must contain an object")
    return (
        approval,
        validate_core_four_approval_document(document),
        file_sha256(approval),
    )


def _probe_approved_source(path: Path, *, ffprobe: Path) -> dict[str, Any]:
    source = validate_local_source_path(path)
    before = file_sha256(source)
    completed = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(source),
        ],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=DEFAULT_AUDIO_IMPORT_LIMITS.probe_timeout_seconds,
    )
    if completed.returncode:
        raise RuntimeError(
            f"ffprobe failed for approved source: {completed.stderr[:1000]}"
        )
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("ffprobe returned invalid JSON") from exc
    streams = document.get("streams")
    if not isinstance(streams, list) or any(
        not isinstance(row, Mapping) for row in streams
    ):
        raise ValueError("ffprobe stream report is invalid")
    audio = [row for row in streams if row.get("codec_type") == "audio"]
    if len(audio) != 1:
        raise ValueError("approved source must contain exactly one audio stream")
    stream = audio[0]
    format_row = document.get("format")
    if not isinstance(format_row, Mapping):
        format_row = {}
    duration = float(stream.get("duration") or format_row.get("duration") or 0)
    sample_rate = int(stream.get("sample_rate") or 0)
    channels = int(stream.get("channels") or 0)
    if (
        not math.isfinite(duration)
        or not 0 < duration <= DEFAULT_AUDIO_IMPORT_LIMITS.maximum_duration_seconds
        or not 0 < sample_rate <= 384_000
        or not 0 < channels <= DEFAULT_AUDIO_IMPORT_LIMITS.maximum_channels
    ):
        raise ValueError("approved source audio clock or duration is invalid")
    after = file_sha256(source)
    if before != after:
        raise ValueError("approved source changed while it was probed")
    non_audio = [
        {
            "stream_index": row.get("index"),
            "codec_type": row.get("codec_type"),
            "codec": row.get("codec_name"),
            "attached_picture": bool(row.get("disposition", {}).get("attached_pic")),
        }
        for row in streams
        if row.get("codec_type") != "audio"
    ]
    return {
        "source_bytes": source.stat().st_size,
        "source_sha256": after,
        "stream_index": stream.get("index"),
        "codec": stream.get("codec_name"),
        "sample_format": stream.get("sample_fmt"),
        "sample_rate": sample_rate,
        "channels": channels,
        "channel_layout": stream.get("channel_layout"),
        "duration_seconds": duration,
        "omitted_non_audio_streams": non_audio,
    }


def _canonicalize(
    source: Path,
    destination: Path,
    *,
    ffmpeg: Path,
    duration_seconds: float,
) -> None:
    command = [
        str(ffmpeg),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-protocol_whitelist",
        "file",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-vn",
        "-sn",
        "-dn",
        "-t",
        f"{duration_seconds:.9f}",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-c:a",
        "pcm_s24le",
        "-fflags",
        "+bitexact",
        "-flags:a",
        "+bitexact",
        "-metadata",
        "encoder=",
        "-write_bext",
        "0",
        "-rf64",
        "auto",
        "-f",
        "wav",
        "-fs",
        str(DEFAULT_AUDIO_IMPORT_LIMITS.maximum_canonical_bytes),
        str(destination),
    ]
    completed = subprocess.run(
        command,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=max(120.0, min(1800.0, duration_seconds * 4.0)),
        env={**os.environ, "LANG": "C", "LC_ALL": "C"},
    )
    if completed.returncode:
        raise RuntimeError(f"canonical decode failed: {completed.stderr[:2000]}")


def _verify_canonical(path: Path, *, python: Path) -> dict[str, Any]:
    probe = (
        "import json,sys,wave; "
        "r=wave.open(sys.argv[1], 'rb'); "
        "print(json.dumps({'frames':r.getnframes(),'channels':r.getnchannels(),"
        "'sample_rate':r.getframerate(),'sample_width':r.getsampwidth(),"
        "'compression':r.getcomptype()})); r.close()"
    )
    completed = subprocess.run(
        [str(python), "-I", "-c", probe, str(path)],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    if completed.returncode:
        raise ValueError(
            f"pinned runtime could not read canonical PCM24: {completed.stderr[:1000]}"
        )
    try:
        parameters = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("canonical PCM24 probe returned invalid JSON") from exc
    frames = parameters.get("frames")
    channels = parameters.get("channels")
    sample_rate = parameters.get("sample_rate")
    sample_width = parameters.get("sample_width")
    compression = parameters.get("compression")
    if (
        frames <= 0
        or channels != 2
        or sample_rate != 44_100
        or sample_width != 3
        or compression != "NONE"
    ):
        raise ValueError("canonical source is not stereo 44.1 kHz PCM24")
    return {
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "frames": frames,
        "channels": channels,
        "sample_rate": sample_rate,
        "sample_width_bytes": sample_width,
        "duration_seconds": frames / sample_rate,
        "temporary_copy_removed_after_inference": True,
    }


def _run_worker(
    *,
    source: Path,
    destination: Path,
    result: Path,
    model_root: Path,
    duration_seconds: float,
) -> dict[str, Any]:
    repository = Path(__file__).resolve().parents[2]
    runtime_python = model_root / "runtime/bin/python"
    worker = repository / "src/sunofriend/separation_scnet_worker.py"
    command = [
        "/usr/bin/sandbox-exec",
        "-p",
        "(version 1)(deny network*)(allow default)",
        str(runtime_python),
        str(worker),
        "--source",
        str(source),
        "--destination",
        str(destination),
        "--result",
        str(result),
        "--model-root",
        str(model_root),
        "--network-denial-enforced",
    ]
    environment = {
        **os.environ,
        "PYTHONPATH": str(repository / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "NO_PROXY": "*",
        "no_proxy": "*",
        "PIP_NO_INDEX": "1",
    }
    ceiling = min(
        MAXIMUM_SECONDS_PER_SONG,
        MAXIMUM_SECONDS_PER_AUDIO_MINUTE * duration_seconds / 60.0,
    )
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=ceiling + 5.0,
            env=environment,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            "SCNet full-song worker exceeded its runtime ceiling"
        ) from exc
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"SCNet full-song worker failed ({completed.returncode}): {detail[:4000]}"
        )
    try:
        value = json.loads(result.read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("SCNet worker report is missing or invalid") from exc
    if not isinstance(value, Mapping):
        raise RuntimeError("SCNet worker report must be an object")
    return dict(value)


def _validate_worker(worker: Mapping[str, Any], *, root: Path) -> None:
    spec = separation_profile(SCNET_RELEASE_PROFILE_ID)
    runtime = worker.get("runtime")
    model = worker.get("model")
    resources = worker.get("resources")
    accounting = worker.get("additive_accounting")
    correction = worker.get("native_other_correction")
    outputs = worker.get("outputs")
    frames = worker.get("frames")
    if (
        worker.get("schema") != "sunofriend.experimental-core-four-worker.v1"
        or worker.get("status") != "complete_unreviewed"
        or worker.get("profile_id") != SCNET_RELEASE_PROFILE_ID
        or worker.get("roles") != ["vocals", "drums", "bass", "other"]
        or worker.get("sample_rate") != 44_100
        or worker.get("channels") != 2
        or not isinstance(frames, int)
        or isinstance(frames, bool)
        or frames <= 0
        or worker.get("inference") != dict(spec.inference_settings)
        or not isinstance(runtime, Mapping)
        or runtime.get("backend") != spec.backend
        or runtime.get("packages") != dict(spec.packages())
        or runtime.get("system") != "Darwin"
        or str(runtime.get("machine", "")).casefold() != "arm64"
        or runtime.get("device") != "cpu"
        or runtime.get("pytorch_present") is not True
        or runtime.get("network_denial_enforced") is not True
        or runtime.get("network_used") is not False
        or runtime.get("writer_count") != 1
        or not isinstance(model, Mapping)
        or model.get("model_id") != spec.model_id
        or model.get("model_revision") != spec.model_revision
        or model.get("source_revision") != spec.runtime_source_revision
        or model.get("weights_sha256") != spec.artifact("weights").sha256
        or model.get("config_sha256") != spec.artifact("config").sha256
        or model.get("source_order") != ["drums", "bass", "other", "vocals"]
        or model.get("checkpoint_local_only") is not True
        or model.get("named_or_network_model_resolution") is not False
        or model.get("compatibility_remediation_cycles") != 1
        or worker.get("source_unchanged") is not True
        or worker.get("model_artifacts_unchanged") is not True
        or not isinstance(resources, Mapping)
        or resources.get("within_runtime_ceiling") is not True
        or not isinstance(accounting, Mapping)
        or accounting.get("passed") is not True
        or accounting.get("maximum_absolute_error_lsb", 3) > 2
        or not isinstance(correction, Mapping)
        or correction.get("used_for_separation_accuracy_claim") is not False
        or not isinstance(outputs, Mapping)
        or set(outputs) != set(OUTPUT_PATHS)
    ):
        raise RuntimeError("SCNet full-song worker objective evidence differs")
    peak_memory = resources.get("peak_unified_memory_bytes")
    if not isinstance(peak_memory, int) or not 0 <= peak_memory <= 12 * 1024**3:
        raise RuntimeError("SCNet full-song worker exceeded the memory ceiling")
    for metric in ("rms", "peak"):
        value = correction.get(metric)
        if type(value) not in (int, float) or not math.isfinite(float(value)):
            raise RuntimeError("SCNet correction metric is invalid")
    for role, relative in OUTPUT_PATHS.items():
        path = root / relative
        claim = outputs[role]
        if (
            not path.is_file()
            or not isinstance(claim, Mapping)
            or claim.get("frames") != frames
            or claim.get("channels") != 2
            or claim.get("sample_rate") != 44_100
            or claim.get("sample_width_bytes") != 3
            or claim.get("bytes") != path.stat().st_size
            or claim.get("sha256") != file_sha256(path)
        ):
            raise RuntimeError(f"SCNet persisted output differs for {role}")


def _verify_installed_profile(root: Path) -> None:
    runtime = root / "runtime/bin/python"
    if not root.is_dir() or not runtime.is_file() or not os.access(runtime, os.X_OK):
        raise FileNotFoundError("installed SCNet profile runtime is missing")
    installation = json.loads((root / "INSTALLATION.json").read_text(encoding="utf-8"))
    compatibility = json.loads(
        (root / "COMPATIBILITY.json").read_text(encoding="utf-8")
    )
    if (
        installation.get("profile_id") != SCNET_RELEASE_PROFILE_ID
        or installation.get("model_terms_accepted") is not True
        or installation.get("checkpoint_use_accepted") is not True
        or compatibility.get("status") != "passed"
        or compatibility.get("compatibility", {}).get("remediation_cycles") != 1
    ):
        raise RuntimeError("installed SCNet approval or compatibility receipt differs")


def _executable_identity(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [str(path), "-version"],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=10,
    )
    if completed.returncode:
        raise RuntimeError(f"decoder identity command failed: {path}")
    return {
        "path": str(path),
        "sha256": file_sha256(path),
        "version": completed.stdout.splitlines()[0],
    }


def _canary_start_here(coverage: str) -> str:
    return (
        f"SCNet full-song canary: {coverage}\n\n"
        "Listen to SOURCE/source-reference.wav, all four STEMS files and "
        "AUDIO/reconstruction-check.wav.\n"
        "At this gate record only corruption, mislabelling, silence across all "
        "roles or gross timing.\n"
        "Poor musical usefulness, bleed or artefacts are not a preview veto.\n"
        "No audio was uploaded and no MIDI/Create action was run.\n"
    )


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists():
        if candidate.parent == candidate:
            raise FileNotFoundError("no existing parent for canary output")
        candidate = candidate.parent
    return candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model-root")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.execute:
        result = load_approved_full_song_plan(
            args.approval,
            args.out,
            model_root=args.model_root,
            ffmpeg=args.ffmpeg,
            ffprobe=args.ffprobe,
        )
    else:
        result = execute_approved_full_song_canaries(
            args.approval,
            args.out,
            execute=True,
            model_root=args.model_root,
            ffmpeg=args.ffmpeg,
            ffprobe=args.ffprobe,
        )
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CANARY_SCHEMA",
    "LISTEN_SCHEMA",
    "RUN_SCHEMA",
    "build_canary_review_server",
    "execute_approved_full_song_canaries",
    "load_approved_full_song_plan",
    "main",
    "record_no_failure_canary_listen",
    "render_canary_listen_html",
    "validate_canary_listen_document",
]
