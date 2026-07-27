"""Immutable public contract for the Workbench balanced MIDI audition.

The renderer and the cache verifier must make decisions from the same values.
Keeping those values in one frozen object prevents a policy change from
silently producing reports that the verifier interprets under older limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BalancedMixContract:
    """Versioned schemas, measurements and safety limits for one mix policy."""

    arrangement_schema: str
    mix_report_schema: str
    receipt_schema: str
    policy: str
    render_horizon_policy: str
    renderer_backend: str
    label: str
    mastering_boundary: str
    window_seconds: float
    absolute_gate_dbfs: float
    relative_gate_db: float
    overlap_relative_gate_db: float
    measurement_statistic: str
    measurement_peak_kind: str
    measurement_scope: str
    source_match_gain_db: tuple[float, float]
    maximum_drum_bus_attenuation_db: float
    drum_overlap_median_target_db: float
    drum_overlap_p95_maximum_db: float
    audition_target_gated_rms_dbfs: float
    sample_peak_ceiling_dbfs: float
    maximum_normalisation_boost_db: float
    normalisation_target_tolerance_db: float
    drum_guard_policy: str
    maximum_lanes: int
    maximum_seconds: int

    def measurement_document(self) -> dict[str, Any]:
        """Return the exact public measurement block for a mix report."""

        return {
            "window_seconds": self.window_seconds,
            "absolute_gate_dbfs": self.absolute_gate_dbfs,
            "relative_gate_db": self.relative_gate_db,
            "overlap_relative_gate_db": self.overlap_relative_gate_db,
            "statistic": self.measurement_statistic,
            "peak_kind": self.measurement_peak_kind,
            "scope": self.measurement_scope,
        }

    def limits_document(self) -> dict[str, Any]:
        """Return the exact public limits block for a mix report."""

        return {
            "source_match_gain_db": list(self.source_match_gain_db),
            "maximum_drum_bus_attenuation_db": (
                self.maximum_drum_bus_attenuation_db
            ),
            "drum_overlap_median_target_db": (
                self.drum_overlap_median_target_db
            ),
            "drum_overlap_p95_maximum_db": (
                self.drum_overlap_p95_maximum_db
            ),
            "audition_target_gated_rms_dbfs": (
                self.audition_target_gated_rms_dbfs
            ),
            "sample_peak_ceiling_dbfs": self.sample_peak_ceiling_dbfs,
            "maximum_normalisation_boost_db": (
                self.maximum_normalisation_boost_db
            ),
            "normalisation_target_tolerance_db": (
                self.normalisation_target_tolerance_db
            ),
        }


BALANCED_MIX_CONTRACT = BalancedMixContract(
    arrangement_schema="sunofriend.workbench-balanced-arrangement.v1",
    mix_report_schema="sunofriend.workbench-balanced-mix-report.v1",
    receipt_schema="sunofriend.workbench-balanced-mix-receipt.v1",
    policy="source-referenced-summed-group-balance-v3",
    render_horizon_policy="longest-verified-source-stem-v1",
    renderer_backend="FluidSynth neutral-preview render",
    label="Balanced selected-MIDI audition",
    mastering_boundary=(
        "gain-only source-referenced balance, audition normalisation and "
        "sample-peak protection; not LUFS, true-peak or release mastering"
    ),
    window_seconds=0.4,
    absolute_gate_dbfs=-70.0,
    relative_gate_db=10.0,
    overlap_relative_gate_db=30.0,
    measurement_statistic="median active non-overlapping block RMS",
    measurement_peak_kind="sample peak, not true peak",
    measurement_scope=(
        "render horizon only; excluded source or neutral-preview tails are not "
        "measured"
    ),
    source_match_gain_db=(-24.0, 6.0),
    maximum_drum_bus_attenuation_db=-18.0,
    drum_overlap_median_target_db=-2.0,
    drum_overlap_p95_maximum_db=3.0,
    audition_target_gated_rms_dbfs=-18.0,
    sample_peak_ceiling_dbfs=-1.0,
    maximum_normalisation_boost_db=12.0,
    normalisation_target_tolerance_db=0.1,
    drum_guard_policy=(
        "on time-aligned 400 ms windows where both buses are active, "
        "the guard aims for median drum level at least 2 dB below "
        "non-drums and p95 drum excess no more than 3 dB, within the "
        "maximum attenuation limit"
    ),
    maximum_lanes=24,
    maximum_seconds=20 * 60,
)


__all__ = ["BALANCED_MIX_CONTRACT", "BalancedMixContract"]
