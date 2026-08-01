"""Private blind listening gate for Kim Vocal 2 FP32 versus published BF16.

The numeric parity gate proves that the MLX implementation reproduces the
converted BF16 weights.  This separate owner-only review asks whether the
precision reduction is musically audible.  It does not select a separator,
change a product route or publish either checkpoint.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import soundfile

from ._separation_melroformer_inference_parity import (
    EVIDENCE_SHA256 as INFERENCE_PARITY_EVIDENCE_SHA256,
    PARITY_FRAMES,
    PARITY_THRESHOLD_DB,
    SAMPLE_RATE,
    _array_sha256,
    _metrics,
    _run_private_melroformer_inference_outputs,
)
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_SHA256,
    SOURCE_CHECKPOINT_SHA256,
)


REVIEW_SCHEMA = "sunofriend.private-melroformer-precision-review.v1"
ANSWER_KEY_SCHEMA = "sunofriend.private-melroformer-precision-answer-key.v1"
RESULT_SCHEMA = "sunofriend.private-melroformer-precision-result.v1"
AUDIO_MANIFEST_SCHEMA = "sunofriend.private-melroformer-precision-audio-manifest.v1"
POLICY_ID = "kim-vocal-2-fp32-vs-published-bf16-blind-audio-v1"
_CHOICES = {"candidate_a", "candidate_b", "equivalent", "neither", "cannot_tell"}
_MINIMUM_RMS_DBFS = -60.0
_MAXIMUM_PAIR_ATTENUATION_DB = 18.0
_MAXIMUM_FINAL_MISMATCH_DB = 0.05
_FULL_SCALE_GUARD = 0.9999


def _run_private_melroformer_precision_review(
    *,
    mlx_source_root: str | Path,
    source_checkpoint: str | Path,
    converted_checkpoint: str | Path,
    companion_root: str | Path,
    authorisation_report: str | Path,
    authorisation_report_sha256: str,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Run the fixed inference pair and create one fresh owner-only review."""

    outputs = _run_private_melroformer_inference_outputs(
        mlx_source_root=mlx_source_root,
        source_checkpoint=source_checkpoint,
        converted_checkpoint=converted_checkpoint,
        companion_root=companion_root,
        authorisation_report=authorisation_report,
        authorisation_report_sha256=authorisation_report_sha256,
    )
    runtime_parity = _metrics(outputs["rounded"], outputs["converted"], np=np)["sdr_db"]
    if runtime_parity <= PARITY_THRESHOLD_DB:
        raise RuntimeError(
            "BF16 PyTorch-to-MLX runtime parity is below the required gate"
        )
    return _create_private_melroformer_precision_review(
        source=outputs["audio"],
        original_fp32=outputs["original"],
        published_bf16=outputs["converted"],
        out_dir=out_dir,
        authorisation=outputs["authorisation"],
        runtime_versions=outputs["runtime_versions"],
        timings=outputs["timings"],
        runtime_parity_sdr_db=runtime_parity,
    )


