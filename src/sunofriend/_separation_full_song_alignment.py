"""Measure private full-song source-to-reconstruction alignment and drift.

This contract answers one narrow question: does the diagnostic reconstruction
remain synchronized with the exact canonical source from early to late in the
song?  It does not score stem fidelity, accept a separator, or enable a product
route.
"""

from __future__ import annotations

from copy import deepcopy
import math
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_full_song_review import (
    _load_stitch_report,
    _verify_audio_record,
    _verify_stitch_audio,
    _write_json_atomic,
)
from ._separation_full_song_stitch import (
    REPORT_NAME as STITCH_REPORT_NAME,
    _FALSE_PERMISSIONS,
)


SCHEMA = "sunofriend.private-separation-full-song-alignment-result.v1"
STATUS = "complete_source_reconstruction_alignment_no_activation"
POLICY_ID = "source-reconstruction-spectral-clock-v1"
REPORT_NAME = "private-separation-full-song-alignment.json"

WINDOW_COUNT = 9
MAXIMUM_WINDOW_SECONDS = 8.0
MINIMUM_SONG_SECONDS = 6.0
FEATURE_FRAME_MILLISECONDS = 20.0
FEATURE_HOP_MILLISECONDS = 10.0
MAXIMUM_SEARCH_LAG_MILLISECONDS = 100.0
MAXIMUM_ACCEPTED_ABSOLUTE_LAG_MILLISECONDS = 20.0
MAXIMUM_ACCEPTED_LAG_SPREAD_MILLISECONDS = 20.0
MINIMUM_ACCEPTED_WINDOW_CORRELATION = 0.90
MINIMUM_ACTIVE_RMS_DBFS = -70.0
_BAND_EDGES_HZ = (0.0, 80.0, 160.0, 315.0, 630.0, 1_250.0, 2_500.0, 5_000.0, 10_000.0, 22_050.0)
_FALSE_EFFECTS = {
    "audio_created_or_mutated": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
}


