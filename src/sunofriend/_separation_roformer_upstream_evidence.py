"""Verify the tracked official evidence for the blocked RoFormer challenger.

The snapshot contains a bounded subset of GitHub's public release and tag-ref
responses plus the already-pinned repository licence identity.  This verifier
does not use the network, open either release asset, or turn absence of terms
into permission to use the checkpoint.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping


UPSTREAM_EVIDENCE = "private-separation-roformer-upstream-evidence.json"
UPSTREAM_EVIDENCE_BYTES = 3_362
UPSTREAM_EVIDENCE_SHA256 = (
    "7767d27d2b4e75f0780560e1510ca835af35a0f5600c200add5654b9cf875bd8"
)
UPSTREAM_EVIDENCE_SCHEMA = "sunofriend.private-roformer-upstream-evidence.v1"
UPSTREAM_VERIFICATION_SCHEMA = (
    "sunofriend.private-roformer-upstream-evidence-verification.v1"
)
OBSERVED_AT = "2026-08-01"
RELEASE_ID = 187_962_340
RELEASE_TAG = "v1.0.12"
RELEASE_REVISION = "aef04b2e52fb3beaf25e333199f5a7236e628e7b"
RELEASE_BODY = "BS Roformer model trained on MUSDB18HQ dataset"
CONFIG_ASSET_ID = 209_603_348
CONFIG_NAME = "config_bs_roformer_384_8_2_485100.yaml"
CONFIG_BYTES = 4_566
CHECKPOINT_ASSET_ID = 209_597_731
CHECKPOINT_NAME = "model_bs_roformer_ep_17_sdr_9.6568.ckpt"
CHECKPOINT_BYTES = 527_385_512
CODE_LICENSE_SHA256 = "3282dc057695ef5b9a64909a7092ca40b2c292c232580fc6ace6e5d665cc0207"
_MAXIMUM_EVIDENCE_BYTES = 64 * 1024


def _verify_private_roformer_upstream_evidence(
    repository_root: str | Path,
) -> dict[str, Any]:
    """Read and validate one exact tracked snapshot without network access."""

    root = Path(repository_root).expanduser().absolute()
    before = root.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        raise ValueError("RoFormer repository root must be a non-symlink directory")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(root, flags)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if os.get_inheritable(descriptor) or _identity(opened) != _identity(before):
            raise ValueError("RoFormer repository root changed before verification")
        contents = _read_evidence_file(descriptor)
        after = root.lstat()
        if _identity(after) != _identity(before):
            raise ValueError("RoFormer repository root changed during verification")
    finally:
        os.close(descriptor)
    return _report_from_verified_contents(contents)


def _report_from_verified_contents(contents: bytes) -> dict[str, Any]:
    if len(contents) != UPSTREAM_EVIDENCE_BYTES:
        raise ValueError("RoFormer upstream evidence file size differs")
    if hashlib.sha256(contents).hexdigest() != UPSTREAM_EVIDENCE_SHA256:
        raise ValueError("RoFormer upstream evidence file hash differs")
    try:
        document = json.loads(contents.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(
            "RoFormer upstream evidence is not valid UTF-8 JSON"
        ) from error
    if not isinstance(document, Mapping):
        raise ValueError("RoFormer upstream evidence must be an object")
    _validate_private_roformer_upstream_evidence(document)
    report: dict[str, Any] = {
        "schema": UPSTREAM_VERIFICATION_SCHEMA,
        "status": "verified_no_checkpoint_authority",
        "path_free": True,
        "verification_sha256": "",
        "snapshot": {
            "path": UPSTREAM_EVIDENCE,
            "bytes": len(contents),
            "sha256": hashlib.sha256(contents).hexdigest(),
            "observed_at": document["observed_at"],
        },
        "release": {
            "id": document["release"]["id"],
            "tag": document["release"]["tag_name"],
            "revision": document["tag_ref"]["object"]["sha"],
            "body": document["release"]["body"],
            "asset_count": len(document["release"]["assets"]),
        },
        "checkpoint": {
            "asset_id": CHECKPOINT_ASSET_ID,
            "name": CHECKPOINT_NAME,
            "bytes": CHECKPOINT_BYTES,
            "published_digest": None,
            "terms_stated_in_release_body": False,
            "allowed_use_verified": False,
            "identity_verified": False,
        },
        "code_license": {
            "identifier": "MIT",
            "sha256": CODE_LICENSE_SHA256,
            "checkpoint_scope_inferred": False,
        },
        "readiness": {
            "official_release_snapshot_verified": True,
            "release_tag_revision_verified": True,
            "checkpoint_digest_published": False,
            "checkpoint_terms_verified": False,
            "checkpoint_allowed_use_verified": False,
            "checkpoint_identity_verified": False,
            "private_evaluation_eligible": False,
        },
        "blockers": [
            "checkpoint_allowed_use_unverified",
            "checkpoint_sha256_unpublished",
            "checkpoint_terms_unverified",
        ],
        "effects": {
            "filesystem_accessed": True,
            "filesystem_written": False,
            "network_used": False,
            "checkpoint_opened": False,
            "checkpoint_downloaded": False,
            "checkpoint_deserialized": False,
            "model_imported": False,
            "process_started": False,
            "product_route_changed": False,
        },
    }
    report["verification_sha256"] = _verification_sha256(report)
    return report


def _validate_private_roformer_upstream_evidence(value: Mapping[str, Any]) -> None:
    if set(value) != {
        "schema",
        "observed_at",
        "observation",
        "release",
        "tag_ref",
        "code_license",
        "findings",
    }:
        raise ValueError("RoFormer upstream evidence fields differ")
    if value.get("schema") != UPSTREAM_EVIDENCE_SCHEMA:
        raise ValueError("RoFormer upstream evidence schema differs")
    if value.get("observed_at") != OBSERVED_AT:
        raise ValueError("RoFormer upstream evidence observation date differs")
    observation = _mapping(value.get("observation"), "observation")
    if observation != {
        "official_primary_sources_only": True,
        "release_api_url": (
            "https://api.github.com/repos/ZFTurbo/"
            "Music-Source-Separation-Training/releases/tags/v1.0.12"
        ),
        "tag_ref_api_url": (
            "https://api.github.com/repos/ZFTurbo/"
            "Music-Source-Separation-Training/git/ref/tags/v1.0.12"
        ),
        "license_url": (
            "https://raw.githubusercontent.com/ZFTurbo/"
            "Music-Source-Separation-Training/"
            f"{RELEASE_REVISION}/LICENSE"
        ),
        "network_used_to_observe": True,
        "checkpoint_asset_downloaded": False,
        "config_asset_downloaded": False,
    }:
        raise ValueError("RoFormer upstream evidence observation differs")
    release = _mapping(value.get("release"), "release")
    expected_release = {
        "id": RELEASE_ID,
        "url": (
            "https://api.github.com/repos/ZFTurbo/"
            "Music-Source-Separation-Training/releases/187962340"
        ),
        "html_url": (
            "https://github.com/ZFTurbo/Music-Source-Separation-Training/"
            "releases/tag/v1.0.12"
        ),
        "tag_name": RELEASE_TAG,
        "target_commitish": "main",
        "name": "BS Roformer MUSDB18HQ",
        "draft": False,
        "prerelease": False,
        "created_at": "2024-11-28T06:40:53Z",
        "published_at": "2024-11-28T07:57:50Z",
        "body": RELEASE_BODY,
        "assets": release.get("assets"),
    }
    if release != expected_release:
        raise ValueError("RoFormer upstream release evidence differs")
    assets = release.get("assets")
    if not isinstance(assets, list) or assets != [
        _expected_asset(
            asset_id=CONFIG_ASSET_ID,
            name=CONFIG_NAME,
            size=CONFIG_BYTES,
            created_at="2024-11-28T07:57:05Z",
            updated_at="2024-11-28T07:57:06Z",
        ),
        _expected_asset(
            asset_id=CHECKPOINT_ASSET_ID,
            name=CHECKPOINT_NAME,
            size=CHECKPOINT_BYTES,
            created_at="2024-11-28T07:08:31Z",
            updated_at="2024-11-28T07:50:02Z",
        ),
    ]:
        raise ValueError("RoFormer upstream release assets differ")
    tag_ref = _mapping(value.get("tag_ref"), "tag ref")
    if tag_ref != {
        "ref": "refs/tags/v1.0.12",
        "url": (
            "https://api.github.com/repos/ZFTurbo/"
            "Music-Source-Separation-Training/git/refs/tags/v1.0.12"
        ),
        "object": {
            "sha": RELEASE_REVISION,
            "type": "commit",
            "url": (
                "https://api.github.com/repos/ZFTurbo/"
                "Music-Source-Separation-Training/git/commits/"
                f"{RELEASE_REVISION}"
            ),
        },
    }:
        raise ValueError("RoFormer upstream tag evidence differs")
    if _mapping(value.get("code_license"), "code licence") != {
        "identifier": "MIT",
        "revision": RELEASE_REVISION,
        "path": "LICENSE",
        "bytes": 1_081,
        "sha256": CODE_LICENSE_SHA256,
    }:
        raise ValueError("RoFormer upstream code-licence evidence differs")
    if _mapping(value.get("findings"), "findings") != {
        "release_tag_resolves_to_pinned_revision": True,
        "checkpoint_digest_published_by_release_api": False,
        "checkpoint_terms_stated_in_release_body": False,
        "checkpoint_allowed_use_verified": False,
        "repository_code_license_projected_onto_checkpoint": False,
        "checkpoint_identity_verified": False,
        "private_evaluation_authorized": False,
    }:
        raise ValueError("RoFormer upstream findings differ")


def _expected_asset(
    *, asset_id: int, name: str, size: int, created_at: str, updated_at: str
) -> dict[str, Any]:
    return {
        "id": asset_id,
        "url": (
            "https://api.github.com/repos/ZFTurbo/"
            f"Music-Source-Separation-Training/releases/assets/{asset_id}"
        ),
        "name": name,
        "content_type": "application/octet-stream",
        "size": size,
        "digest": None,
        "created_at": created_at,
        "updated_at": updated_at,
        "browser_download_url": (
            "https://github.com/ZFTurbo/Music-Source-Separation-Training/"
            f"releases/download/{RELEASE_TAG}/{name}"
        ),
    }


def _read_evidence_file(root_descriptor: int) -> bytes:
    attached = os.stat(UPSTREAM_EVIDENCE, dir_fd=root_descriptor, follow_symlinks=False)
    if not stat.S_ISREG(attached.st_mode) or stat.S_ISLNK(attached.st_mode):
        raise ValueError("RoFormer upstream evidence file is unsafe")
    if attached.st_size != UPSTREAM_EVIDENCE_BYTES:
        raise ValueError("RoFormer upstream evidence file size differs")
    if attached.st_size > _MAXIMUM_EVIDENCE_BYTES:
        raise ValueError("RoFormer upstream evidence file exceeds audit bound")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(UPSTREAM_EVIDENCE, flags, dir_fd=root_descriptor)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if os.get_inheritable(descriptor) or _identity(opened) != _identity(attached):
            raise ValueError("RoFormer upstream evidence file changed")
        contents = bytearray()
        digest = hashlib.sha256()
        while block := os.read(descriptor, 64 * 1024):
            contents.extend(block)
            digest.update(block)
            if len(contents) > UPSTREAM_EVIDENCE_BYTES:
                raise ValueError("RoFormer upstream evidence file grew")
        after = os.fstat(descriptor)
        rebound = os.stat(
            UPSTREAM_EVIDENCE,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if _identity(after) != _identity(opened) or _identity(rebound) != _identity(
            opened
        ):
            raise ValueError("RoFormer upstream evidence file changed")
    finally:
        os.close(descriptor)
    if len(contents) != UPSTREAM_EVIDENCE_BYTES:
        raise ValueError("RoFormer upstream evidence file size differs")
    if digest.hexdigest() != UPSTREAM_EVIDENCE_SHA256:
        raise ValueError("RoFormer upstream evidence file hash differs")
    return bytes(contents)


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"RoFormer upstream {label} must be an object")
    return dict(value)


def _verification_sha256(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("verification_sha256", None)
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
    )


__all__ = [
    "UPSTREAM_EVIDENCE",
    "UPSTREAM_EVIDENCE_BYTES",
    "UPSTREAM_EVIDENCE_SHA256",
    "_report_from_verified_contents",
    "_validate_private_roformer_upstream_evidence",
    "_verification_sha256",
    "_verify_private_roformer_upstream_evidence",
]
