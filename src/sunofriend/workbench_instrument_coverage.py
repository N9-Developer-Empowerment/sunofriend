"""Deterministic complete-patch coverage probes for keys MIDI.

The probe is deliberately separate from the musical A/B review.  It asks a
smaller, objective question first: does each complete General MIDI patch
produce a measurable response for one representative observed velocity in
every used channel/pitch/velocity-bucket zone?  Probe MIDI is synthetic and
private; the later listening review still uses the selected MIDI byte-for-byte
except for its audited Program Change proxy.
"""

from __future__ import annotations

import math
import statistics
import struct
from collections import defaultdict
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .clip import read_midi_clips


KEYS_COVERAGE_SCHEMA = "sunofriend.workbench-instrument-review.keys-coverage.v1"
KEYS_COVERAGE_POLICY = "deterministic-observed-pitch-velocity-bucket-probe-v1"
KEYS_COVERAGE_CLAIM = "representative-used-pitch-velocity-bucket-coverage"

MAXIMUM_COVERAGE_ZONES = 512
MAXIMUM_COVERAGE_SECONDS = 180.0
MAXIMUM_COVERAGE_AUDIO_BYTES = 256 * 1024 * 1024
PROBE_BPM = 120.0
PROBE_LEAD_IN_SECONDS = 0.05
PROBE_NOTE_SECONDS = 0.20
PROBE_SLOT_SECONDS = 0.35
MINIMUM_COVERAGE_RMS_DBFS = -72.0
MINIMUM_COVERAGE_PEAK_DBFS = -60.0
# A dry SoundFont voice may keep a release tail after Note Off/CC120.  The
# representative onset must still rise measurably above that local tail, while
# a constant drone or background floor must fail.  GeneralUser GS Electric
# Piano 2's weakest observed Pupsies zone rises by about 3.89 dB, so 3 dB keeps
# a measured margin without pretending the pre-guard is silent.
MINIMUM_ACTIVE_ABOVE_GUARD_DB = 3.0
MAXIMUM_NORMALIZED_RMS_DEFICIT_DB = 24.0

VELOCITY_BUCKETS = (
    {"id": "soft", "minimum": 1, "maximum": 42},
    {"id": "medium", "minimum": 43, "maximum": 84},
    {"id": "strong", "minimum": 85, "maximum": 127},
)
_BASE_ZONE_FIELDS = {
    "index",
    "channel",
    "pitch",
    "velocity_bucket",
    "tested_velocity",
    "observed_velocity_minimum",
    "observed_velocity_maximum",
    "observed_note_count",
    "slot_start_seconds",
    "start_seconds",
    "note_end_seconds",
    "window_end_seconds",
}


class InstrumentCoverageError(ValueError):
    """A complete patch cannot safely cover the selected keys performance."""


def prepare_keys_coverage_preflight(
    *,
    selected_midi: str | Path,
    work_directory: str | Path,
    programs: Mapping[str, Mapping[str, Any]],
    maximum_note_ons: int,
    sample_rate: int,
    soundfont_path: str | Path,
    renderer_path: str | Path,
    render: Callable[..., Any],
) -> dict[str, Any]:
    """Plan, render and fail closed for each private complete-patch identity."""

    if set(programs) != {"control", "challenger"}:
        raise InstrumentCoverageError(
            "keys coverage requires exactly control and challenger patches"
        )
    program_values = {
        identity: int(programs[identity]["program"])
        for identity in ("control", "challenger")
    }
    if len(set(program_values.values())) != 2:
        raise InstrumentCoverageError(
            "keys coverage patches must use distinct programs"
        )
    plan = plan_keys_coverage(
        selected_midi,
        maximum_note_ons=maximum_note_ons,
    )
    root = Path(work_directory)
    identities: dict[str, Any] = {}
    for identity in ("control", "challenger"):
        probe = root / f"{identity}-keys-coverage.mid"
        rendered = root / f"{identity}-keys-coverage-raw.wav"
        try:
            write_keys_coverage_probe(
                plan,
                probe,
                program=program_values[identity],
            )
            render(
                probe,
                rendered,
                sample_rate=int(sample_rate),
                gain=0.7,
                soundfont_path=Path(soundfont_path),
                fluidsynth_path=str(renderer_path),
            )
            rendered.chmod(0o600)
            report = measure_keys_coverage_audio(
                plan,
                rendered,
                expected_sample_rate=int(sample_rate),
            )
            require_keys_coverage(report)
            identities[identity] = {
                "report": report,
                "probe_path": probe,
            }
        finally:
            rendered.unlink(missing_ok=True)
    return {
        **keys_coverage_contract(required=True),
        "status": "passed",
        "functional_status": "passed",
        "quality_status": "review_required",
        "zone_count": plan["zone_count"],
        "duration_seconds": plan["duration_seconds"],
        "private_identities": identities,
    }


