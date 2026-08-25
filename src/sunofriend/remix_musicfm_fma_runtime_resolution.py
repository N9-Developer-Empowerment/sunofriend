"""Retain a metadata-only MusicFM Windows wheel resolution without overstating it."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit

from .source_receipt import document_sha256


MUSICFM_FMA_RUNTIME_RESOLUTION_SCHEMA = (
    "sunofriend.remix-musicfm-fma-runtime-resolution.v0"
)

_COMMIT = re.compile(r"^[0-9a-f]{40}$")

# Public package-index metadata observed on 2026-08-21. These are candidates,
# not downloaded artifacts or an install lock. The Mac resolver chose Windows
# wheels but evaluated environment markers against its Darwin host.
_CANDIDATE_WHEELS = [
    (
        "torch",
        "2.7.1+cu128",
        "torch-2.7.1+cu128-cp311-cp311-win_amd64.whl",
        3_273_066_072,
        "138c66dcd0ed2f07aafba3ed8b7958e2bed893694990e0b4b55b6b2b4a336aa6",
        True,
    ),
    (
        "torchaudio",
        "2.7.1+cu128",
        "torchaudio-2.7.1+cu128-cp311-cp311-win_amd64.whl",
        4_660_477,
        "37a42de8c0f601dc0bc7dcccc4049644ef5adcf45920dd5813c339121e5b5a8c",
        True,
    ),
    (
        "transformers",
        "4.53.2",
        "transformers-4.53.2-py3-none-any.whl",
        10_826_609,
        "db8f4819bb34f000029c73c3c557e7d06fc1b8e612ec142eecdae3947a9c78bf",
        True,
    ),
    (
        "einops",
        "0.8.1",
        "einops-0.8.1-py3-none-any.whl",
        64_359,
        "919387eb55330f5757c6bea9165c5ff5cfe63a642682ea788a6d472576d81737",
        True,
    ),
    (
        "huggingface-hub",
        "0.36.2",
        "huggingface_hub-0.36.2-py3-none-any.whl",
        566_395,
        "48f0c8eac16145dfce371e9d2d7772854a4f591bcb56c9cf548accf531d54270",
        False,
    ),
    (
        "hf-xet",
        "1.6.0",
        "hf_xet-1.6.0-cp38-abi3-win_amd64.whl",
        4_033_128,
        "fb4fadde1b2b70bf4c0c14a6dccbe7194b1c28947fefd5bbe3fed9d940676c3b",
        False,
    ),
    (
        "tokenizers",
        "0.21.4",
        "tokenizers-0.21.4-cp39-abi3-win_amd64.whl",
        2_507_568,
        "475d807a5c3eb72c59ad9b5fcdb254f6e17f53dfcbb9903233b0dfa9c943b597",
        False,
    ),
    (
        "fsspec",
        "2026.7.0",
        "fsspec-2026.7.0-py3-none-any.whl",
        206_583,
        "b57ddbafedfaef7018c1ecab32aa200a9d7ca26b77965f64e48b70061249d279",
        False,
    ),
    (
        "numpy",
        "2.4.6",
        "numpy-2.4.6-cp311-cp311-win_amd64.whl",
        12_608_406,
        "1e254a00cdf42b1e4d5b3d68d33af63268d41340d8885df2ab6470f2e1500147",
        False,
    ),
    (
        "packaging",
        "26.3",
        "packaging-26.3-py3-none-any.whl",
        129_956,
        "d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c",
        False,
    ),
    (
        "pyyaml",
        "6.0.3",
        "pyyaml-6.0.3-cp311-cp311-win_amd64.whl",
        158_763,
        "9f3bfb4965eb874431221a3ff3fdcddc7e74e3b07799e0e84ca4a0f867d449bf",
        False,
    ),
    (
        "regex",
        "2026.7.19",
        "regex-2026.7.19-cp311-cp311-win_amd64.whl",
        277_983,
        "8d3469c91dd92ee41b7c95280edbd975ef1ba9195086686623a1c6e8935ce965",
        False,
    ),
    (
        "safetensors",
        "0.8.0",
        "safetensors-0.8.0-cp310-abi3-win_amd64.whl",
        355_540,
        "096ec1a98435df7beb08853bb5aa9081a84f23d0adc67ed1a0a10550f608373f",
        False,
    ),
    (
        "sympy",
        "1.14.0",
        "sympy-1.14.0-py3-none-any.whl",
        6_299_353,
        "e091cc3e99d2141a0ba2847328f5479b05d94a6635cb96148ccb3f34671bd8f5",
        False,
    ),
    (
        "mpmath",
        "1.3.0",
        "mpmath-1.3.0-py3-none-any.whl",
        536_198,
        "a0b2b9fe80bbcd81a6647ff13108738cfb482d481d826cc0e02f5b35e5c88d2c",
        False,
    ),
    (
        "tqdm",
        "4.70.0",
        "tqdm-4.70.0-py3-none-any.whl",
        80_184,
        "7f585706bfddbdebf89daac705b2dfcc16890130727d3197ca62c732b4310953",
        False,
    ),
    (
        "typing-extensions",
        "4.16.0",
        "typing_extensions-4.16.0-py3-none-any.whl",
        45_571,
        "481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8",
        False,
    ),
    (
        "filelock",
        "3.32.3",
        "filelock-3.32.3-py3-none-any.whl",
        98_901,
        "7f0ca4bcc0e181c60dbbd8aa9ab5b120ebb99e4e064e83636340056f833a1f09",
        False,
    ),
    (
        "jinja2",
        "3.1.6",
        "jinja2-3.1.6-py3-none-any.whl",
        134_899,
        "85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67",
        False,
    ),
    (
        "markupsafe",
        "3.0.3",
        "markupsafe-3.0.3-cp311-cp311-win_amd64.whl",
        15_077,
        "de8a88e63464af587c950061a5e6a67d3632e36df62b986892331d4620a35c01",
        False,
    ),
    (
        "networkx",
        "3.6.1",
        "networkx-3.6.1-py3-none-any.whl",
        2_068_504,
        "d47fbf302e7d9cbbb9e2555a0d267983d2aa476bac30e90dfbe5669bd57f3762",
        False,
    ),
    (
        "requests",
        "2.34.2",
        "requests-2.34.2-py3-none-any.whl",
        73_075,
        "2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0",
        False,
    ),
    (
        "charset-normalizer",
        "3.5.1",
        "charset_normalizer-3.5.1-cp311-cp311-win_amd64.whl",
        206_653,
        "f9b1e28d0e8dbfa858abdba91d6b547beaf2df1a59bec6da6faae7b96a4991a9",
        False,
    ),
    (
        "idna",
        "3.19",
        "idna-3.19-py3-none-any.whl",
        68_550,
        "815e7be7a7806d54abb586dc943addc79e8b2ee16915059658cbeff4b1b43bf4",
        False,
    ),
    (
        "urllib3",
        "2.7.0",
        "urllib3-2.7.0-py3-none-any.whl",
        131_087,
        "9fb4c81ebbb1ce9531cce37674bbc6f1360472bc18ca9a553ede278ef7276897",
        False,
    ),
    (
        "certifi",
        "2026.7.22",
        "certifi-2026.7.22-py3-none-any.whl",
        136_983,
        "62f22742b58a1a33014a2b6b706588a8d7e2a88ae7bd1a6ebe8c992928483775",
        False,
    ),
]


def create_musicfm_fma_runtime_resolution(
    runtime_plan: Mapping[str, Any],
    *,
    resolver_report_bytes: bytes,
    repository_commit: str,
) -> dict[str, Any]:
    """Create partial evidence from a pip report without downloading wheels."""

    if not _COMMIT.fullmatch(str(repository_commit)):
        raise ValueError("repository_commit must be a full Git commit")
    report = _parse_and_validate_report(resolver_report_bytes)
    document = _resolution_values(
        runtime_plan,
        report,
        report_bytes=resolver_report_bytes,
        repository_commit=str(repository_commit),
    )
    document["document_sha256"] = document_sha256(document)
    return validate_musicfm_fma_runtime_resolution(
        document,
        runtime_plan,
        resolver_report_bytes=resolver_report_bytes,
    )


def validate_musicfm_fma_runtime_resolution(
    resolution: Mapping[str, Any],
    runtime_plan: Mapping[str, Any],
    *,
    resolver_report_bytes: bytes,
) -> dict[str, Any]:
    document = dict(resolution)
    if document.get("schema") != MUSICFM_FMA_RUNTIME_RESOLUTION_SCHEMA:
        raise ValueError("unsupported MusicFM-FMA runtime resolution schema")
    supplied = document.get("document_sha256")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if supplied != document_sha256(unsigned):
        raise ValueError("MusicFM-FMA runtime resolution hash changed")
    commit = str(document.get("repository_commit") or "")
    if not _COMMIT.fullmatch(commit):
        raise ValueError("MusicFM-FMA runtime resolution commit changed")
    report = _parse_and_validate_report(resolver_report_bytes)
    expected = _resolution_values(
        runtime_plan,
        report,
        report_bytes=resolver_report_bytes,
        repository_commit=commit,
    )
    if unsigned != expected:
        raise ValueError("MusicFM-FMA runtime resolution evidence or authority changed")
    return document


def _parse_and_validate_report(raw: bytes) -> Mapping[str, Any]:
    try:
        report = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("resolver report must be valid UTF-8 JSON") from error
    if not isinstance(report, Mapping) or report.get("version") != "1":
        raise ValueError("unsupported pip resolver report")
    environment = report.get("environment")
    if not isinstance(environment, Mapping):
        raise ValueError("resolver report environment is missing")
    if environment.get("platform_system") != "Darwin":
        raise ValueError("this partial-evidence schema requires the Darwin report")
    installs = report.get("install")
    if not isinstance(installs, list) or len(installs) != len(_CANDIDATE_WHEELS):
        raise ValueError("resolver report package roster changed")
    for observed, expected in zip(installs, _CANDIDATE_WHEELS):
        _validate_report_package(observed, expected)
    return report


def _validate_report_package(observed: Any, expected: tuple[Any, ...]) -> None:
    """Validate one candidate wheel's exact index identity and selection flags."""

    if not isinstance(observed, Mapping):
        raise ValueError("resolver report package row changed")
    metadata = observed.get("metadata")
    download = observed.get("download_info")
    if not isinstance(metadata, Mapping) or not isinstance(download, Mapping):
        raise ValueError("resolver report package metadata changed")
    name, version, filename, _bytes, sha256, requested = expected
    observed_name = str(metadata.get("name") or "").lower().replace("_", "-")
    observed_filename = unquote(
        urlsplit(str(download.get("url") or "")).path.rsplit("/", 1)[-1]
    )
    archive = download.get("archive_info")
    hashes = archive.get("hashes") if isinstance(archive, Mapping) else None
    observed_sha = hashes.get("sha256") if isinstance(hashes, Mapping) else None
    if (
        observed_name != name
        or metadata.get("version") != version
        or observed_filename != filename
        or observed_sha != sha256
        or observed.get("requested") is not requested
        or observed.get("is_yanked") is not False
    ):
        raise ValueError("resolver report package identity changed")


