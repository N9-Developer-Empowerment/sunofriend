"""State-compatible Banquet setup-C topology with no inference entrypoint.

This module intentionally defines model construction only.  It has no forward
method, checkpoint path, audio path, CLI, publication or MIDI integration.  A
separately approved synthetic runner may later extend the topology without
coupling inference authority to the evidence loader.
"""

from __future__ import annotations

from contextlib import redirect_stdout
import math
import sys

import numpy as np
import torch
from torch import nn
import torchaudio

from hear21passt.base import AugmentMelSTFT, PasstBasicWrapper
from hear21passt.models.passt import get_model as get_passt_model


def _hz_to_midi(hertz: float | np.ndarray) -> float | np.ndarray:
    return 69.0 + 12.0 * np.log2(np.asarray(hertz) / 440.0)


def _midi_to_hz(midi: float | np.ndarray) -> float | np.ndarray:
    return 440.0 * np.power(2.0, (np.asarray(midi) - 69.0) / 12.0)


def _musical_bands(
    *, n_bands: int = 64, sample_rate: int = 44_100, n_fft: int = 2_048
) -> tuple[list[tuple[int, int]], list[torch.Tensor]]:
    n_freqs = n_fft // 2 + 1
    bin_hz = sample_rate / n_fft
    minimum_hz = bin_hz
    maximum_hz = sample_rate / 2
    octaves_per_band = math.log2(maximum_hz / minimum_hz) / n_bands
    bandwidth_multiplier = math.pow(2.0, octaves_per_band)
    midi_points = np.linspace(
        max(0.0, float(_hz_to_midi(minimum_hz))),
        float(_hz_to_midi(maximum_hz)),
        n_bands,
    )
    centre_hz = _midi_to_hz(midi_points)
    low_bins = np.floor((centre_hz / bandwidth_multiplier) / bin_hz).astype(int)
    high_bins = np.ceil((centre_hz * bandwidth_multiplier) / bin_hz).astype(int)
    filterbank = np.zeros((n_bands, n_freqs), dtype=np.float64)
    for index in range(n_bands):
        filterbank[index, low_bins[index] : high_bins[index] + 1] = 1.0
    filterbank[0, : low_bins[0]] = 1.0
    filterbank[-1, high_bins[-1] + 1 :] = 1.0
    weight_per_bin = np.sum(filterbank, axis=0, keepdims=True)
    if np.any(weight_per_bin == 0):
        raise RuntimeError("musical band construction left an uncovered frequency bin")
    normalized = filterbank / weight_per_bin
    specs: list[tuple[int, int]] = []
    weights: list[torch.Tensor] = []
    for index in range(n_bands):
        active = np.flatnonzero(filterbank[index])
        if active.size == 0:
            continue
        start = int(active[0])
        end = int(active[-1]) + 1
        specs.append((start, end))
        weights.append(torch.as_tensor(normalized[index, start:end]))
    if len(specs) != n_bands:
        raise RuntimeError("musical band construction produced the wrong band count")
    return specs, weights


class _NormFC(nn.Module):
    def __init__(self, bandwidth: int) -> None:
        super().__init__()
        self.norm = nn.LayerNorm(2 * bandwidth * 2)
        self.fc = nn.Linear(2 * bandwidth * 2, 128)


class _BandSplit(nn.Module):
    def __init__(self, band_specs: list[tuple[int, int]]) -> None:
        super().__init__()
        self.norm_fc_modules = nn.ModuleList(
            [_NormFC(end - start) for start, end in band_specs]
        )


class _ResidualGRU(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.norm = nn.LayerNorm(128)
        self.rnn = nn.GRU(
            input_size=128,
            hidden_size=256,
            num_layers=1,
            batch_first=True,
            bidirectional=True,
        )
        self.fc = nn.Linear(512, 128)


class _TFModel(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.seqband = nn.ModuleList([_ResidualGRU() for _ in range(16)])


class _NormMLP(nn.Module):
    def __init__(self, bandwidth: int) -> None:
        super().__init__()
        self.norm = nn.LayerNorm(128)
        self.hidden = nn.Sequential(nn.Linear(128, 512), nn.Tanh())
        self.output = nn.Sequential(nn.Linear(512, bandwidth * 2 * 2 * 2), nn.GLU())


class _MaskEstimator(nn.Module):
    def __init__(
        self,
        band_specs: list[tuple[int, int]],
        frequency_weights: list[torch.Tensor],
    ) -> None:
        super().__init__()
        self.norm_mlp = nn.ModuleList(
            [_NormMLP(end - start) for start, end in band_specs]
        )
        for index, weight in enumerate(frequency_weights):
            self.register_buffer(f"freq_weights/{index}", weight)


def new_passt(*, n_classes: int) -> nn.Module:
    """Construct the exact download-disabled OpenMIC PaSST topology."""

    with redirect_stdout(sys.stderr):
        return get_passt_model(
            arch="openmic",
            pretrained=False,
            n_classes=n_classes,
            in_channels=1,
            fstride=10,
            tstride=10,
            input_fdim=128,
            input_tdim=998,
            u_patchout=0,
            s_patchout_t=0,
            s_patchout_f=0,
        )


class _QueryEncoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        with redirect_stdout(sys.stderr):
            mel = AugmentMelSTFT(
                n_mels=128,
                sr=32_000,
                win_length=800,
                hopsize=320,
                n_fft=1_024,
                freqm=48,
                timem=192,
                htk=False,
                fmin=0.0,
                fmax=None,
                norm=1,
                fmin_aug_range=10,
                fmax_aug_range=2_000,
            )
        self.passt = PasstBasicWrapper(
            mel=mel,
            net=new_passt(n_classes=527),
            mode="embed_only",
            arch="openmic",
        ).eval()
        self.resample = torchaudio.transforms.Resample(
            orig_freq=44_100,
            new_freq=32_000,
        ).eval()


class _FiLM(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.gn = nn.GroupNorm(8, 128)
        self.gamma = nn.Sequential(nn.Linear(768, 128), nn.ELU(), nn.Linear(128, 128))
        self.beta = nn.Sequential(nn.Linear(768, 128), nn.ELU(), nn.Linear(128, 128))


class BanquetLoadAdapter(nn.Module):
    """State-compatible pinned Banquet setup-C adapter with no forward method."""

    def __init__(self) -> None:
        super().__init__()
        self.stft = torchaudio.transforms.Spectrogram(
            n_fft=2_048,
            win_length=2_048,
            hop_length=512,
            pad_mode="reflect",
            pad=0,
            window_fn=torch.hann_window,
            wkwargs=None,
            power=None,
            normalized=True,
            center=True,
            onesided=True,
        )
        self.istft = torchaudio.transforms.InverseSpectrogram(
            n_fft=2_048,
            win_length=2_048,
            hop_length=512,
            pad_mode="reflect",
            pad=0,
            window_fn=torch.hann_window,
            wkwargs=None,
            normalized=True,
            center=True,
            onesided=True,
        )
        band_specs, frequency_weights = _musical_bands()
        self.band_split = _BandSplit(band_specs)
        self.tf_model = _TFModel()
        self.mask_estim = _MaskEstimator(band_specs, frequency_weights)
        self.query_encoder = _QueryEncoder()
        self.film = _FiLM()


__all__ = ["BanquetLoadAdapter", "new_passt"]
