"""Transparent, source-referenced balancing for Workbench MIDI auditions.

This module deliberately operates on rendered neutral MIDI audio.  It never
changes MIDI notes, velocities, timing, source stems, selections, or review
state.  The result is an audition aid and a reproducible GarageBand fader
recipe, not a release master.
"""

from __future__ import annotations

import json
import math
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Mapping, Sequence

from .role_semantics import is_drum_role
from .workbench_balanced_contract import BALANCED_MIX_CONTRACT


BALANCED_ARRANGEMENT_SCHEMA = BALANCED_MIX_CONTRACT.arrangement_schema
BALANCED_MIX_REPORT_SCHEMA = BALANCED_MIX_CONTRACT.mix_report_schema
BALANCED_MIX_POLICY = BALANCED_MIX_CONTRACT.policy

_WINDOW_SECONDS = BALANCED_MIX_CONTRACT.window_seconds
_ABSOLUTE_GATE_DBFS = BALANCED_MIX_CONTRACT.absolute_gate_dbfs
_RELATIVE_GATE_DB = BALANCED_MIX_CONTRACT.relative_gate_db
_OVERLAP_RELATIVE_GATE_DB = BALANCED_MIX_CONTRACT.overlap_relative_gate_db
_LANE_MIN_GAIN_DB, _LANE_MAX_GAIN_DB = (
    BALANCED_MIX_CONTRACT.source_match_gain_db
)
_DRUM_BUS_MAXIMUM_ATTENUATION_DB = (
    BALANCED_MIX_CONTRACT.maximum_drum_bus_attenuation_db
)
_DRUM_VS_NON_DRUM_TARGET_DB = (
    BALANCED_MIX_CONTRACT.drum_overlap_median_target_db
)
_DRUM_P95_ALLOWANCE_DB = BALANCED_MIX_CONTRACT.drum_overlap_p95_maximum_db
_AUDITION_TARGET_GATED_RMS_DBFS = (
    BALANCED_MIX_CONTRACT.audition_target_gated_rms_dbfs
)
_SAMPLE_PEAK_CEILING_DBFS = BALANCED_MIX_CONTRACT.sample_peak_ceiling_dbfs
_MAXIMUM_NORMALISATION_BOOST_DB = (
    BALANCED_MIX_CONTRACT.maximum_normalisation_boost_db
)
_NORMALISATION_TARGET_TOLERANCE_DB = (
    BALANCED_MIX_CONTRACT.normalisation_target_tolerance_db
)
_MAXIMUM_LANES = BALANCED_MIX_CONTRACT.maximum_lanes
_MAXIMUM_SECONDS = BALANCED_MIX_CONTRACT.maximum_seconds


