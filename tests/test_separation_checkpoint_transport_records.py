from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from typing import Any, Callable, Mapping

import pytest

from sunofriend._separation_checkpoint_transport_records import (
    SEPARATION_WORKER_REQUEST_V2_EXECUTION_SUPPORTED,
    SEPARATION_WORKER_REQUEST_V2_MAXIMUM_BYTES,
    SEPARATION_WORKER_REQUEST_V2_POLICY_ID,
    SEPARATION_WORKER_REQUEST_V2_SCHEMA,
    SeparationWorkerRequestV2Record,
    build_separation_worker_request_v2_record,
    separation_worker_request_v2_sha256,
    validate_separation_worker_request_v2_record,
)
from sunofriend.separation_launch_contract import _DESCRIPTOR_POLICY


_BINDING_KEYS = (
    "worker_request_sha256",
    "preflight_sha256",
    "acceptance_artifact_sha256",
    "separation_request_fingerprint_sha256",
    "output_allowlist_sha256",
    "execution_admission_binding_sha256",
    "checkpoint_inspection_sha256",
    "checkpoint_classification_evidence_sha256",
    "lease_observation_sha256",
    "checkpoint_sha256",
    "checkpoint_bytes",
    "checkpoint_file_identity_sha256",
    "archive_evidence_sha256",
    "pickle_evidence_sha256",
    "runtime_artifact_sha256",
    "runtime_parent_measurements_sha256",
)
_MINIMUM_ADMISSION_BLOCKERS = {
    "checkpoint_descriptor_not_carried_to_loader",
    "checkpoint_path_to_loader_toctou_unresolved",
    "static_checkpoint_inspection_not_load_authority",
}
_TRANSPORT_BLOCKERS = {
    "validated_v1_projection_facade_not_implemented",
    "source_transport_undefined",
    "output_transport_undefined",
    "worker_protocol_not_implemented",
    "checkpoint_fd5_installation_not_attempted",
    "child_checkpoint_remeasurement_not_implemented",
    "checkpoint_immutable_backing_not_proven",
    "unsafe_executable_pickle_loading_not_authorized",
    "real_execution_unsupported",
}


def _sha(character: str) -> str:
    return character * 64


def _bindings() -> dict[str, Any]:
    return {
        "worker_request_sha256": _sha("1"),
        "preflight_sha256": _sha("2"),
        "acceptance_artifact_sha256": _sha("3"),
        "separation_request_fingerprint_sha256": _sha("4"),
        "output_allowlist_sha256": _sha("5"),
        "execution_admission_binding_sha256": _sha("6"),
        "checkpoint_inspection_sha256": _sha("7"),
        "checkpoint_classification_evidence_sha256": _sha("8"),
        "lease_observation_sha256": _sha("9"),
        "checkpoint_sha256": _sha("a"),
        "checkpoint_bytes": 84_141_911,
        "checkpoint_file_identity_sha256": _sha("b"),
        "archive_evidence_sha256": _sha("c"),
        "pickle_evidence_sha256": None,
        "runtime_artifact_sha256": _sha("d"),
        "runtime_parent_measurements_sha256": _sha("e"),
    }


