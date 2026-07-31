"""Prepare one authorised real-song excerpt for private separation research.

This is a development-only bridge between the tracked, audio-free corpus
manifest and the existing private HTDemucs runner.  It never imports a result
into a Sunofriend project.  Provider excerpts and every derived artifact stay
under the caller's fresh local output directory.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


AUTHORISED_EXCERPT_SCHEMA = "sunofriend.private-authorised-separation-excerpt.v1"
_CORPUS_SCHEMA = "sunofriend.authorised-separation-corpus.v1"
_REPORT_NAME = "authorised-separation-excerpt.json"


def _run_authorised_separation_excerpt(
    corpus_manifest_path: str | Path,
    track_id: str,
    *,
    out_dir: str | Path,
    checkpoint_path: str | Path,
    python: str | Path | None = None,
    separator_runner: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Stage aligned provider excerpts and run one private local separator."""

    import numpy as np
    import soundfile

    manifest_path = _regular_json(corpus_manifest_path, "corpus manifest")
    manifest_sha256 = _sha256(manifest_path)
    corpus = json.loads(manifest_path.read_text(encoding="utf-8"))
    if corpus.get("schema") != _CORPUS_SCHEMA:
        raise ValueError("unsupported authorised separation corpus schema")
    permission = corpus.get("permission")
    if not isinstance(permission, Mapping):
        raise ValueError("corpus permission record is missing")
    artist = corpus.get("artist")
    if not isinstance(artist, Mapping):
        raise ValueError("corpus artist record is missing")
    artist_name = str(artist.get("name", "")).strip()
    artist_profile = str(artist.get("soundcloud_profile", "")).strip()
    if not artist_name or not artist_profile:
        raise ValueError("corpus artist name and profile are required")
    track = _track(corpus, track_id)
    if track.get("evaluation_state") not in {
        "ready_for_excerpt_selection",
        "private_excerpt_staged",
    }:
        raise ValueError(f"track is not ready for excerpt selection: {track_id}")
    plan = _excerpt_plan(track)
    start = float(plan["start_seconds"])
    end = float(plan["end_seconds"])
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise ValueError("evaluation excerpt bounds must be finite and increasing")
    if end - start > 30.0:
        raise ValueError("authorised development excerpts are limited to 30 seconds")

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"Authorised separation excerpt output already exists: {destination}"
        )
    checkpoint = _regular_file(checkpoint_path, "Demucs checkpoint")
    track_root = _inside(
        manifest_path.parent,
        str(track["directory"]),
        "track directory",
        require_directory=True,
    )
    original_files = _wav_files(track_root / "ORIGINAL")
    if len(original_files) != 1:
        raise ValueError("track must contain exactly one ORIGINAL WAV")
    original = original_files[0]

    pack_specs: list[tuple[str, Path, tuple[str, ...]]] = []
    seen_pack_ids: set[str] = set()
    for raw_pack in plan["provider_packs"]:
        if not isinstance(raw_pack, Mapping):
            raise ValueError("provider pack entries must be objects")
        pack_id = str(raw_pack.get("id", "")).strip()
        if not pack_id or pack_id in seen_pack_ids:
            raise ValueError("provider pack ids must be non-empty and unique")
        seen_pack_ids.add(pack_id)
        pack_dir = _inside(
            track_root,
            str(raw_pack.get("directory", "")),
            f"{pack_id} provider directory",
            require_directory=True,
        )
        excluded = tuple(
            str(value).strip().lower()
            for value in raw_pack.get("exclude_filename_contains", [])
            if str(value).strip()
        )
        pack_specs.append((pack_id, pack_dir, excluded))
    role_group_proposals = _role_group_proposals(plan, seen_pack_ids)

    source_paths = [original]
    provider_inputs: dict[str, list[Path]] = {}
    for pack_id, pack_dir, _excluded in pack_specs:
        paths = _wav_files(pack_dir)
        if not paths:
            raise ValueError(f"provider pack contains no WAV files: {pack_id}")
        provider_inputs[pack_id] = paths
        source_paths.extend(paths)
    source_hashes = {path: _sha256(path) for path in source_paths}

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-",
            dir=destination.parent,
        )
    )
    temporary.chmod(0o700)
    local_run_started = False
    try:
        original_excerpt_dir = temporary / "ORIGINAL-EXCERPT"
        provider_excerpt_root = temporary / "PROVIDER-EXCERPTS"
        local_run_dir = temporary / "LOCAL-HTDEMUCS"
        original_excerpt_dir.mkdir(mode=0o700)
        provider_excerpt_root.mkdir(mode=0o700)

        original_excerpt_path = original_excerpt_dir / "source.wav"
        original_excerpt, sample_rate = _write_excerpt(
            original,
            original_excerpt_path,
            start=start,
            end=end,
            soundfile=soundfile,
        )
        geometry = {
            "sample_rate": sample_rate,
            "channels": int(original_excerpt.shape[1]),
            "frames": int(original_excerpt.shape[0]),
            "duration_seconds": round(len(original_excerpt) / sample_rate, 9),
        }
        original_evidence = {
            "source_path": str(original),
            "source_sha256": source_hashes[original],
            "excerpt": _artifact(temporary, original_excerpt_path),
            "geometry": geometry,
            "rms_dbfs": _rms_dbfs(original_excerpt, np=np),
            "peak": round(float(np.max(np.abs(original_excerpt))), 9),
        }
        model_input_dir = temporary / "LOCAL-MODEL-INPUT"
        model_input_dir.mkdir(mode=0o700)
        model_input_path = model_input_dir / "source-44100.wav"
        model_input, model_input_policy = _write_model_input(
            original_excerpt,
            source_rate=sample_rate,
            target=model_input_path,
            soundfile=soundfile,
            np=np,
        )
        original_evidence["local_model_input"] = {
            "artifact": _artifact(temporary, model_input_path),
            "geometry": {
                "sample_rate": 44_100,
                "channels": int(model_input.shape[1]),
                "frames": int(model_input.shape[0]),
                "duration_seconds": round(len(model_input) / 44_100, 9),
            },
            "derivation": model_input_policy,
        }

        provider_evidence: dict[str, Any] = {}
        for pack_id, _pack_dir, excluded_tokens in pack_specs:
            pack_output = provider_excerpt_root / _safe_token(pack_id)
            pack_output.mkdir(mode=0o700)
            items = []
            sum_inputs = []
            for index, source in enumerate(provider_inputs[pack_id]):
                target = pack_output / f"{index:02d}-{_safe_token(source.stem)}.wav"
                excerpt, rate = _write_excerpt(
                    source,
                    target,
                    start=start,
                    end=end,
                    soundfile=soundfile,
                )
                if rate != sample_rate or excerpt.shape != original_excerpt.shape:
                    raise ValueError(
                        f"{pack_id} provider excerpt geometry does not match original"
                    )
                excluded = any(token in source.name.lower() for token in excluded_tokens)
                if not excluded:
                    sum_inputs.append(excerpt.astype("float64"))
                items.append(
                    {
                        "source_path": str(source),
                        "source_sha256": source_hashes[source],
                        "excerpt": _artifact(temporary, target),
                        "rms_dbfs": _rms_dbfs(excerpt, np=np),
                        "excluded_from_pack_sum": excluded,
                    }
                )
            if not sum_inputs:
                raise ValueError(f"provider pack has no sources eligible for sum: {pack_id}")
            provider_sum = np.sum(np.stack(sum_inputs, axis=0), axis=0, dtype="float64")
            provider_evidence[pack_id] = {
                "source_count": len(items),
                "summed_source_count": len(sum_inputs),
                "items": items,
                "pack_sum_alignment": _alignment_metrics(
                    original_excerpt.astype("float64"),
                    provider_sum,
                    sample_rate=sample_rate,
                    np=np,
                ),
            }

        if separator_runner is None:
            from ._separation_demucs_private_run import (
                _run_private_demucs_four_stem_experiment,
            )

            run_separator = _run_private_demucs_four_stem_experiment
        else:
            run_separator = separator_runner
        local_run_started = True
        local_result = run_separator(
            model_input_path,
            out_dir=local_run_dir,
            checkpoint_path=checkpoint,
            start_seconds=0.0,
            end_seconds=len(model_input) / 44_100,
            python=python,
        )
        local_report = _regular_json(local_result["report"], "local separator report")
        if not _is_inside(temporary, local_report):
            raise ValueError("local separator report was written outside output")

        for path, expected_hash in source_hashes.items():
            _require_hash(path, expected_hash, f"{path.name} source")
        if _sha256(manifest_path) != manifest_sha256:
            raise ValueError("corpus manifest changed during excerpt preparation")

        document: dict[str, Any] = {
            "schema": AUTHORISED_EXCERPT_SCHEMA,
            "status": "complete_review_required",
            "evidence_scope": "private_development_only",
            "corpus": {
                "manifest_path": str(manifest_path),
                "manifest_sha256": manifest_sha256,
                "track_id": track["id"],
                "track_title": track["title"],
                "artist": dict(artist),
                "permission": dict(permission),
                "preferred_credit": f"Music by {artist_name} — {artist_profile}",
            },
            "excerpt": {
                "start_seconds": start,
                "end_seconds": end,
                "selection_policy": plan["selection_policy"],
                "geometry": geometry,
                "role_group_proposals": role_group_proposals,
            },
            "original": original_evidence,
            "provider_packs": provider_evidence,
            "local_separator": {
                "status": local_result.get("status"),
                "report": _artifact(temporary, local_report),
                "document_sha256": _load_document_hash(local_report),
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
                "provider_audio_mutated": False,
                "local_excerpts_created": True,
                "midi_created": False,
                "source_graph_mutated": False,
            },
            "limitations": [
                "Provider outputs are estimated stems, not ground-truth multitracks.",
                "Pack-sum correlation proves broad alignment, not correct role assignment.",
                "Provider labels are not assumed to describe equivalent musical content.",
                "The local HTDemucs input is an explicitly recorded 44.1 kHz derivative of the native-rate original excerpt.",
                "This one authorised excerpt is not a hidden test set or acceptance threshold.",
                "No MIDI candidate, separator result or provider pack is selected here.",
                "Provider-derived audio remains local pending redistribution-term review.",
            ],
            "next": {
                "provider_role_mapping_required": True,
                "downstream_midi_comparison_required": True,
                "human_listening_required": True,
                "cross_song_repetition_required": True,
            },
        }
        document["artifacts"] = _artifacts(temporary)
        document["document_sha256"] = _document_sha256(document)
        report_path = temporary / _REPORT_NAME
        _write_json(report_path, document)
        _make_private_tree(temporary)
        if os.path.lexists(destination):
            raise FileExistsError(
                f"Authorised separation excerpt output appeared during run: {destination}"
            )
        os.rename(temporary, destination)
        document["report"] = str(destination / _REPORT_NAME)
        return document
    except BaseException:
        if temporary.exists():
            if local_run_started and (temporary / "LOCAL-HTDEMUCS").exists():
                # The inner private runner intentionally preserves failure evidence.
                # Keep that contract, but never label the outer run complete.
                failure_destination = destination
                if not os.path.lexists(failure_destination):
                    os.rename(temporary, failure_destination)
                else:
                    shutil.rmtree(temporary, ignore_errors=True)
            else:
                shutil.rmtree(temporary, ignore_errors=True)
        raise


