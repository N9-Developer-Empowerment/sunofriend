from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Callable

import pytest
import sunofriend._separation_checkpoint_transport_records as records_module
import sunofriend._separation_worker_request_v2_values as values_module

from sunofriend._separation_worker_request_v2_values import (
    _BINDING_FIELDS,
    _CHECKPOINT_FORMATS,
    _MAX_CHECKPOINT_BYTES,
    _MAX_JSON_DEPTH,
    _MAX_JSON_ITEMS,
    _PREPARED_ROLE_IDS,
    _bounded_json_copy,
    _validated_bindings,
    _validated_logical_request,
)
from sunofriend.separation_checkpoint_inspection import (
    MAX_CHECKPOINT_BYTES,
)
from sunofriend.source_roles import prepared_source_role_ids


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


def _validate(logical: dict[str, Any] | None = None) -> dict[str, Any]:
    return _validated_logical_request(
        _logical_request() if logical is None else logical,
        bindings=_validated_bindings(_bindings()),
    )


def test_exact_binding_vocabulary_and_nullable_pickle() -> None:
    assert set(_bindings()) == _BINDING_FIELDS
    assert len(_BINDING_FIELDS) == 16
    assert _validated_bindings(_bindings())["pickle_evidence_sha256"] is None
    bindings = _bindings()
    bindings["pickle_evidence_sha256"] = _sha("f")
    assert (
        _validated_bindings(bindings)["pickle_evidence_sha256"] == _sha("f")
    )


@pytest.mark.parametrize(
    "bad_bytes", [True, False, 0, _MAX_CHECKPOINT_BYTES + 1]
)
def test_checkpoint_binding_bytes_are_strict_and_bounded(
    bad_bytes: Any,
) -> None:
    bindings = _bindings()
    bindings["checkpoint_bytes"] = bad_bytes
    with pytest.raises(ValueError, match="integer|bounds"):
        _validated_bindings(bindings)


@pytest.mark.parametrize("missing", sorted(_BINDING_FIELDS))
def test_each_missing_binding_is_rejected(missing: str) -> None:
    bindings = _bindings()
    del bindings[missing]
    with pytest.raises(ValueError, match="fields"):
        _validated_bindings(bindings)


def test_extra_binding_is_rejected() -> None:
    bindings = _bindings()
    bindings["extra_sha256"] = _sha("f")
    with pytest.raises(ValueError, match="fields"):
        _validated_bindings(bindings)


@pytest.mark.parametrize(
    "value",
    ["C:maj", "D:min", "profile:cpu", "metadata:value", ".5", ".hidden"],
)
def test_music_semantic_strings_are_not_misclassified_as_paths(
    value: str,
) -> None:
    logical = _logical_request()
    logical["settings"]["music_value"] = value
    assert _validate(logical)["settings"]["music_value"] == value


@pytest.mark.parametrize(
    "value",
    [
        "/private/tmp/checkpoint.pt",
        "relative/checkpoint.pt",
        r"relative\checkpoint.pt",
        r"C:\Models\checkpoint.pt",
        r"C:/Models/checkpoint.pt",
        r"\\server\share",
        ".",
        "..",
        "../checkpoint.pt",
        "./checkpoint.pt",
        "https://example.invalid/checkpoint.pt",
        "ftp://example.invalid/item",
        "file:checkpoint.pt",
        "mailto:user@example.invalid",
        "data:text/plain,item",
        "www.example.invalid",
        "bad\x00value",
        "bad\nvalue",
        " leading",
        "trailing ",
    ],
)
def test_actual_paths_urls_controls_and_noncanonical_values_are_rejected(
    value: str,
) -> None:
    logical = _logical_request()
    logical["settings"]["unsafe"] = value
    with pytest.raises(ValueError, match="path|URL|canonical"):
        _validate(logical)


@pytest.mark.parametrize(
    "key",
    [
        "path",
        "paths",
        "relative_path",
        "checkpoint_path",
        "checkpoint_paths",
        "bad/key",
        "bad\\key",
        " bad",
        "bad ",
        "bad\x00key",
    ],
)
def test_recursive_path_and_noncanonical_keys_are_rejected(key: str) -> None:
    logical = _logical_request()
    logical["settings"]["nested"][key] = "safe"
    with pytest.raises(ValueError, match="path|canonical"):
        _validate(logical)


