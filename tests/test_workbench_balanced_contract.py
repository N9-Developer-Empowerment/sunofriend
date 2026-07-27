from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from sunofriend import workbench_artifacts, workbench_mix
from sunofriend.workbench_balanced_contract import BALANCED_MIX_CONTRACT


class BalancedMixContractTests(unittest.TestCase):
    def test_v3_public_documents_remain_exact_and_are_fresh(self) -> None:
        expected_measurement = {
            "window_seconds": 0.4,
            "absolute_gate_dbfs": -70.0,
            "relative_gate_db": 10.0,
            "overlap_relative_gate_db": 30.0,
            "statistic": "median active non-overlapping block RMS",
            "peak_kind": "sample peak, not true peak",
            "scope": (
                "render horizon only; excluded source or neutral-preview tails "
                "are not measured"
            ),
        }
        expected_limits = {
            "source_match_gain_db": [-24.0, 6.0],
            "maximum_drum_bus_attenuation_db": -18.0,
            "drum_overlap_median_target_db": -2.0,
            "drum_overlap_p95_maximum_db": 3.0,
            "audition_target_gated_rms_dbfs": -18.0,
            "sample_peak_ceiling_dbfs": -1.0,
            "maximum_normalisation_boost_db": 12.0,
            "normalisation_target_tolerance_db": 0.1,
        }

        measurement = BALANCED_MIX_CONTRACT.measurement_document()
        limits = BALANCED_MIX_CONTRACT.limits_document()
        self.assertEqual(measurement, expected_measurement)
        self.assertEqual(limits, expected_limits)

        measurement["window_seconds"] = 999.0
        limits["source_match_gain_db"][0] = 999.0
        self.assertEqual(
            BALANCED_MIX_CONTRACT.measurement_document(),
            expected_measurement,
        )
        self.assertEqual(
            BALANCED_MIX_CONTRACT.limits_document(),
            expected_limits,
        )

    def test_renderer_and_cache_verifier_share_one_immutable_contract(
        self,
    ) -> None:
        self.assertIs(
            workbench_mix.BALANCED_MIX_CONTRACT,
            BALANCED_MIX_CONTRACT,
        )
        self.assertIs(
            workbench_artifacts.BALANCED_MIX_CONTRACT,
            BALANCED_MIX_CONTRACT,
        )
        self.assertEqual(
            workbench_mix.BALANCED_ARRANGEMENT_SCHEMA,
            BALANCED_MIX_CONTRACT.arrangement_schema,
        )
        self.assertEqual(
            workbench_mix.BALANCED_MIX_REPORT_SCHEMA,
            BALANCED_MIX_CONTRACT.mix_report_schema,
        )
        self.assertEqual(
            workbench_mix.BALANCED_MIX_POLICY,
            "source-referenced-summed-group-balance-v3",
        )
        self.assertEqual(
            workbench_artifacts._BALANCED_MIX_RECEIPT_SCHEMA,
            BALANCED_MIX_CONTRACT.receipt_schema,
        )
        self.assertEqual(
            workbench_artifacts._BALANCED_MASTERING_BOUNDARY,
            BALANCED_MIX_CONTRACT.mastering_boundary,
        )

        with self.assertRaises(FrozenInstanceError):
            BALANCED_MIX_CONTRACT.window_seconds = 0.5


if __name__ == "__main__":
    unittest.main()
