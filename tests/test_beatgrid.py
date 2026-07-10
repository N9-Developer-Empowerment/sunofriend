from __future__ import annotations

import unittest

from sunofriend.beatgrid import Grid


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


if __name__ == "__main__":
    unittest.main()
