#!/usr/bin/env python3
"""Verify the query runtime's package imports without loading model artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib
from importlib import metadata
import json
from pathlib import Path
import platform
import socket
import sys
from typing import Any
import urllib.request


SCHEMA = "sunofriend.other-refinement-query-runtime-import-evidence.v1"
IMPORT_MODULES = (
    "numpy",
    "torch",
    "torchaudio",
    "torchvision",
    "timm",
    "hear21passt",
    "hear21passt.models.passt",
    "hear21passt.base",
)
CHECKPOINT_SUFFIXES = (".ckpt", ".pt", ".pth", ".safetensors")
AUDIO_SUFFIXES = (".aac", ".aif", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".wav")


def _canonical_name(value: str) -> str:
    return value.lower().replace("_", "-").replace(".", "-")


def _requirements(path: Path) -> dict[str, str]:
    packages: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "--")):
            continue
        requirement = line.split(" --hash=", 1)[0]
        if requirement.count("==") != 1:
            raise ValueError(f"runtime requirement is not exact: {line}")
        name, version = requirement.split("==", 1)
        packages[_canonical_name(name)] = version
    if len(packages) != 28:
        raise ValueError("runtime lock must contain exactly 28 packages")
    return dict(sorted(packages.items()))


def _document_sha256(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "report_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _relative_module_path(module: Any, runtime_root: Path) -> str | None:
    source = getattr(module, "__file__", None)
    if source is None:
        return None
    resolved = Path(source).resolve()
    try:
        return str(resolved.relative_to(runtime_root))
    except ValueError as error:
        raise RuntimeError(f"module resolved outside the isolated runtime: {source}") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    args = parser.parse_args()

    runtime_root = args.runtime_root.resolve()
    requirements_path = args.requirements.resolve()
    if Path(sys.prefix).resolve() != runtime_root:
        raise RuntimeError("import worker is not running from the expected isolated runtime")
    if sys.base_prefix == sys.prefix:
        raise RuntimeError("import worker is not running inside a virtual environment")
    if sys.version_info[:2] != (3, 12) or platform.machine() != "arm64":
        raise RuntimeError("import worker requires CPython 3.12 on arm64")

    expected_packages = _requirements(requirements_path)
    installed_packages = {
        _canonical_name(distribution.metadata["Name"]): distribution.version
        for distribution in metadata.distributions()
        if distribution.metadata.get("Name")
    }
    observed_locked = {
        name: installed_packages.get(name) for name in expected_packages
    }
    if observed_locked != expected_packages:
        raise RuntimeError("installed packages differ from the exact runtime lock")
    extras = {
        name: version
        for name, version in installed_packages.items()
        if name not in expected_packages
    }
    if set(extras) != {"pip"}:
        raise RuntimeError(f"unexpected packages in isolated runtime: {sorted(extras)}")

    network_attempts: list[str] = []
    checkpoint_open_attempts: list[str] = []
    audio_open_attempts: list[str] = []
    torch_load_calls: list[str] = []

    def audit(event: str, event_args: tuple[Any, ...]) -> None:
        if event.startswith("socket."):
            network_attempts.append(event)
            raise RuntimeError(f"network operation forbidden during import verification: {event}")
        if event == "open" and event_args:
            target = event_args[0]
            if isinstance(target, (str, bytes)):
                text = str(target).lower()
                if text.endswith(CHECKPOINT_SUFFIXES):
                    checkpoint_open_attempts.append(text)
                    raise RuntimeError("checkpoint file open forbidden during import verification")
                if text.endswith(AUDIO_SUFFIXES):
                    audio_open_attempts.append(text)
                    raise RuntimeError("audio file open forbidden during import verification")

    sys.addaudithook(audit)

    def deny_network(*_args: Any, **_kwargs: Any) -> Any:
        network_attempts.append("python_network_api")
        raise RuntimeError("network API forbidden during import verification")

    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    urllib.request.urlopen = deny_network

    imported: dict[str, dict[str, str | None]] = {}
    for module_name in IMPORT_MODULES:
        module = importlib.import_module(module_name)
        imported[module_name] = {
            "version": str(getattr(module, "__version__", "not_declared")),
            "runtime_relative_path": _relative_module_path(module, runtime_root),
        }
        if module_name == "torch":
            torch = module

            def deny_torch_load(*_args: Any, **_kwargs: Any) -> Any:
                torch_load_calls.append("torch.load")
                raise RuntimeError("torch.load forbidden during import verification")

            torch.load = deny_torch_load
            torch.hub.load_state_dict_from_url = deny_torch_load
            torch.hub.download_url_to_file = deny_torch_load

    if network_attempts or checkpoint_open_attempts or audio_open_attempts or torch_load_calls:
        raise RuntimeError("import verification crossed an approved effects boundary")

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "report_sha256": "",
        "status": "isolated_hash_locked_runtime_imports_verified_network_denied",
        "runtime": {
            "implementation": platform.python_implementation(),
            "python": platform.python_version(),
            "machine": platform.machine(),
            "virtual_environment": True,
            "isolated_mode": bool(sys.flags.isolated),
            "user_site_enabled": bool(sys.flags.no_user_site == 0),
        },
        "locked_package_count": len(expected_packages),
        "locked_packages": expected_packages,
        "bootstrap_packages": extras,
        "imports": imported,
        "guards": {
            "os_network_denial_required": True,
            "python_network_attempts": len(network_attempts),
            "checkpoint_open_attempts": len(checkpoint_open_attempts),
            "audio_open_attempts": len(audio_open_attempts),
            "torch_load_calls": len(torch_load_calls),
        },
        "effects": {
            "dependency_installed": True,
            "packages_imported": list(IMPORT_MODULES),
            "checkpoint_loaded": False,
            "model_constructed": False,
            "inference_runs": 0,
            "audio_reads": 0,
            "audio_writes": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
        },
    }
    report["report_sha256"] = _document_sha256(report)
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
