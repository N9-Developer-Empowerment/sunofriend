"""Audio-evidence role grouping for one authorised separation excerpt.

Provider names propose groups; they never prove them.  This private tool
requires every non-excluded provider excerpt to belong to exactly one proposed
broad role, writes common-rate group auditions, and compares each provider
group with every local HTDemucs broad role.  It records rankings but does not
select, promote or activate a mapping.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_authorised_excerpt import (
    AUTHORISED_EXCERPT_SCHEMA,
    _document_sha256 as _source_document_sha256,
    _write_model_input,
)


AUTHORISED_ROLE_MAPPING_SCHEMA = "sunofriend.private-authorised-role-mapping.v1"
_REPORT_NAME = "authorised-role-mapping.json"
_ROLES = ("bass", "drums", "other", "vocals")
_SAMPLE_RATE = 44_100


def _map_authorised_excerpt_roles(
    excerpt_report_path: str | Path,
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Create review-only broad groups and cross-role audio evidence."""

    import numpy as np
    import soundfile

    source_report_path = _regular_json(excerpt_report_path, "excerpt report")
    source_root = source_report_path.parent
    source_report_sha256 = _sha256(source_report_path)
    source = json.loads(source_report_path.read_text(encoding="utf-8"))
    if source.get("schema") != AUTHORISED_EXCERPT_SCHEMA:
        raise ValueError("unsupported authorised excerpt schema")
    if source.get("document_sha256") != _source_document_sha256(source):
        raise ValueError("authorised excerpt document hash changed")
    _verify_artifacts(source_root, source.get("artifacts"), "excerpt")

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"Authorised role mapping already exists: {destination}")
    proposals = source.get("excerpt", {}).get("role_group_proposals")
    if not isinstance(proposals, Mapping):
        raise ValueError("excerpt report does not contain role group proposals")
    provider_packs = source.get("provider_packs")
    if not isinstance(provider_packs, Mapping) or set(provider_packs) != set(proposals):
        raise ValueError("provider packs and role group proposals do not match")

    local_report_artifact = source.get("local_separator", {}).get("report")
    local_report_path = _artifact_path(
        source_root,
        local_report_artifact,
        "local separator report",
    )
    local_report = json.loads(local_report_path.read_text(encoding="utf-8"))
    expected_local_document_hash = source.get("local_separator", {}).get(
        "document_sha256"
    )
    if local_report.get("document_sha256") != expected_local_document_hash:
        raise ValueError("local separator document identity changed")
    local_stems = _local_stems(local_report_path.parent, local_report)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-",
            dir=destination.parent,
        )
    )
    temporary.chmod(0o700)
    try:
        groups_root = temporary / "ROLE-GROUPS"
        groups_root.mkdir(mode=0o700)
        signals: dict[str, dict[str, Any]] = {"local-htdemucs": {}}
        group_evidence: dict[str, Any] = {"local-htdemucs": {}}

        local_out = groups_root / "local-htdemucs"
        local_out.mkdir(mode=0o700)
        for role in _ROLES:
            source_path = local_stems[role]
            target = local_out / f"{role}.wav"
            shutil.copyfile(source_path, target)
            value, rate = soundfile.read(target, dtype="float32", always_2d=True)
            _require_common_geometry(value, rate, role)
            signals["local-htdemucs"][role] = value.astype("float64")
            group_evidence["local-htdemucs"][role] = {
                "members": [str(source_path)],
                "artifact": _artifact(temporary, target),
                "rms_dbfs": _db(_rms(value, np=np)),
            }

        provider_memberships: dict[str, dict[str, list[Mapping[str, Any]]]] = {}
        provider_native_closure: dict[str, Any] = {}
        for pack_id in sorted(provider_packs):
            pack = provider_packs[pack_id]
            pack_proposals = proposals[pack_id]
            if not isinstance(pack, Mapping) or not isinstance(pack_proposals, Mapping):
                raise ValueError(f"invalid provider role evidence: {pack_id}")
            memberships = _assign_provider_items(pack_id, pack, pack_proposals)
            provider_memberships[pack_id] = memberships
            pack_out = groups_root / _safe_token(pack_id)
            pack_out.mkdir(mode=0o700)
            signals[pack_id] = {}
            group_evidence[pack_id] = {}
            native_groups = {}
            for role in _ROLES:
                members = memberships[role]
                arrays = []
                member_evidence = []
                for item in members:
                    path = _artifact_path(
                        source_root,
                        item.get("excerpt"),
                        f"{pack_id} {role} member",
                    )
                    value, rate = soundfile.read(path, dtype="float32", always_2d=True)
                    arrays.append(value.astype("float64"))
                    member_evidence.append(
                        {
                            "source_path": item["source_path"],
                            "source_sha256": item["source_sha256"],
                            "excerpt_sha256": item["excerpt"]["sha256"],
                            "native_rms_dbfs": item["rms_dbfs"],
                        }
                    )
                _require_same_native_geometry(arrays, pack_id, role)
                native_group = np.sum(np.stack(arrays, axis=0), axis=0, dtype="float64")
                native_groups[role] = native_group
                target = pack_out / f"{role}.wav"
                common_value, derivation = _write_model_input(
                    native_group,
                    source_rate=int(source["excerpt"]["geometry"]["sample_rate"]),
                    target=target,
                    soundfile=soundfile,
                    np=np,
                )
                _require_common_geometry(common_value, _SAMPLE_RATE, f"{pack_id} {role}")
                signals[pack_id][role] = common_value.astype("float64")
                group_evidence[pack_id][role] = {
                    "members": member_evidence,
                    "artifact": _artifact(temporary, target),
                    "rms_dbfs": _db(_rms(common_value, np=np)),
                    "derivation": derivation,
                }
            proposed_sum = np.sum(
                np.stack([native_groups[role] for role in _ROLES], axis=0),
                axis=0,
                dtype="float64",
            )
            source_sum = _provider_sum(source_root, pack, soundfile=soundfile, np=np)
            delta = proposed_sum - source_sum
            maximum_error = float(np.max(np.abs(delta)))
            provider_native_closure[pack_id] = {
                "passed": maximum_error <= 1e-12,
                "maximum_absolute_error": round(maximum_error, 15),
                "rms_error": round(_rms(delta, np=np), 15),
                "meaning": (
                    "Every non-excluded provider source belongs to exactly one "
                    "proposed broad group; this is partition accounting, not role truth."
                ),
            }
            if maximum_error > 1e-12:
                raise ValueError(f"{pack_id} proposed groups do not close to provider sum")

        features = {
            pack_id: {
                role: _features(value, sample_rate=_SAMPLE_RATE, np=np)
                for role, value in role_signals.items()
            }
            for pack_id, role_signals in signals.items()
        }
        comparisons: dict[str, Any] = {}
        all_diagonal_rank_first = True
        for pack_id in sorted(provider_packs):
            matrix: dict[str, dict[str, Any]] = {}
            observations: dict[str, Any] = {}
            for local_role in _ROLES:
                row = {}
                for provider_role in _ROLES:
                    row[provider_role] = _similarity(
                        features["local-htdemucs"][local_role],
                        features[pack_id][provider_role],
                        np=np,
                    )
                matrix[local_role] = row
                ranked = sorted(
                    _ROLES,
                    key=lambda role: (-row[role]["evidence_similarity"], role),
                )
                proposed_rank = ranked.index(local_role) + 1
                proposed_score = row[local_role]["evidence_similarity"]
                best_other_score = max(
                    row[role]["evidence_similarity"]
                    for role in _ROLES
                    if role != local_role
                )
                rank_first = proposed_rank == 1
                all_diagonal_rank_first = all_diagonal_rank_first and rank_first
                observations[local_role] = {
                    "proposed_provider_role": local_role,
                    "rank": proposed_rank,
                    "ranked_provider_roles": ranked,
                    "evidence_similarity": proposed_score,
                    "margin_over_best_other": round(
                        proposed_score - best_other_score,
                        9,
                    ),
                    "audio_rank_consistent_with_proposal": rank_first,
                    "accepted": False,
                }
            comparisons[pack_id] = {
                "matrix": matrix,
                "proposed_role_observations": observations,
            }

        for path, artifact in source["artifacts"].items():
            _require_hash(
                source_root / path,
                artifact["sha256"],
                f"source artifact {path}",
            )
        if _sha256(source_report_path) != source_report_sha256:
            raise ValueError("excerpt report changed during role mapping")

        document: dict[str, Any] = {
            "schema": AUTHORISED_ROLE_MAPPING_SCHEMA,
            "status": "complete_review_required",
            "evidence_scope": "private_development_only",
            "source_excerpt": {
                "report_path": str(source_report_path),
                "report_sha256": source_report_sha256,
                "document_sha256": source["document_sha256"],
                "track_id": source["corpus"]["track_id"],
                "start_seconds": source["excerpt"]["start_seconds"],
                "end_seconds": source["excerpt"]["end_seconds"],
            },
            "policy": {
                "roles": list(_ROLES),
                "common_sample_rate": _SAMPLE_RATE,
                "provider_names_propose_but_do_not_prove_groups": True,
                "every_nonexcluded_provider_item_assigned_exactly_once": True,
                "similarity_is_descriptive_not_acceptance": True,
                "similarity_weights": {
                    "spectral_shape": 0.55,
                    "envelope": 0.30,
                    "absolute_waveform": 0.15,
                },
            },
            "groups": group_evidence,
            "provider_partition_closure": provider_native_closure,
            "comparisons_to_local_htdemucs": comparisons,
            "observations": {
                "all_proposed_roles_rank_first": all_diagonal_rank_first,
                "automatic_acceptance": False,
            },
            "permissions": {
                "accepted": False,
                "production_eligible": False,
                "automatic_selection": False,
                "automatic_promotion": False,
                "source_graph_activation": False,
                "public_result": False,
                "simple_mode_available": False,
                "studio_import_available": False,
            },
            "effects": {
                "source_audio_mutated": False,
                "group_auditions_created": True,
                "midi_created": False,
                "source_graph_mutated": False,
            },
            "limitations": [
                "HTDemucs is another estimate, not ground truth.",
                "Spectral, envelope and waveform similarity cannot prove musical ownership.",
                "A broad group can rank first while still containing leakage or missing material.",
                "The four-role partition is intentionally coarser than Moises leaf stems.",
                "Human listening remains required before using a mapping as a preference.",
            ],
            "next": {
                "human_role_mapping_review_required": True,
                "inactive_downstream_midi_comparison_allowed": True,
                "automatic_mapping_selection_allowed": False,
            },
        }
        document["artifacts"] = _artifacts(temporary)
        document["document_sha256"] = _document_sha256(document)
        report_path = temporary / _REPORT_NAME
        _write_json(report_path, document)
        _make_private_tree(temporary)
        if os.path.lexists(destination):
            raise FileExistsError(
                f"Authorised role mapping output appeared during run: {destination}"
            )
        os.rename(temporary, destination)
        document["report"] = str(destination / _REPORT_NAME)
        return document
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _assign_provider_items(
    pack_id: str,
    pack: Mapping[str, Any],
    proposals: Mapping[str, Any],
) -> dict[str, list[Mapping[str, Any]]]:
    if set(proposals) != set(_ROLES):
        raise ValueError(f"{pack_id} proposals do not contain the four broad roles")
    result: dict[str, list[Mapping[str, Any]]] = {role: [] for role in _ROLES}
    items = pack.get("items")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise ValueError(f"{pack_id} items are missing")
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError(f"{pack_id} contains invalid item evidence")
        if item.get("excluded_from_pack_sum") is True:
            continue
        filename = Path(str(item.get("source_path", ""))).name.casefold()
        matches = []
        for role in _ROLES:
            patterns = proposals[role]
            if not isinstance(patterns, Sequence) or isinstance(patterns, (str, bytes)):
                raise ValueError(f"{pack_id} {role} proposal is invalid")
            if any(str(pattern).casefold() in filename for pattern in patterns):
                matches.append(role)
        if len(matches) != 1:
            raise ValueError(
                f"{pack_id} provider item must match exactly one broad role: "
                f"{filename} matched {matches}"
            )
        result[matches[0]].append(item)
    for role, members in result.items():
        if not members:
            raise ValueError(f"{pack_id} {role} proposal has no provider members")
    return result