def _track(corpus: Mapping[str, Any], track_id: str) -> Mapping[str, Any]:
    wanted = str(track_id).strip()
    matches = [
        value
        for value in corpus.get("tracks", [])
        if isinstance(value, Mapping) and value.get("id") == wanted
    ]
    if len(matches) != 1:
        raise ValueError(f"corpus track id must resolve exactly once: {wanted}")
    return matches[0]


def _excerpt_plan(track: Mapping[str, Any]) -> Mapping[str, Any]:
    plan = track.get("evaluation_excerpt")
    if not isinstance(plan, Mapping):
        raise ValueError("track does not contain an evaluation excerpt plan")
    packs = plan.get("provider_packs")
    if not isinstance(packs, Sequence) or isinstance(packs, (str, bytes)) or not packs:
        raise ValueError("evaluation excerpt must contain provider packs")
    if not str(plan.get("selection_policy", "")).strip():
        raise ValueError("evaluation excerpt selection policy is missing")
    return plan


def _role_group_proposals(
    plan: Mapping[str, Any],
    pack_ids: set[str],
) -> dict[str, dict[str, list[str]]]:
    raw = plan.get("role_group_proposals")
    if not isinstance(raw, Mapping) or set(raw) != pack_ids:
        raise ValueError("role group proposals must match provider pack ids exactly")
    expected_roles = {"bass", "drums", "other", "vocals"}
    result: dict[str, dict[str, list[str]]] = {}
    for pack_id in sorted(pack_ids):
        groups = raw[pack_id]
        if not isinstance(groups, Mapping) or set(groups) != expected_roles:
            raise ValueError(
                f"{pack_id} role group proposals must contain bass, drums, other and vocals"
            )
        result[pack_id] = {}
        for role in sorted(expected_roles):
            patterns = groups[role]
            if (
                not isinstance(patterns, Sequence)
                or isinstance(patterns, (str, bytes))
                or not patterns
            ):
                raise ValueError(f"{pack_id} {role} proposal must contain patterns")
            normalized = [str(pattern).strip() for pattern in patterns]
            if any(not pattern for pattern in normalized) or len(set(normalized)) != len(
                normalized
            ):
                raise ValueError(
                    f"{pack_id} {role} proposal patterns must be non-empty and unique"
                )
            result[pack_id][role] = normalized
    return result