def _create_private_melroformer_precision_review(
    *,
    source: Any,
    original_fp32: Any,
    published_bf16: Any,
    out_dir: str | Path,
    authorisation: Mapping[str, Any],
    runtime_versions: Mapping[str, str],
    timings: Mapping[str, float | int],
    runtime_parity_sdr_db: float,
) -> dict[str, Any]:
    """Create one sealed review from already-computed exact output arrays."""

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"precision review already exists: {destination}")
    arrays = {
        "source": _validated_audio(source),
        "input_1": _validated_audio(original_fp32),
        "input_2": _validated_audio(published_bf16),
    }
    if {value.shape for value in arrays.values()} != {(PARITY_FRAMES, 2)}:
        raise ValueError(
            "precision review requires one exact eight-second stereo window"
        )
    if (
        not math.isfinite(float(runtime_parity_sdr_db))
        or runtime_parity_sdr_db <= PARITY_THRESHOLD_DB
    ):
        raise ValueError("precision review requires verified BF16 runtime parity")
    if authorisation.get("source_window_seconds") != PARITY_FRAMES / SAMPLE_RATE:
        raise ValueError("precision review authorisation window differs")

    input_hashes = {name: _array_sha256(value, np=np) for name, value in arrays.items()}
    package_contract = {
        "policy_id": POLICY_ID,
        "source_float32_sha256": input_hashes["source"],
        "input_1_float32_sha256": input_hashes["input_1"],
        "input_2_float32_sha256": input_hashes["input_2"],
        "sample_rate": SAMPLE_RATE,
        "channels": 2,
        "frames": PARITY_FRAMES,
        "source_checkpoint_sha256": SOURCE_CHECKPOINT_SHA256,
        "converted_checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
        "authorisation_report_sha256": authorisation.get("report_sha256"),
        "tracked_inference_parity_sha256": INFERENCE_PARITY_EVIDENCE_SHA256,
    }
    package_commitment = _document_hash(package_contract)
    blind_nonce = secrets.token_bytes(32)
    nonce_commitment = hashlib.sha256(
        blind_nonce + bytes.fromhex(package_commitment)
    ).hexdigest()
    mapping = _blind_mapping(blind_nonce, package_commitment)

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.mkdir(mode=0o700)
        audio_dir = destination / "audio"
        private_dir = destination / "private-evidence"
        audio_dir.mkdir(mode=0o700)
        private_dir.mkdir(mode=0o700)
        for name in ("input_1", "input_2"):
            _write_audio(private_dir / f"{name}-raw.wav", arrays[name], subtype="FLOAT")

        matched, level_evidence = _level_match(
            {name: arrays[name] for name in ("input_1", "input_2")}
        )
        source_path = audio_dir / "source-reference.wav"
        _write_audio(source_path, arrays["source"], subtype="PCM_24")
        source_record = _audio_record(source_path, destination)
        anonymous: dict[str, dict[str, Any]] = {}
        for slot in ("candidate_a", "candidate_b"):
            path = audio_dir / f"{slot}.wav"
            _write_audio(path, matched[mapping[slot]], subtype="PCM_24")
            anonymous[slot] = _audio_record(path, destination)
        final_mismatch = abs(
            anonymous["candidate_a"]["rms_dbfs"] - anonymous["candidate_b"]["rms_dbfs"]
        )
        if final_mismatch > _MAXIMUM_FINAL_MISMATCH_DB:
            raise RuntimeError("precision-review PCM24 candidate levels differ")
        level_evidence["final_pcm24"] = {
            "candidate_a_rms_dbfs": anonymous["candidate_a"]["rms_dbfs"],
            "candidate_b_rms_dbfs": anonymous["candidate_b"]["rms_dbfs"],
            "mismatch_db": round(final_mismatch, 6),
            "within_tolerance": True,
        }

        manifest = {
            "schema": AUDIO_MANIFEST_SCHEMA,
            "package_commitment": package_commitment,
            "files": [
                _manifest_row(source_record, "source-reference"),
                _manifest_row(anonymous["candidate_a"], "blinded-candidate-a"),
                _manifest_row(anonymous["candidate_b"], "blinded-candidate-b"),
            ],
        }
        manifest["file_count"] = len(manifest["files"])
        manifest_path = destination / "melroformer_precision_audio_manifest.json"
        _write_json(manifest_path, manifest)
        manifest_sha256 = _sha256(manifest_path)

        unit = {
            "unit_id": "01-vocal-precision",
            "source_seconds": [
                float(authorisation.get("source_start_seconds", 0.0)),
                float(authorisation.get("source_start_seconds", 0.0))
                + PARITY_FRAMES / SAMPLE_RATE,
            ],
            "duration_seconds": PARITY_FRAMES / SAMPLE_RATE,
            "sample_rate": SAMPLE_RATE,
            "frame_count": PARITY_FRAMES,
            "listening_focus": [
                "recognisable vocal words, consonants and phrase continuity",
                "metallic, warbling, buzzy or watery artefacts",
                "music bleed around the voice",
                "lost breath, attacks and note tails",
            ],
            "source": source_record,
            "candidate_a": anonymous["candidate_a"],
            "candidate_b": anonymous["candidate_b"],
            "heard": {"source": False, "candidate_a": False, "candidate_b": False},
            "choice": None,
            "notes": "",
        }
        answer_key = {
            "schema": ANSWER_KEY_SCHEMA,
            "status": "complete",
            "policy_id": POLICY_ID,
            "package_commitment": package_commitment,
            "blind_nonce_hex": blind_nonce.hex(),
            "blind_nonce_commitment": nonce_commitment,
            "package_contract": package_contract,
            "mapping": {
                "candidate_a": {
                    "identity": mapping["candidate_a"],
                    "precision": _precision_label(mapping["candidate_a"]),
                },
                "candidate_b": {
                    "identity": mapping["candidate_b"],
                    "precision": _precision_label(mapping["candidate_b"]),
                },
            },
            "raw_inputs": {
                "input_1": {
                    "precision": "original FP32 PyTorch checkpoint",
                    "float32_sha256": input_hashes["input_1"],
                    "audio": _audio_record(
                        private_dir / "input_1-raw.wav", destination
                    ),
                },
                "input_2": {
                    "precision": "published BF16 MLX checkpoint",
                    "float32_sha256": input_hashes["input_2"],
                    "audio": _audio_record(
                        private_dir / "input_2-raw.wav", destination
                    ),
                },
            },
            "level_match": level_evidence,
            "immutable_review_unit_sha256": _document_hash(
                _immutable_review_unit(unit)
            ),
        }
        answer_path = destination / "melroformer_precision_answer_key.json"
        _write_json(answer_path, answer_key)
        answer_sha256 = _sha256(answer_path)

        seed = {
            "schema": REVIEW_SCHEMA,
            "operation": "private-melroformer-precision-review",
            "status": "unreviewed",
            "blind": True,
            "review_required": True,
            "policy_id": POLICY_ID,
            "package_commitment": package_commitment,
            "question": (
                "Which vocal separation is more musically useful and less "
                "distracting, or are they effectively equivalent?"
            ),
            "policy": {
                "choices": sorted(_CHOICES),
                "source_reference_is_not_a_candidate": True,
                "source_reference_level_matched": False,
                "candidate_level_method": level_evidence["method"],
                "level_claim": "fixed-window sample RMS, not LUFS or perceived loudness",
                "time_shift_seconds": 0.0,
                "time_stretch_ratio": 1.0,
                "limiter_used": False,
                "compression_used": False,
                "equalisation_used": False,
            },
            "geometry": {
                "sample_rate": SAMPLE_RATE,
                "channels": 2,
                "frames": PARITY_FRAMES,
                "seconds": PARITY_FRAMES / SAMPLE_RATE,
                "alignment": "same exact source frames; one model chunk; no overlap",
            },
            "authorisation": {
                "track_id": authorisation.get("track_id"),
                "source_start_seconds": authorisation.get("source_start_seconds"),
                "report_sha256": authorisation.get("report_sha256"),
                "source_pcm24_sha256": authorisation.get("source_pcm24_sha256"),
            },
            "runtime_evidence": {
                "versions": dict(runtime_versions),
                "timings": dict(timings),
                "bf16_roundtrip_to_mlx_sdr_db": float(runtime_parity_sdr_db),
                "tracked_inference_parity_sha256": INFERENCE_PARITY_EVIDENCE_SHA256,
            },
            "review_evidence": {
                "manifest": manifest_path.name,
                "manifest_sha256": manifest_sha256,
                "audio_file_count": manifest["file_count"],
            },
            "answer_key": {
                "path": answer_path.name,
                "sha256": answer_sha256,
                "embedded_in_html": False,
            },
            "blind_assignment": {
                "policy": "secret-random-single-unit-v1",
                "nonce_commitment": nonce_commitment,
            },
            "summary": {"unit_count": 1, "reviewed_unit_count": 0},
            "units": [unit],
            "effects": _zero_effects(),
            "warnings": [
                "Do not open the separate answer key before exporting the completed review.",
                "Only A and B are fixed-window sample-RMS matched; the mixed source is an unlevelled reference.",
                "This review records listening evidence only and cannot enable, select or promote a separator.",
            ],
        }
        seed_path = destination / "melroformer_precision_review.json"
        _write_json(seed_path, seed)
        html_path = destination / "melroformer_precision_review.html"
        html_path.write_text(_review_html(seed), encoding="utf-8")
        os.chmod(html_path, 0o600)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise

    return {
        "schema": REVIEW_SCHEMA,
        "status": "complete",
        "out_dir": str(destination),
        "html": str(destination / "melroformer_precision_review.html"),
        "seed": str(destination / "melroformer_precision_review.json"),
        "answer_key": str(destination / "melroformer_precision_answer_key.json"),
        "answer_key_sha256": answer_sha256,
        "audio_manifest": str(manifest_path),
        "audio_manifest_sha256": manifest_sha256,
        "effects": _zero_effects(),
    }


