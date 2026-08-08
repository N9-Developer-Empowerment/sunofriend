from __future__ import annotations

import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import zipfile

import pytest

from sunofriend.separation_other_refinement_next_runtime_evidence import (
    APPROVED_DIRECT_REQUIREMENTS,
    RUNTIME_SOURCE,
    inspect_runtime_wheel_evidence,
    validate_runtime_wheel_evidence,
)


ROOT = Path(__file__).resolve().parents[1]


def _wheel(root: Path, name: str, version: str) -> Path:
    dist_info = f"{name.replace('-', '_')}-{version}.dist-info"
    path = root / f"{name}-{version}-py3-none-any.whl"
    metadata = "\n".join(
        (
            "Metadata-Version: 2.4",
            f"Name: {name}",
            f"Version: {version}",
            "License-Expression: MIT",
            "Requires-Python: >=3.10",
            "Requires-Dist: fixture-dependency>=1",
            "",
            "fixture",
            "",
        )
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(f"{dist_info}/METADATA", metadata)
        archive.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\nTag: py3-none-any\n",
        )
        archive.writestr(f"{dist_info}/licenses/LICENSE", "MIT License\n")
        archive.writestr(f"{name}/__init__.py", "raise AssertionError('not imported')\n")
    return path


def _approved_closure(root: Path) -> None:
    for name, version in APPROVED_DIRECT_REQUIREMENTS.items():
        _wheel(root, name, version)
    _wheel(root, "fixture-dependency", "1.2.3")


def test_mega53_runtime_evidence_hashes_without_importing(tmp_path: Path) -> None:
    _approved_closure(tmp_path)

    evidence = inspect_runtime_wheel_evidence(tmp_path)

    assert evidence["package_count"] == len(APPROVED_DIRECT_REQUIREMENTS) + 1
    assert evidence["runtime_source"] == RUNTIME_SOURCE
    assert evidence["packages"]["mlx"] == "0.31.2"
    assert evidence["packages"]["torch"] == "2.2.2"
    assert evidence["wheel_bytes"] == sum(path.stat().st_size for path in tmp_path.iterdir())
    mlx = next(item for item in evidence["artifacts"] if item["package"] == "mlx")
    assert mlx["sha256"] == hashlib.sha256((tmp_path / mlx["filename"]).read_bytes()).hexdigest()
    assert mlx["license_files"]
    assert evidence["inspection"]["packages_imported"] is False
    assert evidence["effects"]["dependency_installed"] is False
    assert evidence["effects"]["checkpoint_loaded"] is False
    assert evidence["effects"]["inference_runs"] == 0
    assert validate_runtime_wheel_evidence(evidence) == evidence


def test_mega53_runtime_evidence_rejects_changed_direct_pin(tmp_path: Path) -> None:
    for name, version in APPROVED_DIRECT_REQUIREMENTS.items():
        if name != "mlx-spectro":
            _wheel(tmp_path, name, version)

    with pytest.raises(ValueError, match="approved direct runtime requirements differ"):
        inspect_runtime_wheel_evidence(tmp_path)


def test_mega53_runtime_evidence_rejects_authority_expansion(tmp_path: Path) -> None:
    _approved_closure(tmp_path)
    changed = copy.deepcopy(inspect_runtime_wheel_evidence(tmp_path))
    changed["effects"]["dependency_installed"] = True

    with pytest.raises(ValueError, match="document hash differs"):
        validate_runtime_wheel_evidence(changed)


def test_mega53_runtime_route_is_capped_download_only_and_network_denied() -> None:
    setup = (
        ROOT / "scripts" / "setup-separation-other-refinement-next-challenger-macos.sh"
    ).read_text(encoding="utf-8")
    downloader = (
        ROOT / "scripts" / "download-separation-other-refinement-next-runtime-wheels.py"
    ).read_text(encoding="utf-8")

    assert "RUNTIME_WHEEL_CAP_BYTES=1610612736" in setup
    assert "--runtime-wheel-evidence-only" in setup
    assert "--accept-runtime-wheel-evidence" in setup
    assert "(deny network*)" in setup
    assert '"pip",\n        "download"' in downloader
    assert '"macosx_14_0_arm64"' in downloader
    assert '"macosx_11_0_arm64"' not in downloader
    assert '"pip",\n        "install"' not in downloader
    assert 'parser.add_argument("--report")' in downloader
    assert "python3.12" in setup
    assert "import torch" not in downloader
    assert "torch.load" not in setup


