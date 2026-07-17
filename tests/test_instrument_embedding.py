from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from sunofriend.instrument_embedding import (
    OPENL3_EMBEDDING_SIZE,
    OPENL3_MEL_BANDS,
    OPENL3_MEL_FRAMES,
    EmbeddingFingerprint,
    InstrumentEmbeddingError,
    OpenL3MusicEmbedding,
    _openl3_inputs,
    compare_embedding_fingerprints,
)


SAMPLE_RATE = 16_000


def _tone(frequency: float, seconds: float) -> np.ndarray:
    times = np.arange(round(seconds * SAMPLE_RATE), dtype=np.float32) / SAMPLE_RATE
    return (0.3 * np.sin(2.0 * np.pi * frequency * times)).astype(np.float32)


class _FakeSession:
    def get_inputs(self):
        return [
            SimpleNamespace(
                name="melspectrogram",
                shape=["batch", OPENL3_MEL_BANDS, OPENL3_MEL_FRAMES, 1],
            )
        ]

    def get_outputs(self):
        return [
            SimpleNamespace(
                name="embeddings", shape=["batch", OPENL3_EMBEDDING_SIZE]
            )
        ]

    def run(self, output_names, inputs):
        self.last_output_names = output_names
        values = inputs["melspectrogram"][:, :, :, 0]
        band_profile = np.mean(values, axis=2)
        tiled = np.tile(band_profile, (1, 4))
        return [tiled.astype(np.float32)]


class InstrumentEmbeddingTests(unittest.TestCase):
    def test_preprocessing_is_deterministic_and_matches_openl3_contract(self):
        audio = _tone(220.0, 1.25)

        first, first_rms, first_starts = _openl3_inputs(audio, SAMPLE_RATE)
        second, second_rms, second_starts = _openl3_inputs(audio, SAMPLE_RATE)

        self.assertEqual(first.shape, (2, 128, 199, 1))
        np.testing.assert_array_equal(first, second)
        np.testing.assert_array_equal(first_rms, second_rms)
        np.testing.assert_array_equal(first_starts, [0.0, 1.0])
        np.testing.assert_array_equal(first_starts, second_starts)
        self.assertAlmostEqual(float(np.max(first[0])), 0.0, places=5)
        self.assertGreaterEqual(float(np.min(first)), -80.0)

    def test_local_model_is_hash_checked_and_inference_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            model = Path(temporary) / "openl3.onnx"
            model.write_bytes(b"fixture-openl3-model")
            expected = hashlib.sha256(model.read_bytes()).hexdigest()
            embedding = OpenL3MusicEmbedding(
                model,
                expected_sha256=expected,
                session_factory=lambda _path: _FakeSession(),
            )

            first = embedding.fingerprint(_tone(220.0, 1.25), SAMPLE_RATE)
            second = embedding.fingerprint(_tone(220.0, 1.25), SAMPLE_RATE)

            self.assertEqual(first.embeddings.shape, (2, 512))
            np.testing.assert_array_equal(first.embeddings, second.embeddings)
            self.assertEqual(embedding.model_record()["sha256"], expected)

    def test_wrong_checkpoint_hash_fails_before_session_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            model = Path(temporary) / "wrong.onnx"
            model.write_bytes(b"wrong")
            called = False

            def session_factory(_path):
                nonlocal called
                called = True
                return _FakeSession()

            with self.assertRaisesRegex(
                InstrumentEmbeddingError, "SHA-256 mismatch"
            ):
                OpenL3MusicEmbedding(
                    model,
                    expected_sha256="0" * 64,
                    session_factory=session_factory,
                )
            self.assertFalse(called)

    def test_similarity_uses_only_timeline_aligned_active_windows(self):
        basis = np.zeros((3, 512), dtype=np.float32)
        basis[:, 0] = 1.0
        different = basis.copy()
        different[1] = 0.0
        different[1, 1] = 1.0
        source = EmbeddingFingerprint(
            embeddings=basis,
            rms=np.asarray([0.2, 0.2, 0.0]),
            start_seconds=np.asarray([0.0, 1.0, 2.0]),
        )
        candidate = EmbeddingFingerprint(
            embeddings=different,
            rms=np.asarray([0.2, 0.2, 0.2]),
            start_seconds=np.asarray([0.0, 1.0, 2.0]),
        )

        result = compare_embedding_fingerprints(source, candidate)

        self.assertEqual(result["active_window_count"], 2)
        self.assertEqual(result["compared_window_count"], 3)
        self.assertEqual(
            [row["window_index"] for row in result["window_scores"]], [0, 1]
        )
        self.assertEqual(result["similarity_score"], 50.0)


if __name__ == "__main__":
    unittest.main()
