"""Offline, weights-only compatibility inspection for the pinned SCNet release.

This module never runs a model forward pass or reads audio.  The setup script
invokes it inside a macOS network-denial sandbox after verifying every staged
artifact and installing the exact isolated runtime.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import resource
import sys
import types
from typing import Any


SCNET_COMPATIBILITY_SCHEMA = "sunofriend.scnet-compatibility.v1"
PROFILE_ID = "scnet-large-musdb-release-v1"
SOURCE_REVISION = "6236f8c559778dc271e1aea9baa3993ae655e905"
EXPECTED_ROLES = ("drums", "bass", "other", "vocals")
EXPECTED_SAMPLE_RATE = 44_100
EXPECTED_CHANNELS = 2
EXPECTED_PARAMETER_COUNT = 42_181_232
EXPECTED_STATE_BYTES = 168_724_928
CHECKPOINT_CAP_BYTES = 1_073_741_824

EXPECTED_PACKAGES = {
    "filelock": "3.32.2",
    "fsspec": "2026.7.0",
    "Jinja2": "3.1.6",
    "MarkupSafe": "3.0.3",
    "mpmath": "1.3.0",
    "networkx": "3.6.1",
    "numpy": "2.5.1",
    "PyYAML": "6.0.3",
    "setuptools": "83.0.0",
    "sympy": "1.14.0",
    "torch": "2.8.0",
    "typing-extensions": "4.16.0",
}

EXPECTED_ARTIFACTS = {
    "model/SCNet-large.th": (
        168_848_417,
        "719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070",
    ),
    "model/scnet-large-config.yaml": (
        1_080,
        "629a4901184bf1d3a75b0b13904f35974785aa042cad3c010fd576248cdce3f0",
    ),
    "TERMS/SCNet-LICENSE": (
        1_067,
        "0bdf1b69335198118ab16cfc50d337b496b8c6d90e83beeaba4643781ab62513",
    ),
    "TERMS/SCNet-README.md": (
        2_031,
        "5216a5b0ae85715f7eedbadda4d8d71dd063fb2bc40ba2a90cb61cf3458136dc",
    ),
    "TERMS/SCNet-requirements.txt": (
        136,
        "892a58352a75ee9d6cd98c68de9a4b6c733fb4f2e5788f3c6bd2b07676c2b66f",
    ),
    "source/scnet/SCNet.py": (
        13_853,
        "5e77c363f7f0187432a984d8ae1aa511826295d732372f0c280e68e4fecd4550",
    ),
    "source/scnet/separation.py": (
        3_783,
        "43402dc6579436d3b5abb921990572684beed8fa10b377a112892b438f40713b",
    ),
}


class CompatibilityError(RuntimeError):
    """A bounded, objective compatibility gate failed."""


def _hash_regular_file(path: Path, *, expected_bytes: int) -> str:
    if path.is_symlink() or not path.is_file():
        raise CompatibilityError(f"artifact is not a regular file: {path.name}")
    observed_bytes = path.stat().st_size
    if observed_bytes != expected_bytes:
        raise CompatibilityError(
            f"artifact byte mismatch for {path.name}: "
            f"expected {expected_bytes}, got {observed_bytes}"
        )
    digest = hashlib.sha256()
    read_bytes = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            read_bytes += len(chunk)
            if read_bytes > expected_bytes:
                raise CompatibilityError(f"artifact grew while hashing: {path.name}")
            digest.update(chunk)
    if read_bytes != expected_bytes:
        raise CompatibilityError(f"artifact changed while hashing: {path.name}")
    return digest.hexdigest()


def _verify_artifacts(root: Path) -> dict[str, dict[str, Any]]:
    verified: dict[str, dict[str, Any]] = {}
    for relative_path, (expected_bytes, expected_sha256) in EXPECTED_ARTIFACTS.items():
        path = root / relative_path
        observed_sha256 = _hash_regular_file(path, expected_bytes=expected_bytes)
        if observed_sha256 != expected_sha256:
            raise CompatibilityError(
                f"artifact SHA-256 mismatch for {relative_path}: "
                f"expected {expected_sha256}, got {observed_sha256}"
            )
        verified[relative_path] = {
            "bytes": expected_bytes,
            "sha256": expected_sha256,
        }
    return verified


def _load_release_module(root: Path) -> Any:
    package_name = "sunofriend_scnet_release"
    package = types.ModuleType(package_name)
    package.__path__ = [str(root / "source/scnet")]
    sys.modules[package_name] = package
    for module_name, filename in (
        (f"{package_name}.separation", "separation.py"),
        (f"{package_name}.SCNet", "SCNet.py"),
    ):
        spec = importlib.util.spec_from_file_location(
            module_name, root / "source/scnet" / filename
        )
        if spec is None or spec.loader is None:
            raise CompatibilityError(f"cannot load pinned source module: {filename}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return sys.modules[f"{package_name}.SCNet"]


def _state_mapping(
    package: Any,
    *,
    tensor_type: type[Any],
) -> tuple[Mapping[str, Any], str, int]:
    if isinstance(package, Mapping) and package and all(
        isinstance(key, str) and isinstance(value, tensor_type)
        for key, value in package.items()
    ):
        return package, "direct_state_dict", 0
    if isinstance(package, Mapping) and "state" in package:
        state = package["state"]
        if isinstance(state, Mapping) and state and all(
            isinstance(key, str) and isinstance(value, tensor_type)
            for key, value in state.items()
        ):
            return state, "official_state_wrapper", 0
    if isinstance(package, Mapping) and "best_state" in package:
        best_state = package["best_state"]
        if isinstance(best_state, Mapping) and best_state and all(
            isinstance(key, str) and isinstance(value, tensor_type)
            for key, value in best_state.items()
        ):
            return best_state, "official_best_state_wrapper", 1
    raise CompatibilityError(
        "checkpoint is not a direct tensor state dict or one of the two "
        "documented official release wrappers"
    )


def _normalize_uniform_prefix(
    state: Mapping[str, Any], expected_keys: set[str]
) -> tuple[dict[str, Any], str | None, int]:
    observed_keys = set(state)
    if observed_keys == expected_keys:
        return dict(state), None, 0
    for prefix in ("module.", "model.", "_orig_mod."):
        if all(key.startswith(prefix) for key in observed_keys):
            normalized = {key[len(prefix) :]: value for key, value in state.items()}
            if set(normalized) == expected_keys:
                return normalized, prefix, 1
    missing = sorted(expected_keys - observed_keys)
    unexpected = sorted(observed_keys - expected_keys)
    raise CompatibilityError(
        "strict state-dict keys differ after the one allowed uniform-prefix "
        f"remediation; missing={missing[:8]!r}, unexpected={unexpected[:8]!r}"
    )


def inspect_scnet_compatibility(root: str | Path) -> dict[str, Any]:
    """Verify and strictly bind the checkpoint without running inference."""

    checked_root = Path(root).resolve(strict=True)
    verified_artifacts = _verify_artifacts(checked_root)
    checkpoint = checked_root / "model/SCNet-large.th"
    if checkpoint.stat().st_size > CHECKPOINT_CAP_BYTES:
        raise CompatibilityError("checkpoint exceeds the approved 1 GiB cap")

    actual_packages = {
        name: importlib.metadata.version(name) for name in EXPECTED_PACKAGES
    }
    if actual_packages != EXPECTED_PACKAGES:
        raise CompatibilityError(
            f"runtime package mismatch: expected {EXPECTED_PACKAGES!r}, "
            f"got {actual_packages!r}"
        )

    import torch
    import yaml

    if torch.__version__ != "2.8.0":
        raise CompatibilityError(f"unexpected torch version: {torch.__version__}")
    config = yaml.safe_load(
        (checked_root / "model/scnet-large-config.yaml").read_text(
            encoding="utf-8"
        )
    )
    if not isinstance(config, Mapping) or not isinstance(config.get("model"), Mapping):
        raise CompatibilityError("SCNet config lacks a model mapping")
    if config.get("data", {}).get("samplerate") != EXPECTED_SAMPLE_RATE:
        raise CompatibilityError("SCNet config sample rate differs from 44100")
    if config.get("data", {}).get("channels") != EXPECTED_CHANNELS:
        raise CompatibilityError("SCNet config channel count differs from two")
    if tuple(config["model"].get("sources", ())) != EXPECTED_ROLES:
        raise CompatibilityError("SCNet config roles differ from the exact four roles")

    source_module = _load_release_module(checked_root)
    torch.set_grad_enabled(False)
    model = source_module.SCNet(**dict(config["model"]))
    expected_state = model.state_dict()
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    state_bytes = sum(
        value.numel() * value.element_size() for value in expected_state.values()
    )
    if parameter_count != EXPECTED_PARAMETER_COUNT or state_bytes != EXPECTED_STATE_BYTES:
        raise CompatibilityError(
            "constructed release architecture identity differs from the reviewed plan"
        )

    package = torch.load(
        checkpoint,
        map_location="cpu",
        weights_only=True,
        mmap=True,
    )
    state, checkpoint_container, wrapper_remediation_cycles = _state_mapping(
        package,
        tensor_type=torch.Tensor,
    )
    normalized_state, removed_prefix, prefix_remediation_cycles = (
        _normalize_uniform_prefix(
        state, set(expected_state)
        )
    )
    remediation_cycles = wrapper_remediation_cycles + prefix_remediation_cycles
    if remediation_cycles > 1:
        raise CompatibilityError(
            "checkpoint requires more than the one permitted transparent "
            "wrapper/prefix remediation"
        )
    for key, expected in expected_state.items():
        observed = normalized_state[key]
        if tuple(observed.shape) != tuple(expected.shape):
            raise CompatibilityError(
                f"state tensor shape mismatch for {key}: "
                f"expected {tuple(expected.shape)}, got {tuple(observed.shape)}"
            )
        if observed.dtype != expected.dtype:
            raise CompatibilityError(
                f"state tensor dtype mismatch for {key}: "
                f"expected {expected.dtype}, got {observed.dtype}"
            )
    model.load_state_dict(normalized_state, strict=True)

    return {
        "schema": SCNET_COMPATIBILITY_SCHEMA,
        "status": "passed",
        "profile_id": PROFILE_ID,
        "source_revision": SOURCE_REVISION,
        "runtime_packages": actual_packages,
        "artifacts": verified_artifacts,
        "checkpoint": {
            "bytes": EXPECTED_ARTIFACTS["model/SCNet-large.th"][0],
            "sha256": EXPECTED_ARTIFACTS["model/SCNet-large.th"][1],
            "weights_only": True,
            "map_location": "cpu",
            "mmap": True,
            "container": checkpoint_container,
            "state_key_count": len(normalized_state),
            "removed_uniform_prefix": removed_prefix,
        },
        "compatibility": {
            "strict_state_dict": True,
            "roles": list(EXPECTED_ROLES),
            "sample_rate": EXPECTED_SAMPLE_RATE,
            "channels": EXPECTED_CHANNELS,
            "parameter_count": parameter_count,
            "state_dict_bytes": state_bytes,
            "remediation_cycles": remediation_cycles,
            "maximum_remediation_cycles": 1,
        },
        "effects": {
            "network_denied_by_parent_sandbox": True,
            "checkpoint_deserialized": True,
            "custom_pickle_globals_allowed": False,
            "forward_passes": 0,
            "audio_reads": [],
            "inference_runs": 0,
            "outputs_published": [],
        },
        "maximum_resident_set_bytes": resource.getrusage(
            resource.RUSAGE_SELF
        ).ru_maxrss,
    }


def compatibility_failure_record(error: Exception) -> dict[str, Any]:
    return {
        "schema": SCNET_COMPATIBILITY_SCHEMA,
        "status": "failed",
        "profile_id": PROFILE_ID,
        "source_revision": SOURCE_REVISION,
        "error_type": type(error).__name__,
        "error": str(error),
        "effects": {
            "network_denied_by_parent_sandbox": True,
            "forward_passes": 0,
            "audio_reads": [],
            "inference_runs": 0,
            "outputs_published": [],
        },
    }


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("usage: separation_scnet_compatibility.py PROFILE_ROOT", file=sys.stderr)
        return 2
    try:
        result = inspect_scnet_compatibility(arguments[0])
    except Exception as error:  # fail closed with a machine-readable receipt
        print(json.dumps(compatibility_failure_record(error), sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CompatibilityError",
    "SCNET_COMPATIBILITY_SCHEMA",
    "compatibility_failure_record",
    "inspect_scnet_compatibility",
    "main",
]
