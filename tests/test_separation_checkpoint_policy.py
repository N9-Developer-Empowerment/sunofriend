from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from sunofriend.separation_checkpoint_policy import (
    CHECKPOINT_EXECUTION_POLICY_SUPPORTED,
    DEMUCS_HTDEMUCS_CHECKPOINT_SHA256,
    SUPPORTED_UNSAFE_PICKLE_PROVIDER_IDS,
    SeparationCheckpointEvidence,
    SeparationCheckpointLoaderEvidence,
    SeparationCheckpointTermsEvidence,
    SeparationUnsafePickleExceptionEvidence,
    build_separation_checkpoint_policy,
    separation_checkpoint_policy_sha256,
    validate_separation_checkpoint_policy,
)


def _sha(character: str) -> str:
    return character * 64


def _terms(
    *,
    verified: bool = True,
    expression: str = "CC-BY-NC-4.0",
) -> SeparationCheckpointTermsEvidence:
    return SeparationCheckpointTermsEvidence(
        terms_sha256=_sha("a") if verified else None,
        terms_verified=verified,
        license_expression=expression,
        allowed_uses=("private_development",),
        allowed_use_evidence_sha256=_sha("b") if verified else None,
        allowed_use_verified=verified,
    )


def _unsafe(
    *,
    approved: bool = False,
    checkpoint_sha256: str | None = None,
) -> SeparationUnsafePickleExceptionEvidence:
    if not approved:
        return SeparationUnsafePickleExceptionEvidence()
    globals_value = ("demucs.hdemucs.HTDemucs",)
    import hashlib
    import json

    globals_hash = hashlib.sha256(
        json.dumps(
            list(globals_value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return SeparationUnsafePickleExceptionEvidence(
        explicitly_approved=True,
        evidence_scope="private_development",
        approval_sha256=_sha("c"),
        provider_id="reported-pickle-provider",
        provider_sha256=_sha("d"),
        provider_qualification_sha256=_sha("e"),
        exact_globals=globals_value,
        exact_globals_sha256=globals_hash,
        checkpoint_sha256=checkpoint_sha256,
    )


def _htdemucs(
    *,
    unsafe: SeparationUnsafePickleExceptionEvidence | None = None,
) -> SeparationCheckpointEvidence:
    return SeparationCheckpointEvidence(
        checkpoint_id="htdemucs-955717e8",
        declared_format="torch-state-dict",
        # This is deliberately the legacy/reporting claim. The code-owned
        # exact hash classification must override it.
        classified_container_kind="torch-state-dict",
        checkpoint_sha256=DEMUCS_HTDEMUCS_CHECKPOINT_SHA256,
        checkpoint_bytes=84_000_000,
        classification_evidence_sha256=_sha("f"),
        terms=_terms(verified=True),
        loader=SeparationCheckpointLoaderEvidence(
            loader_id="demucs-states-load-model",
            loader_sha256=_sha("1"),
            deserialization_mode="torch-load-pickle-model-package",
            weights_only=False,
        ),
        unsafe_pickle_exception=unsafe
        or SeparationUnsafePickleExceptionEvidence(),
    )


def _unknown_safetensors() -> SeparationCheckpointEvidence:
    return SeparationCheckpointEvidence(
        checkpoint_id="synthetic-safetensors",
        declared_format="safetensors",
        classified_container_kind="safetensors",
        checkpoint_sha256=_sha("2"),
        checkpoint_bytes=1024,
        classification_evidence_sha256=_sha("3"),
        terms=_terms(),
        loader=SeparationCheckpointLoaderEvidence(
            loader_id="synthetic-safetensors-loader",
            loader_sha256=_sha("4"),
            deserialization_mode="safetensors-tensor-load",
            weights_only="not_applicable",
        ),
        unsafe_pickle_exception=SeparationUnsafePickleExceptionEvidence(),
    )


def _plain(value: object) -> object:
    from collections.abc import Mapping

    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def test_exact_htdemucs_hash_is_categorically_pickle_and_blocked() -> None:
    policy = build_separation_checkpoint_policy(_htdemucs())

    assert CHECKPOINT_EXECUTION_POLICY_SUPPORTED is False
    assert not SUPPORTED_UNSAFE_PICKLE_PROVIDER_IDS
    assert policy["checkpoint"]["declared_format"] == "torch-state-dict"
    assert policy["checkpoint"]["reported_container_kind"] == "torch-state-dict"
    assert (
        policy["checkpoint"]["classified_container_kind"]
        == "torch-pickle-model-package"
    )
    blockers = set(policy["decision"]["blockers"])
    assert {
        "checkpoint_terms_unverified",
        "checkpoint_allowed_use_unverified",
        "checkpoint_format_classification_mismatch",
        "checkpoint_reported_classification_disagrees",
        "checkpoint_is_pickle_model_package",
        "unsafe_deserialization_not_approved",
        "checkpoint_execution_policy_not_implemented",
        "trusted_evidence_cross_binding_unimplemented",
    }.issubset(blockers)
    assert policy["terms"]["reported_terms_verified"] is True
    assert policy["terms"]["policy_terms_verified"] is False
    assert policy["terms"]["policy_allowed_use_verified"] is False
    assert policy["decision"]["status"] == "blocked"
    assert policy["decision"]["run_status"] == "not_run"
    assert policy["decision"]["private_development_checkpoint_eligible"] is False
    assert policy["decision"]["worker_start_permitted"] is False
    assert policy["publication_scope"] == "private_local_contract_evidence"
    assert policy["public_redacted_projection_available"] is False
    assert all(item is False for item in policy["effects"].values())


def test_complete_unsafe_exception_metadata_cannot_waive_pickle_blocker() -> None:
    unsafe = _unsafe(
        approved=True,
        checkpoint_sha256=DEMUCS_HTDEMUCS_CHECKPOINT_SHA256,
    )
    policy = build_separation_checkpoint_policy(_htdemucs(unsafe=unsafe))

    assert policy["unsafe_pickle_exception"]["reported_evidence_complete"] is True
    assert (
        policy["unsafe_pickle_exception"]["qualifying_provider_supported"]
        is False
    )
    assert policy["unsafe_pickle_exception"]["waives_pickle_blocker"] is False
    assert "checkpoint_is_pickle_model_package" in policy["decision"]["blockers"]
    assert "unsafe_deserialization_not_approved" in policy["decision"]["blockers"]
    assert (
        "unsafe_pickle_exception_metadata_recorded_only"
        in policy["decision"]["advisories"]
    )


def test_even_forced_provider_and_terms_claims_cannot_waive_pickle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sunofriend.separation_checkpoint_policy as policy_module

    monkeypatch.setattr(
        policy_module,
        "SUPPORTED_UNSAFE_PICKLE_PROVIDER_IDS",
        frozenset({"reported-pickle-provider"}),
    )
    monkeypatch.setattr(
        policy_module,
        "_KNOWN_CHECKPOINTS",
        {
            DEMUCS_HTDEMUCS_CHECKPOINT_SHA256: {
                "policy_id": "synthetic-forced-terms",
                "classified_container_kind": "torch-pickle-model-package",
                "terms_verified": True,
                "allowed_use_verified": True,
            }
        },
    )
    unsafe = _unsafe(
        approved=True,
        checkpoint_sha256=DEMUCS_HTDEMUCS_CHECKPOINT_SHA256,
    )
    policy = build_separation_checkpoint_policy(_htdemucs(unsafe=unsafe))

    assert policy["terms"]["policy_terms_verified"] is True
    assert policy["terms"]["policy_allowed_use_verified"] is True
    assert (
        policy["unsafe_pickle_exception"]["qualifying_provider_supported"]
        is True
    )
    assert "checkpoint_is_pickle_model_package" in policy["decision"]["blockers"]
    assert "unsafe_deserialization_not_approved" in policy["decision"]["blockers"]
    assert policy["decision"]["private_development_checkpoint_eligible"] is False
    assert policy["decision"]["worker_start_permitted"] is False


def test_unknown_hash_remains_uninspected_and_blocked_despite_safe_claims() -> None:
    policy = build_separation_checkpoint_policy(_unknown_safetensors())

    assert policy["checkpoint"]["reported_container_kind"] == "safetensors"
    assert policy["checkpoint"]["classified_container_kind"] == "uninspected"
    blockers = set(policy["decision"]["blockers"])
    assert {
        "checkpoint_container_uninspected",
        "checkpoint_format_classification_mismatch",
        "checkpoint_reported_classification_disagrees",
        "checkpoint_terms_unverified",
        "trusted_evidence_cross_binding_unimplemented",
    }.issubset(blockers)
    assert policy["decision"]["private_development_checkpoint_eligible"] is False


def test_weights_only_defaults_true_and_spdx_uppercase_is_accepted() -> None:
    loader = SeparationCheckpointLoaderEvidence(
        loader_id="synthetic-loader",
        loader_sha256=_sha("5"),
        deserialization_mode="torch-load-state-dict",
    )

    assert loader.weights_only is True
    assert _terms(expression="Apache-2.0 OR CC-BY-NC-4.0").license_expression == (
        "Apache-2.0 OR CC-BY-NC-4.0"
    )
    assert _unknown_safetensors().loader.weights_only == "not_applicable"
    with pytest.raises(ValueError, match="true, false or not_applicable"):
        replace(loader, weights_only="reported_true")


def test_evidence_sequences_are_bounded_sorted_and_unique() -> None:
    with pytest.raises(ValueError, match="sorted and unique"):
        replace(_terms(), allowed_uses=("private_development", "private_development"))
    with pytest.raises(ValueError, match="must be an array"):
        replace(_terms(), allowed_uses=tuple(f"use_{index}" for index in range(257)))
    with pytest.raises(ValueError, match="unsafe pickle global"):
        replace(
            SeparationUnsafePickleExceptionEvidence(),
            exact_globals=("builtins/eval",),
        )


def test_policy_is_deeply_immutable_sorted_and_self_hashed() -> None:
    evidence = _htdemucs()
    policy = build_separation_checkpoint_policy(evidence)

    assert policy["policy_sha256"] == separation_checkpoint_policy_sha256(policy)
    assert tuple(sorted(policy["decision"]["blockers"])) == policy["decision"][
        "blockers"
    ]
    with pytest.raises(TypeError):
        policy["decision"]["status"] = "ready"
    with pytest.raises(TypeError):
        policy["checkpoint"]["sha256"] = _sha("9")

    plain = _plain(policy)
    assert validate_separation_checkpoint_policy(
        plain,
        reported_evidence=evidence,
    ) == policy
    plain["decision"]["blockers"].pop()
    with pytest.raises(ValueError, match="does not match reported evidence"):
        validate_separation_checkpoint_policy(
            plain,
            reported_evidence=evidence,
        )


def test_plain_mapping_cannot_replace_exact_synthetic_evidence() -> None:
    evidence = _htdemucs()
    with pytest.raises(ValueError, match="exact synthetic evidence"):
        build_separation_checkpoint_policy(asdict(evidence))  # type: ignore[arg-type]
