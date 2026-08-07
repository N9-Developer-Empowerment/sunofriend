"""Prepare and record one bounded private guitar/keys review corpus.

Provider stems are local comparison estimates.  They never become ground truth,
model-selection votes, source nodes or MIDI inputs through this module.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from .audio_formats import file_sha256, resolve_executable
from .separation_other_refinement import (
    validate_other_refinement_plan,
    validate_other_refinement_result,
)
from .separation_other_refinement_review import record_other_refinement_review


CORPUS_DEFINITION_SCHEMA = "sunofriend.other-refinement-evaluation-corpus.v1"
CORPUS_REVIEW_INDEX_SCHEMA = "sunofriend.other-refinement-corpus-review-index.v1"
CORPUS_LISTENING_SCHEMA = "sunofriend.other-refinement-corpus-listening.v1"
CORPUS_FEEDBACK_INDEX_SCHEMA = "sunofriend.other-refinement-corpus-feedback.v1"

_TARGETS = frozenset({"guitar", "keys"})
_RIGHTS = frozenset({"owned", "authorised_private_use"})
_SAFE_TOKEN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_POLICY = {
    "configuration_count": 1,
    "case_duration_seconds": 15.0,
    "targets": ["guitar", "keys"],
    "keys_semantics": "piano_proxy_not_general_keyboards",
    "windows_frozen_before_inference": True,
    "provider_stems_are_ground_truth": False,
    "provider_labels_prove_instrument_presence": False,
    "relative_activity_score_proves_instrument_presence": False,
    "automatic_model_selection": False,
    "automatic_source_activation": False,
    "automatic_midi_activation": False,
    "poor_or_mixed_feedback_blocks_access": False,
    "retry_policy": "objective_execution_fault_only",
    "review_trigger": "one bounded round of 10 valid reports",
}


def load_other_refinement_corpus_definition(path: str | Path) -> dict[str, Any]:
    """Load and strictly validate the fixed, pre-inference corpus definition."""

    source = _regular_file(path, "other-refinement corpus definition")
    if source.stat().st_size > 1024 * 1024:
        raise ValueError("other-refinement corpus definition is too large")
    value = _load_json(source, "other-refinement corpus definition")
    if set(value) != {
        "schema",
        "status",
        "checked_on",
        "policy",
        "tracks",
        "comparison_cues",
        "permissions",
    }:
        raise ValueError("other-refinement corpus definition fields differ")
    if value.get("schema") != CORPUS_DEFINITION_SCHEMA:
        raise ValueError("unsupported other-refinement corpus definition")
    if value.get("status") != "fixed_authorised_private_evaluation_no_selection":
        raise ValueError("other-refinement corpus definition status differs")
    if (
        not isinstance(value.get("checked_on"), str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value["checked_on"]) is None
    ):
        raise ValueError("other-refinement corpus checked date differs")
    policy = value.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("other-refinement corpus policy is missing")
    maximum_cases = policy.get("maximum_cases")
    if type(maximum_cases) is not int or not 1 <= maximum_cases <= 10:
        raise ValueError("other-refinement corpus case ceiling is invalid")
    expected_policy = {**_EXPECTED_POLICY, "maximum_cases": maximum_cases}
    if policy != expected_policy:
        raise ValueError("other-refinement corpus policy differs")

    cues = value.get("comparison_cues")
    if not isinstance(cues, dict) or set(cues) != _TARGETS:
        raise ValueError("other-refinement corpus comparison cues differ")
    validated_cues = {
        target: _validate_cues(target, target_cues)
        for target, target_cues in cues.items()
    }

    tracks = value.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        raise ValueError("other-refinement corpus tracks are missing")
    case_ids: set[str] = set()
    track_ids: set[str] = set()
    case_count = 0
    for track in tracks:
        if not isinstance(track, dict):
            raise ValueError("other-refinement corpus track differs")
        required = {
            "track_id",
            "display_name",
            "directory",
            "corpus_manifest",
            "rights_category",
            "common_provider_horizon_seconds",
            "cases",
        }
        optional = {"known_geometry_limitation", "private_scope"}
        if not required <= set(track) or set(track) - required - optional:
            raise ValueError("other-refinement corpus track fields differ")
        track_id = _token(track.get("track_id"), "track ID")
        if track_id in track_ids:
            raise ValueError("other-refinement corpus track IDs must be unique")
        track_ids.add(track_id)
        if not _plain_text(track.get("display_name"), maximum=300):
            raise ValueError("other-refinement corpus display name is invalid")
        _safe_relative(track.get("directory"), "track directory")
        if track.get("corpus_manifest") not in {
            "corpus.json",
            "private-reference-corpus.json",
        }:
            raise ValueError("other-refinement corpus authority manifest differs")
        if track.get("rights_category") not in _RIGHTS:
            raise ValueError("other-refinement corpus rights category differs")
        if track["corpus_manifest"] == "corpus.json":
            if track["rights_category"] != "owned" or "private_scope" in track:
                raise ValueError("owner-authorised corpus rights binding differs")
        elif (
            track["rights_category"] != "authorised_private_use"
            or track.get("private_scope") != "private_local_evaluation_only"
        ):
            raise ValueError("private-reference corpus rights binding differs")
        if "known_geometry_limitation" in track and not _plain_text(
            track["known_geometry_limitation"], maximum=1000
        ):
            raise ValueError("other-refinement geometry limitation is invalid")
        horizon = _finite_positive(
            track.get("common_provider_horizon_seconds"), "provider horizon"
        )
        cases = track.get("cases")
        if not isinstance(cases, list) or {item.get("target_id") for item in cases} != (
            _TARGETS
        ):
            raise ValueError("each corpus track must have guitar and keys cases")
        for case in cases:
            if not isinstance(case, dict) or set(case) != {
                "case_id",
                "target_id",
                "start_seconds",
                "end_seconds",
                "selection_score",
            }:
                raise ValueError("other-refinement corpus case fields differ")
            case_id = _token(case.get("case_id"), "case ID")
            if case_id in case_ids or not case_id.startswith(track_id + "-"):
                raise ValueError("other-refinement corpus case IDs differ")
            case_ids.add(case_id)
            target_id = case.get("target_id")
            if target_id not in _TARGETS or not case_id.endswith("-" + target_id):
                raise ValueError("other-refinement corpus target binding differs")
            start = _finite_nonnegative(case.get("start_seconds"), "case start")
            end = _finite_positive(case.get("end_seconds"), "case end")
            if end - start != expected_policy["case_duration_seconds"] or end > horizon:
                raise ValueError("other-refinement corpus case window differs")
            _finite_nonnegative(case.get("selection_score"), "selection score")
            case_count += 1
    if case_count != maximum_cases:
        raise ValueError("other-refinement corpus does not fill its case ceiling")
    if validated_cues != cues:
        raise ValueError("other-refinement corpus cue validation changed values")
    if value.get("permissions") != {
        "audio_committed": False,
        "provider_audio_redistributed": False,
        "local_review_only": True,
        "candidate_selected": False,
        "profile_promoted": False,
        "source_graph_mutated": False,
        "midi_created": False,
    }:
        raise ValueError("other-refinement corpus permission boundary differs")
    return value


def validate_other_refinement_corpus_authority(
    definition: Mapping[str, Any], *, stem_root: str | Path
) -> list[dict[str, Any]]:
    """Bind every case to the existing tracked rights manifest."""

    stems = _real_directory(stem_root, "stem example root")
    authorities: list[dict[str, Any]] = []
    for track in definition["tracks"]:
        manifest_path = _regular_file(
            stems / track["corpus_manifest"], "corpus authority manifest"
        )
        manifest = _load_json(manifest_path, "corpus authority manifest")
        records = manifest.get("tracks")
        if not isinstance(records, list):
            raise ValueError("corpus authority tracks are missing")
        matches = [item for item in records if item.get("id") == track["track_id"]]
        if len(matches) != 1:
            raise ValueError("corpus authority track binding differs")
        if track["corpus_manifest"] == "corpus.json":
            permission = manifest.get("permission")
            if (
                manifest.get("schema") != "sunofriend.authorised-separation-corpus.v1"
                or not isinstance(permission, dict)
                or permission.get("authority") != "creator_and_copyright_holder"
                or permission.get("allowed_use")
                != "download, study, transform and reuse"
                or track["rights_category"] != "owned"
            ):
                raise ValueError("owner-authorised corpus evidence differs")
            authority = "creator_and_copyright_holder"
            scope = "authorised_development_corpus"
        else:
            permission = matches[0].get("private_processing_authority")
            if (
                manifest.get("schema")
                != "sunofriend.private-reference-separation-corpus.v1"
                or not isinstance(permission, dict)
                or permission.get("status") != "user_authorised"
                or permission.get("scope") != "private_local_evaluation_only"
                or permission.get("repository_distribution") is not False
                or permission.get("public_demo_use") is not False
                or track["rights_category"] != "authorised_private_use"
            ):
                raise ValueError("private-reference authority evidence differs")
            authority = "user_authorised"
            scope = "private_local_evaluation_only"
        authorities.append(
            {
                "track_id": track["track_id"],
                "manifest_schema": manifest["schema"],
                "manifest_sha256": file_sha256(manifest_path),
                "authority": authority,
                "scope": scope,
                "repository_distribution": False,
                "public_demo_use": False,
            }
        )
    return authorities


def prepare_other_refinement_corpus_review(
    definition_path: str | Path,
    *,
    stem_root: str | Path,
    execution_root: str | Path,
    output: str | Path,
    ffmpeg: str | Path = "ffmpeg",
) -> dict[str, Any]:
    """Create a fresh, self-contained localhost review package."""

    definition_file = _regular_file(
        definition_path, "other-refinement corpus definition"
    )
    definition = load_other_refinement_corpus_definition(definition_file)
    stems = _real_directory(stem_root, "stem example root")
    authorities = {
        item["track_id"]: item
        for item in validate_other_refinement_corpus_authority(
            definition, stem_root=stems
        )
    }
    execution = _real_directory(execution_root, "corpus execution root")
    destination = Path(output).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"corpus review output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_path = resolve_executable(ffmpeg)

    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-", dir=destination.parent
        )
    )
    staging.chmod(0o700)
    try:
        cases: list[dict[str, Any]] = []
        for track in definition["tracks"]:
            track_root = _real_directory(
                stems / track["directory"], "corpus track directory"
            )
            if stems not in track_root.parents:
                raise ValueError("corpus track directory escapes the stem root")
            for case in track["cases"]:
                cases.append(
                    _prepare_case(
                        track=track,
                        case=case,
                        cues=definition["comparison_cues"][case["target_id"]],
                        authority=authorities[track["track_id"]],
                        track_root=track_root,
                        execution=execution,
                        staging=staging,
                        ffmpeg=ffmpeg_path,
                    )
                )
        cases.sort(key=lambda item: item["case_id"])
        index: dict[str, Any] = {
            "schema": CORPUS_REVIEW_INDEX_SCHEMA,
            "status": "objective_execution_complete_listening_pending_no_selection",
            "definition": {
                "schema": definition["schema"],
                "file_sha256": file_sha256(definition_file),
                "document_sha256": _document_sha256(definition),
            },
            "policy": dict(definition["policy"]),
            "cases": cases,
            "objective_summary": {
                "case_count": len(cases),
                "all_reconstruction_accounting_passed": all(
                    item["objective"]["reconstruction_accounting_passed"]
                    for item in cases
                ),
                "maximum_reconstruction_error_lsb": max(
                    item["objective"]["maximum_reconstruction_error_lsb"]
                    for item in cases
                ),
                "network_used": any(
                    item["objective"]["network_used"] for item in cases
                ),
                "candidate_selected": False,
                "source_graph_mutated": False,
                "midi_created": False,
            },
            "comparison_boundary": {
                "provider_stems_are_ground_truth": False,
                "provider_labels_prove_instrument_presence": False,
                "similarity_or_listening_automatically_selects_model": False,
                "audio_and_filenames_in_export": False,
            },
        }
        index["document_sha256"] = _document_sha256(index)
        technical = staging / "TECHNICAL"
        technical.mkdir(mode=0o700)
        _write_private_json(technical / "corpus-review-index.json", index)
        page = staging / "review.html"
        page.write_text(_render_review(index), encoding="utf-8")
        page.chmod(0o600)
        os.replace(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "status": index["status"],
        "root": str(destination),
        "review_html": str(destination / "review.html"),
        "index": str(destination / "TECHNICAL/corpus-review-index.json"),
        "case_count": len(index["cases"]),
        "effects": {
            "model_executed": False,
            "network_used": False,
            "provider_reference_excerpts_created": True,
            "candidate_selected": False,
            "source_graph_mutated": False,
            "midi_created": False,
        },
    }


def build_other_refinement_corpus_review_server(
    review_root: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8766,
) -> ThreadingHTTPServer:
    """Serve one prepared package with byte ranges and no upload route."""

    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("corpus review server must bind to localhost")
    root = _real_directory(review_root, "corpus review root")
    index_path = _regular_file(
        root / "TECHNICAL/corpus-review-index.json", "corpus review index"
    )
    index = _load_json(index_path, "corpus review index")
    if index.get("schema") != CORPUS_REVIEW_INDEX_SCHEMA or index.get(
        "document_sha256"
    ) != _document_sha256(index):
        raise ValueError("corpus review index identity differs")
    page = _regular_file(root / "review.html", "corpus review page").read_bytes()
    routes: dict[str, Path] = {}
    for case in index.get("cases", []):
        for item in case.get("audio", []):
            route = item.get("route")
            artifact = item.get("artifact")
            if not isinstance(route, str) or not isinstance(artifact, dict):
                raise ValueError("corpus review audio route differs")
            path = _artifact_path(root, artifact)
            if route in routes:
                raise ValueError("corpus review audio routes must be unique")
            routes[route] = path

    class ReviewHandler(BaseHTTPRequestHandler):
        server_version = "SunofriendCorpusReview/1"

        def do_GET(self) -> None:  # noqa: N802
            self._serve(send_body=True)

        def do_HEAD(self) -> None:  # noqa: N802
            self._serve(send_body=False)

        def do_POST(self) -> None:  # noqa: N802
            self.send_error(405, "This local page accepts no submissions")

        def _serve(self, *, send_body: bool) -> None:
            route = self.path.partition("?")[0]
            if route in {"/", "/index.html", "/review.html"}:
                self._headers(200, "text/html; charset=utf-8", len(page))
                if send_body:
                    self.wfile.write(page)
                return
            if route == "/healthz":
                body = b'{"status":"ok","network_scope":"localhost_only"}\n'
                self._headers(200, "application/json; charset=utf-8", len(body))
                if send_body:
                    self.wfile.write(body)
                return
            path = routes.get(route)
            if path is None:
                self.send_error(404, "Not found")
                return
            self._serve_audio(path, send_body=send_body)

        def _serve_audio(self, path: Path, *, send_body: bool) -> None:
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            header = self.headers.get("Range")
            if header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
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
                status,
                "audio/wav",
                length,
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
            status: int,
            content_type: str,
            length: int,
            *,
            content_range: str | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
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


def record_other_refinement_corpus_reviews(
    execution_root: str | Path,
    review_root: str | Path,
    bundle_path: str | Path,
    *,
    out: str | Path,
) -> dict[str, Any]:
    """Split one ten-case browser bundle into strict per-result evidence."""

    execution = _real_directory(execution_root, "corpus execution root")
    review = _real_directory(review_root, "corpus review root")
    index_path = _regular_file(
        review / "TECHNICAL/corpus-review-index.json", "corpus review index"
    )
    index = _load_json(index_path, "corpus review index")
    if index.get("schema") != CORPUS_REVIEW_INDEX_SCHEMA or index.get(
        "document_sha256"
    ) != _document_sha256(index):
        raise ValueError("corpus review index identity differs")
    source_bundle = _regular_file(bundle_path, "corpus listening bundle")
    if source_bundle.stat().st_size > 1024 * 1024:
        raise ValueError("corpus listening bundle is too large")
    bundle = _load_json(source_bundle, "corpus listening bundle")
    if set(bundle) != {
        "schema",
        "review_index_sha256",
        "reviews",
        "audio_included",
        "filenames_included",
        "browser_telemetry_included",
        "exported_at",
    }:
        raise ValueError("corpus listening bundle fields differ")
    if (
        bundle.get("schema") != CORPUS_LISTENING_SCHEMA
        or bundle.get("review_index_sha256") != index["document_sha256"]
        or bundle.get("audio_included") is not False
        or bundle.get("filenames_included") is not False
        or bundle.get("browser_telemetry_included") is not False
    ):
        raise ValueError("corpus listening bundle boundary differs")
    reviews = bundle.get("reviews")
    if not isinstance(reviews, list):
        raise ValueError("corpus listening reviews are missing")
    expected = {item["case_id"]: item for item in index["cases"]}
    if len(expected) != 10:
        raise ValueError("corpus review index must bind the fixed ten cases")
    supplied: dict[str, dict[str, Any]] = {}
    for item in reviews:
        if not isinstance(item, dict) or set(item) != {"case_id", "review"}:
            raise ValueError("corpus listening review item differs")
        case_id = item.get("case_id")
        if case_id not in expected or case_id in supplied:
            raise ValueError("corpus listening case binding differs")
        if not isinstance(item.get("review"), dict):
            raise ValueError("corpus listening case review differs")
        if (
            item["review"].get("result_sha256")
            != expected[case_id]["result_document_sha256"]
            or item["review"].get("target_id") != expected[case_id]["target_id"]
        ):
            raise ValueError("corpus listening result binding differs")
        supplied[case_id] = item["review"]
    if set(supplied) != set(expected):
        raise ValueError("corpus listening bundle must contain every fixed case")
    _timestamp(bundle.get("exported_at"), "corpus listening exported_at")

    destination = Path(out).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"corpus feedback output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-", dir=destination.parent
        )
    )
    staging.chmod(0o700)
    try:
        raw_root, feedback_root = staging / "RAW", staging / "FEEDBACK"
        raw_root.mkdir(mode=0o700)
        feedback_root.mkdir(mode=0o700)
        records: list[dict[str, Any]] = []
        for case_id in sorted(expected):
            raw_path = raw_root / f"{case_id}.json"
            _write_private_json(raw_path, supplied[case_id])
            feedback_path = feedback_root / f"{case_id}.json"
            feedback = record_other_refinement_review(
                execution / "REFINEMENTS" / case_id,
                raw_path,
                out=feedback_path,
            )
            records.append(
                {
                    "case_id": case_id,
                    "target_id": expected[case_id]["target_id"],
                    "result_document_sha256": expected[case_id][
                        "result_document_sha256"
                    ],
                    "raw_review_sha256": file_sha256(raw_path),
                    "feedback_file_sha256": file_sha256(feedback_path),
                    "feedback_document_sha256": feedback["document_sha256"],
                    "usefulness": feedback["observations"]["usefulness"],
                }
            )
        feedback_index: dict[str, Any] = {
            "schema": CORPUS_FEEDBACK_INDEX_SCHEMA,
            "status": "ten_valid_reports_recorded_no_activation",
            "review_index_document_sha256": index["document_sha256"],
            "listening_bundle_file_sha256": file_sha256(source_bundle),
            "valid_report_count": len(records),
            "records": records,
            "feedback_policy": {
                "poor_or_mixed_feedback_disables_profile": False,
                "automatic_model_selection": False,
                "automatic_source_activation": False,
                "automatic_midi_activation": False,
            },
            "effects": {
                "audio_mutated": False,
                "model_executed": False,
                "network_used": False,
                "candidate_selected": False,
                "source_graph_mutated": False,
                "midi_created": False,
                "profile_status_changed": False,
            },
        }
        feedback_index["document_sha256"] = _document_sha256(feedback_index)
        _write_private_json(staging / "corpus-feedback-index.json", feedback_index)
        os.replace(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return feedback_index


def _prepare_case(
    *,
    track: Mapping[str, Any],
    case: Mapping[str, Any],
    cues: list[dict[str, Any]],
    authority: Mapping[str, Any],
    track_root: Path,
    execution: Path,
    staging: Path,
    ffmpeg: Path,
) -> dict[str, Any]:
    case_id, target_id = case["case_id"], case["target_id"]
    input_path = _regular_file(execution / "INPUTS" / f"{case_id}.wav", "case input")
    result_root = _real_directory(
        execution / "REFINEMENTS" / case_id, "case refinement result"
    )
    plan = _load_json(
        _regular_file(
            result_root / "TECHNICAL/other-refinement-plan.json", "refinement plan"
        ),
        "refinement plan",
    )
    result = _load_json(
        _regular_file(
            result_root / "TECHNICAL/other-refinement-result.json",
            "refinement result",
        ),
        "refinement result",
    )
    plan = validate_other_refinement_plan(plan)
    result = validate_other_refinement_result(result, plan=plan, root=result_root)
    if result["request"]["target_id"] != target_id:
        raise ValueError("corpus case target differs from refinement result")
    expected_frames = round((case["end_seconds"] - case["start_seconds"]) * 44_100)
    if (
        _pcm24_geometry(input_path)["frames"] != expected_frames
        or result["parent"]["geometry"]["frames"] != expected_frames
    ):
        raise ValueError("corpus case execution clock differs from frozen window")
    case_root = staging / "AUDIO" / case_id
    case_root.mkdir(parents=True, mode=0o700)
    sources = [
        ("source", "Source mix excerpt", input_path),
        ("parent", "SCNet grouped other parent", result_root / "PARENT/other.wav"),
        (
            "target",
            "Sunofriend guitar estimate"
            if target_id == "guitar"
            else "Sunofriend piano-proxy estimate",
            result_root / result["outputs"]["target"]["relative_path"],
        ),
        (
            "residual",
            "Exact grouped-other residual",
            result_root / "STEMS/other-residual.wav",
        ),
    ]
    audio: list[dict[str, Any]] = []
    for index, (kind, label, source) in enumerate(sources, start=1):
        source = _regular_file(source, f"case {kind} audio")
        target = case_root / f"{index:02d}-{kind}.wav"
        _copy_private(source, target)
        audio.append(_audio_item(staging, target, case_id, kind, label, None))

    reference_index = len(audio) + 1
    for cue in cues:
        matches = sorted(
            path
            for path in track_root.glob(cue["glob"])
            if path.is_file() and not path.is_symlink()
        )
        if not cue["minimum_matches"] <= len(matches) <= cue["maximum_matches"]:
            raise ValueError(
                f"{case_id} comparison cue match count differs: {cue['glob']}"
            )
        for provider_index, source in enumerate(matches, start=1):
            source = _regular_file_under(
                track_root, source, f"{case_id} provider comparison"
            )
            kind = f"reference-{reference_index:02d}"
            label = f"{cue['provider']} comparison {provider_index}"
            target = case_root / f"{reference_index:02d}-{kind}.wav"
            _extract_reference(
                ffmpeg,
                source,
                target,
                start_seconds=case["start_seconds"],
                duration_seconds=case["end_seconds"] - case["start_seconds"],
            )
            audio.append(
                _audio_item(
                    staging,
                    target,
                    case_id,
                    kind,
                    label,
                    cue["interpretation"],
                )
            )
            reference_index += 1
    ratio = result["outputs"]["target"]["rms"] / result["parent"]["rms"]
    return {
        "case_id": case_id,
        "track_id": track["track_id"],
        "display_name": track["display_name"],
        "target_id": target_id,
        "target_semantics": (
            "direct_experimental_guitar"
            if target_id == "guitar"
            else "piano_proxy_not_general_keyboards"
        ),
        "window": {
            "start_seconds": case["start_seconds"],
            "end_seconds": case["end_seconds"],
            "selection_score": case["selection_score"],
            "selection_score_proves_presence": False,
        },
        "result_document_sha256": result["document_sha256"],
        "authority": dict(authority),
        "objective": {
            "target_rms": result["outputs"]["target"]["rms"],
            "parent_rms": result["parent"]["rms"],
            "target_to_parent_rms_ratio": ratio,
            "rms_ratio_is_quality_score": False,
            "reconstruction_accounting_passed": result["additive_accounting"]["passed"],
            "maximum_reconstruction_error_lsb": result["additive_accounting"][
                "maximum_absolute_error_lsb"
            ],
            "network_used": result["execution"]["network_used"],
        },
        "audio": audio,
    }


def _validate_cues(target: str, value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{target} comparison cues are missing")
    validated: list[dict[str, Any]] = []
    for cue in value:
        if not isinstance(cue, dict) or set(cue) != {
            "provider",
            "glob",
            "interpretation",
            "minimum_matches",
            "maximum_matches",
        }:
            raise ValueError(f"{target} comparison cue fields differ")
        if cue.get("provider") not in {"Moises", "Suno"}:
            raise ValueError(f"{target} comparison cue provider differs")
        pattern = _safe_relative(cue.get("glob"), f"{target} comparison glob")
        if not pattern.lower().endswith(".wav"):
            raise ValueError(f"{target} comparison cue must select WAV audio")
        if "truth" not in str(cue.get("interpretation")) and target == "guitar":
            raise ValueError("guitar comparison cues must disclaim truth")
        minimum, maximum = cue.get("minimum_matches"), cue.get("maximum_matches")
        if (
            type(minimum) is not int
            or type(maximum) is not int
            or minimum < 0
            or maximum < minimum
            or maximum > 4
        ):
            raise ValueError(f"{target} comparison cue match ceiling differs")
        validated.append(dict(cue))
    return validated


def _extract_reference(
    ffmpeg: Path,
    source: Path,
    target: Path,
    *,
    start_seconds: float,
    duration_seconds: float,
) -> None:
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    completed = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-af",
            (
                f"atrim=start={start_seconds}:duration={duration_seconds},"
                "asetpts=PTS-STARTPTS,aresample=44100"
            ),
            "-ac",
            "2",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s24le",
            str(target),
        ],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
        env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
    )
    if completed.returncode:
        raise RuntimeError(
            f"provider reference extraction failed: {completed.stderr[:1000]}"
        )
    target.chmod(0o600)
    geometry = _pcm24_geometry(target)
    expected_frames = round(duration_seconds * 44_100)
    if geometry != {
        "sample_rate": 44_100,
        "channels": 2,
        "frames": expected_frames,
        "sample_width_bytes": 3,
    }:
        raise ValueError("provider comparison excerpt geometry differs")


def _audio_item(
    root: Path,
    path: Path,
    case_id: str,
    kind: str,
    label: str,
    interpretation: str | None,
) -> dict[str, Any]:
    value = {
        "kind": kind,
        "label": label,
        "route": f"/audio/{case_id}/{kind}.wav",
        "artifact": _artifact(root, path),
    }
    if interpretation is not None:
        value["provider_interpretation"] = interpretation
    return value


def _render_review(index: Mapping[str, Any]) -> str:
    cards: list[str] = []
    for number, case in enumerate(index["cases"], start=1):
        audio = []
        for item in case["audio"]:
            note = item.get("provider_interpretation")
            audio.append(
                '<article class="audio-card"><h3>'
                + html.escape(item["label"])
                + "</h3>"
                + (
                    f'<p class="small">{html.escape(note.replace("_", " "))}</p>'
                    if note
                    else ""
                )
                + f'<audio controls preload="metadata" src="{html.escape(item["route"])}"></audio></article>'
            )
        cards.append(
            f'''<section class="case" data-case="{html.escape(case["case_id"])}">
<div class="eyebrow">Case {number:02d} · {html.escape(case["target_id"])}</div>
<h2>{html.escape(case["display_name"])} — {html.escape(case["target_semantics"].replace("_", " "))}</h2>
<p>Fixed source window {case["window"]["start_seconds"]:.0f}–{case["window"]["end_seconds"]:.0f} s. Target RMS is {case["objective"]["target_to_parent_rms_ratio"] * 100:.2f}% of the grouped-other parent; that is a level observation, not a quality score.</p>
<div class="audio-grid">{"".join(audio)}</div>
<label class="check"><input class="listened" type="checkbox">I listened to the source, parent, target, residual and available provider comparisons.</label>
<div class="fields"><label>Usefulness<select class="usefulness"><option value="cannot_tell">Cannot tell</option><option value="useful">Useful</option><option value="mixed">Mixed</option><option value="not_useful">Not useful</option></select></label><label>Bleed<select class="bleed"><option>cannot_tell</option><option>none</option><option>some</option><option>severe</option></select></label><label>Missing target content<select class="missing"><option>cannot_tell</option><option>none</option><option>some</option><option>severe</option></select></label><label>Artefacts<select class="artefacts"><option>cannot_tell</option><option>none</option><option>some</option><option>severe</option></select></label><label>Timing/join problems<select class="timing"><option>cannot_tell</option><option>none</option><option>some</option><option>severe</option></select></label><label>Downstream MIDI<select class="midi"><option>not_tested</option><option>cannot_tell</option><option>improved</option><option>no_change</option><option>worse</option></select></label></div>
<label>Notes<textarea class="notes" maxlength="5000"></textarea></label>
<button type="button" class="download-one">Download this review JSON</button><button type="button" class="copy-one secondary">Copy text-only feedback</button><span class="message"></span>
</section>'''
        )
    bindings = [
        {
            "case_id": case["case_id"],
            "target_id": case["target_id"],
            "result_sha256": case["result_document_sha256"],
        }
        for case in index["cases"]
    ]
    bindings_json = json.dumps(bindings, separators=(",", ":"), ensure_ascii=True)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; connect-src 'none'; media-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>Sunofriend guitar and piano-proxy corpus review</title><style>
:root{{--ink:#f4f7fb;--muted:#b9c6d5;--night:#071321;--panel:#102031;--line:#31506a;--cyan:#4fe2ee}}*{{box-sizing:border-box}}body{{margin:0;background:var(--night);color:var(--ink);font:17px/1.5 system-ui,sans-serif}}main{{max-width:1240px;margin:auto;padding:30px 20px 90px}}h1{{font-size:clamp(2.4rem,7vw,5rem);line-height:1;margin:.2em 0}}.lede{{max-width:900px;font-size:1.15rem}}.notice,.case{{border:1px solid var(--line);border-radius:18px;background:var(--panel);padding:22px;margin:20px 0}}.notice{{border-left:6px solid #ffd666}}.eyebrow{{color:var(--cyan);font-weight:800;letter-spacing:.12em;text-transform:uppercase}}.audio-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}.audio-card{{background:#091522;border:1px solid var(--line);border-radius:12px;padding:13px}}.audio-card h3{{margin:.1em 0}}audio{{width:100%}}.small,.message{{color:var(--muted);font-size:.85rem}}label{{display:block;margin:12px 0;font-weight:650}}.check{{padding:14px;background:#152a3d;border-radius:10px}}input{{width:1.15rem;height:1.15rem;vertical-align:-.15rem}}select,textarea{{display:block;width:100%;margin-top:5px;padding:10px;background:#071321;color:var(--ink);border:1px solid var(--line);border-radius:8px;font:inherit}}textarea{{min-height:90px}}.fields{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}button{{border:0;border-radius:9px;padding:12px 16px;background:var(--cyan);font:inherit;font-weight:800;margin:5px;cursor:pointer}}button.secondary{{background:#244966;color:white}}.sticky{{position:sticky;bottom:0;background:#071321ee;border-top:1px solid var(--line);padding:14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}@media(max-width:800px){{.audio-grid,.fields{{grid-template-columns:1fr}}}}
</style></head><body><main><div class="eyebrow">Sunofriend · bounded local evaluation</div><h1>Five songs. Two targets. No automatic winner.</h1><p class="lede">Review exactly ten frozen cases. Moises and Suno stems are independent comparison estimates, never ground truth. The keys target is the model's piano proxy, not general keyboards or synths. Poor or mixed feedback remains evidence and does not disable the installed challenger.</p><div class="notice"><b>Privacy:</b> this localhost page makes no network requests and accepts no uploads. Review JSON contains result hashes and answers, but no audio, filenames or browser telemetry.</div>{"".join(cards)}<div class="sticky"><button id="download-all" type="button">Download all completed reviews</button><button id="copy-summary" class="secondary" type="button">Copy text-only summary</button><strong id="progress">0 / {len(bindings)} listened</strong><span id="global-message" class="message"></span></div></main><script>
const bindings={bindings_json};const indexHash='{index["document_sha256"]}';const sections=[...document.querySelectorAll('[data-case]')];const val=(section,selector)=>section.querySelector(selector).value;function review(section,binding){{return{{schema:'sunofriend.other-refinement-listening.v1',result_sha256:binding.result_sha256,target_id:binding.target_id,listened:section.querySelector('.listened').checked,usefulness:val(section,'.usefulness'),bleed:val(section,'.bleed'),missing_content:val(section,'.missing'),artefacts:val(section,'.artefacts'),timing_or_join_problems:val(section,'.timing'),downstream_midi:val(section,'.midi'),notes:val(section,'.notes'),activation_choice:'none',exported_at:new Date().toISOString()}}}}function saveJson(value,name){{const blob=new Blob([JSON.stringify(value,null,2)+'\n'],{{type:'application/json'}});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)}}function update(){{const count=sections.filter(section=>section.querySelector('.listened').checked).length;document.getElementById('progress').textContent=count+' / '+bindings.length+' listened'}}sections.forEach((section,index)=>{{section.addEventListener('change',update);section.querySelector('.download-one').onclick=()=>{{const data=review(section,bindings[index]);saveJson(data,'sunofriend-other-refinement-listening-'+bindings[index].case_id+'.json');section.querySelector('.message').textContent='Download requested.'}};section.querySelector('.copy-one').onclick=async()=>{{const d=review(section,bindings[index]);const text=`Sunofriend ${{bindings[index].target_id}} review: usefulness=${{d.usefulness}}; bleed=${{d.bleed}}; missing=${{d.missing_content}}; artefacts=${{d.artefacts}}; timing=${{d.timing_or_join_problems}}; MIDI=${{d.downstream_midi}}; notes=${{d.notes||'none'}}`;await navigator.clipboard.writeText(text);section.querySelector('.message').textContent='Text-only feedback copied.'}}}});document.getElementById('download-all').onclick=()=>{{const incomplete=sections.filter(section=>!section.querySelector('.listened').checked);if(incomplete.length){{document.getElementById('global-message').textContent='Listen to all ten cases before downloading the bounded bundle.';incomplete[0].scrollIntoView({{behavior:'smooth'}});return}}const data={{schema:'{CORPUS_LISTENING_SCHEMA}',review_index_sha256:indexHash,reviews:sections.map((section,index)=>({{case_id:bindings[index].case_id,review:review(section,bindings[index])}})),audio_included:false,filenames_included:false,browser_telemetry_included:false,exported_at:new Date().toISOString()}};saveJson(data,'sunofriend-other-refinement-corpus-listening.json');document.getElementById('global-message').textContent='Ten-review bundle download requested.'}};document.getElementById('copy-summary').onclick=async()=>{{const lines=sections.map((section,index)=>{{const d=review(section,bindings[index]);return `${{index+1}}. ${{bindings[index].target_id}}: ${{d.usefulness}}; bleed=${{d.bleed}}; missing=${{d.missing_content}}; artefacts=${{d.artefacts}}; timing=${{d.timing_or_join_problems}}; MIDI=${{d.downstream_midi}}; notes=${{d.notes||'none'}}`}});await navigator.clipboard.writeText(lines.join('\n'));document.getElementById('global-message').textContent='Text-only summary copied; no filenames or audio included.'}};update();
</script></body></html>"""


