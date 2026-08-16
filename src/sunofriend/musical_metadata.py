"""Deterministic, local key, tempo and tuning evidence for source audio.

The estimates in this module are deliberately suggestions.  They can fill a
missing prepared-project value when confidence is high, but they never replace
an explicit value or metadata already carried by the source name.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from .audio_formats import file_sha256
from .source_receipt import canonical_json_bytes, document_sha256


MUSICAL_METADATA_SCHEMA = "sunofriend.musical-metadata-analysis.v1"
MUSICAL_METADATA_RELATIVE_PATH = "INPUT/context/automatic-musical-metadata.json"
ALGORITHM_ID = "librosa-cqt-onset-v1"
ANALYSIS_SAMPLE_RATE = 22_050
HOP_LENGTH = 512
WINDOW_COUNT = 10

_MAJOR_PROFILE = (
    6.35,
    2.23,
    3.48,
    2.33,
    4.38,
    4.09,
    2.52,
    5.19,
    2.39,
    3.66,
    2.29,
    2.88,
)
_MINOR_PROFILE = (
    6.33,
    2.68,
    3.52,
    5.38,
    2.60,
    3.53,
    2.54,
    4.75,
    3.98,
    2.69,
    3.34,
    3.17,
)
_MAJOR_NAMES = (
    "C",
    "Db",
    "D",
    "Eb",
    "E",
    "F",
    "Gb",
    "G",
    "Ab",
    "A",
    "Bb",
    "B",
)
_MINOR_NAMES = (
    "C",
    "C#",
    "D",
    "Eb",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "Bb",
    "B",
)


class MusicalMetadataError(RuntimeError):
    """The local musical-metadata analysis could not produce valid evidence."""


def analyze_musical_metadata(
    source: str | Path,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Return path-free automatic musical evidence for one local audio file."""

    path = Path(source).expanduser().resolve(strict=True)
    if path.is_symlink() or not path.is_file():
        raise MusicalMetadataError("musical metadata source must be a regular file")
    source_hash = file_sha256(path)
    if expected_sha256 is not None and source_hash != expected_sha256:
        raise MusicalMetadataError("musical metadata source hash changed")

    try:
        import librosa
        import numpy as np
    except ImportError as exc:  # pragma: no cover - installation boundary
        raise MusicalMetadataError(
            "automatic key/BPM analysis requires numpy and librosa; "
            "install Sunofriend with the convert extra"
        ) from exc

    try:
        audio, sample_rate = librosa.load(
            path,
            sr=ANALYSIS_SAMPLE_RATE,
            mono=True,
            dtype=np.float32,
        )
    except Exception as exc:
        raise MusicalMetadataError(f"could not decode audio for analysis: {exc}") from exc
    if audio.ndim != 1 or len(audio) < sample_rate:
        raise MusicalMetadataError(
            "automatic key/BPM analysis needs at least one second of audio"
        )
    if not np.all(np.isfinite(audio)):
        raise MusicalMetadataError("decoded analysis audio contains non-finite samples")
    peak = float(np.max(np.abs(audio)))
    if peak <= 1e-8:
        raise MusicalMetadataError("automatic key/BPM analysis cannot analyze silence")

    duration_seconds = float(len(audio) / sample_rate)
    onset = librosa.onset.onset_strength(
        y=audio,
        sr=sample_rate,
        hop_length=HOP_LENGTH,
    )
    tempo = _tempo_evidence(
        audio,
        onset,
        sample_rate=sample_rate,
        librosa=librosa,
        np=np,
    )
    tuning = _tuning_evidence(
        audio,
        sample_rate=sample_rate,
        librosa=librosa,
    )
    key = _key_evidence(
        audio,
        sample_rate=sample_rate,
        tuning_offset=float(tuning["semitone_offset"]),
        librosa=librosa,
        np=np,
    )

    payload: dict[str, Any] = {
        "schema": MUSICAL_METADATA_SCHEMA,
        "status": "complete_unreviewed",
        "network_used": False,
        "source": {
            "sha256": source_hash,
            "bytes": path.stat().st_size,
            "duration_seconds": _rounded(duration_seconds, 6),
        },
        "algorithm": {
            "id": ALGORITHM_ID,
            "analysis_sample_rate": ANALYSIS_SAMPLE_RATE,
            "hop_length": HOP_LENGTH,
            "window_count": WINDOW_COUNT,
            "tempo_method": "onset-strength autocorrelation with segment agreement",
            "key_method": "tuning-aware CQT chroma with major/minor profiles",
            "tuning_method": "spectral-bin deviation from equal temperament",
        },
        "estimates": {
            "tempo": tempo,
            "key": key,
            "tuning": tuning,
        },
        "suggested_metadata": {
            "bpm": tempo["selected_bpm"],
            "key": key["selected_key"],
            "tuning_hz": tuning["concert_a_hz"],
        },
        "review": {
            "status": "not_reviewed",
            "review_recommended": True,
            "claim": (
                "Automatic musical estimates are starting points for a musician "
                "or DAW, not human-confirmed facts."
            ),
        },
        "effects": {
            "source_audio_mutated": False,
            "midi_mutated": False,
            "project_state_changed": False,
        },
    }
    return {**payload, "analysis_sha256": document_sha256(payload)}