def _logical_request() -> dict[str, Any]:
    bindings = _bindings()
    checkpoint_id = "muscriptor.large"
    return {
        "preflight": {
            "preflight_id": f"separation-backend-preflight:{_sha('f')}",
            "preflight_sha256": bindings["preflight_sha256"],
            "status": "verified_not_run",
            "arm": {
                "arm_id": "candidate",
                "separator_identity_id": "muscriptor-candidate",
                "backend_id": "muscriptor",
                "package_name": "muscriptor",
                "package_version": "1.0.0",
                "checkpoint_id": checkpoint_id,
                "checkpoint_format": "safetensors",
                "planned_device": {
                    "platform": "macos",
                    "machine": "arm64",
                    "accelerator": "cpu",
                },
                "evaluation_scope": "private-local-evaluation-only",
            },
            "bindings": {
                "preparation_sha256": _sha("4"),
                "acceptance_artifact_sha256": bindings[
                    "acceptance_artifact_sha256"
                ],
                "acceptance_profile_id": "private-local-v1",
                "hidden_manifest_sha256": _sha("5"),
                "hidden_split_sha256": _sha("6"),
            },
        },
        "identities": {
            "source": {
                "source_id": f"sha256:{_sha('7')}",
                "source_sha256": _sha("7"),
                "canonical_sha256": _sha("8"),
                "bytes": 1_058_400,
                "geometry": {
                    "sample_rate": 44_100,
                    "channels": 2,
                    "frames": 88_200,
                    "duration_seconds": 2.0,
                },
            },
            "checkpoint": {
                "checkpoint_id": checkpoint_id,
                "format": "safetensors",
                "sha256": bindings["checkpoint_sha256"],
                "bytes": bindings["checkpoint_bytes"],
            },
            "worker": {"sha256": _sha("9"), "bytes": 8_192},
            "runtime": {
                "runtime_id": "cpython",
                "runtime_version": "3.12.9",
                "python_version": "3.12.9",
                "sha256": _sha("a"),
                "bytes": 3_145_728,
                "verified_launcher_chain_sha256": _sha("b"),
            },
            "dependency_lock": {"sha256": _sha("c"), "bytes": 16_384},
        },
        "roles": ["bass", "drums", "vocals"],
        "settings": {
            "confidence": 0.625,
            "device": "cpu",
            "nested": {"enabled": True, "thresholds": [0.1, 1, None]},
        },
        "seed": 17,
        "isolation": {
            "policy_id": "postinstall-os-deny-and-observe-v1",
            "evidence_scope": "private_development",
            "required_status": "development_enforced_observation_unproven",
            "provider_id": "sandbox-exec",
            "profile_sha256": _sha("d"),
            "environment_sha256": _sha("e"),
            "file_descriptor_policy_sha256": _sha("f"),
            "canary_sha256": _sha("1"),
            "observer_id": "sunofriend-parent-observer",
            "observer_sha256": _sha("2"),
        },
    }


def _blockers() -> list[str]:
    return sorted(
        {
            *_MINIMUM_ADMISSION_BLOCKERS,
            "network_denial_unproven",
            "runtime_closure_incomplete",
        }
    )


def _advisories() -> list[str]:
    return ["checkpoint_review_recommended", "private_evidence_only"]


def _build(
    *,
    bindings: Mapping[str, Any] | None = None,
    logical: Mapping[str, Any] | None = None,
    blockers: list[str] | None = None,
    advisories: list[str] | None = None,
) -> SeparationWorkerRequestV2Record:
    return build_separation_worker_request_v2_record(
        expected_bindings=_bindings() if bindings is None else bindings,
        expected_logical_request=(
            _logical_request() if logical is None else logical
        ),
        expected_admission_blockers=(
            _blockers() if blockers is None else blockers
        ),
        expected_admission_advisories=(
            _advisories() if advisories is None else advisories
        ),
    )


def _validate(
    document: Mapping[str, Any],
    *,
    logical: Mapping[str, Any] | None = None,
) -> SeparationWorkerRequestV2Record:
    return validate_separation_worker_request_v2_record(
        document,
        expected_bindings=_bindings(),
        expected_logical_request=(
            _logical_request() if logical is None else logical
        ),
        expected_admission_blockers=_blockers(),
        expected_admission_advisories=_advisories(),
    )


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _oracle_hash(value: Mapping[str, Any]) -> str:
    document = _plain(value)
    document.pop("request_sha256", None)
    return hashlib.sha256(_canonical(document)).hexdigest()


def _rehash(document: dict[str, Any]) -> None:
    document["request_sha256"] = _oracle_hash(document)


def test_exact_blocked_projection_hash_and_immutability() -> None:
    record = _build()
    document = _plain(record)

    assert type(record) is SeparationWorkerRequestV2Record
    assert document["schema"] == SEPARATION_WORKER_REQUEST_V2_SCHEMA
    assert document["policy_id"] == SEPARATION_WORKER_REQUEST_V2_POLICY_ID
    assert SEPARATION_WORKER_REQUEST_V2_EXECUTION_SUPPORTED is False
    assert document["status"] == "blocked"
    assert document["run_status"] == "not_run"
    assert document["execution_permitted"] is False
    assert document["selection_permitted"] is False
    assert document["request_sha256"] == _oracle_hash(document)
    assert separation_worker_request_v2_sha256(record) == _oracle_hash(
        document
    )
    assert _plain(_validate(record)) == document
    with pytest.raises(TypeError):
        record["status"] = "ready"  # type: ignore[index]
    with pytest.raises(TypeError):
        record["logical_request"]["settings"]["x"] = 1  # type: ignore[index]


