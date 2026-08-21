from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

import sunofriend.remix_musicfm_fma_windows_setup as windows_setup_module
from sunofriend.remix_musicfm_fma_windows_setup import (
    MUSICFM_WINDOWS_ASSET_MANIFEST_SCHEMA,
    MUSICFM_WINDOWS_INSTALL_LOCK_SCHEMA,
    create_windows_asset_manifest,
    create_windows_install_lock,
    validate_windows_asset_manifest,
    validate_windows_install_lock,
)
from sunofriend.source_receipt import document_sha256


ROOT = Path(__file__).parents[1]
SETUP = ROOT / "scripts" / "setup-remix-musicfm-fma-windows.ps1"
VALIDATOR = ROOT / "scripts" / "validate-remix-musicfm-windows-setup-inputs.py"
BUILDER = ROOT / "scripts" / "build-remix-musicfm-windows-install-lock.py"


def _native_evidence() -> tuple[bytes, bytes]:
    installs = []
    for (
        name,
        version,
        filename,
        sha256,
        requested,
    ) in windows_setup_module._WINDOWS_WHEELS:
        installs.append(
            {
                "download_info": {
                    "url": f"https://example.invalid/{filename.replace('+', '%2B')}",
                    "archive_info": {"hashes": {"sha256": sha256}},
                },
                "is_yanked": False,
                "requested": requested,
                "metadata": {"name": name, "version": version},
            }
        )
    report = json.dumps(
        {
            "version": "1",
            "environment": {
                "platform_system": "Windows",
                "python_version": "3.11.16",
            },
            "install": installs,
        },
        separators=(",", ":"),
    ).encode()
    receipt = json.dumps(
        {
            "schema": windows_setup_module.NATIVE_RECEIPT_SCHEMA,
            "status": "metadata_only_resolution_complete_unvalidated",
            "platform": {
                "operating_system": "Windows",
                "architecture": "AMD64",
                "python_version": "3.11.16",
            },
            "report": {
                "filename": "native-windows-pip-report.json",
                "bytes": len(report),
                "sha256": hashlib.sha256(report).hexdigest(),
            },
            "resolver_policy": {
                "native_environment_markers": True,
                "ignore_installed": True,
                "only_binary": True,
                "pip_cache_disabled": True,
                "wheel_files_retained": False,
                "packages_installed": False,
                "packages_imported": False,
                "model_loaded": False,
                "audio_opened": False,
                "inference_run": False,
                "training_started": False,
            },
            "authority": {
                "dependency_download_authorized": False,
                "dependency_install_authorized": False,
                "model_import_authorized": False,
                "model_load_authorized": False,
                "inference_authorized": False,
                "private_audio_access_authorized": False,
                "training_execution_authorized": False,
                "product_ordering_changed": False,
            },
        },
        separators=(",", ":"),
    ).encode()
    return report, receipt


def _rehash(document: dict) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)


def test_native_lock_uses_exact_windows_roster_and_binds_report() -> None:
    report, receipt = _native_evidence()
    lock = create_windows_install_lock(report, receipt, repository_commit="8" * 40)
    assert lock["schema"] == MUSICFM_WINDOWS_INSTALL_LOCK_SCHEMA
    assert len(lock["items"]) == 26
    assert "colorama" in {row["package"] for row in lock["items"]}
    assert "hf-xet" not in {row["package"] for row in lock["items"]}
    assert lock["native_report_sha256"] == hashlib.sha256(report).hexdigest()
    assert lock["maximum_total_download_bytes"] == 3_500_000_000
    assert lock["authority"]["existing_environment_modification_authorized"] is False
    assert validate_windows_install_lock(lock, report, receipt) == lock