def _measure_private_separation_full_song_alignment(
    package_dir: str | Path,
    *,
    out: str | Path,
) -> dict[str, Any]:
    """Write one hash-bound, path-free alignment report for a sealed stitch."""

    import numpy as np
    import soundfile

    package = Path(package_dir).expanduser().absolute()
    stitch_path = package / STITCH_REPORT_NAME
    stitch = _load_stitch_report(stitch_path)
    _verify_stitch_audio(package, stitch)
    output = Path(out).expanduser().absolute()
    if os.path.lexists(output):
        raise FileExistsError(f"private full-song alignment result exists: {output}")

    source_path = _verify_audio_record(
        package,
        stitch["artifacts"]["source"],
        label="private full-song alignment source",
        path_key="path",
    )
    reconstruction_path = _verify_audio_record(
        package,
        stitch["artifacts"]["reconstruction"],
        label="private full-song alignment reconstruction",
        path_key="path",
    )
    clock = stitch["clock"]
    _require_audio_clock(source_path, clock=clock, soundfile=soundfile)
    _require_audio_clock(reconstruction_path, clock=clock, soundfile=soundfile)
    duration_seconds = float(clock["duration_seconds"])
    if duration_seconds < MINIMUM_SONG_SECONDS:
        raise ValueError("private full-song alignment source is too short")

    sample_rate = int(clock["sample_rate"])
    window_seconds = min(MAXIMUM_WINDOW_SECONDS, duration_seconds / 12.0)
    window_frames = max(1, int(round(window_seconds * sample_rate)))
    starts = _window_start_frames(
        total_frames=int(clock["frames"]),
        window_frames=window_frames,
    )
    windows: list[dict[str, Any]] = []
    with soundfile.SoundFile(source_path) as source_handle, soundfile.SoundFile(
        reconstruction_path
    ) as reconstruction_handle:
        for index, start_frame in enumerate(starts, start=1):
            source_handle.seek(start_frame)
            reconstruction_handle.seek(start_frame)
            source = source_handle.read(window_frames, dtype="float64", always_2d=True)
            reconstruction = reconstruction_handle.read(
                window_frames,
                dtype="float64",
                always_2d=True,
            )
            measurement = _measure_window(
                source,
                reconstruction,
                sample_rate=sample_rate,
                np=np,
            )
            windows.append(
                {
                    "window_index": index,
                    "song_third": _song_third(index),
                    "start_frame": start_frame,
                    "end_frame": start_frame + window_frames,
                    "start_seconds": round(start_frame / sample_rate, 6),
                    "end_seconds": round(
                        (start_frame + window_frames) / sample_rate,
                        6,
                    ),
                    **measurement,
                }
            )

    eligible = [window for window in windows if window["eligible"]]
    lags = [float(window["best_lag_milliseconds"]) for window in eligible]
    correlations = [
        float(window["peak_normalized_correlation"]) for window in eligible
    ]
    coverage_complete = (
        len(eligible) == WINDOW_COUNT
        and {window["song_third"] for window in eligible}
        == {"early", "middle", "late"}
    )
    maximum_absolute_lag = max((abs(value) for value in lags), default=math.inf)
    lag_spread = max(lags) - min(lags) if lags else math.inf
    minimum_correlation = min(correlations, default=-1.0)
    gate_passed = (
        coverage_complete
        and maximum_absolute_lag
        <= MAXIMUM_ACCEPTED_ABSOLUTE_LAG_MILLISECONDS
        and lag_spread <= MAXIMUM_ACCEPTED_LAG_SPREAD_MILLISECONDS
        and minimum_correlation >= MINIMUM_ACCEPTED_WINDOW_CORRELATION
    )

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "stitch_report_sha256": _sha256(stitch_path),
            "stitch_document_sha256": stitch["document_sha256"],
            "source_audio_sha256": stitch["artifacts"]["source"]["sha256"],
            "reconstruction_audio_sha256": stitch["artifacts"]["reconstruction"][
                "sha256"
            ],
            "plan_document_sha256": stitch["bindings"]["plan_document_sha256"],
            "execution_state_sha256": stitch["bindings"]["execution_state_sha256"],
        },
        "clock": deepcopy(clock),
        "protocol": {
            "comparison": "canonical source versus diagnostic reconstruction",
            "feature": "log spectral-band energy",
            "window_count": WINDOW_COUNT,
            "window_seconds": round(window_frames / sample_rate, 6),
            "feature_frame_milliseconds": FEATURE_FRAME_MILLISECONDS,
            "feature_hop_milliseconds": FEATURE_HOP_MILLISECONDS,
            "maximum_search_lag_milliseconds": MAXIMUM_SEARCH_LAG_MILLISECONDS,
            "lag_sign": "positive means reconstruction is later than source",
            "source_and_reconstruction_gain_normalized_for_timing": True,
        },
        "thresholds": {
            "minimum_active_rms_dbfs": MINIMUM_ACTIVE_RMS_DBFS,
            "minimum_eligible_window_count": WINDOW_COUNT,
            "all_song_thirds_required": True,
            "maximum_absolute_lag_milliseconds": MAXIMUM_ACCEPTED_ABSOLUTE_LAG_MILLISECONDS,
            "maximum_lag_spread_milliseconds": MAXIMUM_ACCEPTED_LAG_SPREAD_MILLISECONDS,
            "minimum_window_normalized_correlation": MINIMUM_ACCEPTED_WINDOW_CORRELATION,
        },
        "windows": windows,
        "summary": {
            "eligible_window_count": len(eligible),
            "maximum_absolute_lag_milliseconds": _finite_or_none(
                maximum_absolute_lag
            ),
            "lag_spread_milliseconds": _finite_or_none(lag_spread),
            "minimum_window_normalized_correlation": round(
                minimum_correlation,
                6,
            ),
            "early_middle_late_coverage_complete": coverage_complete,
        },
        "readiness": {
            "exact_source_and_reconstruction_clock_verified": True,
            "source_to_reconstruction_alignment_verified": gate_passed,
            "drift_acceptance_complete": gate_passed,
            "alignment_gate_passed": gate_passed,
            "separator_accuracy_established": False,
            "publication_ready": False,
        },
        "interpretation": {
            "alignment_is_separator_quality": False,
            "reconstruction_similarity_is_role_fidelity": False,
            "gate_pass_is_separator_acceptance": False,
            "automatic_winner_selected": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": [
            "This report measures only source-to-reconstruction synchronization and drift.",
            "A reconstruction can remain synchronized while vocals or instrumental stems contain bleed, omissions or artefacts.",
            "Spectral correlation is used as clock evidence, not as a music-quality or separator-accuracy score.",
            "Human full-song and exact-boundary listening remain separate required evidence.",
        ],
    }
    result["document_sha256"] = _document_sha256(result)
    _write_json_atomic(output, result)
    return {**result, "report": str(output)}