def test_v1_request_projection_retains_preflight_and_isolation() -> None:
    logical = _logical_request()
    projected = _plain(_build(logical=logical))["logical_request"]

    assert set(projected) == {
        "preflight",
        "identities",
        "roles",
        "settings",
        "seed",
        "isolation",
    }
    assert projected == logical
    assert set(projected["preflight"]) == {
        "preflight_id",
        "preflight_sha256",
        "status",
        "arm",
        "bindings",
    }
    assert set(projected["isolation"]) == {
        "policy_id",
        "evidence_scope",
        "required_status",
        "provider_id",
        "profile_sha256",
        "environment_sha256",
        "file_descriptor_policy_sha256",
        "canary_sha256",
        "observer_id",
        "observer_sha256",
    }


def test_real_validated_v1_request_fits_the_stricter_v2_projection(
    tmp_path: Path,
) -> None:
    namespace = runpy.run_path(
        str(Path(__file__).with_name("test_separation_worker_contract.py"))
    )
    fixture = namespace["_fixture"](tmp_path)
    request = _plain(fixture["worker_request"])
    bindings = _bindings()
    bindings.update(
        {
            "worker_request_sha256": request["request_sha256"],
            "preflight_sha256": request["preflight"]["preflight_sha256"],
            "acceptance_artifact_sha256": request["preflight"]["bindings"][
                "acceptance_artifact_sha256"
            ],
            "separation_request_fingerprint_sha256": request[
                "separation_request_fingerprint_sha256"
            ],
            "output_allowlist_sha256": hashlib.sha256(
                _canonical(request["output_allowlist"])
            ).hexdigest(),
            "checkpoint_sha256": request["identities"]["checkpoint"][
                "sha256"
            ],
            "checkpoint_bytes": request["identities"]["checkpoint"]["bytes"],
        }
    )
    logical = {
        key: request[key]
        for key in (
            "preflight",
            "identities",
            "roles",
            "settings",
            "seed",
            "isolation",
        )
    }

    projected = _plain(
        build_separation_worker_request_v2_record(
            expected_bindings=bindings,
            expected_logical_request=logical,
            expected_admission_blockers=_blockers(),
            expected_admission_advisories=_advisories(),
        )
    )

    assert projected["logical_request"] == logical
    assert projected["bindings"]["worker_request_sha256"] == request[
        "request_sha256"
    ]
    assert projected["status"] == "blocked"
    assert projected["real_execution_supported"] is False


def test_descriptors_slots_decision_and_permanent_limitations() -> None:
    document = _plain(_build())
    assert document["structure"]["logical_descriptor_requirements"] == [
        {
            "logical_descriptor": 3,
            "purpose": "sealed_path_free_worker_request",
            "direction": "parent_to_worker",
            "access": "read_only",
        },
        {
            "logical_descriptor": 4,
            "purpose": "bounded_path_free_worker_result",
            "direction": "worker_to_parent",
            "access": "write_only",
        },
        {
            "logical_descriptor": 5,
            "purpose": "read_only_checkpoint",
            "direction": "parent_to_worker",
            "access": "read_only",
        },
    ]
    assert document["structure"]["output_slots"] == [
        {
            "role": "bass",
            "artifact_kind": "pcm24_wav",
            "slot_id": "stem-01",
        },
        {
            "role": "drums",
            "artifact_kind": "pcm24_wav",
            "slot_id": "stem-02",
        },
        {
            "role": "vocals",
            "artifact_kind": "pcm24_wav",
            "slot_id": "stem-03",
        },
    ]
    decision = document["decision"]
    assert decision["blocker_sources"] == {
        "admission_binding": _blockers(),
        "transport_v2": sorted(_TRANSPORT_BLOCKERS),
    }
    assert decision["blockers"] == sorted(
        {*_blockers(), *_TRANSPORT_BLOCKERS}
    )
    assert decision["advisories"] == _advisories()
    assert document["limitations"] == [
        "v2_is_blocked_design_evidence_not_a_child_executable_request",
        "v2_record_does_not_prove_expected_input_provenance",
        "v2_is_a_stricter_admitted_and_inspected_v1_subset",
        "future_executable_transport_requires_a_new_request_schema",
        "future_blocked_launch_v2_owns_descriptor_binding_size_and_installation",
        "v2_false_capabilities_are_permanent",
    ]
    assert all(value is False for value in document["capabilities"].values())
    assert all(value is False for value in document["effects"].values())
    assert document["capabilities"]["child_executable_request_supported"] is False


