from __future__ import annotations

import unittest
from unittest.mock import patch

from sunofriend.beatgrid import Grid, grid_from_metronome
from sunofriend.compare import Onset

try:
    import numpy  # noqa: F401

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


class GridTest(unittest.TestCase):
    def test_beat_mapping_with_offset(self):
        grid = Grid(bpm=120.0, offset=0.25)
        self.assertAlmostEqual(grid.beat_of(0.25), 0.0)
        self.assertAlmostEqual(grid.beat_of(0.75), 1.0)
        self.assertAlmostEqual(grid.time_of(4), 2.25)

    def test_snap_respects_offset(self):
        grid = Grid(bpm=120.0, offset=0.25)
        # 16th step = 0.125s; grid lines at 0.25, 0.375, 0.5 ...
        self.assertAlmostEqual(grid.snap(0.38, subdiv=4), 0.375)
        self.assertAlmostEqual(grid.snap(0.26, subdiv=4), 0.25)
        # without offset the same time would snap differently
        self.assertAlmostEqual(Grid(bpm=120.0).snap(0.38, subdiv=4), 0.375)

    def test_is_strong(self):
        grid = Grid(bpm=120.0, offset=0.25)
        self.assertTrue(grid.is_strong(0.25))      # beat 0
        self.assertTrue(grid.is_strong(0.75))      # beat 1
        self.assertFalse(grid.is_strong(0.5))      # the 'and' of beat 0

    @unittest.skipUnless(NUMPY_AVAILABLE, "NumPy is part of the optional listen stack")
    def test_subdivision_metronome_does_not_double_the_tempo(self):
        # Eighth-note clicks at a nominal 120 BPM: click interval is 0.25s,
        # while a quarter-note beat remains 0.5s.
        onsets = [
            Onset(i * 0.25, 1.0 if i % 8 == 0 else 0.5)
            for i in range(80)
        ]
        with patch("sunofriend.compare.extract_onsets", return_value=onsets):
            grid = grid_from_metronome("unused.wav", nominal_bpm=120)

        self.assertAlmostEqual(grid.bpm, 120.0, places=2)
        self.assertAlmostEqual(grid.time_of(10), 5.0, places=3)
        self.assertEqual(len(grid.beat_times), 40)


if __name__ == "__main__":
    unittest.main()
