from __future__ import annotations

import ast
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import pytest
import sunofriend._separation_checkpoint_launch_v2_records as records_module

from sunofriend._separation_checkpoint_launch_v2_records import (
    _FD5_REQUIRED_SEQUENCE,
    _LAUNCH_V2_BLOCKERS,
    _REQUEST_BINDING_FIELDS,
    _SEALED_BUT_UNPROVEN_BINDINGS,
    _SEPARATION_LAUNCH_PLAN_V2_MAXIMUM_BYTES,
    _SEPARATION_LAUNCH_PLAN_V2_SCHEMA,
    _SeparationLaunchPlanV2Record,
    _build_blocked_separation_launch_plan_v2_record,
    _separation_launch_plan_v2_sha256,
    _validate_blocked_separation_launch_plan_v2_record_shape,
)
from tests.test_separation_checkpoint_transport_records import (
    _build as _worker_request_v2,
)


SOURCE = (
    Path(__file__).parents[1]
    / "src"
    / "sunofriend"
    / "_separation_checkpoint_launch_v2_records.py"
)
_GOLDEN_PLAN_SHA256 = (
    "6be121486e087de5decdb24a2adb62bf2f992acaae7a9457208ea1b5d2401505"
)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _plan() -> _SeparationLaunchPlanV2Record:
    return _build_blocked_separation_launch_plan_v2_record(
        worker_request_v2=_worker_request_v2()
    )


