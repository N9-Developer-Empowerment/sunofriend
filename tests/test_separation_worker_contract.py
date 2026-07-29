from __future__ import annotations

import copy
import hashlib
import runpy
from pathlib import Path
from typing import Any

import pytest

from sunofriend.separation_contract import (
    SeparationAudioGeometry,
    SeparationRequest,
)
from sunofriend.separation_worker_contract import (
    SEPARATION_WORKER_ISOLATION_POLICY,
    SeparationRuntimeArtifactIdentity,
    build_separation_worker_request,
    build_separation_worker_result,
    separation_worker_request_sha256,
    separation_worker_result_sha256,
    validate_separation_worker_request,
    validate_separation_worker_result,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _fixture(tmp_path: Path) -> dict[str, Any]:
    namespace = runpy.run_path(
        str(Path(__file__).with_name("test_separation_backend_preflight.py"))
    )
    inputs = namespace["_make_inputs"](tmp_path / "preflight")
    acceptance = copy.deepcopy(inputs["acceptance"])
    candidate = acceptance["identities"]["candidate_separator"]
    candidate["backend_id"] = "candidate-separator-backend"
    candidate["checkpoint"]["checkpoint_id"] = "candidate-separator-checkpoint"
    namespace["_replace_acceptance"](inputs, acceptance)
    preflight = namespace["_run"](inputs)
    identity = inputs["acceptance"]["identities"]["candidate_separator"]
    geometry = SeparationAudioGeometry(
        sample_rate=44_100,
        channels=2,
        frames=88_200,
        duration_seconds=2.0,
    )
    source_sha = _sha("original source")
    request = SeparationRequest.create(
        source_path=tmp_path / "source.wav",
        output_dir=tmp_path / "worker-output",
        checkpoint_path=inputs["checkpoint"],
        source_id=f"sha256:{source_sha}",
        source_sha256=source_sha,
        canonical_sha256=_sha("canonical source"),
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
        "profile_sha256": _sha("profile"),
        "environment_sha256": _sha("environment"),
        "file_descriptor_policy_sha256": _sha("fd-policy"),
        "canary_sha256": _sha("canary"),
        "observer_id": "sunofriend-parent-observer",
        "observer_sha256": _sha("observer"),
    }
    runtime_artifact = SeparationRuntimeArtifactIdentity(
        path=inputs["launcher"],
        sha256=_sha("runtime launcher"),
        bytes=1024,
        verified_launcher_chain_sha256=_sha("verified launcher chain"),
    )
    worker_request = build_separation_worker_request(
        preflight=preflight,
        trusted_acceptance=inputs["acceptance"],
        separation_request=request,
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
    return {
        "inputs": inputs,
        "preflight": preflight,
        "acceptance": inputs["acceptance"],
        "separation_request": request,
        "isolation": isolation,
        "runtime_artifact": runtime_artifact,
        "worker_request": worker_request,
        "geometry": geometry.to_dict(),
    }


def _input_hashes(request: Any) -> dict[str, str]:
    identities = request["identities"]
    return {
        "source": identities["source"]["canonical_sha256"],
        "checkpoint": identities["checkpoint"]["sha256"],
        "worker": identities["worker"]["sha256"],
        "runtime": identities["runtime"]["sha256"],
        "dependency_lock": identities["dependency_lock"]["sha256"],
    }


def _outputs(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "role": role,
            "relative_path": f"STEMS/{role}.wav",
            "sha256": _sha(f"{role} output"),
            "bytes": 8192,
            "geometry": fixture["geometry"],
        }
        for role in ("bass", "drums")
    ]


def _enforcement(
    fixture: dict[str, Any],
    *,
    status: str = "development_enforced_observation_unproven",
) -> dict[str, Any]:
    return {
        "isolation_status": status,
        "isolation": fixture["isolation"],
        "checks": {
            "network_denial": "enforced",
            "input_read_only": "enforced",
            "output_allowlist": "enforced",
            "child_process_denial": "enforced",
            "checkpoint_identity_before_load": "enforced",
        },
        "effects": {
            "network_used": False,
            "outside_output_writes": False,
            "child_processes_started": False,
        },
        "worker_started": True,
        "inference_started": True,
    }


def _result(fixture: dict[str, Any]) -> Any:
    return build_separation_worker_result(
        worker_request=fixture["worker_request"],
        **_trusted(fixture),
        status="complete",
        after_input_hashes=_input_hashes(fixture["worker_request"]),
        outputs=_outputs(fixture),
        enforcement=_enforcement(fixture),
        error=None,
    )


def _trusted(fixture: dict[str, Any]) -> dict[str, Any]:
    return {
        "trusted_preflight": fixture["preflight"],
        "trusted_acceptance": fixture["acceptance"],
        "trusted_separation_request": fixture["separation_request"],
        "trusted_runtime_artifact": fixture["runtime_artifact"],
    }


def _rebuild_request(
    fixture: dict[str, Any],
    *,
    isolation: dict[str, Any] | None = None,
) -> Any:
    identities = fixture["worker_request"]["identities"]
    return build_separation_worker_request(
        preflight=fixture["preflight"],
        trusted_acceptance=fixture["acceptance"],
        separation_request=fixture["separation_request"],
        worker_path=fixture["inputs"]["worker"],
        trusted_runtime_artifact=fixture["runtime_artifact"],
        dependency_lock_path=fixture["inputs"]["dependency_lock"],
        source_bytes=identities["source"]["bytes"],
        checkpoint_bytes=identities["checkpoint"]["bytes"],
        worker_sha256=identities["worker"]["sha256"],
        worker_bytes=identities["worker"]["bytes"],
        runtime_id=identities["runtime"]["runtime_id"],
        runtime_version=identities["runtime"]["runtime_version"],
        python_version=identities["runtime"]["python_version"],
        dependency_lock_sha256=identities["dependency_lock"]["sha256"],
        dependency_lock_bytes=identities["dependency_lock"]["bytes"],
        isolation=isolation or fixture["isolation"],
    )


def _rehash_request(document: dict[str, Any]) -> None:
    document["request_sha256"] = separation_worker_request_sha256(document)


def _rehash_result(document: dict[str, Any]) -> None:
    document["result_sha256"] = separation_worker_result_sha256(document)


def test_builds_strict_deeply_immutable_request_and_path_free_result(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    request = fixture["worker_request"]
    result = _result(fixture)

    assert request["preflight"]["status"] == "verified_not_run"
    assert request["output_allowlist"][0]["relative_path"] == "STEMS/bass.wav"
    assert result["status"] == "complete"
    assert result["enforcement"]["isolation_status"] == (
        "development_enforced_observation_unproven"
    )
    assert all(item["unchanged"] for item in result["input_hashes"].values())
    assert not any(
        text.startswith(str(tmp_path)) for text in _all_strings(_plain(result))
    )
    with pytest.raises(TypeError):
        request["paths"]["source_path"] = "/changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        result["outputs"][0]["sha256"] = _sha("changed")  # type: ignore[index]


def _all_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _all_strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _all_strings(item)]
    return []


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda request: request["paths"].__setitem__(
                "worker_path", "/tmp/worker/../worker.py"
            ),
            "canonical absolute",
        ),
        (
            lambda request: request["paths"].__setitem__(
                "worker_path",
                "//"
                + request["paths"]["output_dir"].lstrip("/")
                + "/physical-output-alias.py",
            ),
            "canonical absolute",
        ),
        (
            lambda request: request["paths"].__setitem__(
                "worker_path", request["paths"]["source_path"].upper()
            ),
            "aliases",
        ),
        (
            lambda request: request["roles"].__setitem__(1, "hats"),
            "canonical prepared",
        ),
        (
            lambda request: request["settings"].__setitem__(
                "model_url", "https://example.invalid/model"
            ),
            "path or URL",
        ),
        (
            lambda request: request["output_allowlist"][0].__setitem__(
                "relative_path", "STEMS/../escape.wav"
            ),
            "alias or escape",
        ),
    ],
)
def test_request_rejects_path_aliases_urls_role_aliases_and_escapes(
    tmp_path: Path, mutation: Any, message: str
) -> None:
    fixture = _fixture(tmp_path)
    document = _plain(fixture["worker_request"])
    mutation(document)
    _rehash_request(document)
    with pytest.raises(ValueError, match=message):
        validate_separation_worker_request(document, **_trusted(fixture))


