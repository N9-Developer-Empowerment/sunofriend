"""Qualify four exact private provider synth estimates for bounded review.

This module performs audio identity, clock and pack-sum alignment checks only.
Provider labels remain proposals: no separator, transcriber, source selection or
public activation is performed here.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Mapping

import numpy as np

from .separation_fine_stem_canary_audio import (
    PCM24_SCALE,
    file_sha256,
    read_canonical_pcm24,
)
from .separation_fine_stem_canary_contract import SAMPLE_RATE_HZ, WINDOW_FRAMES
from .separation_fine_stem_integration_report import (
    validate_fine_stem_integration_report,
)
from .separation_fine_stem_synth_bottleneck_plan import (
    SYNTH_CASE_COUNT,
    validate_fine_stem_synth_bottleneck_plan,
)


PROVIDER_INPUT_SCHEMA = "sunofriend.private-fine-stem-synth-provider-inputs.v1"
QUALIFICATION_SCHEMA = "sunofriend.fine-stem-synth-provider-qualification.v1"
QUALIFICATION_STATUS = "provider_estimates_aligned_private_review_required"
MINIMUM_SAMPLE_CORRELATION = 0.85
MINIMUM_ENVELOPE_CORRELATION = 0.90
MAXIMUM_ABSOLUTE_LAG_MILLISECONDS = 20.0
MAXIMUM_SEARCH_LAG_MILLISECONDS = 1_000.0
_WINDOW_SECONDS = 15
_EXPECTED_PROVIDER = "Suno"
_EXPECTED_PROVIDER_ROLE = "Synth"


def qualification_document_sha256(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "document_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _regular_file(path: Path, label: str) -> Path:
    expanded = path.expanduser().absolute()
    details = expanded.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError(f"{label} is not a regular file")
    return expanded.resolve(strict=True)


def _regular_directory(path: Path, label: str) -> Path:
    expanded = path.expanduser().absolute()
    details = expanded.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        raise ValueError(f"{label} is not a regular directory")
    return expanded.resolve(strict=True)


def _artifact_path(root: Path, evidence: Mapping[str, Any], label: str) -> Path:
    relative = str(evidence.get("relative_path", ""))
    if not relative or Path(relative).is_absolute():
        raise ValueError(f"{label} path differs")
    path = _regular_file(root / relative, label)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} escapes its package") from error
    return path


def _provider_wavs(directory: Path) -> list[Path]:
    values = [
        _regular_file(path, "provider pack WAV")
        for path in sorted(
            directory.glob("*.wav"), key=lambda item: item.name.casefold()
        )
    ]
    if len(values) < 4 or len({path.name.casefold() for path in values}) != len(values):
        raise ValueError("provider pack WAV inventory differs")
    return values


def _artifact(path: Path, root: Path) -> dict[str, Any]:
    import soundfile as sf

    info = sf.info(path)
    if (
        info.samplerate != SAMPLE_RATE_HZ
        or info.channels != 2
        or info.frames != WINDOW_FRAMES
        or info.subtype != "PCM_24"
    ):
        raise RuntimeError("provider qualification artifact geometry differs")
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "channels": 2,
        "frames": WINDOW_FRAMES,
        "subtype": "PCM_24",
    }


def _input_identity(path: Path) -> dict[str, Any]:
    import soundfile as sf

    info = sf.info(path)
    return {
        "absolute_path": str(path),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "sample_rate_hz": int(info.samplerate),
        "channels": int(info.channels),
        "frames": int(info.frames),
        "subtype": info.subtype,
    }


def _read_native_window(path: Path, *, start_seconds: int) -> tuple[np.ndarray, int]:
    import soundfile as sf

    info = sf.info(path)
    if info.samplerate <= 0 or info.channels not in {1, 2}:
        raise RuntimeError("provider source geometry differs")
    start = start_seconds * int(info.samplerate)
    frames = _WINDOW_SECONDS * int(info.samplerate)
    if start < 0 or start + frames > int(info.frames):
        raise RuntimeError("provider source does not contain the frozen window")
    with sf.SoundFile(path) as source:
        source.seek(start)
        value = source.read(frames, dtype="float64", always_2d=True)
    if value.shape != (frames, info.channels) or not np.isfinite(value).all():
        raise RuntimeError("provider source decode differs")
    if info.channels == 1:
        value = np.repeat(value, 2, axis=1)
    return np.asarray(value, dtype=np.float64), int(info.samplerate)


def _canonical(value: np.ndarray, *, source_rate: int) -> np.ndarray:
    if source_rate != SAMPLE_RATE_HZ:
        from scipy.signal import resample_poly

        divisor = math.gcd(source_rate, SAMPLE_RATE_HZ)
        value = resample_poly(
            value,
            SAMPLE_RATE_HZ // divisor,
            source_rate // divisor,
            axis=0,
            padtype="constant",
        )
    if len(value) < WINDOW_FRAMES:
        value = np.pad(value, ((0, WINDOW_FRAMES - len(value)), (0, 0)))
    value = np.ascontiguousarray(value[:WINDOW_FRAMES], dtype=np.float64)
    if value.shape != (WINDOW_FRAMES, 2) or not np.isfinite(value).all():
        raise RuntimeError("provider canonical window differs")
    return value


def _correlation(left: np.ndarray, right: np.ndarray) -> float:
    if left.shape != right.shape or left.ndim != 1 or len(left) < 2:
        raise ValueError("provider correlation inputs differ")
    left = left - float(np.mean(left))
    right = right - float(np.mean(right))
    denominator = float(np.sqrt(np.dot(left, left) * np.dot(right, right)))
    return float(np.dot(left, right) / denominator) if denominator > 1e-30 else 0.0


def _db(value: float) -> float:
    return round(20.0 * math.log10(max(float(value), 1e-12)), 6)


def _alignment(reference: np.ndarray, provider_sum: np.ndarray) -> dict[str, Any]:
    reference_mono = reference.mean(axis=1)
    provider_mono = provider_sum.mean(axis=1)
    sample_correlation = _correlation(reference_mono, provider_mono)
    denominator = float(np.dot(provider_mono, provider_mono))
    gain = (
        float(np.dot(reference_mono, provider_mono) / denominator)
        if denominator > 1e-30
        else 0.0
    )
    residual = reference_mono - gain * provider_mono
    hop = int(round(SAMPLE_RATE_HZ * 0.010))
    reference_envelope = np.sqrt(np.mean(reference_mono.reshape(-1, hop) ** 2, axis=1))
    provider_envelope = np.sqrt(np.mean(provider_mono.reshape(-1, hop) ** 2, axis=1))
    best = (-1.0, 0)
    maximum_lag_bins = int(MAXIMUM_SEARCH_LAG_MILLISECONDS / 10)
    for lag in range(-maximum_lag_bins, maximum_lag_bins + 1):
        if lag < 0:
            left, right = reference_envelope[-lag:], provider_envelope[:lag]
        elif lag > 0:
            left, right = reference_envelope[:-lag], provider_envelope[lag:]
        else:
            left, right = reference_envelope, provider_envelope
        value = _correlation(left, right)
        if value > best[0]:
            best = (value, lag)
    lag_ms = float(best[1] * 10)
    passed = (
        sample_correlation >= MINIMUM_SAMPLE_CORRELATION
        and best[0] >= MINIMUM_ENVELOPE_CORRELATION
        and abs(lag_ms) <= MAXIMUM_ABSOLUTE_LAG_MILLISECONDS
    )
    return {
        "passed": passed,
        "sample_correlation_at_recorded_window": round(sample_correlation, 9),
        "envelope_correlation_at_best_lag": round(float(best[0]), 9),
        "envelope_best_lag_milliseconds": lag_ms,
        "optimal_pack_sum_gain_db": _db(abs(gain)),
        "gain_matched_residual_rms_dbfs": _db(
            float(np.sqrt(np.mean(np.square(residual))))
        ),
        "thresholds": {
            "minimum_sample_correlation": MINIMUM_SAMPLE_CORRELATION,
            "minimum_envelope_correlation": MINIMUM_ENVELOPE_CORRELATION,
            "maximum_absolute_lag_milliseconds": MAXIMUM_ABSOLUTE_LAG_MILLISECONDS,
        },
        "lag_semantics": "positive means provider activity is later than the bound source reference",
        "sum_semantics": "all WAVs in the frozen provider pack summed in float64",
        "proves_role_label": False,
    }


def _write_pcm24(path: Path, value: np.ndarray) -> dict[str, Any]:
    import soundfile as sf

    peak = float(np.max(np.abs(value)))
    clipped = np.clip(value, -1.0, 1.0 - 1.0 / PCM24_SCALE)
    clipped_samples = int(np.count_nonzero(clipped != value))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    sf.write(path, clipped, SAMPLE_RATE_HZ, subtype="PCM_24", format="WAV")
    path.chmod(0o600)
    persisted = sf.read(path, dtype="float64", always_2d=True)[0]
    if persisted.shape != (WINDOW_FRAMES, 2) or not np.isfinite(persisted).all():
        raise RuntimeError("provider PCM24 persistence differs")
    return {
        "pre_write_peak": peak,
        "out_of_range_samples_clipped": clipped_samples,
        "clipping_required": clipped_samples > 0,
    }


def _validate_inputs(
    value: Mapping[str, Any], request: Mapping[str, Any]
) -> dict[str, Any]:
    document = copy.deepcopy(dict(value))
    if document.get("schema") != PROVIDER_INPUT_SCHEMA:
        raise ValueError("provider input schema differs")
    if document.get("request_document_sha256") != request["document_sha256"]:
        raise ValueError("provider input/request binding differs")
    if document.get("selection_policy") != (
        "first unsuffixed Suno stem pack frozen before audio analysis; "
        "prefer its discrete Synth.wav estimate"
    ):
        raise ValueError("provider input selection policy differs")
    if document.get("selection_frozen_before_audio_analysis") is not True:
        raise ValueError("provider input selection was not frozen")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) != SYNTH_CASE_COUNT:
        raise ValueError("provider input cases differ")
    expected = {case["case_id"] for case in request["cases"]}
    if {case.get("case_id") for case in cases} != expected:
        raise ValueError("provider input case identities differ")
    for case in cases:
        if (
            case.get("provider") != _EXPECTED_PROVIDER
            or case.get("provider_role_label") != _EXPECTED_PROVIDER_ROLE
            or case.get("target_filename")
            not in {"5 Synth.wav", "6 Synth.wav", "7 Synth.wav"}
            or case.get("rights_category") not in {"owned", "authorised_private_use"}
            or not str(case.get("provider_use_boundary", "")).strip()
        ):
            raise ValueError("provider input evidence differs")
    return document


def _source_artifact_matches(
    request_case: Mapping[str, Any], integration_case: Mapping[str, Any]
) -> None:
    if (
        request_case["track_id"] != integration_case["track_id"]
        or request_case["window_seconds"] != integration_case["window_seconds"]
        or request_case["source_reference"]
        != {
            "role": "reference",
            **integration_case["artifacts"]["reference"],
        }
    ):
        raise ValueError("provider qualification source binding differs")


def qualify_fine_stem_synth_provider_estimates(
    *,
    request: Mapping[str, Any],
    integration_report: Mapping[str, Any],
    integration_root: str | Path,
    provider_inputs: Mapping[str, Any],
    out_dir: str | Path,
) -> dict[str, Any]:
    """Write four aligned private PCM24 provider estimates atomically."""

    qualified_request = validate_fine_stem_synth_bottleneck_plan(request)
    integration = validate_fine_stem_integration_report(integration_report)
    inputs = _validate_inputs(provider_inputs, qualified_request)
    if integration["report_sha256"] != qualified_request["integration_report_sha256"]:
        raise ValueError("provider qualification integration binding differs")
    source_root = _regular_directory(Path(integration_root), "integration root")
    destination = Path(out_dir).expanduser().absolute()
    if destination.exists() or os.path.lexists(destination):
        raise FileExistsError("fresh provider qualification output is required")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-", dir=destination.parent
        )
    )
    staging.chmod(0o700)
    request_by_id = {case["case_id"]: case for case in qualified_request["cases"]}
    integration_by_id = {case["case_id"]: case for case in integration["cases"]}
    cases: list[dict[str, Any]] = []
    audio_input_identities = 0
    try:
        for supplied in inputs["cases"]:
            case_id = supplied["case_id"]
            request_case = request_by_id[case_id]
            integration_case = integration_by_id[case_id]
            _source_artifact_matches(request_case, integration_case)
            start_seconds, end_seconds = request_case["window_seconds"]
            if end_seconds - start_seconds != _WINDOW_SECONDS:
                raise ValueError("provider qualification window duration differs")
            reference_evidence = integration_case["artifacts"]["reference"]
            reference_path = _artifact_path(
                source_root,
                reference_evidence,
                "integration source reference",
            )
            if (
                reference_path.stat().st_size != reference_evidence["bytes"]
                or file_sha256(reference_path) != reference_evidence["sha256"]
            ):
                raise ValueError("integration source reference identity differs")
            reference = read_canonical_pcm24(reference_path)
            pack_directory = _regular_directory(
                Path(str(supplied["pack_directory"])), "provider pack"
            )
            pack_paths = _provider_wavs(pack_directory)
            target_matches = [
                path for path in pack_paths if path.name == supplied["target_filename"]
            ]
            if len(target_matches) != 1:
                raise ValueError("provider target filename is not unique in pack")
            native_values: list[np.ndarray] = []
            pack_rate: int | None = None
            pack_geometry: tuple[int, int] | None = None
            pack_full_geometry: tuple[int, int, int] | None = None
            pack_items = []
            target_native: np.ndarray | None = None
            for path in pack_paths:
                value, rate = _read_native_window(path, start_seconds=start_seconds)
                geometry = (rate, len(value))
                if pack_geometry is None:
                    pack_geometry, pack_rate = geometry, rate
                elif geometry != pack_geometry:
                    raise ValueError("provider pack clocks differ")
                native_values.append(value)
                identity = _input_identity(path)
                full_geometry = (
                    identity["sample_rate_hz"],
                    identity["channels"],
                    identity["frames"],
                )
                if pack_full_geometry is None:
                    pack_full_geometry = full_geometry
                elif full_geometry != pack_full_geometry:
                    raise ValueError("provider pack full-song clocks differ")
                identity["selected_provider_target"] = path == target_matches[0]
                pack_items.append(identity)
                if path == target_matches[0]:
                    target_native = value
            if pack_rate is None or target_native is None:
                raise RuntimeError("provider target was not decoded")
            provider_sum = _canonical(
                np.sum(np.stack(native_values), axis=0, dtype=np.float64),
                source_rate=pack_rate,
            )
            provider_target = _canonical(target_native, source_rate=pack_rate)
            alignment = _alignment(reference, provider_sum)
            if not alignment["passed"]:
                raise RuntimeError(f"provider pack failed source alignment: {case_id}")
            case_root = staging / "CASES" / case_id
            reference_out = case_root / "reference.wav"
            provider_out = case_root / "provider_synth.wav"
            case_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(reference_path, reference_out)
            reference_out.chmod(0o600)
            persistence = _write_pcm24(provider_out, provider_target)
            if (
                file_sha256(reference_out) != reference_evidence["sha256"]
                or file_sha256(reference_path) != reference_evidence["sha256"]
            ):
                raise RuntimeError("provider qualification reference copy differs")
            for path, identity in zip(pack_paths, pack_items):
                if (
                    path.stat().st_size != identity["bytes"]
                    or file_sha256(path) != identity["sha256"]
                ):
                    raise RuntimeError("provider pack mutated during qualification")
            cases.append(
                {
                    "case_id": case_id,
                    "track_id": request_case["track_id"],
                    "title": request_case["title"],
                    "window_seconds": request_case["window_seconds"],
                    "provider": supplied["provider"],
                    "provider_role_label": supplied["provider_role_label"],
                    "provider_estimate_is_ground_truth": False,
                    "rights_category": supplied["rights_category"],
                    "provider_use_boundary": supplied["provider_use_boundary"],
                    "selection": {
                        "policy": inputs["selection_policy"],
                        "frozen_before_audio_analysis": True,
                        "pack_directory": str(pack_directory),
                        "target_filename": supplied["target_filename"],
                    },
                    "provider_pack_items": pack_items,
                    "alignment": alignment,
                    "resampling": {
                        "source_sample_rate_hz": pack_rate,
                        "target_sample_rate_hz": SAMPLE_RATE_HZ,
                        "algorithm": (
                            "identity"
                            if pack_rate == SAMPLE_RATE_HZ
                            else "scipy.signal.resample_poly(padtype=constant)"
                        ),
                        "scipy_version": (
                            None
                            if pack_rate == SAMPLE_RATE_HZ
                            else importlib.metadata.version("scipy")
                        ),
                    },
                    "persistence": persistence,
                    "artifacts": {
                        "reference": _artifact(reference_out, staging),
                        "provider_synth": _artifact(provider_out, staging),
                    },
                    "human_target_presence": "not_reviewed",
                }
            )
            audio_input_identities += 1 + len(pack_paths)
        order = [case["case_id"] for case in qualified_request["cases"]]
        cases.sort(key=lambda case: order.index(case["case_id"]))
        document: dict[str, Any] = {
            "schema": QUALIFICATION_SCHEMA,
            "document_sha256": "",
            "status": QUALIFICATION_STATUS,
            "created_on": "2026-08-10",
            "request_document_sha256": qualified_request["document_sha256"],
            "integration_report_sha256": integration["report_sha256"],
            "purpose": (
                "bind four exact provider synth estimates and prove their source clocks "
                "before any same-transcriber MIDI comparison"
            ),
            "cases": cases,
            "objective_summary": {
                "aligned_case_count": sum(
                    case["alignment"]["passed"] for case in cases
                ),
                "provider_target_count": len(cases),
                "human_target_presence_confirmed_count": 0,
                "ready_for_private_presence_review": True,
                "ready_for_midi_execution": False,
            },
            "limitations": [
                "Provider stems are comparison estimates, not ground-truth multitracks.",
                "Pack-sum alignment proves song and clock identity, not a correct Synth role label.",
                "The provider estimate must be heard beside the exact source before the MIDI plan can be executable.",
                "No usefulness threshold controls access to the existing core-four preview.",
            ],
            "boundaries": {
                "private_review_only": True,
                "provider_audio_bound": True,
                "provider_role_human_confirmed": False,
                "separator_model_loaded": False,
                "transcriber_run": False,
                "midi_created": False,
                "source_selected": False,
                "public_activation": False,
                "hosting": False,
                "redistribution": False,
                "audio_upload": False,
                "training_started": False,
                "automatic_retry": False,
            },
            "effects": {
                "private_audio_input_identities": audio_input_identities,
                "private_audio_writes": SYNTH_CASE_COUNT * 2,
                "checkpoint_loads": 0,
                "model_constructions": 0,
                "separator_inference_attempts": 0,
                "midi_transcription_attempts": 0,
                "midi_writes": 0,
                "network_attempts": 0,
                "source_selections": 0,
                "public_activations": 0,
                "training_attempts": 0,
            },
        }
        document["document_sha256"] = qualification_document_sha256(document)
        validate_fine_stem_synth_provider_qualification(document)
        technical = staging / "TECHNICAL"
        review = staging / "REVIEW"
        technical.mkdir(mode=0o700)
        review.mkdir(mode=0o700)
        report_path = technical / "PROVIDER-QUALIFICATION.json"
        report_path.write_text(
            json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        report_path.chmod(0o600)
        if os.path.lexists(destination):
            raise FileExistsError("provider qualification output appeared during run")
        staging.rename(destination)
        return document
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def validate_fine_stem_synth_provider_qualification(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    document = copy.deepcopy(dict(value))
    if (
        document.get("schema") != QUALIFICATION_SCHEMA
        or document.get("status") != QUALIFICATION_STATUS
        or document.get("document_sha256") != qualification_document_sha256(document)
    ):
        raise ValueError("provider qualification identity differs")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) != SYNTH_CASE_COUNT:
        raise ValueError("provider qualification cases differ")
    if len({case.get("case_id") for case in cases}) != SYNTH_CASE_COUNT:
        raise ValueError("provider qualification case identities differ")
    for case in cases:
        if (
            case.get("provider") != _EXPECTED_PROVIDER
            or case.get("provider_role_label") != _EXPECTED_PROVIDER_ROLE
            or case.get("provider_estimate_is_ground_truth") is not False
            or case.get("human_target_presence") != "not_reviewed"
            or case.get("selection", {}).get("frozen_before_audio_analysis") is not True
            or case.get("alignment", {}).get("passed") is not True
            or set(case.get("artifacts", {})) != {"reference", "provider_synth"}
        ):
            raise ValueError("provider qualification evidence differs")
    summary = document.get("objective_summary", {})
    if (
        summary.get("aligned_case_count") != SYNTH_CASE_COUNT
        or summary.get("provider_target_count") != SYNTH_CASE_COUNT
        or summary.get("human_target_presence_confirmed_count") != 0
        or summary.get("ready_for_private_presence_review") is not True
        or summary.get("ready_for_midi_execution") is not False
    ):
        raise ValueError("provider qualification summary differs")
    boundaries = document.get("boundaries", {})
    if (
        boundaries.get("private_review_only") is not True
        or boundaries.get("provider_audio_bound") is not True
        or boundaries.get("provider_role_human_confirmed") is not False
        or any(
            boundaries.get(key) is not False
            for key in (
                "separator_model_loaded",
                "transcriber_run",
                "midi_created",
                "source_selected",
                "public_activation",
                "hosting",
                "redistribution",
                "audio_upload",
                "training_started",
                "automatic_retry",
            )
        )
    ):
        raise ValueError("provider qualification grants permission")
    effects = document.get("effects", {})
    if any(
        effects.get(key) != 0
        for key in (
            "checkpoint_loads",
            "model_constructions",
            "separator_inference_attempts",
            "midi_transcription_attempts",
            "midi_writes",
            "network_attempts",
            "source_selections",
            "public_activations",
            "training_attempts",
        )
    ):
        raise ValueError("provider qualification contains forbidden effects")
    return document


__all__ = [
    "PROVIDER_INPUT_SCHEMA",
    "QUALIFICATION_SCHEMA",
    "QUALIFICATION_STATUS",
    "qualification_document_sha256",
    "qualify_fine_stem_synth_provider_estimates",
    "validate_fine_stem_synth_provider_qualification",
]