def _artifact(root: Path, path: Path) -> dict[str, Any]:
    geometry = _pcm24_geometry(path)
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
        **geometry,
    }


def _artifact_path(root: Path, value: Mapping[str, Any]) -> Path:
    relative = _safe_relative(value.get("relative_path"), "audio artifact path")
    path = _regular_file(
        root.joinpath(*PurePosixPath(relative).parts), "audio artifact"
    )
    if path.stat().st_size != value.get("bytes") or file_sha256(path) != value.get(
        "sha256"
    ):
        raise ValueError("corpus review audio artifact changed")
    expected = {
        field: value.get(field)
        for field in ("sample_rate", "channels", "frames", "sample_width_bytes")
    }
    if _pcm24_geometry(path) != expected:
        raise ValueError("corpus review audio geometry changed")
    return path


def _pcm24_geometry(path: Path) -> dict[str, int]:
    import soundfile

    with soundfile.SoundFile(str(path), "r") as source:
        value = {
            "sample_rate": source.samplerate,
            "channels": source.channels,
            "frames": source.frames,
            "sample_width_bytes": 3 if source.subtype == "PCM_24" else 0,
        }
    if (
        value["sample_rate"] != 44_100
        or value["channels"] != 2
        or value["frames"] <= 0
        or value["sample_width_bytes"] != 3
    ):
        raise ValueError("corpus review audio is not canonical PCM24")
    return value