@pytest.mark.parametrize("kind", ["report", "receipt", "lock"])
def test_native_lock_rejects_report_receipt_or_authority_tampering(kind: str) -> None:
    report, receipt = _native_evidence()
    lock = create_windows_install_lock(report, receipt, repository_commit="8" * 40)
    if kind == "report":
        changed = json.loads(report)
        changed["install"][16]["metadata"]["name"] = "hf-xet"
        report = json.dumps(changed, separators=(",", ":")).encode()
    elif kind == "receipt":
        changed = json.loads(receipt)
        changed["resolver_policy"]["packages_installed"] = True
        receipt = json.dumps(changed, separators=(",", ":")).encode()
    else:
        lock = deepcopy(lock)
        lock["authority"]["model_load_authorized"] = True
        _rehash(lock)
    with pytest.raises(ValueError, match="changed|binding|lacks|wrong"):
        validate_windows_install_lock(lock, report, receipt)


def test_asset_manifest_is_exact_evidence_bound_and_no_load() -> None:
    manifest = create_windows_asset_manifest(repository_commit="8" * 40)
    assert manifest["schema"] == MUSICFM_WINDOWS_ASSET_MANIFEST_SCHEMA
    assert len(manifest["items"]) == 10
    checkpoint = [row for row in manifest["items"] if row["kind"] == "checkpoint"]
    assert checkpoint == [
        {
            "kind": "checkpoint",
            "target_relative_path": "assets/pretrained_fma.pt",
            "url": (
                "https://huggingface.co/minzwon/MusicFM/resolve/"
                "4513b38bc25ad1d227b1980819b9691ba97f4d87/"
                "pretrained_fma.pt?download=true"
            ),
            "bytes": 1_316_802_154,
            "sha256": "68392eee13d34c2941b3761934abb6b1e67b2e9df498695bda2ea5c1087d4b96",
        }
    ]
    assert manifest["binding"]["static_evidence_sha256"] == (
        "99f1c24d44a3f08d68d614e4878c1cc0c05f1e941e071cbb9a3f5e9c7aeaf846"
    )
    assert manifest["authority"]["model_load_authorized"] is False
    assert manifest["authority"]["private_audio_access_authorized"] is False
    assert validate_windows_asset_manifest(manifest) == manifest

    changed = deepcopy(manifest)
    changed["items"][-1]["sha256"] = "9" * 64
    _rehash(changed)
    with pytest.raises(ValueError, match="manifest changed"):
        validate_windows_asset_manifest(changed)


def test_windows_setup_validates_before_writes_and_installs_only_offline() -> None:
    text = SETUP.read_text(encoding="utf-8")
    validation = text.index("validate-remix-musicfm-windows-setup-inputs.py")
    first_write = text.index("New-Item -ItemType Directory -Path $FreshRoot")
    assert validation < first_write
    assert "[switch]$ConfirmAuthorizedSetup" in text
    assert "& $Python -m venv" in text
    assert "Asset target must be safe and relative" in text
    assert "Wheel download cap exceeded" in text
    assert "Asset download cap exceeded" in text
    assert "--no-index --no-deps @wheelFiles" in text
    assert "-m pip check" in text
    assert "model_imported=$false" in text
    assert "checkpoint_loaded=$false" in text
    assert "private_audio_opened=$false" in text
    assert "from_pretrained" not in text
    assert "torch.load" not in text
    assert VALIDATOR.is_file()


def test_builder_and_validator_round_trip_exact_setup_documents(tmp_path: Path) -> None:
    report, receipt = _native_evidence()
    report_path = tmp_path / "native-windows-pip-report.json"
    receipt_path = tmp_path / "native-windows-resolution-receipt.json"
    output = tmp_path / "setup-inputs"
    report_path.write_bytes(report)
    receipt_path.write_bytes(receipt)

    subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            str(report_path),
            str(receipt_path),
            "--out-dir",
            str(output),
        ],
        cwd=ROOT,
        check=True,
    )
    lock_path = output / "native-windows-install-lock.json"
    manifest_path = output / "asset-download-manifest.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert lock["repository_commit"] == manifest["repository_commit"]
    assert lock_path.stat().st_mode & 0o777 == 0o600
    assert manifest_path.stat().st_mode & 0o777 == 0o600

    subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            str(report_path),
            str(receipt_path),
            str(lock_path),
            str(manifest_path),
        ],
        cwd=ROOT,
        check=True,
    )