def _window_start_frames(*, total_frames: int, window_frames: int) -> list[int]:
    available = total_frames - window_frames
    if available < 0:
        raise ValueError("private full-song alignment window exceeds source")
    if WINDOW_COUNT == 1:
        return [available // 2]
    return [
        int(round(available * index / (WINDOW_COUNT - 1)))
        for index in range(WINDOW_COUNT)
    ]


def _song_third(index: int) -> str:
    if index <= WINDOW_COUNT // 3:
        return "early"
    if index <= 2 * WINDOW_COUNT // 3:
        return "middle"
    return "late"


def _measure_window(
    source: Any,
    reconstruction: Any,
    *,
    sample_rate: int,
    np: Any,
) -> dict[str, Any]:
    if source.shape != reconstruction.shape or source.ndim != 2:
        raise ValueError("private full-song alignment window geometry differs")
    source_rms = float(np.sqrt(np.mean(np.square(source), dtype=np.float64)))
    reconstruction_rms = float(
        np.sqrt(np.mean(np.square(reconstruction), dtype=np.float64))
    )
    source_dbfs = _dbfs(source_rms)
    reconstruction_dbfs = _dbfs(reconstruction_rms)
    source_features = _spectral_features(source, sample_rate=sample_rate, np=np)
    reconstruction_features = _spectral_features(
        reconstruction,
        sample_rate=sample_rate,
        np=np,
    )
    maximum_lag_hops = int(
        round(MAXIMUM_SEARCH_LAG_MILLISECONDS / FEATURE_HOP_MILLISECONDS)
    )
    lag_hops, correlation = _best_feature_lag(
        source_features,
        reconstruction_features,
        maximum_lag_hops=maximum_lag_hops,
        np=np,
    )
    eligible = (
        source_dbfs >= MINIMUM_ACTIVE_RMS_DBFS
        and reconstruction_dbfs >= MINIMUM_ACTIVE_RMS_DBFS
        and correlation is not None
    )
    return {
        "source_rms_dbfs": round(source_dbfs, 6),
        "reconstruction_rms_dbfs": round(reconstruction_dbfs, 6),
        "eligible": eligible,
        "best_lag_milliseconds": (
            round(lag_hops * FEATURE_HOP_MILLISECONDS, 6)
            if correlation is not None
            else None
        ),
        "peak_normalized_correlation": (
            round(correlation, 6) if correlation is not None else None
        ),
    }


def _spectral_features(audio: Any, *, sample_rate: int, np: Any) -> Any:
    mono = np.mean(audio, axis=1, dtype=np.float64)
    frame_length = max(
        16,
        int(round(sample_rate * FEATURE_FRAME_MILLISECONDS / 1_000.0)),
    )
    hop_length = max(
        1,
        int(round(sample_rate * FEATURE_HOP_MILLISECONDS / 1_000.0)),
    )
    if mono.size < frame_length:
        raise ValueError("private full-song alignment window is too short")
    frame_count = 1 + (mono.size - frame_length) // hop_length
    frames = np.lib.stride_tricks.sliding_window_view(mono, frame_length)[
        ::hop_length
    ][:frame_count]
    spectrum = np.fft.rfft(frames * np.hanning(frame_length), axis=1)
    power = np.square(np.abs(spectrum), dtype=np.float64)
    frequencies = np.fft.rfftfreq(frame_length, d=1.0 / sample_rate)
    columns = []
    for lower, upper in zip(_BAND_EDGES_HZ[:-1], _BAND_EDGES_HZ[1:]):
        mask = (frequencies >= lower) & (frequencies < upper)
        columns.append(np.log1p(np.sum(power[:, mask], axis=1, dtype=np.float64)))
    features = np.stack(columns, axis=1)
    features -= np.mean(features, axis=0, keepdims=True)
    scale = np.std(features, axis=0, keepdims=True)
    return features / np.where(scale > 1.0e-12, scale, 1.0)


def _best_feature_lag(
    source: Any,
    reconstruction: Any,
    *,
    maximum_lag_hops: int,
    np: Any,
) -> tuple[int, float | None]:
    if source.shape != reconstruction.shape or source.ndim != 2:
        raise ValueError("private full-song alignment feature geometry differs")
    best_lag = 0
    best_correlation: float | None = None
    for lag in range(-maximum_lag_hops, maximum_lag_hops + 1):
        if lag < 0:
            left = source[-lag:]
            right = reconstruction[:lag]
        elif lag > 0:
            left = source[:-lag]
            right = reconstruction[lag:]
        else:
            left = source
            right = reconstruction
        if left.shape[0] < 3:
            continue
        numerator = float(np.sum(left * right, dtype=np.float64))
        denominator = float(
            np.sqrt(
                np.sum(np.square(left), dtype=np.float64)
                * np.sum(np.square(right), dtype=np.float64)
            )
        )
        if denominator <= 1.0e-12:
            continue
        correlation = numerator / denominator
        if best_correlation is None or correlation > best_correlation:
            best_lag = lag
            best_correlation = correlation
    return best_lag, best_correlation


def _require_audio_clock(path: Path, *, clock: Mapping[str, Any], soundfile: Any) -> None:
    info = soundfile.info(path)
    if (
        info.format != "WAV"
        or info.subtype != "PCM_24"
        or info.samplerate != clock.get("sample_rate")
        or info.channels != clock.get("channels")
        or info.frames != clock.get("frames")
    ):
        raise ValueError("private full-song alignment audio clock differs")


def _dbfs(rms: float) -> float:
    return 20.0 * math.log10(max(rms, 1.0e-12))


def _finite_or_none(value: float) -> float | None:
    return round(value, 6) if math.isfinite(value) else None


__all__: tuple[str, ...] = ()