def _canonical(value: Any) -> bytes:
    return json.dumps(
        _plain(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def test_exact_schema_hash_and_deep_immutability() -> None:
    plan = _plan()

    assert type(plan) is _SeparationLaunchPlanV2Record
    assert plan["schema"] == _SEPARATION_LAUNCH_PLAN_V2_SCHEMA
    assert plan["status"] == "blocked"
    assert plan["run_status"] == "not_run"
    assert plan["real_execution_supported"] is False
    assert plan["execution_permitted"] is False
    assert plan["worker_start_permitted"] is False
    assert plan["descriptor_installation_permitted"] is False
    assert plan["plan_sha256"] == _GOLDEN_PLAN_SHA256
    assert plan["plan_sha256"] == _separation_launch_plan_v2_sha256(plan)
    assert len(_canonical(plan)) <= _SEPARATION_LAUNCH_PLAN_V2_MAXIMUM_BYTES
    assert isinstance(plan._document, MappingProxyType)
    assert isinstance(plan["bindings"], MappingProxyType)
    assert isinstance(plan["decision"]["blockers"], tuple)

    with pytest.raises(TypeError):
        plan["status"] = "ready"  # type: ignore[index]
    with pytest.raises(TypeError):
        plan["bindings"]["checkpoint_bytes"] = 1  # type: ignore[index]
    with pytest.raises(AttributeError):
        plan["decision"]["blockers"].append("ready")

    assert _validate_blocked_separation_launch_plan_v2_record_shape(plan) is plan
    with pytest.raises(ValueError, match="exact validated record"):
        _validate_blocked_separation_launch_plan_v2_record_shape(_plain(plan))


def test_all_request_bindings_are_sealed_with_explicit_authority_boundary() -> None:
    request = _worker_request_v2()
    plan = _build_blocked_separation_launch_plan_v2_record(
        worker_request_v2=request
    )
    bindings = plan["bindings"]

    assert set(bindings) == {
        *_REQUEST_BINDING_FIELDS,
        "worker_request_v2_sha256",
        "worker_request_v2_bindings_sha256",
    }
    for key in _REQUEST_BINDING_FIELDS:
        assert bindings[key] == request["bindings"][key]
    assert bindings["worker_request_v2_sha256"] == request["request_sha256"]
    assert plan["binding_authority"]["sealed_but_unproven"] == (
        _SEALED_BUT_UNPROVEN_BINDINGS
    )
    requirements = plan["binding_authority"][
        "lease_facade_cross_binding_requirements"
    ]
    assert set(requirements) == (
        _REQUEST_BINDING_FIELDS - set(_SEALED_BUT_UNPROVEN_BINDINGS)
    )
    assert set(requirements).isdisjoint(_SEALED_BUT_UNPROVEN_BINDINGS)


def test_construction_requirements_serialize_no_claimed_authority() -> None:
    plan = _plan()
    requirements = plan["construction_requirements"]

    assert requirements == {
        "authority_scope": "requirements_only_not_proven_by_record",
        "exact_worker_request_v2_required": True,
        "exact_reservation_required": True,
        "lease_remeasurement_under_lock_required": True,
        "conditions_proven_by_serialized_record": False,
        "reservation_authority_serialized": False,
        "authorizes_descriptor_installation": False,
        "authorizes_worker_start": False,
        "authorizes_execution": False,
    }
    assert not hasattr(plan, "_reservation")
    assert not hasattr(plan, "_lease")
    assert "reservation object" not in json.dumps(_plain(plan))


def test_logical_descriptor_design_is_fixed_and_not_installed() -> None:
    plan = _plan()
    design = plan["logical_descriptor_design"]
    rows = design["logical_descriptors"]

    assert [row["logical_descriptor"] for row in rows] == [3, 4, 5]
    assert [row["purpose"] for row in rows] == [
        "sealed_path_free_worker_request",
        "bounded_path_free_worker_result",
        "read_only_checkpoint",
    ]
    assert design["inherit_unlisted_descriptors"] is False
    assert design["raw_descriptor_values_serialized"] is False
    assert rows[0]["state"] == "transport_undefined_not_materialized"
    assert rows[1]["state"] == "transport_undefined_not_created"
    assert rows[2]["state"] == "reserved_not_installed"
    assert rows[2]["expected_bytes"] == plan["bindings"]["checkpoint_bytes"]


def test_fd5_design_requires_atomic_child_creation_without_attempting_it() -> None:
    design = _plan()["checkpoint_fd5_installation_design"]

    assert design["status"] == "design_only_not_implemented"
    assert design["run_status"] == "not_run"
    assert design["target_logical_descriptor"] == 5
    assert design["parent_checkpoint_path_reopened"] is False
    assert design["parent_descriptor_table_mutated"] is False
    assert design["installation_implemented"] is False
    assert design["installation_attempted"] is False
    assert design["atomicity_boundary"] == (
        "lease_lock_through_child_creation_result"
    )
    assert design["installation_mechanism"] == (
        "single_child_creation_file_action"
    )
    assert design["required_sequence"] == _FD5_REQUIRED_SEQUENCE
    assert "allocate_collision_free_staging_descriptors" in (
        design["required_sequence"]
    )
    assert (
        "require_offset_independent_child_reader_or_serialized_offset_protocol"
        in design["required_sequence"]
    )
    assert "verify_child_fd5_full_hash_before_deserialization" in (
        design["required_sequence"]
    )
    assert "set_child_fd5_noninheritable_immediately_after_exec" in (
        design["required_sequence"]
    )
    assert design["required_sequence"].index(
        "set_child_fd5_noninheritable_immediately_after_exec"
    ) < design["required_sequence"].index(
        "verify_child_fd5_read_only_before_checkpoint_read"
    )


def test_every_capability_effect_and_permission_remains_false() -> None:
    plan = _plan()

    assert plan["capabilities"]
    assert plan["effects"]
    assert all(value is False for value in plan["capabilities"].values())
    assert all(value is False for value in plan["effects"].values())
    assert set(_LAUNCH_V2_BLOCKERS).issubset(
        plan["decision"]["blockers"]
    )
    assert set(_worker_request_v2()["decision"]["blockers"]).issubset(
        plan["decision"]["blockers"]
    )
    assert plan["decision"]["blocker_sources"]["launch_plan_v2"] == tuple(
        sorted(_LAUNCH_V2_BLOCKERS)
    )


@pytest.mark.parametrize(
    ("location", "key", "value", "message"),
    [
        ((), "schema", "sunofriend.separation-launch-plan.v3", "unsupported"),
        ((), "execution_permitted", True, "blocked and not run"),
        (
            ("construction_requirements",),
            "reservation_authority_serialized",
            True,
            "construction requirements",
        ),
        (
            ("logical_descriptor_design",),
            "raw_descriptor_values_serialized",
            True,
            "descriptor design",
        ),
        (
            ("checkpoint_fd5_installation_design",),
            "installation_attempted",
            True,
            "installation design",
        ),
        (
            ("bindings",),
            "checkpoint_bytes",
            True,
            "checkpoint bytes",
        ),
        (
            ("capabilities",),
            "process_start_supported",
            True,
            "must all be false",
        ),
        (
            ("effects",),
            "checkpoint_descriptor_installed",
            True,
            "must all be false",
        ),
    ],
)
def test_tampering_and_type_substitution_fail_closed(
    location: tuple[str, ...],
    key: str,
    value: Any,
    message: str,
) -> None:
    plan = _plan()
    document = _plain(plan)
    target = document
    for component in location:
        target = target[component]
    target[key] = value
    document["plan_sha256"] = _separation_launch_plan_v2_sha256(document)
    object.__setattr__(plan, "_document", document)

    with pytest.raises(ValueError, match=message):
        _validate_blocked_separation_launch_plan_v2_record_shape(plan)


def test_self_hash_tamper_and_size_bound_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    document = _plain(plan)
    document["plan_sha256"] = "0" * 64
    object.__setattr__(plan, "_document", document)
    with pytest.raises(ValueError, match="hash is invalid"):
        _validate_blocked_separation_launch_plan_v2_record_shape(plan)

    monkeypatch.setattr(
        records_module,
        "_SEPARATION_LAUNCH_PLAN_V2_MAXIMUM_BYTES",
        1,
    )
    with pytest.raises(ValueError, match="maximum bytes"):
        _plan()


def test_record_is_path_free_and_contains_no_raw_descriptor_or_argv() -> None:
    document = _plain(_plan())

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                assert key not in {
                    "argv",
                    "checkpoint_fd",
                    "descriptor",
                    "file_descriptor",
                    "raw_descriptor",
                    "raw_fd",
                    "reservation",
                    "reservation_authority",
                }
                assert not key.endswith("_path")
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            assert "/" not in value
            assert "\\" not in value

    walk(document)


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def test_module_has_no_execution_installation_loader_or_public_surface() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    forbidden_imports = {
        "asyncio",
        "ctypes",
        "fcntl",
        "http",
        "importlib",
        "multiprocessing",
        "os",
        "pickle",
        "requests",
        "runpy",
        "safetensors",
        "socket",
        "subprocess",
        "torch",
        "urllib",
    }
    forbidden_calls = {
        "__import__",
        "compile",
        "dup",
        "dup2",
        "eval",
        "exec",
        "fork",
        "forkpty",
        "load",
        "loads",
        "open",
        "popen",
        "posix_spawn",
        "posix_spawnp",
        "set_inheritable",
        "spawn",
        "system",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {
                alias.name.split(".", 1)[0] for alias in node.names
            } & forbidden_imports
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".", 1)[0] not in forbidden_imports
        elif isinstance(node, ast.Call):
            qualified = _qualified_name(node.func)
            assert (
                qualified.rsplit(".", 1)[-1] not in forbidden_calls
                or qualified == "re.compile"
            )
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            assert node.name.startswith("_")

    assert records_module.__all__ == []