def _local_stems(root: Path, report: Mapping[str, Any]) -> dict[str, Path]:
    raw = report.get("estimated_stems")
    if not isinstance(raw, Mapping) or set(raw) != set(_ROLES):
        raise ValueError("local separator report does not contain four broad stems")
    result = {}
    for role in _ROLES:
        evidence = raw[role]
        if not isinstance(evidence, Mapping):
            raise ValueError(f"invalid local {role} stem evidence")
        path = _inside(root, str(evidence.get("path", "")), f"local {role} stem")
        _require_hash(path, str(evidence.get("sha256", "")), f"local {role} stem")
        result[role] = path
    return result


def _provider_sum(root: Path, pack: Mapping[str, Any], *, soundfile: Any, np: Any) -> Any:
    arrays = []
    for item in pack["items"]:
        if item.get("excluded_from_pack_sum") is True:
            continue
        path = _artifact_path(root, item["excerpt"], "provider sum member")
        value, _rate = soundfile.read(path, dtype="float32", always_2d=True)
        arrays.append(value.astype("float64"))
    _require_same_native_geometry(arrays, "provider", "sum")
    return np.sum(np.stack(arrays, axis=0), axis=0, dtype="float64")


def _features(value: Any, *, sample_rate: int, np: Any) -> dict[str, Any]:
    mono = value.mean(axis=1).astype("float64")
    hop = max(1, int(round(sample_rate * 0.010)))
    usable = (len(mono) // hop) * hop
    envelope = np.sqrt(np.mean(mono[:usable].reshape(-1, hop) ** 2, axis=1))
    return {
        "waveform": mono,
        "envelope": envelope,
        "spectral": _spectral_vector(mono, sample_rate=sample_rate, np=np),
    }


def _spectral_vector(value: Any, *, sample_rate: int, np: Any) -> Any:
    frame_length = 4096
    hop = 2048
    if len(value) < frame_length:
        value = np.pad(value, (0, frame_length - len(value)))
    frame_count = 1 + (len(value) - frame_length) // hop
    starts = np.arange(frame_count) * hop
    frames = np.stack([value[start : start + frame_length] for start in starts])
    window = np.hanning(frame_length)
    power = np.mean(np.abs(np.fft.rfft(frames * window, axis=1)) ** 2, axis=0)
    frequencies = np.fft.rfftfreq(frame_length, 1.0 / sample_rate)
    edges = np.geomspace(30.0, min(18_000.0, sample_rate / 2.0), 65)
    bands = []
    for lower, upper in zip(edges[:-1], edges[1:]):
        mask = (frequencies >= lower) & (frequencies < upper)
        bands.append(float(np.sum(power[mask])) if np.any(mask) else 0.0)
    bands = np.asarray(bands, dtype="float64")
    total = float(np.sum(bands))
    if total > 0:
        bands /= total
    return np.sqrt(bands)


def _similarity(left: Mapping[str, Any], right: Mapping[str, Any], *, np: Any) -> dict[str, float]:
    waveform = abs(_correlation(left["waveform"], right["waveform"], np=np))
    envelope = max(0.0, _correlation(left["envelope"], right["envelope"], np=np))
    spectral = _cosine(left["spectral"], right["spectral"], np=np)
    combined = 0.55 * spectral + 0.30 * envelope + 0.15 * waveform
    return {
        "evidence_similarity": round(float(combined), 9),
        "spectral_shape_cosine": round(float(spectral), 9),
        "envelope_correlation": round(float(envelope), 9),
        "absolute_waveform_correlation": round(float(waveform), 9),
    }


def _correlation(left: Any, right: Any, *, np: Any) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("correlation inputs must have equal non-trivial length")
    left = left - float(np.mean(left))
    right = right - float(np.mean(right))
    denominator = float(np.sqrt(np.dot(left, left) * np.dot(right, right)))
    return float(np.dot(left, right) / denominator) if denominator > 1e-30 else 0.0


def _cosine(left: Any, right: Any, *, np: Any) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(np.dot(left, right) / denominator) if denominator > 1e-30 else 0.0


def _require_common_geometry(value: Any, rate: int, label: str) -> None:
    if int(rate) != _SAMPLE_RATE or value.ndim != 2 or value.shape[1] != 2:
        raise ValueError(f"{label} does not have common 44.1 kHz stereo geometry")


def _require_same_native_geometry(arrays: Sequence[Any], pack: str, role: str) -> None:
    if not arrays or any(value.shape != arrays[0].shape for value in arrays):
        raise ValueError(f"{pack} {role} members do not share native geometry")


def _verify_artifacts(root: Path, raw: Any, label: str) -> None:
    if not isinstance(raw, Mapping) or not raw:
        raise ValueError(f"{label} artifact manifest is missing")
    for relative, evidence in raw.items():
        if not isinstance(evidence, Mapping):
            raise ValueError(f"invalid {label} artifact evidence")
        path = _inside(root, str(relative), f"{label} artifact")
        _require_hash(path, str(evidence.get("sha256", "")), f"{label} artifact")
        if path.stat().st_size != evidence.get("bytes"):
            raise ValueError(f"{label} artifact byte count changed: {relative}")


def _artifact_path(root: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} evidence is missing")
    path = _inside(root, str(raw.get("path", "")), label)
    _require_hash(path, str(raw.get("sha256", "")), label)
    if path.stat().st_size != raw.get("bytes"):
        raise ValueError(f"{label} byte count changed")
    return path


def _inside(root: Path, relative: str, label: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError(f"{label} must use a relative artifact path")
    root = root.resolve(strict=True)
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} escapes its evidence root") from error
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError(f"{label} is not a regular non-link file")
    return path


def _regular_json(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().absolute()
    try:
        details = path.lstat()
    except OSError as error:
        raise ValueError(f"{label} must be a non-empty regular JSON file") from error
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or details.st_size <= 0
        or path.suffix.lower() != ".json"
    ):
        raise ValueError(f"{label} must be a non-empty regular JSON file")
    return path


def _safe_token(value: str) -> str:
    token = "".join(character if character.isalnum() else "-" for character in value)
    token = "-".join(part for part in token.split("-") if part).lower()
    if not token:
        raise ValueError("name does not contain a safe filename token")
    return token


def _artifact(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _artifacts(root: Path) -> dict[str, Any]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("role mapping output contains a symbolic link")
        if path.is_file() and path.name != _REPORT_NAME:
            result[path.relative_to(root).as_posix()] = {
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
    return result


def _rms(value: Any, *, np: Any) -> float:
    return float(np.sqrt(np.mean(value.astype("float64") ** 2))) if value.size else 0.0


def _db(value: float) -> float:
    return round(20.0 * math.log10(max(float(value), 1e-12)), 6)


def _require_hash(path: Path, expected: str, label: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"{label} hash changed: expected {expected}, got {actual}")


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


def _make_private_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("role mapping output contains a symbolic link")
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__: tuple[str, ...] = ()