def test_runtime_case_alias_cannot_hide_inside_output_directory(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime_artifact"]
    aliased_path = Path(
        str(fixture["separation_request"].output_dir).upper() + "/runtime-python"
    )
    aliased_runtime = SeparationRuntimeArtifactIdentity(
        path=aliased_path,
        sha256=runtime.sha256,
        bytes=runtime.bytes,
        verified_launcher_chain_sha256=(runtime.verified_launcher_chain_sha256),
    )
    document = _plain(fixture["worker_request"])
    document["paths"]["runtime_python_path"] = str(aliased_path)
    _rehash_request(document)
    trusted = _trusted(fixture)
    trusted["trusted_runtime_artifact"] = aliased_runtime

    with pytest.raises(ValueError, match="outside output directory"):
        validate_separation_worker_request(document, **trusted)


def test_request_rejects_forged_preflight_and_extra_fields(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    forged = _plain(fixture["worker_request"])
    forged["preflight"]["arm"]["backend_id"] = "forged-backend"
    _rehash_request(forged)
    with pytest.raises(ValueError, match="forged preflight"):
        validate_separation_worker_request(forged, **_trusted(fixture))

    extra = _plain(fixture["worker_request"])
    extra["quality"] = {"score": 1.0}
    with pytest.raises(ValueError, match="fields"):
        validate_separation_worker_request(extra, **_trusted(fixture))


@pytest.mark.parametrize(
    ("identity_path", "replacement"),
    [
        (("worker", "sha256"), _sha("substituted worker")),
        (("dependency_lock", "sha256"), _sha("substituted lock")),
        (("runtime", "runtime_version"), "3.11.99"),
    ],
)
def test_request_rejects_resigned_unregistered_runtime_identity(
    tmp_path: Path,
    identity_path: tuple[str, str],
    replacement: str,
) -> None:
    fixture = _fixture(tmp_path)
    document = _plain(fixture["worker_request"])
    document["identities"][identity_path[0]][identity_path[1]] = replacement
    _rehash_request(document)

    with pytest.raises(ValueError, match="registration"):
        validate_separation_worker_request(document, **_trusted(fixture))


@pytest.mark.parametrize(
    ("setting", "replacement"),
    [("split", 1), ("segments", 8.0)],
)
def test_request_settings_bind_with_type_aware_canonical_json(
    tmp_path: Path,
    setting: str,
    replacement: Any,
) -> None:
    fixture = _fixture(tmp_path)
    document = _plain(fixture["worker_request"])
    document["settings"][setting] = replacement
    _rehash_request(document)

    with pytest.raises(ValueError, match="settings do not bind"):
        validate_separation_worker_request(document, **_trusted(fixture))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda request, tmp_path: request["paths"].__setitem__(
                "runtime_python_path", str(tmp_path / "substituted-python")
            ),
            "paths do not bind",
        ),
        (
            lambda request, _tmp_path: request["identities"]["runtime"].__setitem__(
                "sha256", _sha("substituted runtime")
            ),
            "identities do not bind",
        ),
        (
            lambda request, _tmp_path: request["identities"]["runtime"].__setitem__(
                "bytes", 2048
            ),
            "identities do not bind",
        ),
        (
            lambda request, _tmp_path: request["identities"]["runtime"].__setitem__(
                "verified_launcher_chain_sha256", _sha("substituted chain")
            ),
            "identities do not bind",
        ),
    ],
)
def test_request_rejects_resigned_runtime_artifact_substitution(
    tmp_path: Path,
    mutation: Any,
    message: str,
) -> None:
    fixture = _fixture(tmp_path)
    document = _plain(fixture["worker_request"])
    mutation(document, tmp_path)
    _rehash_request(document)

    with pytest.raises(ValueError, match=message):
        validate_separation_worker_request(document, **_trusted(fixture))


