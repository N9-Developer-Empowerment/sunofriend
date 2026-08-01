"""Private parent boundary for one authorised MelRoFormer worker run.

This is a development-only action. The parent binds explicit local artifacts,
launches the fixed worker under a macOS sandbox, and independently reopens the
two PCM24 outputs. It grants no product, selection or publication authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from ._separation_macos_sandbox_probe import (
    SANDBOX_EXEC_PATH,
    _regular_file_identity,
)
from ._separation_macos_sandbox_network_observer import (
    _run_with_macos_sandbox_network_observer,
    _validate_macos_sandbox_network_observation,
)
from ._separation_melroformer_artifacts import (
    _inspect_companion_files,
    _inspect_local_checkpoint,
)
from ._separation_melroformer_pcm24_quarantine import (
    _validate_private_melroformer_pcm24_quarantine,
    _verify_private_melroformer_pcm24_quarantine,
)
from ._separation_melroformer_real_bridge import (
    _load_private_authorised_excerpt_pcm24,
)
from ._separation_melroformer_runtime_evidence import (
    SOURCE_MANIFEST_SHA256,
    SOURCE_REVISION,
    _verify_private_melroformer_source_tree,
)
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from ._separation_melroformer_worker_sandbox import (
    WORKER_RELATIVE_PATH,
    _path_free_identity,
    _regular_non_symlink_file_identity,
    _sandbox_profile,
    _validate_child_canaries,
)
from ._separation_python_import_closure import (
    _melroformer_python_import_roots,
    _validate_verified_python_import_closure,
    _verify_python_import_closure_claim,
)
from .separation_contract import _canonical_json_bytes, _freeze_json


SCHEMA = "sunofriend.private-melroformer-authorised-worker-sandbox.v1"
POLICY_ID = "private-melroformer-authorised-worker-sandbox-v1"
CHILD_SCHEMA = "sunofriend.private-melroformer-authorised-worker-child.v1"
IMPORT_CLOSURE_SCHEMA = (
    "sunofriend.private-melroformer-authorised-worker-sandbox.v2"
)
IMPORT_CLOSURE_POLICY_ID = (
    "private-melroformer-authorised-worker-sandbox-import-closure-v2"
)
IMPORT_CLOSURE_CHILD_SCHEMA = (
    "sunofriend.private-melroformer-authorised-worker-import-closure-child.v1"
)
NETWORK_OBSERVATION_SCHEMA = (
    "sunofriend.private-melroformer-authorised-worker-sandbox.v3"
)
NETWORK_OBSERVATION_POLICY_ID = (
    "private-melroformer-authorised-worker-network-observation-v3"
)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_MAXIMUM_STDOUT_BYTES = 2 * 1024 * 1024


def _run_private_melroformer_authorised_worker(
    *,
    repository_root: str | Path,
    runtime_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
    authorisation_report_path: str | Path,
    expected_authorisation_report_sha256: str,
    staging_directory: str | Path,
    device: str = "gpu",
    bind_python_import_closure: bool = False,
    observe_outbound_attempts: bool = False,
) -> Mapping[str, Any]:
    """Run and parent-verify one exact, bounded authorised worker on Darwin."""

    if platform.system() != "Darwin":
        raise RuntimeError("MelRoFormer authorised worker sandbox requires Darwin")
    if device not in {"gpu", "cpu"}:
        raise ValueError("MelRoFormer authorised worker device must be gpu or cpu")
    if not _is_sha(expected_authorisation_report_sha256):
        raise ValueError("MelRoFormer authorisation report hash is invalid")
    if observe_outbound_attempts and not bind_python_import_closure:
        raise ValueError(
            "MelRoFormer network observation requires the Python import closure"
        )

    repository = Path(repository_root).expanduser().resolve(strict=True)
    if not repository.is_dir() or repository.is_symlink():
        raise ValueError("MelRoFormer worker repository root must be a directory")
    worker_path = repository / WORKER_RELATIVE_PATH
    runtime_launch_path = Path(runtime_path).expanduser().absolute()
    source = Path(source_root).expanduser().absolute()
    checkpoint = Path(checkpoint_path).expanduser().absolute()
    companions = Path(companion_root).expanduser().absolute()
    report = Path(authorisation_report_path).expanduser().absolute()

    artifacts_before = _observe_artifacts(
        worker_path=worker_path,
        runtime_path=runtime_launch_path,
        source_root=source,
        checkpoint_path=checkpoint,
        companion_root=companions,
    )
    np = __import__("numpy")
    source_audio, authorisation_before = _load_private_authorised_excerpt_pcm24(
        np,
        report_path=report,
        expected_report_sha256=expected_authorisation_report_sha256,
    )

    staging = Path(staging_directory).expanduser().absolute()
    staging.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(staging, 0o700)
    output = staging / "output"
    outside = staging.parent / f".{staging.name}-outside-write-canary"
    if outside.exists() or outside.is_symlink():
        raise ValueError("MelRoFormer outside-write canary path already exists")
    profile = _sandbox_profile(staging)
    environment = {
        "HF_HUB_OFFLINE": "1",
        "HOME": "/var/empty",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(repository / "src"),
        "TMPDIR": "/var/empty",
        "TRANSFORMERS_OFFLINE": "1",
    }
    command = [
            artifacts_before["provider"]["resolved_path"],
            "-p",
            profile,
            str(runtime_launch_path),
            "-B",
            str(worker_path),
            "--authorised-excerpt",
            str(report),
            "--authorisation-report-sha256",
            expected_authorisation_report_sha256,
            "--source-root",
            str(source),
            "--checkpoint",
            str(checkpoint),
            "--companion-root",
            str(companions),
            "--device",
            device,
            "--destination",
            str(output),
            "--outside-write-canary",
            str(outside),
        ]
    if bind_python_import_closure:
        command.extend(
            [
                "--bind-python-import-closure",
                "--repository-root",
                str(repository),
            ]
        )
    network_observation = None
    if observe_outbound_attempts:
        completed, network_observation = (
            _run_with_macos_sandbox_network_observer(
                command=command,
                cwd=repository,
                environment=environment,
                timeout_seconds=120.0,
                expected_canary_port=9,
            )
        )
    else:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            cwd=repository,
            env=environment,
            timeout=120.0,
        )
    stdout_bytes = completed.stdout.encode("utf-8")
    stderr_bytes = completed.stderr.encode("utf-8")
    if (
        completed.returncode != 0
        or stderr_bytes
        or not 1 <= len(stdout_bytes) <= _MAXIMUM_STDOUT_BYTES
    ):
        raise RuntimeError(
            "MelRoFormer authorised worker did not complete cleanly: "
            f"exit={completed.returncode}; stderr_bytes={len(stderr_bytes)}; "
            f"stderr_sha256={hashlib.sha256(stderr_bytes).hexdigest()}"
        )
    try:
        child = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("MelRoFormer authorised worker returned invalid JSON") from error
    _validate_authorised_child(
        child, require_import_closure=bind_python_import_closure
    )
    import_closure = None
    if bind_python_import_closure:
        roots = _melroformer_python_import_roots(
            repository_root=repository,
            source_root=source,
            runtime_environment_root=runtime_launch_path.parent.parent,
            base_runtime_root=Path(
                artifacts_before["runtime"]["resolved_path"]
            ).parent.parent,
        )
        import_closure = _verify_python_import_closure_claim(
            child["import_closure"], roots=roots
        )
    child_quarantine = _validate_private_melroformer_pcm24_quarantine(
        child["quarantine"]
    )
    if outside.exists() or outside.is_symlink():
        raise RuntimeError("MelRoFormer outside-write canary unexpectedly persisted")
    if sorted(item.name for item in staging.iterdir()) != ["output"]:
        raise RuntimeError("MelRoFormer staging tree contains an unexpected entry")

    claims = {
        item["role"]: {
            key: item[key]
            for key in ("role", "relative_path", "bytes", "sha256", "geometry")
        }
        for item in child_quarantine["outputs"]
    }
    parent_quarantine = _verify_private_melroformer_pcm24_quarantine(
        destination=output,
        source=source_audio,
        claims=claims,
        np=np,
    )
    if parent_quarantine["evidence_sha256"] != child_quarantine["evidence_sha256"]:
        raise RuntimeError("MelRoFormer child and parent quarantine evidence differ")

    artifacts_after = _observe_artifacts(
        worker_path=worker_path,
        runtime_path=runtime_launch_path,
        source_root=source,
        checkpoint_path=checkpoint,
        companion_root=companions,
    )
    _, authorisation_after = _load_private_authorised_excerpt_pcm24(
        np,
        report_path=report,
        expected_report_sha256=expected_authorisation_report_sha256,
    )
    if not _artifacts_equal(artifacts_before, artifacts_after):
        raise RuntimeError("MelRoFormer worker input artifact changed during inference")
    if dict(authorisation_before) != dict(authorisation_after):
        raise RuntimeError("MelRoFormer authorised input changed during inference")
    if dict(child["model"]["authorisation"]) != dict(authorisation_before):
        raise RuntimeError("MelRoFormer child authorisation evidence differs")

    bridge = child["model"]["bridge"]
    inference = child["model"]["inference"]
    payload = {
        "schema": (
            NETWORK_OBSERVATION_SCHEMA
            if network_observation
            else IMPORT_CLOSURE_SCHEMA
            if import_closure
            else SCHEMA
        ),
        "policy_id": (
            NETWORK_OBSERVATION_POLICY_ID
            if network_observation
            else IMPORT_CLOSURE_POLICY_ID
            if import_closure
            else POLICY_ID
        ),
        "status": "authorised_model_worker_complete_parent_verified",
        "artifacts": {
            "provider": _path_free_identity(artifacts_before["provider"]),
            "runtime": _path_free_identity(artifacts_before["runtime"]),
            "worker": _path_free_identity(artifacts_before["worker"]),
            "checkpoint": _path_free_identity(artifacts_before["checkpoint"]),
            "source_revision": SOURCE_REVISION,
            "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
            "companions": artifacts_before["companions"],
            "authorisation_report_sha256": expected_authorisation_report_sha256,
            "authorised_audio_sha256": authorisation_before["audio_sha256"],
            "unchanged_after_worker": True,
            "hash_before_exec_path_toctou_closed": False,
            "complete_python_import_closure_bound": import_closure is not None,
        },
        "isolation": {
            "profile_sha256": hashlib.sha256(profile.encode("utf-8")).hexdigest(),
            "environment_sha256": hashlib.sha256(
                _canonical_json_bytes(environment)
            ).hexdigest(),
            "network_denial": "enforced_canary_observed",
            "child_process_denial": "enforced_canary_observed",
            "outside_write_denial": "enforced_canary_observed",
            "arbitrary_attempt_stream_observed": network_observation is not None,
            "allowed_write_scope": "fresh_private_staging_tree_only",
        },
        "canaries": child["canaries"],
        **({"import_closure": import_closure} if import_closure else {}),
        **(
            {"network_observation": network_observation}
            if network_observation
            else {}
        ),
        "authorisation": dict(authorisation_before),
        "model": {
            "candidate_id": bridge["candidate_id"],
            "device": bridge["runtime"]["mlx_device"],
            "checkpoint_sha256": bridge["checkpoint"]["sha256"],
            "checkpoint_tensor_count": bridge["checkpoint"][
                "static_tensor_count"
            ],
            "model_keys_complete": bridge["weight_coverage"]["complete"],
            "upstream_downloader_called": bridge["source"][
                "upstream_from_pretrained_called"
            ],
        },
        "inference": {
            "status": inference["status"],
            "frames": inference["geometry"]["frames"],
            "chunk_count": inference["transport"]["chunk_count"],
            "inference_seconds": inference["measurement"]["inference_seconds"],
            "peak_memory_bytes": inference["measurement"]["peak_memory_bytes"],
            "vocal_float32_sha256": inference["outputs"]["vocals"]["sha256"],
            "instrumental_float32_sha256": inference["outputs"]["instrumental"][
                "sha256"
            ],
            "maximum_absolute_reconstruction_error": inference[
                "additive_accounting"
            ]["maximum_absolute_error"],
        },
        "quarantine": {
            "child_evidence_sha256": child_quarantine["evidence_sha256"],
            "parent_evidence_sha256": parent_quarantine["evidence_sha256"],
            "evidence_identical": True,
            "outputs": [
                {
                    "role": item["role"],
                    "bytes": item["bytes"],
                    "sha256": item["sha256"],
                }
                for item in parent_quarantine["outputs"]
            ],
            "maximum_integer_reconstruction_error_lsb": parent_quarantine[
                "additive_reconstruction"
            ]["maximum_integer_error_lsb"],
        },
        "conclusion": {
            "network_denial_bound_to_model_worker": True,
            "child_process_denial_bound_to_model_worker": True,
            "outside_write_denial_bound_to_model_worker": True,
            "pcm24_quarantine_bound_to_model_worker": True,
            "authorised_excerpt_bound_to_model_worker": True,
            **(
                {
                    "kernel_sandbox_network_denial_stream_bound_to_model_worker": True
                }
                if network_observation
                else {}
            ),
            "worker_authorized_for_product": False,
        },
        "permissions": {
            "automatic_selection_permitted": False,
            "source_graph_activation_permitted": False,
            "simple_mode_available": False,
            "studio_import_available": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "effects": {
            "process_started": True,
            "filesystem_written": True,
            "audio_outputs_persisted": True,
            "network_used": False,
            "checkpoint_opened": True,
            "tensor_deserialized": True,
            "model_imported": True,
            "audio_inference_called": True,
            "authorised_audio_read": True,
            "source_graph_changed": False,
        },
        "limitations": {
            "private_development_observation_only": True,
            "arbitrary_model_attempt_stream_observed": network_observation is not None,
            "hash_before_exec_path_toctou_closed": False,
            "complete_python_import_closure_bound": import_closure is not None,
            "ordinary_outputs_can_change_after_parent_verification": True,
            "conversion_parity_independently_verified": False,
            "human_listening_completed": False,
            "downstream_vocal_midi_evaluated": False,
        },
    }
    document = {
        **payload,
        "evidence_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    return _validate_private_melroformer_authorised_worker(document)


def _observe_artifacts(
    *,
    worker_path: Path,
    runtime_path: Path,
    source_root: Path,
    checkpoint_path: Path,
    companion_root: Path,
) -> dict[str, Any]:
    checkpoint = _inspect_local_checkpoint(checkpoint_path)
    if not checkpoint["cryptographic_identity_verified"]:
        raise ValueError("MelRoFormer checkpoint identity differs")
    source = _verify_private_melroformer_source_tree(source_root)
    if source["status"] != "verified_not_imported":
        raise ValueError("MelRoFormer source identity differs")
    companions = _inspect_companion_files(companion_root)
    if not companions["all_cryptographic_identities_verified"]:
        raise ValueError("MelRoFormer companion identities differ")
    return {
        "provider": _regular_file_identity(SANDBOX_EXEC_PATH),
        "runtime": _regular_file_identity(runtime_path),
        "worker": _regular_non_symlink_file_identity(worker_path),
        "checkpoint": {
            "resolved_path": checkpoint["path"],
            "bytes": checkpoint["bytes"],
            "sha256": checkpoint["sha256"],
        },
        "source": source,
        "companions": {
            name: {
                "bytes": item["bytes"],
                "sha256": item["sha256"],
            }
            for name, item in sorted(companions["files"].items())
        },
    }


def _artifacts_equal(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    for name in ("provider", "runtime", "worker", "checkpoint"):
        if any(before[name][key] != after[name][key] for key in ("bytes", "sha256")):
            return False
    return (
        before["source"] == after["source"]
        and before["companions"] == after["companions"]
    )


def _validate_authorised_child(
    value: Any, *, require_import_closure: bool = False
) -> None:
    expected_fields = {"schema", "status", "canaries", "model", "quarantine"}
    expected_schema = CHILD_SCHEMA
    if require_import_closure:
        expected_fields.add("import_closure")
        expected_schema = IMPORT_CLOSURE_CHILD_SCHEMA
    if (
        not isinstance(value, dict)
        or set(value) != expected_fields
        or value.get("schema") != expected_schema
        or value.get("status") != "complete"
        or not isinstance(value.get("model"), dict)
        or set(value["model"]) != {"authorisation", "bridge", "inference"}
    ):
        raise ValueError("MelRoFormer authorised worker child envelope differs")
    _validate_child_canaries(value["canaries"])
    bridge = value["model"]["bridge"]
    inference = value["model"]["inference"]
    if (
        bridge.get("candidate_id") != "mlx-melroformer-kim-vocal-2"
        or bridge.get("checkpoint", {}).get("sha256")
        != CONVERSION_CHECKPOINT_SHA256
        or bridge.get("checkpoint", {}).get("bytes")
        != CONVERSION_CHECKPOINT_BYTES
        or bridge.get("source", {}).get("manifest_sha256")
        != SOURCE_MANIFEST_SHA256
        or bridge.get("source", {}).get("upstream_from_pretrained_called") is not False
        or inference.get("status")
        not in {
            "private_real_single_chunk_validated_not_persisted",
            "private_real_overlapped_excerpt_validated_not_persisted",
        }
        or inference.get("additive_accounting", {}).get("passed") is not True
    ):
        raise ValueError("MelRoFormer authorised worker model evidence differs")


def _validate_private_melroformer_authorised_worker(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate a historical v1, import-bound v2 or network-observed v3 record."""

    schema = document.get("schema") if isinstance(document, Mapping) else None
    if schema == SCHEMA:
        return _validate_private_melroformer_authorised_worker_v1(document)
    if schema == IMPORT_CLOSURE_SCHEMA:
        return _validate_private_melroformer_authorised_worker_v2(document)
    if schema == NETWORK_OBSERVATION_SCHEMA:
        return _validate_private_melroformer_authorised_worker_v3(document)
    raise ValueError("MelRoFormer authorised worker evidence identity differs")


