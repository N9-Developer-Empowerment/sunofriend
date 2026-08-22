from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from remix_learning_contract_fixtures import remix_fixture
from sunofriend.remix_learning_contract import (
    create_remix_controlled_variant_set,
    create_remix_owner_registry,
    create_remix_pairwise_label,
    create_remix_training_snapshot,
)
from sunofriend.remix_ranker_training import (
    REMIX_FROZEN_FEATURE_MANIFEST_SCHEMA,
    REMIX_RANKER_BOUND_REQUEST_SCHEMA,
    REMIX_RANKER_BOUND_RESULT_SCHEMA,
    REMIX_SYNTHETIC_TRAINING_SNAPSHOT_SCHEMA,
    build_synthetic_remix_training_snapshot,
    create_remix_frozen_feature_manifest,
    create_remix_ranker_training_request,
    run_remix_ranker_training,
    synthetic_frozen_values,
    validate_remix_frozen_feature_manifest,
    validate_remix_ranker_training_result,
    write_frozen_feature_vector,
)
from sunofriend.remix_ranker_training_verifier import (
    REMIX_RANKER_BOUND_VERIFICATION_SCHEMA,
    verify_remix_ranker_training,
)
from sunofriend.source_receipt import document_sha256


COMMIT = "7" * 40


def _rehash(document: dict) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)


def _extractor(*, dimension: int, synthetic: bool) -> dict:
    return {
        "name": "synthetic-frozen-vector-v1"
        if synthetic
        else "musicfm-fma-test-contract",
        "source_revision": COMMIT,
        "checkpoint_sha256": "8" * 64,
        "license_spdx": "CC0-1.0" if synthetic else "MIT",
        "layer": "fixture" if synthetic else "layer-7",
        "sample_rate_hz": 24_000,
        "feature_rate_hz": 25.0,
        "pooling": "synthetic_fixed_vector" if synthetic else "mean_over_anchor",
        "feature_dimension": dimension,
        "dtype": "float64-json-number",
        "extractor_frozen": True,
        "gradient_into_extractor": False,
    }


def _synthetic_package(tmp_path: Path) -> tuple[dict, dict, dict, Path]:
    snapshot = build_synthetic_remix_training_snapshot()
    root = tmp_path / "features"
    root.mkdir(mode=0o700, parents=True)
    rows = []
    for index, (variant_hash, values) in enumerate(
        sorted(synthetic_frozen_values().items()), start=1
    ):
        artifact = write_frozen_feature_vector(
            root / f"feature-{index:03d}.json",
            variant_evidence_sha256=variant_hash,
            values=values,
        )
        rows.append(
            {
                "variant_evidence_sha256": variant_hash,
                "artifact": artifact,
                "shape": [8],
                "dtype": "float64-json-number",
                "finite": True,
            }
        )
    manifest = create_remix_frozen_feature_manifest(
        snapshot,
        feature_root=root,
        rows=rows,
        feature_set_id="synthetic-frozen-001",
        repository_commit=COMMIT,
        extractor=_extractor(dimension=8, synthetic=True),
        synthetic_only=True,
    )
    request = create_remix_ranker_training_request(
        snapshot,
        manifest,
        feature_root=root,
        request_id="synthetic-request-001",
        repository_commit=COMMIT,
        dependency_contract_sha256="9" * 64,
    )
    return snapshot, manifest, request, root


def test_synthetic_pipeline_uses_commit_bound_frozen_manifest_and_all_controls(
    tmp_path: Path,
) -> None:
    snapshot, manifest, request, root = _synthetic_package(tmp_path)
    assert snapshot["schema"] == REMIX_SYNTHETIC_TRAINING_SNAPSHOT_SCHEMA
    assert manifest["schema"] == REMIX_FROZEN_FEATURE_MANIFEST_SCHEMA
    assert manifest["admission"]["artifact_hashes_verified"] is True
    assert manifest["admission"]["extractor_frozen"] is True
    assert len(manifest["rows"]) == 192
    assert request["schema"] == REMIX_RANKER_BOUND_REQUEST_SCHEMA
    assert request["repository_commit"] == COMMIT
    assert request["status"] == "planned_synthetic_contract_canary"
    assert request["dataset"]["split_counts"] == {
        "train": 64,
        "validation": 16,
        "test": 16,
    }
    assert not any(
        request["authority"][key]
        for key in (
            "source_mutation_authorized",
            "remix_render_authorized",
            "checkpoint_promotion_authorized",
            "product_ordering_authorized",
            "automatic_preference_authorized",
        )
    )

    result = run_remix_ranker_training(
        request,
        snapshot,
        manifest,
        feature_root=root,
        repository_commit=COMMIT,
    )
    assert result["schema"] == REMIX_RANKER_BOUND_RESULT_SCHEMA
    assert result["status"] == "complete_synthetic_training_pipeline_unpromoted"
    assert set(result["metrics"]) == {
        "constant_majority",
        "smallest_absolute_change",
        "largest_attenuation",
        "operation_linear",
        "combined_clean",
        "combined_resumed",
        "combined_shuffled",
    }
    assert result["controls"]["maximum_resume_parameter_difference"] == 0.0
    assert result["controls"]["maximum_left_right_swap_probability_error"] <= 1e-12
    assert result["controls"]["clean_minus_shuffled_test_accuracy"] >= 0.20
    assert result["resource_receipt"]["network_attempts"] == 0
    assert result["resource_receipt"]["downloads"] == 0
    assert result["resource_receipt"]["audio_files_opened"] == 0
    assert result["authority"]["product_admitted"] is False
    assert result["authority"]["product_ordering_changed"] is False

    verification = verify_remix_ranker_training(
        request, snapshot, manifest, result, feature_root=root
    )
    assert verification["schema"] == REMIX_RANKER_BOUND_VERIFICATION_SCHEMA
    assert verification["status"] == "verified_synthetic_training_evidence_unpromoted"
    assert all(verification["checks"].values())
    assert verification["execution"]["training_performed_by_verifier"] is False
    assert verification["execution"]["network_attempts"] == 0
    assert verification["authority"]["product_admitted"] is False