def test_model_fd_and_descriptor_settings_remain_valid_json_values() -> None:
    logical = _logical_request()
    logical["settings"].update({"fd": 3, "descriptor": 5})
    checked = _validate(logical)
    assert checked["settings"]["fd"] == 3
    assert checked["settings"]["descriptor"] == 5


@pytest.mark.parametrize(
    "roles",
    [
        ["vocals", "bass"],
        ["bass", "bass"],
        ["bass", "not_a_prepared_role"],
        [],
        "bass",
    ],
)
def test_roles_are_sorted_unique_prepared_ids(roles: Any) -> None:
    logical = _logical_request()
    logical["roles"] = roles
    with pytest.raises(ValueError, match="roles"):
        _validate(logical)


def test_frozen_role_vocabulary_matches_v1_prepared_roles() -> None:
    assert _PREPARED_ROLE_IDS == prepared_source_role_ids()


@pytest.mark.parametrize("checkpoint_format", sorted(_CHECKPOINT_FORMATS))
def test_every_v1_worker_checkpoint_format_is_accepted(
    checkpoint_format: str,
) -> None:
    logical = _logical_request()
    logical["identities"]["checkpoint"]["format"] = checkpoint_format
    logical["preflight"]["arm"]["checkpoint_format"] = checkpoint_format
    assert (
        _validate(logical)["identities"]["checkpoint"]["format"]
        == checkpoint_format
    )


def test_checkpoint_format_and_maximum_match_v1_inspection_contract() -> None:
    assert _CHECKPOINT_FORMATS == {
        "coreml",
        "onnx",
        "safetensors",
        "torch-state-dict",
    }
    assert _MAX_CHECKPOINT_BYTES == MAX_CHECKPOINT_BYTES


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("sample_rate", True),
        ("sample_rate", 0),
        ("sample_rate", 768_001),
        ("channels", 0),
        ("channels", 65),
        ("frames", 0),
        ("duration_seconds", "2.0"),
        ("duration_seconds", 3.0),
    ],
)
def test_geometry_types_bounds_and_clock_match_are_enforced(
    field: str,
    bad: Any,
) -> None:
    logical = _logical_request()
    logical["identities"]["source"]["geometry"][field] = bad
    with pytest.raises(ValueError):
        _validate(logical)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_settings_and_geometry_are_rejected(bad: float) -> None:
    logical = _logical_request()
    logical["settings"]["bad"] = bad
    with pytest.raises(ValueError):
        _validate(logical)
    logical = _logical_request()
    logical["identities"]["source"]["geometry"]["duration_seconds"] = bad
    with pytest.raises(ValueError):
        _validate(logical)