def test_mega53_runtime_route_requires_specific_acceptance(tmp_path: Path) -> None:
    setup = ROOT / "scripts" / "setup-separation-other-refinement-next-challenger-macos.sh"
    result = subprocess.run(
        [str(setup), "--runtime-wheel-evidence-only"],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "SUNOFRIEND_SEPARATION_ROOT": str(tmp_path / "separation"),
        },
    )

    assert result.returncode == 2
    assert "requires --accept-runtime-wheel-evidence" in result.stderr
    assert not (tmp_path / "separation").exists()


def test_mega53_isolated_runtime_route_requires_specific_acceptance(
    tmp_path: Path,
) -> None:
    setup = ROOT / "scripts" / "setup-separation-other-refinement-next-challenger-macos.sh"
    result = subprocess.run(
        [str(setup), "--install-runtime"],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "SUNOFRIEND_SEPARATION_ROOT": str(tmp_path / "separation"),
        },
    )

    assert result.returncode == 2
    assert "requires --accept-runtime-install-and-import" in result.stderr
    assert not (tmp_path / "separation").exists()


def test_mega53_isolated_runtime_route_is_offline_hash_locked_and_import_only() -> None:
    setup = (
        ROOT / "scripts" / "setup-separation-other-refinement-next-challenger-macos.sh"
    ).read_text(encoding="utf-8")
    worker = (
        ROOT / "scripts" / "verify-separation-other-refinement-next-runtime-imports.py"
    ).read_text(encoding="utf-8")

    acceptance = setup.index('if [ "$ACCEPTED_RUNTIME_INSTALL_AND_IMPORT" != true ]')
    first_install_write = setup.index('mkdir -p "$RUNTIME_IMPORT_PARENT"')
    assert acceptance < first_install_write
    assert "--install-runtime" in setup
    assert "--accept-runtime-install-and-import" in setup
    assert "--no-index" in setup
    assert "--find-links" in setup
    assert "--require-hashes" in setup
    assert "(deny network*)" in setup
    assert '"$STAGING/runtime/bin/python" -I -B "$RUNTIME_IMPORT_SCRIPT"' in setup
    assert "torch.load = deny_torch_load" in worker
    assert 'event == "socket.__new__"' in worker
    assert 'event == "socket.bind"' in worker
    assert '{"::1", "127.0.0.1"}' in worker
    assert '"local_bind_attempts": local_bind_attempts' in worker
    assert '"socket_constructions": socket_constructions' in worker
    assert "checkpoint file open forbidden" in worker
    assert "audio file open forbidden" in worker
    assert "importlib.import_module(module_name)" in worker
    assert "load_model(" not in worker
    assert "BSRoformer(" not in worker


def test_mega53_import_worker_parses_exact_29_package_lock() -> None:
    worker_path = (
        ROOT / "scripts" / "verify-separation-other-refinement-next-runtime-imports.py"
    )
    spec = importlib.util.spec_from_file_location("mega53_runtime_import_worker", worker_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    packages = module._requirements(
        ROOT / "separation-other-refinement-next-runtime-requirements.txt"
    )

    assert len(packages) == 29
    assert packages["torch"] == "2.2.2"
    assert packages["mlx"] == "0.31.2"
    assert packages["mlx-spectro"] == "0.7.0"
    assert packages["rotary-embedding-torch"] == "0.8.9"


def test_committed_mega53_runtime_lock_matches_completed_evidence() -> None:
    lock = ROOT / "separation-other-refinement-next-runtime-requirements.txt"
    contents = lock.read_bytes()
    requirement_lines = [
        line
        for line in contents.decode("utf-8").splitlines()
        if line and not line.startswith(("#", "--"))
    ]

    assert len(requirement_lines) == 29
    assert hashlib.sha256(contents).hexdigest() == (
        "284d198c43e9074a4d645f005d937dd4e93b99e22aa21d942caaa1822b13d10b"
    )
    assert any(line.startswith("torch==2.2.2 ") for line in requirement_lines)
    assert any(line.startswith("mlx==0.31.2 ") for line in requirement_lines)
    assert any(line.startswith("mlx-spectro==0.7.0 ") for line in requirement_lines)
