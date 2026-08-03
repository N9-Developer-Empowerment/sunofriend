"""Parent verification for one completed native Kim worker staging tree.

The real worker writes two quarantined PCM24 stems plus a private Python import
closure claim.  This module independently reopens those artifacts, reopens the
authorised source excerpt, verifies additive reconstruction and re-hashes every
claimed Python module.  It returns only path-free evidence and grants no
selection, publication or product authority.

This is deliberately not a process coordinator.  In particular it cannot
prove that the checkpoint lease, native session or live observers remained
unchanged; the later fixed coordinator must combine those separate facts.
"""

from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping

from ._separation_checkpoint_canonical import (
    canonical_json_bytes,
    canonical_sha256,
    deep_freeze,
    plain,
)
from ._separation_melroformer_native_transport import (
    _validate_private_melroformer_native_request,
)
from ._separation_melroformer_pcm24_quarantine import (
    ATTENUATED_SCHEMA,
    _shared_level_management,
    _validate_private_melroformer_pcm24_quarantine,
    _verify_private_melroformer_pcm24_quarantine,
)
from ._separation_melroformer_real_bridge import (
    _load_private_authorised_excerpt_pcm24,
)
from ._separation_melroformer_runtime_evidence import _read_exact_regular_file
from ._separation_melroformer_supervision import (
    _validate_post_cpython_signal_state,
)
from ._separation_python_import_closure import (
    _melroformer_python_import_roots,
    _verify_python_import_closure_claim,
)


__all__: tuple[str, ...] = ()

SCHEMA = "sunofriend.private-melroformer-native-staging-verification.v1"
POLICY_ID = "private-kim-native-parent-staging-verification-v1"
_CHILD_SCHEMA = "sunofriend.private-melroformer-native-worker-child.v1"
_CHILD_STATUS = "real_worker_complete_parent_verification_required"
_CLOSURE_RELATIVE_PATH = "WORKER-EVIDENCE/python-import-closure-claim.json"
_MAXIMUM_CLOSURE_BYTES = 2 * 1024 * 1024
_SHA_RE = frozenset("0123456789abcdef")