def test_real_explicit_snapshot_and_admitted_features_remain_training_ineligible(
    tmp_path: Path,
) -> None:
    snapshot = _real_one_label_snapshot()
    root = tmp_path / "real-shaped-features"
    root.mkdir(mode=0o700)
    variant_hashes = sorted(
        row["variant_evidence_sha256"]
        for variant_set in snapshot["variant_sets"]
        for row in variant_set["variants"]
    )
    rows = []
    for index, variant_hash in enumerate(variant_hashes, start=1):
        values = [float(index), float(index + 1), float(index + 2)]
        artifact = write_frozen_feature_vector(
            root / f"real-shaped-{index}.json",
            variant_evidence_sha256=variant_hash,
            values=values,
        )
        rows.append(
            {
                "variant_evidence_sha256": variant_hash,
                "artifact": artifact,
                "shape": [3],
                "dtype": "float64-json-number",
                "finite": True,
            }
        )
    manifest = create_remix_frozen_feature_manifest(
        snapshot,
        feature_root=root,
        rows=rows,
        feature_set_id="real-shaped-frozen-001",
        repository_commit=COMMIT,
        extractor=_extractor(dimension=3, synthetic=False),
        synthetic_only=False,
    )
    request = create_remix_ranker_training_request(
        snapshot,
        manifest,
        feature_root=root,
        request_id="real-shaped-request-001",
        repository_commit=COMMIT,
        dependency_contract_sha256="9" * 64,
    )
    assert manifest["admission"]["synthetic_only"] is False
    assert request["status"] == "blocked_insufficient_real_evidence"
    assert request["dataset"]["training_eligible"] is False
    with pytest.raises(ValueError, match="real remix training remains ineligible"):
        run_remix_ranker_training(
            request,
            snapshot,
            manifest,
            feature_root=root,
            repository_commit=COMMIT,
        )


