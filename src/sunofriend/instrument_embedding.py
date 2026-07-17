"""Optional learned audio-embedding evidence for instrument matching.

The Phase 3 matcher deliberately keeps this evidence separate from the
explainable spectral/dynamics/attack score.  A local, hash-pinned OpenL3 ONNX
checkpoint turns aligned one-second audio windows into normalized vectors;
cosine similarity then supplies a second audition ranking.  No checkpoint is
downloaded at runtime and the learned result never changes the existing GM
ranking.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


OPENL3_MODEL_NAME = "openl3-music-mel128-emb512-3"
OPENL3_MODEL_FILENAME = f"{OPENL3_MODEL_NAME}.onnx"
OPENL3_MODEL_SHA256 = (
    "81c24c8a723054717fdea5c7448acb6023baaf70a0fc526deb030c2032db0ed3"
)
OPENL3_MODEL_BYTES = 18_740_670
OPENL3_MODEL_URL = (
    "https://essentia.upf.edu/models/feature-extractors/openl3/"
    f"{OPENL3_MODEL_FILENAME}"
)
OPENL3_SOURCE_URL = "https://github.com/marl/openl3"
OPENL3_LICENSE = "CC-BY-4.0 (original OpenL3 model weights)"
OPENL3_SAMPLE_RATE = 48_000
OPENL3_WINDOW_SECONDS = 1.0
OPENL3_N_FFT = 2_048
OPENL3_HOP_LENGTH = 242
OPENL3_MEL_BANDS = 128
OPENL3_MEL_FRAMES = 199
OPENL3_EMBEDDING_SIZE = 512


class InstrumentEmbeddingError(RuntimeError):
    """Raised when optional learned instrument evidence cannot be trusted."""


@dataclass(frozen=True)
class EmbeddingFingerprint:
    embeddings: Any
    rms: Any
    start_seconds: Any

    def summary(self) -> dict[str, Any]:
        import numpy as np

        levels = np.asarray(self.rms, dtype=float)
        maximum = float(np.max(levels)) if len(levels) else 0.0
        threshold = max(maximum * 0.01, 1e-7)
        active = levels > threshold
        return {
            "window_count": int(len(levels)),
            "active_window_count": int(np.count_nonzero(active)),
            "window_seconds": OPENL3_WINDOW_SECONDS,
            "rms": {
                "minimum": _rounded(float(np.min(levels)) if len(levels) else 0.0),
                "median": _rounded(float(np.median(levels)) if len(levels) else 0.0),
                "maximum": _rounded(maximum),
                "active_threshold": _rounded(threshold),
            },
        }


class OpenL3MusicEmbedding:
    """Load and run the pinned OpenL3 music embedding ONNX model on CPU."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        expected_sha256: str = OPENL3_MODEL_SHA256,
        session_factory: Callable[[str], Any] | None = None,
    ) -> None:
        model = Path(model_path).expanduser()
        if not model.is_file():
            raise InstrumentEmbeddingError(f"OpenL3 model not found: {model}")
        actual_sha256 = _sha256(model)
        if actual_sha256 != expected_sha256:
            raise InstrumentEmbeddingError(
                "OpenL3 model SHA-256 mismatch: "
                f"expected {expected_sha256}, found {actual_sha256}"
            )
        try:
            if session_factory is None:
                import onnxruntime as ort

                session = ort.InferenceSession(
                    str(model), providers=["CPUExecutionProvider"]
                )
            else:
                session = session_factory(str(model))
        except Exception as exc:
            raise InstrumentEmbeddingError(
                f"OpenL3 ONNX model could not be loaded: {type(exc).__name__}: {exc}"
            ) from exc
        self._validate_contract(session)
        self.model_path = model.resolve()
        self.model_sha256 = actual_sha256
        self.model_bytes = model.stat().st_size
        self._session = session

    @staticmethod
    def _validate_contract(session: Any) -> None:
        try:
            inputs = session.get_inputs()
            outputs = session.get_outputs()
        except Exception as exc:
            raise InstrumentEmbeddingError(
                f"OpenL3 ONNX session did not expose its contract: {exc}"
            ) from exc
        if len(inputs) != 1 or len(outputs) != 1:
            raise InstrumentEmbeddingError(
                "OpenL3 ONNX contract must have exactly one input and one output"
            )
        input_node = inputs[0]
        output_node = outputs[0]
        input_shape = list(input_node.shape)
        output_shape = list(output_node.shape)
        if (
            input_node.name != "melspectrogram"
            or input_shape[1:] != [OPENL3_MEL_BANDS, OPENL3_MEL_FRAMES, 1]
            or output_node.name != "embeddings"
            or output_shape[-1:] != [OPENL3_EMBEDDING_SIZE]
        ):
            raise InstrumentEmbeddingError(
                "Unexpected OpenL3 ONNX contract: "
                f"input {input_node.name!r} {input_shape}, "
                f"output {output_node.name!r} {output_shape}"
            )

    def model_record(self) -> dict[str, Any]:
        return {
            "name": OPENL3_MODEL_NAME,
            "path": str(self.model_path),
            "sha256": self.model_sha256,
            "bytes": self.model_bytes,
            "expected_bytes": OPENL3_MODEL_BYTES,
            "source": OPENL3_SOURCE_URL,
            "checkpoint_url": OPENL3_MODEL_URL,
            "license": OPENL3_LICENSE,
            "runtime": "onnxruntime CPUExecutionProvider",
            "input": {
                "name": "melspectrogram",
                "shape": ["batch", OPENL3_MEL_BANDS, OPENL3_MEL_FRAMES, 1],
            },
            "output": {
                "name": "embeddings",
                "shape": ["batch", OPENL3_EMBEDDING_SIZE],
            },
        }

    def preprocessing_record(self) -> dict[str, Any]:
        return {
            "sample_rate": OPENL3_SAMPLE_RATE,
            "window_seconds": OPENL3_WINDOW_SECONDS,
            "window_overlap_seconds": 0.0,
            "final_window": "zero-padded",
            "n_fft": OPENL3_N_FFT,
            "hop_length": OPENL3_HOP_LENGTH,
            "mel_bands": OPENL3_MEL_BANDS,
            "mel_scale": "Slaney",
            "magnitude_power": 1.0,
            "decibels": "10*log10, floor at window maximum minus 80 dB",
            "embedding_normalization": "L2 per window",
        }

    def fingerprint(self, values: Any, sample_rate: int) -> EmbeddingFingerprint:
        import numpy as np

        inputs, rms, starts = _openl3_inputs(values, sample_rate)
        batches = []
        for start in range(0, len(inputs), 16):
            batch = inputs[start : start + 16]
            try:
                result = self._session.run(
                    ["embeddings"], {"melspectrogram": batch}
                )[0]
            except Exception as exc:
                raise InstrumentEmbeddingError(
                    f"OpenL3 inference failed: {type(exc).__name__}: {exc}"
                ) from exc
            batches.append(np.asarray(result, dtype=np.float32))
        embeddings = np.concatenate(batches, axis=0)
        if embeddings.shape != (len(inputs), OPENL3_EMBEDDING_SIZE):
            raise InstrumentEmbeddingError(
                "OpenL3 inference returned unexpected shape "
                f"{list(embeddings.shape)}"
            )
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / np.maximum(norms, 1e-12)
        embeddings = np.nan_to_num(embeddings, copy=False)
        return EmbeddingFingerprint(
            embeddings=embeddings,
            rms=rms,
            start_seconds=starts,
        )


