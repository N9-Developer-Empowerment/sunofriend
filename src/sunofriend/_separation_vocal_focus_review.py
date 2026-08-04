"""Blind, source-bound review of several private vocal-separation candidates.

This diagnostic follows a human-described missing vocal event through one exact
authorised excerpt.  It keeps Kim and provider alternatives anonymous, asks for
independent ratings, and creates no selection, activation or publication gate.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import stat
from typing import Any, Mapping, Sequence

import numpy as np

from ._separation_audio_quality_review import (
    SAMPLE_RATE,
    _audio_record,
    _document_hash,
    _html,
    _load_json,
    _make_private_tree,
    _manifest_row,
    _read_exact_audio,
    _read_json,
    _regular_audio,
    _safe_id,
    _validate_candidate,
    _validate_excerpt,
    _validate_mapping,
    _zero_effects,
    _zero_permissions,
)
from ._separation_authorised_midi_comparison import (
    _artifact_path,
    _document_sha256,
    _regular_json,
    _sha256,
)
from ._separation_melroformer_precision_review import (
    _browser_json_equal,
    _write_audio,
    _write_json,
    _write_json_atomic,
)


REVIEW_SCHEMA = "sunofriend.private-separated-vocal-focus-review.v1"
ANSWER_KEY_SCHEMA = "sunofriend.private-separated-vocal-focus-answer-key.v1"
RESULT_SCHEMA = "sunofriend.private-separated-vocal-focus-result.v1"
AUDIO_MANIFEST_SCHEMA = "sunofriend.private-separated-vocal-focus-manifest.v1"
POLICY_ID = "private-separated-vocal-focus-v1"
_MAXIMUM_FOCUS_CHARACTERS = 500
_MAXIMUM_PROVIDER_COUNT = 5
_MINIMUM_RMS_DBFS = -60.0
_MAXIMUM_ATTENUATION_DB = 18.0
_FULL_SCALE_GUARD = 0.9999
_FOCUS_RETENTION = frozenset(
    ("substantially_complete", "partially_complete", "little_or_none", "cannot_tell")
)
_PROBLEM_SEVERITY = frozenset(("low", "noticeable", "severe", "cannot_tell"))
_USEFULNESS = frozenset(("yes", "no", "cannot_tell"))


@dataclass(frozen=True)
class VocalFocusInput:
    """One exact source with Kim plus one or more provider vocal estimates."""

    track_id: str
    authorised_excerpt: Path
    candidate_midi_evaluation: Path
    role_mapping: Path
    provider_ids: tuple[str, ...]


@dataclass(frozen=True)
class _LoadedFocus:
    track_id: str
    source_track_id: str
    excerpt: Any
    candidate: Any
    mapping: Any
    source_path: Path
    source_audio: np.ndarray
    candidate_paths: Mapping[str, Path]
    candidate_audio: Mapping[str, np.ndarray]
    start_seconds: float
    end_seconds: float


def _create_private_separated_vocal_focus_review(
    source: VocalFocusInput,
    *,
    focus: str,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Create one fresh blinded multi-candidate vocal-focus review."""

    focus = _validated_focus(focus)
    loaded = _load_focus(source)
    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"separated-vocal focus review already exists: {destination}"
        )

    contract = _package_contract(loaded, focus)
    package_commitment = _document_hash(contract)
    blind_nonce = secrets.token_bytes(32)
    nonce_commitment = hashlib.sha256(
        blind_nonce + bytes.fromhex(package_commitment)
    ).hexdigest()
    mapping = _blind_mapping(
        blind_nonce,
        package_commitment,
        loaded.track_id,
        tuple(sorted(loaded.candidate_audio)),
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.mkdir(mode=0o700)
        audio_root = destination / "audio"
        audio_root.mkdir(mode=0o700)
        matched, level_evidence = _level_match_many(
            {
                identity: np.asarray(values, dtype=np.float64)
                for identity, values in loaded.candidate_audio.items()
            }
        )
        source_path = audio_root / "source-reference.wav"
        _write_audio(source_path, loaded.source_audio, subtype="PCM_24")
        source_record = _audio_record(source_path, destination)

        candidates: dict[str, dict[str, Any]] = {}
        manifest_rows = [
            _manifest_row(source_record, loaded.track_id, "mixed-source-reference")
        ]
        for slot, identity in mapping.items():
            path = audio_root / f"{slot}.wav"
            _write_audio(path, matched[identity], subtype="PCM_24")
            record = _audio_record(path, destination)
            candidates[slot] = record
            manifest_rows.append(
                _manifest_row(record, loaded.track_id, f"blinded-{slot}")
            )
        rms_values = [record["rms_dbfs"] for record in candidates.values()]
        mismatch = max(rms_values) - min(rms_values)
        if mismatch > 0.05:
            raise RuntimeError("separated-vocal focus PCM24 candidate levels differ")
        level_evidence["final_pcm24"] = {
            "candidate_rms_dbfs": {
                slot: candidates[slot]["rms_dbfs"] for slot in sorted(candidates)
            },
            "maximum_mismatch_db": round(mismatch, 6),
            "within_tolerance": True,
        }

        unit = {
            "unit_id": loaded.track_id,
            "track_id": loaded.track_id,
            "source_track_id": loaded.source_track_id,
            "source_seconds": [loaded.start_seconds, loaded.end_seconds],
            "duration_seconds": loaded.end_seconds - loaded.start_seconds,
            "sample_rate": SAMPLE_RATE,
            "frame_count": len(loaded.source_audio),
            "source": source_record,
            "candidate_slots": list(mapping),
            "candidates": candidates,
            "heard": {
                "source": False,
                **{slot: False for slot in mapping},
            },
            "ratings": {slot: _empty_ratings() for slot in mapping},
            "notes": "",
        }
        manifest = {
            "schema": AUDIO_MANIFEST_SCHEMA,
            "package_commitment": package_commitment,
            "file_count": len(manifest_rows),
            "files": manifest_rows,
        }
        manifest_path = destination / "separated_vocal_focus_manifest.json"
        _write_json(manifest_path, manifest)
        manifest_sha256 = _sha256(manifest_path)

        answer_key = {
            "schema": ANSWER_KEY_SCHEMA,
            "status": "complete",
            "policy_id": POLICY_ID,
            "package_commitment": package_commitment,
            "blind_nonce_hex": blind_nonce.hex(),
            "blind_nonce_commitment": nonce_commitment,
            "package_contract": contract,
            "mapping": dict(mapping),
            "level_match": level_evidence,
            "immutable_review_unit_sha256": _document_hash(_immutable_unit(unit)),
        }
        answer_path = destination / "separated_vocal_focus_answer_key.json"
        _write_json(answer_path, answer_key)
        answer_sha256 = _sha256(answer_path)

        seed = {
            "schema": REVIEW_SCHEMA,
            "operation": "private-separated-vocal-focus-review",
            "status": "unreviewed",
            "evidence_scope": "private_development_only",
            "blind": True,
            "review_required": True,
            "policy_id": POLICY_ID,
            "package_commitment": package_commitment,
            "focus": focus,
            "question": (
                "Which anonymous separation candidates preserve the exact vocal "
                "event described below, without unacceptable music bleed or artefacts?"
            ),
            "policy": {
                "focus_retention_choices": sorted(_FOCUS_RETENTION),
                "bleed_choices": sorted(_PROBLEM_SEVERITY),
                "artefact_choices": sorted(_PROBLEM_SEVERITY),
                "useful_for_focus_choices": sorted(_USEFULNESS),
                "ratings_are_independent_per_candidate": True,
                "multiple_useful_candidates_allowed": True,
                "provider_control_is_not_ground_truth": True,
                "source_reference_is_not_a_candidate": True,
                "source_reference_level_matched": False,
                "candidate_level_method": (
                    "multi-candidate-fixed-window-rms-attenuation-plus-common-peak-guard-v1"
                ),
                "level_claim": "fixed-window sample RMS, not perceived loudness",
                "automatic_selection": False,
                "automatic_promotion": False,
                "production_eligible": False,
            },
            "geometry": {
                "sample_rate": SAMPLE_RATE,
                "channels": 2,
                "candidate_count": len(mapping),
                "alignment": "one exact authorised excerpt at recorded zero",
            },
            "review_evidence": {
                "manifest": manifest_path.name,
                "manifest_sha256": manifest_sha256,
                "audio_file_count": len(manifest_rows),
            },
            "answer_key": {
                "path": answer_path.name,
                "sha256": answer_sha256,
                "embedded_in_html": False,
            },
            "blind_assignment": {
                "policy": "secret-random-per-focus-review-v1",
                "nonce_commitment": nonce_commitment,
            },
            "summary": {"candidate_count": len(mapping), "reviewed_candidate_count": 0},
            "unit": unit,
            "permissions": _zero_permissions(),
            "effects": _zero_effects(),
            "warnings": [
                "Do not open the separate answer key before exporting the completed review.",
                "Candidates are sample-RMS matched; the mixed source is not level matched.",
                "A provider candidate is a comparison control, not score truth.",
                "This diagnostic cannot select, activate, promote or publish a separator.",
            ],
        }
        seed_path = destination / "separated_vocal_focus_review.json"
        _write_json(seed_path, seed)
        html_path = destination / "separated_vocal_focus_review.html"
        html_path.write_text(_review_html(seed), encoding="utf-8")
        html_path.chmod(0o600)
        _make_private_tree(destination)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise

    return {
        "schema": REVIEW_SCHEMA,
        "status": "complete",
        "out_dir": str(destination),
        "html": str(html_path),
        "seed": str(seed_path),
        "answer_key": str(answer_path),
        "answer_key_sha256": answer_sha256,
        "audio_manifest": str(manifest_path),
        "audio_manifest_sha256": manifest_sha256,
        "permissions": _zero_permissions(),
        "effects": _zero_effects(),
    }


def _resolve_private_separated_vocal_focus_review(
    review_path: str | Path,
    *,
    package_dir: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Verify one browser export and reveal the bound candidate identities."""

    package = Path(package_dir).expanduser().resolve(strict=True)
    review_file = _regular_json(review_path, "reviewed vocal-focus export")
    output = Path(out).expanduser().absolute()
    if os.path.lexists(output):
        raise FileExistsError(f"vocal-focus result already exists: {output}")
    seed_path = package / "separated_vocal_focus_review.json"
    seed = _read_json(seed_path)
    review = _read_json(review_file)
    if seed.get("schema") != REVIEW_SCHEMA or seed.get("status") != "unreviewed":
        raise ValueError("separated-vocal focus package seed is invalid")
    if not _browser_json_equal(
        _immutable_review_document(review), _immutable_review_document(seed)
    ):
        raise ValueError("separated-vocal focus export changed immutable evidence")
    _validate_completed_unit(review.get("unit"))
    if review.get("status") != "reviewed":
        raise ValueError("separated-vocal focus review is incomplete")
    candidate_count = len(review["unit"]["candidate_slots"])
    if (review.get("summary") or {}).get("reviewed_candidate_count") != candidate_count:
        raise ValueError("separated-vocal focus review is incomplete")
    if review.get("permissions") != _zero_permissions():
        raise ValueError("separated-vocal focus review declares a permission")
    if review.get("effects") != _zero_effects():
        raise ValueError("separated-vocal focus review declares an automatic effect")
    _verify_review_audio(review, package)

    answer_record = seed.get("answer_key") or {}
    answer_path = package / str(answer_record.get("path", ""))
    if not answer_path.is_file() or _sha256(answer_path) != answer_record.get("sha256"):
        raise ValueError("separated-vocal focus answer key changed or is missing")
    answer = _read_json(answer_path)
    _verify_answer_key(answer, seed)
    mapping = answer["mapping"]
    ratings = {
        mapping[slot]: dict(review["unit"]["ratings"][slot])
        for slot in review["unit"]["candidate_slots"]
    }
    results = {
        "useful_for_focus": sorted(
            method
            for method, row in ratings.items()
            if row["useful_for_focus"] == "yes"
        ),
        "not_useful_for_focus": sorted(
            method for method, row in ratings.items() if row["useful_for_focus"] == "no"
        ),
        "cannot_tell": sorted(
            method
            for method, row in ratings.items()
            if row["useful_for_focus"] == "cannot_tell"
        ),
    }
    result = {
        "schema": RESULT_SCHEMA,
        "status": "complete_review_no_activation",
        "evidence_scope": "private_development_only",
        "blind_review": True,
        "policy_id": POLICY_ID,
        "package_commitment": review["package_commitment"],
        "review_sha256": _sha256(review_file),
        "seed_sha256": _sha256(seed_path),
        "answer_key_sha256": _sha256(answer_path),
        "focus": review["focus"],
        "source_binding": deepcopy(answer["package_contract"]["source_binding"]),
        "ratings_by_method": ratings,
        "results": results,
        "notes": review["unit"]["notes"],
        "interpretation": {
            "ratings_are_human_listening_evidence": True,
            "useful_is_focus_relative": True,
            "multiple_useful_candidates_allowed": True,
            "winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": _zero_permissions(),
        "effects": _zero_effects(),
    }
    result["document_sha256"] = _document_sha256(result)
    _write_json_atomic(output, result)
    output.chmod(0o600)
    return {**result, "report": str(output)}


def _load_focus(source: VocalFocusInput) -> _LoadedFocus:
    track_id = _safe_id(source.track_id, "track ID")
    provider_ids = tuple(source.provider_ids)
    if not 1 <= len(provider_ids) <= _MAXIMUM_PROVIDER_COUNT or len(
        set(provider_ids)
    ) != len(provider_ids):
        raise ValueError("vocal-focus review requires 1-5 unique provider IDs")
    excerpt = _load_json(source.authorised_excerpt, "authorised excerpt")
    candidate = _load_json(source.candidate_midi_evaluation, "candidate evaluation")
    mapping = _load_json(source.role_mapping, "role mapping")
    _validate_excerpt(excerpt)
    _validate_candidate(candidate, excerpt)
    validated = [
        _validate_mapping(mapping, excerpt, provider_id=provider_id)
        for provider_id in provider_ids
    ]
    if len(set(validated)) != 1:
        raise ValueError("provider role mappings do not share one exact source window")
    source_track_id, start, end = validated[0]

    source_record = excerpt.document["artifacts"].get(
        "LOCAL-MODEL-INPUT/source-44100.wav"
    )
    if not isinstance(source_record, Mapping):
        raise ValueError("authorised 44.1 kHz source artifact is missing")
    source_path = _artifact_path(
        excerpt.path.parent,
        {"path": "LOCAL-MODEL-INPUT/source-44100.wav", **source_record},
        "authorised source audio",
    )
    worker = candidate.document["worker"]
    kim_path = _regular_audio(
        candidate.document["candidate"]["primary"]["independent_evaluation"][
            "stem_path"
        ],
        "Kim vocal candidate",
    )
    if kim_path.stat().st_size != worker.get("vocal_pcm24_bytes") or _sha256(
        kim_path
    ) != worker.get("vocal_pcm24_sha256"):
        raise ValueError("Kim vocal candidate identity changed")

    paths: dict[str, Path] = {"kim-vocal-2": kim_path}
    for provider_id in provider_ids:
        artifact = mapping.document["groups"][provider_id]["vocals"]["artifact"]
        paths[f"provider-{provider_id}-broad-vocals"] = _artifact_path(
            mapping.path.parent,
            artifact,
            f"{provider_id} broad-vocal audio",
        )
    duration = end - start
    return _LoadedFocus(
        track_id=track_id,
        source_track_id=source_track_id,
        excerpt=excerpt,
        candidate=candidate,
        mapping=mapping,
        source_path=source_path,
        source_audio=_read_exact_audio(source_path, duration, "source"),
        candidate_paths=paths,
        candidate_audio={
            identity: _read_exact_audio(path, duration, identity)
            for identity, path in paths.items()
        },
        start_seconds=start,
        end_seconds=end,
    )


def _package_contract(loaded: _LoadedFocus, focus: str) -> dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "focus": focus,
        "source_binding": {
            "track_id": loaded.track_id,
            "source_track_id": loaded.source_track_id,
            "start_seconds": loaded.start_seconds,
            "end_seconds": loaded.end_seconds,
            "authorised_excerpt_sha256": loaded.excerpt.file_sha256,
            "authorised_excerpt_document_sha256": loaded.excerpt.document[
                "document_sha256"
            ],
            "candidate_evaluation_sha256": loaded.candidate.file_sha256,
            "candidate_evaluation_document_sha256": loaded.candidate.document[
                "document_sha256"
            ],
            "role_mapping_sha256": loaded.mapping.file_sha256,
            "role_mapping_document_sha256": loaded.mapping.document["document_sha256"],
            "source_audio_sha256": _sha256(loaded.source_path),
            "candidate_audio_sha256": {
                identity: _sha256(path)
                for identity, path in sorted(loaded.candidate_paths.items())
            },
            "sample_rate": SAMPLE_RATE,
            "channels": 2,
            "frames": len(loaded.source_audio),
        },
    }


def _blind_mapping(
    nonce: bytes,
    commitment: str,
    track_id: str,
    identities: Sequence[str],
) -> dict[str, str]:
    ranked = sorted(
        identities,
        key=lambda identity: hashlib.sha256(
            nonce
            + bytes.fromhex(commitment)
            + track_id.encode("ascii")
            + identity.encode("ascii")
        ).digest(),
    )
    return {
        f"candidate_{chr(ord('a') + index)}": identity
        for index, identity in enumerate(ranked)
    }


def _validated_focus(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("vocal-focus description must be text")
    result = " ".join(value.split())
    if not result or len(result) > _MAXIMUM_FOCUS_CHARACTERS:
        raise ValueError("vocal-focus description must contain 1-500 characters")
    return result


def _level_match_many(
    values: Mapping[str, np.ndarray],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    if not 2 <= len(values) <= 6:
        raise ValueError("vocal-focus level match requires 2-6 candidates")
    rms = {
        name: math.sqrt(float(np.mean(np.square(value))))
        for name, value in values.items()
    }

    def dbfs(value: float) -> float:
        return 20.0 * math.log10(max(float(value), 1e-12))

    if any(dbfs(value) < _MINIMUM_RMS_DBFS for value in rms.values()):
        raise ValueError("vocal-focus candidate is below the RMS floor")
    target = min(rms.values())
    scales = {name: target / value for name, value in rms.items()}
    gain_db = {name: 20.0 * math.log10(scale) for name, scale in scales.items()}
    if any(value < -_MAXIMUM_ATTENUATION_DB for value in gain_db.values()):
        raise ValueError("vocal-focus candidates differ by more than 18 dB")
    matched = {
        name: np.asarray(value * scales[name], dtype=np.float64)
        for name, value in values.items()
    }
    maximum_peak = max(float(np.max(np.abs(value))) for value in matched.values())
    common_peak_scale = min(1.0, (_FULL_SCALE_GUARD - 1e-6) / max(maximum_peak, 1e-12))
    if common_peak_scale < 1.0:
        matched = {name: value * common_peak_scale for name, value in matched.items()}
    after = {
        name: math.sqrt(float(np.mean(np.square(value))))
        for name, value in matched.items()
    }
    after_dbfs = [dbfs(value) for value in after.values()]
    if max(after_dbfs) - min(after_dbfs) > 1e-7:
        raise RuntimeError("vocal-focus in-memory RMS matching failed")
    return matched, {
        "method": (
            "multi-candidate-fixed-window-rms-attenuation-plus-common-peak-guard-v1"
        ),
        "minimum_rms_dbfs": _MINIMUM_RMS_DBFS,
        "maximum_attenuation_db": _MAXIMUM_ATTENUATION_DB,
        "common_peak_guard_linear_scale": round(common_peak_scale, 12),
        "limiter_used": False,
        "inputs": {
            name: {
                "rms_before_dbfs": round(dbfs(rms[name]), 6),
                "gain_db": round(gain_db[name], 6),
                "rms_after_dbfs": round(dbfs(after[name]), 6),
                "peak_after_dbfs": round(dbfs(float(np.max(np.abs(matched[name])))), 6),
            }
            for name in sorted(values)
        },
    }


def _empty_ratings() -> dict[str, None]:
    return {
        "focus_retention": None,
        "non_vocal_bleed": None,
        "artefacts": None,
        "useful_for_focus": None,
    }


def _validate_completed_unit(unit: Any) -> None:
    if not isinstance(unit, Mapping):
        raise ValueError("separated-vocal focus unit differs")
    slots = unit.get("candidate_slots")
    heard = unit.get("heard")
    ratings = unit.get("ratings")
    if (
        not isinstance(slots, list)
        or not slots
        or len(set(slots)) != len(slots)
        or not isinstance(heard, Mapping)
        or set(heard) != {"source", *slots}
        or any(value is not True for value in heard.values())
        or not isinstance(ratings, Mapping)
        or set(ratings) != set(slots)
        or not isinstance(unit.get("notes"), str)
        or len(unit["notes"]) > 4_000
    ):
        raise ValueError("separated-vocal focus review is incomplete")
    for slot in slots:
        row = ratings[slot]
        if (
            not isinstance(row, Mapping)
            or set(row)
            != {"focus_retention", "non_vocal_bleed", "artefacts", "useful_for_focus"}
            or row.get("focus_retention") not in _FOCUS_RETENTION
            or row.get("non_vocal_bleed") not in _PROBLEM_SEVERITY
            or row.get("artefacts") not in _PROBLEM_SEVERITY
            or row.get("useful_for_focus") not in _USEFULNESS
        ):
            raise ValueError("separated-vocal focus candidate ratings are incomplete")


def _verify_review_audio(review: Mapping[str, Any], package: Path) -> None:
    evidence = review.get("review_evidence") or {}
    manifest_path = package / str(evidence.get("manifest", ""))
    if not manifest_path.is_file() or _sha256(manifest_path) != evidence.get(
        "manifest_sha256"
    ):
        raise ValueError("separated-vocal focus manifest changed")
    manifest = _read_json(manifest_path)
    rows = {str(row.get("path")): row for row in manifest.get("files", [])}
    unit = review["unit"]
    expected_count = 1 + len(unit["candidate_slots"])
    if (
        manifest.get("schema") != AUDIO_MANIFEST_SCHEMA
        or manifest.get("package_commitment") != review.get("package_commitment")
        or manifest.get("file_count") != expected_count
        or len(rows) != expected_count
    ):
        raise ValueError("separated-vocal focus manifest is incompatible")
    records = [
        unit["source"],
        *[unit["candidates"][slot] for slot in unit["candidate_slots"]],
    ]
    referenced = set()
    for record in records:
        relative = str(record.get("audio", ""))
        unresolved = package / relative
        try:
            details = unresolved.lstat()
        except OSError as error:
            raise ValueError("separated-vocal focus audio changed") from error
        path = unresolved.resolve(strict=True)
        if (
            package not in path.parents
            or stat.S_ISLNK(details.st_mode)
            or not stat.S_ISREG(details.st_mode)
            or path.stat().st_size != record.get("bytes")
            or _sha256(path) != record.get("sha256")
            or (rows.get(relative) or {}).get("sha256") != record.get("sha256")
        ):
            raise ValueError("separated-vocal focus audio changed")
        referenced.add(relative)
    if referenced != set(rows):
        raise ValueError("separated-vocal focus audio references differ")


def _verify_answer_key(answer: Mapping[str, Any], seed: Mapping[str, Any]) -> None:
    contract = answer.get("package_contract")
    if (
        answer.get("schema") != ANSWER_KEY_SCHEMA
        or answer.get("status") != "complete"
        or answer.get("policy_id") != POLICY_ID
        or answer.get("package_commitment") != seed.get("package_commitment")
        or not isinstance(contract, Mapping)
        or _document_hash(contract) != seed.get("package_commitment")
        or contract.get("policy_id") != POLICY_ID
        or contract.get("focus") != seed.get("focus")
    ):
        raise ValueError("separated-vocal focus answer key is incompatible")
    try:
        nonce = bytes.fromhex(str(answer.get("blind_nonce_hex", "")))
        commitment = str(seed.get("package_commitment", ""))
        commitment_bytes = bytes.fromhex(commitment)
    except ValueError as error:
        raise ValueError("separated-vocal focus blind nonce is invalid") from error
    expected_nonce_commitment = hashlib.sha256(nonce + commitment_bytes).hexdigest()
    if (
        len(nonce) != 32
        or len(commitment_bytes) != 32
        or expected_nonce_commitment != answer.get("blind_nonce_commitment")
        or expected_nonce_commitment
        != (seed.get("blind_assignment") or {}).get("nonce_commitment")
    ):
        raise ValueError("separated-vocal focus blind commitment differs")
    identities = tuple(
        sorted((contract.get("source_binding") or {}).get("candidate_audio_sha256", {}))
    )
    expected_mapping = _blind_mapping(
        nonce, commitment, str(seed["unit"]["track_id"]), identities
    )
    if answer.get("mapping") != expected_mapping or answer.get(
        "immutable_review_unit_sha256"
    ) != _document_hash(_immutable_unit(seed["unit"])):
        raise ValueError("separated-vocal focus blind assignment differs")


def _immutable_unit(unit: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(unit))
    for key in ("heard", "ratings", "notes"):
        result.pop(key, None)
    return result


def _immutable_review_document(document: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(document))
    result["status"] = "unreviewed"
    slots = result["unit"]["candidate_slots"]
    result["summary"]["reviewed_candidate_count"] = 0
    result["unit"]["heard"] = {"source": False, **{slot: False for slot in slots}}
    result["unit"]["ratings"] = {slot: _empty_ratings() for slot in slots}
    result["unit"]["notes"] = ""
    return result


def _review_html(seed: Mapping[str, Any]) -> str:
    payload = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend vocal-focus review</title><style>
body{{font-family:system-ui,sans-serif;background:#101820;color:#edf4f8;margin:0;padding:2rem;line-height:1.5}}main{{max-width:1180px;margin:auto}}.panel{{background:#192631;border:1px solid #405565;border-radius:16px;padding:1.3rem;margin:1rem 0}}.players,.ratings{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:1rem}}audio{{width:100%}}label{{display:block;margin:.45rem 0}}button{{font-size:1rem;padding:.7rem 1rem;margin:.3rem;border:0;border-radius:9px;background:#2d638c;color:white}}select,textarea{{width:100%;box-sizing:border-box;background:#0e1720;color:white;border:1px solid #60798c;border-radius:8px;padding:.5rem}}textarea{{min-height:5rem}}.warning{{border-left:4px solid #ffd166;padding:.8rem;background:#2a261a}}.focus{{border-left:4px solid #50d890;padding:.8rem;background:#152a22;font-size:1.1rem}}.status{{color:#ffd166;font-size:1.2rem}}h3{{margin-bottom:.25rem}}</style></head>
<body><main><h1>Vocal-event retention review</h1><section class="panel"><p><b>{_html(seed["question"])}</b></p><p class="focus"><b>Listen for this exact event:</b> {_html(seed["focus"])}</p><p>First hear the mixed source. Then switch between every anonymous separation from the same playback position. Rate each candidate independently; more than one may be useful.</p><p class="warning">Candidates are sample-RMS matched. The mixed source is not. Judge whether the named vocal event remains, plus unwanted music bleed and metallic, watery, buzzy or broken artefacts. Do not open the answer key before exporting.</p></section><p id="status" class="status">Reviewed 0 of {seed["summary"]["candidate_count"]} candidates</p><section id="root" class="panel"></section><button id="mark">Mark complete</button><button id="export">Export reviewed JSON</button>
<script>
const review={payload},u=review.unit,root=document.getElementById('root'),slots=u.candidate_slots;let current=null,playhead=0;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));const letter=s=>s.slice(-1).toUpperCase();const options=(values,labels)=>`<option value="">Choose…</option>${{values.map(v=>`<option value="${{v}}">${{labels[v]||v}}</option>`).join('')}}`;const retention=['substantially_complete','partially_complete','little_or_none','cannot_tell'],severity=['low','noticeable','severe','cannot_tell'],useful=['yes','no','cannot_tell'],labels={{substantially_complete:'Substantially complete',partially_complete:'Partially complete',little_or_none:'Little or none',cannot_tell:'Cannot tell',low:'Low',noticeable:'Noticeable',severe:'Severe',yes:'Yes',no:'No'}};
const players=[['source','Mixed source'],...slots.map(s=>[s,`Candidate ${{letter(s)}}`])];root.innerHTML=`<div class="players">${{players.map(([key,label])=>{{const rec=key==='source'?u.source:u.candidates[key];return `<div><b>${{label}}</b><audio id="audio-${{key}}" controls loop preload="metadata" src="${{esc(rec.audio)}}"></audio><label><input type="checkbox" data-heard="${{key}}"> I heard ${{label}}</label><button type="button" data-play="audio-${{key}}">Play from same point</button></div>`}}).join('')}}</div><div class="ratings">${{slots.map(slot=>`<section><h3>Candidate ${{letter(slot)}}</h3><label>Named vocal event retained<select data-slot="${{slot}}" data-field="focus_retention">${{options(retention,labels)}}</select></label><label>Non-vocal bleed<select data-slot="${{slot}}" data-field="non_vocal_bleed">${{options(severity,labels)}}</select></label><label>Distracting artefacts<select data-slot="${{slot}}" data-field="artefacts">${{options(severity,labels)}}</select></label><label>Useful for this exact focus<select data-slot="${{slot}}" data-field="useful_for_focus">${{options(useful,labels)}}</select></label></section>`).join('')}}</div><label>Optional private note<textarea></textarea></label>`;
document.querySelectorAll('audio').forEach(a=>{{a.onplay=()=>{{if(current&&current!==a)current.pause();current=a;a.currentTime=Math.min(playhead,Math.max(0,(a.duration||0)-.01))}};a.ontimeupdate=()=>{{if(current===a)playhead=a.currentTime}}}});document.querySelectorAll('[data-play]').forEach(b=>b.onclick=()=>{{const a=document.getElementById(b.dataset.play);document.querySelectorAll('audio').forEach(x=>x.pause());a.currentTime=Math.min(playhead,Math.max(0,(a.duration||0)-.01));current=a;a.play()}});
function sync(){{for(const key of ['source',...slots])u.heard[key]=root.querySelector(`[data-heard="${{key}}"]`).checked;for(const slot of slots)for(const field of ['focus_retention','non_vocal_bleed','artefacts','useful_for_focus'])u.ratings[slot][field]=root.querySelector(`[data-slot="${{slot}}"][data-field="${{field}}"]`).value||null;u.notes=root.querySelector('textarea').value;const done=slots.filter(slot=>u.heard[slot]&&Object.values(u.ratings[slot]).every(Boolean)).length;review.summary.reviewed_candidate_count=done;if(review.status==='reviewed'&&(!u.heard.source||done!==slots.length))review.status='unreviewed';document.getElementById('status').textContent=`Reviewed ${{done}} of ${{slots.length}} candidates`;return u.heard.source&&done===slots.length}}root.onchange=sync;root.oninput=sync;
document.getElementById('mark').onclick=()=>{{if(!sync()){{alert('Hear the mixed source and every candidate, then complete every candidate rating.');return}}review.status='reviewed';document.getElementById('status').textContent=`Review complete · ${{slots.length}} of ${{slots.length}} candidates`}};
document.getElementById('export').onclick=()=>{{sync();if(review.status!=='reviewed'){{alert('Mark the complete review first.');return}}const blob=new Blob([JSON.stringify(review,null,2)+'\\n'],{{type:'application/json'}}),link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='separated-vocal-focus.reviewed.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000)}};
</script></main></body></html>"""


__all__ = [
    "ANSWER_KEY_SCHEMA",
    "AUDIO_MANIFEST_SCHEMA",
    "POLICY_ID",
    "RESULT_SCHEMA",
    "REVIEW_SCHEMA",
    "VocalFocusInput",
    "_create_private_separated_vocal_focus_review",
    "_resolve_private_separated_vocal_focus_review",
]