def build_balanced_midi_audition(
    lanes: Sequence[Mapping[str, Any]],
    *,
    output_path: str | Path,
    report_path: str | Path,
    recipe_path: str | Path,
    output_frames: int | None = None,
) -> dict[str, Any]:
    """Build one deterministic gain-only MIDI mix and path-free report.

    Each lane must identify one verified source stem and one verified neutral
    MIDI preview.  Source audio is measured but never mixed into the result.
    """

    if not lanes:
        raise ValueError("balanced MIDI audition requires at least one selected lane")
    if len(lanes) > _MAXIMUM_LANES:
        raise ValueError(
            "balanced MIDI audition supports at most "
            f"{_MAXIMUM_LANES} selected lanes"
        )

    np, soundfile = _audio_modules()
    prepared = [dict(lane) for lane in lanes]
    output = Path(output_path).expanduser().resolve()
    report = Path(report_path).expanduser().resolve()
    recipe = Path(recipe_path).expanduser().resolve()
    temporary_mix = output.with_name(f".{output.name}.float-tmp.wav")
    destination_paths = {output, report, recipe, temporary_mix}
    if len(destination_paths) != 4:
        raise ValueError(
            "balanced audition output, temporary mix, report and recipe must differ"
        )
    input_paths = {
        Path(str(lane.get(key, ""))).expanduser().resolve()
        for lane in prepared
        for key in ("source_path", "preview_path")
    }
    if destination_paths & input_paths:
        raise ValueError("balanced audition outputs must not overwrite input audio")
    source_metrics: dict[str, dict[str, Any]] = {}
    preview_metrics: dict[str, dict[str, Any]] = {}
    preview_infos: dict[str, dict[str, int | float]] = {}
    preview_geometry: tuple[int, int] | None = None

    for lane in prepared:
        _require_lane_fields(lane)
        preview_digest = str(lane["preview_sha256"])
        if preview_digest not in preview_infos:
            preview_infos[preview_digest] = _audio_info(
                soundfile,
                Path(str(lane["preview_path"])),
                label="neutral MIDI preview",
            )
        preview_info = preview_infos[preview_digest]
        geometry = (
            int(preview_info["sample_rate"]),
            int(preview_info["channels"]),
        )
        if preview_geometry is None:
            preview_geometry = geometry
        elif preview_geometry != geometry:
            raise ValueError(
                "all neutral MIDI previews must share one sample rate and channel count"
            )
        if geometry[1] not in {1, 2}:
            raise ValueError("neutral MIDI previews must be mono or stereo")

    assert preview_geometry is not None
    sample_rate, channels = preview_geometry
    maximum_preview_frames = max(
        int(preview_infos[str(lane["preview_sha256"])]["frames"])
        for lane in prepared
    )
    selected_output_frames = (
        maximum_preview_frames if output_frames is None else int(output_frames)
    )
    if selected_output_frames <= 0:
        raise ValueError("balanced MIDI audition output must contain audio frames")
    if selected_output_frames > sample_rate * _MAXIMUM_SECONDS:
        raise ValueError(
            "balanced MIDI audition supports songs up to "
            f"{_MAXIMUM_SECONDS // 60} minutes"
        )

    # Balance evidence is scoped to exactly the audio that will be heard.  A
    # renderer tail or stray transcription after the source-song horizon must
    # not change an audible lane's gain or trigger a false full-scale failure.
    for lane in prepared:
        source_digest = str(lane["source_sha256"])
        preview_digest = str(lane["preview_sha256"])
        if source_digest not in source_metrics:
            source_metrics[source_digest] = _measure_audio(
                np,
                soundfile,
                Path(str(lane["source_path"])),
                label="source stem",
                horizon_frames=selected_output_frames,
                horizon_sample_rate=sample_rate,
            )
        if preview_digest not in preview_metrics:
            preview_metrics[preview_digest] = _measure_audio(
                np,
                soundfile,
                Path(str(lane["preview_path"])),
                label="neutral MIDI preview",
                horizon_frames=selected_output_frames,
                horizon_sample_rate=sample_rate,
            )
        preview = preview_metrics[preview_digest]
        if preview["gated_rms_dbfs"] is None:
            raise ValueError("a selected neutral MIDI preview is silent")
        if int(preview["full_scale_sample_count"]) != 0:
            raise ValueError(
                "a selected neutral MIDI preview contains full-scale samples; "
                "create a lower-gain neutral render before balancing"
            )

    source_groups: dict[str, list[dict[str, Any]]] = {}
    for lane in prepared:
        source_digest = str(lane["source_sha256"])
        source_groups.setdefault(source_digest, []).append(lane)
        source = source_metrics[source_digest]
        preview = preview_metrics[str(lane["preview_sha256"])]
        fallback_reason = None
        source_level = source["gated_rms_dbfs"]
        preview_level = preview["gated_rms_dbfs"]
        assert preview_level is not None
        if source_level is None:
            provisional_gain_db = (
                -6.0 if is_drum_role(lane["role"]) else 0.0
            )
            fallback_reason = (
                "source stem had no measurable active blocks; conservative role "
                "fallback used"
            )
        else:
            provisional_gain_db = float(source_level) - float(preview_level)
        lane["provisional_source_match_gain_db"] = provisional_gain_db
        lane["fallback_reason"] = fallback_reason

    public_source_groups: list[dict[str, Any]] = []
    for source_digest in sorted(source_groups):
        group_lanes = source_groups[source_digest]
        source = source_metrics[source_digest]
        before_calibration = _measure_lane_mix(
            np,
            soundfile,
            group_lanes,
            frames=selected_output_frames,
            sample_rate=sample_rate,
            channels=channels,
            gain_key="provisional_source_match_gain_db",
        )
        measured_group_level = before_calibration["gated_rms_dbfs"]
        if measured_group_level is None:
            raise ValueError(
                "selected neutral MIDI previews cancel to silence within one "
                "source group"
            )
        source_level = source["gated_rms_dbfs"]
        if source_level is None:
            target_group_level = max(
                float(
                    preview_metrics[str(lane["preview_sha256"])][
                        "gated_rms_dbfs"
                    ]
                )
                + float(lane["provisional_source_match_gain_db"])
                for lane in group_lanes
            )
            target_reason = (
                "loudest conservatively adjusted selected preview because the "
                "source stem had no measurable active blocks"
            )
        else:
            target_group_level = float(source_level)
            target_reason = "measured source-stem gated RMS"
        group_calibration_gain_db = (
            target_group_level - float(measured_group_level)
        )
        for lane in group_lanes:
            raw_gain_db = (
                float(lane["provisional_source_match_gain_db"])
                + group_calibration_gain_db
            )
            matched_gain_db = _clamp(
                raw_gain_db,
                _LANE_MIN_GAIN_DB,
                _LANE_MAX_GAIN_DB,
            )
            lane["source_duplicate_count"] = len(group_lanes)
            lane["source_group_calibration_gain_db"] = (
                group_calibration_gain_db
            )
            lane["raw_source_match_gain_db"] = raw_gain_db
            lane["source_match_gain_db"] = matched_gain_db
            lane["source_match_clamped"] = not math.isclose(
                raw_gain_db, matched_gain_db, abs_tol=1e-9
            )
        after_calibration = _measure_lane_mix(
            np,
            soundfile,
            group_lanes,
            frames=selected_output_frames,
            sample_rate=sample_rate,
            channels=channels,
            gain_key="source_match_gain_db",
        )
        achieved_group_level = after_calibration["gated_rms_dbfs"]
        public_source_groups.append(
            {
                "source_sha256": source_digest,
                "selected_lane_count": len(group_lanes),
                "target_gated_rms_dbfs": _rounded(target_group_level),
                "target_reason": target_reason,
                "before_calibration": _public_metrics(before_calibration),
                "calibration_gain_db": _rounded(group_calibration_gain_db),
                "after_calibration": _public_metrics(after_calibration),
                "residual_level_error_db": (
                    None
                    if achieved_group_level is None
                    else _rounded(
                        float(achieved_group_level) - target_group_level
                    )
                ),
                "clamped_lane_count": sum(
                    bool(lane["source_match_clamped"])
                    for lane in group_lanes
                ),
            }
        )

    drum_metrics, non_drum_metrics, overlap_metrics = _measure_mixed_groups(
        np,
        soundfile,
        prepared,
        frames=selected_output_frames,
        sample_rate=sample_rate,
        channels=channels,
        gain_key="source_match_gain_db",
    )
    # As with output normalisation, use the values published in the receipt
    # for policy decisions so an exact −18 dB boundary cannot straddle opposite
    # sides after report rounding.
    public_overlap_metrics = _public_overlap_metrics(overlap_metrics)
    required_drum_bus_gain_db = _required_drum_bus_guard(
        public_overlap_metrics
    )
    drum_bus_gain_db = _drum_bus_guard(public_overlap_metrics)
    for lane in prepared:
        lane["drum_bus_gain_db"] = (
            drum_bus_gain_db if is_drum_role(lane["role"]) else 0.0
        )
        lane["audition_lane_gain_db"] = (
            float(lane["source_match_gain_db"])
            + float(lane["drum_bus_gain_db"])
        )
    (
        after_guard_drum_metrics,
        after_guard_non_drum_metrics,
        _recomputed_after_guard_overlap_metrics,
    ) = (
        _measure_mixed_groups(
            np,
            soundfile,
            prepared,
            frames=selected_output_frames,
            sample_rate=sample_rate,
            channels=channels,
            gain_key="audition_lane_gain_db",
        )
    )
    after_guard_overlap_metrics = _shift_overlap_metrics(
        public_overlap_metrics,
        gain_db=drum_bus_gain_db,
    )
    public_after_guard_overlap_metrics = _public_overlap_metrics(
        after_guard_overlap_metrics
    )
    drum_guard_status = _drum_guard_status(
        public_after_guard_overlap_metrics
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    recipe.parent.mkdir(parents=True, exist_ok=True)
    try:
        pre_master = _write_mix(
            np,
            soundfile,
            prepared,
            output_path=temporary_mix,
            frames=selected_output_frames,
            sample_rate=sample_rate,
            channels=channels,
            gain_key="audition_lane_gain_db",
            subtype="FLOAT",
        )
        if pre_master["gated_rms_dbfs"] is None or pre_master["sample_peak_dbfs"] is None:
            raise ValueError("balanced MIDI audition produced no audible audio")
        # Gain decisions use the same six-decimal values that the path-free
        # report publishes. This keeps the builder and cache validator on one
        # deterministic side of exact policy boundaries such as the +12 dB
        # maximum boost.
        public_pre_master = _public_metrics(pre_master)
        raw_normalisation_gain_db = (
            _AUDITION_TARGET_GATED_RMS_DBFS
            - float(public_pre_master["gated_rms_dbfs"])
        )
        requested_normalisation_gain_db = min(
            raw_normalisation_gain_db,
            _MAXIMUM_NORMALISATION_BOOST_DB,
        )
        peak_room_db = _SAMPLE_PEAK_CEILING_DBFS - float(
            public_pre_master["sample_peak_dbfs"]
        )
        master_gain_db = min(requested_normalisation_gain_db, peak_room_db)
        post_master = _apply_gain(
            np,
            soundfile,
            temporary_mix,
            output,
            gain_db=master_gain_db,
            subtype="PCM_24",
        )
    finally:
        temporary_mix.unlink(missing_ok=True)

    if (
        post_master["sample_peak_dbfs"] is not None
        and float(post_master["sample_peak_dbfs"])
        > _SAMPLE_PEAK_CEILING_DBFS + 0.001
    ):
        output.unlink(missing_ok=True)
        raise RuntimeError("balanced audition sample-peak protection failed")
    if int(post_master["full_scale_sample_count"]) != 0:
        output.unlink(missing_ok=True)
        raise RuntimeError("balanced audition contains full-scale samples")
    post_master_level = post_master["gated_rms_dbfs"]
    post_master_target_error_db = (
        None
        if post_master_level is None
        else float(post_master_level) - _AUDITION_TARGET_GATED_RMS_DBFS
    )
    normalisation_target_met = (
        post_master_target_error_db is not None
        and abs(post_master_target_error_db)
        <= _NORMALISATION_TARGET_TOLERANCE_DB
    )
    normalisation_limit = None
    if requested_normalisation_gain_db < raw_normalisation_gain_db:
        normalisation_limit = "maximum_positive_boost"
    if master_gain_db < requested_normalisation_gain_db:
        normalisation_limit = "sample_peak_ceiling"

    public_lanes = []
    for lane in prepared:
        public_lane = {
            "track_id": str(lane["track_id"]),
            "stem_id": str(lane["stem_id"]),
            "candidate_id": str(lane["candidate_id"]),
            "role": str(lane["role"]),
            "decision": str(lane["decision"]),
            "selection_index": int(lane["selection_index"]),
            "garageband_pack_archive_member": str(
                lane["garageband_pack_archive_member"]
            ),
            "source_sha256": str(lane["source_sha256"]),
            "source_bytes": int(lane["source_bytes"]),
            "source_midi_sha256": str(lane["source_midi_sha256"]),
            "preview_sha256": str(lane["preview_sha256"]),
            "preview_bytes": int(lane["preview_bytes"]),
            "neutral_preview_cache_key": str(
                lane["neutral_preview_cache_key"]
            ),
            "source_metrics": _public_metrics(
                source_metrics[str(lane["source_sha256"])]
            ),
            "preview_metrics": _public_metrics(
                preview_metrics[str(lane["preview_sha256"])]
            ),
            "source_duplicate_count": int(lane["source_duplicate_count"]),
            "provisional_source_match_gain_db": _rounded(
                lane["provisional_source_match_gain_db"]
            ),
            "source_group_calibration_gain_db": _rounded(
                lane["source_group_calibration_gain_db"]
            ),
            "raw_source_match_gain_db": _rounded(
                lane["raw_source_match_gain_db"]
            ),
            "source_match_gain_db": _rounded(lane["source_match_gain_db"]),
            "source_match_clamped": bool(lane["source_match_clamped"]),
            "fallback_reason": lane["fallback_reason"],
            "drum_bus_gain_db": _rounded(lane["drum_bus_gain_db"]),
            "garageband_track_trim_db": _rounded(
                lane["audition_lane_gain_db"]
            ),
        }
        starter_sound = lane.get("starter_sound")
        if isinstance(starter_sound, Mapping):
            public_lane["starter_sound"] = {
                key: starter_sound.get(key)
                for key in (
                    "family",
                    "name",
                    "program_zero_based",
                    "general_midi_number",
                    "midi_channel_one_based",
                    "combined_midi_channel_one_based",
                    "assignment_status",
                    "selection_basis",
                    "physical_instrument_claim",
                    "factory_patch_selected",
                    "native_garageband_patch_embedded",
                )
            }
            public_lane["starter_midi_archive_member"] = str(
                lane.get("starter_midi_archive_member") or ""
            )
            public_lane["starter_preview_archive_member"] = str(
                lane.get("starter_preview_archive_member") or ""
            )
        public_lanes.append(public_lane)

    result = {
        "schema": BALANCED_MIX_REPORT_SCHEMA,
        "policy": BALANCED_MIX_POLICY,
        "label": BALANCED_MIX_CONTRACT.label,
        "path_free_report": True,
        "mastered": False,
        "mastering_boundary": BALANCED_MIX_CONTRACT.mastering_boundary,
        "sample_rate": sample_rate,
        "channels": channels,
        "frames": selected_output_frames,
        "duration_seconds": _rounded(selected_output_frames / sample_rate),
        "measurement": BALANCED_MIX_CONTRACT.measurement_document(),
        "source_groups": public_source_groups,
        "limits": BALANCED_MIX_CONTRACT.limits_document(),
        "lanes": public_lanes,
        "drum_bus": {
            "before_guard": _public_metrics(drum_metrics),
            "non_drum_reference": _public_metrics(non_drum_metrics),
            "before_guard_overlap": public_overlap_metrics,
            "required_guard_gain_db": _rounded(required_drum_bus_gain_db),
            "guard_gain_db": _rounded(drum_bus_gain_db),
            "guard_clamped": required_drum_bus_gain_db
            < _DRUM_BUS_MAXIMUM_ATTENUATION_DB,
            "after_guard": _public_metrics(after_guard_drum_metrics),
            "after_guard_non_drum_reference": _public_metrics(
                after_guard_non_drum_metrics
            ),
            "after_guard_overlap": public_after_guard_overlap_metrics,
            **drum_guard_status,
            "policy": BALANCED_MIX_CONTRACT.drum_guard_policy,
        },
        "output": {
            "pre_master": public_pre_master,
            "raw_normalisation_gain_db": _rounded(
                raw_normalisation_gain_db
            ),
            "requested_normalisation_gain_db": _rounded(
                requested_normalisation_gain_db
            ),
            "available_sample_peak_room_db": _rounded(peak_room_db),
            "master_output_gain_db": _rounded(master_gain_db),
            "post_master": _public_metrics(post_master),
            "post_master_target_error_db": (
                None
                if post_master_target_error_db is None
                else _rounded(post_master_target_error_db)
            ),
            "normalisation_target_met": normalisation_target_met,
            "normalisation_limit": normalisation_limit,
        },
        "processing": {
            "per_lane_gain": True,
            "summed_source_group_calibration": True,
            "drum_bus_gain": not math.isclose(
                drum_bus_gain_db, 0.0, abs_tol=1e-9
            ),
            "global_output_gain": not math.isclose(
                master_gain_db, 0.0, abs_tol=1e-9
            ),
            "sample_peak_protection": True,
            "compression": False,
            "limiter": False,
            "equalisation": False,
            "saturation": False,
            "reverb": False,
            "chorus": False,
            "stereo_widening": False,
        },
        "effects": {
            "source_audio_mutated": False,
            "midi_mutated": False,
            "selection_changed": False,
            "feedback_recorded": False,
            "event_appended": False,
            "automatic_selection": False,
            "automatic_ranking": False,
            "default_selection_changed": False,
        },
    }
    report.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    recipe.write_text(garageband_mix_recipe(result), encoding="utf-8")
    return result


def _audio_info(
    soundfile: Any,
    path: Path,
    *,
    label: str,
) -> dict[str, int | float]:
    try:
        info = soundfile.info(str(path))
    except Exception as exc:
        raise ValueError(f"{label} is not readable audio") from exc
    sample_rate = int(info.samplerate)
    channels = int(info.channels)
    frames = int(info.frames)
    full_scale_threshold = _full_scale_threshold(str(info.subtype))
    if not 8_000 <= sample_rate <= 96_000:
        raise ValueError(f"{label} sample rate must be between 8 and 96 kHz")
    if channels not in {1, 2}:
        raise ValueError(f"{label} must be mono or stereo")
    if frames <= 0:
        raise ValueError(f"{label} must contain at least one audio frame")
    if frames > sample_rate * _MAXIMUM_SECONDS:
        raise ValueError(f"{label} must be no longer than 20 minutes")
    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "frames": frames,
        "full_scale_threshold": full_scale_threshold,
    }