def keys_coverage_contract(*, required: bool) -> dict[str, Any]:
    """Return the path-free public preflight contract."""

    return {
        "schema": KEYS_COVERAGE_SCHEMA,
        "required": bool(required),
        "status": "required" if required else "not_required",
        "policy": KEYS_COVERAGE_POLICY,
        "claim": KEYS_COVERAGE_CLAIM,
        "velocity_buckets": [dict(bucket) for bucket in VELOCITY_BUCKETS],
        "zone_definition": (
            "one zone per observed channel, pitch and velocity bucket; the "
            "minimum velocity actually observed in that zone is tested"
        ),
        "functional_status": "required" if required else "not_required",
        "quality_status": "review_required",
        "safe_pass_text": (
            "Both complete keyboard proxies produced measurable responses for "
            "each representative pitch and used velocity bucket tested from "
            "this selected MIDI. Tone, musical fit, chord clarity, every exact "
            "velocity, pitch correctness and GarageBand equivalence still "
            "require listening."
        ),
        "non_claims": [
            "not every exact used velocity is tested",
            "pitch correctness and octave mapping are not proven",
            "polyphonic chord and per-voice clarity are not proven",
            "tone, musical fit and GarageBand equivalence are not proven",
        ],
        "limits": {
            "maximum_zones": MAXIMUM_COVERAGE_ZONES,
            "maximum_probe_seconds": MAXIMUM_COVERAGE_SECONDS,
            "probe_note_seconds": PROBE_NOTE_SECONDS,
            "probe_slot_seconds": PROBE_SLOT_SECONDS,
        },
        "thresholds": {
            "both_absolute_gates_required": True,
            "minimum_rms_dbfs": MINIMUM_COVERAGE_RMS_DBFS,
            "minimum_peak_dbfs": MINIMUM_COVERAGE_PEAK_DBFS,
            "minimum_active_above_pre_guard_db": (MINIMUM_ACTIVE_ABOVE_GUARD_DB),
            "maximum_velocity_normalized_rms_deficit_db": (
                MAXIMUM_NORMALIZED_RMS_DEFICIT_DB
            ),
            "singleton_channel_bucket_uses_absolute_gates_only": True,
        },
        "actual_review_midi_changed": False,
    }


def plan_keys_coverage(
    selected_midi: str | Path,
    *,
    maximum_note_ons: int,
) -> dict[str, Any]:
    """Plan representative probes from observed selected-MIDI velocities."""

    observed: dict[tuple[int, int, str], list[int]] = defaultdict(list)
    clips = read_midi_clips(selected_midi, max_notes=maximum_note_ons)
    for clip in clips:
        channel = int(clip.instrument.channel)
        if channel == 9:
            raise InstrumentCoverageError(
                "keys coverage does not accept drum-channel notes"
            )
        for note in clip.notes:
            velocity = int(note.velocity)
            observed[
                (channel, int(note.pitch), _velocity_bucket(velocity)["id"])
            ].append(velocity)
    if not observed:
        raise InstrumentCoverageError(
            "keys coverage needs at least one playable selected-MIDI note"
        )
    if len(observed) > MAXIMUM_COVERAGE_ZONES:
        raise InstrumentCoverageError(
            "keys coverage exceeds the safe 512-zone probe limit"
        )

    bucket_rank = {
        str(bucket["id"]): index for index, bucket in enumerate(VELOCITY_BUCKETS)
    }
    zones: list[dict[str, Any]] = []
    for index, key in enumerate(
        sorted(
            observed,
            key=lambda row: (row[0], row[1], bucket_rank[row[2]]),
        )
    ):
        channel, pitch, bucket_id = key
        velocities = observed[key]
        start = PROBE_LEAD_IN_SECONDS + index * PROBE_SLOT_SECONDS
        zones.append(
            {
                "index": index,
                "channel": channel,
                "pitch": pitch,
                "velocity_bucket": bucket_id,
                "tested_velocity": min(velocities),
                "observed_velocity_minimum": min(velocities),
                "observed_velocity_maximum": max(velocities),
                "observed_note_count": len(velocities),
                "slot_start_seconds": round(index * PROBE_SLOT_SECONDS, 9),
                "start_seconds": round(start, 9),
                "note_end_seconds": round(start + PROBE_NOTE_SECONDS, 9),
                "window_end_seconds": round((index + 1) * PROBE_SLOT_SECONDS, 9),
            }
        )
    duration = len(zones) * PROBE_SLOT_SECONDS
    if duration > MAXIMUM_COVERAGE_SECONDS + 1e-9:
        raise InstrumentCoverageError(
            "keys coverage exceeds the safe 180-second probe limit"
        )
    return {
        **keys_coverage_contract(required=True),
        "status": "planned",
        "zone_count": len(zones),
        "duration_seconds": round(duration, 9),
        "probe_bpm": PROBE_BPM,
        "zones": zones,
    }