@pytest.mark.parametrize("missing", sorted(_MINIMUM_ADMISSION_BLOCKERS))
def test_each_minimum_admission_blocker_is_required(missing: str) -> None:
    blockers = [item for item in _blockers() if item != missing]
    with pytest.raises(ValueError, match="required inherited"):
        _build(blockers=blockers)


def test_empty_advisories_are_valid_but_empty_blockers_are_not() -> None:
    assert _plain(_build(advisories=[]))["decision"]["advisories"] == []
    with pytest.raises(ValueError, match="required inherited"):
        _build(blockers=[])


@pytest.mark.parametrize("binding_key", _BINDING_KEYS)
def test_each_rehashed_binding_change_is_rejected(binding_key: str) -> None:
    candidate = _plain(_build())
    value = candidate["bindings"][binding_key]
    if binding_key == "checkpoint_bytes":
        replacement: Any = value + 1
    elif binding_key == "pickle_evidence_sha256":
        replacement = _sha("f")
    else:
        replacement = _sha("f") if value != _sha("f") else _sha("e")
    candidate["bindings"][binding_key] = replacement
    _rehash(candidate)
    with pytest.raises(ValueError):
        _validate(candidate)


@pytest.mark.parametrize("binding_key", _BINDING_KEYS)
def test_each_rehashed_binding_removal_is_rejected(binding_key: str) -> None:
    candidate = _plain(_build())
    del candidate["bindings"][binding_key]
    _rehash(candidate)
    with pytest.raises(ValueError, match="fields"):
        _validate(candidate)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["decision"]["blocker_sources"][
            "admission_binding"
        ].append("waived_by_caller"),
        lambda value: value["decision"]["blocker_sources"][
            "admission_binding"
        ].remove("static_checkpoint_inspection_not_load_authority"),
        lambda value: value["decision"].update(
            {"advisories": ["different_advisory"]}
        ),
        lambda value: value["decision"]["blockers"].pop(),
        lambda value: value["decision"]["blocker_sources"][
            "transport_v2"
        ].pop(),
        lambda value: value["limitations"].pop(),
    ],
)
def test_rehashed_decision_or_semantic_edits_are_rejected(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    candidate = _plain(_build())
    mutate(candidate)
    candidate["decision"]["blocker_sources"]["admission_binding"].sort()
    _rehash(candidate)
    with pytest.raises(ValueError):
        _validate(candidate)


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("capabilities", "worker_start_supported"),
        ("capabilities", "checkpoint_loading_supported"),
        ("capabilities", "inference_supported"),
        ("capabilities", "selection_supported"),
        ("capabilities", "publication_supported"),
        ("capabilities", "acceptance_supported"),
        ("capabilities", "promotion_supported"),
        ("capabilities", "child_executable_request_supported"),
        ("effects", "filesystem_accessed"),
        ("effects", "checkpoint_opened"),
        ("effects", "checkpoint_descriptor_retained"),
        ("effects", "checkpoint_lease_reserved"),
        ("effects", "checkpoint_descriptor_installed"),
        ("effects", "checkpoint_loaded"),
        ("effects", "checkpoint_deserialized"),
        ("effects", "inference_started"),
        ("effects", "quarantine_created"),
        ("effects", "publication_permitted"),
        ("effects", "selection_permitted"),
        ("effects", "acceptance_eligible"),
        ("effects", "promotion_eligible"),
    ],
)
def test_rehashed_capability_or_effect_claim_is_rejected(
    section: str,
    field: str,
) -> None:
    candidate = _plain(_build())
    candidate[section][field] = True
    _rehash(candidate)
    with pytest.raises(ValueError, match="false"):
        _validate(candidate)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["structure"][
            "logical_descriptor_requirements"
        ][1].update({"logical_descriptor": 3}),
        lambda value: value["structure"][
            "logical_descriptor_requirements"
        ][1].update({"logical_descriptor": 4.0}),
        lambda value: value["structure"][
            "logical_descriptor_requirements"
        ][0].update({"claim": "retained"}),
        lambda value: value["structure"]["output_slots"][1].update(
            {"slot_id": "stem-01"}
        ),
        lambda value: value["structure"]["output_slots"].append(
            {
                "role": "keys",
                "artifact_kind": "pcm24_wav",
                "slot_id": "stem-04",
            }
        ),
    ],
)
def test_descriptor_rows_slots_collisions_and_extras_are_rejected(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    candidate = _plain(_build())
    mutate(candidate)
    _rehash(candidate)
    with pytest.raises(ValueError):
        _validate(candidate)


def test_model_settings_may_use_fd_and_descriptor_as_music_parameters() -> None:
    logical = _logical_request()
    logical["settings"].update({"fd": 3, "descriptor": 5})
    document = _plain(_build(logical=logical))
    assert document["logical_request"]["settings"]["fd"] == 3
    assert document["logical_request"]["settings"]["descriptor"] == 5


@pytest.mark.parametrize(
    "field",
    [
        "checkpoint_fd",
        "raw_fd",
        "source_fd",
        "file_descriptor",
        "descriptor_number",
    ],
)
def test_descriptor_shaped_model_settings_cannot_claim_transport(
    field: str,
) -> None:
    logical = _logical_request()
    logical["settings"]["nested"][field] = 5
    with pytest.raises(ValueError, match="descriptor"):
        _build(logical=logical)


@pytest.mark.parametrize(
    "raw_key",
    ["fd", "raw_fd", "checkpoint_fd", "file_descriptor", "descriptor"],
)
def test_protocol_owned_raw_descriptor_claims_are_rejected(
    raw_key: str,
) -> None:
    candidate = _plain(_build())
    candidate["structure"][raw_key] = 5
    _rehash(candidate)
    with pytest.raises(ValueError, match="descriptor"):
        _validate(candidate)


@pytest.mark.parametrize(
    ("original", "replacement"),
    [(True, 1), (1, True), (8, 8.0), (8.0, 8)],
)
def test_rehashed_settings_type_substitution_is_rejected(
    original: Any,
    replacement: Any,
) -> None:
    logical = _logical_request()
    logical["settings"]["typed"] = original
    candidate = _plain(_build(logical=logical))
    candidate["logical_request"]["settings"]["typed"] = replacement
    _rehash(candidate)
    with pytest.raises(ValueError, match="expected facade"):
        _validate(candidate, logical=logical)


def test_rehashed_geometry_float_to_int_substitution_is_rejected() -> None:
    candidate = _plain(_build())
    candidate["logical_request"]["identities"]["source"]["geometry"][
        "duration_seconds"
    ] = 2
    _rehash(candidate)
    with pytest.raises(ValueError, match="not canonical"):
        _validate(candidate)


def test_sealed_record_exact_size_boundary_and_overflow() -> None:
    logical = _logical_request()
    logical["settings"]["padding"] = ""
    base = _plain(_build(logical=logical))
    padding = SEPARATION_WORKER_REQUEST_V2_MAXIMUM_BYTES - len(
        _canonical(base)
    )
    assert padding > 0
    logical["settings"]["padding"] = "x" * padding
    boundary = _plain(_build(logical=logical))
    assert len(_canonical(boundary)) == SEPARATION_WORKER_REQUEST_V2_MAXIMUM_BYTES

    logical["settings"]["padding"] += "x"
    with pytest.raises(ValueError, match="maximum bytes"):
        _build(logical=logical)


def test_fd3_size_limit_matches_launch_v1_contract() -> None:
    fd3 = next(
        item
        for item in _DESCRIPTOR_POLICY["descriptors"]
        if item["descriptor"] == 3
    )
    assert fd3["maximum_bytes"] == SEPARATION_WORKER_REQUEST_V2_MAXIMUM_BYTES


def test_self_hash_excludes_only_request_sha256() -> None:
    document = _plain(_build())
    original = separation_worker_request_v2_sha256(document)
    document["request_sha256"] = _sha("f")
    assert separation_worker_request_v2_sha256(document) == original
    document["additional_claim"] = False
    assert separation_worker_request_v2_sha256(document) != original
    document["request_sha256"] = separation_worker_request_v2_sha256(
        document
    )
    with pytest.raises(ValueError, match="fields"):
        _validate(document)
