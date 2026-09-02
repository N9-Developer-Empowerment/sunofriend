from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from sunofriend import _remix_musicfm_loader as loader
from sunofriend._remix_musicfm_loader import FrozenAudioFeatureExtraction
from sunofriend.remix_musicfm_private_features import (
    MUSICFM_PRIVATE_FEATURE_REQUEST_SCHEMA,
    create_musicfm_private_feature_request,
    run_musicfm_private_features,
    validate_musicfm_private_feature_request,
    validate_musicfm_private_feature_result,
    verify_musicfm_private_feature_round_trip,
)
from sunofriend.remix_source_delta_dataset import (
    create_remix_source_delta_training_snapshot,
)
from sunofriend.source_receipt import document_sha256

from test_remix_source_delta_dataset import _example


ROOT = Path(__file__).parents[1]
WINDOWS_HANDOFF = ROOT / "scripts/run-remix-musicfm-private-features-windows.ps1"


def _snapshot_and_request(tmp_path: Path) -> tuple[dict, dict, dict]:
    example = _example(tmp_path)
    snapshot = create_remix_source_delta_training_snapshot(
        snapshot_id="private-features-001",
        examples=[{**example, "split": "train"}],
    )
    request = create_musicfm_private_feature_request(
        repository_commit="8" * 40,
        setup_receipt_sha256="7" * 64,
        setup_receipt_bytes=512,
        training_snapshot=snapshot,
        label_document_sha256=example["label"]["document_sha256"],
    )
    return example, snapshot, request


def _paths_for_request(example: dict, request: dict, staging: Path) -> dict[str, Path]:
    staging.mkdir()
    sources = tuple((example["render_root"] / "AUDIO").glob("*.wav"))
    by_hash = {
        hashlib.sha256(path.read_bytes()).hexdigest(): path for path in sources
    }
    paths = {}
    for row in request["inputs"]:
        target = staging / f"{row['role']}.wav"
        target.write_bytes(by_hash[row["audio_sha256"]].read_bytes())
        paths[row["role"]] = target
    return paths


def _rehash(document: dict) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)


def test_request_is_path_free_hash_bound_private_features_only(tmp_path: Path) -> None:
    _, snapshot, request = _snapshot_and_request(tmp_path)

    assert request["schema"] == MUSICFM_PRIVATE_FEATURE_REQUEST_SCHEMA
    assert validate_musicfm_private_feature_request(request, snapshot) == request
    assert [row["role"] for row in request["inputs"]] == [
        "control",
        "left",
        "right",
    ]
    assert request["binding"]["training_snapshot_sha256"] == snapshot["document_sha256"]
    assert request["authority"] == {
        "model_load_authorized": True,
        "private_audio_access_authorized": True,
        "frozen_feature_extraction_authorized": True,
        "training_execution_authorized": False,
        "checkpoint_promotion_authorized": False,
        "product_ordering_changed": False,
    }
    encoded = json.dumps(request, sort_keys=True)
    assert "/Users/" not in encoded
    assert "C:\\" not in encoded


@pytest.mark.parametrize("change", ("training", "network", "path", "audio"))
def test_request_rejects_rehashed_scope_or_identity_change(
    tmp_path: Path, change: str
) -> None:
    _, snapshot, request = _snapshot_and_request(tmp_path)
    changed = deepcopy(request)
    if change == "training":
        changed["authority"]["training_execution_authorized"] = True
    elif change == "network":
        changed["execution"]["network_allowed"] = True
    elif change == "path":
        changed["private_path"] = "C:\\Users\\owner\\private.wav"
    else:
        changed["inputs"][0]["audio_sha256"] = "9" * 64
    _rehash(changed)

    with pytest.raises(ValueError, match="changed"):
        validate_musicfm_private_feature_request(changed, snapshot)