def compare_embedding_fingerprints(
    source: EmbeddingFingerprint,
    candidate: EmbeddingFingerprint,
) -> dict[str, Any]:
    """Compare same-timeline embedding windows without changing either input."""

    import numpy as np

    count = min(
        len(source.embeddings),
        len(candidate.embeddings),
        len(source.rms),
        len(candidate.rms),
    )
    if count <= 0:
        return _empty_comparison()
    source_rms = np.asarray(source.rms[:count], dtype=float)
    candidate_rms = np.asarray(candidate.rms[:count], dtype=float)
    source_threshold = max(float(np.max(source_rms)) * 0.01, 1e-7)
    candidate_threshold = max(float(np.max(candidate_rms)) * 0.01, 1e-7)
    active = (source_rms > source_threshold) & (candidate_rms > candidate_threshold)
    indices = np.flatnonzero(active)
    if not len(indices):
        result = _empty_comparison()
        result["compared_window_count"] = int(count)
        return result
    cosine = np.sum(
        source.embeddings[:count] * candidate.embeddings[:count], axis=1
    )
    scores = np.clip(cosine[active], 0.0, 1.0)
    percentiles = np.percentile(scores, [10, 50, 90])
    window_scores = [
        {
            "window_index": int(index),
            "start_seconds": _rounded(float(source.start_seconds[index]), 6),
            "cosine_similarity": _rounded(float(cosine[index]), 6),
        }
        for index in indices
    ]
    return {
        "similarity_score": _rounded(float(percentiles[1]) * 100.0, 3),
        "compared_window_count": int(count),
        "active_window_count": int(len(indices)),
        "similarity_percentiles": {
            "p10": _rounded(float(percentiles[0]) * 100.0, 3),
            "p50": _rounded(float(percentiles[1]) * 100.0, 3),
            "p90": _rounded(float(percentiles[2]) * 100.0, 3),
        },
        "window_scores": window_scores,
    }


