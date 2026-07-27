"""Private, confirm-before-publish Workbench listening-master cache.

The balanced selected-MIDI WAV is the immutable control.  This service creates
one fixed-policy listening-master challenger in owner-only pending storage and
publishes it to the rebuildable cache only after the caller presents the exact
pending token.  The persisted manifest is path-free; absolute paths exist only
in the private binding and in the server-facing materialized result.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .listening_master import build_listening_master
from .listening_master_contract import (
    FFMPEG_IDENTITY_POLICY,
    LISTENING_MASTER_EFFECTS,
    LISTENING_MASTER_LABEL,
    LISTENING_MASTER_POLICY,
    LISTENING_MASTER_PROCESSING_FLAGS,
    LISTENING_MASTER_SCHEMA,
    LISTENING_MASTER_SCOPE,
    LISTENING_MASTER_TARGETS,
    LISTENING_MASTER_TIMING_POLICY,
    LISTENING_MASTER_VERIFICATION_SCHEMA,
    verify_listening_master_artifacts,
)
from .workbench_balanced_contract import BALANCED_MIX_CONTRACT


WORKBENCH_LISTENING_MASTER_SCHEMA = (
    "sunofriend.workbench-listening-master.v1"
)
WORKBENCH_LISTENING_MASTER_KEY_SCHEMA = (
    "sunofriend.workbench-listening-master-key.v1"
)
WORKBENCH_LISTENING_MASTER_PRIVATE_BINDING_SCHEMA = (
    "sunofriend.workbench-listening-master-private-binding.v1"
)

_CACHE_DIRECTORY = "listening-masters"
_PENDING_DIRECTORY = ".pending"
_MANIFEST_NAME = "manifest.json"
_PRIVATE_BINDING_NAME = ".private-binding.json"
_MASTER_NAME = "listening-master.wav"
_RECEIPT_NAME = "listening-master-receipt.json"
_MAXIMUM_CACHE_ENTRIES = 8
_MAXIMUM_CACHE_BYTES = 2 * 1024 * 1024 * 1024
_MAXIMUM_JSON_BYTES = 4 * 1024 * 1024
_DEFAULT_PENDING_STALE_SECONDS = 6 * 60 * 60
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_PENDING_NAME_PATTERN = re.compile(
    r"^(?P<cache>[0-9a-f]{64})-(?P<token>[0-9a-f]{32})\.pending$"
)
_BUILDING_NAME_PATTERN = re.compile(
    r"^\.(?P<cache>[0-9a-f]{64})-(?P<token>[0-9a-f]{32})\.building$"
)

LISTENING_MASTER_SERVICE_EFFECTS: dict[str, bool] = {
    "source_audio_mutated": False,
    "source_audio_overwritten": False,
    "balanced_control_mutated": False,
    "balanced_control_replaced": False,
    "control_balance_replaced": False,
    "midi_mutated": False,
    "selection_changed": False,
    "feedback_recorded": False,
    "event_recorded": False,
    "automatic_selection": False,
    "automatic_ranking": False,
    "default_selection_changed": False,
    "listening_master_created": True,
}

_Builder = Callable[..., Mapping[str, Any]]


class WorkbenchListeningMasterService:
    """Build and retain verified listening masters for one Workbench state root."""

    def __init__(
        self,
        root: str | Path,
        *,
        builder: _Builder = build_listening_master,
        ffmpeg_path: str | Path | None = None,
        pending_stale_seconds: int = _DEFAULT_PENDING_STALE_SECONDS,
    ) -> None:
        if (
            isinstance(pending_stale_seconds, bool)
            or not isinstance(pending_stale_seconds, int)
            or pending_stale_seconds < 1
        ):
            raise ValueError("listening-master pending age must be a positive integer")
        state_root = Path(root).expanduser().resolve()
        self.root = state_root / _CACHE_DIRECTORY
        self._pending_root = self.root / _PENDING_DIRECTORY
        self._builder = builder
        self._ffmpeg_path = (
            Path(ffmpeg_path).expanduser().resolve()
            if ffmpeg_path is not None
            else None
        )
        self._pending_stale_seconds = pending_stale_seconds
        self._live_pending: set[tuple[str, str]] = set()
        self._lock = threading.RLock()

    def cached(self, balanced: Mapping[str, Any]) -> dict[str, Any] | None:
        """Return a fully reverified promoted artifact for this exact balance."""

        binding = _validated_balanced_binding(balanced)
        cache_key = _cache_key(binding["public"])
        with self._lock:
            if not self.root.is_dir() or self.root.is_symlink():
                return None
            final = self.root / cache_key
            if not final.exists():
                return None
            result = self._load_entry(
                final,
                cache_key=cache_key,
                current_binding=binding,
            )
            if result is None:
                return None
            final.touch(exist_ok=True)
            self._prune_cache(cache_key)
            result["cache_hit"] = True
            return result

    def prepare(self, balanced: Mapping[str, Any]) -> dict[str, Any]:
        """Prepare one challenger privately without publishing it to the cache."""

        binding = _validated_balanced_binding(balanced)
        cache_key = _cache_key(binding["public"])
        with self._lock:
            self._ensure_storage()
            self._reclaim_stale_pending()
            final = self.root / cache_key
            if final.exists():
                result = self._load_entry(
                    final,
                    cache_key=cache_key,
                    current_binding=binding,
                )
                if result is None:
                    raise ValueError(
                        "listening-master cache entry failed full verification"
                    )
                final.touch(exist_ok=True)
                self._prune_cache(cache_key)
                result["cache_hit"] = True
                return result

            pending_token = uuid.uuid4().hex
            building = self._pending_root / (
                f".{cache_key}-{pending_token}.building"
            )
            pending = self._pending_root / (
                f"{cache_key}-{pending_token}.pending"
            )
            building.mkdir(mode=0o700, parents=False, exist_ok=False)
            _require_owner_only_directory(building)
            try:
                private_binding = _private_binding_document(
                    cache_key=cache_key,
                    pending_token=pending_token,
                    binding=binding,
                )
                _write_private_json(
                    building / _PRIVATE_BINDING_NAME,
                    private_binding,
                )
                self._builder(
                    Path(str(binding["preview"]["path"])),
                    output_path=building / _MASTER_NAME,
                    report_path=building / _RECEIPT_NAME,
                    ffmpeg_path=self._ffmpeg_path,
                )
                for artifact in (
                    building / _MASTER_NAME,
                    building / _RECEIPT_NAME,
                ):
                    artifact.chmod(0o600)
                    _require_owner_only_regular_file(artifact)
                current_binding = _validated_balanced_binding(balanced)
                if current_binding["public"] != binding["public"]:
                    raise ValueError(
                        "balanced artifact changed while preparing listening master"
                    )
                verification = verify_listening_master_artifacts(
                    Path(str(current_binding["preview"]["path"])),
                    building / _MASTER_NAME,
                    building / _RECEIPT_NAME,
                )
                manifest = _manifest_document(
                    cache_key=cache_key,
                    binding=binding,
                    master_path=building / _MASTER_NAME,
                    receipt_path=building / _RECEIPT_NAME,
                    verification=verification,
                )
                _write_private_json(building / _MANIFEST_NAME, manifest)
                _require_entry_within_cache_bound(building)
                _fsync_tree(building)
                building.rename(pending)
                _require_owner_only_directory(pending)
                _fsync_directory(self._pending_root)
            except BaseException:
                _remove_owned_directory(building)
                _remove_owned_directory(pending)
                raise

            self._live_pending.add((cache_key, pending_token))
            result = self._load_entry(
                pending,
                cache_key=cache_key,
                current_binding=binding,
                pending_token=pending_token,
            )
            if result is None:
                self._live_pending.discard((cache_key, pending_token))
                _remove_owned_directory(pending)
                raise RuntimeError(
                    "prepared listening-master artifacts failed verification"
                )
            result["cache_hit"] = False
            result["_pending_token"] = pending_token
            return result

    def promote(
        self,
        cache_key: str,
        pending_token: str | None = None,
    ) -> dict[str, Any]:
        """Publish exactly one caller-confirmed pending artifact.

        ``pending_token=None`` is accepted only for an already promoted cache,
        which lets callers treat a cache-hit prepare result uniformly.
        """

        _require_sha256(cache_key, label="listening-master cache key")
        if pending_token is not None:
            _require_pending_token(pending_token)
        with self._lock:
            self._ensure_storage()
            self._reclaim_stale_pending()
            final = self.root / cache_key
            if pending_token is None:
                result = self._load_entry(final, cache_key=cache_key)
                if result is None:
                    raise ValueError(
                        "listening-master cache entry is not promoted or verified"
                    )
                final.touch(exist_ok=True)
                self._prune_cache(cache_key)
                result["cache_hit"] = True
                return result

            pending = self._pending_path(cache_key, pending_token)
            pending_result = self._load_entry(
                pending,
                cache_key=cache_key,
                pending_token=pending_token,
            )
            if pending_result is None:
                # An exact repeated confirmation is an idempotent cache hit.
                promoted = self._load_entry(final, cache_key=cache_key)
                if (
                    promoted is not None
                    and promoted.get("_promoted_pending_token") == pending_token
                ):
                    final.touch(exist_ok=True)
                    self._prune_cache(cache_key)
                    promoted["cache_hit"] = True
                    return promoted
                raise ValueError(
                    "listening-master pending token is missing or failed verification"
                )
            _require_entry_within_cache_bound(pending)

            if final.exists():
                promoted = self._load_entry(
                    final,
                    cache_key=cache_key,
                    current_binding=pending_result["_balanced_binding"],
                )
                if (
                    promoted is None
                    or promoted["manifest_sha256"]
                    != pending_result["manifest_sha256"]
                ):
                    raise ValueError(
                        "a different listening master already owns this cache key"
                    )
                _remove_owned_directory(pending)
                self._live_pending.discard((cache_key, pending_token))
                promoted["cache_hit"] = True
                return promoted

            try:
                pending.rename(final)
                _require_owner_only_directory(final)
                promoted = self._load_entry(final, cache_key=cache_key)
                if promoted is None:
                    raise RuntimeError(
                        "promoted listening-master cache failed verification"
                    )
                _fsync_directory(self.root)
            except BaseException:
                if final.is_dir() and not final.is_symlink() and not pending.exists():
                    final.rename(pending)
                raise

            self._live_pending.discard((cache_key, pending_token))
            final.touch(exist_ok=True)
            self._prune_cache(cache_key)
            promoted["cache_hit"] = False
            return promoted

    def discard(self, cache_key: str, pending_token: str) -> bool:
        """Discard only the exact unpromoted work owned by the supplied token."""

        _require_sha256(cache_key, label="listening-master cache key")
        _require_pending_token(pending_token)
        with self._lock:
            if not self._pending_root.is_dir() or self._pending_root.is_symlink():
                return False
            pending = self._pending_path(cache_key, pending_token)
            if pending.is_symlink() or not pending.is_dir():
                return False
            binding = _read_private_binding(pending / _PRIVATE_BINDING_NAME)
            if (
                binding is None
                or binding.get("cache_key") != cache_key
                or binding.get("pending_token") != pending_token
            ):
                return False
            _remove_owned_directory(pending)
            self._live_pending.discard((cache_key, pending_token))
            _fsync_directory(self._pending_root)
            return True

    def _pending_path(self, cache_key: str, pending_token: str) -> Path:
        return self._pending_root / f"{cache_key}-{pending_token}.pending"

    def _ensure_storage(self) -> None:
        _ensure_owner_only_directory(self.root)
        _ensure_owner_only_directory(self._pending_root)

    def _load_entry(
        self,
        entry: Path,
        *,
        cache_key: str,
        current_binding: Mapping[str, Any] | None = None,
        pending_token: str | None = None,
    ) -> dict[str, Any] | None:
        if entry.is_symlink() or not entry.is_dir():
            return None
        try:
            _require_owner_only_directory(entry)
            manifest = _read_json(entry / _MANIFEST_NAME)
            if not _valid_manifest(manifest, cache_key=cache_key):
                return None
            private = _read_private_binding(entry / _PRIVATE_BINDING_NAME)
            if private is None or private.get("cache_key") != cache_key:
                return None
            if pending_token is not None and private.get("pending_token") != pending_token:
                return None
            stored_balanced = private.get("balanced")
            if not isinstance(stored_balanced, Mapping):
                return None
            stored_binding = _validated_balanced_binding(stored_balanced)
            if stored_binding["public"] != _balanced_public_from_manifest(manifest):
                return None
            if (
                current_binding is not None
                and current_binding["public"] != stored_binding["public"]
            ):
                return None
            active_binding = current_binding or stored_binding
            master_path = entry / _MASTER_NAME
            receipt_path = entry / _RECEIPT_NAME
            if (
                _file_record(master_path, include_path=False) != manifest["master"]
                or _file_record(receipt_path, include_path=False)
                != manifest["receipt"]
            ):
                return None
            verification = verify_listening_master_artifacts(
                Path(str(active_binding["preview"]["path"])),
                master_path,
                receipt_path,
            )
            if _verification_summary(verification) != manifest["summary"]:
                return None
        except (KeyError, OSError, RuntimeError, TypeError, ValueError):
            return None

        result = dict(manifest)
        result["master"] = _file_record(master_path, include_path=True)
        result["receipt"] = _file_record(receipt_path, include_path=True)
        result["_balanced_binding"] = active_binding
        result["_promoted_pending_token"] = private["pending_token"]
        return result

    def _reclaim_stale_pending(self) -> None:
        if not self._pending_root.is_dir() or self._pending_root.is_symlink():
            return
        cutoff_ns = time.time_ns() - (
            self._pending_stale_seconds * 1_000_000_000
        )
        for candidate in self._pending_root.iterdir():
            if candidate.is_symlink() or not candidate.is_dir():
                continue
            pending_match = _PENDING_NAME_PATTERN.fullmatch(candidate.name)
            building_match = _BUILDING_NAME_PATTERN.fullmatch(candidate.name)
            match = pending_match or building_match
            if match is None:
                continue
            cache_key = match.group("cache")
            token = match.group("token")
            if (cache_key, token) in self._live_pending:
                continue
            try:
                modified_ns = os.lstat(candidate).st_mtime_ns
            except OSError:
                continue
            if modified_ns > cutoff_ns:
                continue
            if building_match is not None:
                _remove_owned_directory(candidate)
                continue
            private = _read_private_binding(candidate / _PRIVATE_BINDING_NAME)
            if (
                private is None
                or private.get("cache_key") != cache_key
                or private.get("pending_token") != token
                or int(private.get("created_ns", cutoff_ns + 1)) > cutoff_ns
            ):
                continue
            _remove_owned_directory(candidate)

    def _prune_cache(self, keep_cache_key: str) -> None:
        entries: list[Path] = []
        for candidate in self.root.iterdir():
            if (
                candidate.name == _PENDING_DIRECTORY
                or candidate.is_symlink()
                or not candidate.is_dir()
                or not _is_sha256(candidate.name)
                or not _authenticated_cache_directory(candidate)
            ):
                continue
            entries.append(candidate)
        entries.sort(
            key=lambda path: (
                path.name == keep_cache_key,
                os.lstat(path).st_mtime_ns,
            ),
            reverse=True,
        )
        retained_entries = 0
        retained_bytes = 0
        for entry in entries:
            entry_bytes = _directory_regular_file_bytes(entry)
            keep = (
                entry.name == keep_cache_key
                or (
                    retained_entries < _MAXIMUM_CACHE_ENTRIES
                    and retained_bytes + entry_bytes <= _MAXIMUM_CACHE_BYTES
                )
            )
            if keep:
                retained_entries += 1
                retained_bytes += entry_bytes
                continue
            _remove_owned_directory(entry)


WorkbenchListeningMaster = WorkbenchListeningMasterService


def _validated_balanced_binding(
    balanced: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(balanced, Mapping):
        raise ValueError("balanced artifact must be a verified mapping")
    required = {
        "schema",
        "cache_key",
        "manifest_sha256",
        "selection_manifest_sha256",
        "policy",
        "mastered",
        "preview",
        "report",
        "receipt",
    }
    if not required <= set(balanced):
        raise ValueError("balanced artifact is missing verified identities")
    if (
        balanced.get("schema") != BALANCED_MIX_CONTRACT.arrangement_schema
        or balanced.get("policy") != BALANCED_MIX_CONTRACT.policy
        or balanced.get("mastered") is not False
    ):
        raise ValueError("balanced artifact policy is not eligible for mastering")
    for key in ("cache_key", "manifest_sha256", "selection_manifest_sha256"):
        _require_sha256(balanced.get(key), label=f"balanced {key}")

    preview = _validated_file_record(
        balanced.get("preview"),
        expected_name="balanced-selected-midi-preview.wav",
        label="balanced preview",
    )
    report = _validated_file_record(
        balanced.get("report"),
        expected_name="balanced-mix-receipt.json",
        label="balanced report",
    )
    receipt = _read_json(Path(str(report["path"])))
    if receipt != balanced.get("receipt"):
        raise ValueError("balanced report no longer matches verified receipt")
    if (
        receipt.get("schema") != BALANCED_MIX_CONTRACT.receipt_schema
        or not _is_sha256(receipt.get("receipt_sha256"))
        or _document_hash(
            {
                key: value
                for key, value in receipt.items()
                if key != "receipt_sha256"
            }
        )
        != receipt["receipt_sha256"]
        or receipt.get("selection_manifest_sha256")
        != balanced["selection_manifest_sha256"]
        or receipt.get("policy") != BALANCED_MIX_CONTRACT.policy
        or receipt.get("mastered") is not False
    ):
        raise ValueError("balanced report receipt is invalid")

    public = {
        "balanced_arrangement_schema": str(balanced["schema"]),
        "balanced_arrangement_manifest_sha256": str(
            balanced["manifest_sha256"]
        ),
        "balanced_arrangement_cache_key": str(balanced["cache_key"]),
        "selection_manifest_sha256": str(
            balanced["selection_manifest_sha256"]
        ),
        "balanced_preview": {
            "name": str(preview["name"]),
            "bytes": int(preview["bytes"]),
            "sha256": str(preview["sha256"]),
        },
        "balanced_report": {
            "name": str(report["name"]),
            "bytes": int(report["bytes"]),
            "sha256": str(report["sha256"]),
            "receipt_schema": str(receipt["schema"]),
            "receipt_sha256": str(receipt["receipt_sha256"]),
        },
    }
    stored_balanced = {
        "schema": str(balanced["schema"]),
        "cache_key": str(balanced["cache_key"]),
        "manifest_sha256": str(balanced["manifest_sha256"]),
        "selection_manifest_sha256": str(
            balanced["selection_manifest_sha256"]
        ),
        "policy": str(balanced["policy"]),
        "mastered": False,
        "preview": preview,
        "report": report,
        "receipt": receipt,
    }
    return {
        "public": public,
        "preview": preview,
        "report": report,
        "stored_balanced": stored_balanced,
    }


def _cache_key(public_binding: Mapping[str, Any]) -> str:
    return _document_hash(
        {
            "schema": WORKBENCH_LISTENING_MASTER_KEY_SCHEMA,
            "balanced": public_binding,
            "master_contract": _master_contract_document(),
        }
    )


def _master_contract_document() -> dict[str, Any]:
    return {
        "service_schema": WORKBENCH_LISTENING_MASTER_SCHEMA,
        "receipt_schema": LISTENING_MASTER_SCHEMA,
        "verification_schema": LISTENING_MASTER_VERIFICATION_SCHEMA,
        "policy": LISTENING_MASTER_POLICY,
        "label": LISTENING_MASTER_LABEL,
        "scope": LISTENING_MASTER_SCOPE,
        "timing_policy": LISTENING_MASTER_TIMING_POLICY,
        "ffmpeg_identity_policy": FFMPEG_IDENTITY_POLICY,
        "targets": _json_copy(dict(LISTENING_MASTER_TARGETS)),
        "processing": _json_copy(dict(LISTENING_MASTER_PROCESSING_FLAGS)),
        "receipt_effects": _json_copy(dict(LISTENING_MASTER_EFFECTS)),
        "service_effects": dict(LISTENING_MASTER_SERVICE_EFFECTS),
    }


def _private_binding_document(
    *,
    cache_key: str,
    pending_token: str,
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": WORKBENCH_LISTENING_MASTER_PRIVATE_BINDING_SCHEMA,
        "cache_key": cache_key,
        "pending_token": pending_token,
        "created_ns": time.time_ns(),
        "balanced": _json_copy(binding["stored_balanced"]),
    }


def _manifest_document(
    *,
    cache_key: str,
    binding: Mapping[str, Any],
    master_path: Path,
    receipt_path: Path,
    verification: Mapping[str, Any],
) -> dict[str, Any]:
    summary = _verification_summary(verification)
    public = binding["public"]
    if (
        summary.get("source", {}).get("sha256")
        != public["balanced_preview"]["sha256"]
        or summary.get("source", {}).get("bytes")
        != public["balanced_preview"]["bytes"]
    ):
        raise ValueError(
            "listening-master verification source is not the balanced preview"
        )
    payload = {
        "schema": WORKBENCH_LISTENING_MASTER_SCHEMA,
        "cache_key": cache_key,
        "selection_manifest_sha256": public["selection_manifest_sha256"],
        "balanced_arrangement_schema": public["balanced_arrangement_schema"],
        "balanced_arrangement_manifest_sha256": public[
            "balanced_arrangement_manifest_sha256"
        ],
        "balanced_arrangement_cache_key": public[
            "balanced_arrangement_cache_key"
        ],
        "balanced_preview_sha256": public["balanced_preview"]["sha256"],
        "balanced_preview_bytes": public["balanced_preview"]["bytes"],
        "balanced_report_sha256": public["balanced_report"]["sha256"],
        "balanced_report_bytes": public["balanced_report"]["bytes"],
        "balanced_report_receipt_schema": public["balanced_report"][
            "receipt_schema"
        ],
        "balanced_report_receipt_sha256": public["balanced_report"][
            "receipt_sha256"
        ],
        "receipt_schema": LISTENING_MASTER_SCHEMA,
        "policy": LISTENING_MASTER_POLICY,
        "mastered": True,
        "release_master": False,
        "master": _file_record(master_path, include_path=False),
        "receipt": _file_record(receipt_path, include_path=False),
        "summary": summary,
        "effects": dict(LISTENING_MASTER_SERVICE_EFFECTS),
        "path_free_manifest": True,
        "private_audio": True,
    }
    if not _path_free_document(payload):
        raise RuntimeError("listening-master manifest contains a local path")
    return {**payload, "manifest_sha256": _document_hash(payload)}


def _verification_summary(verification: Mapping[str, Any]) -> dict[str, Any]:
    if (
        not isinstance(verification, Mapping)
        or verification.get("schema") != LISTENING_MASTER_VERIFICATION_SCHEMA
        or verification.get("status") != "verified"
        or verification.get("receipt_schema") != LISTENING_MASTER_SCHEMA
        or verification.get("policy") != LISTENING_MASTER_POLICY
        or verification.get("mastered") is not True
        or verification.get("release_master") is not False
        or verification.get("effects") != LISTENING_MASTER_EFFECTS
    ):
        raise ValueError("listening-master verification contract is invalid")
    summary = {
        key: _json_copy(value)
        for key, value in verification.items()
        if key != "receipt"
    }
    try:
        summary.update(
            {
                "input_integrated_lufs": verification["measurements"][
                    "analysis"
                ]["input_i"],
                "output_integrated_lufs": verification["measurements"][
                    "verification"
                ]["input_i"],
                "output_true_peak_dbtp": verification["measurements"][
                    "verification"
                ]["input_tp"],
            }
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "listening-master verification measurements are incomplete"
        ) from exc
    if not _path_free_document(summary):
        raise ValueError("listening-master verification summary contains a path")
    return summary


def _valid_manifest(value: Any, *, cache_key: str) -> bool:
    keys = {
        "schema",
        "cache_key",
        "selection_manifest_sha256",
        "balanced_arrangement_schema",
        "balanced_arrangement_manifest_sha256",
        "balanced_arrangement_cache_key",
        "balanced_preview_sha256",
        "balanced_preview_bytes",
        "balanced_report_sha256",
        "balanced_report_bytes",
        "balanced_report_receipt_schema",
        "balanced_report_receipt_sha256",
        "receipt_schema",
        "policy",
        "mastered",
        "release_master",
        "master",
        "receipt",
        "summary",
        "effects",
        "path_free_manifest",
        "private_audio",
        "manifest_sha256",
    }
    if not isinstance(value, dict) or set(value) != keys:
        return False
    unsigned = {
        key: item for key, item in value.items() if key != "manifest_sha256"
    }
    return bool(
        value.get("schema") == WORKBENCH_LISTENING_MASTER_SCHEMA
        and value.get("cache_key") == cache_key
        and _is_sha256(value.get("manifest_sha256"))
        and _document_hash(unsigned) == value["manifest_sha256"]
        and value.get("balanced_arrangement_schema")
        == BALANCED_MIX_CONTRACT.arrangement_schema
        and all(
            _is_sha256(value.get(key))
            for key in (
                "selection_manifest_sha256",
                "balanced_arrangement_manifest_sha256",
                "balanced_arrangement_cache_key",
                "balanced_preview_sha256",
                "balanced_report_sha256",
                "balanced_report_receipt_sha256",
            )
        )
        and _valid_nonnegative_int(value.get("balanced_preview_bytes"))
        and _valid_nonnegative_int(value.get("balanced_report_bytes"))
        and value.get("balanced_report_receipt_schema")
        == BALANCED_MIX_CONTRACT.receipt_schema
        and value.get("receipt_schema") == LISTENING_MASTER_SCHEMA
        and value.get("policy") == LISTENING_MASTER_POLICY
        and value.get("mastered") is True
        and value.get("release_master") is False
        and value.get("effects") == LISTENING_MASTER_SERVICE_EFFECTS
        and value.get("path_free_manifest") is True
        and value.get("private_audio") is True
        and _valid_path_free_file_record(value.get("master"), _MASTER_NAME)
        and _valid_path_free_file_record(value.get("receipt"), _RECEIPT_NAME)
        and isinstance(value.get("summary"), Mapping)
        and _path_free_document(value)
    )


def _balanced_public_from_manifest(
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "balanced_arrangement_schema": manifest["balanced_arrangement_schema"],
        "balanced_arrangement_manifest_sha256": manifest[
            "balanced_arrangement_manifest_sha256"
        ],
        "balanced_arrangement_cache_key": manifest[
            "balanced_arrangement_cache_key"
        ],
        "selection_manifest_sha256": manifest["selection_manifest_sha256"],
        "balanced_preview": {
            "name": "balanced-selected-midi-preview.wav",
            "bytes": manifest["balanced_preview_bytes"],
            "sha256": manifest["balanced_preview_sha256"],
        },
        "balanced_report": {
            "name": "balanced-mix-receipt.json",
            "bytes": manifest["balanced_report_bytes"],
            "sha256": manifest["balanced_report_sha256"],
            "receipt_schema": manifest["balanced_report_receipt_schema"],
            "receipt_sha256": manifest["balanced_report_receipt_sha256"],
        },
    }


def _validated_file_record(
    value: Any,
    *,
    expected_name: str,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} record is invalid")
    path_value = value.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"{label} path is invalid")
    path = _unresolved_absolute_path(path_value)
    name = value.get("name")
    if name != expected_name or path.name != expected_name:
        raise ValueError(f"{label} name is invalid")
    actual = _file_record(path, include_path=True)
    if (
        value.get("bytes") != actual["bytes"]
        or value.get("sha256") != actual["sha256"]
    ):
        raise ValueError(f"{label} changed after balanced verification")
    return actual


def _file_record(path: Path, *, include_path: bool) -> dict[str, Any]:
    resolved = _unresolved_absolute_path(path)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(resolved, flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise ValueError("artifact is not a regular owner-only file")
        size = int(metadata.st_size)
        digest = hashlib.sha256()
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        final_metadata = os.fstat(descriptor)
        current = os.stat(resolved, follow_symlinks=False)
        expected_identity = (
            int(metadata.st_dev),
            int(metadata.st_ino),
            size,
            int(metadata.st_mtime_ns),
            int(metadata.st_ctime_ns),
        )
        if any(
            (
                int(observed.st_dev),
                int(observed.st_ino),
                int(observed.st_size),
                int(observed.st_mtime_ns),
                int(observed.st_ctime_ns),
            )
            != expected_identity
            for observed in (final_metadata, current)
        ):
            raise ValueError("artifact changed while it was verified")
    finally:
        os.close(descriptor)
    record: dict[str, Any] = {
        "name": resolved.name,
        "bytes": size,
        "sha256": digest.hexdigest(),
    }
    if include_path:
        record["path"] = str(resolved)
    return record


def _valid_path_free_file_record(value: Any, name: str) -> bool:
    return bool(
        isinstance(value, Mapping)
        and set(value) == {"name", "bytes", "sha256"}
        and value.get("name") == name
        and _valid_nonnegative_int(value.get("bytes"))
        and _is_sha256(value.get("sha256"))
    )


def _read_private_binding(path: Path) -> dict[str, Any] | None:
    try:
        value = _read_json(path)
    except (OSError, ValueError):
        return None
    if (
        not isinstance(value, dict)
        or set(value)
        != {"schema", "cache_key", "pending_token", "created_ns", "balanced"}
        or value.get("schema")
        != WORKBENCH_LISTENING_MASTER_PRIVATE_BINDING_SCHEMA
        or not _is_sha256(value.get("cache_key"))
        or not _is_pending_token(value.get("pending_token"))
        or not _valid_nonnegative_int(value.get("created_ns"))
        or not isinstance(value.get("balanced"), Mapping)
    ):
        return None
    return value


def _read_json(path: Path) -> dict[str, Any]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or metadata.st_size < 2
            or metadata.st_size > _MAXIMUM_JSON_BYTES
        ):
            raise ValueError("private JSON artifact has invalid size or type")
        payload = bytearray()
        while len(payload) <= _MAXIMUM_JSON_BYTES:
            block = os.read(descriptor, min(1024 * 1024, _MAXIMUM_JSON_BYTES + 1))
            if not block:
                break
            payload.extend(block)
        if len(payload) > _MAXIMUM_JSON_BYTES:
            raise ValueError("private JSON artifact exceeds its size limit")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("private JSON artifact is invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("private JSON artifact must be an object")
    return value


def _write_private_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(value, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(payload) > _MAXIMUM_JSON_BYTES:
        raise ValueError("listening-master JSON artifact is too large")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("could not write listening-master JSON artifact")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    path.chmod(0o600)


def _ensure_owner_only_directory(path: Path) -> None:
    if os.path.lexists(path):
        metadata = os.lstat(path)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("listening-master storage is unsafe")
    else:
        path.mkdir(mode=0o700, parents=True, exist_ok=False)
    path.chmod(0o700)
    _require_owner_only_directory(path)


def _require_owner_only_directory(path: Path) -> None:
    metadata = os.lstat(path)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ValueError("listening-master storage is not owner-only")


def _require_owner_only_regular_file(path: Path) -> None:
    metadata = os.lstat(path)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ValueError("listening-master artifact is not owner-only")


def _require_entry_within_cache_bound(path: Path) -> None:
    if _directory_regular_file_bytes(path) > _MAXIMUM_CACHE_BYTES:
        raise ValueError("listening-master artifact exceeds the 2 GiB cache bound")


def _directory_regular_file_bytes(path: Path) -> int:
    total = 0
    for root, directories, files in os.walk(path, followlinks=False):
        root_path = Path(root)
        for name in directories:
            if (root_path / name).is_symlink():
                raise ValueError("listening-master cache contains a linked directory")
        for name in files:
            candidate = root_path / name
            metadata = os.lstat(candidate)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("listening-master cache contains a non-regular file")
            total += int(metadata.st_size)
    return total


def _authenticated_cache_directory(path: Path) -> bool:
    try:
        manifest = _read_json(path / _MANIFEST_NAME)
    except (OSError, ValueError):
        return False
    return _valid_manifest(manifest, cache_key=path.name)


def _remove_owned_directory(path: Path) -> None:
    if not os.path.lexists(path):
        return
    metadata = os.lstat(path)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        return
    shutil.rmtree(path)


def _fsync_tree(path: Path) -> None:
    for child in path.iterdir():
        if child.is_symlink() or not child.is_file():
            raise ValueError("listening-master pending artifact is unsafe")
        descriptor = os.open(
            child,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    _fsync_directory(path)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _path_free_document(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                return False
            lowered = key.lower()
            if lowered == "path" or lowered.endswith("_path"):
                return False
            if not _path_free_document(child):
                return False
        return True
    if isinstance(value, list):
        return all(_path_free_document(child) for child in value)
    if isinstance(value, str):
        lowered = value.lower()
        return not (
            value.startswith(("/", "~/", "../", ".\\"))
            or lowered.startswith("file://")
            or (
                len(value) >= 3
                and value[1] == ":"
                and value[2] in {"/", "\\"}
            )
        )
    return True


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


def _unresolved_absolute_path(value: str | Path) -> Path:
    expanded = Path(value).expanduser()
    return Path(os.path.abspath(os.fspath(expanded)))


def _document_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None


def _require_sha256(value: Any, *, label: str) -> None:
    if not _is_sha256(value):
        raise ValueError(f"{label} is invalid")


def _is_pending_token(value: Any) -> bool:
    return isinstance(value, str) and _TOKEN_PATTERN.fullmatch(value) is not None


def _require_pending_token(value: Any) -> None:
    if not _is_pending_token(value):
        raise ValueError("listening-master pending token is invalid")


def _valid_nonnegative_int(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and value >= 0
    )


__all__ = [
    "LISTENING_MASTER_SERVICE_EFFECTS",
    "WORKBENCH_LISTENING_MASTER_KEY_SCHEMA",
    "WORKBENCH_LISTENING_MASTER_SCHEMA",
    "WorkbenchListeningMaster",
    "WorkbenchListeningMasterService",
]