def _measure_audio(
    np: Any,
    soundfile: Any,
    path: Path,
    *,
    label: str,
    horizon_frames: int | None = None,
    horizon_sample_rate: int | None = None,
) -> dict[str, Any]:
    info = _audio_info(soundfile, path, label=label)
    sample_rate = int(info["sample_rate"])
    channels = int(info["channels"])
    file_frames = int(info["frames"])
    full_scale_threshold = float(info["full_scale_threshold"])
    if (horizon_frames is None) != (horizon_sample_rate is None):
        raise ValueError("audio measurement horizon requires frames and sample rate")
    measured_frames = file_frames
    if horizon_frames is not None and horizon_sample_rate is not None:
        if horizon_frames <= 0 or horizon_sample_rate <= 0:
            raise ValueError("audio measurement horizon must be positive")
        scaled_horizon_frames = (
            int(horizon_frames) * sample_rate + int(horizon_sample_rate) - 1
        ) // int(horizon_sample_rate)
        measured_frames = min(file_frames, scaled_horizon_frames)
    block_frames = max(1, int(round(sample_rate * _WINDOW_SECONDS)))
    block_rms: list[float] = []
    sample_peak = 0.0
    full_scale_count = 0
    try:
        for values in soundfile.blocks(
            str(path),
            blocksize=block_frames,
            stop=measured_frames,
            dtype="float64",
            always_2d=True,
        ):
            if values.size == 0:
                continue
            if not bool(np.isfinite(values).all()):
                raise ValueError(f"{label} contains non-finite samples")
            absolute = np.abs(values)
            sample_peak = max(sample_peak, float(np.max(absolute)))
            full_scale_count += int(
                np.count_nonzero(absolute >= full_scale_threshold)
            )
            analysis_values = _padded_analysis_block(
                np,
                values,
                block_frames=block_frames,
            )
            block_rms.append(
                float(np.sqrt(np.mean(np.square(analysis_values))))
            )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"{label} changed or became unreadable") from exc
    return _summarize_metrics(
        np,
        block_rms,
        sample_peak=sample_peak,
        full_scale_count=full_scale_count,
        sample_rate=sample_rate,
        channels=channels,
        frames=measured_frames,
    )