def test_request_requires_parent_owned_exact_runtime_artifact(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    trusted = _trusted(fixture)
    runtime = fixture["runtime_artifact"]
    trusted["trusted_runtime_artifact"] = {
        "path": str(runtime.path),
        "sha256": runtime.sha256,
        "bytes": runtime.bytes,
        "verified_launcher_chain_sha256": runtime.verified_launcher_chain_sha256,
    }

    with pytest.raises(ValueError, match="parent-owned exact identity"):
        validate_separation_worker_request(
            fixture["worker_request"],
            **trusted,
        )


def test_result_rejects_binding_mutation_paths_and_claims(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    for mutate, message in (
        (
            lambda item: item.__setitem__(
                "worker_request_sha256", _sha("other request")
            ),
            "bind",
        ),
        (
            lambda item: item["error"].update({"message": "/Users/private/source.wav"}),
            "path or URL",
        ),
        (
            lambda item: item.__setitem__("promotion", {"selected": True}),
            "fields",
        ),
    ):
        document = _plain(_result(fixture))
        if document["error"] is None:
            document["error"] = {
                "code": "diagnostic",
                "message": "safe",
                "retryable": False,
            }
        mutate(document)
        with pytest.raises(ValueError, match=message):
            if set(document) == {
                "schema",
                "result_sha256",
                "worker_request_sha256",
                "preflight_id",
                "preflight_sha256",
                "separation_request_fingerprint_sha256",
                "status",
                "input_hashes",
                "outputs",
                "enforcement",
                "error",
            }:
                _rehash_result(document)
            validate_separation_worker_result(
                document,
                worker_request=fixture["worker_request"],
                **_trusted(fixture),
            )


@pytest.mark.parametrize(
    "error_path",
    ["logs/error.txt", r"\\server\share\error.txt"],
)
def test_result_rejects_relative_and_unc_error_paths(
    tmp_path: Path,
    error_path: str,
) -> None:
    fixture = _fixture(tmp_path)
    document = _plain(_result(fixture))
    document["error"] = {
        "code": "diagnostic",
        "message": error_path,
        "retryable": False,
    }
    _rehash_result(document)

    with pytest.raises(ValueError, match="path or URL"):
        validate_separation_worker_result(
            document,
            worker_request=fixture["worker_request"],
            **_trusted(fixture),
        )


def test_result_rejects_self_signed_forged_request_anchor(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    request = _plain(fixture["worker_request"])
    forged_worker = _sha("forged self-signed worker")
    request["identities"]["worker"]["sha256"] = forged_worker
    _rehash_request(request)
    result = _plain(_result(fixture))
    result["worker_request_sha256"] = request["request_sha256"]
    result["input_hashes"]["worker"] = {
        "before_sha256": forged_worker,
        "after_sha256": forged_worker,
        "unchanged": True,
    }
    _rehash_result(result)

    with pytest.raises(ValueError, match="registration"):
        validate_separation_worker_result(
            result,
            worker_request=request,
            **_trusted(fixture),
        )


def test_complete_result_requires_exact_outputs_immutable_inputs_and_controls(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    missing = _plain(_result(fixture))
    missing["outputs"].pop()
    _rehash_result(missing)
    with pytest.raises(ValueError, match="every allowed output"):
        validate_separation_worker_result(
            missing,
            worker_request=fixture["worker_request"],
            **_trusted(fixture),
        )

    changed = _plain(_result(fixture))
    changed["input_hashes"]["checkpoint"]["after_sha256"] = _sha("changed")
    changed["input_hashes"]["checkpoint"]["unchanged"] = False
    _rehash_result(changed)
    with pytest.raises(ValueError, match="unchanged inputs"):
        validate_separation_worker_result(
            changed,
            worker_request=fixture["worker_request"],
            **_trusted(fixture),
        )

    violated = _plain(_result(fixture))
    violated["enforcement"]["checks"]["network_denial"] = "violated"
    _rehash_result(violated)
    with pytest.raises(ValueError, match="enforced controls"):
        validate_separation_worker_result(
            violated,
            worker_request=fixture["worker_request"],
            **_trusted(fixture),
        )


@pytest.mark.parametrize(
    ("evidence_scope", "required_status", "message"),
    [
        (
            "hidden_acceptance",
            "development_enforced_observation_unproven",
            "evidence scope",
        ),
        (
            "private_development",
            "acceptance_ready",
            "required isolation status",
        ),
        ("hidden_acceptance", "acceptance_ready", "evidence scope"),
    ],
)
def test_v1_rejects_hidden_acceptance_and_acceptance_ready_requests(
    tmp_path: Path,
    evidence_scope: str,
    required_status: str,
    message: str,
) -> None:
    fixture = _fixture(tmp_path)
    isolation = copy.deepcopy(fixture["isolation"])
    isolation.update(
        {
            "evidence_scope": evidence_scope,
            "required_status": required_status,
            "provider_id": "test-kernel-boundary",
        }
    )
    with pytest.raises(ValueError, match=message):
        _rebuild_request(fixture, isolation=isolation)


def test_v1_result_can_never_claim_acceptance_ready(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(ValueError, match="isolation status"):
        build_separation_worker_result(
            worker_request=fixture["worker_request"],
            **_trusted(fixture),
            status="complete",
            after_input_hashes=_input_hashes(fixture["worker_request"]),
            outputs=_outputs(fixture),
            enforcement=_enforcement(fixture, status="acceptance_ready"),
            error=None,
        )


def test_blocked_result_is_path_free_and_cannot_claim_started_worker(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    enforcement = _enforcement(fixture, status="blocked")
    enforcement["checks"] = {key: "not_attempted" for key in enforcement["checks"]}
    enforcement["worker_started"] = False
    enforcement["inference_started"] = False
    result = build_separation_worker_result(
        worker_request=fixture["worker_request"],
        **_trusted(fixture),
        status="blocked",
        after_input_hashes=_input_hashes(fixture["worker_request"]),
        outputs=[],
        enforcement=enforcement,
        error={
            "code": "isolation_unavailable",
            "message": "Required isolation was unavailable",
            "retryable": False,
        },
    )
    assert result["status"] == "blocked"
    started = _plain(result)
    started["enforcement"]["worker_started"] = True
    _rehash_result(started)
    with pytest.raises(ValueError, match="blocked result"):
        validate_separation_worker_result(
            started,
            worker_request=fixture["worker_request"],
            **_trusted(fixture),
        )
