from __future__ import annotations

import math
import unittest

from sunofriend.note_alignment import AlignmentEvent, align_events


class NoteAlignmentTests(unittest.TestCase):
    def test_alignment_is_one_to_one_offset_aware_and_order_independent(self) -> None:
        left = [
            AlignmentEvent(4, 30.05, 60.0, "keys"),
            AlignmentEvent(2, 30.10, 60.0, "keys"),
            AlignmentEvent(7, 30.50, 64.0, "keys"),
        ]
        right = [
            AlignmentEvent(9, 0.06, 60.0, "keys"),
            AlignmentEvent(8, 0.00, 60.0, "keys"),
            AlignmentEvent(3, 0.50, 65.0, "keys"),
        ]

        first = align_events(
            left,
            right,
            left_offset=30.0,
            right_offset=0.0,
            tolerance=0.05,
            pitch_policy="exact_integer",
            require_exact_label=True,
        )
        second = align_events(
            list(reversed(left)),
            list(reversed(right)),
            left_offset=30.0,
            right_offset=0.0,
            tolerance=0.05,
            pitch_policy="exact_integer",
            require_exact_label=True,
        )

        self.assertEqual(first, second)
        self.assertEqual(
            [(match.left_index, match.right_index) for match in first.matches],
            [(4, 8), (2, 9)],
        )
        self.assertEqual(first.unmatched_left_indices, (7,))
        self.assertEqual(first.unmatched_right_indices, (3,))
        self.assertAlmostEqual(first.matches[0].left_onset_seconds, 0.05)
        self.assertAlmostEqual(first.matches[0].onset_delta_seconds, -0.05)

    def test_tolerance_is_inclusive_and_empty_inputs_retain_indices(self) -> None:
        result = align_events(
            [AlignmentEvent(5, 10.0, 60)],
            [AlignmentEvent(6, 1.125, 60)],
            left_offset=9.0,
            right_offset=0.0,
            tolerance=0.125,
            pitch_policy="exact_integer",
            require_exact_label=False,
        )
        self.assertEqual(len(result.matches), 1)

        outside = align_events(
            [AlignmentEvent(5, 10.0, 60)],
            [AlignmentEvent(6, 1.125001, 60)],
            left_offset=9.0,
            right_offset=0.0,
            tolerance=0.125,
            pitch_policy="exact_integer",
            require_exact_label=False,
        )
        self.assertEqual(outside.matches, ())

        empty = align_events(
            [AlignmentEvent(5, 10.0, 60)],
            [],
            left_offset=9.0,
            right_offset=0.0,
            tolerance=0.0,
            pitch_policy="exact_integer",
            require_exact_label=False,
        )
        self.assertEqual(empty.matches, ())
        self.assertEqual(empty.unmatched_left_indices, (5,))
        self.assertEqual(empty.unmatched_right_indices, ())

    def test_legacy_left_greedy_policy_preserves_nearest_unused_semantics(self) -> None:
        left = [
            AlignmentEvent(0, 0.05, 60),
            AlignmentEvent(1, 0.10, 60),
        ]
        right = [
            AlignmentEvent(0, 0.00, 60),
            AlignmentEvent(1, 0.09, 60),
        ]

        maximum_cardinality = align_events(
            left,
            right,
            left_offset=0.0,
            right_offset=0.0,
            tolerance=0.06,
            pitch_policy="exact_integer",
            require_exact_label=False,
        )
        legacy = align_events(
            left,
            right,
            left_offset=0.0,
            right_offset=0.0,
            tolerance=0.06,
            pitch_policy="exact_integer",
            require_exact_label=False,
            matching_policy="left_greedy_closest",
        )

        self.assertEqual(len(maximum_cardinality.matches), 2)
        self.assertEqual(
            [(match.left_index, match.right_index) for match in legacy.matches],
            [(0, 1)],
        )

    def test_pitch_and_label_policies_are_explicit(self) -> None:
        rounded = align_events(
            [AlignmentEvent(0, 0.0, 60.49, "electric_piano")],
            [AlignmentEvent(1, 0.0, 60.40, "acoustic_piano")],
            left_offset=0.0,
            right_offset=0.0,
            tolerance=0.0,
            pitch_policy="rounded",
            require_exact_label=False,
        )
        self.assertEqual(len(rounded.matches), 1)

        labelled = align_events(
            [AlignmentEvent(0, 0.0, 60.49, "electric_piano")],
            [AlignmentEvent(1, 0.0, 60.40, "acoustic_piano")],
            left_offset=0.0,
            right_offset=0.0,
            tolerance=0.0,
            pitch_policy="rounded",
            require_exact_label=True,
        )
        self.assertEqual(labelled.matches, ())

        with self.assertRaisesRegex(ValueError, "integral pitches"):
            align_events(
                [AlignmentEvent(0, 0.0, 60.49)],
                [AlignmentEvent(1, 0.0, 60.0)],
                left_offset=0.0,
                right_offset=0.0,
                tolerance=0.0,
                pitch_policy="exact_integer",
                require_exact_label=False,
            )

    def test_event_validation_rejects_bool_nonfinite_and_malformed_values(self) -> None:
        invalid_events = (
            (lambda: AlignmentEvent(True, 0.0, 60), "source_index"),
            (lambda: AlignmentEvent(-1, 0.0, 60), "source_index"),
            (lambda: AlignmentEvent(0, True, 60), "onset"),
            (lambda: AlignmentEvent(0, -0.1, 60), "non-negative"),
            (lambda: AlignmentEvent(0, math.nan, 60), "finite number"),
            (lambda: AlignmentEvent(0, 0.0, True), "pitch"),
            (lambda: AlignmentEvent(0, 0.0, math.inf), "finite number"),
            (lambda: AlignmentEvent(0, 0.0, 60, 1), "text or null"),
        )
        for build, message in invalid_events:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(ValueError, message),
            ):
                build()

        valid = AlignmentEvent(0, 0.0, 60)
        invalid_calls = (
            (
                {"left": [valid, valid]},
                "source indices must be unique",
            ),
            ({"left": [object()]}, "malformed value"),
            ({"left_offset": True}, "left_offset must be a finite number"),
            ({"right_offset": math.inf}, "right_offset must be a finite number"),
            ({"tolerance": True}, "tolerance must be a finite number"),
            ({"tolerance": -0.1}, "tolerance must be non-negative"),
            ({"pitch_policy": "octave"}, "pitch_policy"),
            ({"require_exact_label": 1}, "must be a boolean"),
            ({"matching_policy": "closest"}, "matching_policy"),
        )
        for changes, message in invalid_calls:
            arguments = {
                "left": [valid],
                "right": [AlignmentEvent(1, 0.0, 60)],
                "left_offset": 0.0,
                "right_offset": 0.0,
                "tolerance": 0.0,
                "pitch_policy": "exact_integer",
                "require_exact_label": False,
            }
            arguments.update(changes)
            with (
                self.subTest(changes=changes),
                self.assertRaisesRegex(ValueError, message),
            ):
                align_events(**arguments)


if __name__ == "__main__":
    unittest.main()