def unavailable_musical_metadata_analysis(
    source: str | Path,
    *,
    source_sha256: str,
    duration_seconds: float | None,
    reason_code: str,
) -> dict[str, Any]:
    """Return path-free evidence that an attempted analysis was unavailable."""

    path = Path(source)
    payload: dict[str, Any] = {
        "schema": MUSICAL_METADATA_SCHEMA,
        "status": "unavailable",
        "network_used": False,
        "source": {
            "sha256": source_sha256,
            "bytes": path.stat().st_size,
            "duration_seconds": (
                _rounded(duration_seconds, 6)
                if duration_seconds is not None
                else None
            ),
        },
        "algorithm": {
            "id": ALGORITHM_ID,
            "analysis_sample_rate": ANALYSIS_SAMPLE_RATE,
            "hop_length": HOP_LENGTH,
            "window_count": WINDOW_COUNT,
        },
        "estimates": None,
        "suggested_metadata": {"bpm": None, "key": None, "tuning_hz": None},
        "unavailable": {
            "reason_code": str(reason_code),
            "claim": "No automatic musical value was promoted.",
        },
        "review": {
            "status": "not_reviewed",
            "review_recommended": True,
        },
        "effects": {
            "source_audio_mutated": False,
            "midi_mutated": False,
            "project_state_changed": False,
        },
    }
    return {**payload, "analysis_sha256": document_sha256(payload)}


def resolve_metadata_precedence(
    analysis: Mapping[str, Any],
    *,
    explicit_key: str | None,
    explicit_bpm: float | None,
    explicit_tuning_hz: float | None,
    inferred_key: str | None,
    inferred_bpm: float | None,
    inferred_tuning_hz: float | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply explicit > existing convention > high-confidence automatic."""

    estimates = analysis.get("estimates")
    suggested = analysis.get("suggested_metadata")
    if not isinstance(suggested, Mapping):
        raise MusicalMetadataError("musical metadata analysis is incomplete")
    if not isinstance(estimates, Mapping):
        effective = {
            "key": explicit_key if explicit_key is not None else inferred_key,
            "bpm": explicit_bpm if explicit_bpm is not None else inferred_bpm,
            "tuning_hz": (
                explicit_tuning_hz
                if explicit_tuning_hz is not None
                else inferred_tuning_hz
            ),
        }
        resolution = {
            "precedence": [
                "explicit_cli",
                "filename_or_folder",
                "high_confidence_automatic",
                "unknown",
            ],
            "effective": dict(effective),
            "provenance": {
                field: (
                    "explicit_cli"
                    if explicit is not None
                    else "filename_or_folder"
                    if inferred is not None
                    else "unknown"
                )
                for field, explicit, inferred in (
                    ("key", explicit_key, inferred_key),
                    ("bpm", explicit_bpm, inferred_bpm),
                    ("tuning_hz", explicit_tuning_hz, inferred_tuning_hz),
                )
            },
            "automatic_comparison": dict(suggested),
            "automatic_overrode_existing_metadata": False,
            "review_recommended": True,
        }
        return effective, resolution
    tempo = estimates.get("tempo")
    key = estimates.get("key")
    tuning = estimates.get("tuning")
    if not all(isinstance(item, Mapping) for item in (tempo, key, tuning)):
        raise MusicalMetadataError("musical metadata estimate records are invalid")

    resolved_key, key_source = _one_precedence_value(
        explicit_key,
        inferred_key,
        suggested.get("key") if key.get("confidence") == "high" else None,
    )
    resolved_bpm, bpm_source = _one_precedence_value(
        explicit_bpm,
        inferred_bpm,
        suggested.get("bpm") if tempo.get("confidence") == "high" else None,
    )
    # Tuning estimation is useful evidence but is intentionally never promoted
    # without an explicit or existing project convention in v1.
    resolved_tuning, tuning_source = _one_precedence_value(
        explicit_tuning_hz,
        inferred_tuning_hz,
        None,
    )
    effective = {
        "key": resolved_key,
        "bpm": resolved_bpm,
        "tuning_hz": resolved_tuning,
    }
    resolution = {
        "precedence": [
            "explicit_cli",
            "filename_or_folder",
            "high_confidence_automatic",
            "unknown",
        ],
        "effective": dict(effective),
        "provenance": {
            "key": key_source,
            "bpm": bpm_source,
            "tuning_hz": tuning_source,
        },
        "automatic_comparison": {
            "key": suggested.get("key"),
            "bpm": suggested.get("bpm"),
            "tuning_hz": suggested.get("tuning_hz"),
        },
        "automatic_overrode_existing_metadata": False,
        "review_recommended": True,
    }
    return effective, resolution


def with_resolution(
    analysis: Mapping[str, Any], resolution: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind one precedence decision into a new self-hashed evidence document."""

    payload = {
        key: value
        for key, value in analysis.items()
        if key not in {"analysis_sha256", "resolution"}
    }
    payload["resolution"] = dict(resolution)
    return {**payload, "analysis_sha256": document_sha256(payload)}


def write_musical_metadata_analysis(
    path: str | Path, document: Mapping[str, Any]
) -> Path:
    """Create one immutable-ready JSON sidecar without replacing a file."""

    target = Path(path)
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"musical metadata evidence already exists: {target}")
    validate_musical_metadata_analysis(document)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(canonical_json_bytes(document))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def validate_musical_metadata_analysis(document: Mapping[str, Any]) -> None:
    if document.get("schema") != MUSICAL_METADATA_SCHEMA:
        raise ValueError("unsupported musical metadata analysis schema")
    digest = str(document.get("analysis_sha256") or "")
    payload = {key: value for key, value in document.items() if key != "analysis_sha256"}
    if digest != document_sha256(payload):
        raise ValueError("musical metadata analysis hash does not match its content")
    source = document.get("source")
    if not isinstance(source, Mapping) or not _is_sha256(source.get("sha256")):
        raise ValueError("musical metadata source identity is invalid")
    if document.get("network_used") is not False:
        raise ValueError("musical metadata analysis must remain local")