def write_keys_coverage_probe(
    plan: Mapping[str, Any],
    destination: str | Path,
    *,
    program: int,
) -> None:
    """Write isolated notes with explicit all-sound/all-notes-off guards."""

    content = _keys_coverage_probe_bytes(plan, program=program)
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    output.chmod(0o600)


def _keys_coverage_probe_bytes(
    plan: Mapping[str, Any],
    *,
    program: int,
) -> bytes:
    """Build the canonical probe bytes used for creation and restart checks."""

    checked_program = int(program)
    if not 0 <= checked_program <= 127:
        raise InstrumentCoverageError("coverage probe program must be 0–127")
    zones = _checked_plan_zones(plan)
    ticks_per_beat = 480
    ticks_per_second = ticks_per_beat * PROBE_BPM / 60.0
    channels = sorted({int(row["channel"]) for row in zones})
    events: list[tuple[int, int, bytes]] = []
    title = b"Sunofriend keys functional coverage"
    events.append((0, 0, b"\xff\x03" + _variable_length(len(title)) + title))
    for channel in channels:
        events.append((0, 1, bytes((0xC0 | channel, checked_program))))
    for row in zones:
        channel = int(row["channel"])
        slot_tick = int(round(float(row["slot_start_seconds"]) * ticks_per_second))
        start_tick = int(round(float(row["start_seconds"]) * ticks_per_second))
        end_tick = int(round(float(row["note_end_seconds"]) * ticks_per_second))
        controller = 0xB0 | channel
        events.extend(
            [
                (slot_tick, 2, bytes((controller, 120, 0))),
                (slot_tick, 3, bytes((controller, 123, 0))),
                (
                    start_tick,
                    4,
                    bytes(
                        (
                            0x90 | channel,
                            int(row["pitch"]),
                            int(row["tested_velocity"]),
                        )
                    ),
                ),
                (
                    end_tick,
                    5,
                    bytes((0x80 | channel, int(row["pitch"]), 0)),
                ),
                (end_tick, 6, bytes((controller, 120, 0))),
                (end_tick, 7, bytes((controller, 123, 0))),
            ]
        )
    events.sort(key=lambda row: (row[0], row[1], row[2]))
    track = bytearray()
    previous_tick = 0
    for tick, _priority, payload in events:
        track.extend(_variable_length(tick - previous_tick))
        track.extend(payload)
        previous_tick = tick
    final_tick = int(round(float(plan["duration_seconds"]) * ticks_per_second))
    track.extend(_variable_length(final_tick - previous_tick))
    track.extend(b"\xff\x2f\x00")
    tempo = int(round(60_000_000 / PROBE_BPM))
    tempo_track = b"\x00\xff\x51\x03" + tempo.to_bytes(3, "big") + b"\x00\xff\x2f\x00"
    return (
        b"MThd"
        + struct.pack(">IHHH", 6, 1, 2, ticks_per_beat)
        + b"MTrk"
        + struct.pack(">I", len(tempo_track))
        + tempo_track
        + b"MTrk"
        + struct.pack(">I", len(track))
        + bytes(track)
    )


