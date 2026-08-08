"""Non-importing evidence for the Mega-53 challenger's runtime closure."""

from __future__ import annotations

from email.parser import BytesParser
from email.policy import default
import hashlib
import json
from pathlib import Path
import re
from typing import Any
import zipfile


RUNTIME_WHEEL_EVIDENCE_SCHEMA = "sunofriend.mega53-runtime-wheel-evidence.v1"
TARGET_PLATFORM = "macosx_14_0_arm64"
TARGET_PYTHON = "3.12"
TARGET_IMPLEMENTATION = "cp"
TARGET_ABI = "cp312"
RUNTIME_SOURCE = {
    "repository": "https://github.com/openmirlab/bs-roformer-infer",
    "revision": "de35ada5817b878da0194ee2860253dda3a9c2b2",
    "git_archive_sha256": (
        "e64fe7733a45f5efc53091bbc2ab6dd04a0ee7373a639f1c9b27275502f26691"
    ),
    "license": "MIT",
}
APPROVED_DIRECT_REQUIREMENTS = {
    "beartype": "0.22.9",
    "einops": "0.8.2",
    "ml-collections": "1.1.0",
    "mlx": "0.31.2",
    "mlx-spectro": "0.7.0",
    "numpy": "1.26.4",
    "packaging": "26.3",
    "pyyaml": "6.0.3",
    "requests": "2.34.2",
    "rotary-embedding-torch": "0.8.9",
    "soundfile": "0.14.0",
    "torch": "2.2.2",
    "tqdm": "4.70.0",
}