def measure_balanced_audio(path: str | Path) -> dict[str, Any]:
    """Measure one rendered balance with the report's exact public policy."""

    np, soundfile = _audio_modules()
    return _public_metrics(
        _measure_audio(
            np,
            soundfile,
            Path(path),
            label="balanced audition output",
        )
    )


def _measure_mixed_groups(
    np: Any,
    soundfile: Any,
    lanes: Sequence[Mapping[str, Any]],
    *,
    frames: int,
    sample_rate: int,
    channels: int,
    gain_key: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    block_frames = max(1, int(round(sample_rate * _WINDOW_SECONDS)))
    drum_blocks: list[float] = []
    non_drum_blocks: list[float] = []
    drum_peak = 0.0
    non_drum_peak = 0.0
    drum_full_scale = 0
    non_drum_full_scale = 0
    with ExitStack() as stack:
        handles = [
            stack.enter_context(
                soundfile.SoundFile(str(lane["preview_path"]), mode="r")
            )
            for lane in lanes
        ]
        position = 0
        while position < frames:
            count = min(block_frames, frames - position)
            drum = np.zeros((count, channels), dtype=np.float64)
            non_drum = np.zeros((count, channels), dtype=np.float64)
            for lane, handle in zip(lanes, handles):
                values = handle.read(count, dtype="float64", always_2d=True)
                values = _padded_channels(np, values, count=count, channels=channels)
                values *= _db_to_linear(float(lane[gain_key]))
                if is_drum_role(lane["role"]):
                    drum += values
                else:
                    non_drum += values
            (
                drum_peak,
                drum_full_scale,
            ) = _append_mix_block_metrics(
                np,
                _padded_analysis_block(
                    np,
                    drum,
                    block_frames=block_frames,
                ),
                drum_blocks,
                drum_peak,
                drum_full_scale,
            )
            (
                non_drum_peak,
                non_drum_full_scale,
            ) = _append_mix_block_metrics(
                np,
                _padded_analysis_block(
                    np,
                    non_drum,
                    block_frames=block_frames,
                ),
                non_drum_blocks,
                non_drum_peak,
                non_drum_full_scale,
            )
            position += count
    drum_metrics = _summarize_metrics(
        np,
        drum_blocks,
        sample_peak=drum_peak,
        full_scale_count=drum_full_scale,
        sample_rate=sample_rate,
        channels=channels,
        frames=frames,
    )
    non_drum_metrics = _summarize_metrics(
            np,
            non_drum_blocks,
            sample_peak=non_drum_peak,
            full_scale_count=non_drum_full_scale,
            sample_rate=sample_rate,
            channels=channels,
            frames=frames,
        )
    return (
        drum_metrics,
        non_drum_metrics,
        _summarize_overlap_metrics(np, drum_blocks, non_drum_blocks),
    )


def _measure_lane_mix(
    np: Any,
    soundfile: Any,
    lanes: Sequence[Mapping[str, Any]],
    *,
    frames: int,
    sample_rate: int,
    channels: int,
    gain_key: str,
) -> dict[str, Any]:
    block_frames = max(1, int(round(sample_rate * _WINDOW_SECONDS)))
    block_rms: list[float] = []
    sample_peak = 0.0
    full_scale_count = 0
    with ExitStack() as stack:
        handles = [
            stack.enter_context(
                soundfile.SoundFile(str(lane["preview_path"]), mode="r")
            )
            for lane in lanes
        ]
        position = 0
        while position < frames:
            count = min(block_frames, frames - position)
            mixed = np.zeros((count, channels), dtype=np.float64)
            for lane, handle in zip(lanes, handles):
                values = handle.read(count, dtype="float64", always_2d=True)
                values = _padded_channels(
                    np,
                    values,
                    count=count,
                    channels=channels,
                )
                mixed += values * _db_to_linear(float(lane[gain_key]))
            sample_peak, full_scale_count = _append_mix_block_metrics(
                np,
                _padded_analysis_block(
                    np,
                    mixed,
                    block_frames=block_frames,
                ),
                block_rms,
                sample_peak,
                full_scale_count,
            )
            position += count
    return _summarize_metrics(
        np,
        block_rms,
        sample_peak=sample_peak,
        full_scale_count=full_scale_count,
        sample_rate=sample_rate,
        channels=channels,
        frames=frames,
    )


def _write_mix(
    np: Any,
    soundfile: Any,
    lanes: Sequence[Mapping[str, Any]],
    *,
    output_path: Path,
    frames: int,
    sample_rate: int,
    channels: int,
    gain_key: str,
    subtype: str,
) -> dict[str, Any]:
    block_frames = max(1, int(round(sample_rate * _WINDOW_SECONDS)))
    block_rms: list[float] = []
    sample_peak = 0.0
    full_scale_count = 0
    with ExitStack() as stack:
        handles = [
            stack.enter_context(
                soundfile.SoundFile(str(lane["preview_path"]), mode="r")
            )
            for lane in lanes
        ]
        destination = stack.enter_context(
            soundfile.SoundFile(
                str(output_path),
                mode="w",
                samplerate=sample_rate,
                channels=channels,
                format="WAV",
                subtype=subtype,
            )
        )
        position = 0
        while position < frames:
            count = min(block_frames, frames - position)
            mixed = np.zeros((count, channels), dtype=np.float64)
            for lane, handle in zip(lanes, handles):
                values = handle.read(count, dtype="float64", always_2d=True)
                values = _padded_channels(np, values, count=count, channels=channels)
                mixed += values * _db_to_linear(float(lane[gain_key]))
            destination.write(mixed)
            sample_peak, full_scale_count = _append_mix_block_metrics(
                np,
                _padded_analysis_block(
                    np,
                    mixed,
                    block_frames=block_frames,
                ),
                block_rms,
                sample_peak,
                full_scale_count,
            )
            position += count
    return _summarize_metrics(
        np,
        block_rms,
        sample_peak=sample_peak,
        full_scale_count=full_scale_count,
        sample_rate=sample_rate,
        channels=channels,
        frames=frames,
    )


def _apply_gain(
    np: Any,
    soundfile: Any,
    source_path: Path,
    output_path: Path,
    *,
    gain_db: float,
    subtype: str,
) -> dict[str, Any]:
    with soundfile.SoundFile(str(source_path), mode="r") as source:
        sample_rate = int(source.samplerate)
        channels = int(source.channels)
        block_frames = max(1, int(round(sample_rate * _WINDOW_SECONDS)))
        gain = _db_to_linear(gain_db)
        with soundfile.SoundFile(
            str(output_path),
            mode="w",
            samplerate=sample_rate,
            channels=channels,
            format="WAV",
            subtype=subtype,
        ) as destination:
            while True:
                values = source.read(
                    block_frames,
                    dtype="float64",
                    always_2d=True,
                )
                if values.size == 0:
                    break
                values *= gain
                destination.write(values)
    return _measure_audio(
        np,
        soundfile,
        output_path,
        label="balanced audition output",
    )


def _summarize_metrics(
    np: Any,
    block_rms: Sequence[float],
    *,
    sample_peak: float,
    full_scale_count: int,
    sample_rate: int,
    channels: int,
    frames: int,
) -> dict[str, Any]:
    positive = [value for value in block_rms if value > 0.0]
    block_db = [20.0 * math.log10(value) for value in positive]
    active: list[float] = []
    if block_db:
        threshold = max(_ABSOLUTE_GATE_DBFS, max(block_db) - _RELATIVE_GATE_DB)
        active = [value for value in block_db if value >= threshold]
    return {
        "sample_rate": int(sample_rate),
        "channels": int(channels),
        "frames": int(frames),
        "duration_seconds": frames / sample_rate if sample_rate else 0.0,
        "block_count": len(block_rms),
        "active_block_count": len(active),
        "gated_rms_dbfs": float(np.median(active)) if active else None,
        "active_block_p95_dbfs": (
            float(np.percentile(active, 95.0)) if active else None
        ),
        "sample_peak_dbfs": (
            20.0 * math.log10(sample_peak) if sample_peak > 0.0 else None
        ),
        "full_scale_sample_count": int(full_scale_count),
    }


def _append_mix_block_metrics(
    np: Any,
    values: Any,
    block_rms: list[float],
    sample_peak: float,
    full_scale_count: int,
) -> tuple[float, int]:
    if values.size == 0:
        block_rms.append(0.0)
        return sample_peak, full_scale_count
    absolute = np.abs(values)
    sample_peak = max(sample_peak, float(np.max(absolute)))
    full_scale_count += int(np.count_nonzero(absolute >= 1.0))
    block_rms.append(float(np.sqrt(np.mean(np.square(values)))))
    return sample_peak, full_scale_count


def _drum_bus_guard(overlap_metrics: Mapping[str, Any]) -> float:
    required = _required_drum_bus_guard(overlap_metrics)
    return _clamp(
        required,
        _DRUM_BUS_MAXIMUM_ATTENUATION_DB,
        0.0,
    )


def _required_drum_bus_guard(overlap_metrics: Mapping[str, Any]) -> float:
    median_difference = overlap_metrics.get("drum_vs_non_drum_median_db")
    p95_difference = overlap_metrics.get("drum_vs_non_drum_p95_db")
    if median_difference is None or p95_difference is None:
        return 0.0
    median_guard = _DRUM_VS_NON_DRUM_TARGET_DB - float(
        median_difference
    )
    p95_guard = _DRUM_P95_ALLOWANCE_DB - float(p95_difference)
    return min(0.0, median_guard, p95_guard)


def _summarize_overlap_metrics(
    np: Any,
    drum_blocks: Sequence[float],
    non_drum_blocks: Sequence[float],
) -> dict[str, Any]:
    if len(drum_blocks) != len(non_drum_blocks):
        raise ValueError("drum and non-drum block measurements are misaligned")
    drum_db = [
        20.0 * math.log10(value) if value > 0.0 else None
        for value in drum_blocks
    ]
    non_drum_db = [
        20.0 * math.log10(value) if value > 0.0 else None
        for value in non_drum_blocks
    ]
    audible_drum = [value for value in drum_db if value is not None]
    audible_non_drum = [value for value in non_drum_db if value is not None]
    drum_gate = (
        max(_ABSOLUTE_GATE_DBFS, max(audible_drum) - _OVERLAP_RELATIVE_GATE_DB)
        if audible_drum
        else None
    )
    non_drum_gate = (
        max(
            _ABSOLUTE_GATE_DBFS,
            max(audible_non_drum) - _OVERLAP_RELATIVE_GATE_DB,
        )
        if audible_non_drum
        else None
    )
    differences: list[float] = []
    if drum_gate is not None and non_drum_gate is not None:
        for drum_value, non_drum_value in zip(drum_db, non_drum_db):
            if (
                drum_value is not None
                and non_drum_value is not None
                and drum_value >= drum_gate
                and non_drum_value >= non_drum_gate
            ):
                differences.append(float(drum_value) - float(non_drum_value))
    return {
        "block_count": len(drum_blocks),
        "overlap_block_count": len(differences),
        "drum_gate_dbfs": drum_gate,
        "non_drum_gate_dbfs": non_drum_gate,
        "drum_vs_non_drum_median_db": (
            float(np.median(differences)) if differences else None
        ),
        "drum_vs_non_drum_p95_db": (
            float(np.percentile(differences, 95.0)) if differences else None
        ),
    }


def _shift_overlap_metrics(
    metrics: Mapping[str, Any],
    *,
    gain_db: float,
) -> dict[str, Any]:
    """Apply drum gain to values from the exact pre-guard overlap cohort.

    The drum and non-drum gates remain the thresholds that selected this fixed
    cohort. Only the measured level differences move after the drum gain. This
    also preserves the documented −70 dBFS absolute gate floor.
    """

    output = dict(metrics)
    for key in (
        "drum_vs_non_drum_median_db",
        "drum_vs_non_drum_p95_db",
    ):
        value = output.get(key)
        if value is not None:
            output[key] = float(value) + float(gain_db)
    return output


def _drum_guard_status(overlap_metrics: Mapping[str, Any]) -> dict[str, Any]:
    median_difference = overlap_metrics.get("drum_vs_non_drum_median_db")
    p95_difference = overlap_metrics.get("drum_vs_non_drum_p95_db")
    applicable = median_difference is not None and p95_difference is not None
    if not applicable:
        return {
            "target_applicable": False,
            "overlap_median_target_met": None,
            "overlap_p95_target_met": None,
            "target_met": None,
        }
    median_met = float(median_difference) <= (
        _DRUM_VS_NON_DRUM_TARGET_DB + 1e-6
    )
    p95_met = float(p95_difference) <= (_DRUM_P95_ALLOWANCE_DB + 1e-6)
    return {
        "target_applicable": True,
        "overlap_median_target_met": median_met,
        "overlap_p95_target_met": p95_met,
        "target_met": median_met and p95_met,
    }


def _padded_channels(
    np: Any,
    values: Any,
    *,
    count: int,
    channels: int,
) -> Any:
    if values.shape[1] == 1 and channels == 2:
        values = np.repeat(values, 2, axis=1)
    if values.shape[1] != channels:
        raise ValueError("neutral MIDI preview channel count changed")
    if values.shape[0] == count:
        return values
    output = np.zeros((count, channels), dtype=np.float64)
    output[: values.shape[0], :] = values
    return output


def _padded_analysis_block(
    np: Any,
    values: Any,
    *,
    block_frames: int,
) -> Any:
    """Pad only the analysis view of a final partial 400 ms block.

    The real output and declared frame horizon remain unchanged. Padding the
    measurement window with silence prevents a one-sample tail from being
    treated as though it filled an entire analysis block.
    """

    if values.shape[0] > block_frames:
        raise ValueError("audio analysis block exceeds the policy window")
    if values.shape[0] == block_frames:
        return values
    output = np.zeros((block_frames, values.shape[1]), dtype=np.float64)
    output[: values.shape[0], :] = values
    return output


def _require_lane_fields(lane: Mapping[str, Any]) -> None:
    required = {
        "track_id",
        "stem_id",
        "candidate_id",
        "role",
        "decision",
        "selection_index",
        "garageband_pack_archive_member",
        "source_path",
        "source_sha256",
        "source_bytes",
        "source_midi_sha256",
        "preview_path",
        "preview_sha256",
        "preview_bytes",
        "neutral_preview_cache_key",
    }
    missing = sorted(required - set(lane))
    if missing:
        raise ValueError("balanced MIDI lane is missing " + ", ".join(missing))


def _audio_modules() -> tuple[Any, Any]:
    try:
        import numpy as np
        import soundfile
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "balanced MIDI audition requires numpy and soundfile; install "
            "Sunofriend with the convert extra"
        ) from exc
    return np, soundfile


