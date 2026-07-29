from __future__ import annotations

import copy
import hashlib
import json
import os
import runpy
from pathlib import Path
from typing import Any

import pytest

from sunofriend.separation_acceptance import (
    canonical_json_bytes,
    separation_acceptance_artifact_sha256,
)
from sunofriend.separation_bakeoff import (
    SEPARATION_BAKEOFF_PREPARATION_SCHEMA,
    load_separation_bakeoff_preparation,
    prepare_separation_bakeoff,
    separation_bakeoff_preparation_sha256,
    validate_separation_bakeoff_preparation,
)


def _inputs(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    namespace = runpy.run_path(
        str(Path(__file__).with_name("test_separation_acceptance.py"))
    )
    acceptance, manifest = namespace["_fixture"]()
    acceptance_path = tmp_path / "acceptance.json"
    manifest_path = tmp_path / "hidden-manifest.json"
    acceptance_path.write_bytes(canonical_json_bytes(acceptance))
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    return acceptance_path, manifest_path, manifest


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _all_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict) or hasattr(value, "items"):
        for key, item in value.items():
            strings.append(str(key))
            strings.extend(_all_strings(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            strings.extend(_all_strings(item))
    return strings


def _all_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict) or hasattr(value, "items"):
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_all_keys(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys.extend(_all_keys(item))
    return keys


def _reidentify(document: dict[str, Any]) -> None:
    identity_payload = {
        "schema": document["schema"],
        "status": document["status"],
        "acceptance": document["acceptance"],
        "hidden_evaluation": document["hidden_evaluation"],
        "orchestration": document["orchestration"],
        "effects": document["effects"],
    }
    document["preparation_id"] = (
        "separation-bakeoff-preparation:"
        + hashlib.sha256(canonical_json_bytes(identity_payload)).hexdigest()
    )
    document["preparation_sha256"] = (
        separation_bakeoff_preparation_sha256(document)
    )


def test_prepare_is_deterministic_redacted_and_deeply_immutable(
    tmp_path: Path,
) -> None:
    acceptance_path, manifest_path, manifest = _inputs(tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())
    acceptance_before = acceptance_path.read_bytes()
    manifest_before = manifest_path.read_bytes()
    first = prepare_separation_bakeoff(
        acceptance_path=acceptance_path,
        hidden_manifest_path=manifest_path,
    )
    second = prepare_separation_bakeoff(
        acceptance_path=acceptance_path,
        hidden_manifest_path=manifest_path,
    )
    after = sorted(path.name for path in tmp_path.iterdir())

    assert before == after
    assert acceptance_path.read_bytes() == acceptance_before
    assert manifest_path.read_bytes() == manifest_before
    assert _plain(first) == _plain(second)
    assert first["schema"] == SEPARATION_BAKEOFF_PREPARATION_SCHEMA
    assert first["status"] == "prepared_not_run"
    assert [arm["arm_id"] for arm in first["orchestration"]["arms"]] == [
        "baseline",
        "candidate",
    ]
    assert all(value is False for value in first["effects"].values())
    with pytest.raises(TypeError):
        first["status"] = "run"  # type: ignore[index]
    with pytest.raises(TypeError):
        first["effects"]["model_executed"] = True  # type: ignore[index]
    assert isinstance(first["orchestration"]["arms"], tuple)

    private_values: set[str] = set()
    for song in manifest["songs"]:
        private_values.update(
            {
                song["song_id"],
                song["song_identity_sha256"],
                song["source_sha256"],
                song["rights_profile_id"],
                song["rights_evidence_sha256"],
            }
        )
        private_values.update(
            role["ground_truth_sha256"] for role in song["roles"]
        )
    exposed = set(_all_strings(first))
    assert not private_values.intersection(exposed)
    assert not any(
        private_value in exposed_value
        for private_value in private_values
        for exposed_value in exposed
    )
    assert str(acceptance_path) not in exposed
    assert str(manifest_path) not in exposed
    exposed_keys = set(_all_keys(first))
    assert not exposed_keys.intersection(
        {"scores", "results", "thresholds", "private_notes"}
    )


def test_preparation_binds_complete_acceptance_and_redacted_manifest_facts(
    tmp_path: Path,
) -> None:
    acceptance_path, manifest_path, _manifest = _inputs(tmp_path)
    prepared = prepare_separation_bakeoff(
        acceptance_path=acceptance_path,
        hidden_manifest_path=manifest_path,
    )
    acceptance_bytes = acceptance_path.read_bytes()
    assert prepared["acceptance"]["canonical_document_sha256"] == (
        hashlib.sha256(acceptance_bytes).hexdigest()
    )
    assert prepared["hidden_evaluation"]["total_songs"] == 12
    assert prepared["hidden_evaluation"]["groups"] == {
        "acoustic": 4,
        "electronic_ai_generated": 4,
        "mixed": 4,
    }
    assert prepared["hidden_evaluation"][
        "ground_truth_pairs_by_role"
    ] == {
        "role-prepared:bass": 12,
        "role-prepared:kick": 12,
    }


def test_hash_excludes_only_self_hash_and_detects_tamper(
    tmp_path: Path,
) -> None:
    acceptance_path, manifest_path, _manifest = _inputs(tmp_path)
    prepared = _plain(
        prepare_separation_bakeoff(
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    )
    original = prepared["preparation_sha256"]
    prepared["preparation_sha256"] = hashlib.sha256(b"other").hexdigest()
    assert separation_bakeoff_preparation_sha256(prepared) == original
    with pytest.raises(ValueError, match="preparation_sha256"):
        validate_separation_bakeoff_preparation(
            prepared,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )


def test_validate_reloads_inputs_and_rejects_forged_bound_identity(
    tmp_path: Path,
) -> None:
    acceptance_path, manifest_path, _manifest = _inputs(tmp_path)
    prepared = _plain(
        prepare_separation_bakeoff(
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    )
    prepared["orchestration"]["arms"][1][
        "separator_identity_id"
    ] = "forged-candidate"
    _reidentify(prepared)
    with pytest.raises(ValueError, match="reverified frozen inputs"):
        validate_separation_bakeoff_preparation(
            prepared,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )


def test_validate_always_reverifies_acceptance_and_manifest(
    tmp_path: Path,
) -> None:
    acceptance_path, manifest_path, manifest = _inputs(tmp_path)
    prepared = prepare_separation_bakeoff(
        acceptance_path=acceptance_path,
        hidden_manifest_path=manifest_path,
    )
    acceptance_document = json.loads(
        acceptance_path.read_text(encoding="utf-8")
    )
    acceptance_document["status"] = "passed"
    acceptance_path.write_bytes(canonical_json_bytes(acceptance_document))
    with pytest.raises(ValueError):
        validate_separation_bakeoff_preparation(
            prepared,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )

    acceptance_path, manifest_path, manifest = _inputs(tmp_path / "second")
    prepared = prepare_separation_bakeoff(
        acceptance_path=acceptance_path,
        hidden_manifest_path=manifest_path,
    )
    manifest["songs"][0]["group"] = "mixed"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(ValueError):
        validate_separation_bakeoff_preparation(
            prepared,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )


def test_effects_are_exhaustive_exact_and_always_false(
    tmp_path: Path,
) -> None:
    acceptance_path, manifest_path, _manifest = _inputs(tmp_path)
    prepared = _plain(
        prepare_separation_bakeoff(
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    )
    expected = {
        "audio_read",
        "audio_written",
        "automatic_defaults_changed",
        "candidate_selected",
        "checkpoint_downloaded",
        "checkpoint_loaded",
        "files_written",
        "hidden_scores_read",
        "inference_started",
        "inference_executed",
        "metrics_computed",
        "model_downloaded",
        "model_executed",
        "model_loaded",
        "network_used",
        "private_metadata_exposed",
        "promotion_decided",
        "results_read",
        "roles_selected",
        "scores_read",
        "threshold_values_exposed",
        "worker_started",
    }
    assert set(prepared["effects"]) == expected
    prepared["effects"]["worker_started"] = True
    _reidentify(prepared)
    with pytest.raises(ValueError, match="must be false"):
        validate_separation_bakeoff_preparation(
            prepared,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    prepared = _plain(
        prepare_separation_bakeoff(
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    )
    prepared["effects"]["model_executed"] = 0
    _reidentify(prepared)
    with pytest.raises(ValueError, match="must be false"):
        validate_separation_bakeoff_preparation(
            prepared,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )


def test_arm_role_resource_and_gate_order_is_strict(
    tmp_path: Path,
) -> None:
    acceptance_path, manifest_path, _manifest = _inputs(tmp_path)
    prepared = _plain(
        prepare_separation_bakeoff(
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    )
    prepared["orchestration"]["arms"].reverse()
    _reidentify(prepared)
    with pytest.raises(ValueError, match="baseline before candidate"):
        validate_separation_bakeoff_preparation(
            prepared,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    prepared = _plain(
        prepare_separation_bakeoff(
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    )
    prepared["orchestration"]["gate_ids"].reverse()
    _reidentify(prepared)
    with pytest.raises(ValueError, match="fixed conjunction"):
        validate_separation_bakeoff_preparation(
            prepared,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    prepared = _plain(
        prepare_separation_bakeoff(
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    )
    prepared["orchestration"]["role_prepared_ids"].reverse()
    _reidentify(prepared)
    with pytest.raises(ValueError, match="roles must be sorted and unique"):
        validate_separation_bakeoff_preparation(
            prepared,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    prepared = _plain(
        prepare_separation_bakeoff(
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    )
    prepared["orchestration"]["resource_class_ids"].append(
        prepared["orchestration"]["resource_class_ids"][0]
    )
    _reidentify(prepared)
    with pytest.raises(
        ValueError, match="resource class IDs must be sorted and unique"
    ):
        validate_separation_bakeoff_preparation(
            prepared,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )


def test_unknown_fields_status_and_bool_as_count_fail_closed(
    tmp_path: Path,
) -> None:
    acceptance_path, manifest_path, _manifest = _inputs(tmp_path)
    prepared = _plain(
        prepare_separation_bakeoff(
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    )
    prepared["result"] = "passed"
    _reidentify(prepared)
    with pytest.raises(ValueError, match="fields are invalid"):
        validate_separation_bakeoff_preparation(
            prepared,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    prepared = _plain(
        prepare_separation_bakeoff(
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    )
    prepared["hidden_evaluation"]["total_songs"] = True
    _reidentify(prepared)
    with pytest.raises(ValueError, match="positive integer"):
        validate_separation_bakeoff_preparation(
            prepared,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    prepared = _plain(
        prepare_separation_bakeoff(
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    )
    prepared["orchestration"]["arms"][0]["order"] = True
    _reidentify(prepared)
    with pytest.raises(ValueError, match="positive integer"):
        validate_separation_bakeoff_preparation(
            prepared,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )


@pytest.mark.parametrize(
    "private_value",
    [
        "/Users/alice/private/model",
        "https://secret.example/private",
        "file:/Users/alice/private",
        "C:\\Users\\alice\\private",
        "../private/model",
    ],
)
def test_hash_rejects_private_paths_and_urls(
    tmp_path: Path,
    private_value: str,
) -> None:
    acceptance_path, manifest_path, _manifest = _inputs(tmp_path)
    prepared = _plain(
        prepare_separation_bakeoff(
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
    )
    prepared["orchestration"]["resource_class_ids"][0] = private_value
    with pytest.raises(ValueError, match="private path or URL"):
        separation_bakeoff_preparation_sha256(prepared)


def test_prepare_rejects_relabelled_operationally_identical_arms(
    tmp_path: Path,
) -> None:
    acceptance_path, manifest_path, _manifest = _inputs(tmp_path)
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    candidate = acceptance["identities"]["candidate_separator"]
    baseline = copy.deepcopy(candidate)
    baseline["identity_id"] = "relabeled-baseline"
    baseline["backend_id"] = "relabeled-baseline:backend"
    acceptance["identities"]["baseline_separator"] = baseline
    acceptance["artifact_sha256"] = (
        separation_acceptance_artifact_sha256(acceptance)
    )
    acceptance_path.write_bytes(canonical_json_bytes(acceptance))

    with pytest.raises(ValueError, match="operationally distinct"):
        prepare_separation_bakeoff(
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )


def test_upstream_byte_bounds_are_forwarded_by_every_public_loader(
    tmp_path: Path,
) -> None:
    acceptance_path, manifest_path, _manifest = _inputs(tmp_path)
    prepared = prepare_separation_bakeoff(
        acceptance_path=acceptance_path,
        hidden_manifest_path=manifest_path,
    )
    preparation_path = tmp_path / "preparation.json"
    preparation_path.write_bytes(canonical_json_bytes(prepared))

    with pytest.raises(ValueError, match="byte bound"):
        prepare_separation_bakeoff(
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
            maximum_acceptance_bytes=10,
        )
    with pytest.raises(ValueError, match="byte bound"):
        validate_separation_bakeoff_preparation(
            prepared,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
            maximum_hidden_manifest_bytes=10,
        )
    with pytest.raises(ValueError, match="byte bound"):
        load_separation_bakeoff_preparation(
            preparation_path,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
            maximum_acceptance_bytes=10,
        )


def test_load_requires_canonical_bounded_regular_non_symlink_json(
    tmp_path: Path,
) -> None:
    acceptance_path, manifest_path, _manifest = _inputs(tmp_path)
    prepared = prepare_separation_bakeoff(
        acceptance_path=acceptance_path,
        hidden_manifest_path=manifest_path,
    )
    preparation_path = tmp_path / "preparation.json"
    preparation_path.write_bytes(canonical_json_bytes(prepared))
    loaded = load_separation_bakeoff_preparation(
        preparation_path,
        acceptance_path=acceptance_path,
        hidden_manifest_path=manifest_path,
    )
    assert loaded["preparation_id"] == prepared["preparation_id"]

    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_text(json.dumps(_plain(prepared)), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical"):
        load_separation_bakeoff_preparation(
            noncanonical,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema":"first","schema":"second"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_separation_bakeoff_preparation(
            duplicate,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )

    with pytest.raises(ValueError, match="byte bound"):
        load_separation_bakeoff_preparation(
            preparation_path,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
            maximum_bytes=10,
        )

    symlink = tmp_path / "preparation-link.json"
    try:
        os.symlink(preparation_path, symlink)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")
    with pytest.raises(ValueError, match="non-symlink"):
        load_separation_bakeoff_preparation(
            symlink,
            acceptance_path=acceptance_path,
            hidden_manifest_path=manifest_path,
        )