def _copy_private(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o600)
    if file_sha256(source) != file_sha256(target):
        raise RuntimeError("corpus review audio copy differs")


def _write_private_json(path: Path, value: Mapping[str, Any]) -> None:
    if os.path.lexists(path):
        raise FileExistsError(f"private JSON already exists: {path}")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _regular_file(path: str | Path, label: str) -> Path:
    value = Path(path).expanduser().absolute()
    if not value.is_file() or value.is_symlink():
        raise ValueError(f"{label} must be a regular file")
    return value


def _regular_file_under(root: Path, path: Path, label: str) -> Path:
    """Return a regular descendant without following symlinked path components."""

    try:
        relative = path.absolute().relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must remain inside its track directory") from exc
    candidate = root
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            raise ValueError(f"{label} must not use symlinks")
    value = candidate.resolve(strict=True)
    if not value.is_file() or root not in value.parents:
        raise ValueError(f"{label} must be a regular track file")
    return value


def _real_directory(path: str | Path, label: str) -> Path:
    candidate = Path(path).expanduser().absolute()
    if candidate.is_symlink():
        raise ValueError(f"{label} must be a real directory")
    value = candidate.resolve(strict=True)
    if not value.is_dir():
        raise ValueError(f"{label} must be a real directory")
    return value


def _safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{label} is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must be a safe relative path")
    return value


def _token(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SAFE_TOKEN.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")
    return value


def _plain_text(value: Any, *, maximum: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _finite_positive(value: Any, label: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return float(value)


def _finite_nonnegative(value: Any, label: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return float(value)


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def _document_sha256(value: Mapping[str, Any]) -> str:
    document = dict(value)
    document.pop("document_sha256", None)
    return hashlib.sha256(
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "CORPUS_DEFINITION_SCHEMA",
    "CORPUS_FEEDBACK_INDEX_SCHEMA",
    "CORPUS_LISTENING_SCHEMA",
    "CORPUS_REVIEW_INDEX_SCHEMA",
    "build_other_refinement_corpus_review_server",
    "load_other_refinement_corpus_definition",
    "prepare_other_refinement_corpus_review",
    "record_other_refinement_corpus_reviews",
    "validate_other_refinement_corpus_authority",
]