def _openl3_inputs(values: Any, sample_rate: int) -> tuple[Any, Any, Any]:
    import librosa
    import numpy as np

    if sample_rate <= 0:
        raise InstrumentEmbeddingError("Audio sample rate must be positive")
    audio = np.asarray(values, dtype=np.float32).reshape(-1)
    audio = np.nan_to_num(audio, copy=False)
    if not len(audio):
        raise InstrumentEmbeddingError("Cannot embed empty audio")
    if sample_rate != OPENL3_SAMPLE_RATE:
        audio = librosa.resample(
            audio,
            orig_sr=sample_rate,
            target_sr=OPENL3_SAMPLE_RATE,
        ).astype(np.float32, copy=False)
    window_samples = int(OPENL3_SAMPLE_RATE * OPENL3_WINDOW_SECONDS)
    count = max(1, math.ceil(len(audio) / window_samples))
    inputs = np.empty(
        (count, OPENL3_MEL_BANDS, OPENL3_MEL_FRAMES, 1), dtype=np.float32
    )
    rms = np.empty(count, dtype=np.float32)
    starts = np.arange(count, dtype=np.float32) * OPENL3_WINDOW_SECONDS
    for index in range(count):
        window = audio[index * window_samples : (index + 1) * window_samples]
        if len(window) < window_samples:
            window = np.pad(window, (0, window_samples - len(window)))
        rms[index] = math.sqrt(float(np.mean(window.astype(np.float64) ** 2)))
        mel = librosa.feature.melspectrogram(
            y=window,
            sr=OPENL3_SAMPLE_RATE,
            n_fft=OPENL3_N_FFT,
            hop_length=OPENL3_HOP_LENGTH,
            n_mels=OPENL3_MEL_BANDS,
            power=1.0,
            center=True,
            htk=False,
            norm="slaney",
        )
        if mel.shape != (OPENL3_MEL_BANDS, OPENL3_MEL_FRAMES):
            raise InstrumentEmbeddingError(
                f"OpenL3 preprocessing produced unexpected shape {list(mel.shape)}"
            )
        decibels = 10.0 * np.log10(np.maximum(mel, 1e-10))
        maximum = float(np.max(decibels))
        decibels = np.maximum(decibels, maximum - 80.0) - maximum
        inputs[index, :, :, 0] = decibels.astype(np.float32, copy=False)
    return inputs, rms, starts


def _empty_comparison() -> dict[str, Any]:
    return {
        "similarity_score": 0.0,
        "compared_window_count": 0,
        "active_window_count": 0,
        "similarity_percentiles": {"p10": 0.0, "p50": 0.0, "p90": 0.0},
        "window_scores": [],
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rounded(value: float, digits: int = 8) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(value, digits)