def _resolution_values(
    runtime_plan: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    report_bytes: bytes,
    repository_commit: str,
) -> dict[str, Any]:
    runtime = dict(runtime_plan)
    runtime_sha = runtime.get("document_sha256")
    if not isinstance(runtime_sha, str):
        raise ValueError("runtime plan document identity is missing")
    environment = report["environment"]
    rows = [
        {
            "package": name,
            "version": version,
            "filename": filename,
            "bytes": size,
            "sha256": sha256,
            "direct_requirement": requested,
            "artifact_downloaded": False,
            "licence_reviewed_from_wheel": False,
        }
        for name, version, filename, size, sha256, requested in _CANDIDATE_WHEELS
    ]
    total = sum(row["bytes"] for row in rows)
    return {
        "schema": MUSICFM_FMA_RUNTIME_RESOLUTION_SCHEMA,
        "status": "partial_candidate_resolution_platform_marker_blocked_no_download",
        "repository_commit": repository_commit,
        "binding": {
            "runtime_plan_sha256": runtime_sha,
            "resolver_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "resolver_report_bytes": len(report_bytes),
        },
        "requested_target": {
            "operating_system": "Windows",
            "architecture": "win_amd64",
            "python_version": "3.11",
            "implementation": "cp",
            "abi": "cp311",
        },
        "actual_marker_environment": {
            "platform_system": environment.get("platform_system"),
            "platform_machine": environment.get("platform_machine"),
            "python_version": environment.get("python_version"),
            "sys_platform": environment.get("sys_platform"),
        },
        "candidate_wheels": {
            "items": rows,
            "count": len(rows),
            "observed_total_bytes": total,
            "windows_wheel_selection_requested": True,
            "environment_markers_evaluated_natively_on_windows": False,
            "complete_transitive_closure": False,
            "installable_lock": False,
        },
        "marker_audit": {
            "known_windows_only_requirement_missing": {
                "parent_package": "tqdm",
                "requirement": 'colorama; platform_system == "Windows"',
            },
            "host_satisfied_requirement_needing_native_recheck": {
                "parent_package": "huggingface-hub",
                "requirement": "hf-xet on selected platform_machine values",
                "observed_candidate": "hf-xet==1.6.0",
            },
            "native_windows_resolution_required": True,
        },
        "gates": {
            "public_index_metadata_resolution_completed": True,
            "candidate_wheel_hashes_and_sizes_recorded": True,
            "native_windows_environment_markers_resolved": False,
            "complete_transitive_wheel_closure_resolved": False,
            "wheel_files_downloaded_and_verified": False,
            "wheel_licence_files_inspected": False,
            "isolated_runtime_installed": False,
        },
        "next_gate": {
            "kind": "native_windows_metadata_only_resolution",
            "retains_report_only": True,
            "downloads_wheels": False,
            "installs_packages": False,
            "imports_packages": False,
            "loads_model": False,
            "runs_inference": False,
            "opens_audio": False,
        },
        "authority": {
            "source_download_authorized": False,
            "wheel_download_authorized": False,
            "dependency_install_authorized": False,
            "model_import_authorized": False,
            "model_load_authorized": False,
            "inference_authorized": False,
            "private_audio_access_authorized": False,
            "training_execution_authorized": False,
            "product_ordering_changed": False,
        },
        "effects": {
            "wheel_downloaded": False,
            "dependency_installed": False,
            "model_imported": False,
            "model_loaded": False,
            "features_extracted": False,
            "training_started": False,
        },
    }


__all__ = [
    "MUSICFM_FMA_RUNTIME_RESOLUTION_SCHEMA",
    "create_musicfm_fma_runtime_resolution",
    "validate_musicfm_fma_runtime_resolution",
]