def measure_keys_coverage_audio(
    plan: Mapping[str, Any],
    rendered_audio: str | Path,
    *,
    expected_sample_rate: int,
) -> dict[str, Any]:
    """Measure absolute audibility and within-dynamic-family consistency."""

    import numpy as np
    import soundfile

    path = Path(rendered_audio)
    if not path.is_file() or path.is_symlink():
        raise InstrumentCoverageError("keys coverage render is unavailable")
    if path.stat().st_size > MAXIMUM_COVERAGE_AUDIO_BYTES:
        raise InstrumentCoverageError(
            "keys coverage render exceeds the safe audio-size limit"
        )
    try:
        with soundfile.SoundFile(path) as source:
            if int(source.samplerate) != int(expected_sample_rate):
                raise InstrumentCoverageError(
                    "keys coverage render sample rate changed"
                )
            if not 1 <= int(source.channels) <= 8:
                raise InstrumentCoverageError(
                    "keys coverage render channel count is invalid"
                )
            audio = source.read(dtype="float32", always_2d=True)
    except InstrumentCoverageError:
        raise
    except Exception as exc:
        raise InstrumentCoverageError("keys coverage render is unreadable") from exc

    zones = _checked_plan_zones(plan)
    preliminary: list[dict[str, Any]] = []
    for row in zones:
        guard_start_frame = int(
            round(float(row["slot_start_seconds"]) * expected_sample_rate)
        )
        start_frame = int(round(float(row["start_seconds"]) * expected_sample_rate))
        end_frame = int(round(float(row["note_end_seconds"]) * expected_sample_rate))
        guard = _audio_window(
            audio,
            guard_start_frame,
            start_frame,
            channels=int(audio.shape[1]),
        )
        window = _audio_window(
            audio,
            start_frame,
            end_frame,
            channels=int(audio.shape[1]),
        )
        rms = float(np.sqrt(np.mean(np.square(window), dtype=np.float64)))
        peak = float(np.max(np.abs(window))) if window.size else 0.0
        guard_rms = float(np.sqrt(np.mean(np.square(guard), dtype=np.float64)))
        rms_dbfs = _dbfs(rms)
        peak_dbfs = _dbfs(peak)
        guard_rms_dbfs = _dbfs(guard_rms)
        active_above_guard_db = rms_dbfs - guard_rms_dbfs
        velocity = int(row["tested_velocity"])
        velocity_gain_db = 20.0 * math.log10(velocity / 127.0)
        preliminary.append(
            {
                **dict(row),
                "rms_dbfs": round(rms_dbfs, 6),
                "peak_dbfs": round(peak_dbfs, 6),
                "pre_guard_rms_dbfs": round(guard_rms_dbfs, 6),
                "active_above_pre_guard_db": round(active_above_guard_db, 6),
                "velocity_gain_db": round(velocity_gain_db, 6),
                "velocity_normalized_rms_dbfs": round(rms_dbfs - velocity_gain_db, 6),
            }
        )

    groups: dict[tuple[int, str], list[float]] = defaultdict(list)
    for row in preliminary:
        groups[(int(row["channel"]), str(row["velocity_bucket"]))].append(
            float(row["velocity_normalized_rms_dbfs"])
        )
    measured: list[dict[str, Any]] = []
    for row in preliminary:
        peers = groups[(int(row["channel"]), str(row["velocity_bucket"]))]
        reference = float(statistics.median(peers)) if len(peers) >= 2 else None
        deficit = (
            None
            if reference is None
            else max(
                0.0,
                reference - float(row["velocity_normalized_rms_dbfs"]),
            )
        )
        absolute_rms_passed = float(row["rms_dbfs"]) >= MINIMUM_COVERAGE_RMS_DBFS
        absolute_peak_passed = float(row["peak_dbfs"]) >= MINIMUM_COVERAGE_PEAK_DBFS
        guard_delta_passed = (
            float(row["active_above_pre_guard_db"]) >= MINIMUM_ACTIVE_ABOVE_GUARD_DB
        )
        consistency_passed = (
            deficit is None or deficit <= MAXIMUM_NORMALIZED_RMS_DEFICIT_DB
        )
        measured.append(
            {
                **row,
                "comparison_peer_count": len(peers),
                "comparison_reference_dbfs": (
                    None if reference is None else round(reference, 6)
                ),
                "normalized_rms_deficit_db": (
                    None if deficit is None else round(deficit, 6)
                ),
                "absolute_rms_passed": absolute_rms_passed,
                "absolute_peak_passed": absolute_peak_passed,
                "active_above_pre_guard_passed": guard_delta_passed,
                "consistency_passed": consistency_passed,
                "passed": (
                    absolute_rms_passed
                    and absolute_peak_passed
                    and guard_delta_passed
                    and consistency_passed
                ),
            }
        )

    failed = [row for row in measured if row["passed"] is not True]
    report = {
        **keys_coverage_contract(required=True),
        "status": "passed" if not failed else "failed",
        "functional_status": "passed" if not failed else "failed",
        "quality_status": "review_required",
        "passed": not failed,
        "zone_count": len(measured),
        "failed_zone_count": len(failed),
        "duration_seconds": plan["duration_seconds"],
        "probe_bpm": PROBE_BPM,
        "summary": {
            "minimum_rms_dbfs": min(float(row["rms_dbfs"]) for row in measured),
            "minimum_peak_dbfs": min(float(row["peak_dbfs"]) for row in measured),
            "minimum_active_above_pre_guard_db": min(
                float(row["active_above_pre_guard_db"]) for row in measured
            ),
            "maximum_normalized_rms_deficit_db": max(
                (
                    float(row["normalized_rms_deficit_db"])
                    for row in measured
                    if row["normalized_rms_deficit_db"] is not None
                ),
                default=0.0,
            ),
        },
        "zones": measured,
    }
    validate_keys_coverage_report(report, require_pass=False)
    return report