def test_feature_artifact_tamper_nonfinite_symlink_and_roster_drift_fail_closed(
    tmp_path: Path,
) -> None:
    snapshot, manifest, _, root = _synthetic_package(tmp_path)
    first = root / manifest["rows"][0]["artifact"]["filename"]
    first.write_bytes(first.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash or size"):
        validate_remix_frozen_feature_manifest(manifest, snapshot, feature_root=root)

    second_root = tmp_path / "second"
    second_snapshot, second_manifest, _, second_features = _synthetic_package(
        second_root
    )
    changed = deepcopy(second_manifest)
    changed["rows"] = changed["rows"][:-1]
    _rehash(changed)
    with pytest.raises(ValueError, match="cover|roster"):
        validate_remix_frozen_feature_manifest(
            changed, second_snapshot, feature_root=second_features
        )

    artifact = second_manifest["rows"][0]["artifact"]
    original = second_features / artifact["filename"]
    replacement = second_features / "replacement.json"
    original.rename(replacement)
    original.symlink_to(replacement.name)
    with pytest.raises(ValueError, match="escaped exact root"):
        validate_remix_frozen_feature_manifest(
            second_manifest, second_snapshot, feature_root=second_features
        )

    with pytest.raises(ValueError, match="finite"):
        write_frozen_feature_vector(
            tmp_path / "nonfinite.json",
            variant_evidence_sha256="a" * 64,
            values=[1.0, math.nan],
        )


def test_commit_authority_prediction_and_resource_tampering_are_rejected(
    tmp_path: Path,
) -> None:
    snapshot, manifest, request, root = _synthetic_package(tmp_path)
    with pytest.raises(ValueError, match="repository commit"):
        run_remix_ranker_training(
            request,
            snapshot,
            manifest,
            feature_root=root,
            repository_commit="6" * 40,
        )
    result = run_remix_ranker_training(
        request,
        snapshot,
        manifest,
        feature_root=root,
        repository_commit=COMMIT,
    )
    promoted = deepcopy(result)
    promoted["authority"]["product_admitted"] = True
    _rehash(promoted)
    with pytest.raises(ValueError, match="authority"):
        validate_remix_ranker_training_result(
            promoted, request, snapshot, manifest, feature_root=root
        )

    forged = deepcopy(result)
    forged["predictions"]["combined_clean"][0]["left_probability"] = 0.5
    forged["predictions"]["combined_clean"][0]["predicted_label"] = 1
    _rehash(forged)
    with pytest.raises(ValueError, match="metrics|predictions"):
        verify_remix_ranker_training(
            request, snapshot, manifest, forged, feature_root=root
        )

    changed_receipt = deepcopy(result)
    changed_receipt["resource_receipt"]["network_attempts"] = 1
    _rehash(changed_receipt)
    with pytest.raises(ValueError, match="resource|offline"):
        validate_remix_ranker_training_result(
            changed_receipt, request, snapshot, manifest, feature_root=root
        )


def test_cli_runs_fixture_training_and_independent_verification(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    package = tmp_path / "package"
    environment = {"PYTHONPATH": str(root / "src")}
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts/create-remix-ranker-synthetic-training-fixture.py"),
            "--out-dir",
            str(package),
            "--repository-commit",
            commit,
            "--dependency-contract",
            str(root / "pyproject.toml"),
        ],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert package.stat().st_mode & 0o777 == 0o700
    result = package / "result.json"
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts/run-remix-ranker-training.py"),
            str(package / "request.json"),
            str(package / "snapshot.json"),
            str(package / "feature-manifest.json"),
            "--feature-root",
            str(package / "features"),
            "--out",
            str(result),
        ],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    verification = package / "verification.json"
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts/verify-remix-ranker-training.py"),
            str(package / "request.json"),
            str(package / "snapshot.json"),
            str(package / "feature-manifest.json"),
            str(result),
            "--feature-root",
            str(package / "features"),
            "--out",
            str(verification),
        ],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.read_text())["status"] == (
        "complete_synthetic_training_pipeline_unpromoted"
    )
    assert json.loads(verification.read_text())["status"] == (
        "verified_synthetic_training_evidence_unpromoted"
    )
    assert result.stat().st_mode & 0o777 == 0o600
    assert verification.stat().st_mode & 0o777 == 0o600


def _real_one_label_snapshot() -> dict:
    fixture = remix_fixture()
    registry = create_remix_owner_registry(
        registry_id="registry-real-shaped-001",
        entries=[
            {
                "composition_id": "composition-real-shaped-001",
                "group_id": "group-real-shaped-001",
                "musical_state": fixture["state"],
                "identity_state": fixture["identity"],
                "source_control": fixture["control"],
                "rights_scope": "owner_local_training",
                "cloud_training_approved": False,
            }
        ],
    )
    variants = create_remix_controlled_variant_set(
        registry,
        fixture["identity"],
        variant_set_id="variants-real-shaped-001",
        variant_family_id="family-real-shaped-001",
        source_control=fixture["control"],
        variants=[
            {
                "variant_id": "left-real-shaped-001",
                "remix_request": fixture["left_request"],
                "remix_result": fixture["left_result"],
            },
            {
                "variant_id": "right-real-shaped-001",
                "remix_request": fixture["right_request"],
                "remix_result": fixture["right_result"],
            },
        ],
    )
    label = create_remix_pairwise_label(
        registry,
        variants,
        fixture["identity"],
        left_variant_id="left-real-shaped-001",
        right_variant_id="right-real-shaped-001",
        heard_control=True,
        heard_left=True,
        heard_right=True,
        outcome="left",
        left_identity_relationship="preserved",
        right_identity_relationship="partly_preserved",
        reason_codes=["change_more_useful"],
        training_admission="explicit_owner_local_training",
        presentation_seed=20260822,
        reviewed_at="2026-08-22T12:00:00Z",
    )
    return create_remix_training_snapshot(
        labels=[label],
        owner_registries=[registry],
        variant_sets=[variants],
        assignments=[
            {
                "label_document_sha256": label["document_sha256"],
                "composition_id": "composition-real-shaped-001",
                "group_id": "group-real-shaped-001",
                "musical_state_sha256": fixture["state"]["document_sha256"],
                "variant_family_id": "family-real-shaped-001",
                "split": "train",
            }
        ],
        snapshot_id="real-shaped-one-label-001",
    )
