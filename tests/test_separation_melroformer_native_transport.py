from __future__ import annotations

import copy
import hashlib
import json
import struct
from pathlib import Path

import pytest

import sunofriend._separation_melroformer_native_transport as transport
from sunofriend._separation_checkpoint_canonical import canonical_json_bytes
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)


def _paths() -> dict[str, str]:
    return {
        "repository_root": "/private/tmp/sunofriend-repository",
        "source_root": "/private/tmp/kim-source",
        "checkpoint_path": "/private/tmp/kim-vocal-2.safetensors",
        "companion_root": "/private/tmp/kim-companions",
        "authorisation_report_path": "/private/tmp/authorisation.json",
        "staging_directory": "/private/tmp/kim-native-staging",
    }


def _identities() -> dict[str, object]:
    return {
        "worker_source_sha256": "1" * 64,
        "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
        "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
        "authorisation_report_sha256": "2" * 64,
        "source_manifest_sha256": "3" * 64,
        "companion_manifest_sha256": "4" * 64,
    }


def _request(*, nonce: str = "a" * 64):
    return transport._build_private_melroformer_native_request(
        run_nonce=nonce,
        paths=_paths(),
        identities=_identities(),
        device="gpu",
    )


def _child_result() -> dict[str, object]:
    return {
        "schema": (
            "sunofriend.private-melroformer-authorised-worker-"
            "supervision-child.v1"
        ),
        "status": "complete",
        "quarantine": {
            "outputs": [
                {"role": "vocals", "relative_path": "vocals.wav"},
                {
                    "role": "instrumental",
                    "relative_path": "instrumental.wav",
                },
            ]
        },
    }


def _rehash_request(value: dict[str, object]) -> dict[str, object]:
    payload = copy.deepcopy(value)
    payload.pop("request_sha256", None)
    value["request_sha256"] = hashlib.sha256(
        canonical_json_bytes(payload)
    ).hexdigest()
    return value


def _rehash_result(value: dict[str, object]) -> dict[str, object]:
    payload = copy.deepcopy(value)
    payload.pop("result_sha256", None)
    value["result_sha256"] = hashlib.sha256(
        canonical_json_bytes(payload)
    ).hexdigest()
    return value


def test_request_and_private_result_frames_round_trip_exactly() -> None:
    request = _request()
    request_frame = transport._encode_private_melroformer_native_request(request)
    decoded_request = transport._decode_private_melroformer_native_request(
        request_frame
    )
    result = transport._build_private_melroformer_native_result(
        request=decoded_request,
        private_process_identity={"pid": 101, "pgid": 101},
        child_result=_child_result(),
    )
    result_frame = transport._encode_private_melroformer_native_result(
        result,
        request=decoded_request,
    )
    decoded_result = transport._decode_private_melroformer_native_result(
        result_frame,
        request=decoded_request,
    )

    assert request_frame[:8] == transport.REQUEST_MAGIC
    assert result_frame[:8] == transport.RESULT_MAGIC
    assert decoded_request["descriptor_contract"]["logical_descriptors"] == (
        3,
        4,
        5,
        6,
        7,
    )
    assert decoded_request["authority"] == {
        "serialized_request_is_execution_authority": False,
        "parent_live_native_admission_required": True,
        "publication_permitted": False,
        "automatic_selection_permitted": False,
        "product_route_permitted": False,
    }
    assert decoded_result["private_process_identity"] == {
        "pid": 101,
        "pgid": 101,
    }
    assert decoded_result["paths_retained"] is False
    assert decoded_result["product_authority_granted"] is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("relative_path", "absolute path"),
        ("root_path", "absolute path"),
        ("url_path", "absolute path"),
        ("unnormalized_path", "absolute path"),
        ("control_path", "absolute path"),
        ("duplicate_path", "must be distinct"),
        ("checkpoint_hash", "checkpoint identity"),
        ("checkpoint_bytes", "checkpoint identity"),
        ("descriptor", "descriptor contract"),
        ("authority", "authority differs"),
        ("execution", "execution policy"),
        ("nonce_type", "request identity"),
        ("zero_nonce", "request identity"),
        ("zero_identity", "artifact identity"),
    ],
)
def test_request_rejects_broadened_paths_identities_and_authority(
    mutation: str,
    message: str,
) -> None:
    value = transport._plain(_request())
    if mutation == "relative_path":
        value["paths"]["source_root"] = "relative/source"
    elif mutation == "root_path":
        value["paths"]["source_root"] = "/"
    elif mutation == "url_path":
        value["paths"]["source_root"] = "https://example.invalid/source"
    elif mutation == "unnormalized_path":
        value["paths"]["source_root"] = "/private/tmp/../source"
    elif mutation == "control_path":
        value["paths"]["source_root"] = "/private/tmp/source\nname"
    elif mutation == "duplicate_path":
        value["paths"]["source_root"] = value["paths"]["repository_root"]
    elif mutation == "checkpoint_hash":
        value["identities"]["checkpoint_sha256"] = "f" * 64
    elif mutation == "checkpoint_bytes":
        value["identities"]["checkpoint_bytes"] += 1
    elif mutation == "descriptor":
        value["descriptor_contract"]["ready_write_fd"] = 9
    elif mutation == "authority":
        value["authority"]["product_route_permitted"] = True
    elif mutation == "execution":
        value["execution"]["bind_real_worker_supervision"] = False
    elif mutation == "nonce_type":
        value["run_nonce"] = int("1" * 64)
    elif mutation == "zero_nonce":
        value["run_nonce"] = "0" * 64
    else:
        value["identities"]["worker_source_sha256"] = "0" * 64
    _rehash_request(value)

    with pytest.raises(ValueError, match=message):
        transport._validate_private_melroformer_native_request(value)