def test_finite_floats_are_retained_and_geometry_is_normalized() -> None:
    logical = _logical_request()
    logical["settings"].update({"small": 1e-12, "negative": -1.25})
    logical["identities"]["source"]["geometry"]["duration_seconds"] = 2
    checked = _validate(logical)
    assert checked["settings"]["small"] == 1e-12
    assert checked["settings"]["negative"] == -1.25
    assert (
        type(
            checked["identities"]["source"]["geometry"]["duration_seconds"]
        )
        is float
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["preflight"].update({"status": "blocked"}),
        lambda value: value["preflight"].update(
            {"preflight_id": "preflight"}
        ),
        lambda value: value["preflight"].update(
            {"preflight_sha256": _sha("3")}
        ),
        lambda value: value["preflight"]["arm"].update(
            {"arm_id": "other"}
        ),
        lambda value: value["preflight"]["arm"].update(
            {"checkpoint_id": "other.checkpoint"}
        ),
        lambda value: value["preflight"]["arm"].update(
            {"checkpoint_format": "none"}
        ),
        lambda value: value["preflight"]["arm"]["planned_device"].update(
            {"platform": "linux"}
        ),
        lambda value: value["preflight"]["bindings"].update(
            {"acceptance_artifact_sha256": _sha("4")}
        ),
        lambda value: value["preflight"].update({"extra": False}),
    ],
)
def test_preflight_projection_fields_and_cross_bindings_are_exact(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    logical = _logical_request()
    mutate(logical)
    with pytest.raises(ValueError):
        _validate(logical)


@pytest.mark.parametrize(
    ("location", "key"),
    [
        (("preflight",), "preflight_sha256"),
        (("preflight", "bindings"), "preparation_sha256"),
        (("preflight", "bindings"), "acceptance_artifact_sha256"),
        (("preflight", "bindings"), "hidden_manifest_sha256"),
        (("preflight", "bindings"), "hidden_split_sha256"),
    ],
)
def test_v1_preflight_hashes_must_not_be_all_zero(
    location: tuple[str, ...],
    key: str,
) -> None:
    logical = _logical_request()
    target = logical
    for part in location:
        target = target[part]
    target[key] = _sha("0")
    if key == "preflight_sha256":
        bindings = _bindings()
        bindings["preflight_sha256"] = _sha("0")
        with pytest.raises(ValueError, match="verified report"):
            _validated_logical_request(
                logical, bindings=_validated_bindings(bindings)
            )
    else:
        with pytest.raises(ValueError, match="all-zero"):
            _validate(logical)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["isolation"].update(
            {"policy_id": "other-policy"}
        ),
        lambda value: value["isolation"].update(
            {"evidence_scope": "public"}
        ),
        lambda value: value["isolation"].update(
            {"required_status": "complete"}
        ),
        lambda value: value["isolation"].update(
            {"provider_id": "Bad Provider"}
        ),
        lambda value: value["isolation"].update(
            {"profile_sha256": "A" * 64}
        ),
        lambda value: value["isolation"].update({"extra": False}),
    ],
)
def test_isolation_projection_is_exact(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    logical = _logical_request()
    mutate(logical)
    with pytest.raises(ValueError):
        _validate(logical)


def test_bounded_json_copy_rejects_depth_before_recursion_error() -> None:
    value: dict[str, Any] = {}
    cursor = value
    for _ in range(_MAX_JSON_DEPTH + 2):
        child: dict[str, Any] = {}
        cursor["nested"] = child
        cursor = child
    with pytest.raises(ValueError, match="depth"):
        _bounded_json_copy(value, "deep value")


def test_bounded_json_copy_rejects_excessive_item_count() -> None:
    value = [0] * (_MAX_JSON_ITEMS + 1)
    with pytest.raises(ValueError, match="items"):
        _bounded_json_copy(value, "wide value")


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


@pytest.mark.parametrize(
    ("module", "expected_imports"),
    [
        (
            records_module,
            {
                (0, "__future__"),
                (0, "re"),
                (0, "dataclasses"),
                (0, "typing"),
                (1, "_separation_checkpoint_canonical"),
                (1, "_separation_worker_request_v2_values"),
            },
        ),
        (
            values_module,
            {
                (0, "__future__"),
                (0, "math"),
                (0, "re"),
                (0, "typing"),
                (1, "_separation_checkpoint_canonical"),
            },
        ),
    ],
)
def test_v2_modules_have_exact_pure_imports_and_no_authority(
    module: Any,
    expected_imports: set[tuple[int, str]],
) -> None:
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[tuple[int, str]] = set()
    forbidden_calls = {
        "__import__",
        "compile",
        "eval",
        "exec",
        "open",
        "os.open",
        "os.posix_spawn",
        "os.system",
        "Path.open",
        "Path.read_bytes",
        "Path.read_text",
        "subprocess.Popen",
        "subprocess.run",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update((0, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add((node.level, node.module or ""))
        elif isinstance(node, ast.Call):
            assert _qualified_name(node.func) not in forbidden_calls
    assert imports == expected_imports
    assert "trusted_" not in source


def test_v1_production_contracts_do_not_import_v2_modules() -> None:
    root = Path(records_module.__file__).parent
    for filename in (
        "separation_worker_contract.py",
        "separation_launch_contract.py",
        "separation_execution_admission_binding.py",
    ):
        source = (root / filename).read_text(encoding="utf-8")
        assert "_separation_checkpoint_transport_records" not in source
        assert "_separation_worker_request_v2_values" not in source