def require_keys_coverage(report: Mapping[str, Any]) -> None:
    """Fail closed unless every representative used zone passed."""

    validate_keys_coverage_report(report, require_pass=False)
    if report.get("passed") is not True:
        failures = [
            (
                f"ch {int(row['channel']) + 1} pitch {row['pitch']} "
                f"{row['velocity_bucket']}@{row['tested_velocity']}"
            )
            for row in report["zones"]
            if row.get("passed") is not True
        ]
        summary = ", ".join(failures[:5])
        if len(failures) > 5:
            summary += f", and {len(failures) - 5} more"
        raise InstrumentCoverageError(
            "complete keys patch failed representative used-zone coverage: " + summary
        )


def validate_keys_coverage_report(
    report: Mapping[str, Any],
    *,
    require_pass: bool = True,
) -> None:
    """Validate persisted coverage evidence without re-running FluidSynth."""

    if not isinstance(report, Mapping):
        raise InstrumentCoverageError("keys coverage report is invalid")
    contract = keys_coverage_contract(required=True)
    expected_report_keys = set(contract) | {
        "passed",
        "zone_count",
        "failed_zone_count",
        "duration_seconds",
        "probe_bpm",
        "summary",
        "zones",
    }
    if set(report) != expected_report_keys:
        raise InstrumentCoverageError("keys coverage report fields are invalid")
    for key, expected in contract.items():
        if key in {"status", "functional_status"}:
            continue
        if report.get(key) != expected:
            raise InstrumentCoverageError(
                f"keys coverage report changed its {key} contract"
            )
    zones = report.get("zones")
    if (
        not isinstance(zones, list)
        or not zones
        or not _is_strict_int(report.get("zone_count"))
        or report["zone_count"] != len(zones)
        or len(zones) > MAXIMUM_COVERAGE_ZONES
        or not _is_finite_number(report.get("duration_seconds"))
        or not _close(
            report["duration_seconds"],
            len(zones) * PROBE_SLOT_SECONDS,
        )
        or report.get("probe_bpm") != PROBE_BPM
        or type(report.get("passed")) is not bool
        or not _is_strict_int(report.get("failed_zone_count"))
    ):
        raise InstrumentCoverageError("keys coverage zones are invalid")

    groups: dict[tuple[int, str], list[float]] = defaultdict(list)
    measured_fields = _BASE_ZONE_FIELDS | {
        "rms_dbfs",
        "peak_dbfs",
        "pre_guard_rms_dbfs",
        "active_above_pre_guard_db",
        "velocity_gain_db",
        "velocity_normalized_rms_dbfs",
        "comparison_peer_count",
        "comparison_reference_dbfs",
        "normalized_rms_deficit_db",
        "absolute_rms_passed",
        "absolute_peak_passed",
        "active_above_pre_guard_passed",
        "consistency_passed",
        "passed",
    }
    for index, row in enumerate(zones):
        _validate_base_zone(row, index=index, exact_fields=measured_fields)
        for key in (
            "rms_dbfs",
            "peak_dbfs",
            "pre_guard_rms_dbfs",
            "active_above_pre_guard_db",
            "velocity_gain_db",
            "velocity_normalized_rms_dbfs",
        ):
            if not _is_finite_number(row.get(key)):
                raise InstrumentCoverageError("keys coverage zone levels are invalid")
        expected_velocity_gain = round(
            20.0 * math.log10(int(row["tested_velocity"]) / 127.0),
            6,
        )
        if (
            not _close(row["velocity_gain_db"], expected_velocity_gain)
            or not _close(
                row["velocity_normalized_rms_dbfs"],
                round(
                    float(row["rms_dbfs"]) - expected_velocity_gain,
                    6,
                ),
            )
            or not _close(
                row["active_above_pre_guard_db"],
                round(
                    float(row["rms_dbfs"]) - float(row["pre_guard_rms_dbfs"]),
                    6,
                ),
            )
            or float(row["rms_dbfs"]) > float(row["peak_dbfs"]) + 1e-6
        ):
            raise InstrumentCoverageError("keys coverage zone level derivation changed")
        groups[(int(row["channel"]), str(row["velocity_bucket"]))].append(
            float(row["velocity_normalized_rms_dbfs"])
        )
    _validate_zone_order(zones)

    failed = 0
    for index, row in enumerate(zones):
        peers = groups[(int(row["channel"]), str(row["velocity_bucket"]))]
        expected_reference = (
            None if len(peers) == 1 else round(float(statistics.median(peers)), 6)
        )
        expected_deficit = (
            None
            if expected_reference is None
            else round(
                max(
                    0.0,
                    expected_reference - float(row["velocity_normalized_rms_dbfs"]),
                ),
                6,
            )
        )
        if (
            not _is_strict_int(row.get("comparison_peer_count"))
            or row["comparison_peer_count"] != len(peers)
            or not _optional_number_matches(
                row.get("comparison_reference_dbfs"),
                expected_reference,
            )
            or not _optional_number_matches(
                row.get("normalized_rms_deficit_db"),
                expected_deficit,
            )
        ):
            raise InstrumentCoverageError("keys coverage comparison evidence changed")
        expected_absolute_rms = float(row["rms_dbfs"]) >= MINIMUM_COVERAGE_RMS_DBFS
        expected_absolute_peak = float(row["peak_dbfs"]) >= MINIMUM_COVERAGE_PEAK_DBFS
        expected_guard = (
            float(row["active_above_pre_guard_db"]) >= MINIMUM_ACTIVE_ABOVE_GUARD_DB
        )
        expected_consistency = (
            expected_deficit is None
            or expected_deficit <= MAXIMUM_NORMALIZED_RMS_DEFICIT_DB
        )
        for key, expected in (
            ("absolute_rms_passed", expected_absolute_rms),
            ("absolute_peak_passed", expected_absolute_peak),
            ("active_above_pre_guard_passed", expected_guard),
            ("consistency_passed", expected_consistency),
        ):
            if type(row.get(key)) is not bool or row[key] is not expected:
                raise InstrumentCoverageError(
                    "keys coverage threshold evidence changed"
                )
        expected_pass = (
            expected_absolute_rms
            and expected_absolute_peak
            and expected_guard
            and expected_consistency
        )
        if type(row.get("passed")) is not bool or row["passed"] is not expected_pass:
            raise InstrumentCoverageError(
                "keys coverage zone pass evidence is inconsistent"
            )
        if not expected_pass:
            failed += 1
    summary = report.get("summary")
    expected_summary = {
        "minimum_rms_dbfs": min(float(row["rms_dbfs"]) for row in zones),
        "minimum_peak_dbfs": min(float(row["peak_dbfs"]) for row in zones),
        "minimum_active_above_pre_guard_db": min(
            float(row["active_above_pre_guard_db"]) for row in zones
        ),
        "maximum_normalized_rms_deficit_db": max(
            (
                float(row["normalized_rms_deficit_db"])
                for row in zones
                if row["normalized_rms_deficit_db"] is not None
            ),
            default=0.0,
        ),
    }
    if (
        not isinstance(summary, Mapping)
        or set(summary) != set(expected_summary)
        or any(
            not _is_finite_number(summary.get(key))
            or not _close(summary[key], expected)
            for key, expected in expected_summary.items()
        )
    ):
        raise InstrumentCoverageError("keys coverage summary metrics changed")
    if (
        report.get("failed_zone_count") != failed
        or report.get("passed") is not (failed == 0)
        or report.get("status") != ("passed" if failed == 0 else "failed")
        or report.get("functional_status") != ("passed" if failed == 0 else "failed")
        or report.get("quality_status") != "review_required"
    ):
        raise InstrumentCoverageError("keys coverage summary is inconsistent")
    if require_pass and failed:
        raise InstrumentCoverageError("persisted keys coverage did not pass")


