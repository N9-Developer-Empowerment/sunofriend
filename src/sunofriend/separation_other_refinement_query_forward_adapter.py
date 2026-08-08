"""Single-use, source-pinned Banquet forward adapter.

The restricted checkpoint loader intentionally exposes no ``forward`` method.
This module supplies the separately authorised tensor math while retaining a
hard one-call boundary.  It accepts tensors only and has no path, audio-file,
network, registry, source-selection or MIDI interface.
"""

from __future__ import annotations

import torch

from .separation_other_refinement_query_model_adapter import (
    BanquetLoadAdapter,
    _musical_bands,
)


def _band_split(model: BanquetLoadAdapter, spectrogram: torch.Tensor) -> torch.Tensor:
    band_specs, _ = _musical_bands()
    batch, _channels, _frequencies, frames = spectrogram.shape
    embedding = torch.zeros(
        (batch, len(band_specs), frames, 128),
        device=spectrogram.device,
        dtype=spectrogram.real.dtype,
    )
    real = torch.view_as_real(spectrogram).permute(0, 3, 1, 4, 2)
    batch, frames, channels, _real_imag, _frequencies = real.shape
    for index, module in enumerate(model.band_split.norm_fc_modules):
        start, end = band_specs[index]
        band = real[..., start:end].reshape(batch, frames, channels, -1)
        band = module.norm(band.reshape(batch, frames, -1))
        embedding[:, index, :, :] = module.fc(band)
    return embedding


def _time_frequency_model(model: BanquetLoadAdapter, value: torch.Tensor) -> torch.Tensor:
    for module in model.tf_model.seqband:
        residual = value.clone()
        value = module.norm(value)
        batch, uncrossed, across, embedding = value.shape
        value = value.reshape(batch * uncrossed, across, embedding)
        value = module.rnn(value.contiguous())[0]
        value = value.reshape(batch, uncrossed, across, -1)
        value = module.fc(value) + residual
        value = value.transpose(1, 2)
    return value


def _query_embedding(model: BanquetLoadAdapter, query: torch.Tensor) -> torch.Tensor:
    query = torch.mean(query, dim=1)
    query = model.query_encoder.resample(query)
    spectrogram = model.query_encoder.passt.mel(query)[..., :998]
    _logits, embedding = model.query_encoder.passt.net(spectrogram[:, None, ...])
    return embedding


def _condition(
    model: BanquetLoadAdapter,
    encoded_mixture: torch.Tensor,
    query_embedding: torch.Tensor,
) -> torch.Tensor:
    value = encoded_mixture.permute(0, 3, 1, 2)
    value = model.film.gn(value)
    gamma = model.film.gamma(query_embedding)[:, :, None, None]
    beta = model.film.beta(query_embedding)[:, :, None, None]
    value = gamma * value
    value = value + beta
    return value.permute(0, 2, 3, 1)


def _estimate_mask(model: BanquetLoadAdapter, value: torch.Tensor) -> torch.Tensor:
    band_specs, _ = _musical_bands()
    batch, _bands, frames, _embedding = value.shape
    masks = torch.zeros(
        (batch, 2, 1_025, frames),
        device=value.device,
        dtype=torch.complex64,
    )
    for index, module in enumerate(model.mask_estim.norm_mlp):
        start, end = band_specs[index]
        band = module.norm(value[:, index, :, :])
        band = module.hidden(band)
        band = module.output(band)
        band = band.reshape(batch, frames, 2, end - start, 2).contiguous()
        band = torch.view_as_complex(band).permute(0, 2, 3, 1)
        weights = model.mask_estim.get_buffer(f"freq_weights/{index}")[:, None]
        masks[:, :, start:end, :] += band * weights
    return masks


def _source_pinned_forward(
    model: BanquetLoadAdapter,
    mixture: torch.Tensor,
    query: torch.Tensor,
) -> torch.Tensor:
    mixture_spectrogram = model.stft(mixture)
    encoded = _band_split(model, mixture_spectrogram)
    encoded = _time_frequency_model(model, encoded)
    query_embedding = _query_embedding(model, query)
    conditioned = _condition(model, encoded, query_embedding)
    mask = _estimate_mask(model, conditioned)
    target_spectrogram = mixture_spectrogram * mask
    return model.istft(target_spectrogram.reshape(mixture_spectrogram.shape), mixture.shape[-1])


class SingleUseBanquetForward:
    """Permit exactly one tensor-forward attempt for one loaded adapter."""

    def __init__(self, model: BanquetLoadAdapter) -> None:
        self._model = model
        self._attempted = False

    @property
    def attempted(self) -> bool:
        return self._attempted

    def run_once(self, mixture: torch.Tensor, query: torch.Tensor) -> torch.Tensor:
        if self._attempted:
            raise RuntimeError("Banquet synthetic forward has already been attempted")
        self._attempted = True
        return _source_pinned_forward(self._model, mixture, query)


__all__ = ["SingleUseBanquetForward"]
