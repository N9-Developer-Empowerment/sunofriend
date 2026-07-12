from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from sunofriend.beatgrid import Grid

try:
    import numpy as np

    from sunofriend.harmony import MAX_BEATS_PER_CHORD, align_chords_to_audio

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


class HarmonyAlignmentTests(unittest.TestCase):
    @unittest.skipUnless(NUMPY_AVAILABLE, "NumPy is part of the optional listen stack")
    def test_opening_chord_can_span_twenty_one_beats(self):
        chords = ["C", "F#", "D"]
        durations = [21, 2, 2]
        templates = {
            "C": (0, 4, 7),
            "F#": (6, 10, 1),
            "D": (2, 6, 9),
        }
        chroma = np.zeros((12, sum(durations)), dtype=float)
        start = 0
        for chord, duration in zip(chords, durations):
            for pitch_class in templates[chord]:
                chroma[pitch_class, start : start + duration] = 1.0
            start += duration

        fake_librosa = types.SimpleNamespace(
            load=lambda *_args, **_kwargs: (np.zeros(1), 22050),
            feature=types.SimpleNamespace(
                chroma_cqt=lambda **_kwargs: chroma,
            ),
            frames_to_time=lambda frames, **_kwargs: np.asarray(frames, dtype=float) + 0.5,
        )
        with patch.dict(sys.modules, {"librosa": fake_librosa}):
            segments = align_chords_to_audio(
                chords,
                "unused.wav",
                Grid(bpm=60.0),
                duration=float(sum(durations)),
            )

        self.assertEqual([segment.name for segment in segments], chords)
        self.assertEqual([segment.start for segment in segments], [0.0, 21.0, 23.0])
        self.assertEqual([segment.end for segment in segments], [21.0, 23.0, 25.0])
        self.assertTrue(
            all(
                0 < segment.end - segment.start <= MAX_BEATS_PER_CHORD
                for segment in segments
            )
        )
        self.assertTrue(
            all(left.end == right.start for left, right in zip(segments, segments[1:]))
        )


if __name__ == "__main__":
    unittest.main()
