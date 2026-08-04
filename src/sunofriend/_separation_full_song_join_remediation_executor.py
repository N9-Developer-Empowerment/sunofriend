"""Execute sealed full-song join-remediation windows as separate candidates.

This owner-only developer contract reuses the audited private Kim worker for
the exact windows in a verified remediation plan.  It preserves every attempt,
keeps the raw stitch immutable, and creates a separate candidate set only after
all worker outputs have been independently reverified.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import tempfile
from typing import Any, Callable, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_full_song_executor import (
    _load_verified_plan,
    _require_private_directory,
    _require_private_regular,
    _verify_attempt,
)
from ._separation_full_song_join_remediation_plan import (
    POLICY_ID as PLAN_POLICY_ID,
    REPORT_NAME as PLAN_REPORT_NAME,
    SCHEMA as PLAN_SCHEMA,
    STATUS as PLAN_STATUS,
)
from ._separation_full_song_plan import (
    CHUNK_REPORT_NAME,
    _FALSE_PERMISSIONS as AUTHORISATION_FALSE_PERMISSIONS,
)
from ._separation_full_song_review import (
    _load_stitch_report,
    _verify_stitch_audio,
)
from ._separation_full_song_stitch import REPORT_NAME as STITCH_REPORT_NAME
from ._separation_melroformer_native_attempt_darwin import (
    _run_private_melroformer_native_attempt_darwin,
)
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)


SCHEMA = "sunofriend.private-separation-full-song-join-remediation-execution.v1"
STATUS_INCOMPLETE = "targeted_join_remediation_execution_incomplete_not_selected"
STATUS_COMPLETE = "targeted_join_remediation_candidates_complete_review_required"
REPORT_NAME = "private-separation-full-song-join-remediation-execution.json"
CANDIDATE_REPORT_NAME = "private-separation-full-song-join-remediation-candidates.json"
ATTEMPTS_DIRECTORY = "ATTEMPTS"
WINDOWS_DIRECTORY = "WINDOWS"
CANDIDATES_DIRECTORY = "CANDIDATES"
TARGET_SAMPLE_RATE = 44_100
_ROLES = ("vocals", "instrumental")
_FALSE_PERMISSIONS = {
    "accepted": False,
    "automatic_selection": False,
    "product_route_permitted": False,
    "publication_permitted": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
}
AttemptRunner = Callable[..., Mapping[str, Any]]


def _execute_private_separation_full_song_join_remediation(
    remediation_plan_path: str | Path,
    *,
    package_dir: str | Path,
    source_plan_path: str | Path,
    out_dir: str | Path,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
    device: str = "gpu",
    maximum_windows: int | None = 1,
    attempt_runner: AttemptRunner = _run_private_melroformer_native_attempt_darwin,
) -> dict[str, Any]:
    """Resume verified remediation work and build candidates when complete."""

    if device not in {"gpu", "cpu"}:
        raise ValueError("private join-remediation device must be gpu or cpu")
    if maximum_windows is not None and (
        isinstance(maximum_windows, bool)
        or not isinstance(maximum_windows, int)
        or maximum_windows < 1
    ):
        raise ValueError("maximum windows must be a positive integer or None")

    plan_path, plan, plan_sha256 = _load_remediation_plan(remediation_plan_path)
    package, stitch, stitch_path = _load_bound_stitch(package_dir, plan)
    full_plan_path, full_plan, full_plan_sha256 = _load_verified_plan(source_plan_path)
    _verify_full_plan_binding(
        full_plan,
        full_plan_sha256=full_plan_sha256,
        stitch=stitch,
        plan=plan,
    )

    destination = Path(out_dir).expanduser().absolute()
    state = _load_or_create_state(
        destination,
        remediation_plan=plan,
        remediation_plan_sha256=plan_sha256,
        stitch=stitch,
        stitch_sha256=_sha256(stitch_path),
        full_plan=full_plan,
        full_plan_sha256=full_plan_sha256,
        package=package,
        full_plan_path=full_plan_path,
    )
    _verify_state(
        destination,
        state,
        remediation_plan=plan,
        remediation_plan_sha256=plan_sha256,
        stitch=stitch,
        stitch_sha256=_sha256(stitch_path),
        full_plan=full_plan,
        full_plan_sha256=full_plan_sha256,
    )

    executed = 0
    for planned, window_state in zip(plan["windows"], state["windows"]):
        if window_state["status"] == "verified_complete":
            continue
        if maximum_windows is not None and executed >= maximum_windows:
            break
        _record_untracked_attempts(destination, window_state)
        _write_state(destination, state)
        attempt_number = max(
            (item["attempt"] for item in window_state["attempts"]),
            default=0,
        ) + 1
        relative_attempt = (
            f"{ATTEMPTS_DIRECTORY}/window-{planned['window_index']:04d}-"
            f"attempt-{attempt_number:03d}"
        )
        attempt = destination / relative_attempt
        authorisation = destination / window_state["authorisation_report"]["path"]
        run_nonce = hashlib.sha256(
            (
                f"{state['execution_nonce']}:{plan_sha256}:"
                f"{planned['window_index']}:{attempt_number}"
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
                authorisation_report_sha256=window_state["authorisation_report"][
                    "sha256"
                ],
                attempt_directory=attempt,
                device=device,
            )
            verified = _verify_attempt(
                attempt,
                expected_frames=planned["source_end_frame"]
                - planned["source_start_frame"],
                expected_authorisation_sha256=window_state["authorisation_report"][
                    "sha256"
                ],
            )
        except BaseException as error:
            if os.path.lexists(attempt):
                window_state["attempts"].append(
                    {
                        "attempt": attempt_number,
                        "path": relative_attempt,
                        "status": "preserved_incomplete",
                        "failure_class": type(error).__name__,
                    }
                )
                _write_state(destination, state)
            raise
        window_state["attempts"].append(
            {
                "attempt": attempt_number,
                "path": relative_attempt,
                "status": "verified_complete",
                **verified,
            }
        )
        window_state["status"] = "verified_complete"
        window_state["selected_attempt"] = attempt_number
        executed += 1
        _write_state(destination, state)

    if all(item["status"] == "verified_complete" for item in state["windows"]):
        if state.get("candidate_report") is None:
            candidate = _build_candidates(
                destination,
                state=state,
                remediation_plan=plan,
                package=package,
                stitch=stitch,
            )
            state["candidate_report"] = {
                "path": CANDIDATE_REPORT_NAME,
                "sha256": _sha256(destination / CANDIDATE_REPORT_NAME),
                "document_sha256": candidate["document_sha256"],
                "bytes": (destination / CANDIDATE_REPORT_NAME).stat().st_size,
            }
            _write_state(destination, state)
        else:
            _verify_candidate_report(destination, state, stitch=stitch)

    _write_state(destination, state)
    result = dict(state)
    result["report"] = str(destination / REPORT_NAME)
    result["candidate_report_path"] = (
        str(destination / CANDIDATE_REPORT_NAME)
        if state.get("candidate_report") is not None
        else None
    )
    result["output_directory"] = str(destination)
    result["windows_executed_this_invocation"] = executed
    return result


def _load_remediation_plan(value: str | Path) -> tuple[Path, dict[str, Any], str]:
    path = Path(value).expanduser().absolute()
    _require_private_regular(path, "private join-remediation plan")
    if path.name != PLAN_REPORT_NAME:
        raise ValueError("private join-remediation plan filename differs")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private join-remediation plan JSON differs") from error
    if (
        not isinstance(document, dict)
        or document.get("schema") != PLAN_SCHEMA
        or document.get("status") != PLAN_STATUS
        or document.get("policy_id") != PLAN_POLICY_ID
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _FALSE_PERMISSIONS
        or not _all_false(document.get("effects"))
    ):
        raise ValueError("private join-remediation plan identity differs")
    windows = document.get("windows")
    if not isinstance(windows, list) or not windows:
        raise ValueError("private join-remediation window inventory differs")
    return path, document, _sha256(path)


def _load_bound_stitch(
    value: str | Path,
    remediation_plan: Mapping[str, Any],
) -> tuple[Path, dict[str, Any], Path]:
    package = Path(value).expanduser().absolute()
    _require_private_directory(package, "private stitch package")
    stitch_path = package / STITCH_REPORT_NAME
    stitch = _load_stitch_report(stitch_path)
    _verify_stitch_audio(package, stitch)
    bindings = remediation_plan["bindings"]
    if (
        _sha256(stitch_path) != bindings["stitch_report_sha256"]
        or stitch["document_sha256"] != bindings["stitch_document_sha256"]
        or stitch["clock"] != remediation_plan["clock"]
        or stitch["artifacts"]["source"]["sha256"]
        != bindings["source_audio_sha256"]
        or stitch["artifacts"]["vocals"]["sha256"]
        != bindings["raw_vocals_audio_sha256"]
        or stitch["artifacts"]["instrumental"]["sha256"]
        != bindings["raw_instrumental_audio_sha256"]
        or stitch["artifacts"]["reconstruction"]["sha256"]
        != bindings["raw_reconstruction_audio_sha256"]
    ):
        raise ValueError("private join-remediation stitch binding differs")
    return package, stitch, stitch_path


def _verify_full_plan_binding(
    full_plan: Mapping[str, Any],
    *,
    full_plan_sha256: str,
    stitch: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> None:
    if (
        full_plan_sha256 != stitch["bindings"]["plan_report_sha256"]
        or full_plan["document_sha256"]
        != stitch["bindings"]["plan_document_sha256"]
        or full_plan["document_sha256"] != plan["bindings"]["plan_document_sha256"]
        or full_plan["canonical_clock"]["frames"] != stitch["clock"]["frames"]
        or full_plan["canonical_clock"]["sample_rate"] != TARGET_SAMPLE_RATE
        or full_plan["canonical_clock"]["channels"] != 2
        or full_plan["canonical_clock"]["pcm24_int32_sequence_sha256"]
        != stitch["artifacts"]["source"]["pcm24_int32_sequence_sha256"]
    ):
        raise ValueError("private join-remediation source plan binding differs")


def _load_or_create_state(
    destination: Path,
    *,
    remediation_plan: Mapping[str, Any],
    remediation_plan_sha256: str,
    stitch: Mapping[str, Any],
    stitch_sha256: str,
    full_plan: Mapping[str, Any],
    full_plan_sha256: str,
    package: Path,
    full_plan_path: Path,
) -> dict[str, Any]:
    report = destination / REPORT_NAME
    if os.path.lexists(destination):
        _require_private_directory(destination, "private remediation execution root")
        _require_private_regular(report, "private remediation execution report")
        try:
            state = json.loads(report.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("private remediation execution state differs") from error
        return state

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=destination.parent)
    )
    temporary.chmod(0o700)
    try:
        (temporary / ATTEMPTS_DIRECTORY).mkdir(mode=0o700)
        (temporary / WINDOWS_DIRECTORY).mkdir(mode=0o700)
        authorisations = _write_window_authorisations(
            temporary,
            remediation_plan=remediation_plan,
            package=package,
            stitch=stitch,
            full_plan=full_plan,
            full_plan_path=full_plan_path,
        )
        state: dict[str, Any] = {
            "schema": SCHEMA,
            "status": STATUS_INCOMPLETE,
            "evidence_scope": "private_development_only",
            "execution_nonce": secrets.token_hex(32),
            "bindings": {
                "remediation_plan_sha256": remediation_plan_sha256,
                "remediation_plan_document_sha256": remediation_plan[
                    "document_sha256"
                ],
                "stitch_report_sha256": stitch_sha256,
                "stitch_document_sha256": stitch["document_sha256"],
                "source_plan_sha256": full_plan_sha256,
                "source_plan_document_sha256": full_plan["document_sha256"],
                "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
                "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            },
            "clock": dict(remediation_plan["clock"]),
            "protocol": dict(remediation_plan["protocol"]),
            "windows": [
                {
                    "window_index": planned["window_index"],
                    "boundary_index": planned["boundary_index"],
                    "source_start_frame": planned["source_start_frame"],
                    "source_end_frame": planned["source_end_frame"],
                    "patch_start_frame": planned["patch_start_frame"],
                    "patch_end_frame": planned["patch_end_frame"],
                    "patch_target_roles": list(planned["patch_target_roles"]),
                    "authorisation_report": authorisation,
                    "status": "not_run",
                    "selected_attempt": None,
                    "attempts": [],
                }
                for planned, authorisation in zip(
                    remediation_plan["windows"], authorisations
                )
            ],
            "candidate_report": None,
            "summary": {},
            "permissions": dict(_FALSE_PERMISSIONS),
            "effects": {},
            "limitations": [
                "Re-inference candidates are separate from the immutable raw stitch.",
                "Candidate creation is not repair success, preference or separator acceptance.",
                "Blind boundary, patch-edge and complete-song listening remain required.",
                "No public CLI, TUI, Simple, Studio or source-graph route is enabled.",
            ],
        }
        _write_state(temporary, state)
        _make_private_tree(temporary)
        os.replace(temporary, destination)
        return state
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _write_window_authorisations(
    root: Path,
    *,
    remediation_plan: Mapping[str, Any],
    package: Path,
    stitch: Mapping[str, Any],
    full_plan: Mapping[str, Any],
    full_plan_path: Path,
) -> list[dict[str, Any]]:
    import soundfile

    first = full_plan["chunks"][0]
    first_report_path = full_plan_path.parent / first["authorisation_report"]["path"]
    _require_private_regular(first_report_path, "private source authorisation")
    first_report = json.loads(first_report_path.read_text(encoding="utf-8"))
    if (
        _sha256(first_report_path) != first["authorisation_report"]["sha256"]
        or first_report.get("document_sha256") != _document_sha256(first_report)
    ):
        raise ValueError("private source authorisation changed")
    source_path = package / stitch["artifacts"]["source"]["path"]
    source_info = soundfile.info(source_path)
    if (
        int(source_info.samplerate) != TARGET_SAMPLE_RATE
        or int(source_info.channels) != 2
        or int(source_info.frames) != stitch["clock"]["frames"]
        or source_info.subtype != "PCM_24"
    ):
        raise ValueError("private remediation canonical source geometry differs")

    claims: list[dict[str, Any]] = []
    for planned in remediation_plan["windows"]:
        window_index = int(planned["window_index"])
        window_root = root / WINDOWS_DIRECTORY / f"window-{window_index:04d}"
        audio = window_root / "LOCAL-MODEL-INPUT" / "source-44100.wav"
        audio.parent.mkdir(parents=True, mode=0o700)
        value, rate = soundfile.read(
            source_path,
            start=int(planned["source_start_frame"]),
            stop=int(planned["source_end_frame"]),
            dtype="float32",
            always_2d=True,
        )
        frames = int(planned["source_end_frame"] - planned["source_start_frame"])
        if int(rate) != TARGET_SAMPLE_RATE or value.shape != (frames, 2):
            raise ValueError("private remediation source window differs")
        soundfile.write(audio, value, TARGET_SAMPLE_RATE, subtype="PCM_24")
        audio.chmod(0o600)
        artifact = {
            "path": "LOCAL-MODEL-INPUT/source-44100.wav",
            "sha256": _sha256(audio),
            "bytes": audio.stat().st_size,
        }
        geometry = {
            "sample_rate": TARGET_SAMPLE_RATE,
            "channels": 2,
            "frames": frames,
            "duration_seconds": frames / TARGET_SAMPLE_RATE,
        }
        report: dict[str, Any] = {
            "schema": first_report["schema"],
            "status": "complete_review_required",
            "evidence_scope": "private_development_only",
            "corpus": dict(first_report["corpus"]),
            "excerpt": {
                "start_seconds": planned["source_start_frame"] / TARGET_SAMPLE_RATE,
                "end_seconds": planned["source_end_frame"] / TARGET_SAMPLE_RATE,
                "selection_policy": PLAN_POLICY_ID,
                "join_remediation_window_index": window_index,
                "boundary_index": planned["boundary_index"],
                "canonical_start_frame": planned["source_start_frame"],
                "canonical_end_frame": planned["source_end_frame"],
            },
            "original": {
                "source": dict(first_report["original"]["source"]),
                "local_model_input": {
                    "artifact": artifact,
                    "geometry": geometry,
                    "derivation": dict(
                        first_report["original"]["local_model_input"]["derivation"]
                    ),
                },
            },
            "permissions": dict(AUTHORISATION_FALSE_PERMISSIONS),
            "effects": {
                "local_excerpt_created": True,
                "model_run": False,
                "source_audio_mutated": False,
                "source_graph_mutated": False,
            },
            "limitations": [
                "This is one exact source-clock window from a reviewed join-remediation plan.",
                "The worker result remains a separately reviewed candidate and cannot replace the raw stitch automatically.",
            ],
        }
        report["document_sha256"] = _document_sha256(report)
        report_path = window_root / CHUNK_REPORT_NAME
        _write_json_exclusive(report_path, report)
        claims.append(
            {
                "path": report_path.relative_to(root).as_posix(),
                "sha256": _sha256(report_path),
                "document_sha256": report["document_sha256"],
                "bytes": report_path.stat().st_size,
                "audio": {
                    "path": audio.relative_to(root).as_posix(),
                    "sha256": artifact["sha256"],
                    "bytes": artifact["bytes"],
                    "frames": frames,
                },
            }
        )
    return claims


def _verify_state(
    root: Path,
    state: Mapping[str, Any],
    *,
    remediation_plan: Mapping[str, Any],
    remediation_plan_sha256: str,
    stitch: Mapping[str, Any],
    stitch_sha256: str,
    full_plan: Mapping[str, Any],
    full_plan_sha256: str,
) -> None:
    expected_bindings = {
        "remediation_plan_sha256": remediation_plan_sha256,
        "remediation_plan_document_sha256": remediation_plan["document_sha256"],
        "stitch_report_sha256": stitch_sha256,
        "stitch_document_sha256": stitch["document_sha256"],
        "source_plan_sha256": full_plan_sha256,
        "source_plan_document_sha256": full_plan["document_sha256"],
        "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
        "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
    }
    windows = state.get("windows")
    if (
        state.get("schema") != SCHEMA
        or state.get("state_sha256") != _state_sha256(state)
        or state.get("bindings") != expected_bindings
        or state.get("clock") != remediation_plan["clock"]
        or state.get("protocol") != remediation_plan["protocol"]
        or state.get("permissions") != _FALSE_PERMISSIONS
        or not isinstance(state.get("execution_nonce"), str)
        or len(state["execution_nonce"]) != 64
        or not isinstance(windows, list)
        or len(windows) != len(remediation_plan["windows"])
    ):
        raise ValueError("private remediation execution state binding differs")
    for planned, actual in zip(remediation_plan["windows"], windows):
        if (
            actual.get("window_index") != planned["window_index"]
            or actual.get("boundary_index") != planned["boundary_index"]
            or actual.get("source_start_frame") != planned["source_start_frame"]
            or actual.get("source_end_frame") != planned["source_end_frame"]
            or actual.get("patch_start_frame") != planned["patch_start_frame"]
            or actual.get("patch_end_frame") != planned["patch_end_frame"]
            or actual.get("patch_target_roles") != planned["patch_target_roles"]
            or actual.get("status") not in {"not_run", "verified_complete"}
            or not isinstance(actual.get("attempts"), list)
        ):
            raise ValueError("private remediation execution window differs")
        _verify_authorisation(root, actual["authorisation_report"], planned)
        if actual["status"] == "verified_complete":
            selected = _selected_attempt_record(actual)
            observed = _verify_attempt(
                root / selected["path"],
                expected_frames=planned["source_end_frame"]
                - planned["source_start_frame"],
                expected_authorisation_sha256=actual["authorisation_report"][
                    "sha256"
                ],
            )
            for key in ("evidence_sha256", "receipt_sha256", "timing_sha256"):
                if selected.get(key) != observed[key]:
                    raise ValueError("private remediation selected attempt changed")
    if state.get("candidate_report") is not None:
        _verify_candidate_report(root, state, stitch=stitch)


def _verify_authorisation(
    root: Path,
    claim: Mapping[str, Any],
    planned: Mapping[str, Any],
) -> None:
    report = root / claim["path"]
    audio = root / claim["audio"]["path"]
    _require_private_regular(report, "private remediation authorisation")
    _require_private_regular(audio, "private remediation window audio")
    document = json.loads(report.read_text(encoding="utf-8"))
    if (
        _sha256(report) != claim["sha256"]
        or report.stat().st_size != claim["bytes"]
        or document.get("document_sha256") != claim["document_sha256"]
        or document.get("document_sha256") != _document_sha256(document)
        or _sha256(audio) != claim["audio"]["sha256"]
        or audio.stat().st_size != claim["audio"]["bytes"]
        or document["excerpt"]["canonical_start_frame"]
        != planned["source_start_frame"]
        or document["excerpt"]["canonical_end_frame"] != planned["source_end_frame"]
    ):
        raise ValueError("private remediation authorisation changed")


def _record_untracked_attempts(root: Path, window_state: dict[str, Any]) -> None:
    known = {item["path"] for item in window_state["attempts"]}
    prefix = f"window-{window_state['window_index']:04d}-attempt-"
    for path in sorted((root / ATTEMPTS_DIRECTORY).glob(f"{prefix}*")):
        relative = path.relative_to(root).as_posix()
        if relative in known:
            continue
        _require_private_directory(path, "preserved incomplete remediation attempt")
        suffix = path.name.removeprefix(prefix)
        if len(suffix) != 3 or not suffix.isdigit():
            raise ValueError("private remediation attempt name differs")
        window_state["attempts"].append(
            {
                "attempt": int(suffix),
                "path": relative,
                "status": "preserved_incomplete",
                "failure_class": "interrupted_or_unrecorded",
            }
        )
    window_state["attempts"].sort(key=lambda item: item["attempt"])


def _selected_attempt_record(window_state: Mapping[str, Any]) -> Mapping[str, Any]:
    selected = window_state.get("selected_attempt")
    records = [
        item
        for item in window_state["attempts"]
        if item.get("attempt") == selected and item.get("status") == "verified_complete"
    ]
    if len(records) != 1:
        raise ValueError("private remediation selected attempt differs")
    return records[0]


def _build_candidates(
    root: Path,
    *,
    state: Mapping[str, Any],
    remediation_plan: Mapping[str, Any],
    package: Path,
    stitch: Mapping[str, Any],
) -> dict[str, Any]:
    import numpy as np
    import soundfile

    candidate_root = root / CANDIDATES_DIRECTORY
    if os.path.lexists(candidate_root) or os.path.lexists(root / CANDIDATE_REPORT_NAME):
        raise FileExistsError("private remediation candidate output already exists")
    candidate_root.mkdir(mode=0o700)
    total_frames = int(stitch["clock"]["frames"])
    raw_paths = {
        role: package / stitch["artifacts"][role]["path"] for role in _ROLES
    }
    raw_hashes_before = {role: _sha256(path) for role, path in raw_paths.items()}
    candidates: dict[str, Any] = {}
    patch_records: list[dict[str, Any]] = []
    candidate_arrays: dict[str, Any] = {}
    for role in _ROLES:
        raw, rate = soundfile.read(raw_paths[role], dtype="float32", always_2d=True)
        if int(rate) != TARGET_SAMPLE_RATE or raw.shape != (total_frames, 2):
            raise ValueError("private remediation raw role geometry differs")
        candidate = raw.copy()
        ranges: list[tuple[int, int]] = []
        for planned, window_state in zip(remediation_plan["windows"], state["windows"]):
            if role not in planned["patch_target_roles"]:
                continue
            selected = _selected_attempt_record(window_state)
            worker_path = (
                root
                / selected["path"]
                / "staging"
                / "quarantine"
                / "STEMS"
                / f"{role}.wav"
            )
            worker, worker_rate = soundfile.read(
                worker_path, dtype="float32", always_2d=True
            )
            expected_window_frames = (
                planned["source_end_frame"] - planned["source_start_frame"]
            )
            if int(worker_rate) != TARGET_SAMPLE_RATE or worker.shape != (
                expected_window_frames,
                2,
            ):
                raise ValueError("private remediation worker role geometry differs")
            start = int(planned["patch_start_frame"])
            end = int(planned["patch_end_frame"])
            local_start = start - int(planned["source_start_frame"])
            local_end = end - int(planned["source_start_frame"])
            changed = _apply_equal_power_patch(
                candidate,
                worker[local_start:local_end],
                start=start,
                end=end,
                blend_frames=int(remediation_plan["protocol"]["edge_blend_frames"]),
                np=np,
            )
            ranges.append((start, end))
            patch_records.append(
                {
                    "window_index": planned["window_index"],
                    "boundary_index": planned["boundary_index"],
                    "role": role,
                    "start_frame": start,
                    "end_frame": end,
                    "edge_blend_frames": remediation_plan["protocol"][
                        "edge_blend_frames"
                    ],
                    "worker_output_sha256": selected["outputs"][role]["sha256"],
                    "changed_sample_values_before_pcm24_rounding": changed,
                }
            )
        peak = float(np.max(np.abs(candidate))) if candidate.size else 0.0
        if not math.isfinite(peak) or peak > 1.0:
            raise ValueError("private remediation candidate role would clip")
        target = candidate_root / f"{role}.wav"
        soundfile.write(target, candidate, TARGET_SAMPLE_RATE, subtype="PCM_24")
        target.chmod(0o600)
        exact = _verify_unchanged_outside_ranges(
            raw_paths[role], target, ranges=ranges, soundfile=soundfile, np=np
        )
        claim = _audio_claim(target, root=root, expected_frames=total_frames, soundfile=soundfile)
        claim["peak_before_write"] = round(peak, 9)
        claim["outside_patch_pcm24_samples_exact"] = exact
        claim["patch_count"] = len(ranges)
        candidates[role] = claim
        candidate_arrays[role] = candidate

    reconstruction = candidate_arrays["vocals"].astype("float64") + candidate_arrays[
        "instrumental"
    ].astype("float64")
    reconstruction_peak = float(np.max(np.abs(reconstruction)))
    reconstruction_gain = min(1.0, 0.98 / reconstruction_peak) if reconstruction_peak else 1.0
    reconstruction_path = candidate_root / "reconstruction.wav"
    soundfile.write(
        reconstruction_path,
        reconstruction * reconstruction_gain,
        TARGET_SAMPLE_RATE,
        subtype="PCM_24",
    )
    reconstruction_path.chmod(0o600)
    candidates["reconstruction"] = _audio_claim(
        reconstruction_path,
        root=root,
        expected_frames=total_frames,
        soundfile=soundfile,
    )
    candidates["reconstruction"]["pre_gain_peak"] = round(reconstruction_peak, 9)
    candidates["reconstruction"]["global_gain"] = round(reconstruction_gain, 9)

    raw_hashes_after = {role: _sha256(path) for role, path in raw_paths.items()}
    if raw_hashes_after != raw_hashes_before or any(
        raw_hashes_after[role] != stitch["artifacts"][role]["sha256"] for role in _ROLES
    ):
        raise ValueError("private remediation raw stitch changed during candidate build")
    source_path = package / stitch["artifacts"]["source"]["path"]
    if _sha256(source_path) != stitch["artifacts"]["source"]["sha256"]:
        raise ValueError("private remediation source changed during candidate build")

    document: dict[str, Any] = {
        "schema": "sunofriend.private-separation-full-song-join-remediation-candidates.v1",
        "status": "candidate_audio_complete_review_required",
        "evidence_scope": "private_development_only",
        "policy_id": PLAN_POLICY_ID,
        "bindings": {
            "execution_state_sha256_before_candidate_report": state["state_sha256"],
            "remediation_plan_document_sha256": remediation_plan["document_sha256"],
            "stitch_document_sha256": stitch["document_sha256"],
            "source_audio_sha256": stitch["artifacts"]["source"]["sha256"],
            "raw_vocals_audio_sha256": stitch["artifacts"]["vocals"]["sha256"],
            "raw_instrumental_audio_sha256": stitch["artifacts"]["instrumental"][
                "sha256"
            ],
            "raw_reconstruction_audio_sha256": stitch["artifacts"][
                "reconstruction"
            ]["sha256"],
        },
        "clock": dict(remediation_plan["clock"]),
        "patches": patch_records,
        "artifacts": candidates,
        "summary": {
            "verified_worker_window_count": len(state["windows"]),
            "patched_boundary_role_pair_count": len(patch_records),
            "candidate_role_count": 3,
            "raw_control_count": 1,
            "raw_stitch_hashes_unchanged": True,
            "blind_boundary_review_required": True,
            "patch_edge_review_required": True,
            "complete_song_review_required": True,
        },
        "readiness": {
            "worker_runs_complete": True,
            "candidate_audio_complete": True,
            "candidate_integrity_verified": True,
            "candidate_review_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {
            "candidate_audio_created": True,
            "model_run": True,
            "raw_stitch_mutated": False,
            "review_evidence_mutated": False,
            "separator_accepted": False,
            "separator_selected": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "Equal-power patch transitions can change local level and require listening.",
            "The reconstruction is diagnostic and may use a disclosed global attenuation.",
            "Candidate integrity does not prove that an audible join was improved.",
            "The raw stitch remains the mandatory unchanged control.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    _write_json_exclusive(root / CANDIDATE_REPORT_NAME, document)
    return document


def _apply_equal_power_patch(
    destination: Any,
    replacement: Any,
    *,
    start: int,
    end: int,
    blend_frames: int,
    np: Any,
) -> int:
    if (
        destination.ndim != 2
        or replacement.shape != (end - start, destination.shape[1])
        or start < 0
        or end > len(destination)
        or end - start <= 2 * blend_frames
        or blend_frames < 1
    ):
        raise ValueError("private remediation patch geometry differs")
    before = destination[start:end].copy()
    theta = np.linspace(0.0, np.pi / 2.0, blend_frames, endpoint=True)
    old_to_new = (
        before[:blend_frames].astype("float64") * np.cos(theta)[:, None]
        + replacement[:blend_frames].astype("float64") * np.sin(theta)[:, None]
    )
    new_to_old = (
        replacement[-blend_frames:].astype("float64") * np.cos(theta)[:, None]
        + before[-blend_frames:].astype("float64") * np.sin(theta)[:, None]
    )
    destination[start : start + blend_frames] = old_to_new.astype(destination.dtype)
    destination[start + blend_frames : end - blend_frames] = replacement[
        blend_frames:-blend_frames
    ]
    destination[end - blend_frames : end] = new_to_old.astype(destination.dtype)
    return int(np.count_nonzero(destination[start:end] != before))


def _verify_unchanged_outside_ranges(
    raw_path: Path,
    candidate_path: Path,
    *,
    ranges: list[tuple[int, int]],
    soundfile: Any,
    np: Any,
) -> bool:
    raw, raw_rate = soundfile.read(raw_path, dtype="int32", always_2d=True)
    candidate, candidate_rate = soundfile.read(
        candidate_path, dtype="int32", always_2d=True
    )
    if int(raw_rate) != int(candidate_rate) or raw.shape != candidate.shape:
        raise ValueError("private remediation candidate round-trip geometry differs")
    mask = np.ones((len(raw),), dtype=bool)
    for start, end in ranges:
        mask[start:end] = False
    if not bool(np.array_equal(raw[mask], candidate[mask])):
        raise ValueError("private remediation candidate changed outside patch ranges")
    return True


def _audio_claim(
    path: Path,
    *,
    root: Path,
    expected_frames: int,
    soundfile: Any,
) -> dict[str, Any]:
    info = soundfile.info(path)
    if (
        int(info.samplerate) != TARGET_SAMPLE_RATE
        or int(info.channels) != 2
        or int(info.frames) != expected_frames
        or info.subtype != "PCM_24"
    ):
        raise ValueError("private remediation candidate audio geometry differs")
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "geometry": {
            "sample_rate": TARGET_SAMPLE_RATE,
            "channels": 2,
            "sample_width_bytes": 3,
            "frames": expected_frames,
        },
    }


def _verify_candidate_report(
    root: Path,
    state: Mapping[str, Any],
    *,
    stitch: Mapping[str, Any],
) -> dict[str, Any]:
    claim = state.get("candidate_report")
    if not isinstance(claim, Mapping):
        raise ValueError("private remediation candidate claim differs")
    path = root / claim["path"]
    _require_private_regular(path, "private remediation candidate report")
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        _sha256(path) != claim.get("sha256")
        or path.stat().st_size != claim.get("bytes")
        or document.get("document_sha256") != claim.get("document_sha256")
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("bindings", {}).get("stitch_document_sha256")
        != stitch["document_sha256"]
    ):
        raise ValueError("private remediation candidate report changed")
    for role in (*_ROLES, "reconstruction"):
        artifact = document["artifacts"][role]
        candidate = root / artifact["path"]
        _require_private_regular(candidate, "private remediation candidate audio")
        if _sha256(candidate) != artifact["sha256"] or candidate.stat().st_size != artifact[
            "bytes"
        ]:
            raise ValueError("private remediation candidate audio changed")
    return document


def _write_state(root: Path, state: dict[str, Any]) -> None:
    complete = sum(item["status"] == "verified_complete" for item in state["windows"])
    total = len(state["windows"])
    candidate_complete = state.get("candidate_report") is not None
    state["status"] = STATUS_COMPLETE if complete == total and candidate_complete else STATUS_INCOMPLETE
    state["summary"] = {
        "total_windows": total,
        "verified_windows": complete,
        "remaining_windows": total - complete,
        "all_worker_runs_complete": complete == total,
        "candidate_audio_complete": candidate_complete,
        "human_candidate_review_complete": False,
        "quality_accepted": False,
    }
    state["effects"] = {
        "authorisation_windows_created": True,
        "candidate_audio_created": candidate_complete,
        "model_run": complete > 0,
        "raw_stitch_mutated": False,
        "review_evidence_mutated": False,
        "separator_accepted": False,
        "separator_selected": False,
        "source_graph_mutated": False,
    }
    state["state_sha256"] = _state_sha256(state)
    payload = (
        json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{REPORT_NAME}.", dir=root)
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


def _state_sha256(state: Mapping[str, Any]) -> str:
    payload = dict(state)
    payload.pop("state_sha256", None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _write_json_exclusive(path: Path, document: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        os.set_inheritable(descriptor, False)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise RuntimeError("private remediation JSON write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _make_private_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("private remediation tree contains a symbolic link")
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)


def _all_false(value: object) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(
        item is False for item in value.values()
    )


__all__: tuple[str, ...] = ()