def _write_excerpt(
    source: Path,
    target: Path,
    *,
    start: float,
    end: float,
    soundfile: Any,
) -> tuple[Any, int]:
    details = soundfile.info(source)
    rate = int(details.samplerate)
    start_frame = int(round(start * rate))
    end_frame = int(round(end * rate))
    if start_frame < 0 or end_frame <= start_frame or end_frame > int(details.frames):
        raise ValueError(f"excerpt is outside source horizon: {source}")
    value, read_rate = soundfile.read(
        source,
        start=start_frame,
        stop=end_frame,
        dtype="float32",
        always_2d=True,
    )
    if int(read_rate) != rate or len(value) != end_frame - start_frame:
        raise ValueError(f"decoded excerpt geometry changed: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(target, value, rate, subtype="PCM_24")
    reopened, reopened_rate = soundfile.read(target, dtype="float32", always_2d=True)
    if int(reopened_rate) != rate or reopened.shape != value.shape:
        raise ValueError(f"persisted excerpt geometry changed: {target}")
    return reopened, rate


def _write_model_input(
    value: Any,
    *,
    source_rate: int,
    target: Path,
    soundfile: Any,
    np: Any,
) -> tuple[Any, dict[str, Any]]:
    target_rate = 44_100
    if source_rate == target_rate:
        resampled = value.astype("float64")
        algorithm = "identity"
        scipy_version = None
    else:
        from scipy.signal import resample_poly

        divisor = math.gcd(source_rate, target_rate)
        up = target_rate // divisor
        down = source_rate // divisor
        resampled = resample_poly(
            value.astype("float64"),
            up,
            down,
            axis=0,
            padtype="constant",
        )
        expected_frames = int(round(len(value) * target_rate / source_rate))
        if len(resampled) > expected_frames:
            resampled = resampled[:expected_frames]
        elif len(resampled) < expected_frames:
            padding = np.zeros(
                (expected_frames - len(resampled), value.shape[1]),
                dtype="float64",
            )
            resampled = np.concatenate((resampled, padding), axis=0)
        algorithm = f"scipy.signal.resample_poly(up={up},down={down},padtype=constant)"
        scipy_version = importlib.metadata.version("scipy")
    if int(np.count_nonzero(np.abs(resampled) > 1.0)):
        peak = float(np.max(np.abs(resampled)))
        resampled = np.clip(resampled, -1.0, 1.0)
        clipping = {
            "required": True,
            "pre_clip_peak": round(peak, 9),
            "policy": "clip only samples outside PCM full scale after resampling",
        }
    else:
        clipping = {"required": False, "pre_clip_peak": None, "policy": "none"}
    soundfile.write(target, resampled, target_rate, subtype="PCM_24")
    reopened, reopened_rate = soundfile.read(target, dtype="float32", always_2d=True)
    if int(reopened_rate) != target_rate or reopened.shape != resampled.shape:
        raise ValueError("persisted local model input geometry changed")
    return reopened, {
        "source_sample_rate": source_rate,
        "target_sample_rate": target_rate,
        "algorithm": algorithm,
        "scipy_version": scipy_version,
        "pcm_subtype": "PCM_24",
        "clipping": clipping,
        "source_excerpt_preserved": True,
    }


def _alignment_metrics(reference: Any, candidate: Any, *, sample_rate: int, np: Any) -> dict[str, Any]:
    reference_mono = reference.mean(axis=1)
    candidate_mono = candidate.mean(axis=1)
    reference_rms = _rms(reference_mono, np=np)
    candidate_rms = _rms(candidate_mono, np=np)
    denominator = float(np.dot(candidate_mono, candidate_mono))
    gain = float(np.dot(reference_mono, candidate_mono) / denominator) if denominator else 0.0
    residual = reference_mono - gain * candidate_mono
    sample_correlation = _correlation(reference_mono, candidate_mono, np=np)

    hop = max(1, int(round(sample_rate * 0.010)))
    usable = (len(reference_mono) // hop) * hop
    reference_envelope = np.sqrt(
        np.mean(reference_mono[:usable].reshape(-1, hop) ** 2, axis=1)
    )
    candidate_envelope = np.sqrt(
        np.mean(candidate_mono[:usable].reshape(-1, hop) ** 2, axis=1)
    )
    max_lag_bins = min(100, max(0, len(reference_envelope) - 2))
    best_lag = 0
    best_correlation = -1.0
    for lag in range(-max_lag_bins, max_lag_bins + 1):
        if lag < 0:
            left = reference_envelope[-lag:]
            right = candidate_envelope[:lag]
        elif lag > 0:
            left = reference_envelope[:-lag]
            right = candidate_envelope[lag:]
        else:
            left = reference_envelope
            right = candidate_envelope
        value = _correlation(left, right, np=np)
        if value > best_correlation:
            best_correlation = value
            best_lag = lag
    return {
        "sample_correlation_at_recorded_zero": round(sample_correlation, 9),
        "optimal_sum_gain_db": _db(abs(gain)),
        "reference_rms_dbfs": _db(reference_rms),
        "provider_sum_rms_dbfs": _db(candidate_rms),
        "gain_matched_residual_rms_dbfs": _db(_rms(residual, np=np)),
        "envelope_best_lag_ms": round(best_lag * 10.0, 6),
        "envelope_correlation_at_best_lag": round(best_correlation, 9),
        "lag_semantics": "positive means provider activity is later than original",
        "sum_semantics": "all non-excluded decoded provider stems summed in float64",
    }


def _correlation(left: Any, right: Any, *, np: Any) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("correlation inputs must have equal non-trivial length")
    left_centered = left - float(np.mean(left))
    right_centered = right - float(np.mean(right))
    denominator = float(
        np.sqrt(np.dot(left_centered, left_centered) * np.dot(right_centered, right_centered))
    )
    if denominator <= 1e-30:
        return 0.0
    return float(np.dot(left_centered, right_centered) / denominator)


def _rms(value: Any, *, np: Any) -> float:
    return float(np.sqrt(np.mean(value.astype("float64") ** 2))) if value.size else 0.0


def _rms_dbfs(value: Any, *, np: Any) -> float:
    return _db(_rms(value, np=np))


def _db(value: float) -> float:
    return round(20.0 * math.log10(max(float(value), 1e-12)), 6)


def _wav_files(directory: Path) -> list[Path]:
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError(f"expected a regular directory: {directory}")
    result = []
    for path in sorted(directory.glob("*.wav"), key=lambda value: value.name.casefold()):
        result.append(_regular_file(path, f"WAV in {directory.name}"))
    return result


def _inside(root: Path, relative: str, label: str, *, require_directory: bool = False) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError(f"{label} must be a relative path")
    root_resolved = root.resolve(strict=True)
    path = (root_resolved / relative).resolve(strict=True)
    try:
        path.relative_to(root_resolved)
    except ValueError as error:
        raise ValueError(f"{label} escapes its allowed root") from error
    if require_directory and (not path.is_dir() or path.is_symlink()):
        raise ValueError(f"{label} must be a regular directory")
    return path


def _regular_json(value: str | Path, label: str) -> Path:
    path = _regular_file(value, label)
    if path.suffix.lower() != ".json":
        raise ValueError(f"{label} must be JSON")
    return path


def _regular_file(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().absolute()
    try:
        details = path.lstat()
    except OSError as error:
        raise ValueError(f"{label} must be a non-empty regular non-link file") from error
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode) or details.st_size <= 0:
        raise ValueError(f"{label} must be a non-empty regular non-link file")
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
            raise ValueError("authorised excerpt output contains a symbolic link")
        if path.is_file() and path.name != _REPORT_NAME:
            result[path.relative_to(root).as_posix()] = {
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
    return result


def _load_document_hash(path: Path) -> str | None:
    value = json.loads(path.read_text(encoding="utf-8"))
    document_hash = value.get("document_sha256")
    return str(document_hash) if document_hash is not None else None


def _require_hash(path: Path, expected: str, label: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"{label} hash changed: expected {expected}, got {actual}")


def _is_inside(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


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
            raise ValueError("authorised excerpt output contains a symbolic link")
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
