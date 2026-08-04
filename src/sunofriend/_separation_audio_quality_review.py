"""Blind, source-bound audio-quality review for private vocal separation.

The package compares one Kim Vocal 2 output with one broad provider-vocal
control for each authorised excerpt.  Candidates are independently rated for
vocal retention, non-vocal bleed and distracting artefacts.  The result is
owner-only listening evidence, not score truth, selection or publication.
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
import soundfile

from ._separation_authorised_excerpt import (
    AUTHORISED_EXCERPT_SCHEMA,
    _document_sha256 as _excerpt_document_sha256,
)
from ._separation_authorised_midi_comparison import (
    _artifact_path,
    _document_sha256,
    _regular_json,
    _sha256,
)
from ._separation_authorised_role_mapping import (
    AUTHORISED_ROLE_MAPPING_SCHEMA,
    _document_sha256 as _mapping_document_sha256,
)
from ._separation_cross_song_evidence_index import _ID_PATTERN
from ._separation_melroformer_midi_evaluation import (
    SCHEMA as MELROFORMER_MIDI_SCHEMA,
)
from ._separation_melroformer_precision_review import (
    _browser_json_equal,
    _level_match,
    _write_audio,
    _write_json,
    _write_json_atomic,
)


REVIEW_SCHEMA = "sunofriend.private-separated-audio-quality-review.v1"
ANSWER_KEY_SCHEMA = "sunofriend.private-separated-audio-quality-answer-key.v1"
RESULT_SCHEMA = "sunofriend.private-separated-audio-quality-result.v2"
AUDIO_MANIFEST_SCHEMA = "sunofriend.private-separated-audio-quality-manifest.v1"
POLICY_ID = "private-separated-vocal-audio-quality-v1"
SAMPLE_RATE = 44_100
_MAXIMUM_REPORT_BYTES = 4 * 1024 * 1024
_MAXIMUM_CASES = 16
_PREFERENCES = frozenset(
    ("candidate_a", "candidate_b", "equivalent", "neither", "cannot_tell")
)
_VOCAL_RETENTION = frozenset(
    ("substantially_complete", "partially_complete", "little_or_none", "cannot_tell")
)
_PROBLEM_SEVERITY = frozenset(("low", "noticeable", "severe", "cannot_tell"))


@dataclass(frozen=True)
class AudioQualityInput:
    """One authorised mixed source, Kim candidate and provider control."""

    track_id: str
    authorised_excerpt: Path
    candidate_midi_evaluation: Path
    role_mapping: Path
    provider_id: str = "moises"


@dataclass(frozen=True)
class _LoadedJson:
    path: Path
    file_sha256: str
    document: dict[str, Any]


@dataclass(frozen=True)
class _LoadedCase:
    track_id: str
    source_track_id: str
    provider_id: str
    excerpt: _LoadedJson
    candidate: _LoadedJson
    mapping: _LoadedJson
    source_path: Path
    candidate_path: Path
    provider_path: Path
    source_audio: np.ndarray
    candidate_audio: np.ndarray
    provider_audio: np.ndarray
    start_seconds: float
    end_seconds: float


def _create_private_separated_audio_quality_review(
    cases: Sequence[AudioQualityInput],
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Create one fresh blinded multi-song vocal-audio review package."""

    if not 2 <= len(cases) <= _MAXIMUM_CASES:
        raise ValueError("separated-audio quality review requires 2-16 cases")
    loaded = tuple(_load_case(case) for case in cases)
    if len({case.track_id for case in loaded}) != len(loaded):
        raise ValueError("separated-audio review track IDs must be unique")
    ordered = tuple(sorted(loaded, key=lambda case: case.track_id))

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"separated-audio review already exists: {destination}")
    package_contract = {
        "policy_id": POLICY_ID,
        "cases": [_case_contract(case) for case in ordered],
    }
    package_commitment = _document_hash(package_contract)
    blind_nonce = secrets.token_bytes(32)
    nonce_commitment = hashlib.sha256(
        blind_nonce + bytes.fromhex(package_commitment)
    ).hexdigest()

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.mkdir(mode=0o700)
        audio_root = destination / "audio"
        audio_root.mkdir(mode=0o700)
        units: list[dict[str, Any]] = []
        answer_units: list[dict[str, Any]] = []
        manifest_rows: list[dict[str, Any]] = []
        for index, case in enumerate(ordered, start=1):
            unit_id = f"{index:02d}-{case.track_id}"
            unit_root = audio_root / unit_id
            unit_root.mkdir(mode=0o700)
            mapping = _blind_mapping(blind_nonce, package_commitment, case.track_id)
            inputs = {
                "input_1": np.asarray(case.candidate_audio, dtype=np.float64),
                "input_2": np.asarray(case.provider_audio, dtype=np.float64),
            }
            matched, level_evidence = _level_match(inputs)

            source_path = unit_root / "source-reference.wav"
            _write_audio(source_path, case.source_audio, subtype="PCM_24")
            source_record = _audio_record(source_path, destination)
            anonymous: dict[str, dict[str, Any]] = {}
            for slot in ("candidate_a", "candidate_b"):
                path = unit_root / f"{slot}.wav"
                _write_audio(path, matched[mapping[slot]], subtype="PCM_24")
                anonymous[slot] = _audio_record(path, destination)
            mismatch = abs(
                anonymous["candidate_a"]["rms_dbfs"]
                - anonymous["candidate_b"]["rms_dbfs"]
            )
            if mismatch > 0.05:
                raise RuntimeError("separated-audio PCM24 candidate levels differ")
            level_evidence["final_pcm24"] = {
                "candidate_a_rms_dbfs": anonymous["candidate_a"]["rms_dbfs"],
                "candidate_b_rms_dbfs": anonymous["candidate_b"]["rms_dbfs"],
                "mismatch_db": round(mismatch, 6),
                "within_tolerance": True,
            }

            unit = {
                "unit_id": unit_id,
                "track_id": case.track_id,
                "source_track_id": case.source_track_id,
                "source_seconds": [case.start_seconds, case.end_seconds],
                "duration_seconds": case.end_seconds - case.start_seconds,
                "sample_rate": SAMPLE_RATE,
                "frame_count": len(case.source_audio),
                "source": source_record,
                "candidate_a": anonymous["candidate_a"],
                "candidate_b": anonymous["candidate_b"],
                "heard": {
                    "source": False,
                    "candidate_a": False,
                    "candidate_b": False,
                },
                "ratings": {
                    "candidate_a": _empty_ratings(),
                    "candidate_b": _empty_ratings(),
                },
                "preference": None,
                "notes": "",
            }
            units.append(unit)
            answer_units.append(
                {
                    "unit_id": unit_id,
                    "track_id": case.track_id,
                    "mapping": {
                        slot: {
                            "identity": identity,
                            "method": _method_label(identity, case.provider_id),
                        }
                        for slot, identity in mapping.items()
                    },
                    "level_match": level_evidence,
                    "immutable_review_unit_sha256": _document_hash(
                        _immutable_unit(unit)
                    ),
                }
            )
            manifest_rows.extend(
                (
                    _manifest_row(source_record, unit_id, "mixed-source-reference"),
                    _manifest_row(
                        anonymous["candidate_a"], unit_id, "blinded-candidate-a"
                    ),
                    _manifest_row(
                        anonymous["candidate_b"], unit_id, "blinded-candidate-b"
                    ),
                )
            )

        manifest = {
            "schema": AUDIO_MANIFEST_SCHEMA,
            "package_commitment": package_commitment,
            "file_count": len(manifest_rows),
            "files": manifest_rows,
        }
        manifest_path = destination / "separated_audio_quality_manifest.json"
        _write_json(manifest_path, manifest)
        manifest_sha256 = _sha256(manifest_path)

        answer_key = {
            "schema": ANSWER_KEY_SCHEMA,
            "status": "complete",
            "policy_id": POLICY_ID,
            "package_commitment": package_commitment,
            "blind_nonce_hex": blind_nonce.hex(),
            "blind_nonce_commitment": nonce_commitment,
            "package_contract": package_contract,
            "units": answer_units,
        }
        answer_path = destination / "separated_audio_quality_answer_key.json"
        _write_json(answer_path, answer_key)
        answer_sha256 = _sha256(answer_path)

        seed = {
            "schema": REVIEW_SCHEMA,
            "operation": "private-separated-audio-quality-review",
            "status": "unreviewed",
            "evidence_scope": "private_development_only",
            "blind": True,
            "review_required": True,
            "policy_id": POLICY_ID,
            "package_commitment": package_commitment,
            "question": (
                "How much vocal is retained, how much non-vocal bleed remains, "
                "and how distracting are the artefacts in each separation?"
            ),
            "policy": {
                "preference_choices": sorted(_PREFERENCES),
                "vocal_retention_choices": sorted(_VOCAL_RETENTION),
                "bleed_choices": sorted(_PROBLEM_SEVERITY),
                "artefact_choices": sorted(_PROBLEM_SEVERITY),
                "ratings_are_independent_per_candidate": True,
                "preference_is_separate_from_ratings": True,
                "provider_control_is_not_ground_truth": True,
                "source_reference_is_not_a_candidate": True,
                "source_reference_level_matched": False,
                "candidate_level_method": (
                    "pairwise-fixed-window-rms-attenuation-plus-common-peak-guard-v1"
                ),
                "level_claim": "fixed-window sample RMS, not perceived loudness",
                "time_shift_seconds": 0.0,
                "time_stretch_ratio": 1.0,
                "limiter_used": False,
                "compression_used": False,
                "equalisation_used": False,
                "automatic_selection": False,
                "automatic_promotion": False,
                "production_eligible": False,
            },
            "geometry": {
                "sample_rate": SAMPLE_RATE,
                "channels": 2,
                "case_count": len(units),
                "alignment": (
                    "each unit uses one exact authorised excerpt at recorded zero"
                ),
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
                "policy": "secret-random-per-unit-v1",
                "nonce_commitment": nonce_commitment,
            },
            "summary": {"unit_count": len(units), "reviewed_unit_count": 0},
            "units": units,
            "permissions": _zero_permissions(),
            "effects": _zero_effects(),
            "warnings": [
                "Do not open the separate answer key before exporting the completed review.",
                "A and B are sample-RMS matched; the mixed source is not level matched.",
                "The provider candidate is a comparison control, not score truth.",
                "This review cannot select, promote, activate or publish a separator.",
            ],
        }
        seed_path = destination / "separated_audio_quality_review.json"
        _write_json(seed_path, seed)
        html_path = destination / "separated_audio_quality_review.html"
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
        "html": str(destination / "separated_audio_quality_review.html"),
        "seed": str(destination / "separated_audio_quality_review.json"),
        "answer_key": str(answer_path),
        "answer_key_sha256": answer_sha256,
        "audio_manifest": str(manifest_path),
        "audio_manifest_sha256": manifest_sha256,
        "permissions": _zero_permissions(),
        "effects": _zero_effects(),
    }