def _resolve_private_melroformer_precision_review(
    review_path: str | Path,
    *,
    package_dir: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Verify and reveal one user-exported complete review without promotion."""

    package = Path(package_dir).expanduser().resolve()
    review_file = Path(review_path).expanduser().resolve()
    output = Path(out).expanduser().absolute()
    if os.path.lexists(output):
        raise FileExistsError(f"precision-review result already exists: {output}")
    seed_path = package / "melroformer_precision_review.json"
    seed = _read_json(seed_path)
    review = _read_json(review_file)
    if seed.get("schema") != REVIEW_SCHEMA or seed.get("status") != "unreviewed":
        raise ValueError("precision-review package seed is invalid")
    if not _browser_json_equal(
        _immutable_review_document(review), _immutable_review_document(seed)
    ):
        raise ValueError("precision-review export changed immutable evidence")
    units = list(review.get("units") or [])
    if (
        review.get("status") != "reviewed"
        or len(units) != 1
        or (review.get("summary") or {}).get("reviewed_unit_count") != 1
    ):
        raise ValueError("precision review is incomplete")
    unit = units[0]
    heard = unit.get("heard") or {}
    if (
        unit.get("choice") not in _CHOICES
        or any(
            heard.get(name) is not True
            for name in ("source", "candidate_a", "candidate_b")
        )
        or not isinstance(unit.get("notes"), str)
    ):
        raise ValueError("precision review has an incomplete listening decision")
    if review.get("effects") != _zero_effects():
        raise ValueError("precision review declares an automatic effect")
    _verify_review_audio(review, package)
    answer_record = seed.get("answer_key") or {}
    answer_path = package / str(answer_record.get("path", ""))
    if not answer_path.is_file() or _sha256(answer_path) != answer_record.get("sha256"):
        raise ValueError("precision-review answer key changed or is missing")
    answer = _read_json(answer_path)
    if (
        answer.get("schema") != ANSWER_KEY_SCHEMA
        or answer.get("package_commitment") != review.get("package_commitment")
        or answer.get("immutable_review_unit_sha256")
        != _document_hash(_immutable_review_unit(seed["units"][0]))
    ):
        raise ValueError("precision-review answer key is incompatible")
    _verify_blind_assignment(answer, seed)
    choice = str(unit["choice"])
    mapping = answer["mapping"]
    resolved_precision = (
        mapping[choice]["precision"]
        if choice in {"candidate_a", "candidate_b"}
        else choice
    )
    result = {
        "schema": RESULT_SCHEMA,
        "status": "complete",
        "blind_review": True,
        "policy_id": POLICY_ID,
        "package_commitment": review.get("package_commitment"),
        "review_sha256": _sha256(review_file),
        "seed_sha256": _sha256(seed_path),
        "answer_key_sha256": _sha256(answer_path),
        "choice": choice,
        "resolved_precision": resolved_precision,
        "candidate_a_precision": mapping["candidate_a"]["precision"],
        "candidate_b_precision": mapping["candidate_b"]["precision"],
        "notes": unit.get("notes", ""),
        "automatic_promotion_allowed": False,
        "decision_required_after_review": True,
        "effects": _zero_effects(),
    }
    _write_json_atomic(output, result)
    return result


def _level_match(
    values: Mapping[str, np.ndarray],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    if set(values) != {"input_1", "input_2"}:
        raise ValueError("precision level match requires exactly two inputs")
    rms = {name: _rms(value) for name, value in values.items()}
    if any(_dbfs(value) < _MINIMUM_RMS_DBFS for value in rms.values()):
        raise ValueError("precision-review candidate is below the RMS floor")
    target = min(rms.values())
    scales = {name: target / value for name, value in rms.items()}
    gain_db = {name: 20.0 * math.log10(scale) for name, scale in scales.items()}
    if any(value < -_MAXIMUM_PAIR_ATTENUATION_DB for value in gain_db.values()):
        raise ValueError("precision-review candidates differ by more than 18 dB")
    matched = {
        name: np.asarray(value * scales[name], dtype=np.float64)
        for name, value in values.items()
    }
    maximum_peak = max(float(np.max(np.abs(value))) for value in matched.values())
    common_peak_scale = min(1.0, (_FULL_SCALE_GUARD - 1e-6) / max(maximum_peak, 1e-12))
    if common_peak_scale < 1.0:
        matched = {name: value * common_peak_scale for name, value in matched.items()}
    after = {name: _rms(value) for name, value in matched.items()}
    if abs(_dbfs(after["input_1"]) - _dbfs(after["input_2"])) > 1e-7:
        raise RuntimeError("precision-review in-memory RMS matching failed")
    return matched, {
        "method": "pairwise-fixed-window-rms-attenuation-plus-common-peak-guard-v1",
        "minimum_rms_dbfs": _MINIMUM_RMS_DBFS,
        "maximum_pair_attenuation_db": _MAXIMUM_PAIR_ATTENUATION_DB,
        "common_peak_guard_linear_scale": round(common_peak_scale, 12),
        "limiter_used": False,
        "inputs": {
            name: {
                "rms_before_dbfs": round(_dbfs(rms[name]), 6),
                "pair_gain_db": round(gain_db[name], 6),
                "rms_after_dbfs": round(_dbfs(after[name]), 6),
                "peak_after_dbfs": round(
                    _dbfs(float(np.max(np.abs(matched[name])))), 6
                ),
            }
            for name in ("input_1", "input_2")
        },
    }


def _validated_audio(value: Any) -> np.ndarray:
    result = np.ascontiguousarray(value, dtype=np.dtype("<f4"))
    if result.ndim != 2 or result.shape[1] != 2 or not np.isfinite(result).all():
        raise ValueError("precision-review audio must be finite stereo float32")
    return result


def _write_audio(path: Path, values: np.ndarray, *, subtype: str) -> None:
    soundfile.write(path, values, SAMPLE_RATE, subtype=subtype)
    os.chmod(path, 0o600)


def _audio_record(path: Path, root: Path) -> dict[str, Any]:
    values, rate = soundfile.read(path, dtype="float64", always_2d=True)
    if int(rate) != SAMPLE_RATE or len(values) != PARITY_FRAMES or values.shape[1] != 2:
        raise RuntimeError("precision-review audio geometry changed")
    if not np.isfinite(values).all():
        raise RuntimeError("precision-review audio is non-finite")
    peak = float(np.max(np.abs(values)))
    if path.parent.name == "audio" and peak >= _FULL_SCALE_GUARD:
        raise RuntimeError("precision-review listening audio is clipped")
    return {
        "audio": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "sample_rate": int(rate),
        "channels": int(values.shape[1]),
        "frames": int(len(values)),
        "rms_dbfs": round(_dbfs(_rms(values)), 6),
        "peak_dbfs": round(_dbfs(peak), 6),
    }


def _verify_review_audio(review: Mapping[str, Any], package: Path) -> None:
    evidence = review.get("review_evidence") or {}
    manifest_path = package / str(evidence.get("manifest", ""))
    if not manifest_path.is_file() or _sha256(manifest_path) != evidence.get(
        "manifest_sha256"
    ):
        raise ValueError("precision-review audio manifest changed")
    manifest = _read_json(manifest_path)
    rows = {str(row.get("path")): row for row in manifest.get("files", [])}
    if (
        manifest.get("schema") != AUDIO_MANIFEST_SCHEMA
        or manifest.get("package_commitment") != review.get("package_commitment")
        or len(rows) != 3
    ):
        raise ValueError("precision-review audio manifest is incompatible")
    referenced = set()
    for name in ("source", "candidate_a", "candidate_b"):
        record = review["units"][0][name]
        relative = str(record.get("audio", ""))
        path = (package / relative).resolve()
        if (
            package not in path.parents
            or not path.is_file()
            or _sha256(path) != record.get("sha256")
        ):
            raise ValueError("precision-review listening audio changed")
        if (rows.get(relative) or {}).get("sha256") != record.get("sha256"):
            raise ValueError("precision-review audio manifest differs")
        referenced.add(relative)
    if referenced != set(rows):
        raise ValueError("precision-review audio references differ")


def _verify_blind_assignment(
    answer: Mapping[str, Any], seed: Mapping[str, Any]
) -> None:
    try:
        nonce = bytes.fromhex(str(answer.get("blind_nonce_hex", "")))
        commitment = str(seed.get("package_commitment", ""))
        commitment_bytes = bytes.fromhex(commitment)
    except ValueError as error:
        raise ValueError("precision-review blind nonce is invalid") from error
    if len(nonce) != 32 or len(commitment_bytes) != 32:
        raise ValueError("precision-review blind nonce is invalid")
    nonce_commitment = hashlib.sha256(nonce + commitment_bytes).hexdigest()
    expected = _blind_mapping(nonce, commitment)
    mapping = answer.get("mapping") or {}
    if (
        nonce_commitment != answer.get("blind_nonce_commitment")
        or nonce_commitment
        != (seed.get("blind_assignment") or {}).get("nonce_commitment")
        or any(
            (mapping.get(slot) or {}).get("identity") != identity
            for slot, identity in expected.items()
        )
    ):
        raise ValueError("precision-review blind assignment is invalid")


def _blind_mapping(nonce: bytes, commitment: str) -> dict[str, str]:
    if hashlib.sha256(nonce + bytes.fromhex(commitment)).digest()[0] % 2:
        return {"candidate_a": "input_2", "candidate_b": "input_1"}
    return {"candidate_a": "input_1", "candidate_b": "input_2"}


def _precision_label(identity: str) -> str:
    return {
        "input_1": "original FP32 PyTorch checkpoint",
        "input_2": "published BF16 MLX checkpoint",
    }[identity]


def _manifest_row(record: Mapping[str, Any], purpose: str) -> dict[str, Any]:
    return {"path": record["audio"], "sha256": record["sha256"], "purpose": purpose}


def _immutable_review_unit(unit: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(unit))
    for key in ("heard", "choice", "notes"):
        result.pop(key, None)
    return result


def _immutable_review_document(document: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(document))
    result["status"] = "unreviewed"
    result["summary"]["reviewed_unit_count"] = 0
    for unit in result["units"]:
        unit["heard"] = {"source": False, "candidate_a": False, "candidate_b": False}
        unit["choice"] = None
        unit["notes"] = ""
    return result


def _browser_json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        return (
            isinstance(left, Mapping)
            and isinstance(right, Mapping)
            and set(left) == set(right)
            and all(_browser_json_equal(left[key], right[key]) for key in left)
        )
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(_browser_json_equal(a, b) for a, b in zip(left, right))
        )
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left is right
    if isinstance(left, (int, float)) or isinstance(right, (int, float)):
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            return False
        if not math.isfinite(float(left)) or not math.isfinite(float(right)):
            return False
        return float(left) == float(right)
    return type(left) is type(right) and left == right


def _zero_effects() -> dict[str, Any]:
    return {
        "separator_enabled": False,
        "source_audio_mutated": False,
        "candidate_audio_mutated": False,
        "checkpoint_mutated": False,
        "selection_changed": False,
        "promotion_allowed": False,
        "default_changed": False,
        "product_route_changed": False,
    }


def _review_html(seed: Mapping[str, Any]) -> str:
    payload = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    focus = "".join(
        f"<li>{_html(item)}</li>" for item in seed["units"][0]["listening_focus"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend Kim Vocal 2 precision review</title><style>
body{{font-family:system-ui,sans-serif;background:#101820;color:#edf4f8;margin:0;padding:2rem;line-height:1.5}}main{{max-width:1050px;margin:auto}}.panel{{background:#192631;border:1px solid #405565;border-radius:16px;padding:1.3rem;margin:1rem 0}}.players{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem}}audio{{width:100%}}label{{display:block;margin:.55rem 0}}button{{font-size:1rem;padding:.7rem 1rem;margin:.3rem;border:0;border-radius:9px;background:#2d638c;color:white}}textarea{{width:100%;min-height:5rem;background:#0e1720;color:white;border:1px solid #60798c;border-radius:8px}}.warning{{border-left:4px solid #ffd166;padding:.8rem;background:#2a261a}}.status{{color:#ffd166;font-size:1.2rem}}</style></head>
<body><main><h1>Kim Vocal 2 precision review</h1><section class="panel"><p><b>{_html(seed["question"])}</b></p><p>This is one eight-second passage. The source is the original mixed music. A and B are two anonymous vocal separations from the same model architecture and exact source frames; only checkpoint precision/runtime differs.</p><p>Listen for:</p><ul>{focus}</ul><p class="warning">Judge musical usefulness and artefacts, not volume. A and B are sample-RMS matched. The source is not level matched. Equivalent, neither and cannot tell are valid.</p><p>Do not open the separate answer key before exporting this review.</p></section>
<p id="status" class="status">Not reviewed</p><section class="panel" id="unit"></section><button id="mark">Mark choice reviewed</button><button id="export">Export reviewed JSON</button>
<script>
const review={payload};const u=review.units[0],root=document.getElementById('unit');let current=null,playhead=0;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
root.innerHTML=`<h2>${{u.source_seconds[0].toFixed(2)}}–${{u.source_seconds[1].toFixed(2)}} source seconds</h2><div class="players">${{[['source','Mixed source reference'],['candidate_a','Candidate A'],['candidate_b','Candidate B']].map(([key,label])=>`<div><b>${{label}}</b><audio id="${{key}}" controls loop preload="metadata" src="${{esc(u[key].audio)}}"></audio><label><input type="checkbox" data-heard="${{key}}"> I heard ${{label}}</label></div>`).join('')}}</div><div>${{[['source','source'],['candidate_a','A'],['candidate_b','B']].map(([key,label])=>`<button type="button" data-play="${{key}}">Play ${{label}} from same point</button>`).join('')}}</div><h3>Which is more musically useful?</h3>${{[['candidate_a','Candidate A'],['candidate_b','Candidate B'],['equivalent','Equivalent / no clear preference'],['neither','Neither is useful'],['cannot_tell','I cannot tell']].map(([value,label])=>`<label><input type="radio" name="choice" value="${{value}}"> ${{label}}</label>`).join('')}}<label>Optional private note<textarea></textarea></label>`;
document.querySelectorAll('audio').forEach(a=>{{a.onplay=()=>{{if(current&&current!==a)current.pause();current=a;a.currentTime=Math.min(playhead,Math.max(0,(a.duration||0)-.01))}};a.ontimeupdate=()=>{{if(current===a)playhead=a.currentTime}}}});document.querySelectorAll('[data-play]').forEach(b=>b.onclick=()=>{{const a=document.getElementById(b.dataset.play);document.querySelectorAll('audio').forEach(x=>x.pause());a.currentTime=Math.min(playhead,Math.max(0,(a.duration||0)-.01));current=a;a.play()}});
function sync(){{u.choice=document.querySelector('input[type=radio]:checked')?.value||null;u.notes=document.querySelector('textarea').value;for(const key of ['source','candidate_a','candidate_b'])u.heard[key]=document.querySelector(`[data-heard="${{key}}"]`).checked;if(review.status==='reviewed'&&(!u.choice||!Object.values(u.heard).every(Boolean)))review.status='unreviewed';document.getElementById('status').textContent=review.status==='reviewed'?'Review complete':'Not reviewed';}}root.onchange=sync;root.oninput=sync;
document.getElementById('mark').onclick=()=>{{sync();if(!u.choice||!Object.values(u.heard).every(Boolean)){{alert('Hear the source, A and B and choose one outcome first.');return}}review.status='reviewed';review.summary.reviewed_unit_count=1;document.getElementById('status').textContent='Review complete';}};
document.getElementById('export').onclick=()=>{{sync();if(review.status!=='reviewed'){{alert('Mark the choice reviewed before exporting.');return}}const blob=new Blob([JSON.stringify(review,null,2)+'\\n'],{{type:'application/json'}}),link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='melroformer_precision_review.reviewed.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);}};
</script></main></body></html>"""


def _html(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _rms(value: np.ndarray) -> float:
    return math.sqrt(float(np.mean(np.square(np.asarray(value, dtype=np.float64)))))


def _dbfs(value: float) -> float:
    return 20.0 * math.log10(max(float(value), 1e-12))


def _document_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        payload = (
            json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
        ).encode()
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("precision-review atomic write made no progress")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


__all__ = [
    "ANSWER_KEY_SCHEMA",
    "AUDIO_MANIFEST_SCHEMA",
    "POLICY_ID",
    "RESULT_SCHEMA",
    "REVIEW_SCHEMA",
    "_create_private_melroformer_precision_review",
    "_resolve_private_melroformer_precision_review",
    "_run_private_melroformer_precision_review",
]
