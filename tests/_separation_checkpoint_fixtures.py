from __future__ import annotations

import copy
import hashlib
import json
import struct
import zlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sunofriend.separation_checkpoint_inspection import (
    SeparationCheckpointInspection,
    bind_separation_checkpoint_inspection_request,
    inspect_separation_checkpoint,
)
from sunofriend.separation_contract import (
    SeparationAudioGeometry,
    SeparationRequest,
)
from sunofriend.separation_worker_contract import (
    SEPARATION_WORKER_ISOLATION_POLICY,
    SeparationRuntimeArtifactIdentity,
    build_separation_worker_request,
)
from tests.test_separation_backend_preflight import (
    _make_inputs as make_preflight_inputs,
)
from tests.test_separation_backend_preflight import (
    _replace_acceptance as replace_acceptance,
)
from tests.test_separation_backend_preflight import _run as run_preflight


_LOCAL = struct.Struct("<4s5H3L2H")
_DESCRIPTOR = struct.Struct("<4s3L")
_CENTRAL = struct.Struct("<4s6H3L5H2L")
_ZIP64_EOCD = struct.Struct("<4sQ2H2L4Q")
_ZIP64_LOCATOR = struct.Struct("<4sLQL")
_EOCD = struct.Struct("<4s4H2LH")
TORCH_ZIP_FLAGS = 0x0808


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def canonical_sha256(value: Any) -> str:
    """Independent test oracle for Sunofriend canonical JSON hashes."""

    encoded = json.dumps(
        _plain(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def model_pickle() -> bytes:
    return b"\x80\x02cdemucs.htdemucs\nHTDemucs\n)\x81."


def torch_zip(
    *,
    pickle_data: bytes | None = None,
    members: list[tuple[bytes, bytes]] | None = None,
    local_names: list[bytes] | None = None,
    flags: int = TORCH_ZIP_FLAGS,
    compression: int = 0,
    local_extra: bytes | None = None,
    central_extra: bytes = b"",
    central_comment: bytes = b"",
    external_attr: int = 0,
    prefix: bytes = b"",
    gap_before_central: bytes = b"",
    zip64: bool = False,
    bad_zip64: bool = False,
    eocd_comment: bytes = b"",
    trailer: bytes = b"",
    descriptor_signature: bytes = b"PK\x07\x08",
    local_crc: int = 0,
    local_sizes: tuple[int, int] = (0, 0),
) -> bytes:
    """Build the exact small stored Torch ZIP dialect without zipfile."""

    if members is None:
        members = [
            (b"archive/data.pkl", pickle_data or b"\x80\x02}."),
            (b"archive/version", b"3\n"),
            (b"archive/data/0", b"\x00\x01\x02\x03"),
        ]
    if local_names is None:
        local_names = [name for name, _data in members]
    if len(local_names) != len(members):
        raise AssertionError("test fixture local-name count differs")

    local = bytearray(prefix)
    central_rows: list[bytes] = []
    for (central_name, data), local_name in zip(members, local_names):
        offset = len(local)
        crc = zlib.crc32(data) & 0xFFFFFFFF
        member_extra = local_extra
        if member_extra is None:
            extra_bytes = (-(offset + _LOCAL.size + len(local_name))) % 64
            if 0 < extra_bytes < 4:
                extra_bytes += 64
            member_extra = (
                b""
                if extra_bytes == 0
                else (
                    struct.pack("<HH", 0x4246, extra_bytes - 4)
                    + b"Z" * (extra_bytes - 4)
                )
            )
        local.extend(
            _LOCAL.pack(
                b"PK\x03\x04",
                0,
                flags,
                compression,
                0,
                0,
                local_crc,
                local_sizes[0],
                local_sizes[1],
                len(local_name),
                len(member_extra),
            )
        )
        local.extend(local_name)
        local.extend(member_extra)
        local.extend(data)
        local.extend(
            _DESCRIPTOR.pack(
                descriptor_signature,
                crc,
                len(data),
                len(data),
            )
        )
        central_rows.append(
            _CENTRAL.pack(
                b"PK\x01\x02",
                0,
                0,
                flags,
                compression,
                0,
                0,
                crc,
                len(data),
                len(data),
                len(central_name),
                len(central_extra),
                len(central_comment),
                0,
                0,
                external_attr,
                offset,
            )
            + central_name
            + central_extra
            + central_comment
        )

    local.extend(gap_before_central)
    central_offset = len(local)
    central = b"".join(central_rows)
    count = len(members)
    result = bytes(local) + central
    central_end = central_offset + len(central)
    if zip64:
        result += _ZIP64_EOCD.pack(
            b"PK\x06\x06",
            44,
            45,
            45,
            0,
            0,
            count,
            count,
            len(central),
            central_offset,
        )
        result += _ZIP64_LOCATOR.pack(
            b"PK\x06\x07",
            0,
            central_end + (1 if bad_zip64 else 0),
            1,
        )
    result += _EOCD.pack(
        b"PK\x05\x06",
        0,
        0,
        count,
        count,
        len(central),
        central_offset,
        len(eocd_comment),
    )
    return result + eocd_comment + trailer


def checkpoint_fixture(
    tmp_path: Path,
    checkpoint_bytes: bytes,
) -> dict[str, Any]:
    inputs = make_preflight_inputs(tmp_path / "preflight")
    old_checkpoint = inputs["checkpoint"]
    old_checkpoint.unlink()
    checkpoint = old_checkpoint.with_suffix(".pt")
    checkpoint.write_bytes(checkpoint_bytes)
    inputs["checkpoint"] = checkpoint

    acceptance = copy.deepcopy(inputs["acceptance"])
    candidate = acceptance["identities"]["candidate_separator"]
    candidate["backend_id"] = "candidate-separator-backend"
    candidate["checkpoint"]["checkpoint_id"] = "candidate-checkpoint"
    candidate["checkpoint"]["format"] = "torch-state-dict"
    candidate["checkpoint"]["sha256"] = _sha256(checkpoint_bytes)
    candidate["checkpoint"]["bytes"] = len(checkpoint_bytes)
    replace_acceptance(inputs, acceptance)
    preflight = run_preflight(inputs)

    identity = inputs["acceptance"]["identities"]["candidate_separator"]
    geometry = SeparationAudioGeometry(
        sample_rate=44_100,
        channels=2,
        frames=88_200,
        duration_seconds=2.0,
    )
    source_sha = _sha256(b"source")
    separation_request = SeparationRequest.create(
        source_path=tmp_path / "source.wav",
        output_dir=tmp_path / "worker-output",
        checkpoint_path=checkpoint,
        source_id=f"sha256:{source_sha}",
        source_sha256=source_sha,
        canonical_sha256=_sha256(b"canonical source"),
        source_geometry=geometry,
        scope="broad",
        parent_node_id=None,
        backend_id=preflight["arm"]["backend_id"],
        checkpoint_id=preflight["arm"]["checkpoint_id"],
        checkpoint_sha256=identity["checkpoint"]["sha256"],
        requested_roles=("bass", "drums"),
        settings={
            "overlap": 0.25,
            "segments": 8,
            "shifts": 0,
            "split": True,
        },
        seed=17,
    )
    isolation = {
        "policy_id": SEPARATION_WORKER_ISOLATION_POLICY,
        "evidence_scope": "private_development",
        "required_status": "development_enforced_observation_unproven",
        "provider_id": "sandbox-exec",
        "profile_sha256": _sha256(b"profile"),
        "environment_sha256": _sha256(b"environment"),
        "file_descriptor_policy_sha256": _sha256(b"fd-policy"),
        "canary_sha256": _sha256(b"canary"),
        "observer_id": "sunofriend-parent-observer",
        "observer_sha256": _sha256(b"observer"),
    }
    runtime_artifact = SeparationRuntimeArtifactIdentity(
        path=inputs["launcher"],
        sha256=_sha256(b"runtime launcher"),
        bytes=1024,
        verified_launcher_chain_sha256=_sha256(b"launcher chain"),
    )
    worker_request = build_separation_worker_request(
        preflight=preflight,
        trusted_acceptance=inputs["acceptance"],
        separation_request=separation_request,
        worker_path=inputs["worker"],
        trusted_runtime_artifact=runtime_artifact,
        dependency_lock_path=inputs["dependency_lock"],
        source_bytes=4096,
        checkpoint_bytes=identity["checkpoint"]["bytes"],
        worker_sha256=identity["worker_sha256"],
        worker_bytes=inputs["worker"].stat().st_size,
        runtime_id=identity["runtime"]["runtime_id"],
        runtime_version=identity["runtime"]["runtime_version"],
        python_version=identity["runtime"]["python_version"],
        dependency_lock_sha256=identity["runtime"]["dependency_lock_sha256"],
        dependency_lock_bytes=inputs["dependency_lock"].stat().st_size,
        isolation=isolation,
    )
    trusted_request = bind_separation_checkpoint_inspection_request(
        worker_request,
        trusted_preflight=preflight,
        trusted_acceptance=inputs["acceptance"],
        trusted_separation_request=separation_request,
        trusted_runtime_artifact=runtime_artifact,
    )
    return {
        "inputs": inputs,
        "checkpoint": checkpoint,
        "preflight": preflight,
        "acceptance": inputs["acceptance"],
        "separation_request": separation_request,
        "runtime_artifact": runtime_artifact,
        "worker_request": worker_request,
        "trusted_request": trusted_request,
    }


def inspection_kwargs(fixture: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "trusted_request": fixture["trusted_request"],
        "trusted_preflight": fixture["preflight"],
        "trusted_acceptance": fixture["acceptance"],
        "trusted_separation_request": fixture["separation_request"],
        "trusted_runtime_artifact": fixture["runtime_artifact"],
    }


def inspect_checkpoint(
    fixture: Mapping[str, Any],
) -> SeparationCheckpointInspection:
    return inspect_separation_checkpoint(
        fixture["worker_request"],
        **inspection_kwargs(fixture),
    )