def _resolve_private_separated_audio_quality_review(
    review_path: str | Path,
    *,
    package_dir: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Verify one completed browser export and reveal identities safely."""

    package = Path(package_dir).expanduser().resolve(strict=True)
    review_file = _regular_json(review_path, "reviewed audio-quality export")
    output = Path(out).expanduser().absolute()
    if os.path.lexists(output):
        raise FileExistsError(f"audio-quality result already exists: {output}")
    seed_path = package / "separated_audio_quality_review.json"
    seed = _read_json(seed_path)
    review = _read_json(review_file)
    if seed.get("schema") != REVIEW_SCHEMA or seed.get("status") != "unreviewed":
        raise ValueError("separated-audio review package seed is invalid")
    if not _browser_json_equal(
        _immutable_review_document(review), _immutable_review_document(seed)
    ):
        raise ValueError("separated-audio review export changed immutable evidence")
    units = review.get("units")
    if (
        review.get("status") != "reviewed"
        or not isinstance(units, list)
        or len(units) != len(seed["units"])
        or (review.get("summary") or {}).get("reviewed_unit_count") != len(units)
    ):
        raise ValueError("separated-audio quality review is incomplete")
    for unit in units:
        _validate_completed_unit(unit)
    if review.get("permissions") != _zero_permissions():
        raise ValueError("separated-audio review declares a permission")
    if review.get("effects") != _zero_effects():
        raise ValueError("separated-audio review declares an automatic effect")
    _verify_review_audio(review, package)

    answer_record = seed.get("answer_key") or {}
    answer_path = package / str(answer_record.get("path", ""))
    if not answer_path.is_file() or _sha256(answer_path) != answer_record.get(
        "sha256"
    ):
        raise ValueError("separated-audio answer key changed or is missing")
    answer = _read_json(answer_path)
    _verify_answer_key(answer, seed)
    answer_by_unit = {unit["unit_id"]: unit for unit in answer["units"]}
    contract_by_track = {
        case["track_id"]: case for case in answer["package_contract"]["cases"]
    }
    resolved_units = []
    for unit in units:
        answer_unit = answer_by_unit[str(unit["unit_id"])]
        mapping = answer_unit["mapping"]
        source_binding = contract_by_track[str(unit["track_id"])]
        ratings = {
            mapping[slot]["method"]: dict(unit["ratings"][slot])
            for slot in ("candidate_a", "candidate_b")
        }
        preference = str(unit["preference"])
        resolved_preference = (
            mapping[preference]["method"]
            if preference in ("candidate_a", "candidate_b")
            else preference
        )
        resolved_units.append(
            {
                "unit_id": unit["unit_id"],
                "track_id": unit["track_id"],
                "source_track_id": unit["source_track_id"],
                "source_seconds": list(unit["source_seconds"]),
                "source_binding": deepcopy(source_binding),
                "candidate_a_method": mapping["candidate_a"]["method"],
                "candidate_b_method": mapping["candidate_b"]["method"],
                "ratings_by_method": ratings,
                "preference": preference,
                "resolved_preference": resolved_preference,
                "notes": unit["notes"],
            }
        )
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
        "unit_count": len(resolved_units),
        "units": resolved_units,
        "interpretation": {
            "ratings_are_human_listening_evidence": True,
            "provider_control_is_ground_truth": False,
            "preference_is_accuracy": False,
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


def _load_case(source: AudioQualityInput) -> _LoadedCase:
    track_id = _safe_id(source.track_id, "track ID")
    provider_id = _safe_id(source.provider_id, "provider ID")
    excerpt = _load_json(source.authorised_excerpt, "authorised excerpt")
    candidate = _load_json(source.candidate_midi_evaluation, "candidate evaluation")
    mapping = _load_json(source.role_mapping, "role mapping")
    _validate_excerpt(excerpt)
    _validate_candidate(candidate, excerpt)
    source_track_id, start, end = _validate_mapping(
        mapping, excerpt, provider_id=provider_id
    )

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
    candidate_path = _regular_audio(
        candidate.document["candidate"]["primary"]["independent_evaluation"][
            "stem_path"
        ],
        "Kim vocal candidate",
    )
    if (
        candidate_path.stat().st_size != worker.get("vocal_pcm24_bytes")
        or _sha256(candidate_path) != worker.get("vocal_pcm24_sha256")
    ):
        raise ValueError("Kim vocal candidate identity changed")
    provider_artifact = mapping.document["groups"][provider_id]["vocals"]["artifact"]
    provider_path = _artifact_path(
        mapping.path.parent, provider_artifact, "provider broad-vocal audio"
    )

    source_audio = _read_exact_audio(source_path, end - start, "source")
    candidate_audio = _read_exact_audio(candidate_path, end - start, "Kim candidate")
    provider_audio = _read_exact_audio(provider_path, end - start, "provider control")
    return _LoadedCase(
        track_id=track_id,
        source_track_id=source_track_id,
        provider_id=provider_id,
        excerpt=excerpt,
        candidate=candidate,
        mapping=mapping,
        source_path=source_path,
        candidate_path=candidate_path,
        provider_path=provider_path,
        source_audio=source_audio,
        candidate_audio=candidate_audio,
        provider_audio=provider_audio,
        start_seconds=start,
        end_seconds=end,
    )


def _validate_excerpt(excerpt: _LoadedJson) -> None:
    document = excerpt.document
    geometry = (document.get("excerpt") or {}).get("geometry")
    if (
        document.get("schema") != AUTHORISED_EXCERPT_SCHEMA
        or document.get("status") != "complete_review_required"
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != _excerpt_document_sha256(document)
        or not isinstance(geometry, Mapping)
        or geometry.get("channels") != 2
    ):
        raise ValueError("authorised excerpt contract differs")
    _require_all_false(document.get("permissions"), "excerpt permissions")


def _validate_candidate(candidate: _LoadedJson, excerpt: _LoadedJson) -> None:
    document = candidate.document
    worker = document.get("worker")
    primary = (document.get("candidate") or {}).get("primary")
    effects = document.get("effects")
    if (
        document.get("schema") != MELROFORMER_MIDI_SCHEMA
        or document.get("status") != "complete_observation_not_acceptance"
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != _document_sha256(document)
        or not isinstance(worker, Mapping)
        or worker.get("candidate_id") != "mlx-melroformer-kim-vocal-2"
        or worker.get("authorisation_report_sha256") != excerpt.file_sha256
        or worker.get("pcm24_quarantine_bound_to_model_worker") is not True
        or not isinstance(primary, Mapping)
        or not isinstance(primary.get("independent_evaluation"), Mapping)
        or not isinstance(effects, Mapping)
        or effects.get("source_audio_mutated") is not False
        or effects.get("source_graph_mutated") is not False
        or effects.get("worker_rerun") is not False
    ):
        raise ValueError("Kim candidate evaluation contract differs")
    _require_all_false(document.get("permissions"), "candidate permissions")


def _validate_mapping(
    mapping: _LoadedJson,
    excerpt: _LoadedJson,
    *,
    provider_id: str,
) -> tuple[str, float, float]:
    document = mapping.document
    source = document.get("source_excerpt")
    groups = document.get("groups")
    geometry = excerpt.document.get("excerpt")
    if (
        document.get("schema") != AUTHORISED_ROLE_MAPPING_SCHEMA
        or document.get("status") != "complete_review_required"
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != _mapping_document_sha256(document)
        or not isinstance(source, Mapping)
        or source.get("report_sha256") != excerpt.file_sha256
        or source.get("document_sha256")
        != excerpt.document.get("document_sha256")
        or not isinstance(geometry, Mapping)
        or not isinstance(groups, Mapping)
        or not isinstance(groups.get(provider_id), Mapping)
        or not isinstance(groups[provider_id].get("vocals"), Mapping)
        or not isinstance(groups[provider_id]["vocals"].get("artifact"), Mapping)
    ):
        raise ValueError("provider role-mapping contract differs")
    _require_all_false(document.get("permissions"), "mapping permissions")
    start = _finite_number(source.get("start_seconds"), "mapping start")
    end = _finite_number(source.get("end_seconds"), "mapping end")
    if (
        start != _finite_number(geometry.get("start_seconds"), "excerpt start")
        or end != _finite_number(geometry.get("end_seconds"), "excerpt end")
        or start < 0.0
        or end <= start
        or end - start > 15.0
    ):
        raise ValueError("provider role-mapping window differs")
    return _safe_id(source.get("track_id"), "source track ID"), start, end


def _case_contract(case: _LoadedCase) -> dict[str, Any]:
    return {
        "track_id": case.track_id,
        "source_track_id": case.source_track_id,
        "provider_id": case.provider_id,
        "start_seconds": case.start_seconds,
        "end_seconds": case.end_seconds,
        "authorised_excerpt_sha256": case.excerpt.file_sha256,
        "authorised_excerpt_document_sha256": case.excerpt.document[
            "document_sha256"
        ],
        "candidate_evaluation_sha256": case.candidate.file_sha256,
        "candidate_evaluation_document_sha256": case.candidate.document[
            "document_sha256"
        ],
        "role_mapping_sha256": case.mapping.file_sha256,
        "role_mapping_document_sha256": case.mapping.document["document_sha256"],
        "source_audio_sha256": _sha256(case.source_path),
        "candidate_audio_sha256": _sha256(case.candidate_path),
        "provider_audio_sha256": _sha256(case.provider_path),
        "sample_rate": SAMPLE_RATE,
        "channels": 2,
        "frames": len(case.source_audio),
    }


def _validate_completed_unit(unit: Any) -> None:
    if not isinstance(unit, Mapping):
        raise ValueError("separated-audio review unit differs")
    heard = unit.get("heard")
    ratings = unit.get("ratings")
    if (
        not isinstance(heard, Mapping)
        or any(
            heard.get(key) is not True
            for key in ("source", "candidate_a", "candidate_b")
        )
        or unit.get("preference") not in _PREFERENCES
        or not isinstance(ratings, Mapping)
        or set(ratings) != {"candidate_a", "candidate_b"}
        or not isinstance(unit.get("notes"), str)
        or len(unit["notes"]) > 4_000
    ):
        raise ValueError("separated-audio review unit is incomplete")
    for slot in ("candidate_a", "candidate_b"):
        value = ratings[slot]
        if (
            not isinstance(value, Mapping)
            or set(value) != {"vocal_retention", "non_vocal_bleed", "artefacts"}
            or value.get("vocal_retention") not in _VOCAL_RETENTION
            or value.get("non_vocal_bleed") not in _PROBLEM_SEVERITY
            or value.get("artefacts") not in _PROBLEM_SEVERITY
        ):
            raise ValueError("separated-audio candidate ratings are incomplete")


def _verify_review_audio(review: Mapping[str, Any], package: Path) -> None:
    evidence = review.get("review_evidence") or {}
    manifest_path = package / str(evidence.get("manifest", ""))
    if not manifest_path.is_file() or _sha256(manifest_path) != evidence.get(
        "manifest_sha256"
    ):
        raise ValueError("separated-audio manifest changed")
    manifest = _read_json(manifest_path)
    rows = {str(row.get("path")): row for row in manifest.get("files", [])}
    expected_count = len(review["units"]) * 3
    if (
        manifest.get("schema") != AUDIO_MANIFEST_SCHEMA
        or manifest.get("package_commitment") != review.get("package_commitment")
        or manifest.get("file_count") != expected_count
        or len(rows) != expected_count
    ):
        raise ValueError("separated-audio manifest is incompatible")
    referenced = set()
    for unit in review["units"]:
        for name in ("source", "candidate_a", "candidate_b"):
            record = unit[name]
            relative = str(record.get("audio", ""))
            unresolved = package / relative
            try:
                details = unresolved.lstat()
            except OSError as error:
                raise ValueError(
                    "separated-audio listening evidence changed"
                ) from error
            path = unresolved.resolve(strict=True)
            if (
                package not in path.parents
                or stat.S_ISLNK(details.st_mode)
                or not stat.S_ISREG(details.st_mode)
                or path.stat().st_size != record.get("bytes")
                or _sha256(path) != record.get("sha256")
            ):
                raise ValueError("separated-audio listening evidence changed")
            row = rows.get(relative) or {}
            if row.get("sha256") != record.get("sha256"):
                raise ValueError("separated-audio manifest differs")
            referenced.add(relative)
    if referenced != set(rows):
        raise ValueError("separated-audio references differ")


def _verify_answer_key(answer: Mapping[str, Any], seed: Mapping[str, Any]) -> None:
    package_contract = answer.get("package_contract")
    if (
        answer.get("schema") != ANSWER_KEY_SCHEMA
        or answer.get("status") != "complete"
        or answer.get("policy_id") != POLICY_ID
        or answer.get("package_commitment") != seed.get("package_commitment")
        or not isinstance(package_contract, Mapping)
        or _document_hash(package_contract)
        != seed.get("package_commitment")
    ):
        raise ValueError("separated-audio answer key is incompatible")
    contract_cases = package_contract.get("cases")
    if (
        package_contract.get("policy_id") != POLICY_ID
        or not isinstance(contract_cases, list)
        or len(contract_cases) != len(seed.get("units", []))
        or not all(isinstance(case, Mapping) for case in contract_cases)
    ):
        raise ValueError("separated-audio package contract differs")
    contract_by_track = {
        case.get("track_id"): case for case in contract_cases
    }
    if (
        len(contract_by_track) != len(contract_cases)
        or set(contract_by_track)
        != {unit.get("track_id") for unit in seed.get("units", [])}
    ):
        raise ValueError("separated-audio package contract differs")
    for seed_unit in seed.get("units", []):
        contract = contract_by_track.get(seed_unit.get("track_id")) or {}
        if (
            contract.get("source_track_id") != seed_unit.get("source_track_id")
            or [contract.get("start_seconds"), contract.get("end_seconds")]
            != seed_unit.get("source_seconds")
            or contract.get("sample_rate") != seed_unit.get("sample_rate")
            or contract.get("channels") != 2
            or contract.get("frames") != seed_unit.get("frame_count")
        ):
            raise ValueError("separated-audio package contract differs")
    try:
        nonce = bytes.fromhex(str(answer.get("blind_nonce_hex", "")))
        commitment = str(seed.get("package_commitment", ""))
        commitment_bytes = bytes.fromhex(commitment)
    except ValueError as error:
        raise ValueError("separated-audio blind nonce is invalid") from error
    if len(nonce) != 32 or len(commitment_bytes) != 32:
        raise ValueError("separated-audio blind nonce is invalid")
    nonce_commitment = hashlib.sha256(nonce + commitment_bytes).hexdigest()
    if (
        nonce_commitment != answer.get("blind_nonce_commitment")
        or nonce_commitment
        != (seed.get("blind_assignment") or {}).get("nonce_commitment")
    ):
        raise ValueError("separated-audio blind commitment differs")
    seed_units = {unit["unit_id"]: unit for unit in seed["units"]}
    answer_units = answer.get("units")
    if not isinstance(answer_units, list) or len(answer_units) != len(seed_units):
        raise ValueError("separated-audio answer units differ")
    answer_ids = [
        unit.get("unit_id") if isinstance(unit, Mapping) else None
        for unit in answer_units
    ]
    if len(set(answer_ids)) != len(answer_ids):
        raise ValueError("separated-audio answer units differ")
    for unit in answer_units:
        if not isinstance(unit, Mapping) or unit.get("unit_id") not in seed_units:
            raise ValueError("separated-audio answer unit differs")
        seed_unit = seed_units[str(unit["unit_id"])]
        expected = _blind_mapping(nonce, commitment, str(seed_unit["track_id"]))
        mapping = unit.get("mapping") or {}
        if (
            unit.get("track_id") != seed_unit.get("track_id")
            or unit.get("immutable_review_unit_sha256")
            != _document_hash(_immutable_unit(seed_unit))
            or any(
                (mapping.get(slot) or {}).get("identity") != identity
                for slot, identity in expected.items()
            )
        ):
            raise ValueError("separated-audio blind assignment differs")


def _review_html(seed: Mapping[str, Any]) -> str:
    payload = json.dumps(seed, sort_keys=True).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend separated-audio quality review</title><style>
body{{font-family:system-ui,sans-serif;background:#101820;color:#edf4f8;margin:0;padding:2rem;line-height:1.5}}main{{max-width:1120px;margin:auto}}.panel{{background:#192631;border:1px solid #405565;border-radius:16px;padding:1.3rem;margin:1rem 0}}.players{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem}}audio{{width:100%}}label{{display:block;margin:.45rem 0}}button{{font-size:1rem;padding:.7rem 1rem;margin:.3rem;border:0;border-radius:9px;background:#2d638c;color:white}}select,textarea{{width:100%;box-sizing:border-box;background:#0e1720;color:white;border:1px solid #60798c;border-radius:8px;padding:.5rem}}textarea{{min-height:4rem}}.warning{{border-left:4px solid #ffd166;padding:.8rem;background:#2a261a}}.status{{color:#ffd166;font-size:1.2rem}}.ratings{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem}}h3{{margin-bottom:.25rem}}</style></head>
<body><main><h1>Separated-audio quality review</h1><section class="panel"><p><b>{_html(seed["question"])}</b></p><p>Each card contains the original mixed excerpt plus two anonymous broad-vocal separations. Rate A and B independently. Then record a separate overall preference.</p><p class="warning">Judge the vocal retained, unwanted music bleed and metallic, watery, buzzy or broken artefacts. A and B are sample-RMS matched. The mixed source is not level matched. Do not open the answer key before exporting.</p></section><p id="status" class="status">Reviewed 0 of {len(seed["units"])}</p><div id="root"></div><button id="mark">Mark complete</button><button id="export">Export reviewed JSON</button>
<script>
const review={payload},root=document.getElementById('root');let current=null,playhead=0;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const options=(values,label)=>`<option value="">Choose…</option>${{values.map(v=>`<option value="${{v}}">${{label[v]||v}}</option>`).join('')}}`;const retain=['substantially_complete','partially_complete','little_or_none','cannot_tell'],severity=['low','noticeable','severe','cannot_tell'],pref=['candidate_a','candidate_b','equivalent','neither','cannot_tell'];const labels={{substantially_complete:'Substantially complete vocal',partially_complete:'Partially complete vocal',little_or_none:'Little or no vocal',cannot_tell:'Cannot tell',low:'Low',noticeable:'Noticeable',severe:'Severe',candidate_a:'Candidate A',candidate_b:'Candidate B',equivalent:'Equivalent',neither:'Neither is useful'}};
review.units.forEach((u,i)=>{{const card=document.createElement('section');card.className='panel';card.dataset.i=i;card.innerHTML=`<h2>Excerpt ${{i+1}} · ${{u.source_seconds[0].toFixed(2)}}–${{u.source_seconds[1].toFixed(2)}} source seconds</h2><div class="players">${{[['source','Mixed source'],['candidate_a','Candidate A'],['candidate_b','Candidate B']].map(([key,label])=>`<div><b>${{label}}</b><audio id="audio-${{i}}-${{key}}" controls loop preload="metadata" src="${{esc(u[key].audio)}}"></audio><label><input type="checkbox" data-heard="${{key}}"> I heard ${{label}}</label></div>`).join('')}}</div><div>${{[['source','source'],['candidate_a','A'],['candidate_b','B']].map(([key,label])=>`<button type="button" data-unit="${{i}}" data-play="audio-${{i}}-${{key}}">Play ${{label}} from same point</button>`).join('')}}</div><div class="ratings">${{['candidate_a','candidate_b'].map((slot,j)=>`<div><h3>Candidate ${{j?'B':'A'}}</h3><label>Vocal retained<select data-slot="${{slot}}" data-field="vocal_retention">${{options(retain,labels)}}</select></label><label>Non-vocal bleed<select data-slot="${{slot}}" data-field="non_vocal_bleed">${{options(severity,labels)}}</select></label><label>Distracting artefacts<select data-slot="${{slot}}" data-field="artefacts">${{options(severity,labels)}}</select></label></div>`).join('')}}</div><label>Separate overall preference<select data-preference>${{options(pref,labels)}}</select></label><label>Optional private note<textarea></textarea></label>`;root.appendChild(card)}});
document.querySelectorAll('audio').forEach(a=>{{a.onplay=()=>{{if(current&&current!==a)current.pause();current=a;a.currentTime=Math.min(playhead,Math.max(0,(a.duration||0)-.01))}};a.ontimeupdate=()=>{{if(current===a)playhead=a.currentTime}}}});document.querySelectorAll('[data-play]').forEach(b=>b.onclick=()=>{{const a=document.getElementById(b.dataset.play);document.querySelectorAll('audio').forEach(x=>x.pause());a.currentTime=Math.min(playhead,Math.max(0,(a.duration||0)-.01));current=a;a.play()}});
function sync(){{let done=0;document.querySelectorAll('section[data-i]').forEach((card,i)=>{{const u=review.units[i];for(const key of ['source','candidate_a','candidate_b'])u.heard[key]=card.querySelector(`[data-heard="${{key}}"]`).checked;for(const slot of ['candidate_a','candidate_b'])for(const field of ['vocal_retention','non_vocal_bleed','artefacts'])u.ratings[slot][field]=card.querySelector(`[data-slot="${{slot}}"][data-field="${{field}}"]`).value||null;u.preference=card.querySelector('[data-preference]').value||null;u.notes=card.querySelector('textarea').value;if(Object.values(u.heard).every(Boolean)&&u.preference&&Object.values(u.ratings).every(r=>Object.values(r).every(Boolean)))done++}});review.summary.reviewed_unit_count=done;if(review.status==='reviewed'&&done!==review.units.length)review.status='unreviewed';document.getElementById('status').textContent=`Reviewed ${{done}} of ${{review.units.length}}`;return done}}root.onchange=sync;root.oninput=sync;
document.getElementById('mark').onclick=()=>{{if(sync()!==review.units.length){{alert('Hear all three audio files and complete every rating and preference for both excerpts.');return}}review.status='reviewed';document.getElementById('status').textContent=`Review complete · ${{review.units.length}} of ${{review.units.length}}`;}};
document.getElementById('export').onclick=()=>{{sync();if(review.status!=='reviewed'){{alert('Mark the complete review first.');return}}const blob=new Blob([JSON.stringify(review,null,2)+'\\n'],{{type:'application/json'}}),link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='separated-audio-quality.reviewed.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000)}};
</script></main></body></html>"""


def _immutable_unit(unit: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(unit))
    for key in ("heard", "ratings", "preference", "notes"):
        result.pop(key, None)
    return result


def _immutable_review_document(document: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(document))
    result["status"] = "unreviewed"
    result["summary"]["reviewed_unit_count"] = 0
    for unit in result["units"]:
        unit["heard"] = {
            "source": False,
            "candidate_a": False,
            "candidate_b": False,
        }
        unit["ratings"] = {
            "candidate_a": _empty_ratings(),
            "candidate_b": _empty_ratings(),
        }
        unit["preference"] = None
        unit["notes"] = ""
    return result


def _empty_ratings() -> dict[str, None]:
    return {"vocal_retention": None, "non_vocal_bleed": None, "artefacts": None}


def _blind_mapping(nonce: bytes, commitment: str, track_id: str) -> dict[str, str]:
    selector = hashlib.sha256(
        nonce + bytes.fromhex(commitment) + track_id.encode("ascii")
    ).digest()[0]
    if selector % 2:
        return {"candidate_a": "input_2", "candidate_b": "input_1"}
    return {"candidate_a": "input_1", "candidate_b": "input_2"}


def _method_label(identity: str, provider_id: str) -> str:
    return {
        "input_1": "kim-vocal-2",
        "input_2": f"provider-{provider_id}-broad-vocals",
    }[identity]


def _read_exact_audio(path: Path, duration: float, label: str) -> np.ndarray:
    info = soundfile.info(path)
    expected_frames = round(duration * SAMPLE_RATE)
    if (
        info.samplerate != SAMPLE_RATE
        or info.channels != 2
        or info.frames != expected_frames
        or info.subtype != "PCM_24"
    ):
        raise ValueError(f"{label} audio geometry differs")
    values, rate = soundfile.read(path, dtype="float32", always_2d=True)
    if int(rate) != SAMPLE_RATE or not np.isfinite(values).all():
        raise ValueError(f"{label} audio is invalid")
    return np.ascontiguousarray(values, dtype=np.dtype("<f4"))


def _audio_record(path: Path, root: Path) -> dict[str, Any]:
    values, rate = soundfile.read(path, dtype="float64", always_2d=True)
    if int(rate) != SAMPLE_RATE or values.shape[1] != 2 or not np.isfinite(values).all():
        raise RuntimeError("separated-audio review geometry changed")
    rms = math.sqrt(float(np.mean(np.square(values))))
    peak = float(np.max(np.abs(values)))
    if path.name in {"candidate_a.wav", "candidate_b.wav"} and peak >= 0.9999:
        raise RuntimeError("separated-audio listening file is clipped")
    return {
        "audio": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "sample_rate": int(rate),
        "channels": int(values.shape[1]),
        "frames": int(len(values)),
        "rms_dbfs": round(_dbfs(rms), 6),
        "peak_dbfs": round(_dbfs(peak), 6),
    }


def _manifest_row(
    record: Mapping[str, Any], unit_id: str, purpose: str
) -> dict[str, Any]:
    return {
        "path": record["audio"],
        "sha256": record["sha256"],
        "bytes": record["bytes"],
        "unit_id": unit_id,
        "purpose": purpose,
    }


def _load_json(value: str | Path, label: str) -> _LoadedJson:
    path = _regular_json(value, label)
    if path.stat().st_size > _MAXIMUM_REPORT_BYTES:
        raise ValueError(f"{label} is too large")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object")
    return _LoadedJson(path=path, file_sha256=_sha256(path), document=document)


def _regular_audio(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} path is missing")
    path = Path(value).expanduser().absolute()
    try:
        details = path.lstat()
    except OSError as error:
        raise ValueError(f"{label} is missing") from error
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or details.st_size <= 44
        or path.suffix.lower() != ".wav"
    ):
        raise ValueError(f"{label} must be a non-empty regular WAV")
    return path


