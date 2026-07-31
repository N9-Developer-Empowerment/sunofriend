"""Ground-truth observations for the private synthetic Demucs experiment."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_demucs_demo_fixture import (
    PRIVATE_DEMUCS_DEMO_SCHEMA,
    _document_sha256 as _fixture_document_sha256,
)
from ._separation_demucs_private_run import (
    PRIVATE_DEMUCS_EXPERIMENT_SCHEMA,
    _document_sha256 as _experiment_document_sha256,
)


PRIVATE_DEMUCS_DEMO_EVALUATION_SCHEMA = "sunofriend.private-demucs-demo-evaluation.v1"
_ROLES = ("bass", "drums", "other", "vocals")
_ACTIVE_ROLES = ("bass", "drums", "other")
_SAMPLE_RATE = 44_100
_ENVELOPE_WINDOW_FRAMES = 441
_MAXIMUM_ALIGNMENT_LAG_WINDOWS = 25


def _evaluate_private_demucs_demo_run(
    fixture_manifest_path: str | Path,
    experiment_report_path: str | Path,
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Compare four estimated stems with exact synthetic references."""

    import numpy as np
    import soundfile

    fixture_path = _regular_json(fixture_manifest_path, "fixture manifest")
    experiment_path = _regular_json(experiment_report_path, "experiment report")
    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"Private separation evaluation already exists: {destination}"
        )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
    _validate_documents(fixture, experiment)
    fixture_root = fixture_path.parent
    experiment_root = experiment_path.parent

    source_path = _inside(fixture_root, fixture["mixture"]["path"], "fixture mixture")
    _require_hash(
        source_path,
        fixture["mixture"]["sha256"],
        "fixture mixture",
    )
    source, sample_rate = soundfile.read(source_path, dtype="float32", always_2d=True)
    if sample_rate != _SAMPLE_RATE:
        raise ValueError("fixture sample rate changed")
    source_rms = _rms(source)

    role_metrics: dict[str, Any] = {}
    output_energy = 0.0
    reference_energy = 0.0
    for role in _ROLES:
        reference_path = _inside(
            fixture_root,
            fixture["references"][role]["path"],
            f"{role} reference",
        )
        estimate_path = _inside(
            experiment_root,
            experiment["estimated_stems"][role]["path"],
            f"{role} estimate",
        )
        _require_hash(
            reference_path,
            fixture["references"][role]["sha256"],
            f"{role} reference",
        )
        _require_hash(
            estimate_path,
            experiment["estimated_stems"][role]["sha256"],
            f"{role} estimate",
        )
        reference, reference_rate = soundfile.read(
            reference_path, dtype="float32", always_2d=True
        )
        estimate, estimate_rate = soundfile.read(
            estimate_path, dtype="float32", always_2d=True
        )
        if (
            reference_rate != sample_rate
            or estimate_rate != sample_rate
            or reference.shape != source.shape
            or estimate.shape != source.shape
        ):
            raise ValueError(f"{role} evaluation geometry changed")
        reference_rms = _rms(reference)
        estimate_rms = _rms(estimate)
        output_energy += float(np.sum(np.square(estimate.astype("float64"))))
        reference_energy += float(np.sum(np.square(reference.astype("float64"))))
        if role in _ACTIVE_ROLES:
            role_metrics[role] = {
                "reference_active": True,
                "reference_rms": round(reference_rms, 12),
                "estimate_rms": round(estimate_rms, 12),
                "gain_error_db": _relative_db(estimate_rms, reference_rms),
                "scale_invariant_sdr": _si_sdr(estimate, reference, np=np),
                "envelope_alignment": _envelope_alignment(
                    estimate,
                    reference,
                    sample_rate=sample_rate,
                    np=np,
                ),
            }
        else:
            role_metrics[role] = {
                "reference_active": False,
                "reference_rms": 0.0,
                "estimate_rms": round(estimate_rms, 12),
                "estimate_dbfs": _dbfs(estimate_rms),
                "estimate_to_source_db": _relative_db(estimate_rms, source_rms),
                "estimate_to_source_energy_ratio": round(
                    (estimate_rms * estimate_rms) / (source_rms * source_rms),
                    12,
                ),
                "scale_invariant_sdr": {
                    "applicable": False,
                    "reason": "reference_is_exact_digital_silence",
                },
            }

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o700)
    destination.chmod(0o700)
    document: dict[str, Any] = {
        "schema": PRIVATE_DEMUCS_DEMO_EVALUATION_SCHEMA,
        "status": "complete_observation_not_acceptance",
        "evidence_scope": "private_development_only",
        "fixture": {
            "manifest_sha256": _sha256(fixture_path),
            "document_sha256": fixture["document_sha256"],
            "source_sha256": fixture["mixture"]["sha256"],
        },
        "experiment": {
            "report_sha256": _sha256(experiment_path),
            "document_sha256": experiment["document_sha256"],
            "checkpoint_sha256": experiment["backend"]["checkpoint_sha256"],
            "worker_sha256": experiment["backend"]["worker_sha256"],
        },
        "geometry": {
            "sample_rate": sample_rate,
            "channels": int(source.shape[1]),
            "frames": int(source.shape[0]),
            "duration_seconds": source.shape[0] / sample_rate,
            "exact_match_required": True,
        },
        "role_metrics": role_metrics,
        "energy_diagnostics": {
            "sum_per_role_output_energy_to_source_energy_ratio": round(
                output_energy / float(np.sum(np.square(source.astype("float64")))),
                12,
            ),
            "sum_per_role_output_energy_to_sum_per_role_reference_energy_ratio": round(
                output_energy / reference_energy,
                12,
            ),
            "meaning": (
                "The numerator sums each estimated role's energy separately; "
                "it is not the energy of the additive estimated-stem sum. "
                "These ratios can flag possible attenuation or duplication "
                "but do not identify correct source assignment."
            ),
        },
        "downstream_midi": {
            "status": "not_run",
            "comparison_required": True,
            "next_scope": (
                "transcribe each clean reference and matching estimate with "
                "identical production settings"
            ),
        },
        "permissions": {
            "accepted": False,
            "production_eligible": False,
            "automatic_selection": False,
            "automatic_promotion": False,
            "source_graph_activation": False,
            "public_result": False,
        },
        "limitations": [
            "The fixture is synthetic and is not representative of every real recording.",
            "SI-SDR and envelope alignment do not prove perceptual stem quality.",
            "The silent-vocals result measures false-positive energy only.",
            "No role threshold was frozen before this observation.",
            "No downstream MIDI or human listening result is included.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    report_path = destination / "private-demucs-demo-evaluation.json"
    _write_json(report_path, document)
    document["report"] = str(report_path)
    return document


def _validate_documents(
    fixture: Mapping[str, Any],
    experiment: Mapping[str, Any],
) -> None:
    if fixture.get("schema") != PRIVATE_DEMUCS_DEMO_SCHEMA:
        raise ValueError("unsupported private Demucs fixture schema")
    if fixture.get("document_sha256") != _fixture_document_sha256(dict(fixture)):
        raise ValueError("private Demucs fixture self-hash is invalid")
    if experiment.get("schema") != PRIVATE_DEMUCS_EXPERIMENT_SCHEMA:
        raise ValueError("unsupported private Demucs experiment schema")
    if experiment.get("document_sha256") != _experiment_document_sha256(experiment):
        raise ValueError("private Demucs experiment self-hash is invalid")
    if experiment.get("status") != "complete_review_required":
        raise ValueError("private Demucs experiment is not complete")
    if experiment.get("evidence_scope") != "private_development_only":
        raise ValueError("private Demucs experiment scope changed")
    if experiment.get("permissions") != {
        "accepted": False,
        "production_eligible": False,
        "automatic_selection": False,
        "automatic_promotion": False,
        "source_graph_activation": False,
        "public_result": False,
        "simple_mode_available": False,
        "studio_import_available": False,
    }:
        raise ValueError("private Demucs experiment permissions changed")
    if experiment["source"]["sha256"] != fixture["mixture"]["sha256"]:
        raise ValueError("experiment source does not bind the fixture mixture")
    if set(experiment.get("estimated_stems", {})) != set(_ROLES):
        raise ValueError("private Demucs experiment role set changed")


def _si_sdr(estimate: Any, reference: Any, *, np: Any) -> dict[str, Any]:
    estimate_flat = estimate.astype("float64").reshape(-1)
    reference_flat = reference.astype("float64").reshape(-1)
    reference_energy = float(np.dot(reference_flat, reference_flat))
    if reference_energy <= 0:
        return {"applicable": False, "reason": "reference_has_no_energy"}
    estimate_energy = float(np.dot(estimate_flat, estimate_flat))
    if estimate_energy <= 0:
        return {
            "applicable": False,
            "reason": "estimate_has_no_energy",
            "perfect_scaled_match": False,
            "value_db": None,
            "scale": 0.0,
        }
    scale = float(np.dot(estimate_flat, reference_flat) / reference_energy)
    projected = scale * reference_flat
    noise = estimate_flat - projected
    projected_energy = float(np.dot(projected, projected))
    noise_energy = float(np.dot(noise, noise))
    if noise_energy == 0:
        return {
            "applicable": True,
            "perfect_scaled_match": True,
            "value_db": None,
            "scale": round(scale, 12),
        }
    value = (
        10.0 * math.log10(projected_energy / noise_energy)
        if projected_energy > 0
        else None
    )
    return {
        "applicable": True,
        "perfect_scaled_match": False,
        "value_db": round(value, 9) if value is not None else None,
        "scale": round(scale, 12),
    }


def _envelope_alignment(
    estimate: Any,
    reference: Any,
    *,
    sample_rate: int,
    np: Any,
) -> dict[str, Any]:
    estimate_envelope = _rms_envelope(estimate, np=np)
    reference_envelope = _rms_envelope(reference, np=np)
    full = _best_lag(estimate_envelope, reference_envelope, np=np)
    quarter = len(reference_envelope) // 4
    segments = []
    for index in range(4):
        start = index * quarter
        end = len(reference_envelope) if index == 3 else (index + 1) * quarter
        result = _best_lag(
            estimate_envelope[start:end],
            reference_envelope[start:end],
            np=np,
        )
        lag_windows = result["estimate_lag_windows"]
        segment = {
            "segment": index + 1,
            "applicable": result["applicable"],
            "estimate_lag_windows": lag_windows,
            "estimate_lag_ms": (
                lag_windows * _ENVELOPE_WINDOW_FRAMES * 1000.0 / sample_rate
                if lag_windows is not None
                else None
            ),
            "correlation": result["correlation"],
        }
        if not result["applicable"]:
            segment["reason"] = result["reason"]
        segments.append(segment)
    first_lag = segments[0]["estimate_lag_ms"]
    last_lag = segments[-1]["estimate_lag_ms"]
    full_lag_windows = full["estimate_lag_windows"]
    result = {
        "applicable": full["applicable"],
        "window_frames": _ENVELOPE_WINDOW_FRAMES,
        "window_ms": _ENVELOPE_WINDOW_FRAMES * 1000.0 / sample_rate,
        "search_range_ms": (
            _MAXIMUM_ALIGNMENT_LAG_WINDOWS
            * _ENVELOPE_WINDOW_FRAMES
            * 1000.0
            / sample_rate
        ),
        "estimate_lag_windows": full_lag_windows,
        "estimate_lag_ms": (
            full_lag_windows * _ENVELOPE_WINDOW_FRAMES * 1000.0 / sample_rate
            if full_lag_windows is not None
            else None
        ),
        "correlation": full["correlation"],
        "segments": segments,
        "first_to_last_lag_drift_ms": (
            round(last_lag - first_lag, 9)
            if first_lag is not None and last_lag is not None
            else None
        ),
        "lag_sign": "positive means the estimate envelope is later",
    }
    if not full["applicable"]:
        result["reason"] = full["reason"]
    return result


def _rms_envelope(samples: Any, *, np: Any) -> Any:
    usable = (samples.shape[0] // _ENVELOPE_WINDOW_FRAMES) * (_ENVELOPE_WINDOW_FRAMES)
    reshaped = (
        samples[:usable]
        .astype("float64")
        .reshape(-1, _ENVELOPE_WINDOW_FRAMES, samples.shape[1])
    )
    return np.sqrt(np.mean(np.square(reshaped), axis=(1, 2)))


def _best_lag(estimate: Any, reference: Any, *, np: Any) -> dict[str, Any]:
    if len(estimate) < 3 or len(reference) < 3:
        return {
            "applicable": False,
            "reason": "insufficient_envelope_windows",
            "estimate_lag_windows": None,
            "correlation": None,
        }
    estimate_centered = estimate - np.mean(estimate)
    reference_centered = reference - np.mean(reference)
    if float(np.sum(np.square(estimate_centered))) <= 0:
        return {
            "applicable": False,
            "reason": "estimate_envelope_has_no_variation",
            "estimate_lag_windows": None,
            "correlation": None,
        }
    if float(np.sum(np.square(reference_centered))) <= 0:
        return {
            "applicable": False,
            "reason": "reference_envelope_has_no_variation",
            "estimate_lag_windows": None,
            "correlation": None,
        }
    best_lag = 0
    best_correlation = -1.0
    for lag in range(
        -_MAXIMUM_ALIGNMENT_LAG_WINDOWS,
        _MAXIMUM_ALIGNMENT_LAG_WINDOWS + 1,
    ):
        if lag > 0:
            left = reference[:-lag]
            right = estimate[lag:]
        elif lag < 0:
            left = reference[-lag:]
            right = estimate[:lag]
        else:
            left = reference
            right = estimate
        if len(left) < 3:
            continue
        left_centered = left - np.mean(left)
        right_centered = right - np.mean(right)
        denominator = float(
            np.sqrt(
                np.sum(np.square(left_centered)) * np.sum(np.square(right_centered))
            )
        )
        correlation = (
            float(np.sum(left_centered * right_centered) / denominator)
            if denominator > 0
            else 0.0
        )
        if correlation > best_correlation or (
            math.isclose(
                correlation,
                best_correlation,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            and abs(lag) < abs(best_lag)
        ):
            best_lag = lag
            best_correlation = correlation
    return {
        "applicable": True,
        "estimate_lag_windows": best_lag,
        "correlation": round(best_correlation, 9),
    }


def _regular_json(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().absolute()
    if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".json":
        raise ValueError(f"{label} must be an existing non-symlink JSON file")
    return path


def _inside(root: Path, relative: str, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{label} path is invalid")
    candidate = (root / relative).absolute()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escaped its evidence root") from exc
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"{label} is unavailable")
    return candidate


def _require_hash(path: Path, expected: str, label: str) -> None:
    if _sha256(path) != expected:
        raise ValueError(f"{label} hash changed")


def _rms(samples: Any) -> float:
    import numpy as np

    return float(np.sqrt(np.mean(np.square(samples.astype("float64")))))


def _relative_db(numerator: float, denominator: float) -> float | None:
    if numerator <= 0 or denominator <= 0:
        return None
    return round(20.0 * math.log10(numerator / denominator), 9)


def _dbfs(value: float) -> float | None:
    if value <= 0:
        return None
    return round(20.0 * math.log10(value), 9)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _document_sha256(document: Mapping[str, Any]) -> str:
    canonical = dict(document)
    canonical.pop("document_sha256", None)
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            document,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


__all__: tuple[str, ...] = ()