def load_musical_metadata_analysis(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("musical metadata analysis must be a JSON object")
    validate_musical_metadata_analysis(value)
    return dict(value)


def _tempo_evidence(audio, onset, *, sample_rate: int, librosa, np) -> dict[str, Any]:
    global_value = float(
        np.asarray(
            librosa.feature.tempo(
                onset_envelope=onset,
                sr=sample_rate,
                hop_length=HOP_LENGTH,
                aggregate=np.median,
            )
        ).reshape(-1)[0]
    )
    if not math.isfinite(global_value) or global_value <= 0:
        raise MusicalMetadataError("tempo analysis did not produce a positive value")

    bounds = np.linspace(0, len(audio), WINDOW_COUNT + 1, dtype=int)
    window_tempos: list[float] = []
    for start, end in zip(bounds[:-1], bounds[1:]):
        segment = audio[int(start) : int(end)]
        segment_onset = librosa.onset.onset_strength(
            y=segment,
            sr=sample_rate,
            hop_length=HOP_LENGTH,
        )
        value = float(
            np.asarray(
                librosa.feature.tempo(
                    onset_envelope=segment_onset,
                    sr=sample_rate,
                    hop_length=HOP_LENGTH,
                    aggregate=np.median,
                )
            ).reshape(-1)[0]
        )
        if math.isfinite(value) and value > 0:
            window_tempos.append(value)

    family_matches = sum(
        1 for value in window_tempos if _same_tempo_family(value, global_value)
    )
    agreement = family_matches / len(window_tempos) if window_tempos else 0.0
    confidence = "high" if agreement >= 0.8 else "medium" if agreement >= 0.5 else "low"
    selected = _snap_tempo(global_value)
    candidates = _tempo_candidates(global_value, window_tempos)
    return {
        "selected_bpm": selected,
        "raw_bpm": _rounded(global_value, 6),
        "confidence": confidence,
        "confidence_score": _rounded(agreement, 4),
        "window_count": len(window_tempos),
        "family_agreement_count": family_matches,
        "window_bpms": [_rounded(value, 6) for value in window_tempos],
        "candidates": candidates,
        "half_time_bpm": _snap_tempo(global_value / 2.0),
        "double_time_bpm": _snap_tempo(global_value * 2.0),
        "meter_or_feel_confirmed": False,
    }


def _key_evidence(audio, *, sample_rate: int, tuning_offset: float, librosa, np) -> dict[str, Any]:
    chroma = librosa.feature.chroma_cqt(
        y=audio,
        sr=sample_rate,
        hop_length=HOP_LENGTH,
        tuning=tuning_offset,
    )
    if chroma.ndim != 2 or chroma.shape[0] != 12 or chroma.shape[1] == 0:
        raise MusicalMetadataError("key analysis did not produce chroma evidence")
    global_scores = _key_scores(np.median(chroma, axis=1), np=np)
    ranked = sorted(global_scores, key=lambda item: item["score"], reverse=True)
    selected = ranked[0]
    margin = float(selected["score"] - ranked[1]["score"])

    votes: dict[str, int] = {}
    for segment in np.array_split(chroma, WINDOW_COUNT, axis=1):
        if segment.shape[1] == 0:
            continue
        result = max(
            _key_scores(np.median(segment, axis=1), np=np),
            key=lambda item: item["score"],
        )
        label = str(result["key"])
        votes[label] = votes.get(label, 0) + 1
    selected_votes = votes.get(str(selected["key"]), 0)
    vote_total = sum(votes.values())
    agreement = selected_votes / vote_total if vote_total else 0.0
    confidence_score = max(0.0, min(1.0, agreement * max(0.0, margin) / 0.12))
    confidence = (
        "high"
        if agreement >= 0.6 and margin >= 0.08
        else "medium"
        if agreement >= 0.4 and margin >= 0.035
        else "low"
    )
    return {
        "selected_key": selected["key"],
        "confidence": confidence,
        "confidence_score": _rounded(confidence_score, 4),
        "profile_margin": _rounded(margin, 6),
        "window_count": vote_total,
        "selected_window_votes": selected_votes,
        "window_votes": dict(sorted(votes.items())),
        "candidates": [
            {"key": item["key"], "score": _rounded(item["score"], 6)}
            for item in ranked[:5]
        ],
        "human_confirmed": False,
    }


def _tuning_evidence(audio, *, sample_rate: int, librosa) -> dict[str, Any]:
    try:
        offset = float(librosa.estimate_tuning(y=audio, sr=sample_rate))
    except Exception:
        offset = 0.0
    if not math.isfinite(offset):
        offset = 0.0
    concert_a = 440.0 * (2.0 ** (offset / 12.0))
    return {
        "concert_a_hz": _rounded(concert_a, 3),
        "semitone_offset": _rounded(offset, 6),
        "confidence": "review_recommended",
        "automatically_promoted": False,
    }


def _key_scores(chroma, *, np) -> list[dict[str, Any]]:
    vector = np.asarray(chroma, dtype=float)
    if not np.all(np.isfinite(vector)) or float(np.linalg.norm(vector)) <= 1e-12:
        raise MusicalMetadataError("key chroma evidence is silent or invalid")
    scores: list[dict[str, Any]] = []
    for mode, profile, names in (
        ("major", _MAJOR_PROFILE, _MAJOR_NAMES),
        ("minor", _MINOR_PROFILE, _MINOR_NAMES),
    ):
        profile_array = np.asarray(profile, dtype=float)
        for pitch_class, name in enumerate(names):
            rolled = np.roll(profile_array, pitch_class)
            score = float(np.corrcoef(vector, rolled)[0, 1])
            if not math.isfinite(score):
                score = -1.0
            scores.append({"key": f"{name} {mode}", "score": score})
    return scores


def _tempo_candidates(global_value: float, window_tempos: list[float]) -> list[dict[str, Any]]:
    families: dict[float, int] = {}
    values = [global_value, global_value / 2.0, global_value * 2.0, *window_tempos]
    for value in values:
        if not math.isfinite(value) or not 30.0 <= value <= 300.0:
            continue
        snapped = float(_snap_tempo(value))
        families[snapped] = families.get(snapped, 0) + 1
    ranked = sorted(families.items(), key=lambda item: (-item[1], abs(item[0] - global_value)))
    return [{"bpm": value, "support": support} for value, support in ranked[:6]]


def _same_tempo_family(value: float, target: float) -> bool:
    return any(abs(value - candidate) / candidate <= 0.035 for candidate in (target, target / 2.0, target * 2.0))


def _snap_tempo(value: float) -> int | float:
    nearest = round(value)
    return int(nearest) if abs(value - nearest) <= 0.5 else _rounded(value, 3)


def _one_precedence_value(explicit: Any, inferred: Any, automatic: Any) -> tuple[Any, str]:
    if explicit is not None and (not isinstance(explicit, str) or explicit.strip()):
        return explicit, "explicit_cli"
    if inferred is not None and (not isinstance(inferred, str) or inferred.strip()):
        return inferred, "filename_or_folder"
    if automatic is not None:
        return automatic, "high_confidence_automatic"
    return None, "unknown"


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _rounded(value: float, places: int) -> float:
    return float(round(float(value), places))


__all__ = [
    "ALGORITHM_ID",
    "MUSICAL_METADATA_RELATIVE_PATH",
    "MUSICAL_METADATA_SCHEMA",
    "MusicalMetadataError",
    "analyze_musical_metadata",
    "load_musical_metadata_analysis",
    "resolve_metadata_precedence",
    "validate_musical_metadata_analysis",
    "with_resolution",
    "unavailable_musical_metadata_analysis",
    "write_musical_metadata_analysis",
]
