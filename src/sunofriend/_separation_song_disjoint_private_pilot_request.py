"""Prepare one reproducible source-bound private separation pilot request.

The existing full-song planner, executor and stitcher are intentionally small
and independently verifiable.  This owner-only preparation layer removes the
manual preflight between them: it binds the pragmatic reference authorization,
proves that the new canonical source differs from the reference source,
measures the exact local Kim runtime/checkpoint/source evidence, and embeds a
fresh gap-free full-song plan.  It starts no worker or model and exposes no
product route.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_checkpoint_canonical import canonical_json_bytes
from ._separation_full_song_executor import (
    _load_verified_plan,
    _require_private_directory,
    _require_private_regular,
)
from ._separation_full_song_join_remediation_executor_v2 import (
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_plan import (
    REPORT_NAME as PLAN_REPORT_NAME,
    _make_private_tree,
    _prepare_private_separation_full_song_plan,
)
from ._separation_full_song_review import _load_stitch_report, _verify_stitch_audio
from ._separation_full_song_stitch import REPORT_NAME as STITCH_REPORT_NAME
from ._separation_melroformer_artifacts import _inspect_companion_files
from ._separation_melroformer_native_runtime_darwin import (
    _measure_private_runtime_launcher,
    _path_free_runtime_binding,
)
from ._separation_melroformer_native_worker import WORKER_RELATIVE_PATH
from ._separation_melroformer_runtime_evidence import (
    SOURCE_MANIFEST_SHA256,
    SOURCE_REVISION,
    _verify_private_melroformer_source_tree,
)
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
    _verify_private_melroformer_upstream_evidence,
)
from ._separation_pragmatic_private_pilot import (
    _load_verified_pragmatic_private_pilot,
)
from ._separation_safetensors_inspection import _inspect_private_safetensors
from ._separation_song_disjoint_private_pilot import (
    _load_reference_v2_execution,
)


_LEGACY_SCHEMA = "sunofriend.private-separation-song-disjoint-pilot-request.v1"
SCHEMA = "sunofriend.private-separation-song-disjoint-pilot-request.v2"
STATUS = "private_pilot_request_prepared_no_model_run"
_LEGACY_POLICY_ID = "source-bound-song-disjoint-private-pilot-request-v1"
POLICY_ID = "source-bound-song-disjoint-private-pilot-request-v2"
REPORT_NAME = "private-separation-song-disjoint-pilot-request.json"
PLAN_DIRECTORY = "PLAN"
_CODE_FILES_V1 = (
    "scripts/private-separation-song-disjoint-pilot-request.py",
    "src/sunofriend/_separation_song_disjoint_private_pilot_request.py",
    "scripts/private-separation-full-song-plan.py",
    "src/sunofriend/_separation_full_song_plan.py",
    "scripts/private-separation-full-song-execute.py",
    "src/sunofriend/_separation_full_song_executor.py",
    "src/sunofriend/_separation_melroformer_native_attempt_darwin.py",
)
_CODE_FILES = (
    *_CODE_FILES_V1,
    "scripts/private-separation-song-disjoint-pilot-execute.py",
    "src/sunofriend/_separation_song_disjoint_private_pilot_execution.py",
    WORKER_RELATIVE_PATH,
    "src/sunofriend/_separation_melroformer_native_worker.py",
)
_PERMISSIONS = {
    "bounded_private_worker_execution_permitted": True,
    "product_route_permitted": False,
    "publication_permitted": False,
    "public_download_permitted": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
    "tui_separation_available": False,
}
_EFFECTS = {
    "canonical_chunk_audio_created": True,
    "model_run": False,
    "private_request_created": True,
    "separator_output_created": False,
    "source_audio_mutated": False,
    "source_graph_mutated": False,
    "product_contract_mutated": False,
    "review_evidence_mutated": False,
}


def _prepare_song_disjoint_private_pilot_request(
    pragmatic_authorization_path: str | Path,
    *,
    reference_v2_execution_path: str | Path,
    reference_stitch_package_dir: str | Path,
    corpus_manifest_path: str | Path,
    track_id: str,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
    out_dir: str | Path,
    device: str = "gpu",
) -> dict[str, Any]:
    """Write a fresh plan plus one path-free, execution-ready request."""

    if device not in {"gpu", "cpu"}:
        raise ValueError("private pilot request device must be gpu or cpu")
    if not isinstance(track_id, str) or not track_id.strip():
        raise ValueError("private pilot request track ID must be non-empty")

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"private pilot request output exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    inputs = _load_request_inputs(
        pragmatic_authorization_path,
        reference_v2_execution_path=reference_v2_execution_path,
        reference_stitch_package_dir=reference_stitch_package_dir,
        repository_root=repository_root,
        runtime_launcher_path=runtime_launcher_path,
        source_root=source_root,
        checkpoint_path=checkpoint_path,
        companion_root=companion_root,
    )
    _require_output_disjoint_from_inputs(
        destination,
        evidence_roots=(
            inputs["reference_stitch_package"],
            inputs["source_root"],
            inputs["companion_root"],
        ),
        evidence_paths=(
            inputs["authorization"]["path"],
            inputs["reference_execution"]["path"],
            inputs["checkpoint_path"],
            Path(corpus_manifest_path).expanduser().absolute(),
            *(inputs["repository_root"] / relative for relative in _CODE_FILES),
        ),
    )

    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-",
            dir=destination.parent,
        )
    )
    temporary.chmod(0o700)
    try:
        plan_result = _prepare_private_separation_full_song_plan(
            corpus_manifest_path,
            track_id.strip(),
            out_dir=temporary / PLAN_DIRECTORY,
        )
        plan_path = temporary / PLAN_DIRECTORY / PLAN_REPORT_NAME
        _, plan, plan_sha256 = _load_verified_plan(plan_path)
        _require_source_distinction(plan, inputs=inputs)

        document = _request_document(
            inputs=inputs,
            plan=plan,
            plan_sha256=plan_sha256,
            device=device,
        )
        report = temporary / REPORT_NAME
        report.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _make_private_tree(temporary)

        rechecked = _load_request_inputs(
            pragmatic_authorization_path,
            reference_v2_execution_path=reference_v2_execution_path,
            reference_stitch_package_dir=reference_stitch_package_dir,
            repository_root=repository_root,
            runtime_launcher_path=runtime_launcher_path,
            source_root=source_root,
            checkpoint_path=checkpoint_path,
            companion_root=companion_root,
        )
        if _request_input_identity(rechecked) != _request_input_identity(inputs):
            raise ValueError("private pilot request inputs changed")
        _, rechecked_plan, rechecked_plan_sha256 = _load_verified_plan(plan_path)
        if (
            rechecked_plan != plan
            or rechecked_plan_sha256 != plan_sha256
        ):
            raise ValueError("private pilot request plan changed")
        persisted = json.loads(report.read_text(encoding="utf-8"))
        if persisted != document:
            raise ValueError("private pilot request report changed")
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return {
        **document,
        "report": str(destination / REPORT_NAME),
        "plan_report": str(destination / PLAN_DIRECTORY / PLAN_REPORT_NAME),
        "plan_output_directory": str(destination / PLAN_DIRECTORY),
        "execution_inputs": {
            "repository_root": str(inputs["repository_root"]),
            "runtime_launcher": str(inputs["runtime_launcher_path"]),
            "source_root": str(inputs["source_root"]),
            "checkpoint": str(inputs["checkpoint_path"]),
            "companion_root": str(inputs["companion_root"]),
            "device": device,
        },
        "plan_command_result": {
            "track_id": plan_result["corpus"]["track_id"],
            "chunk_count": plan_result["chunking"]["chunk_count"],
        },
    }


def _load_verified_song_disjoint_private_pilot_request(
    value: str | Path,
) -> dict[str, Any]:
    """Load one sealed request and re-verify its embedded plan tree."""

    path = Path(value).expanduser().absolute()
    _require_private_regular(path, "private song-disjoint pilot request")
    if path.name != REPORT_NAME:
        raise ValueError("private pilot request filename differs")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private pilot request JSON differs") from error
    if (
        not isinstance(document, dict)
        or document.get("schema") not in {SCHEMA, _LEGACY_SCHEMA}
        or document.get("status") != STATUS
        or document.get("policy_id")
        != (
            POLICY_ID
            if document.get("schema") == SCHEMA
            else _LEGACY_POLICY_ID
        )
        or document.get("evidence_scope") != "private_development_only"
        or document.get("permissions") != _PERMISSIONS
        or document.get("effects") != _EFFECTS
        or document.get("document_sha256") != _document_sha256(document)
    ):
        raise ValueError("private pilot request identity differs")
    _validate_request_document(document)
    plan_claim = document.get("plan")
    if not isinstance(plan_claim, Mapping) or plan_claim.get("path") != (
        f"{PLAN_DIRECTORY}/{PLAN_REPORT_NAME}"
    ):
        raise ValueError("private pilot request plan claim differs")
    plan_path, plan, plan_sha256 = _load_verified_plan(path.parent / plan_claim["path"])
    if (
        plan_sha256 != plan_claim.get("sha256")
        or plan.get("document_sha256") != plan_claim.get("document_sha256")
        or plan.get("canonical_clock", {}).get("pcm24_int32_sequence_sha256")
        != document.get("source_distinction", {}).get(
            "pilot_canonical_pcm24_int32_sequence_sha256"
        )
    ):
        raise ValueError("private pilot request plan binding differs")
    return {
        "path": path,
        "sha256": _sha256(path),
        "document": document,
        "plan_path": plan_path,
        "plan": plan,
        "plan_sha256": plan_sha256,
    }


def _validate_request_document(document: Mapping[str, Any]) -> None:
    bindings = document.get("bindings")
    pilot = document.get("pilot")
    distinction = document.get("source_distinction")
    environment = document.get("execution_environment")
    plan = document.get("plan")
    readiness = document.get("readiness")
    if not all(
        isinstance(item, Mapping)
        for item in (bindings, pilot, distinction, environment, plan, readiness)
    ):
        raise ValueError("private pilot request fields differ")
    assert isinstance(bindings, Mapping)
    assert isinstance(pilot, Mapping)
    assert isinstance(distinction, Mapping)
    assert isinstance(environment, Mapping)
    assert isinstance(plan, Mapping)
    assert isinstance(readiness, Mapping)
    if (
        set(bindings)
        != {
            "pragmatic_authorization_sha256",
            "pragmatic_authorization_document_sha256",
            "reference_v2_execution_sha256",
            "reference_v2_execution_document_sha256",
            "reference_stitch_sha256",
            "reference_stitch_document_sha256",
            "corpus_manifest_sha256",
        }
        or any(not _is_sha256(value) for value in bindings.values())
        or pilot.get("candidate_id") != "mlx-melroformer-kim-vocal-2"
        or pilot.get("device") not in {"gpu", "cpu"}
        or pilot.get("worker_policy")
        != "one-independent-audited-worker-call-per-plan-chunk"
        or pilot.get("stitch_policy")
        != "raw-concatenation-no-crossfade-no-gain-no-repair"
        or pilot.get("fresh_track_specific_human_review_required") is not True
    ):
        raise ValueError("private pilot request binding differs")
    reference_pcm = distinction.get(
        "reference_canonical_pcm24_int32_sequence_sha256"
    )
    pilot_pcm = distinction.get("pilot_canonical_pcm24_int32_sequence_sha256")
    if (
        not _is_sha256(reference_pcm)
        or not _is_sha256(pilot_pcm)
        or reference_pcm == pilot_pcm
        or distinction
        != {
            "reference_canonical_pcm24_int32_sequence_sha256": reference_pcm,
            "pilot_canonical_pcm24_int32_sequence_sha256": pilot_pcm,
            "byte_distinct": True,
            "song_disjoint_content_check_passed": True,
            "musical_identity_inferred_from_hash": False,
        }
    ):
        raise ValueError("private pilot request source distinction differs")
    schema = document.get("schema")
    expected_code_files = _CODE_FILES if schema == SCHEMA else _CODE_FILES_V1
    checkpoint = environment.get("checkpoint")
    audited_source = environment.get("audited_source")
    companions = environment.get("companions")
    code = environment.get("coordinator_code")
    if (
        not isinstance(checkpoint, Mapping)
        or checkpoint.get("bytes") != CONVERSION_CHECKPOINT_BYTES
        or checkpoint.get("sha256") != CONVERSION_CHECKPOINT_SHA256
        or checkpoint.get("tensor_values_observed") is not False
        or checkpoint.get("tensor_library_imported") is not False
        or not isinstance(audited_source, Mapping)
        or audited_source.get("status") != "verified_not_imported"
        or audited_source.get("revision") != SOURCE_REVISION
        or audited_source.get("manifest_sha256") != SOURCE_MANIFEST_SHA256
        or not isinstance(audited_source.get("files"), list)
        or not audited_source["files"]
        or not isinstance(companions, Mapping)
        or set(companions) != {"LICENSE", "config.json"}
        or not isinstance(code, Mapping)
        or set(code) != set(expected_code_files)
        or environment.get("offline_environment_required") is not True
    ):
        raise ValueError("private pilot request execution environment differs")
    for item in (*audited_source["files"], *companions.values(), *code.values()):
        if (
            not isinstance(item, Mapping)
            or isinstance(item.get("bytes"), bool)
            or not isinstance(item.get("bytes"), int)
            or item["bytes"] <= 0
            or not _is_sha256(item.get("sha256"))
        ):
            raise ValueError("private pilot request artifact identity differs")
    if schema == SCHEMA:
        worker = environment.get("worker_source")
        if (
            not isinstance(worker, Mapping)
            or worker != code.get(WORKER_RELATIVE_PATH)
            or not _is_sha256(environment.get("companion_manifest_sha256"))
        ):
            raise ValueError("private pilot request worker binding differs")
    elif (
        "worker_source" in environment
        or "companion_manifest_sha256" in environment
    ):
        raise ValueError("legacy private pilot request environment differs")
    if (
        plan.get("policy_id") != "contiguous-canonical-44100-worker-chunks-v1"
        or plan.get("sample_rate") != 44_100
        or plan.get("channels") != 2
        or isinstance(plan.get("frames"), bool)
        or not isinstance(plan.get("frames"), int)
        or plan["frames"] <= 0
        or isinstance(plan.get("chunk_count"), bool)
        or not isinstance(plan.get("chunk_count"), int)
        or plan["chunk_count"] <= 0
        or plan.get("maximum_chunk_frames") != 661_500
        or plan.get("maximum_chunk_seconds") != 15.0
        or plan.get("gap_frames") != 0
        or plan.get("overlap_frames") != 0
        or not _is_sha256(plan.get("sha256"))
        or not _is_sha256(plan.get("document_sha256"))
        or readiness
        != {
            "pragmatic_reference_authorization_verified": True,
            "source_distinct_from_reference": True,
            "local_runtime_checkpoint_and_source_verified": True,
            "gap_free_worker_queue_prepared": True,
            "private_worker_execution_ready": True,
            "worker_runs_complete": False,
            "stitch_complete": False,
            "human_review_complete": False,
            "separator_selected_or_accepted": False,
            "publication_ready": False,
        }
        or document.get("next_action")
        != (
            "execute_or_resume_through_the_request_bound_adapter"
            if schema == SCHEMA
            else "execute_or_resume_the_exact_embedded_plan"
        )
    ):
        raise ValueError("private pilot request readiness differs")


def _load_request_inputs(
    pragmatic_authorization_path: str | Path,
    *,
    reference_v2_execution_path: str | Path,
    reference_stitch_package_dir: str | Path,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
) -> dict[str, Any]:
    authorization = _load_verified_pragmatic_private_pilot(
        pragmatic_authorization_path
    )
    if (
        authorization["document"].get("permissions", {}).get(
            "bounded_private_pilot_use"
        )
        is not True
    ):
        raise ValueError("pragmatic authorization does not permit a private pilot")
    reference = _load_reference_v2_execution(
        reference_v2_execution_path,
        authorization=authorization["document"],
    )
    stitch_package = Path(reference_stitch_package_dir).expanduser().absolute()
    _require_private_directory(stitch_package, "reference stitch package")
    stitch_path = stitch_package / STITCH_REPORT_NAME
    stitch = _load_stitch_report(stitch_path)
    _verify_stitch_audio(stitch_package, stitch)
    reference_bindings = reference["document"].get("bindings", {})
    if (
        reference_bindings.get("stitch_report_sha256") != _sha256(stitch_path)
        or reference_bindings.get("stitch_document_sha256")
        != stitch.get("document_sha256")
        or reference_bindings.get("source_audio_sha256")
        != stitch.get("artifacts", {}).get("source", {}).get("sha256")
    ):
        raise ValueError("reference stitch differs from pragmatic authorization")
    reference_pcm = stitch.get("artifacts", {}).get("source", {}).get(
        "pcm24_int32_sequence_sha256"
    )
    if not _is_sha256(reference_pcm):
        raise ValueError("reference stitch source PCM identity differs")

    measured = _measure_request_execution_environment(
        repository_root=repository_root,
        runtime_launcher_path=runtime_launcher_path,
        source_root=source_root,
        checkpoint_path=checkpoint_path,
        companion_root=companion_root,
    )
    return {
        "authorization": authorization,
        "reference_execution": reference,
        "reference_stitch_package": stitch_package,
        "reference_stitch_path": stitch_path,
        "reference_stitch": stitch,
        "reference_source_pcm24_sha256": reference_pcm,
        **measured,
    }


def _measure_request_execution_environment(
    *,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
) -> dict[str, Any]:
    """Measure the exact path-free environment used by a v2 request."""

    repository = Path(repository_root).expanduser().absolute()
    if not repository.is_dir() or repository.is_symlink():
        raise ValueError("private pilot repository root must be a directory")
    upstream = _verify_private_melroformer_upstream_evidence(repository)
    code = {
        relative: _regular_file_claim(repository / relative, label=relative)
        for relative in _CODE_FILES
    }
    runtime_path = Path(runtime_launcher_path).expanduser().absolute()
    runtime = _measure_private_runtime_launcher(runtime_path)
    source = Path(source_root).expanduser().absolute()
    source_observation = _verify_private_melroformer_source_tree(source)
    companions = Path(companion_root).expanduser().absolute()
    companion_observation = _inspect_companion_files(companions)
    if companion_observation.get("all_cryptographic_identities_verified") is not True:
        raise ValueError("private pilot companion identities differ")
    checkpoint = Path(checkpoint_path).expanduser().absolute()
    checkpoint_observation = _inspect_private_safetensors(
        checkpoint,
        expected_bytes=CONVERSION_CHECKPOINT_BYTES,
        expected_sha256=CONVERSION_CHECKPOINT_SHA256,
    )
    measured = {
        "repository_root": repository,
        "upstream": upstream,
        "code": code,
        "runtime_launcher_path": runtime_path,
        "runtime": runtime,
        "source_root": source,
        "source_observation": source_observation,
        "checkpoint_path": checkpoint,
        "checkpoint_observation": checkpoint_observation,
        "companion_root": companions,
        "companion_observation": companion_observation,
    }
    measured["execution_environment"] = _execution_environment_document(measured)
    return measured


def _request_document(
    *,
    inputs: Mapping[str, Any],
    plan: Mapping[str, Any],
    plan_sha256: str,
    device: str,
) -> dict[str, Any]:
    authorization = inputs["authorization"]
    reference = inputs["reference_execution"]
    stitch = inputs["reference_stitch"]
    pilot_pcm = plan["canonical_clock"]["pcm24_int32_sequence_sha256"]
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "policy_id": POLICY_ID,
        "evidence_scope": "private_development_only",
        "bindings": {
            "pragmatic_authorization_sha256": authorization["sha256"],
            "pragmatic_authorization_document_sha256": authorization["document"][
                "document_sha256"
            ],
            "reference_v2_execution_sha256": reference["sha256"],
            "reference_v2_execution_document_sha256": reference["document"][
                "document_sha256"
            ],
            "reference_stitch_sha256": _sha256(inputs["reference_stitch_path"]),
            "reference_stitch_document_sha256": stitch["document_sha256"],
            "corpus_manifest_sha256": plan["corpus"]["manifest_sha256"],
        },
        "pilot": {
            "track_id": plan["corpus"]["track_id"],
            "track_title": plan["corpus"]["track_title"],
            "rights_authority": plan["corpus"]["rights_authority"],
            "device": device,
            "candidate_id": "mlx-melroformer-kim-vocal-2",
            "worker_policy": "one-independent-audited-worker-call-per-plan-chunk",
            "stitch_policy": "raw-concatenation-no-crossfade-no-gain-no-repair",
            "fresh_track_specific_human_review_required": True,
        },
        "source_distinction": {
            "reference_canonical_pcm24_int32_sequence_sha256": inputs[
                "reference_source_pcm24_sha256"
            ],
            "pilot_canonical_pcm24_int32_sequence_sha256": pilot_pcm,
            "byte_distinct": True,
            "song_disjoint_content_check_passed": True,
            "musical_identity_inferred_from_hash": False,
        },
        "execution_environment": inputs.get("execution_environment")
        or _execution_environment_document(inputs),
        "plan": {
            "path": f"{PLAN_DIRECTORY}/{PLAN_REPORT_NAME}",
            "sha256": plan_sha256,
            "document_sha256": plan["document_sha256"],
            "policy_id": plan["policy_id"],
            "sample_rate": plan["canonical_clock"]["sample_rate"],
            "channels": plan["canonical_clock"]["channels"],
            "frames": plan["canonical_clock"]["frames"],
            "duration_seconds": plan["canonical_clock"]["duration_seconds"],
            "chunk_count": plan["chunking"]["chunk_count"],
            "maximum_chunk_frames": plan["chunking"]["maximum_chunk_frames"],
            "maximum_chunk_seconds": plan["chunking"]["maximum_chunk_seconds"],
            "gap_frames": plan["chunking"]["gap_frames"],
            "overlap_frames": plan["chunking"]["overlap_frames"],
        },
        "readiness": {
            "pragmatic_reference_authorization_verified": True,
            "source_distinct_from_reference": True,
            "local_runtime_checkpoint_and_source_verified": True,
            "gap_free_worker_queue_prepared": True,
            "private_worker_execution_ready": True,
            "worker_runs_complete": False,
            "stitch_complete": False,
            "human_review_complete": False,
            "separator_selected_or_accepted": False,
            "publication_ready": False,
        },
        "permissions": dict(_PERMISSIONS),
        "effects": dict(_EFFECTS),
        "next_action": "execute_or_resume_through_the_request_bound_adapter",
        "limitations": [
            "Preparation creates canonical chunk audio but runs no worker or model.",
            "Source-content distinction is a cryptographic PCM comparison, not musical identity or quality evidence.",
            "Exact local paths are returned only to the invoking process and are not stored in this report.",
            "The runtime, checkpoint, source and companion inputs must be reverified at execution time.",
            "A complete stitch, alignment check and fresh track-specific human review are still required.",
            "This request enables no Simple, Studio, TUI, source-graph, public download or publication route.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _execution_environment_document(inputs: Mapping[str, Any]) -> dict[str, Any]:
    source_observation = inputs["source_observation"]
    checkpoint = inputs["checkpoint_observation"]
    companions = inputs["companion_observation"]
    companion_files = [
        {
            "name": name,
            "bytes": item["bytes"],
            "sha256": item["sha256"],
        }
        for name, item in sorted(companions["files"].items())
    ]
    code = inputs["code"]
    return {
        "runtime": _path_free_runtime_binding(inputs["runtime"]),
        "checkpoint": {
            key: checkpoint[key]
            for key in (
                "schema",
                "status",
                "bytes",
                "sha256",
                "container",
                "header_bytes",
                "data_bytes",
                "tensor_count",
                "tensor_names_sha256",
                "dtype_counts",
                "tensor_values_observed",
                "tensor_library_imported",
            )
        },
        "audited_source": {
            "status": source_observation["status"],
            "revision": SOURCE_REVISION,
            "manifest_sha256": SOURCE_MANIFEST_SHA256,
            "files": [
                {
                    "path": item["path"],
                    "bytes": item["bytes"],
                    "sha256": item["sha256"],
                }
                for item in source_observation["files"]
            ],
        },
        "companions": {
            item["name"]: {
                "bytes": item["bytes"],
                "sha256": item["sha256"],
            }
            for item in companion_files
        },
        "companion_manifest_sha256": hashlib.sha256(
            canonical_json_bytes(companion_files)
        ).hexdigest(),
        "worker_source": code[WORKER_RELATIVE_PATH],
        "tracked_upstream_evidence_sha256": inputs["upstream"][
            "verification_sha256"
        ],
        "coordinator_code": code,
        "offline_environment_required": True,
    }


def _require_source_distinction(
    plan: Mapping[str, Any], *, inputs: Mapping[str, Any]
) -> None:
    pilot_pcm = plan.get("canonical_clock", {}).get(
        "pcm24_int32_sequence_sha256"
    )
    reference_pcm = inputs["reference_source_pcm24_sha256"]
    if not _is_sha256(pilot_pcm) or pilot_pcm == reference_pcm:
        raise ValueError("private pilot source is not distinct from the reference")


def _request_input_identity(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    checkpoint = inputs["checkpoint_observation"]
    companions = inputs["companion_observation"]
    source = inputs["source_observation"]
    return {
        "authorization_sha256": inputs["authorization"]["sha256"],
        "reference_execution_sha256": inputs["reference_execution"]["sha256"],
        "reference_stitch_sha256": _sha256(inputs["reference_stitch_path"]),
        "reference_source_pcm24_sha256": inputs[
            "reference_source_pcm24_sha256"
        ],
        "runtime": _path_free_runtime_binding(inputs["runtime"]),
        "checkpoint": {
            "bytes": checkpoint["bytes"],
            "sha256": checkpoint["sha256"],
            "tensor_names_sha256": checkpoint["tensor_names_sha256"],
        },
        "source_files": [
            (item["path"], item["bytes"], item["sha256"])
            for item in source["files"]
        ],
        "companions": {
            name: (item["bytes"], item["sha256"])
            for name, item in companions["files"].items()
        },
        "upstream_sha256": inputs["upstream"]["verification_sha256"],
        "code": inputs["code"],
    }


def _regular_file_claim(path: Path, *, label: str) -> dict[str, Any]:
    try:
        before = path.lstat()
    except OSError as error:
        raise ValueError(f"private pilot {label} is unavailable") from error
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
    ):
        raise ValueError(f"private pilot {label} must be one regular file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ):
            raise ValueError(f"private pilot {label} changed before measurement")
        digest = hashlib.sha256()
        offset = 0
        while offset < opened.st_size:
            chunk = os.pread(descriptor, min(1024 * 1024, opened.st_size - offset), offset)
            if not chunk:
                raise ValueError(f"private pilot {label} is truncated")
            digest.update(chunk)
            offset += len(chunk)
        after_descriptor = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = path.lstat()
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        )
        != (
            after_descriptor.st_dev,
            after_descriptor.st_ino,
            after_descriptor.st_size,
            after_descriptor.st_mtime_ns,
        )
    ):
        raise ValueError(f"private pilot {label} changed during measurement")
    return {"bytes": before.st_size, "sha256": digest.hexdigest()}


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__: tuple[str, ...] = ()