def _validate_private_melroformer_authorised_worker_v3(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _plain(document)
    digest = value.pop("evidence_sha256", None) if isinstance(value, dict) else None
    if not _is_sha(digest) or digest != hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest():
        raise ValueError("MelRoFormer authorised worker evidence self-hash differs")
    if (
        value.get("schema") != NETWORK_OBSERVATION_SCHEMA
        or value.get("policy_id") != NETWORK_OBSERVATION_POLICY_ID
        or value.get("status")
        != "authorised_model_worker_complete_parent_verified"
        or set(value)
        != {
            "schema",
            "policy_id",
            "status",
            "artifacts",
            "isolation",
            "canaries",
            "import_closure",
            "network_observation",
            "authorisation",
            "model",
            "inference",
            "quarantine",
            "conclusion",
            "permissions",
            "effects",
            "limitations",
        }
    ):
        raise ValueError("MelRoFormer authorised worker network fields differ")
    _validate_macos_sandbox_network_observation(value["network_observation"])
    if (
        value["isolation"].get("arbitrary_attempt_stream_observed") is not True
        or value["limitations"].get("arbitrary_model_attempt_stream_observed")
        is not True
        or value["conclusion"].get(
            "kernel_sandbox_network_denial_stream_bound_to_model_worker"
        )
        is not True
        or value["network_observation"]["observation"].get(
            "target_pid_bound"
        )
        is not True
        or value["network_observation"]["observation"].get(
            "deliberate_canary_denial_count"
        )
        < 1
        or value["network_observation"]["limitations"].get(
            "executable_path_toctou_closed"
        )
        is not False
    ):
        raise ValueError("MelRoFormer authorised worker network claim differs")

    import_bound = _plain(value)
    import_bound.pop("network_observation")
    import_bound["schema"] = IMPORT_CLOSURE_SCHEMA
    import_bound["policy_id"] = IMPORT_CLOSURE_POLICY_ID
    import_bound["isolation"]["arbitrary_attempt_stream_observed"] = False
    import_bound["limitations"]["arbitrary_model_attempt_stream_observed"] = False
    import_bound["conclusion"].pop(
        "kernel_sandbox_network_denial_stream_bound_to_model_worker"
    )
    import_bound["evidence_sha256"] = hashlib.sha256(
        _canonical_json_bytes(import_bound)
    ).hexdigest()
    _validate_private_melroformer_authorised_worker_v2(import_bound)
    checked = {**value, "evidence_sha256": digest}
    encoded = json.dumps(checked, sort_keys=True, separators=(",", ":"))
    if "/Users/" in encoded or "file://" in encoded or "://" in encoded:
        raise ValueError("MelRoFormer authorised worker evidence is not path-free")
    return _freeze_json(checked)


def _validate_private_melroformer_authorised_worker_v2(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _plain(document)
    digest = value.pop("evidence_sha256", None) if isinstance(value, dict) else None
    if not _is_sha(digest) or digest != hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest():
        raise ValueError("MelRoFormer authorised worker evidence self-hash differs")
    if (
        value.get("schema") != IMPORT_CLOSURE_SCHEMA
        or value.get("policy_id") != IMPORT_CLOSURE_POLICY_ID
        or value.get("status")
        != "authorised_model_worker_complete_parent_verified"
        or set(value)
        != {
            "schema",
            "policy_id",
            "status",
            "artifacts",
            "isolation",
            "canaries",
            "import_closure",
            "authorisation",
            "model",
            "inference",
            "quarantine",
            "conclusion",
            "permissions",
            "effects",
            "limitations",
        }
    ):
        raise ValueError("MelRoFormer authorised worker import-closure fields differ")
    _validate_verified_python_import_closure(value["import_closure"])
    if (
        value["artifacts"].get("complete_python_import_closure_bound") is not True
        or value["limitations"].get("complete_python_import_closure_bound")
        is not True
        or value["artifacts"].get("hash_before_exec_path_toctou_closed") is not False
        or value["limitations"].get("hash_before_exec_path_toctou_closed") is not False
    ):
        raise ValueError("MelRoFormer authorised worker import-closure claim differs")

    legacy = _plain(value)
    legacy.pop("import_closure")
    legacy["schema"] = SCHEMA
    legacy["policy_id"] = POLICY_ID
    legacy["artifacts"]["complete_python_import_closure_bound"] = False
    legacy["limitations"]["complete_python_import_closure_bound"] = False
    legacy["evidence_sha256"] = hashlib.sha256(
        _canonical_json_bytes(legacy)
    ).hexdigest()
    _validate_private_melroformer_authorised_worker_v1(legacy)
    checked = {**value, "evidence_sha256": digest}
    encoded = json.dumps(checked, sort_keys=True, separators=(",", ":"))
    if "/Users/" in encoded or "file://" in encoded or "://" in encoded:
        raise ValueError("MelRoFormer authorised worker evidence is not path-free")
    return _freeze_json(checked)


def _validate_private_melroformer_authorised_worker_v1(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _plain(document)
    digest = value.pop("evidence_sha256", None) if isinstance(value, dict) else None
    if not _is_sha(digest) or digest != hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest():
        raise ValueError("MelRoFormer authorised worker evidence self-hash differs")
    if (
        value.get("schema") != SCHEMA
        or value.get("policy_id") != POLICY_ID
        or value.get("status")
        != "authorised_model_worker_complete_parent_verified"
    ):
        raise ValueError("MelRoFormer authorised worker evidence identity differs")
    required = {
        "schema",
        "policy_id",
        "status",
        "artifacts",
        "isolation",
        "canaries",
        "authorisation",
        "model",
        "inference",
        "quarantine",
        "conclusion",
        "permissions",
        "effects",
        "limitations",
    }
    if set(value) != required:
        raise ValueError("MelRoFormer authorised worker evidence fields differ")
    _validate_child_canaries(value["canaries"])
    artifacts = value["artifacts"]
    if set(artifacts) != {
        "provider",
        "runtime",
        "worker",
        "checkpoint",
        "source_revision",
        "source_manifest_sha256",
        "companions",
        "authorisation_report_sha256",
        "authorised_audio_sha256",
        "unchanged_after_worker",
        "hash_before_exec_path_toctou_closed",
        "complete_python_import_closure_bound",
    }:
        raise ValueError("MelRoFormer authorised worker artifact fields differ")
    for name in ("provider", "runtime", "worker", "checkpoint"):
        identity = artifacts[name]
        if (
            set(identity) != {"bytes", "sha256"}
            or type(identity["bytes"]) is not int
            or identity["bytes"] <= 0
            or not _is_sha(identity["sha256"])
        ):
            raise ValueError("MelRoFormer authorised worker artifact identity differs")
    companions = artifacts["companions"]
    if set(companions) != {"LICENSE", "config.json"} or any(
        set(item) != {"bytes", "sha256"}
        or type(item["bytes"]) is not int
        or item["bytes"] <= 0
        or not _is_sha(item["sha256"])
        for item in companions.values()
    ):
        raise ValueError("MelRoFormer authorised worker companion evidence differs")
    if (
        artifacts["checkpoint"]["bytes"] != CONVERSION_CHECKPOINT_BYTES
        or artifacts["checkpoint"]["sha256"] != CONVERSION_CHECKPOINT_SHA256
        or artifacts["source_revision"] != SOURCE_REVISION
        or artifacts["source_manifest_sha256"] != SOURCE_MANIFEST_SHA256
        or not _is_sha(artifacts["authorisation_report_sha256"])
        or not _is_sha(artifacts["authorised_audio_sha256"])
        or artifacts["unchanged_after_worker"] is not True
        or artifacts["hash_before_exec_path_toctou_closed"] is not False
        or artifacts["complete_python_import_closure_bound"] is not False
    ):
        raise ValueError("MelRoFormer authorised worker artifact evidence differs")
    isolation = value["isolation"]
    if isolation != {
        "profile_sha256": isolation.get("profile_sha256"),
        "environment_sha256": isolation.get("environment_sha256"),
        "network_denial": "enforced_canary_observed",
        "child_process_denial": "enforced_canary_observed",
        "outside_write_denial": "enforced_canary_observed",
        "arbitrary_attempt_stream_observed": False,
        "allowed_write_scope": "fresh_private_staging_tree_only",
    } or not _is_sha(isolation.get("profile_sha256")) or not _is_sha(
        isolation.get("environment_sha256")
    ):
        raise ValueError("MelRoFormer authorised worker isolation evidence differs")
    authorisation = value["authorisation"]
    if (
        authorisation.get("schema")
        != "sunofriend.private-melroformer-authorised-input.v1"
        or authorisation.get("report_sha256")
        != artifacts["authorisation_report_sha256"]
        or authorisation.get("audio_sha256") != artifacts["authorised_audio_sha256"]
        or authorisation.get("rights_authority")
        != "creator_and_copyright_holder"
        or authorisation.get("evidence_scope") != "private_development_only"
        or authorisation.get("sample_rate") != 44_100
        or authorisation.get("channels") != 2
        or type(authorisation.get("frames")) is not int
        or not 4_096 <= authorisation["frames"] <= 661_500
        or authorisation.get("audio_persisted_by_bridge") is not False
    ):
        raise ValueError("MelRoFormer authorised worker authorisation differs")
    model = value["model"]
    if (
        set(model)
        != {
            "candidate_id",
            "device",
            "checkpoint_sha256",
            "checkpoint_tensor_count",
            "model_keys_complete",
            "upstream_downloader_called",
        }
        or model["candidate_id"] != "mlx-melroformer-kim-vocal-2"
        or model["device"] not in {"gpu", "cpu"}
        or model["checkpoint_sha256"] != CONVERSION_CHECKPOINT_SHA256
        or model["checkpoint_tensor_count"] != 708
        or model["model_keys_complete"] is not True
        or model["upstream_downloader_called"] is not False
    ):
        raise ValueError("MelRoFormer authorised worker model evidence differs")
    inference = value["inference"]
    if (
        set(inference)
        != {
            "status",
            "frames",
            "chunk_count",
            "inference_seconds",
            "peak_memory_bytes",
            "vocal_float32_sha256",
            "instrumental_float32_sha256",
            "maximum_absolute_reconstruction_error",
        }
        or inference["status"]
        not in {
            "private_real_single_chunk_validated_not_persisted",
            "private_real_overlapped_excerpt_validated_not_persisted",
        }
        or inference["frames"] != authorisation["frames"]
        or type(inference["chunk_count"]) is not int
        or not 1 <= inference["chunk_count"] <= 3
        or isinstance(inference["inference_seconds"], bool)
        or not isinstance(inference["inference_seconds"], (int, float))
        or not 0 < inference["inference_seconds"] <= 3_600
        or type(inference["peak_memory_bytes"]) is not int
        or not 1 <= inference["peak_memory_bytes"] <= 64 * 1024**3
        or not _is_sha(inference["vocal_float32_sha256"])
        or not _is_sha(inference["instrumental_float32_sha256"])
        or isinstance(inference["maximum_absolute_reconstruction_error"], bool)
        or not isinstance(
            inference["maximum_absolute_reconstruction_error"], (int, float)
        )
        or not 0 <= inference["maximum_absolute_reconstruction_error"] <= 1e-6
    ):
        raise ValueError("MelRoFormer authorised worker inference evidence differs")
    if value["conclusion"] != {
        "network_denial_bound_to_model_worker": True,
        "child_process_denial_bound_to_model_worker": True,
        "outside_write_denial_bound_to_model_worker": True,
        "pcm24_quarantine_bound_to_model_worker": True,
        "authorised_excerpt_bound_to_model_worker": True,
        "worker_authorized_for_product": False,
    }:
        raise ValueError("MelRoFormer authorised worker conclusion differs")
    if value["permissions"] != {
        "automatic_selection_permitted": False,
        "source_graph_activation_permitted": False,
        "simple_mode_available": False,
        "studio_import_available": False,
        "product_route_permitted": False,
        "publication_permitted": False,
    }:
        raise ValueError("MelRoFormer authorised worker grants a product permission")
    if value["effects"] != {
        "process_started": True,
        "filesystem_written": True,
        "audio_outputs_persisted": True,
        "network_used": False,
        "checkpoint_opened": True,
        "tensor_deserialized": True,
        "model_imported": True,
        "audio_inference_called": True,
        "authorised_audio_read": True,
        "source_graph_changed": False,
    }:
        raise ValueError("MelRoFormer authorised worker effects differ")
    if value["limitations"] != {
        "private_development_observation_only": True,
        "arbitrary_model_attempt_stream_observed": False,
        "hash_before_exec_path_toctou_closed": False,
        "complete_python_import_closure_bound": False,
        "ordinary_outputs_can_change_after_parent_verification": True,
        "conversion_parity_independently_verified": False,
        "human_listening_completed": False,
        "downstream_vocal_midi_evaluated": False,
    }:
        raise ValueError("MelRoFormer authorised worker limitations differ")
    quarantine = value["quarantine"]
    if (
        quarantine.get("child_evidence_sha256")
        != quarantine.get("parent_evidence_sha256")
        or quarantine.get("evidence_identical") is not True
        or not _is_sha(quarantine.get("child_evidence_sha256"))
        or [item.get("role") for item in quarantine.get("outputs", [])]
        != ["instrumental", "vocals"]
        or not 0
        <= quarantine.get("maximum_integer_reconstruction_error_lsb", -1)
        <= 2
    ):
        raise ValueError("MelRoFormer authorised worker quarantine evidence differs")
    for item in quarantine["outputs"]:
        if (
            set(item) != {"role", "bytes", "sha256"}
            or type(item["bytes"]) is not int
            or not 1 <= item["bytes"] <= 4 * 1024 * 1024
            or not _is_sha(item["sha256"])
        ):
            raise ValueError("MelRoFormer authorised worker output evidence differs")
    checked = {**value, "evidence_sha256": digest}
    encoded = json.dumps(checked, sort_keys=True, separators=(",", ":"))
    if "/Users/" in encoded or "://" in encoded:
        raise ValueError("MelRoFormer authorised worker evidence is not path-free")
    return _freeze_json(checked)


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA_RE.fullmatch(value) is not None


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


__all__ = [
    "NETWORK_OBSERVATION_POLICY_ID",
    "NETWORK_OBSERVATION_SCHEMA",
    "POLICY_ID",
    "SCHEMA",
    "_run_private_melroformer_authorised_worker",
    "_validate_private_melroformer_authorised_worker",
]
