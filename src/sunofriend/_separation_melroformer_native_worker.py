"""Private fd3-fd7 execution core for the fixed native Kim worker.

The bootstrap hardens the five inherited descriptors before importing this
module. This core validates the framed request, binds its parent-selected
worker and repository, loads the exact checkpoint only through descriptor 5,
performs one authorised excerpt inference, pauses on the existing ready/release
boundary, and writes one path-free result frame. It remains unreachable from
every public product route.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import socket
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

from ._separation_checkpoint_canonical import canonical_json_bytes, plain
from ._separation_melroformer_artifacts import (
    CONFIG_BYTES,
    CONFIG_NAME,
    CONFIG_SHA256,
    LICENSE_BYTES,
    LICENSE_NAME,
    LICENSE_SHA256,
    _inspect_companion_files,
)
from ._separation_melroformer_native_transport import (
    REQUEST_MAXIMUM_BYTES,
    RESULT_MAXIMUM_BYTES,
    _build_private_melroformer_native_result,
    _decode_private_melroformer_native_request,
    _encode_private_melroformer_native_result,
)
from ._separation_melroformer_pcm24_quarantine import (
    _materialize_private_melroformer_pcm24_quarantine,
)
from ._separation_melroformer_real_bridge import (
    _infer_private_melroformer_excerpt,
    _load_private_authorised_excerpt,
    _load_private_melroformer_model,
)
from ._separation_melroformer_runtime_evidence import SOURCE_MANIFEST_SHA256
from ._separation_melroformer_supervision import (
    _observe_post_cpython_signal_state,
)
from ._separation_python_import_closure import (
    _capture_python_import_closure_claim,
    _mark_python_import_closure_stable,
    _melroformer_python_import_roots,
)
from ._separation_worker_ready_handshake import (
    READY_PHASE,
    READY_SCHEMA,
    RELEASE_PROTOCOL,
    _worker_wait_for_native_image_inventory,
)


SCHEMA = "sunofriend.private-melroformer-native-worker-child.v1"
STATUS = "real_worker_complete_parent_verification_required"
WORKER_RELATIVE_PATH = "scripts/private-melroformer-native-worker.py"
CHECKPOINT_DESCRIPTOR = 5
REQUEST_DESCRIPTOR = 3
RESULT_DESCRIPTOR = 4
READY_DESCRIPTOR = 6
RELEASE_DESCRIPTOR = 7
_EVIDENCE_DIRECTORY = "WORKER-EVIDENCE"
_CLOSURE_NAME = "python-import-closure-claim.json"
_MAXIMUM_WORKER_BYTES = 256 * 1024


def _run_private_melroformer_native_worker(
    *,
    worker_path: str | Path,
    repository_root: str | Path,
) -> int:
    """Execute one already-authorised request through fixed descriptors."""

    worker = Path(worker_path).absolute()
    repository = Path(repository_root).absolute()
    request = _read_private_melroformer_native_request(REQUEST_DESCRIPTOR)
    paths = request["paths"]
    identities = request["identities"]
    execution = request["execution"]
    expected_worker = repository / WORKER_RELATIVE_PATH
    if (
        worker != expected_worker
        or paths["repository_root"] != str(repository)
        or identities["source_manifest_sha256"] != SOURCE_MANIFEST_SHA256
    ):
        raise ValueError("native Kim worker repository binding differs")
    worker_identity = _regular_file_identity(
        worker,
        maximum_bytes=_MAXIMUM_WORKER_BYTES,
    )
    if worker_identity["sha256"] != identities["worker_source_sha256"]:
        raise ValueError("native Kim worker source identity differs")
    companion = _inspect_companion_files(paths["companion_root"])
    companion_identity = _companion_manifest_identity(companion)
    if companion_identity["manifest_sha256"] != identities[
        "companion_manifest_sha256"
    ]:
        raise ValueError("native Kim companion manifest identity differs")
    if os.getpgrp() != os.getpid():
        raise RuntimeError("native Kim worker lacks a private process group")

    signal_state = _observe_post_cpython_signal_state()
    canaries = _sandbox_canaries(Path(paths["staging_directory"]))
    handle = None
    try:
        handle = _load_private_melroformer_model(
            source_root=paths["source_root"],
            checkpoint_path=paths["checkpoint_path"],
            companion_root=paths["companion_root"],
            device=execution["device"],
            checkpoint_descriptor=CHECKPOINT_DESCRIPTOR,
        )
    finally:
        _close_descriptor(CHECKPOINT_DESCRIPTOR)
    source, authorisation = _load_private_authorised_excerpt(
        handle,
        report_path=paths["authorisation_report_path"],
        expected_report_sha256=identities["authorisation_report_sha256"],
    )
    observation = _infer_private_melroformer_excerpt(
        handle,
        source,
        sample_rate=execution["sample_rate"],
    )
    _worker_wait_for_native_image_inventory(
        ready_fd=READY_DESCRIPTOR,
        release_fd=RELEASE_DESCRIPTOR,
        claim={
            "schema": READY_SCHEMA,
            "phase": READY_PHASE,
            "candidate_id": request["candidate_id"],
            "checkpoint_sha256": identities["checkpoint_sha256"],
            "authorised_audio_sha256": authorisation["audio_sha256"],
            "source_frames": observation.evidence["geometry"]["frames"],
            "vocal_float32_sha256": observation.evidence["outputs"]["vocals"][
                "sha256"
            ],
            "instrumental_float32_sha256": observation.evidence["outputs"][
                "instrumental"
            ]["sha256"],
            "release_protocol": RELEASE_PROTOCOL,
        },
    )
    staging = Path(paths["staging_directory"])
    quarantine = _materialize_private_melroformer_pcm24_quarantine(
        destination=staging / "quarantine",
        source=source,
        vocals=observation.vocals,
        instrumental=observation.instrumental,
        np=handle.np,
        allow_shared_attenuation=True,
    )
    roots = _melroformer_python_import_roots(
        repository_root=repository,
        source_root=paths["source_root"],
        runtime_environment_root=sys.prefix,
        base_runtime_root=sys.base_prefix,
    )
    closure = _mark_python_import_closure_stable(
        _capture_python_import_closure_claim(roots=roots)
    )
    closure_artifact = _write_private_closure_claim(staging, closure)
    child_result = {
        "schema": SCHEMA,
        "status": STATUS,
        "request_validated": True,
        "worker": worker_identity,
        "companion_manifest": companion_identity,
        "canaries": canaries,
        "signal_state": plain(signal_state),
        "model": {
            "authorisation": plain(authorisation),
            "bridge": plain(handle.evidence),
            "inference": plain(observation.evidence),
        },
        "quarantine": plain(quarantine),
        "python_import_closure_claim": closure_artifact,
        "descriptor_contract": {
            "request_frame_read_from_fd3": True,
            "result_frame_written_to_fd4": True,
            "checkpoint_loaded_from_fd5": True,
            "ready_release_completed_on_fd6_fd7": True,
            "checkpoint_path_reopened": False,
            "logical_descriptors_retained": False,
        },
        "permissions": {
            "publication_permitted": False,
            "automatic_selection_permitted": False,
            "product_route_permitted": False,
        },
    }
    result = _build_private_melroformer_native_result(
        request=request,
        private_process_identity={"pid": os.getpid(), "pgid": os.getpgrp()},
        child_result=child_result,
    )
    _write_private_melroformer_native_result(
        RESULT_DESCRIPTOR,
        _encode_private_melroformer_native_result(result, request=request),
    )
    return 0


def _read_private_melroformer_native_request(descriptor: int) -> Mapping[str, Any]:
    state = os.fstat(descriptor)
    if (
        not stat.S_ISREG(state.st_mode)
        or state.st_nlink != 1
        or state.st_size <= 0
        or state.st_size > REQUEST_MAXIMUM_BYTES
        or os.get_inheritable(descriptor)
        or fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE == os.O_WRONLY
    ):
        raise ValueError("native Kim request descriptor differs")
    frame = os.pread(descriptor, state.st_size, 0)
    if len(frame) != state.st_size:
        raise ValueError("native Kim request frame is truncated")
    _close_descriptor(descriptor)
    return _decode_private_melroformer_native_request(frame)


def _write_private_melroformer_native_result(
    descriptor: int,
    frame: bytes,
) -> None:
    state = os.fstat(descriptor)
    flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
    if (
        type(frame) is not bytes
        or not frame
        or len(frame) > RESULT_MAXIMUM_BYTES
        or not stat.S_ISREG(state.st_mode)
        or state.st_nlink != 1
        or state.st_size != 0
        or os.get_inheritable(descriptor)
        or flags & os.O_ACCMODE == os.O_RDONLY
        or flags & os.O_APPEND
    ):
        raise ValueError("native Kim result descriptor differs")
    offset = 0
    while offset < len(frame):
        written = os.pwrite(descriptor, frame[offset:], offset)
        if written <= 0:
            raise RuntimeError("native Kim result write made no progress")
        offset += written
    os.ftruncate(descriptor, len(frame))
    os.fsync(descriptor)
    _close_descriptor(descriptor)


def _companion_manifest_identity(
    observation: Mapping[str, Any],
) -> Mapping[str, Any]:
    if observation.get("all_cryptographic_identities_verified") is not True:
        raise ValueError("native Kim companion identities are not verified")
    files = observation.get("files")
    if not isinstance(files, Mapping) or set(files) != {CONFIG_NAME, LICENSE_NAME}:
        raise ValueError("native Kim companion files differ")
    expected = {
        CONFIG_NAME: {"bytes": CONFIG_BYTES, "sha256": CONFIG_SHA256},
        LICENSE_NAME: {"bytes": LICENSE_BYTES, "sha256": LICENSE_SHA256},
    }
    clean = []
    for name in sorted(expected):
        item = files[name]
        if (
            not isinstance(item, Mapping)
            or item.get("bytes") != expected[name]["bytes"]
            or item.get("sha256") != expected[name]["sha256"]
            or item.get("cryptographic_identity_verified") is not True
        ):
            raise ValueError("native Kim companion identity differs")
        clean.append({"name": name, **expected[name]})
    return {
        "files": clean,
        "manifest_sha256": hashlib.sha256(canonical_json_bytes(clean)).hexdigest(),
    }


def _regular_file_identity(path: Path, *, maximum_bytes: int) -> Mapping[str, Any]:
    before = path.lstat()
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or not 1 <= before.st_size <= maximum_bytes
    ):
        raise ValueError("native Kim worker source is not a bounded regular file")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        digest = hashlib.sha256()
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    rebound = path.lstat()
    if _stat_identity(before) != _stat_identity(opened) or _stat_identity(
        opened
    ) != _stat_identity(after) or _stat_identity(after) != _stat_identity(rebound):
        raise ValueError("native Kim worker source changed during hashing")
    return {"bytes": opened.st_size, "sha256": digest.hexdigest()}


def _sandbox_canaries(staging: Path) -> Mapping[str, Any]:
    if os.environ.get("SUNOFRIEND_PRIVATE_KIM_NATIVE_SANDBOX") != "1":
        raise ValueError("native Kim fixed sandbox environment differs")
    attached = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        network_errno = attached.connect_ex(("127.0.0.1", 9))
    finally:
        attached.close()
    try:
        child = os.fork()
    except OSError as error:
        fork_errno = error.errno or 0
    else:
        if child == 0:
            os._exit(97)
        os.waitpid(child, 0)
        fork_errno = 0
    outside = staging.parent / f".{staging.name}-outside-native-write-canary"
    try:
        descriptor = os.open(
            outside,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except OSError as error:
        outside_errno = error.errno or 0
    else:
        os.close(descriptor)
        outside_errno = 0
    if (network_errno, fork_errno, outside_errno) != (
        errno.EPERM,
        errno.EPERM,
        errno.EPERM,
    ):
        raise RuntimeError("native Kim sandbox canary differs")
    return {
        "network_connect_errno": network_errno,
        "network_errno_name": errno.errorcode[network_errno],
        "process_fork_errno": fork_errno,
        "process_fork_errno_name": errno.errorcode[fork_errno],
        "outside_write_errno": outside_errno,
        "outside_write_errno_name": errno.errorcode[outside_errno],
        "fixed_sandbox_environment_observed": True,
    }


def _write_private_closure_claim(
    staging: Path,
    closure: Mapping[str, Any],
) -> Mapping[str, Any]:
    directory = staging / _EVIDENCE_DIRECTORY
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(directory, 0o700)
    encoded = json.dumps(
        plain(closure),
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    descriptor = os.open(
        directory / _CLOSURE_NAME,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        os.set_inheritable(descriptor, False)
        offset = 0
        while offset < len(encoded):
            written = os.write(descriptor, encoded[offset:])
            if written <= 0:
                raise RuntimeError("native Kim closure write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return {
        "relative_path": f"{_EVIDENCE_DIRECTORY}/{_CLOSURE_NAME}",
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "contains_private_paths": True,
        "parent_verification_required": True,
    }


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
    )


def _close_descriptor(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError as error:
        if error.errno != errno.EBADF:
            raise


__all__: tuple[str, ...] = ()