def _db_to_linear(value: float) -> float:
    return 10.0 ** (value / 20.0)


def _full_scale_threshold(subtype: str) -> float:
    integer_bits = {
        "PCM_S8": 8,
        "PCM_16": 16,
        "PCM_24": 24,
        "PCM_32": 32,
    }.get(subtype)
    if integer_bits is None:
        return 1.0
    return ((1 << (integer_bits - 1)) - 1) / float(1 << (integer_bits - 1))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def _rounded(value: Any) -> float:
    return round(float(value), 6)


def _public_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: (
            None
            if value is None
            else int(value)
            if key
            in {
                "sample_rate",
                "channels",
                "frames",
                "block_count",
                "active_block_count",
                "full_scale_sample_count",
            }
            else _rounded(value)
        )
        for key, value in metrics.items()
    }


def _public_overlap_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: (
            None
            if value is None
            else int(value)
            if key in {"block_count", "overlap_block_count"}
            else _rounded(value)
        )
        for key, value in metrics.items()
    }


def garageband_mix_recipe(report: Mapping[str, Any]) -> str:
    """Return the deterministic GarageBand fader recipe for one mix report."""

    has_starter_sounds = any(
        isinstance(lane.get("starter_sound"), Mapping)
        for lane in report["lanes"]
    )
    lines = [
        "Sunofriend balanced selected-MIDI audition",
        "==========================================",
        "",
        "This is a reproducible starting recipe, not a release master.",
        "Use the same MIDI files and comparable patches, then enter these relative",
        "track trims in GarageBand. Different GarageBand patches can still need",
        "small ear-led adjustments because their loudness differs from the neutral",
        "SoundFont used for this audition.",
        *(
            [
                "The automatic starter sounds below are embedded in separately",
                "labelled MIDI proxies and remain editable, unreviewed choices.",
            ]
            if has_starter_sounds
            else []
        ),
        "",
        "Track trims",
        "-----------",
        "",
    ]
    for lane in report["lanes"]:
        starter = lane.get("starter_sound")
        starter_text = ""
        if isinstance(starter, Mapping):
            if starter.get("family") == "general-midi-drum-kit":
                label = "Standard Drum Kit on MIDI channel 10"
            else:
                label = (
                    f"GM {int(starter['general_midi_number'])} "
                    f"{starter['name']}"
                )
            starter_text = (
                f" · automatic starter {label} · "
                f"`{lane['starter_midi_archive_member']}` · "
                f"preview `{lane['starter_preview_archive_member']}`"
            )
        lines.append(
            f"- Track {int(lane['selection_index']):02d} · "
            f"`{lane['garageband_pack_archive_member']}` · "
            f"{lane['role']} · candidate {lane['candidate_id']} · "
            f"{float(lane['garageband_track_trim_db']):+.2f} dB"
            f"{starter_text}"
        )
    lines.extend(
        [
            "",
            "Output",
            "------",
            "",
            (
                "- Audition output gain: "
                f"{float(report['output']['master_output_gain_db']):+.2f} dB"
            ),
            "- Sample-peak ceiling: -1.00 dBFS (not a true-peak claim)",
            "- Compression, limiter, EQ, saturation, reverb and widening: off",
            "",
            "Keep the original selected MIDI unchanged. Finish patch choice, dynamics,",
            "EQ, compression, automation and final loudness/mastering in GarageBand.",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "BALANCED_ARRANGEMENT_SCHEMA",
    "BALANCED_MIX_POLICY",
    "BALANCED_MIX_REPORT_SCHEMA",
    "build_balanced_midi_audition",
    "garageband_mix_recipe",
    "is_drum_role",
    "measure_balanced_audio",
]
