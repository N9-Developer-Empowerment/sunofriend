#!/usr/bin/env python3
"""Construct and strictly load the two approved query-challenger models.

This is deliberately a construction/load gate, not an inference worker. It
does not accept an audio path and never calls either model. The state-compatible
Banquet topology follows the MIT-licensed pinned Query Bandit source revision
recorded in the shared pure evidence contract.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import hashlib
import json
import math
from pathlib import Path
import socket
import sys
from typing import Any
import urllib.request

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

import numpy as np
import torch
from torch import nn
import torchaudio

from hear21passt.base import AugmentMelSTFT, PasstBasicWrapper
from hear21passt.models.passt import get_model as get_passt_model

from sunofriend.separation_other_refinement_query_load_contract import (
    EXPECTED_CHECKPOINTS,
    EXPECTED_MODEL_STATES,
    QUERY_BANDIT_SOURCE_REVISION,
    QUERY_MODEL_LOAD_REPORT_SCHEMA,
    QUERY_MODEL_LOAD_REPORT_STATUS,
    query_model_load_report_sha256,
)

EXPECTED = {
    label: {
        "filename": checkpoint["file"],
        "bytes": checkpoint["bytes"],
        "sha256": checkpoint["sha256"],
        **EXPECTED_MODEL_STATES[label],
    }
    for label, checkpoint in EXPECTED_CHECKPOINTS.items()
}
AUDIO_SUFFIXES = (".aac", ".aif", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".wav")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _state_dict(document: Any, label: str) -> dict[str, torch.Tensor]:
    candidate = document.get("state_dict") if isinstance(document, dict) else None
    if candidate is None and isinstance(document, dict):
        candidate = document
    if not isinstance(candidate, dict) or not candidate:
        raise RuntimeError(f"{label} checkpoint has no state dictionary")
    if any(not isinstance(key, str) for key in candidate):
        raise RuntimeError(f"{label} state dictionary contains a non-string key")
    if any(not torch.is_tensor(value) for value in candidate.values()):
        raise RuntimeError(f"{label} state dictionary contains a non-tensor value")
    return candidate


def _inventory(state: dict[str, torch.Tensor]) -> dict[str, Any]:
    tensors = {
        key: {
            "shape": list(value.shape),
            "dtype": str(value.dtype),
            "numel": value.numel(),
            "device": str(value.device),
            "requires_grad": bool(value.requires_grad),
        }
        for key, value in sorted(state.items())
    }
    return {
        "key_count": len(tensors),
        "total_numel": sum(value["numel"] for value in tensors.values()),
        "inventory_sha256": hashlib.sha256(
            json.dumps(tensors, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }


def _verify_state_contract(
    label: str,
    model_state: dict[str, torch.Tensor],
    checkpoint_state: dict[str, torch.Tensor],
) -> dict[str, Any]:
    model_keys = set(model_state)
    checkpoint_keys = set(checkpoint_state)
    missing = sorted(model_keys - checkpoint_keys)
    unexpected = sorted(checkpoint_keys - model_keys)
    if missing or unexpected:
        raise RuntimeError(
            f"{label} state keys differ: missing={missing[:8]}, unexpected={unexpected[:8]}"
        )
    shape_mismatches = []
    dtype_mismatches = []
    for key in sorted(model_keys):
        if model_state[key].shape != checkpoint_state[key].shape:
            shape_mismatches.append(
                {
                    "key": key,
                    "model": list(model_state[key].shape),
                    "checkpoint": list(checkpoint_state[key].shape),
                }
            )
        if model_state[key].dtype != checkpoint_state[key].dtype:
            dtype_mismatches.append(
                {
                    "key": key,
                    "model": str(model_state[key].dtype),
                    "checkpoint": str(checkpoint_state[key].dtype),
                }
            )
    if shape_mismatches or dtype_mismatches:
        raise RuntimeError(
            f"{label} state tensor contracts differ: "
            f"shape={shape_mismatches[:4]}, dtype={dtype_mismatches[:4]}"
        )
    inventory = _inventory(checkpoint_state)
    expected = EXPECTED[label]
    for field in ("inventory_sha256", "key_count", "total_numel"):
        if inventory[field] != expected[field]:
            raise RuntimeError(f"{label} checkpoint {field} differs")
    return {
        "keys_equal": True,
        "shapes_equal": True,
        "dtypes_equal": True,
        **inventory,
    }


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


def _new_passt(*, n_classes: int) -> nn.Module:
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
            net=_new_passt(n_classes=527),
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


def _construct_and_load(
    paths: dict[str, Path],
    load_calls: list[str],
) -> dict[str, Any]:
    passt_document = torch.load(
        paths["passt"],
        weights_only=True,
        map_location="cpu",
    )
    passt_state = _state_dict(passt_document, "passt")
    passt_model = _new_passt(n_classes=20).eval()
    passt_contract = _verify_state_contract(
        "passt", passt_model.state_dict(), passt_state
    )
    passt_result = passt_model.load_state_dict(passt_state, strict=True)
    if passt_result.missing_keys or passt_result.unexpected_keys:
        raise RuntimeError("PaSST strict load returned unresolved keys")
    del passt_document
    del passt_state

    banquet_document = torch.load(
        paths["banquet"],
        weights_only=True,
        map_location="cpu",
    )
    raw_banquet_state = _state_dict(banquet_document, "banquet")
    if not all(key.startswith("model.") for key in raw_banquet_state):
        raise RuntimeError("Banquet checkpoint state is not rooted at model")
    banquet_state = {key.removeprefix("model."): value for key, value in raw_banquet_state.items()}
    banquet_model = BanquetLoadAdapter().eval()
    banquet_contract = _verify_state_contract(
        "banquet",
        {f"model.{key}": value for key, value in banquet_model.state_dict().items()},
        raw_banquet_state,
    )
    banquet_result = banquet_model.load_state_dict(banquet_state, strict=True)
    if banquet_result.missing_keys or banquet_result.unexpected_keys:
        raise RuntimeError("Banquet strict load returned unresolved keys")
    del banquet_document
    del raw_banquet_state
    del banquet_state

    if load_calls != [str(paths["passt"]), str(paths["banquet"])]:
        raise RuntimeError("restricted model load order differs")
    return {
        "passt": {
            **passt_contract,
            "architecture": "OpenMIC PaSST, pretrained=False, 20 classes",
            "strict_load_missing_keys": [],
            "strict_load_unexpected_keys": [],
        },
        "banquet": {
            **banquet_contract,
            "architecture": (
                "pinned setup-C PasstFiLMConditionedBandit load adapter, "
                "64 musical bands, 8 sequential band modules, embedded "
                "OpenMIC PaSST pretrained=False with 527 classes"
            ),
            "checkpoint_root_prefix_removed_for_load": "model.",
            "strict_load_missing_keys": [],
            "strict_load_unexpected_keys": [],
        },
        "models_retained_until_process_exit": bool(passt_model and banquet_model),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--banquet", type=Path, required=True)
    parser.add_argument("--passt", type=Path, required=True)
    args = parser.parse_args()
    paths = {"banquet": args.banquet.resolve(), "passt": args.passt.resolve()}
    allowed_checkpoint_paths = frozenset(paths.values())
    network_attempts: list[str] = []
    audio_open_attempts: list[str] = []
    checkpoint_open_attempts: list[str] = []
    load_calls: list[str] = []

    def audit(event: str, event_args: tuple[Any, ...]) -> None:
        if event.startswith("socket."):
            network_attempts.append(event)
            raise RuntimeError(f"network operation forbidden during model load: {event}")
        if event == "open" and event_args:
            target = event_args[0]
            if isinstance(target, (str, bytes)):
                path = Path(target).resolve()
                text = str(path).lower()
                if text.endswith(AUDIO_SUFFIXES):
                    audio_open_attempts.append(text)
                    raise RuntimeError("audio open forbidden during model load")
                if text.endswith((".ckpt", ".pt", ".pth", ".safetensors")):
                    if path not in allowed_checkpoint_paths:
                        checkpoint_open_attempts.append(text)
                        raise RuntimeError("unapproved checkpoint open during model load")

    sys.addaudithook(audit)

    def deny_network(*_args: Any, **_kwargs: Any) -> Any:
        network_attempts.append("python_network_api")
        raise RuntimeError("network API forbidden during model load")

    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    urllib.request.urlopen = deny_network

    for label, path in paths.items():
        expected = EXPECTED[label]
        if path.name != expected["filename"]:
            raise RuntimeError(f"{label} checkpoint filename differs")
        if path.stat().st_size != expected["bytes"] or _sha256(path) != expected["sha256"]:
            raise RuntimeError(f"{label} checkpoint identity differs")

    real_torch_load = torch.load

    def restricted_torch_load(path: str | Path, *args: Any, **kwargs: Any) -> Any:
        resolved = Path(path).resolve()
        if resolved not in allowed_checkpoint_paths:
            raise RuntimeError("torch.load path is outside the two approved checkpoints")
        if args or kwargs != {"weights_only": True, "map_location": "cpu"}:
            raise RuntimeError("torch.load must use the exact weights-only CPU contract")
        load_calls.append(str(resolved))
        return real_torch_load(resolved, weights_only=True, map_location="cpu")

    torch.load = restricted_torch_load
    models = _construct_and_load(paths, load_calls)
    if network_attempts or audio_open_attempts or checkpoint_open_attempts:
        raise RuntimeError("restricted model load crossed an effects boundary")

    report: dict[str, Any] = {
        "schema": QUERY_MODEL_LOAD_REPORT_SCHEMA,
        "report_sha256": "",
        "status": QUERY_MODEL_LOAD_REPORT_STATUS,
        "source_revision": QUERY_BANDIT_SOURCE_REVISION,
        "runtime": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "torchaudio": torchaudio.__version__,
            "numpy": np.__version__,
        },
        "checkpoints": {
            label: {
                "file": expected["filename"],
                "bytes": expected["bytes"],
                "sha256": expected["sha256"],
            }
            for label, expected in EXPECTED.items()
        },
        "models": models,
        "guards": {
            "os_network_denial_required": True,
            "network_attempts": len(network_attempts),
            "audio_open_attempts": len(audio_open_attempts),
            "unapproved_checkpoint_open_attempts": len(checkpoint_open_attempts),
            "restricted_torch_load_calls": len(load_calls),
            "pretrained_network_resolution": False,
        },
        "effects": {
            "checkpoint_loaded": True,
            "model_constructed": True,
            "inference_runs": 0,
            "audio_reads": 0,
            "audio_writes": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
        },
    }
    report["report_sha256"] = query_model_load_report_sha256(report)
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
