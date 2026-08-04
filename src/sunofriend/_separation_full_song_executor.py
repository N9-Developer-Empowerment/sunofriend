"""Resume the bounded private Kim worker over one sealed full-song plan.

This developer-only owner records every independently verified chunk attempt.
Interrupted or malformed attempts are retained as evidence and never trusted or
overwritten.  It does not stitch results, choose a stem, or enable a product
route.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile
from typing import Any, Callable, Mapping
import wave

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_full_song_plan import (
    CHUNK_REPORT_NAME,
    REPORT_NAME as PLAN_REPORT_NAME,
    SCHEMA as PLAN_SCHEMA,
    STATUS as PLAN_STATUS,
)
from ._separation_melroformer_native_attempt_darwin import (
    _EVIDENCE_SCHEMA,
    _TIMING_SCHEMA,
    _run_private_melroformer_native_attempt_darwin,
)
from ._separation_melroformer_real_bridge import (
    MAXIMUM_EXCERPT_FRAMES,
    MINIMUM_PROBE_FRAMES,
)
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)


SCHEMA = "sunofriend.private-separation-full-song-execution.v1"
REPORT_NAME = "private-separation-full-song-execution.json"
ATTEMPTS_DIRECTORY = "ATTEMPTS"
_INCOMPLETE_STATUS = "private_chunk_execution_incomplete_not_selected"
_COMPLETE_STATUS = "private_chunk_execution_complete_not_selected"
_SHA256_KEYS = (
    "evidence_sha256",
    "receipt_sha256",
    "timing_sha256",
)
_FALSE_PERMISSIONS = {
    "accepted": False,
    "automatic_selection": False,
    "source_graph_activation": False,
    "simple_mode_available": False,
    "studio_import_available": False,
    "product_route_permitted": False,
    "publication_permitted": False,
}
AttemptRunner = Callable[..., Mapping[str, Any]]


def _execute_private_separation_full_song_queue(
    plan_report_path: str | Path,
    *,
    out_dir: str | Path,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
    device: str = "gpu",
    maximum_chunks: int | None = 1,
    attempt_runner: AttemptRunner = _run_private_melroformer_native_attempt_darwin,
) -> dict[str, Any]:
    """Run and verify the next bounded queue entries, resuming safely."""

    if device not in {"gpu", "cpu"}:
        raise ValueError("private full-song execution device must be gpu or cpu")
    if maximum_chunks is not None and (
        isinstance(maximum_chunks, bool)
        or not isinstance(maximum_chunks, int)
        or maximum_chunks < 1
    ):
        raise ValueError("maximum chunks must be a positive integer or None")

    plan_path, plan, plan_sha256 = _load_verified_plan(plan_report_path)
    destination = Path(out_dir).expanduser().absolute()
    state = _load_or_create_state(destination, plan=plan, plan_sha256=plan_sha256)
    _verify_state_binding(state, plan=plan, plan_sha256=plan_sha256)
    _verify_completed_attempts(destination, state, plan)

    executed = 0
    for chunk, chunk_state in zip(plan["chunks"], state["chunks"]):
        if chunk_state["status"] == "verified_complete":
            continue
        if maximum_chunks is not None and executed >= maximum_chunks:
            break
        _record_untracked_attempts(destination, chunk_state)
        _write_state(destination, state)
        attempt_number = max(
            (item["attempt"] for item in chunk_state["attempts"]),
            default=0,
        ) + 1
        relative_attempt = (
            f"{ATTEMPTS_DIRECTORY}/chunk-{chunk['index']:04d}-"
            f"attempt-{attempt_number:03d}"
        )
        attempt = destination / relative_attempt
        authorisation = plan_path.parent / chunk["authorisation_report"]["path"]
        run_nonce = hashlib.sha256(
            (
                f"{state['execution_nonce']}:{plan_sha256}:"
                f"{chunk['index']}:{attempt_number}"
            ).encode("ascii")
        ).hexdigest()
        try:
            attempt_runner(
                run_nonce=run_nonce,
                repository_root=repository_root,
                runtime_launcher_path=runtime_launcher_path,
                source_root=source_root,
                checkpoint_path=checkpoint_path,
                companion_root=companion_root,
                authorisation_report_path=authorisation,
                authorisation_report_sha256=chunk["authorisation_report"]["sha256"],
                attempt_directory=attempt,
                device=device,
            )
            verified = _verify_attempt(
                attempt,
                expected_frames=chunk["frames"],
                expected_authorisation_sha256=chunk["authorisation_report"]["sha256"],
            )
        except BaseException as error:
            if os.path.lexists(attempt):
                chunk_state["attempts"].append(
                    {
                        "attempt": attempt_number,
                        "path": relative_attempt,
                        "status": "preserved_incomplete",
                        "failure_class": type(error).__name__,
                    }
                )
                _write_state(destination, state)
            raise
        chunk_state["attempts"].append(
            {
                "attempt": attempt_number,
                "path": relative_attempt,
                "status": "verified_complete",
                **verified,
            }
        )
        chunk_state["status"] = "verified_complete"
        chunk_state["selected_attempt"] = attempt_number
        executed += 1
        _write_state(destination, state)

    _refresh_summary(state)
    _write_state(destination, state)
    result = dict(state)
    result["report"] = str(destination / REPORT_NAME)
    result["output_directory"] = str(destination)
    result["chunks_executed_this_invocation"] = executed
    return result


def _load_verified_plan(
    value: str | Path,
) -> tuple[Path, dict[str, Any], str]:
    path = Path(value).expanduser().absolute()
    _require_private_regular(path, "private full-song plan")
    if path.name != PLAN_REPORT_NAME:
        raise ValueError("private full-song plan filename differs")
    raw_sha256 = _sha256(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private full-song plan JSON differs") from error
    if (
        not isinstance(document, dict)
        or document.get("schema") != PLAN_SCHEMA
        or document.get("status") != PLAN_STATUS
        or document.get("document_sha256") != _document_sha256(document)
    ):
        raise ValueError("private full-song plan identity differs")
    chunks = document.get("chunks")
    chunking = document.get("chunking")
    canonical = document.get("canonical_clock")
    if (
        not isinstance(chunks, list)
        or not isinstance(chunking, dict)
        or not isinstance(canonical, dict)
        or len(chunks) != chunking.get("chunk_count")
        or not chunks
    ):
        raise ValueError("private full-song plan chunk inventory differs")
    expected_start = 0
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise ValueError("private full-song plan chunk differs")
        frames = chunk.get("frames")
        start = chunk.get("start_frame")
        end = chunk.get("end_frame")
        if (
            chunk.get("index") != index
            or start != expected_start
            or end != start + frames
            or isinstance(frames, bool)
            or not isinstance(frames, int)
            or not MINIMUM_PROBE_FRAMES <= frames <= MAXIMUM_EXCERPT_FRAMES
        ):
            raise ValueError("private full-song plan chunk clock differs")
        expected_start = end
        _verify_plan_artifact(path.parent, chunk, "authorisation_report")
        _verify_plan_artifact(path.parent, chunk, "audio_artifact")
        report = path.parent / chunk["authorisation_report"]["path"]
        if report.name != CHUNK_REPORT_NAME:
            raise ValueError("private full-song chunk authorisation name differs")
        authorisation = json.loads(report.read_text(encoding="utf-8"))
        geometry = authorisation.get("original", {}).get("local_model_input", {}).get(
            "geometry", {}
        )
        if (
            authorisation.get("document_sha256") != _document_sha256(authorisation)
            or authorisation.get("document_sha256")
            != chunk["authorisation_report"]["document_sha256"]
            or geometry.get("frames") != frames
            or geometry.get("sample_rate") != 44_100
            or geometry.get("channels") != 2
        ):
            raise ValueError("private full-song chunk authorisation differs")
    if expected_start != canonical.get("frames"):
        raise ValueError("private full-song plan coverage differs")
    return path, document, raw_sha256


def _verify_plan_artifact(root: Path, chunk: Mapping[str, Any], key: str) -> None:
    claim = chunk.get(key)
    if not isinstance(claim, Mapping):
        raise ValueError("private full-song plan artifact claim differs")
    relative = claim.get("path")
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("private full-song plan artifact path differs")
    path = root / relative
    _require_private_regular(path, "private full-song plan artifact")
    if path.stat().st_size != claim.get("bytes") or _sha256(path) != claim.get("sha256"):
        raise ValueError("private full-song plan artifact hash differs")


def _load_or_create_state(
    destination: Path,
    *,
    plan: Mapping[str, Any],
    plan_sha256: str,
) -> dict[str, Any]:
    report = destination / REPORT_NAME
    if not os.path.lexists(destination):
        destination.mkdir(parents=True, mode=0o700)
        destination.chmod(0o700)
        (destination / ATTEMPTS_DIRECTORY).mkdir(mode=0o700)
        state: dict[str, Any] = {
            "schema": SCHEMA,
            "status": _INCOMPLETE_STATUS,
            "evidence_scope": "private_development_only",
            "execution_nonce": secrets.token_hex(32),
            "bindings": {
                "plan_report_sha256": plan_sha256,
                "plan_document_sha256": plan["document_sha256"],
                "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
                "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
                "canonical_frames": plan["canonical_clock"]["frames"],
                "chunk_count": len(plan["chunks"]),
            },
            "summary": {},
            "chunks": [
                {
                    "index": chunk["index"],
                    "frames": chunk["frames"],
                    "authorisation_report_sha256": chunk["authorisation_report"]["sha256"],
                    "status": "not_run",
                    "selected_attempt": None,
                    "attempts": [],
                }
                for chunk in plan["chunks"]
            ],
            "permissions": dict(_FALSE_PERMISSIONS),
            "limitations": [
                "Chunk execution evidence is not separator quality acceptance.",
                "Completed chunks remain unstitched and unselected.",
                "No public CLI, TUI, Simple, Studio or source-graph route is enabled.",
            ],
        }
        _refresh_summary(state)
        _write_state(destination, state)
        return state
    _require_private_directory(destination, "private full-song execution root")
    _require_private_directory(
        destination / ATTEMPTS_DIRECTORY,
        "private full-song attempts root",
    )
    _require_private_regular(report, "private full-song execution report")
    try:
        state = json.loads(report.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private full-song execution report JSON differs") from error
    return state


def _verify_state_binding(
    state: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    plan_sha256: str,
) -> None:
    bindings = state.get("bindings")
    chunks = state.get("chunks")
    if (
        state.get("schema") != SCHEMA
        or state.get("state_sha256") != _state_sha256(state)
        or state.get("permissions") != _FALSE_PERMISSIONS
        or not isinstance(bindings, Mapping)
        or bindings
        != {
            "plan_report_sha256": plan_sha256,
            "plan_document_sha256": plan["document_sha256"],
            "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            "canonical_frames": plan["canonical_clock"]["frames"],
            "chunk_count": len(plan["chunks"]),
        }
        or not isinstance(chunks, list)
        or len(chunks) != len(plan["chunks"])
        or not isinstance(state.get("execution_nonce"), str)
        or len(state["execution_nonce"]) != 64
    ):
        raise ValueError("private full-song execution state differs")
    for expected, actual in zip(plan["chunks"], chunks):
        if (
            not isinstance(actual, Mapping)
            or actual.get("index") != expected["index"]
            or actual.get("frames") != expected["frames"]
            or actual.get("authorisation_report_sha256")
            != expected["authorisation_report"]["sha256"]
            or actual.get("status") not in {"not_run", "verified_complete"}
            or not isinstance(actual.get("attempts"), list)
        ):
            raise ValueError("private full-song execution chunk state differs")


def _record_untracked_attempts(root: Path, chunk_state: dict[str, Any]) -> None:
    known = {item["path"] for item in chunk_state["attempts"]}
    prefix = f"chunk-{chunk_state['index']:04d}-attempt-"
    for path in sorted((root / ATTEMPTS_DIRECTORY).glob(f"{prefix}*")):
        relative = path.relative_to(root).as_posix()
        if relative in known:
            continue
        _require_private_directory(path, "preserved incomplete attempt")
        suffix = path.name.removeprefix(prefix)
        if len(suffix) != 3 or not suffix.isdigit():
            raise ValueError("private full-song attempt name differs")
        chunk_state["attempts"].append(
            {
                "attempt": int(suffix),
                "path": relative,
                "status": "preserved_incomplete",
                "failure_class": "interrupted_or_unrecorded",
            }
        )
    chunk_state["attempts"].sort(key=lambda item: item["attempt"])


def _verify_completed_attempts(
    root: Path,
    state: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> None:
    for chunk_state, chunk in zip(state["chunks"], plan["chunks"]):
        if chunk_state["status"] != "verified_complete":
            continue
        selected = chunk_state.get("selected_attempt")
        records = [
            item
            for item in chunk_state["attempts"]
            if item.get("attempt") == selected
            and item.get("status") == "verified_complete"
        ]
        if len(records) != 1:
            raise ValueError("private full-song selected attempt differs")
        observed = _verify_attempt(
            root / records[0]["path"],
            expected_frames=chunk["frames"],
            expected_authorisation_sha256=chunk["authorisation_report"]["sha256"],
        )
        for key in _SHA256_KEYS:
            if records[0].get(key) != observed[key]:
                raise ValueError("private full-song completed attempt changed")


def _verify_attempt(
    attempt: Path,
    *,
    expected_frames: int,
    expected_authorisation_sha256: str,
) -> dict[str, Any]:
    _require_private_directory(attempt, "private full-song attempt")
    evidence = _load_hashed_json(
        attempt / "native-attempt-evidence.json",
        key="evidence_sha256",
    )
    receipt = _load_hashed_json(
        attempt / "native-attempt-receipt.json",
        key="receipt_sha256",
    )
    timing = _load_hashed_json(
        attempt / "native-attempt-timing.json",
        key="timing_sha256",
    )
    bindings = evidence.get("bindings", {})
    if (
        evidence.get("schema") != _EVIDENCE_SCHEMA
        or evidence.get("status") != "private_native_attempt_verified_not_selected"
        or bindings.get("authorisation_report_sha256")
        != expected_authorisation_sha256
        or bindings.get("checkpoint_sha256") != CONVERSION_CHECKPOINT_SHA256
        or bindings.get("checkpoint_bytes") != CONVERSION_CHECKPOINT_BYTES
        or receipt.get("schema")
        != "sunofriend.private-melroformer-native-coordinator.v1"
        or receipt.get("status") != "private_native_worker_complete_and_terminal"
        or receipt.get("request_sha256") != bindings.get("request_sha256")
        or receipt.get("receipt_sha256")
        != bindings.get("terminal_receipt_sha256")
        or timing.get("schema") != _TIMING_SCHEMA
        or timing.get("bindings", {}).get("request_sha256")
        != bindings.get("request_sha256")
        or timing.get("bindings", {}).get("terminal_receipt_sha256")
        != receipt.get("receipt_sha256")
        or timing.get("bindings", {}).get("output_evidence_sha256")
        != evidence.get("evidence_sha256")
        or not _all_false_permissions(evidence.get("permissions"))
        or not _all_false_permissions(receipt.get("permissions"))
        or not _all_false_permissions(timing.get("permissions"))
    ):
        raise ValueError("private full-song attempt evidence differs")
    outputs = evidence.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != 2:
        raise ValueError("private full-song attempt output inventory differs")
    by_role = {item.get("role"): item for item in outputs if isinstance(item, Mapping)}
    if set(by_role) != {"instrumental", "vocals"}:
        raise ValueError("private full-song attempt roles differ")
    output_claims: dict[str, Any] = {}
    for role in ("instrumental", "vocals"):
        path = attempt / "staging" / "quarantine" / "STEMS" / f"{role}.wav"
        _require_private_regular(path, "private full-song output")
        claim = by_role[role]
        with wave.open(str(path), "rb") as reader:
            geometry = {
                "sample_rate": reader.getframerate(),
                "channels": reader.getnchannels(),
                "sample_width_bytes": reader.getsampwidth(),
                "frames": reader.getnframes(),
            }
            if reader.getcomptype() != "NONE":
                raise ValueError("private full-song output compression differs")
        if (
            geometry
            != {
                "sample_rate": 44_100,
                "channels": 2,
                "sample_width_bytes": 3,
                "frames": expected_frames,
            }
            or path.stat().st_size != claim.get("bytes")
            or _sha256(path) != claim.get("sha256")
            or dict(claim.get("geometry", {})) != geometry
        ):
            raise ValueError("private full-song output binding differs")
        output_claims[role] = {
            "sha256": claim["sha256"],
            "bytes": claim["bytes"],
            "frames": expected_frames,
        }
    return {
        "evidence_sha256": evidence["evidence_sha256"],
        "receipt_sha256": receipt["receipt_sha256"],
        "timing_sha256": timing["timing_sha256"],
        "outputs": output_claims,
    }


def _load_hashed_json(path: Path, *, key: str) -> dict[str, Any]:
    _require_private_regular(path, "private full-song attempt JSON")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private full-song attempt JSON differs") from error
    if not isinstance(document, dict):
        raise ValueError("private full-song attempt JSON is not an object")
    claimed = document.get(key)
    payload = dict(document)
    payload.pop(key, None)
    if claimed != hashlib.sha256(canonical_json_bytes(payload)).hexdigest():
        raise ValueError("private full-song attempt JSON self-hash differs")
    return document


def _refresh_summary(state: dict[str, Any]) -> None:
    complete = sum(chunk["status"] == "verified_complete" for chunk in state["chunks"])
    total = len(state["chunks"])
    state["status"] = _COMPLETE_STATUS if complete == total else _INCOMPLETE_STATUS
    state["summary"] = {
        "total_chunks": total,
        "verified_chunks": complete,
        "remaining_chunks": total - complete,
        "all_worker_runs_complete": complete == total,
        "stitched_outputs_complete": False,
        "human_boundary_review_complete": False,
        "quality_accepted": False,
    }


def _all_false_permissions(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and bool(value)
        and all(item is False for item in value.values())
    )


def _state_sha256(state: Mapping[str, Any]) -> str:
    payload = dict(state)
    payload.pop("state_sha256", None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _write_state(root: Path, state: dict[str, Any]) -> None:
    _refresh_summary(state)
    state["state_sha256"] = _state_sha256(state)
    payload = (
        json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{REPORT_NAME}.",
        dir=root,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.chmod(0o600)
        temporary.write_bytes(payload)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, root / REPORT_NAME)
        (root / REPORT_NAME).chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _require_private_regular(path: Path, label: str) -> None:
    try:
        state = path.lstat()
    except OSError as error:
        raise ValueError(f"{label} is unavailable") from error
    if (
        stat.S_ISLNK(state.st_mode)
        or not stat.S_ISREG(state.st_mode)
        or state.st_nlink != 1
        or state.st_uid != os.geteuid()
        or stat.S_IMODE(state.st_mode) & 0o077
    ):
        raise ValueError(f"{label} is not an owner-only regular file")


def _require_private_directory(path: Path, label: str) -> None:
    try:
        state = path.lstat()
    except OSError as error:
        raise ValueError(f"{label} is unavailable") from error
    if (
        stat.S_ISLNK(state.st_mode)
        or not stat.S_ISDIR(state.st_mode)
        or state.st_uid != os.geteuid()
        or stat.S_IMODE(state.st_mode) & 0o077
    ):
        raise ValueError(f"{label} is not an owner-only directory")


__all__: tuple[str, ...] = ()
