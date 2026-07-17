"""Advisory sustain-loop evidence for source-derived sample instruments.

Loop points are deliberately never applied here.  The analyser ranks possible
forward-loop boundaries using both waveform continuity and short-time spectral
continuity, writes click-revealing auditions, and leaves the SoundFont/SFZ
unchanged until a later explicit listening workflow exists.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any, Sequence


SAMPLE_LOOP_SUGGESTIONS_SCHEMA = "sunofriend.sample-loop-suggestions.v1"
DRUM_KINDS = {"kick", "snare", "hat", "cymbals", "toms", "other_kit", "drums"}
MINIMUM_SAMPLE_SECONDS = 0.65
MINIMUM_LOOP_SECONDS = 0.24
BOUNDARY_WINDOW_SECONDS = 0.025
MAXIMUM_SUGGESTIONS = 3


def analyze_sample_loop_suggestions(
    sample_root: str | Path,
    samples: Sequence[dict[str, Any]],
    *,
    kind: str,
) -> dict[str, Any]:
    """Rank possible loop points without changing any sampler mapping."""

    import numpy as np
    import soundfile

    root = Path(sample_root)
    normalized_kind = str(kind).strip().lower()
    rows: list[dict[str, Any]] = []
    audition_dir = root / "loop-auditions"
    for sample in samples:
        relative = Path(str(sample["file"]))
        source = root / relative
        if not source.is_file():
            raise ValueError(f"Sample loop source not found: {source}")
        values, sample_rate = soundfile.read(source, dtype="float32", always_2d=True)
        audio = np.asarray(values[:, 0], dtype=np.float32)
        audio = np.nan_to_num(audio, copy=False)
        base = {
            "file": str(relative),
            "pitch": int(sample["pitch"]),
            "sample_rate": int(sample_rate),
            "frame_count": int(len(audio)),
            "duration_seconds": _round(len(audio) / max(1, sample_rate), 6),
            "review_required": False,
            "status": "not-applicable" if normalized_kind in DRUM_KINDS else None,
            "reason": (
                "Percussive one-shots are intentionally not sustain-looped."
                if normalized_kind in DRUM_KINDS
                else None
            ),
            "candidate_count_evaluated": 0,
            "suggestions": [],
        }
        if normalized_kind in DRUM_KINDS:
            rows.append(base)
            continue
        analysis = _analyse_one(audio, int(sample_rate))
        base.update(analysis)
        for rank, candidate in enumerate(base["suggestions"], 1):
            audition_dir.mkdir(exist_ok=True)
            audition = audition_dir / (f"{relative.stem}-candidate-{rank:02d}.wav")
            _write_loop_audition(
                audition,
                audio,
                int(sample_rate),
                int(candidate["loop_start_frame"]),
                int(candidate["loop_end_frame"]),
            )
            candidate["audition"] = str(Path("loop-auditions") / audition.name)
            candidate["audition_sha256"] = _sha256(audition)
        rows.append(base)

    suggestions = [
        candidate for row in rows for candidate in row.get("suggestions", [])
    ]
    candidate_samples = sum(bool(row.get("suggestions")) for row in rows)
    return {
        "schema": SAMPLE_LOOP_SUGGESTIONS_SCHEMA,
        "operation": "sample-loop-suggestions",
        "status": ("not-applicable" if normalized_kind in DRUM_KINDS else "complete"),
        "advisory_only": True,
        "review_required": bool(suggestions),
        "kind": normalized_kind,
        "method": {
            "minimum_sample_seconds": MINIMUM_SAMPLE_SECONDS,
            "minimum_loop_seconds": MINIMUM_LOOP_SECONDS,
            "boundary_window_seconds": BOUNDARY_WINDOW_SECONDS,
            "maximum_suggestions_per_sample": MAXIMUM_SUGGESTIONS,
            "candidate_region": (
                "after the attack and before the release; start/end grids are "
                "evaluated deterministically"
            ),
            "waveform_continuity": (
                "sample jump, slope jump, boundary-window normalised RMSE and "
                "RMS-level difference"
            ),
            "representation_continuity": (
                "Hann-window log-spectrum cosine distance, spectral-centroid "
                "difference and within-loop RMS stability"
            ),
            "ranking": "lower weighted continuity score ranks first",
            "audition": (
                "attack followed by four raw forward-loop repeats; no crossfade "
                "is added so discontinuities remain audible"
            ),
        },
        "summary": {
            "sample_count": len(rows),
            "candidate_sample_count": candidate_samples,
            "suggested_loop_count": len(suggestions),
            "not_applicable_sample_count": sum(
                row["status"] == "not-applicable" for row in rows
            ),
            "too_short_sample_count": sum(row["status"] == "too-short" for row in rows),
            "weak_candidate_sample_count": sum(
                row["status"] == "weak-candidate" for row in rows
            ),
        },
        "samples": rows,
        "effects": {
            "sample_audio_files_modified": 0,
            "soundfont_zones_changed": 0,
            "sfz_regions_changed": 0,
            "looped_zones_added": 0,
            "midi_notes_changed": 0,
        },
        "warnings": [
            "These are boundary suggestions, not accepted loop points; the generated SF2 and SFZ remain unlooped.",
            "A low discontinuity score cannot detect musical phrase motion, vibrato intent, bleed or baked effects; listen to every audition.",
            "The audition repeats the raw loop without a crossfade so clicks, level steps and timbre changes are not hidden.",
        ],
    }


def sample_loop_suggestions_svg(report: dict[str, Any]) -> str:
    """Render the best suggested boundary per sample as an audit timeline."""

    samples = list(report.get("samples", []))
    width = 1200
    row_height = 72
    top = 78
    height = max(220, top + row_height * max(1, len(samples)) + 65)
    left, right = 220, 45
    plot_width = width - left - right
    chunks = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#101820"/>',
        '<text x="45" y="34" fill="#ffffff" font-family="sans-serif" font-size="20">Advisory sample-loop boundaries</text>',
        '<text x="45" y="57" fill="#b8c4ce" font-family="sans-serif" font-size="12">Blue = sample duration; green = best candidate; no sampler zone is changed</text>',
    ]
    if not samples:
        chunks.append(
            '<text x="45" y="120" fill="#ffd166" font-family="sans-serif" font-size="14">No samples</text>'
        )
    for index, sample in enumerate(samples):
        y = top + index * row_height
        duration = max(float(sample.get("duration_seconds", 0.0)), 1e-9)
        label = f"MIDI {sample.get('pitch')} · {Path(str(sample.get('file'))).name}"
        chunks.extend(
            [
                f'<text x="45" y="{y + 18}" fill="#eef4f8" font-family="sans-serif" font-size="12">{_xml(label)}</text>',
                f'<rect x="{left}" y="{y + 4}" width="{plot_width}" height="18" rx="5" fill="#275d82"/>',
            ]
        )
        suggestions = list(sample.get("suggestions", []))
        if suggestions:
            best = suggestions[0]
            start = left + plot_width * float(best["loop_start_seconds"]) / duration
            end = left + plot_width * float(best["loop_end_seconds"]) / duration
            chunks.append(
                f'<rect x="{start:.2f}" y="{y + 4}" width="{max(2.0, end - start):.2f}" height="18" rx="4" fill="#51cf66"/>'
            )
            detail = (
                f"{best['loop_start_seconds']:.3f}–{best['loop_end_seconds']:.3f}s; "
                f"score {best['continuity_score']:.4f}; review required"
            )
        else:
            detail = f"{sample.get('status')}: {sample.get('reason') or 'no candidate'}"
        chunks.append(
            f'<text x="{left}" y="{y + 45}" fill="#b8c4ce" font-family="sans-serif" font-size="11">{_xml(detail)}</text>'
        )
    chunks.append("</svg>")
    return "\n".join(chunks) + "\n"


def _analyse_one(audio: Any, sample_rate: int) -> dict[str, Any]:
    import numpy as np

    frame_count = len(audio)
    duration = frame_count / max(1, sample_rate)
    peak = float(np.max(np.abs(audio))) if frame_count else 0.0
    if duration < MINIMUM_SAMPLE_SECONDS:
        return {
            "review_required": False,
            "status": "too-short",
            "reason": (
                f"Sample duration {duration:.3f}s is below the "
                f"{MINIMUM_SAMPLE_SECONDS:.2f}s advisory minimum."
            ),
            "candidate_count_evaluated": 0,
            "suggestions": [],
        }
    if peak <= 1e-7:
        return {
            "review_required": False,
            "status": "silent",
            "reason": "Sample has no usable amplitude.",
            "candidate_count_evaluated": 0,
            "suggestions": [],
        }

    window = max(64, int(round(BOUNDARY_WINDOW_SECONDS * sample_rate)))
    minimum_loop = max(window * 2, int(round(MINIMUM_LOOP_SECONDS * sample_rate)))
    start_low = max(window, int(round(frame_count * 0.20)))
    start_high = min(
        int(round(frame_count * 0.48)), frame_count - minimum_loop - window
    )
    end_low = max(int(round(frame_count * 0.58)), start_low + minimum_loop)
    end_high = min(frame_count - window, int(round(frame_count * 0.90)))
    if start_high <= start_low or end_high <= end_low:
        return {
            "review_required": False,
            "status": "insufficient-sustain",
            "reason": "The post-attack/pre-release region cannot hold a useful loop.",
            "candidate_count_evaluated": 0,
            "suggestions": [],
        }

    start_positions = _grid(start_low, start_high, 28)
    end_positions = _grid(end_low, end_high, 32)
    start_features = {
        position: _boundary_feature(audio[position : position + window], sample_rate)
        for position in start_positions
    }
    end_features = {
        position: _boundary_feature(audio[position - window : position], sample_rate)
        for position in end_positions
    }
    evaluated: list[dict[str, Any]] = []
    for start in start_positions:
        for end in end_positions:
            if end - start < minimum_loop:
                continue
            candidate = _score_boundary(
                audio,
                sample_rate,
                start,
                end,
                peak,
                start_features[start],
                end_features[end],
            )
            evaluated.append(candidate)
    evaluated.sort(
        key=lambda row: (
            float(row["continuity_score"]),
            -int(row["loop_length_frames"]),
            int(row["loop_start_frame"]),
            int(row["loop_end_frame"]),
        )
    )
    selected: list[dict[str, Any]] = []
    separation = max(1, int(round(0.02 * sample_rate)))
    for candidate in evaluated:
        if any(
            abs(int(candidate["loop_start_frame"]) - int(row["loop_start_frame"]))
            < separation
            and abs(int(candidate["loop_end_frame"]) - int(row["loop_end_frame"]))
            < separation
            for row in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) >= MAXIMUM_SUGGESTIONS:
            break
    if not selected:
        return {
            "review_required": False,
            "status": "insufficient-sustain",
            "reason": "No valid deterministic boundary pair was found.",
            "candidate_count_evaluated": len(evaluated),
            "suggestions": [],
        }
    best = float(selected[0]["continuity_score"])
    return {
        "review_required": True,
        "status": "candidate" if best <= 0.55 else "weak-candidate",
        "reason": (
            "Candidate boundaries require listening before any sampler loop is enabled."
        ),
        "candidate_count_evaluated": len(evaluated),
        "suggestions": selected,
    }


def _boundary_feature(values: Any, sample_rate: int) -> dict[str, Any]:
    import numpy as np

    window = np.hanning(len(values)).astype(np.float64)
    audio = np.asarray(values, dtype=np.float64)
    spectrum = np.log1p(np.abs(np.fft.rfft(audio * window)))
    norm = float(np.linalg.norm(spectrum))
    frequencies = np.fft.rfftfreq(len(audio), 1.0 / sample_rate)
    magnitude = np.expm1(spectrum)
    total = float(np.sum(magnitude))
    centroid = float(np.sum(frequencies * magnitude) / total) if total > 1e-12 else 0.0
    return {
        "audio": audio,
        "spectrum": spectrum,
        "spectrum_norm": norm,
        "rms": math.sqrt(float(np.mean(audio**2))),
        "centroid": centroid,
    }


def _score_boundary(
    audio: Any,
    sample_rate: int,
    start: int,
    end: int,
    peak: float,
    start_feature: dict[str, Any],
    end_feature: dict[str, Any],
) -> dict[str, Any]:
    import numpy as np

    start_audio = start_feature["audio"]
    end_audio = end_feature["audio"]
    local_scale = max(
        float(start_feature["rms"]), float(end_feature["rms"]), peak * 0.02, 1e-8
    )
    sample_jump = min(2.0, abs(float(audio[start]) - float(audio[end - 1])) / peak)
    start_slope = float(audio[min(start + 1, len(audio) - 1)] - audio[start])
    end_slope = float(audio[end - 1] - audio[max(0, end - 2)])
    slope_jump = min(2.0, abs(start_slope - end_slope) / peak)
    segment_nrmse = min(
        2.0,
        math.sqrt(float(np.mean((start_audio - end_audio) ** 2))) / local_scale,
    )
    start_rms = max(float(start_feature["rms"]), 1e-10)
    end_rms = max(float(end_feature["rms"]), 1e-10)
    rms_delta_db = abs(20.0 * math.log10(start_rms / end_rms))
    spectrum_denominator = max(
        float(start_feature["spectrum_norm"]) * float(end_feature["spectrum_norm"]),
        1e-12,
    )
    spectral_cosine = float(
        np.dot(start_feature["spectrum"], end_feature["spectrum"])
        / spectrum_denominator
    )
    spectral_distance = min(1.0, max(0.0, 1.0 - spectral_cosine))
    centroid_scale = max(
        float(start_feature["centroid"]), float(end_feature["centroid"]), 20.0
    )
    centroid_delta = min(
        1.0,
        abs(float(start_feature["centroid"]) - float(end_feature["centroid"]))
        / centroid_scale,
    )
    loop = np.asarray(audio[start:end], dtype=np.float64)
    chunks = [chunk for chunk in np.array_split(loop, 4) if len(chunk)]
    chunk_rms = np.asarray(
        [math.sqrt(float(np.mean(chunk**2))) for chunk in chunks], dtype=np.float64
    )
    stability = min(
        1.0,
        float(np.std(chunk_rms) / max(float(np.mean(chunk_rms)), 1e-10)),
    )
    score = (
        0.16 * min(1.0, sample_jump)
        + 0.10 * min(1.0, slope_jump)
        + 0.24 * min(1.0, segment_nrmse / 2.0)
        + 0.12 * min(1.0, rms_delta_db / 12.0)
        + 0.22 * spectral_distance
        + 0.08 * centroid_delta
        + 0.08 * stability
    )
    return {
        "loop_start_frame": int(start),
        "loop_end_frame": int(end),
        "loop_length_frames": int(end - start),
        "loop_start_seconds": _round(start / sample_rate, 6),
        "loop_end_seconds": _round(end / sample_rate, 6),
        "loop_length_seconds": _round((end - start) / sample_rate, 6),
        "continuity_score": _round(score, 6),
        "waveform_continuity": {
            "sample_jump_ratio": _round(sample_jump, 6),
            "slope_jump_ratio": _round(slope_jump, 6),
            "boundary_segment_nrmse": _round(segment_nrmse, 6),
            "rms_delta_db": _round(rms_delta_db, 6),
        },
        "representation_continuity": {
            "log_spectrum_cosine_distance": _round(spectral_distance, 6),
            "spectral_centroid_delta_ratio": _round(centroid_delta, 6),
            "within_loop_rms_cv": _round(stability, 6),
        },
        "selection_effect": "none",
    }


def _write_loop_audition(
    path: Path,
    audio: Any,
    sample_rate: int,
    start: int,
    end: int,
) -> None:
    import numpy as np
    import soundfile

    attack = np.asarray(audio[:start], dtype=np.float32)
    loop = np.asarray(audio[start:end], dtype=np.float32)
    audition = np.concatenate([attack, loop, loop, loop, loop])
    maximum = int(round(6.0 * sample_rate))
    audition = audition[:maximum]
    fade = min(len(audition), max(1, int(round(0.04 * sample_rate))))
    audition[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(path, audition, sample_rate, subtype="PCM_24")


def _grid(low: int, high: int, count: int) -> list[int]:
    import numpy as np

    return sorted({int(round(value)) for value in np.linspace(low, high, count)})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _round(value: float, digits: int) -> float:
    rounded = round(float(value), digits)
    return 0.0 if rounded == 0 else rounded


def _xml(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


__all__ = [
    "SAMPLE_LOOP_SUGGESTIONS_SCHEMA",
    "analyze_sample_loop_suggestions",
    "sample_loop_suggestions_svg",
]