def _verify_private_melroformer_native_worker_staging(
    *,
    request: Mapping[str, Any],
    child_result: Mapping[str, Any],
    runtime_environment_root: str | Path,
    base_runtime_root: str | Path,
) -> Mapping[str, Any]:
    """Reopen and verify every artifact created by one real native worker."""

    checked_request = _validate_private_melroformer_native_request(request)
    child = _validate_native_worker_child_result(
        child_result,
        request=checked_request,
    )
    staging = Path(checked_request["paths"]["staging_directory"])
    staging_identity = _require_private_staging_tree(staging)

    # Import lazily so importing this private verifier cannot load an audio/ML
    # runtime into a parent that only inspects contracts.
    import numpy as np

    source_before, authorisation_before = _load_private_authorised_excerpt_pcm24(
        np,
        report_path=checked_request["paths"]["authorisation_report_path"],
        expected_report_sha256=checked_request["identities"][
            "authorisation_report_sha256"
        ],
    )
    if plain(child["model"]["authorisation"]) != plain(authorisation_before):
        raise ValueError("native Kim child source authorisation differs")
    inference_geometry = child["model"]["inference"].get("geometry")
    if inference_geometry != {
        "sample_rate": authorisation_before["sample_rate"],
        "channels": authorisation_before["channels"],
        "frames": authorisation_before["frames"],
        "duration_seconds": (
            authorisation_before["frames"] / authorisation_before["sample_rate"]
        ),
        "maximum_frames": 661_500,
    }:
        raise ValueError("native Kim child inference geometry differs")

    child_quarantine = _validate_private_melroformer_pcm24_quarantine(
        child["quarantine"]
    )
    level_management = _expected_level_management(
        source_before,
        child=child,
        child_quarantine=child_quarantine,
        np=np,
    )
    claims = _quarantine_claims(child_quarantine)
    parent_quarantine = _verify_private_melroformer_pcm24_quarantine(
        destination=staging / "quarantine",
        source=source_before,
        claims=claims,
        np=np,
        level_management=level_management,
    )
    if (
        parent_quarantine["evidence_sha256"]
        != child_quarantine["evidence_sha256"]
    ):
        raise RuntimeError("native Kim child and parent quarantine evidence differ")

    closure_claim, closure_artifact = _read_closure_claim(
        staging,
        child["python_import_closure_claim"],
    )
    roots = _melroformer_python_import_roots(
        repository_root=checked_request["paths"]["repository_root"],
        source_root=checked_request["paths"]["source_root"],
        runtime_environment_root=runtime_environment_root,
        base_runtime_root=base_runtime_root,
    )
    closure_evidence = _verify_python_import_closure_claim(
        closure_claim,
        roots=roots,
    )

    # Close the time window around the other parent checks: re-open the source,
    # closure claim and quarantine once more after every claimed module file was
    # independently hashed.
    closure_claim_after, closure_artifact_after = _read_closure_claim(
        staging,
        child["python_import_closure_claim"],
    )
    if (
        closure_artifact_after != closure_artifact
        or plain(closure_claim_after) != plain(closure_claim)
    ):
        raise RuntimeError("native Kim closure claim changed during verification")
    parent_quarantine_after = _verify_private_melroformer_pcm24_quarantine(
        destination=staging / "quarantine",
        source=source_before,
        claims=claims,
        np=np,
        level_management=level_management,
    )
    if plain(parent_quarantine_after) != plain(parent_quarantine):
        raise RuntimeError("native Kim quarantine changed during verification")
    source_after, authorisation_after = _load_private_authorised_excerpt_pcm24(
        np,
        report_path=checked_request["paths"]["authorisation_report_path"],
        expected_report_sha256=checked_request["identities"][
            "authorisation_report_sha256"
        ],
    )
    if (
        plain(authorisation_after) != plain(authorisation_before)
        or source_after.shape != source_before.shape
        or source_after.dtype != source_before.dtype
        or not np.array_equal(source_after, source_before)
    ):
        raise RuntimeError("native Kim authorised source changed during verification")
    if _require_private_staging_tree(staging) != staging_identity:
        raise RuntimeError("native Kim staging identity changed during verification")

    payload = {
        "schema": SCHEMA,
        "policy_id": POLICY_ID,
        "status": "private_worker_staging_parent_verified",
        "evidence_scope": "private_local_parent_verification_only",
        "request_sha256": checked_request["request_sha256"],
        "authorised_source": {
            "report_sha256": authorisation_before["report_sha256"],
            "audio_sha256": authorisation_before["audio_sha256"],
            "frames": authorisation_before["frames"],
            "sample_rate": authorisation_before["sample_rate"],
            "channels": authorisation_before["channels"],
            "unchanged_during_parent_verification": True,
        },
        "quarantine": {
            "child_evidence_sha256": child_quarantine["evidence_sha256"],
            "parent_evidence_sha256": parent_quarantine["evidence_sha256"],
            "child_parent_evidence_identical": True,
            "unchanged_during_parent_verification": True,
        },
        "python_import_closure": {
            "claim_artifact_sha256": closure_artifact["sha256"],
            "claim_sha256": closure_claim["claim_sha256"],
            "parent_evidence_sha256": closure_evidence["evidence_sha256"],
            "module_count": closure_evidence["module_count"],
            "file_count": closure_evidence["file_count"],
            "aggregate_file_bytes": closure_evidence["aggregate_file_bytes"],
            "unchanged_during_parent_verification": True,
        },
        "boundary": {
            "staging_entry_allowlist_verified": True,
            "owner_only_directories_verified": True,
            "regular_single_link_closure_claim_verified": True,
            "private_artifacts_independently_verified": True,
            "checkpoint_lease_remeasured": False,
            "native_session_remeasured": False,
            "live_observers_verified": False,
            "paths_retained": False,
        },
        "permissions": {
            "automatic_selection_permitted": False,
            "source_graph_activation_permitted": False,
            "simple_mode_available": False,
            "studio_import_available": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "limitations": [
            "staging_verification_is_not_process_or_checkpoint_lease_evidence",
            "native_non_module_loads_are_verified_by_a_separate_observer",
            "fixed_parent_coordinator_is_still_required",
            "no_public_cli_tui_simple_studio_or_source_graph_route",
        ],
    }
    document = {
        **payload,
        "evidence_sha256": canonical_sha256(payload),
    }
    _reject_private_values(document)
    return deep_freeze(document)


def _validate_native_worker_child_result(
    value: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
) -> Mapping[str, Any]:
    child = plain(value)
    if not isinstance(child, dict) or set(child) != {
        "schema",
        "status",
        "request_validated",
        "worker",
        "companion_manifest",
        "canaries",
        "signal_state",
        "model",
        "quarantine",
        "python_import_closure_claim",
        "descriptor_contract",
        "permissions",
    }:
        raise ValueError("native Kim child result fields differ")
    worker = child["worker"]
    companion = child["companion_manifest"]
    model = child["model"]
    bridge = model.get("bridge") if isinstance(model, dict) else None
    checkpoint = bridge.get("checkpoint") if isinstance(bridge, dict) else None
    source = bridge.get("source") if isinstance(bridge, dict) else None
    if (
        child["schema"] != _CHILD_SCHEMA
        or child["status"] != _CHILD_STATUS
        or child["request_validated"] is not True
        or not isinstance(worker, dict)
        or set(worker) != {"bytes", "sha256"}
        or type(worker["bytes"]) is not int
        or not 1 <= worker["bytes"] <= 1024 * 1024
        or worker["sha256"] != request["identities"]["worker_source_sha256"]
        or not isinstance(companion, dict)
        or set(companion) != {"files", "manifest_sha256"}
        or companion.get("manifest_sha256")
        != request["identities"]["companion_manifest_sha256"]
        or not isinstance(model, dict)
        or set(model) != {"authorisation", "bridge", "inference"}
        or not isinstance(bridge, dict)
        or bridge.get("candidate_id") != request["candidate_id"]
        or not isinstance(checkpoint, dict)
        or checkpoint.get("bytes") != request["identities"]["checkpoint_bytes"]
        or checkpoint.get("sha256")
        != request["identities"]["checkpoint_sha256"]
        or checkpoint.get("descriptor_pinned_during_tensor_load") is not True
        or checkpoint.get("transport") != "inherited_read_only_descriptor"
        or checkpoint.get("path_reopened_by_loader") is not False
        or checkpoint.get("descriptor_number_retained") is not False
        or not isinstance(source, dict)
        or source.get("manifest_sha256")
        != request["identities"]["source_manifest_sha256"]
        or source.get("verified") is not True
    ):
        raise ValueError("native Kim child result identity differs")
    if child["canaries"] != {
        "network_connect_errno": errno.EPERM,
        "network_errno_name": errno.errorcode[errno.EPERM],
        "process_fork_errno": errno.EPERM,
        "process_fork_errno_name": errno.errorcode[errno.EPERM],
        "outside_write_errno": errno.EPERM,
        "outside_write_errno_name": errno.errorcode[errno.EPERM],
        "fixed_sandbox_environment_observed": True,
    }:
        raise ValueError("native Kim child sandbox canaries differ")
    _validate_post_cpython_signal_state(child["signal_state"])
    if child["descriptor_contract"] != {
        "request_frame_read_from_fd3": True,
        "result_frame_written_to_fd4": True,
        "checkpoint_loaded_from_fd5": True,
        "ready_release_completed_on_fd6_fd7": True,
        "checkpoint_path_reopened": False,
        "logical_descriptors_retained": False,
    }:
        raise ValueError("native Kim child descriptor contract differs")
    if child["permissions"] != {
        "publication_permitted": False,
        "automatic_selection_permitted": False,
        "product_route_permitted": False,
    }:
        raise ValueError("native Kim child grants a permission")
    return deep_freeze(child)


def _expected_level_management(
    source: Any,
    *,
    child: Mapping[str, Any],
    child_quarantine: Mapping[str, Any],
    np: Any,
) -> Mapping[str, Any] | None:
    if child_quarantine["schema"] != ATTENUATED_SCHEMA:
        return None
    outputs = child["model"]["inference"].get("outputs")
    if not isinstance(outputs, Mapping):
        raise ValueError("native Kim inference output peaks are absent")
    peaks = [float(np.max(np.abs(source)))]
    for role in ("vocals", "instrumental"):
        item = outputs.get(role)
        peak = item.get("peak") if isinstance(item, Mapping) else None
        if (
            isinstance(peak, bool)
            or not isinstance(peak, (int, float))
            or not 0.0 <= float(peak) <= 4.0
        ):
            raise ValueError("native Kim inference output peak differs")
        peaks.append(float(peak))
    expected = _shared_level_management(max(peaks))
    if plain(child_quarantine["level_management"]) != plain(expected):
        raise ValueError("native Kim shared-headroom evidence differs")
    return expected


def _quarantine_claims(value: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    return {
        item["role"]: {
            key: item[key]
            for key in ("role", "relative_path", "bytes", "sha256", "geometry")
        }
        for item in value["outputs"]
    }


def _read_closure_claim(
    staging: Path,
    artifact_value: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    artifact = plain(artifact_value)
    if not isinstance(artifact, dict) or set(artifact) != {
        "relative_path",
        "bytes",
        "sha256",
        "contains_private_paths",
        "parent_verification_required",
    }:
        raise ValueError("native Kim closure artifact fields differ")
    if (
        artifact["relative_path"] != _CLOSURE_RELATIVE_PATH
        or type(artifact["bytes"]) is not int
        or not 1 <= artifact["bytes"] <= _MAXIMUM_CLOSURE_BYTES
        or not _is_sha(artifact["sha256"])
        or artifact["contains_private_paths"] is not True
        or artifact["parent_verification_required"] is not True
    ):
        raise ValueError("native Kim closure artifact identity differs")
    path = staging / _CLOSURE_RELATIVE_PATH
    attached = path.lstat()
    if (
        stat.S_ISLNK(attached.st_mode)
        or not stat.S_ISREG(attached.st_mode)
        or attached.st_nlink != 1
        or attached.st_uid != os.geteuid()
        or stat.S_IMODE(attached.st_mode) != 0o600
    ):
        raise ValueError("native Kim closure claim file is unsafe")
    raw = _read_exact_regular_file(
        path,
        expected_sha256=artifact["sha256"],
        expected_bytes=artifact["bytes"],
    )
    try:
        claim = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("native Kim closure claim JSON is invalid") from error
    if type(claim) is not dict or canonical_json_bytes(claim) != raw:
        raise ValueError("native Kim closure claim JSON is not canonical")
    return deep_freeze(claim), deep_freeze(artifact)


def _require_private_staging_tree(staging: Path) -> Mapping[str, Any]:
    attached = staging.lstat()
    resolved = staging.resolve(strict=True)
    if (
        stat.S_ISLNK(attached.st_mode)
        or not stat.S_ISDIR(attached.st_mode)
        or resolved != staging
        or attached.st_uid != os.geteuid()
        or stat.S_IMODE(attached.st_mode) != 0o700
        or sorted(os.listdir(staging)) != ["WORKER-EVIDENCE", "quarantine"]
    ):
        raise ValueError("native Kim staging tree differs")
    identities = {"staging": _directory_identity(attached)}
    for relative in ("WORKER-EVIDENCE", "quarantine"):
        path = staging / relative
        state = path.lstat()
        if (
            stat.S_ISLNK(state.st_mode)
            or not stat.S_ISDIR(state.st_mode)
            or state.st_uid != os.geteuid()
            or stat.S_IMODE(state.st_mode) != 0o700
        ):
            raise ValueError("native Kim staging directory is unsafe")
        identities[relative] = _directory_identity(state)
    return deep_freeze(identities)


def _directory_identity(value: os.stat_result) -> Mapping[str, int]:
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "uid": value.st_uid,
        "mode": stat.S_IMODE(value.st_mode),
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _is_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _SHA_RE for character in value)
    )


def _reject_private_values(value: Mapping[str, Any]) -> None:
    encoded = canonical_json_bytes(value)
    if b'"pid"' in encoded or b'"pgid"' in encoded or b'"paths"' in encoded:
        raise RuntimeError("native Kim staging evidence retained a private field")
    if b"://" in encoded or b'"/' in encoded:
        raise RuntimeError("native Kim staging evidence retained a path or URL")