def canonicalize_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _document_sha256(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "evidence_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _single_member(names: list[str], suffix: str, wheel: Path) -> str:
    matches = [name for name in names if name.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"{wheel.name} must contain exactly one {suffix} member")
    return matches[0]


def inspect_runtime_wheel_evidence(wheel_directory: str | Path) -> dict[str, Any]:
    """Hash wheels and inspect only ZIP metadata and bundled licence records."""

    root = Path(wheel_directory).resolve()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("runtime wheel directory must be a regular directory")
    entries = sorted(root.iterdir(), key=lambda path: path.name.lower())
    if not entries:
        raise ValueError("runtime wheel directory is empty")
    artifacts: list[dict[str, Any]] = []
    packages: dict[str, str] = {}
    total_bytes = 0
    for wheel in entries:
        stat = wheel.lstat()
        if wheel.is_symlink() or not wheel.is_file() or stat.st_nlink != 1:
            raise ValueError(f"runtime artifact must be a single-link file: {wheel.name}")
        if wheel.suffix != ".whl":
            raise ValueError(f"runtime artifact is not a wheel: {wheel.name}")
        sha256 = _sha256(wheel)
        total_bytes += stat.st_size
        try:
            with zipfile.ZipFile(wheel) as archive:
                names = archive.namelist()
                if not names or archive.testzip() is not None:
                    raise ValueError(f"wheel ZIP integrity failed: {wheel.name}")
                metadata_member = _single_member(names, ".dist-info/METADATA", wheel)
                wheel_member = _single_member(names, ".dist-info/WHEEL", wheel)
                metadata_bytes = archive.read(metadata_member)
                wheel_bytes = archive.read(wheel_member)
                metadata = BytesParser(policy=default).parsebytes(metadata_bytes)
                wheel_metadata = BytesParser(policy=default).parsebytes(wheel_bytes)
                package_name = canonicalize_distribution_name(str(metadata["Name"]))
                package_version = str(metadata["Version"])
                if not package_name or not package_version:
                    raise ValueError(f"wheel metadata identity is incomplete: {wheel.name}")
                if package_name in packages:
                    raise ValueError(f"duplicate runtime package: {package_name}")
                packages[package_name] = package_version
                licence_members = sorted(
                    name
                    for name in names
                    if ".dist-info/licenses/" in name.lower()
                    or Path(name).name.lower().startswith(
                        ("license", "licence", "copying")
                    )
                )
                licence_evidence = []
                for member in licence_members:
                    payload = archive.read(member)
                    licence_evidence.append(
                        {
                            "member": member,
                            "bytes": len(payload),
                            "sha256": hashlib.sha256(payload).hexdigest(),
                        }
                    )
                artifacts.append(
                    {
                        "filename": wheel.name,
                        "bytes": stat.st_size,
                        "sha256": sha256,
                        "package": package_name,
                        "version": package_version,
                        "requires_dist": sorted(metadata.get_all("Requires-Dist", [])),
                        "requires_python": metadata.get("Requires-Python"),
                        "license_expression": metadata.get("License-Expression"),
                        "license_field": metadata.get("License"),
                        "license_classifiers": sorted(
                            classifier
                            for classifier in metadata.get_all("Classifier", [])
                            if classifier.startswith("License ::")
                        ),
                        "license_files": licence_evidence,
                        "project_urls": sorted(metadata.get_all("Project-URL", [])),
                        "wheel_tags": sorted(wheel_metadata.get_all("Tag", [])),
                        "zip_member_count": len(names),
                        "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
                        "wheel_metadata_sha256": hashlib.sha256(wheel_bytes).hexdigest(),
                    }
                )
        except zipfile.BadZipFile as error:
            raise ValueError(f"runtime artifact is not a valid wheel ZIP: {wheel.name}") from error

    missing_or_changed = {
        name: {"expected": version, "observed": packages.get(name)}
        for name, version in APPROVED_DIRECT_REQUIREMENTS.items()
        if packages.get(name) != version
    }
    if missing_or_changed:
        raise ValueError(
            "approved direct runtime requirements differ: "
            + json.dumps(missing_or_changed, sort_keys=True)
        )
    requirement_lines = [
        f"{artifact['package']}=={artifact['version']} "
        f"--hash=sha256:{artifact['sha256']}"
        for artifact in sorted(artifacts, key=lambda item: item["package"])
    ]
    evidence: dict[str, Any] = {
        "schema": RUNTIME_WHEEL_EVIDENCE_SCHEMA,
        "evidence_sha256": "",
        "status": "hash_locked_wheel_closure_statically_inspected_not_installed",
        "runtime_source": RUNTIME_SOURCE,
        "target": {
            "platform": TARGET_PLATFORM,
            "python": TARGET_PYTHON,
            "implementation": TARGET_IMPLEMENTATION,
            "abi": TARGET_ABI,
            "only_binary": True,
        },
        "approved_direct_requirements": APPROVED_DIRECT_REQUIREMENTS,
        "package_count": len(artifacts),
        "wheel_bytes": total_bytes,
        "packages": dict(sorted(packages.items())),
        "artifacts": sorted(artifacts, key=lambda item: item["package"]),
        "hash_locked_requirements": requirement_lines,
        "future_installation_plan": {
            "approved_now": False,
            "fresh_isolated_cpython": "3.12 on macOS arm64",
            "dependency_command_contract": (
                "pip install --no-index --find-links WHEELS --require-hashes "
                "-r REQUIREMENTS"
            ),
            "source_contract": (
                "use only the separately verified exact source archive; do not "
                "resolve or download a PyPI bs-roformer-infer wheel"
            ),
            "network_denied": True,
            "package_import_verification_requires_later_approval": True,
        },
        "inspection": {
            "wheel_zip_integrity_checked": True,
            "core_metadata_parsed": True,
            "wheel_metadata_parsed": True,
            "licence_metadata_and_member_hashes_recorded": True,
            "archive_payloads_executed": False,
            "packages_imported": False,
        },
        "effects": {
            "dependency_artifacts_downloaded": True,
            "dependency_installed": False,
            "model_packages_imported": False,
            "wheel_code_executed": False,
            "source_archive_executed": False,
            "checkpoint_loaded": False,
            "model_constructed": False,
            "inference_runs": 0,
            "audio_reads": 0,
            "audio_writes": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
        },
    }
    evidence["evidence_sha256"] = _document_sha256(evidence)
    return evidence


def validate_runtime_wheel_evidence(value: dict[str, Any]) -> dict[str, Any]:
    """Reject an incomplete or authority-expanding wheel evidence document."""

    if value.get("schema") != RUNTIME_WHEEL_EVIDENCE_SCHEMA:
        raise ValueError("runtime wheel evidence schema differs")
    if value.get("evidence_sha256") != _document_sha256(value):
        raise ValueError("runtime wheel evidence document hash differs")
    if value.get("runtime_source") != RUNTIME_SOURCE:
        raise ValueError("runtime wheel evidence source identity differs")
    if value.get("approved_direct_requirements") != APPROVED_DIRECT_REQUIREMENTS:
        raise ValueError("runtime wheel evidence direct requirements differ")
    packages = value.get("packages", {})
    for name, version in APPROVED_DIRECT_REQUIREMENTS.items():
        if packages.get(name) != version:
            raise ValueError(f"runtime wheel evidence differs for {name}")
    effects = value.get("effects", {})
    required_false = (
        "dependency_installed",
        "model_packages_imported",
        "wheel_code_executed",
        "source_archive_executed",
        "checkpoint_loaded",
        "model_constructed",
        "public_activation",
        "source_selection",
        "midi_created",
        "hosting",
        "redistribution",
    )
    if any(effects.get(key) is not False for key in required_false):
        raise ValueError("runtime wheel evidence expands approved effects")
    if effects.get("inference_runs") != 0 or effects.get("audio_reads") != 0:
        raise ValueError("runtime wheel evidence contains execution effects")
    artifacts = value.get("artifacts", [])
    if value.get("package_count") != len(artifacts) or not artifacts:
        raise ValueError("runtime wheel evidence artifact count differs")
    if value.get("wheel_bytes") != sum(item["bytes"] for item in artifacts):
        raise ValueError("runtime wheel evidence byte accounting differs")
    return value
