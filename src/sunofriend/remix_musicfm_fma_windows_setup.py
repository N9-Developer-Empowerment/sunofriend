"""Exact native-Windows setup inputs for the frozen MusicFM-FMA provider."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit

from .source_receipt import document_sha256


MUSICFM_WINDOWS_INSTALL_LOCK_SCHEMA = (
    "sunofriend.remix-musicfm-fma-native-windows-install-lock.v0"
)
MUSICFM_WINDOWS_ASSET_MANIFEST_SCHEMA = (
    "sunofriend.remix-musicfm-fma-asset-download-manifest.v0"
)
NATIVE_RECEIPT_SCHEMA = (
    "sunofriend.remix-musicfm-fma-native-windows-resolution-receipt.v0"
)

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAXIMUM_WHEEL_BYTES = 3_500_000_000

# Exact native Windows resolver result retained on 2026-08-21.  Unlike the
# earlier Darwin-hosted partial pass, this includes colorama and excludes
# hf-xet.  Entries are (normalised name, version, filename, sha256, requested).
_WINDOWS_WHEELS = (
    (
        "torch",
        "2.7.1+cu128",
        "torch-2.7.1+cu128-cp311-cp311-win_amd64.whl",
        "138c66dcd0ed2f07aafba3ed8b7958e2bed893694990e0b4b55b6b2b4a336aa6",
        True,
    ),
    (
        "torchaudio",
        "2.7.1+cu128",
        "torchaudio-2.7.1+cu128-cp311-cp311-win_amd64.whl",
        "37a42de8c0f601dc0bc7dcccc4049644ef5adcf45920dd5813c339121e5b5a8c",
        True,
    ),
    (
        "transformers",
        "4.53.2",
        "transformers-4.53.2-py3-none-any.whl",
        "db8f4819bb34f000029c73c3c557e7d06fc1b8e612ec142eecdae3947a9c78bf",
        True,
    ),
    (
        "einops",
        "0.8.1",
        "einops-0.8.1-py3-none-any.whl",
        "919387eb55330f5757c6bea9165c5ff5cfe63a642682ea788a6d472576d81737",
        True,
    ),
    (
        "huggingface-hub",
        "0.36.2",
        "huggingface_hub-0.36.2-py3-none-any.whl",
        "48f0c8eac16145dfce371e9d2d7772854a4f591bcb56c9cf548accf531d54270",
        False,
    ),
    (
        "tokenizers",
        "0.21.4",
        "tokenizers-0.21.4-cp39-abi3-win_amd64.whl",
        "475d807a5c3eb72c59ad9b5fcdb254f6e17f53dfcbb9903233b0dfa9c943b597",
        False,
    ),
    (
        "fsspec",
        "2026.7.0",
        "fsspec-2026.7.0-py3-none-any.whl",
        "b57ddbafedfaef7018c1ecab32aa200a9d7ca26b77965f64e48b70061249d279",
        False,
    ),
    (
        "numpy",
        "2.4.6",
        "numpy-2.4.6-cp311-cp311-win_amd64.whl",
        "1e254a00cdf42b1e4d5b3d68d33af63268d41340d8885df2ab6470f2e1500147",
        False,
    ),
    (
        "packaging",
        "26.3",
        "packaging-26.3-py3-none-any.whl",
        "d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c",
        False,
    ),
    (
        "pyyaml",
        "6.0.3",
        "pyyaml-6.0.3-cp311-cp311-win_amd64.whl",
        "9f3bfb4965eb874431221a3ff3fdcddc7e74e3b07799e0e84ca4a0f867d449bf",
        False,
    ),
    (
        "regex",
        "2026.7.19",
        "regex-2026.7.19-cp311-cp311-win_amd64.whl",
        "8d3469c91dd92ee41b7c95280edbd975ef1ba9195086686623a1c6e8935ce965",
        False,
    ),
    (
        "safetensors",
        "0.8.0",
        "safetensors-0.8.0-cp310-abi3-win_amd64.whl",
        "096ec1a98435df7beb08853bb5aa9081a84f23d0adc67ed1a0a10550f608373f",
        False,
    ),
    (
        "sympy",
        "1.14.0",
        "sympy-1.14.0-py3-none-any.whl",
        "e091cc3e99d2141a0ba2847328f5479b05d94a6635cb96148ccb3f34671bd8f5",
        False,
    ),
    (
        "mpmath",
        "1.3.0",
        "mpmath-1.3.0-py3-none-any.whl",
        "a0b2b9fe80bbcd81a6647ff13108738cfb482d481d826cc0e02f5b35e5c88d2c",
        False,
    ),
    (
        "tqdm",
        "4.70.0",
        "tqdm-4.70.0-py3-none-any.whl",
        "7f585706bfddbdebf89daac705b2dfcc16890130727d3197ca62c732b4310953",
        False,
    ),
    (
        "typing-extensions",
        "4.16.0",
        "typing_extensions-4.16.0-py3-none-any.whl",
        "481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8",
        False,
    ),
    (
        "colorama",
        "0.4.6",
        "colorama-0.4.6-py2.py3-none-any.whl",
        "4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6",
        False,
    ),
    (
        "filelock",
        "3.32.3",
        "filelock-3.32.3-py3-none-any.whl",
        "7f0ca4bcc0e181c60dbbd8aa9ab5b120ebb99e4e064e83636340056f833a1f09",
        False,
    ),
    (
        "jinja2",
        "3.1.6",
        "jinja2-3.1.6-py3-none-any.whl",
        "85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67",
        False,
    ),
    (
        "markupsafe",
        "3.0.3",
        "markupsafe-3.0.3-cp311-cp311-win_amd64.whl",
        "de8a88e63464af587c950061a5e6a67d3632e36df62b986892331d4620a35c01",
        False,
    ),
    (
        "networkx",
        "3.6.1",
        "networkx-3.6.1-py3-none-any.whl",
        "d47fbf302e7d9cbbb9e2555a0d267983d2aa476bac30e90dfbe5669bd57f3762",
        False,
    ),
    (
        "requests",
        "2.34.2",
        "requests-2.34.2-py3-none-any.whl",
        "2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0",
        False,
    ),
    (
        "charset-normalizer",
        "3.5.1",
        "charset_normalizer-3.5.1-cp311-cp311-win_amd64.whl",
        "f9b1e28d0e8dbfa858abdba91d6b547beaf2df1a59bec6da6faae7b96a4991a9",
        False,
    ),
    (
        "idna",
        "3.19",
        "idna-3.19-py3-none-any.whl",
        "815e7be7a7806d54abb586dc943addc79e8b2ee16915059658cbeff4b1b43bf4",
        False,
    ),
    (
        "urllib3",
        "2.7.0",
        "urllib3-2.7.0-py3-none-any.whl",
        "9fb4c81ebbb1ce9531cce37674bbc6f1360472bc18ca9a553ede278ef7276897",
        False,
    ),
    (
        "certifi",
        "2026.7.22",
        "certifi-2026.7.22-py3-none-any.whl",
        "62f22742b58a1a33014a2b6b706588a8d7e2a88ae7bd1a6ebe8c992928483775",
        False,
    ),
)

_SOURCE_REVISION = "b83ebedb401bcef639b26b05c0c8bee1dc2dfe71"
_MODEL_REVISION = "4513b38bc25ad1d227b1980819b9691ba97f4d87"
_CONFIG_REVISION = "6b36ef01c6443c67ae7ed0822876d091ab50e4aa"
_STATIC_EVIDENCE_SHA256 = (
    "99f1c24d44a3f08d68d614e4878c1cc0c05f1e941e071cbb9a3f5e9c7aeaf846"
)
_READINESS_SHA256 = "699515e32ce70fc20e5f1f528f988ad6746e01d89580b436e644ec0f8ffbc2a9"


def create_windows_install_lock(
    resolver_report_bytes: bytes,
    native_receipt_bytes: bytes,
    *,
    repository_commit: str,
) -> dict[str, Any]:
    _commit(repository_commit)
    document = _create_lock_unchecked(
        resolver_report_bytes, native_receipt_bytes, repository_commit
    )
    return validate_windows_install_lock(
        document,
        resolver_report_bytes,
        native_receipt_bytes,
    )


def validate_windows_install_lock(
    value: Mapping[str, Any],
    resolver_report_bytes: bytes,
    native_receipt_bytes: bytes,
) -> dict[str, Any]:
    document = _verified(value, MUSICFM_WINDOWS_INSTALL_LOCK_SCHEMA)
    commit = str(document.get("repository_commit") or "")
    _commit(commit)
    expected = _create_lock_unchecked(
        resolver_report_bytes,
        native_receipt_bytes,
        commit,
    )
    if document != expected:
        raise ValueError("native Windows MusicFM install lock changed")
    return document


def create_windows_asset_manifest(*, repository_commit: str) -> dict[str, Any]:
    _commit(repository_commit)
    document = _asset_manifest_values(repository_commit=repository_commit)
    document["document_sha256"] = document_sha256(document)
    return validate_windows_asset_manifest(document)


def _asset_manifest_values(*, repository_commit: str) -> dict[str, Any]:
    github = f"https://raw.githubusercontent.com/minzwon/musicfm/{_SOURCE_REVISION}"
    model = f"https://huggingface.co/minzwon/MusicFM/resolve/{_MODEL_REVISION}"
    config = (
        "https://huggingface.co/facebook/"
        "wav2vec2-conformer-rope-large-960h-ft/resolve/"
        f"{_CONFIG_REVISION}"
    )
    items = [
        _asset(
            "source",
            "source/musicfm/LICENSE",
            f"{github}/LICENSE",
            12_888,
            "5684e11c103b652a5fc59a2cc930c4bb63b5d4aa497e8519aaeb147bc4d34877",
        ),
        _asset(
            "source",
            "source/musicfm/model/__init__.py",
            f"{github}/model/__init__.py",
            2,
            "75a11da44c802486bc6f65640aa48a730f0f684c5c07a42ba3cd1735eb3fb070",
        ),
        _asset(
            "source",
            "source/musicfm/model/musicfm_25hz.py",
            f"{github}/model/musicfm_25hz.py",
            8_605,
            "9645e51938e7a73689a0792ecb15ee957e0723582c8f040949eadd25036ec804",
        ),
        _asset(
            "source",
            "source/musicfm/modules/__init__.py",
            f"{github}/modules/__init__.py",
            2,
            "75a11da44c802486bc6f65640aa48a730f0f684c5c07a42ba3cd1735eb3fb070",
        ),
        _asset(
            "source",
            "source/musicfm/modules/conv.py",
            f"{github}/modules/conv.py",
            3_154,
            "585705a6450db374e8c411034e846491f7f48d4ed0516fbf8d3b84855ef0d7d1",
        ),
        _asset(
            "source",
            "source/musicfm/modules/features.py",
            f"{github}/modules/features.py",
            1_869,
            "aa8e99711f4a4eab522ff89fe86fc27e281e373ed0ae416743736da229f171da",
        ),
        _asset(
            "source",
            "source/musicfm/modules/random_quantizer.py",
            f"{github}/modules/random_quantizer.py",
            3_055,
            "2ffae390fbf7fefa8a62000ba0490af92ecc001d3b5715fb98f7a1e1578c2aa2",
        ),
        _asset(
            "statistics",
            "assets/fma_stats.json",
            f"{model}/fma_stats.json?download=true",
            2_281,
            "5416e468018bae68c6231d4cbb2b11f0d11c04e6437881505ae427a3f8344904",
        ),
        _asset(
            "conformer_config",
            "assets/wav2vec2-conformer-config.json",
            f"{config}/config.json?download=true",
            2_239,
            "7a63cb5706c9a37483f1973a3c226d54eb504ce15cf62cb52637019540c8a75d",
        ),
        _asset(
            "checkpoint",
            "assets/pretrained_fma.pt",
            f"{model}/pretrained_fma.pt?download=true",
            1_316_802_154,
            "68392eee13d34c2941b3761934abb6b1e67b2e9df498695bda2ea5c1087d4b96",
        ),
    ]
    return {
        "schema": MUSICFM_WINDOWS_ASSET_MANIFEST_SCHEMA,
        "status": "pinned_assets_approved_for_isolated_setup",
        "repository_commit": repository_commit,
        "binding": {
            "source_revision": _SOURCE_REVISION,
            "model_publication_revision": _MODEL_REVISION,
            "conformer_publication_revision": _CONFIG_REVISION,
            "static_evidence_sha256": _STATIC_EVIDENCE_SHA256,
            "readiness_sha256": _READINESS_SHA256,
        },
        "maximum_total_download_bytes": 1_317_000_000,
        "items": items,
        "authority": {
            "asset_download_authorized": True,
            "checkpoint_download_authorized": True,
            "model_load_authorized": False,
            "synthetic_inference_authorized": False,
            "private_audio_access_authorized": False,
        },
    }


def validate_windows_asset_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    document = _verified(value, MUSICFM_WINDOWS_ASSET_MANIFEST_SCHEMA)
    commit = str(document.get("repository_commit") or "")
    _commit(commit)
    expected = _asset_manifest_values(repository_commit=commit)
    expected["document_sha256"] = document_sha256(expected)
    if document != expected:
        raise ValueError("native Windows MusicFM asset manifest changed")
    return document


def _asset(kind: str, target: str, url: str, size: int, sha256: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "target_relative_path": target,
        "url": url,
        "bytes": size,
        "sha256": sha256,
    }


def _native_receipt(raw: bytes, report: bytes) -> Mapping[str, Any]:
    try:
        receipt = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("native resolver receipt must be UTF-8 JSON") from error
    if (
        not isinstance(receipt, Mapping)
        or receipt.get("schema") != NATIVE_RECEIPT_SCHEMA
    ):
        raise ValueError("wrong native Windows resolver receipt")
    if receipt.get("status") != "metadata_only_resolution_complete_unvalidated":
        raise ValueError("native Windows resolver status changed")
    record = receipt.get("report")
    if not isinstance(record, Mapping) or record != {
        "filename": "native-windows-pip-report.json",
        "bytes": len(report),
        "sha256": hashlib.sha256(report).hexdigest(),
    }:
        raise ValueError("native Windows resolver report binding changed")
    policy = receipt.get("resolver_policy")
    authority = receipt.get("authority")
    if (
        not isinstance(policy, Mapping)
        or any(
            policy.get(key) is not False
            for key in (
                "wheel_files_retained",
                "packages_installed",
                "packages_imported",
                "model_loaded",
                "audio_opened",
                "inference_run",
                "training_started",
            )
        )
        or not isinstance(authority, Mapping)
        or any(authority.values())
    ):
        raise ValueError("native Windows resolver effects or authority changed")
    return receipt


def _report(raw: bytes) -> Mapping[str, Any]:
    try:
        report = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("native resolver report must be UTF-8 JSON") from error
    environment = report.get("environment") if isinstance(report, Mapping) else None
    if report.get("version") != "1" or not isinstance(environment, Mapping):
        raise ValueError("unsupported native Windows pip report")
    if (
        environment.get("platform_system") != "Windows"
        or environment.get("platform_machine") != "AMD64"
        or environment.get("python_version") != "3.11"
        or environment.get("python_full_version") != "3.11.16"
        or environment.get("implementation_version") != "3.11.16"
    ):
        raise ValueError("native Windows resolver platform changed")
    return report


def _wheel_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    installs = report.get("install")
    if not isinstance(installs, list) or len(installs) != len(_WINDOWS_WHEELS):
        raise ValueError("native Windows resolver package count changed")
    observed: dict[str, Mapping[str, Any]] = {}
    for row in installs:
        if not isinstance(row, Mapping) or not isinstance(row.get("metadata"), Mapping):
            raise ValueError("native Windows resolver row changed")
        name = _normalise(row["metadata"].get("name"))
        if name in observed:
            raise ValueError("native Windows resolver repeats a package")
        observed[name] = row
    result: list[dict[str, Any]] = []
    for name, version, filename, sha256, requested in _WINDOWS_WHEELS:
        row = observed.get(name)
        if row is None:
            raise ValueError(f"native Windows resolver lacks {name}")
        info = row.get("download_info")
        metadata = row.get("metadata")
        archive = info.get("archive_info") if isinstance(info, Mapping) else None
        hashes = archive.get("hashes") if isinstance(archive, Mapping) else None
        url = str(info.get("url") or "") if isinstance(info, Mapping) else ""
        got_filename = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
        if (
            not isinstance(metadata, Mapping)
            or metadata.get("version") != version
            or got_filename != filename
            or not isinstance(hashes, Mapping)
            or hashes.get("sha256") != sha256
            or row.get("requested") is not requested
            or row.get("is_yanked") is not False
        ):
            raise ValueError(f"native Windows resolver identity changed for {name}")
        result.append(
            {
                "package": name,
                "version": version,
                "filename": filename,
                "sha256": sha256,
                "url": url,
            }
        )
    return result


def _normalise(value: Any) -> str:
    return str(value or "").lower().replace("_", "-")


def _verified(value: Mapping[str, Any], schema: str) -> dict[str, Any]:
    document = dict(value)
    supplied = document.get("document_sha256")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if (
        document.get("schema") != schema
        or not isinstance(supplied, str)
        or not _SHA256.fullmatch(supplied)
        or supplied != document_sha256(unsigned)
    ):
        raise ValueError("native Windows MusicFM setup document hash changed")
    return document


def _commit(value: str) -> None:
    if not _COMMIT.fullmatch(value):
        raise ValueError("repository_commit must be a full Git commit")


# Non-recursive constructor used by the validator.
def _create_lock_unchecked(
    report: bytes, receipt: bytes, commit: str
) -> dict[str, Any]:
    checked_receipt = _native_receipt(receipt, report)
    document: dict[str, Any] = {
        "schema": MUSICFM_WINDOWS_INSTALL_LOCK_SCHEMA,
        "status": "complete_native_resolution_approved_for_isolated_setup",
        "repository_commit": commit,
        "native_receipt_file_sha256": hashlib.sha256(receipt).hexdigest(),
        "native_report_sha256": hashlib.sha256(report).hexdigest(),
        "native_report_bytes": len(report),
        "platform": checked_receipt["platform"],
        "maximum_total_download_bytes": _MAXIMUM_WHEEL_BYTES,
        "items": _wheel_rows(_report(report)),
        "authority": {
            "wheel_download_authorized": True,
            "isolated_install_authorized": True,
            "existing_environment_modification_authorized": False,
            "model_load_authorized": False,
            "private_audio_access_authorized": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return document


__all__ = [
    "MUSICFM_WINDOWS_ASSET_MANIFEST_SCHEMA",
    "MUSICFM_WINDOWS_INSTALL_LOCK_SCHEMA",
    "create_windows_asset_manifest",
    "create_windows_install_lock",
    "validate_windows_asset_manifest",
    "validate_windows_install_lock",
]
