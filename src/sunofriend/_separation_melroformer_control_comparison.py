"""No-output comparison of private Kim Vocal 2 and sealed vocal controls.

The comparison is descriptive evidence, not reference truth, ranking,
selection or product authority. It accepts only the exact self-hashed role
mapping bound to the already-verified authorised excerpt and reads the four
fixed PCM24 vocal controls without persisting candidate audio.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from ._separation_authorised_role_mapping import (
    AUTHORISED_ROLE_MAPPING_SCHEMA,
    _correlation,
    _features,
    _similarity,
)
from ._separation_melroformer_real_bridge import (
    MAXIMUM_EXCERPT_FRAMES,
    MINIMUM_PROBE_FRAMES,
    _PrivateMelRoFormerHandle,
    _decode_pcm24_excerpt,
    _reject_duplicate_json_object,
)
from ._separation_melroformer_runtime_evidence import _read_exact_regular_file


SCHEMA = "sunofriend.private-melroformer-vocal-control-comparison.v1"
_CONTROL_IDS = ("local-htdemucs", "moises", "suno-a", "suno-b")
_DENIED_PERMISSIONS = (
    "accepted",
    "automatic_promotion",
    "automatic_selection",
    "production_eligible",
    "public_result",
    "simple_mode_available",
    "source_graph_activation",
    "studio_import_available",
)
_SHA256_CHARS = frozenset("0123456789abcdef")


def _compare_private_melroformer_vocals(
    handle: _PrivateMelRoFormerHandle,
    *,
    source: Any,
    candidate_vocals: Any,
    source_authorisation: Mapping[str, Any],
    control_report_path: str | Path,
    expected_control_report_sha256: str,
) -> Mapping[str, Any]:
    """Return path-free same-clock comparisons without accepting a winner."""

    if type(handle) is not _PrivateMelRoFormerHandle:
        raise ValueError("MelRoFormer control comparison requires a private handle")
    if not _is_sha256(expected_control_report_sha256):
        raise ValueError("MelRoFormer control report hash is invalid")
    np = handle.np
    mixture = np.asarray(source)
    candidate = np.asarray(candidate_vocals, dtype=np.float32)
    if (
        mixture.dtype != np.float32
        or candidate.dtype != np.float32
        or mixture.ndim != 2
        or mixture.shape[1] != 2
        or candidate.shape != mixture.shape
        or not MINIMUM_PROBE_FRAMES <= len(mixture) <= MAXIMUM_EXCERPT_FRAMES
        or not bool(np.isfinite(mixture).all())
        or not bool(np.isfinite(candidate).all())
    ):
        raise ValueError("MelRoFormer comparison audio geometry differs")
    report = Path(control_report_path).expanduser().absolute()
    attached = report.lstat()
    if not 1 <= attached.st_size <= 2 * 1024 * 1024:
        raise ValueError("MelRoFormer control report size is invalid")
    raw_report = _read_exact_regular_file(
        report,
        expected_sha256=expected_control_report_sha256,
        expected_bytes=attached.st_size,
    )
    document = json.loads(
        raw_report,
        object_pairs_hook=_reject_duplicate_json_object,
    )
    _validate_control_report(document, source_authorisation)
    controls = _load_controls(report.parent, document, handle)
    if any(value.shape != mixture.shape for value in controls.values()):
        raise ValueError("MelRoFormer vocal control geometry differs")

    candidate_features = _features(candidate, sample_rate=44_100, np=np)
    control_features = {
        identity: _features(value, sample_rate=44_100, np=np)
        for identity, value in controls.items()
    }
    comparisons = {
        identity: {
            **_similarity(candidate_features, control_features[identity], np=np),
            **_directional_difference(candidate, value, np=np),
        }
        for identity, value in controls.items()
    }
    pairwise_controls: dict[str, Mapping[str, float]] = {}
    for left_index, left in enumerate(_CONTROL_IDS):
        for right in _CONTROL_IDS[left_index + 1 :]:
            pairwise_controls[f"{left}__{right}"] = _similarity(
                control_features[left], control_features[right], np=np
            )
    evidence = {
        "schema": SCHEMA,
        "status": "descriptive_review_required_no_winner",
        "source_binding": {
            "track_id": source_authorisation["track_id"],
            "authorisation_report_sha256": source_authorisation["report_sha256"],
            "control_report_sha256": expected_control_report_sha256,
            "source_start_seconds": source_authorisation["source_start_seconds"],
            "source_end_seconds": source_authorisation["source_end_seconds"],
            "sample_rate": 44_100,
            "channels": 2,
            "frames": len(mixture),
        },
        "candidate": {
            "identity": "mlx-melroformer-kim-vocal-2",
            "audio": _audio_summary(candidate, np=np),
            "audio_persisted": False,
            "mixture_rms_ratio": _ratio(_rms(candidate, np=np), _rms(mixture, np=np)),
        },
        "controls": {
            identity: {
                "audio": _audio_summary(value, np=np),
                "source_pcm24_sha256": document["artifacts"][
                    f"ROLE-GROUPS/{identity}/vocals.wav"
                ]["sha256"],
                "source_pcm24_persisted": True,
                "decoded_audio_persisted_by_comparison": False,
                "mixture_rms_ratio": _ratio(_rms(value, np=np), _rms(mixture, np=np)),
            }
            for identity, value in controls.items()
        },
        "candidate_vs_controls": comparisons,
        "control_pairwise_context": pairwise_controls,
        "interpretation": {
            "controls_are_estimated_not_ground_truth": True,
            "provider_names_do_not_contribute_to_scores": True,
            "similarity_is_descriptive_not_acceptance": True,
            "automatic_ranking_performed": False,
            "winner_selected": False,
        },
        "permissions": {
            "audio_persistence_permitted": False,
            "automatic_selection_permitted": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "effects": {
            "filesystem_accessed": True,
            "filesystem_written": False,
            "network_used": False,
            "process_started": False,
        },
    }
    return _freeze(evidence)


def _validate_control_report(
    document: Any, source_authorisation: Mapping[str, Any]
) -> None:
    if not isinstance(document, Mapping):
        raise ValueError("MelRoFormer control report is not an object")
    canonical = dict(document)
    self_hash = canonical.pop("document_sha256", None)
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    source = document.get("source_excerpt")
    policy = document.get("policy")
    permissions = document.get("permissions")
    artifacts = document.get("artifacts")
    if not all(
        isinstance(value, Mapping) for value in (source, policy, permissions, artifacts)
    ):
        raise ValueError("MelRoFormer control report is incomplete")
    if (
        document.get("schema") != AUTHORISED_ROLE_MAPPING_SCHEMA
        or document.get("status") != "complete_review_required"
        or document.get("evidence_scope") != "private_development_only"
        or self_hash != hashlib.sha256(payload).hexdigest()
        or source.get("report_sha256") != source_authorisation.get("report_sha256")
        or source.get("track_id") != source_authorisation.get("track_id")
        or source.get("start_seconds")
        != source_authorisation.get("source_start_seconds")
        or source.get("end_seconds") != source_authorisation.get("source_end_seconds")
        or policy.get("common_sample_rate") != 44_100
        or policy.get("roles") != ["bass", "drums", "other", "vocals"]
        or policy.get("similarity_is_descriptive_not_acceptance") is not True
        or policy.get("provider_names_propose_but_do_not_prove_groups") is not True
    ):
        raise ValueError("MelRoFormer control report binding differs")
    if any(permissions.get(name) is not False for name in _DENIED_PERMISSIONS):
        raise ValueError("MelRoFormer control report product permissions differ")


def _load_controls(
    root: Path,
    document: Mapping[str, Any],
    handle: _PrivateMelRoFormerHandle,
) -> dict[str, Any]:
    artifacts = document["artifacts"]
    result: dict[str, Any] = {}
    resolved_root = root.resolve(strict=True)
    for identity in _CONTROL_IDS:
        relative = f"ROLE-GROUPS/{identity}/vocals.wav"
        artifact = artifacts.get(relative)
        if (
            not isinstance(artifact, Mapping)
            or type(artifact.get("bytes")) is not int
            or not 1 <= artifact["bytes"] <= 8 * 1024 * 1024
            or not _is_sha256(artifact.get("sha256"))
        ):
            raise ValueError("MelRoFormer vocal control artifact differs")
        path = root / relative
        if resolved_root not in path.resolve(strict=True).parents:
            raise ValueError("MelRoFormer vocal control escapes its report root")
        contents = _read_exact_regular_file(
            path,
            expected_sha256=artifact["sha256"],
            expected_bytes=artifact["bytes"],
        )
        result[identity] = _decode_pcm24_excerpt(handle.np, contents)
    return result


def _directional_difference(
    candidate: Any, control: Any, *, np: Any
) -> dict[str, float]:
    estimate = candidate.astype(np.float64).reshape(-1)
    reference = control.astype(np.float64).reshape(-1)
    denominator = float(np.dot(estimate, estimate))
    gain = (
        float(np.dot(estimate, reference) / denominator) if denominator > 1e-30 else 0.0
    )
    residual = reference - gain * estimate
    return {
        "signed_waveform_correlation": round(
            _correlation(estimate, reference, np=np), 9
        ),
        "candidate_gain_to_match_control_db": _db(abs(gain)),
        "control_minus_gain_matched_candidate_rms_dbfs": _db(_rms(residual, np=np)),
        "control_minus_gain_matched_candidate_rms_ratio": _ratio(
            _rms(residual, np=np), _rms(reference, np=np)
        ),
    }


def _audio_summary(value: Any, *, np: Any) -> dict[str, Any]:
    little_endian = np.asarray(value, dtype="<f4", order="C")
    rms = _rms(little_endian, np=np)
    return {
        "float32_sha256": hashlib.sha256(little_endian.tobytes()).hexdigest(),
        "peak": float(np.max(np.abs(little_endian))),
        "rms": rms,
        "rms_dbfs": _db(rms),
    }


def _rms(value: Any, *, np: Any) -> float:
    return float(np.sqrt(np.mean(value.astype(np.float64) ** 2)))


def _ratio(numerator: float, denominator: float) -> float:
    return round(float(numerator / denominator), 9) if denominator > 1e-30 else 0.0


def _db(value: float) -> float:
    return round(20.0 * math.log10(max(float(value), 1e-12)), 6)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and set(value).issubset(_SHA256_CHARS)
    )


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


__all__ = ["SCHEMA", "_compare_private_melroformer_vocals"]