@pytest.mark.parametrize("mutation", ["magic", "trailing", "length", "noncanonical", "duplicate"])
def test_request_frame_rejects_boundary_and_canonical_json_failures(
    mutation: str,
) -> None:
    request = transport._plain(_request())
    frame = transport._encode_private_melroformer_native_request(request)
    if mutation == "magic":
        frame = b"INVALID!" + frame[8:]
    elif mutation == "trailing":
        frame += b"x"
    elif mutation == "length":
        frame = frame[:8] + struct.pack(">Q", 1) + frame[16:]
    elif mutation == "noncanonical":
        payload = json.dumps(request, indent=2).encode("ascii")
        frame = struct.pack(">8sQ", transport.REQUEST_MAGIC, len(payload)) + payload
    else:
        payload = frame[16:].replace(
            b'{"authority":',
            b'{"schema":"duplicate","authority":',
            1,
        )
        frame = struct.pack(">8sQ", transport.REQUEST_MAGIC, len(payload)) + payload

    with pytest.raises(ValueError):
        transport._decode_private_melroformer_native_request(frame)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("request_hash", "result identity"),
        ("run_nonce", "result identity"),
        ("pid", "result identity"),
        ("child_hash", "result identity"),
        ("path", "path-free"),
        ("windows_path", "path-free"),
        ("authority", "result identity"),
    ],
)
def test_result_rejects_unbound_identity_paths_and_authority(
    mutation: str,
    message: str,
) -> None:
    request = _request()
    value = transport._plain(
        transport._build_private_melroformer_native_result(
            request=request,
            private_process_identity={"pid": 101, "pgid": 101},
            child_result=_child_result(),
        )
    )
    if mutation == "request_hash":
        value["request_sha256"] = "9" * 64
    elif mutation == "run_nonce":
        value["run_nonce"] = "b" * 64
    elif mutation == "pid":
        value["private_process_identity"]["pid"] = 0
    elif mutation == "child_hash":
        value["child_result_sha256"] = "8" * 64
    elif mutation == "path":
        value["child_result"]["source"] = "/private/tmp/audio.wav"
        value["child_result_sha256"] = hashlib.sha256(
            canonical_json_bytes(value["child_result"])
        ).hexdigest()
    elif mutation == "windows_path":
        value["child_result"]["source"] = "C:\\private\\audio.wav"
        value["child_result_sha256"] = hashlib.sha256(
            canonical_json_bytes(value["child_result"])
        ).hexdigest()
    else:
        value["product_authority_granted"] = True
    _rehash_result(value)

    with pytest.raises(ValueError, match=message):
        transport._validate_private_melroformer_native_result(
            value,
            request=request,
        )


def test_result_is_bound_to_exact_request_nonce() -> None:
    first = _request(nonce="a" * 64)
    second = _request(nonce="b" * 64)
    result = transport._build_private_melroformer_native_result(
        request=first,
        private_process_identity={"pid": 101, "pgid": 101},
        child_result=_child_result(),
    )

    with pytest.raises(ValueError, match="result identity"):
        transport._encode_private_melroformer_native_result(
            result,
            request=second,
        )


def test_transport_module_is_pure_and_has_no_public_route() -> None:
    source_path = (
        Path(__file__).parents[1]
        / "src"
        / "sunofriend"
        / "_separation_melroformer_native_transport.py"
    )
    source = source_path.read_text(encoding="utf-8")

    for forbidden in (
        "import os",
        "import pathlib",
        "import socket",
        "import subprocess",
        "import torch",
        "import mlx",
        "open(",
        "Popen(",
        "posix_spawn(",
    ):
        assert forbidden not in source
    assert "__all__: tuple[str, ...] = ()" in source