def public_keys_coverage_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe report suitable for one still-blind candidate slot."""

    validate_keys_coverage_report(report)
    return {
        key: _json_copy(report[key])
        for key in (
            "passed",
            "zone_count",
            "failed_zone_count",
            "duration_seconds",
            "summary",
            "zones",
        )
    }


def verify_keys_coverage_probe(
    report: Mapping[str, Any],
    probe_midi: str | Path,
    *,
    expected_program: int,
    maximum_note_ons: int,
) -> dict[str, Any]:
    """Re-check a persisted probe against its path-free measured zone rows."""

    validate_keys_coverage_report(report)
    probe_path = Path(probe_midi)
    canonical = _keys_coverage_probe_bytes(
        _coverage_plan_from_report(report),
        program=int(expected_program),
    )
    if probe_path.read_bytes() != canonical:
        raise InstrumentCoverageError("persisted keys coverage probe bytes changed")
    expected = [
        (
            int(row["channel"]),
            int(row["pitch"]),
            int(row["tested_velocity"]),
            float(row["start_seconds"]),
            float(row["note_end_seconds"]),
        )
        for row in report["zones"]
    ]
    actual: list[tuple[int, int, int, float, float]] = []
    programs: set[int] = set()
    for clip in read_midi_clips(probe_path, max_notes=maximum_note_ons):
        channel = int(clip.instrument.channel)
        programs.add(int(clip.instrument.program))
        for note in clip.notes:
            actual.append(
                (
                    channel,
                    int(note.pitch),
                    int(note.velocity),
                    round(float(note.source_start_seconds), 9),
                    round(float(note.source_end_seconds), 9),
                )
            )
    actual.sort(key=lambda row: (row[3], row[0], row[1], row[2]))
    if len(actual) != len(expected) or any(
        (
            before[:3] != after[:3]
            or abs(before[3] - after[3]) > 1e-6
            or abs(before[4] - after[4]) > 1e-6
        )
        for before, after in zip(actual, expected)
    ):
        raise InstrumentCoverageError(
            "persisted keys coverage probe no longer matches measured zones"
        )
    if programs != {int(expected_program)}:
        raise InstrumentCoverageError("persisted keys coverage probe program changed")
    return {
        "note_count": len(actual),
        "channels": sorted({row[0] for row in actual}),
        "expected_program": int(expected_program),
        "notes_match_report": True,
    }


def _coverage_plan_from_report(report: Mapping[str, Any]) -> dict[str, Any]:
    contract = keys_coverage_contract(required=True)
    return {
        **contract,
        "status": "planned",
        "zone_count": int(report["zone_count"]),
        "duration_seconds": float(report["duration_seconds"]),
        "probe_bpm": PROBE_BPM,
        "zones": [
            {key: row[key] for key in _BASE_ZONE_FIELDS} for row in report["zones"]
        ],
    }


def _checked_plan_zones(plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    contract = keys_coverage_contract(required=True)
    expected_plan_keys = set(contract) | {
        "zone_count",
        "duration_seconds",
        "probe_bpm",
        "zones",
    }
    if (
        not isinstance(plan, Mapping)
        or set(plan) != expected_plan_keys
        or plan.get("status") != "planned"
        or any(
            plan.get(key) != value for key, value in contract.items() if key != "status"
        )
        or not isinstance(plan.get("zones"), list)
        or not _is_strict_int(plan.get("zone_count"))
        or plan["zone_count"] != len(plan["zones"])
        or not 1 <= len(plan["zones"]) <= MAXIMUM_COVERAGE_ZONES
        or not _is_finite_number(plan.get("duration_seconds"))
        or not _close(
            plan["duration_seconds"],
            len(plan["zones"]) * PROBE_SLOT_SECONDS,
        )
        or float(plan["duration_seconds"]) > MAXIMUM_COVERAGE_SECONDS
        or plan.get("probe_bpm") != PROBE_BPM
    ):
        raise InstrumentCoverageError("keys coverage plan is invalid")
    zones = plan["zones"]
    seen: set[tuple[int, int, str]] = set()
    for index, row in enumerate(zones):
        _validate_base_zone(row, index=index, exact_fields=_BASE_ZONE_FIELDS)
        identity = (
            int(row["channel"]),
            int(row["pitch"]),
            str(row["velocity_bucket"]),
        )
        if identity in seen:
            raise InstrumentCoverageError("keys coverage plan zones are duplicated")
        seen.add(identity)
    _validate_zone_order(zones)
    return zones


def _validate_base_zone(
    row: Any,
    *,
    index: int,
    exact_fields: set[str],
) -> None:
    if not isinstance(row, Mapping) or set(row) != exact_fields:
        raise InstrumentCoverageError("keys coverage zone fields are invalid")
    integer_fields = (
        "index",
        "channel",
        "pitch",
        "tested_velocity",
        "observed_velocity_minimum",
        "observed_velocity_maximum",
        "observed_note_count",
    )
    if any(not _is_strict_int(row.get(key)) for key in integer_fields):
        raise InstrumentCoverageError("keys coverage zone types are invalid")
    channel = int(row["channel"])
    pitch = int(row["pitch"])
    minimum = int(row["observed_velocity_minimum"])
    maximum = int(row["observed_velocity_maximum"])
    tested = int(row["tested_velocity"])
    count = int(row["observed_note_count"])
    if (
        int(row["index"]) != index
        or not 0 <= channel <= 15
        or channel == 9
        or not 0 <= pitch <= 127
        or not 1 <= minimum <= maximum <= 127
        or tested != minimum
        or count < 1
    ):
        raise InstrumentCoverageError("keys coverage zone values are invalid")
    bucket = _velocity_bucket(tested)
    if (
        row.get("velocity_bucket") != bucket["id"]
        or _velocity_bucket(maximum)["id"] != bucket["id"]
    ):
        raise InstrumentCoverageError("keys coverage velocity bucket is invalid")
    timing_keys = (
        "slot_start_seconds",
        "start_seconds",
        "note_end_seconds",
        "window_end_seconds",
    )
    if any(not _is_finite_number(row.get(key)) for key in timing_keys):
        raise InstrumentCoverageError("keys coverage zone timing is invalid")
    expected_slot = index * PROBE_SLOT_SECONDS
    if (
        not _close(row["slot_start_seconds"], expected_slot)
        or not _close(
            row["start_seconds"],
            expected_slot + PROBE_LEAD_IN_SECONDS,
        )
        or not _close(
            row["note_end_seconds"],
            expected_slot + PROBE_LEAD_IN_SECONDS + PROBE_NOTE_SECONDS,
        )
        or not _close(
            row["window_end_seconds"],
            expected_slot + PROBE_SLOT_SECONDS,
        )
    ):
        raise InstrumentCoverageError("keys coverage zone geometry changed")


def _validate_zone_order(zones: list[Any]) -> None:
    rank = {str(bucket["id"]): index for index, bucket in enumerate(VELOCITY_BUCKETS)}
    identities = [
        (
            int(row["channel"]),
            int(row["pitch"]),
            rank[str(row["velocity_bucket"])],
        )
        for row in zones
    ]
    if identities != sorted(identities) or len(set(identities)) != len(identities):
        raise InstrumentCoverageError("keys coverage zones are not uniquely ordered")


def _is_strict_int(value: Any) -> bool:
    return type(value) is int


def _is_finite_number(value: Any) -> bool:
    return type(value) in {int, float} and math.isfinite(float(value))


def _close(left: Any, right: Any, *, tolerance: float = 0.000002) -> bool:
    return (
        _is_finite_number(left)
        and _is_finite_number(right)
        and abs(float(left) - float(right)) <= tolerance
    )


def _optional_number_matches(value: Any, expected: float | None) -> bool:
    if expected is None:
        return value is None
    return _close(value, expected)


def _velocity_bucket(velocity: int) -> Mapping[str, Any]:
    for bucket in VELOCITY_BUCKETS:
        if int(bucket["minimum"]) <= velocity <= int(bucket["maximum"]):
            return bucket
    raise InstrumentCoverageError("MIDI velocity must be from 1 to 127")


def _dbfs(value: float) -> float:
    return -120.0 if value <= 1e-12 else 20.0 * math.log10(value)


def _audio_window(audio: Any, start: int, end: int, *, channels: int):
    import numpy as np

    frame_count = max(1, end - start)
    if start >= len(audio):
        return np.zeros((frame_count, channels), dtype="float32")
    window = np.asarray(audio[start : min(end, len(audio))])
    missing = frame_count - len(window)
    if missing > 0:
        window = np.pad(window, ((0, missing), (0, 0)))
    return window


def _variable_length(value: int) -> bytes:
    if value < 0:
        raise InstrumentCoverageError("coverage probe MIDI delta is negative")
    buffer = value & 0x7F
    output = bytearray()
    while value >> 7:
        value >>= 7
        buffer <<= 8
        buffer |= (value & 0x7F) | 0x80
    while True:
        output.append(buffer & 0xFF)
        if buffer & 0x80:
            buffer >>= 8
        else:
            return bytes(output)


def _json_copy(value: Any) -> Any:
    import json

    return json.loads(json.dumps(value, allow_nan=False))