def test_run_verifies_audio_and_writes_only_private_frozen_features(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    example, snapshot, request = _snapshot_and_request(tmp_path)
    paths = _paths_for_request(example, request, tmp_path / "isolated-inputs")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    output_parent = tmp_path / "outputs"
    output_parent.mkdir()
    monkeypatch.setattr(
        "sunofriend.remix_musicfm_private_features._verify_setup_receipt",
        lambda root, checked: {**checked["setup_receipt"], "packages": 26},
    )
    monkeypatch.setattr(
        "sunofriend.remix_musicfm_private_features._verify_runtime_assets",
        lambda root, commit: {"assets/pretrained_fma.pt": {"sha256": loader.CHECKPOINT_SHA256}},
    )

    def extract(root: Path, assets: dict, waveforms: dict, rates: dict) -> FrozenAudioFeatureExtraction:
        assert set(waveforms) == {"control", "left", "right"}
        assert set(rates.values()) == {
            request["inputs"][0]["geometry"]["sample_rate_hz"]
        }
        arrays = {role: np.zeros((1, 3, 1024), dtype=np.float32) for role in waveforms}
        metrics = {
            role: {
                "source_sample_rate_hz": rates[role],
                "source_frames": int(waveforms[role].shape[0]),
                "model_sample_rate_hz": 24_000,
                "model_frames": 24_000,
                "feature_shape": [1, 3, 1024],
                "feature_dtype": "float32",
                "finite": True,
                "feature_frames": 3,
                "feature_dimension": 1024,
                "feature_rate_hz": 3.0,
            }
            for role in waveforms
        }
        return FrozenAudioFeatureExtraction(
            features=arrays,
            metrics=metrics,
            loader=loader.expected_loader_evidence(state_tensor_count=500),
            environment={
                "torch_version": "2.7.1+cu128",
                "cuda_version": "12.8",
                "device_name": "NVIDIA GeForce RTX 4080 Laptop GPU",
                "cublas_workspace_config": ":4096:8",
            },
        )

    monkeypatch.setattr(
        "sunofriend.remix_musicfm_private_features.extract_audio_frozen_features",
        extract,
    )
    output = output_parent / "features"
    result = run_musicfm_private_features(
        request,
        snapshot,
        runtime_root=runtime,
        inputs=paths,
        out_dir=output,
    )

    assert validate_musicfm_private_feature_result(result, request, snapshot) == result
    verified = verify_musicfm_private_feature_round_trip(output, request, snapshot)
    assert verified["status"] == "verified_private_frozen_features_only"
    assert verified["private_audio_opened"] is True
    assert verified["training_started"] is False
    assert result["effects"]["model_weights_changed"] is False
    assert result["privacy"]["paths_embedded"] is False
    assert "/Users/" not in json.dumps(result, sort_keys=True)


def test_run_refuses_changed_audio_and_onedrive_staging(tmp_path: Path) -> None:
    example, snapshot, request = _snapshot_and_request(tmp_path)
    paths = _paths_for_request(example, request, tmp_path / "isolated-inputs")
    paths["left"].write_bytes(b"changed")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    output_parent = tmp_path / "outputs"
    output_parent.mkdir()
    with pytest.raises(ValueError, match="identity changed"):
        run_musicfm_private_features(
            request,
            snapshot,
            runtime_root=runtime,
            inputs=paths,
            out_dir=output_parent / "features",
        )

    onedrive = tmp_path / "OneDrive-private"
    safe_paths = _paths_for_request(example, request, onedrive)
    with pytest.raises(ValueError, match="outside OneDrive"):
        run_musicfm_private_features(
            request,
            snapshot,
            runtime_root=runtime,
            inputs=safe_paths,
            out_dir=output_parent / "features-2",
        )


def test_windows_handoff_only_stages_and_runs_bound_python_operation() -> None:
    source = WINDOWS_HANDOFF.read_text(encoding="utf-8")
    assert "outside OneDrive" in source
    assert source.count("Copy-Item -LiteralPath") == 5
    assert "run-remix-musicfm-private-features.py" in source
    assert "--control" in source and "--left" in source and "--right" in source
    assert "optimizer" not in source.lower()
    assert "torch.distributed" not in source.lower()


def test_loader_extracts_each_role_once_with_local_resampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Tensor:
        def __init__(self, values: np.ndarray) -> None:
            self.values = np.asarray(values, dtype=np.float32)
            self.dtype = "float32"

        @property
        def ndim(self) -> int:
            return self.values.ndim

        @property
        def shape(self) -> tuple[int, ...]:
            return self.values.shape

        def numel(self) -> int:
            return self.values.size

        def unsqueeze(self, axis: int) -> "Tensor":
            return Tensor(np.expand_dims(self.values, axis))

        def to(self, device: object) -> "Tensor":
            return self

        def float(self) -> "Tensor":
            return self

        def cpu(self) -> "Tensor":
            return self

        def numpy(self) -> np.ndarray:
            return self.values

    class Truth:
        def all(self) -> bool:
            return True

    class Cuda:
        @staticmethod
        def is_available() -> bool:
            return True

        @staticmethod
        def get_device_name(index: int) -> str:
            assert index == 0
            return "NVIDIA GeForce RTX 4080 Laptop GPU"

    class Cudnn:
        benchmark = True
        deterministic = False

    class Backends:
        cudnn = Cudnn()

    class Torch:
        float32 = "float32"
        __version__ = "2.7.1+cu128"
        version = type("Version", (), {"cuda": "12.8"})()
        cuda = Cuda()
        backends = Backends()

        @staticmethod
        def as_tensor(values: np.ndarray, dtype: str) -> Tensor:
            assert dtype == "float32"
            return Tensor(values)

        @staticmethod
        def isfinite(value: Tensor) -> Truth:
            return Truth()

        @staticmethod
        def use_deterministic_algorithms(enabled: bool) -> None:
            assert enabled is True

        @staticmethod
        def device(name: str) -> str:
            assert name == "cuda"
            return name

        @staticmethod
        @contextmanager
        def inference_mode():
            yield

    class Model:
        def to(self, device: str) -> "Model":
            return self

        def get_latent(self, waveform: Tensor, layer_ix: int) -> Tensor:
            assert waveform.ndim == 2
            assert layer_ix == 7
            return Tensor(np.zeros((1, 5, 1024), dtype=np.float32))

    class Functional:
        @staticmethod
        def resample(waveform: Tensor, source_rate: int, target_rate: int) -> Tensor:
            size = round(waveform.numel() * target_rate / source_rate)
            return Tensor(np.zeros(size, dtype=np.float32))

    fake_torch = Torch()
    monkeypatch.setattr(
        loader,
        "_load_restricted_model",
        lambda root, assets: (
            Model(),
            fake_torch,
            loader.expected_loader_evidence(state_tensor_count=500),
        ),
    )
    monkeypatch.setattr(
        loader.importlib,
        "import_module",
        lambda name: type("Torchaudio", (), {"functional": Functional()})(),
    )
    waveforms = {
        role: np.zeros(48_000, dtype=np.float32)
        for role in ("control", "left", "right")
    }

    result = loader.extract_audio_frozen_features(
        Path("runtime"),
        {"assets/pretrained_fma.pt": {"sha256": loader.CHECKPOINT_SHA256}},
        waveforms,
        {role: 48_000 for role in waveforms},
    )

    assert set(result.features) == {"control", "left", "right"}
    assert all(value.shape == (1, 5, 1024) for value in result.features.values())
    assert result.metrics["control"]["model_frames"] == 24_000
    assert result.metrics["control"]["feature_rate_hz"] == 5.0
    assert result.environment["device_name"] == "NVIDIA GeForce RTX 4080 Laptop GPU"