def _require_all_false(raw: Any, label: str) -> None:
    if (
        not isinstance(raw, Mapping)
        or not raw
        or any(value is not False for value in raw.values())
    ):
        raise ValueError(f"{label} differ")


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase ASCII token")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"expected JSON object: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path.name}")
    return value


def _document_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _dbfs(value: float) -> float:
    return 20.0 * math.log10(max(float(value), 1e-12))


def _make_private_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("separated-audio review contains a symbolic link")
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)


def _zero_permissions() -> dict[str, bool]:
    return {
        "accepted": False,
        "automatic_promotion": False,
        "automatic_selection": False,
        "production_eligible": False,
        "public_result": False,
        "simple_mode_available": False,
        "source_graph_activation": False,
        "studio_import_available": False,
    }


def _zero_effects() -> dict[str, bool]:
    return {
        "audio_created_or_mutated": False,
        "candidate_activated": False,
        "default_changed": False,
        "midi_created_or_mutated": False,
        "separator_selected": False,
        "source_graph_mutated": False,
    }


def _html(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


__all__ = [
    "ANSWER_KEY_SCHEMA",
    "AUDIO_MANIFEST_SCHEMA",
    "AudioQualityInput",
    "POLICY_ID",
    "RESULT_SCHEMA",
    "REVIEW_SCHEMA",
    "_create_private_separated_audio_quality_review",
    "_resolve_private_separated_audio_quality_review",
]
