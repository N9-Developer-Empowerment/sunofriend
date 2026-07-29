from __future__ import annotations

import copy
import hashlib
import json
import os
import platform
import runpy
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
import sunofriend.separation_backend_preflight as backend_preflight

from sunofriend.separation_acceptance import (
    canonical_json_bytes,
    deployment_profile_id,
    separation_acceptance_artifact_sha256,
    validate_separation_acceptance_thresholds,
)
from sunofriend.separation_backend_preflight import (
    SEPARATION_BACKEND_PREFLIGHT_SCHEMA,
    preflight_separation_backend,
    separation_backend_preflight_sha256,
    validate_separation_backend_preflight,
)
from sunofriend.separation_bakeoff import (
    prepare_separation_bakeoff,
    separation_bakeoff_preparation_sha256,
)


_PACKAGE_NAME = "synthetic-package"
_PACKAGE_VERSION = "1.2.3"
_PACKAGE_COMMIT = hashlib.sha256(b"synthetic-package-commit").hexdigest()[:40]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _all_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict) or hasattr(value, "items"):
        result: list[str] = []
        for key, item in value.items():
            result.append(str(key))
            result.extend(_all_strings(item))
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            result.extend(_all_strings(item))
        return result
    return []


def _rehash_report(report: dict[str, Any]) -> None:
    identity_payload = {
        key: report[key]
        for key in (
            "schema",
            "status",
            "bindings",
            "arm",
            "probe",
            "checks",
            "blockers",
            "limitations",
            "effects",
        )
    }
    report["preflight_id"] = (
        "separation-backend-preflight:"
        + hashlib.sha256(canonical_json_bytes(identity_payload)).hexdigest()
    )
    report["preflight_sha256"] = separation_backend_preflight_sha256(
        report
    )


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _distribution_source_sha256(
    site_root: Path,
    relative_paths: list[str],
) -> str:
    """Mirror the registered installed-distribution byte algorithm.

    The v1 algorithm includes the complete installed package tree and stable
    distribution metadata. Only install-location/provenance metadata is
    excluded and bound separately.
    """

    digest = hashlib.sha256()
    selected: list[str] = []
    roots: set[str] = set()
    for relative in relative_paths:
        folded = relative.casefold()
        if folded.endswith(".dist-info/direct_url.json"):
            continue
        selected.append(relative)
        parts = Path(relative).parts
        if len(parts) > 1:
            if parts[0].casefold().endswith(".dist-info"):
                roots.add(parts[0])
            else:
                roots.add(parts[0])
    directories: list[str] = []
    for root in sorted(roots):
        root_path = site_root / root
        directories.append(root)
        for directory, child_directories, _files in os.walk(root_path):
            child_directories.sort()
            relative_directory = Path(directory).relative_to(
                site_root
            )
            if relative_directory.as_posix() != root:
                directories.append(relative_directory.as_posix())
    for relative in sorted(set(directories)):
        digest.update(b"directory\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
    for relative in sorted(selected):
        data = (site_root / relative).read_bytes()
        digest.update(b"file\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def _make_runtime(
    root: Path,
) -> dict[str, Any]:
    runtime_root = root / "runtime-env"
    bin_dir = runtime_root / "bin"
    bin_dir.mkdir(parents=True)
    launcher = bin_dir / "python"
    launcher.symlink_to(Path(sys.executable).resolve())
    (runtime_root / "pyvenv.cfg").write_text(
        "home = synthetic\n"
        f"version = {platform.python_version()}\n",
        encoding="utf-8",
    )

    python_tag = f"python{sys.version_info.major}.{sys.version_info.minor}"
    site_root = runtime_root / "lib" / python_tag / "site-packages"
    package_root = site_root / "synthetic_package"
    dist_info = site_root / "synthetic_package-1.2.3.dist-info"
    package_root.mkdir(parents=True)
    dist_info.mkdir(parents=True)

    import_trap = root / "package-imported.txt"
    pth_trap = root / "pth-executed.txt"
    init_relative = "synthetic_package/__init__.py"
    empty_relative = "synthetic_package/empty.py"
    metadata_relative = "synthetic_package-1.2.3.dist-info/METADATA"
    wheel_relative = "synthetic_package-1.2.3.dist-info/WHEEL"
    direct_relative = (
        "synthetic_package-1.2.3.dist-info/direct_url.json"
    )
    pth_relative = "synthetic_package_trap.pth"
    record_relative = "synthetic_package-1.2.3.dist-info/RECORD"
    relative_paths = [
        init_relative,
        empty_relative,
        metadata_relative,
        wheel_relative,
        direct_relative,
        pth_relative,
        record_relative,
    ]
    _write(
        site_root / init_relative,
        (
            "from pathlib import Path\n"
            f"Path({str(import_trap)!r}).write_text('imported')\n"
        ).encode("utf-8"),
    )
    _write(site_root / empty_relative, b"")
    _write(
        site_root / metadata_relative,
        (
            "Metadata-Version: 2.4\n"
            f"Name: {_PACKAGE_NAME}\n"
            f"Version: {_PACKAGE_VERSION}\n"
        ).encode("utf-8"),
    )
    _write(
        site_root / wheel_relative,
        (
            "Wheel-Version: 1.0\n"
            "Generator: synthetic-test\n"
            "Root-Is-Purelib: true\n"
            "Tag: py3-none-any\n"
        ).encode("utf-8"),
    )
    _write(
        site_root / direct_relative,
        canonical_json_bytes(
            {
                "url": "file:///private/synthetic/source",
                "vcs_info": {
                    "vcs": "git",
                    "commit_id": _PACKAGE_COMMIT,
                    "requested_revision": "main",
                },
            }
        ),
    )
    _write(
        site_root / pth_relative,
        (
            "import pathlib; "
            f"pathlib.Path({str(pth_trap)!r}).write_text('executed')\n"
        ).encode("utf-8"),
    )
    _write(
        site_root / record_relative,
        "".join(f"{relative},,\n" for relative in relative_paths).encode(
            "utf-8"
        ),
    )
    return {
        "runtime_root": runtime_root,
        "launcher": launcher,
        "site_root": site_root,
        "relative_paths": relative_paths,
        "init": site_root / init_relative,
        "metadata": site_root / metadata_relative,
        "direct_url": site_root / direct_relative,
        "import_trap": import_trap,
        "pth_trap": pth_trap,
        "package_source_sha256": _distribution_source_sha256(
            site_root, relative_paths
        ),
    }


def _base_acceptance_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    namespace = runpy.run_path(
        str(Path(__file__).with_name("test_separation_acceptance.py"))
    )
    acceptance, manifest = namespace["_fixture"]()
    return copy.deepcopy(acceptance), copy.deepcopy(manifest)


def _make_inputs(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    runtime = _make_runtime(root)
    worker = root / "separator-worker.py"
    dependency_lock = root / "separator.lock"
    checkpoint = root / "model.safetensors"
    worker_bytes = b"# synthetic metadata-only worker\n"
    lock_bytes = b"synthetic-package==1.2.3 --hash=sha256:fixture\n"
    checkpoint_bytes = b"synthetic checkpoint bytes; never deserialize\n"
    _write(worker, worker_bytes)
    _write(dependency_lock, lock_bytes)
    _write(checkpoint, checkpoint_bytes)

    acceptance, manifest = _base_acceptance_fixture()
    identity = acceptance["identities"]["candidate_separator"]
    identity["package_name"] = _PACKAGE_NAME
    identity["package_version"] = _PACKAGE_VERSION
    identity["package_commit"] = _PACKAGE_COMMIT
    identity["package_source_sha256"] = runtime[
        "package_source_sha256"
    ]
    identity["worker_sha256"] = _sha256(worker_bytes)
    identity["runtime"] = {
        "runtime_id": sys.implementation.name,
        "runtime_version": platform.python_version(),
        "python_version": platform.python_version(),
        "dependency_lock_sha256": _sha256(lock_bytes),
    }
    identity["device"] = {
        "platform": "macos",
        "machine": platform.machine(),
        "accelerator": "mps",
    }
    identity["checkpoint"]["format"] = "safetensors"
    identity["checkpoint"]["sha256"] = _sha256(checkpoint_bytes)
    identity["checkpoint"]["bytes"] = len(checkpoint_bytes)
    resource = acceptance["resource_gates"]["mac_classes"][0]
    resource["runtime"] = (
        f"{sys.implementation.name}-{platform.python_version()}"
    )
    resource["architecture"] = platform.machine()
    resource["device"] = "mps"
    acceptance["artifact_sha256"] = separation_acceptance_artifact_sha256(
        acceptance
    )
    acceptance = _plain(validate_separation_acceptance_thresholds(acceptance))

    acceptance_path = root / "acceptance.json"
    manifest_path = root / "hidden-manifest.json"
    preparation_path = root / "preparation.json"
    acceptance_path.write_bytes(canonical_json_bytes(acceptance))
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    preparation = prepare_separation_bakeoff(
        acceptance_path=acceptance_path,
        hidden_manifest_path=manifest_path,
    )
    preparation_path.write_bytes(canonical_json_bytes(preparation))
    return {
        **runtime,
        "worker": worker,
        "dependency_lock": dependency_lock,
        "checkpoint": checkpoint,
        "acceptance": acceptance,
        "manifest": manifest,
        "preparation": _plain(preparation),
        "acceptance_path": acceptance_path,
        "manifest_path": manifest_path,
        "preparation_path": preparation_path,
    }


def _run(inputs: dict[str, Any], **overrides: Any) -> Any:
    arguments = {
        "acceptance_path": inputs["acceptance_path"],
        "hidden_manifest_path": inputs["manifest_path"],
        "arm_id": "candidate",
        "runtime_python_path": inputs["launcher"],
        "worker_path": inputs["worker"],
        "dependency_lock_path": inputs["dependency_lock"],
        "checkpoint_path": inputs["checkpoint"],
    }
    arguments.update(overrides)
    return preflight_separation_backend(
        inputs["preparation_path"],
        **arguments,
    )


def _replace_acceptance(
    inputs: dict[str, Any],
    acceptance: dict[str, Any],
) -> None:
    acceptance["artifact_sha256"] = (
        separation_acceptance_artifact_sha256(acceptance)
    )
    acceptance = _plain(
        validate_separation_acceptance_thresholds(acceptance)
    )
    inputs["acceptance"] = acceptance
    inputs["acceptance_path"].write_bytes(canonical_json_bytes(acceptance))
    preparation = prepare_separation_bakeoff(
        acceptance_path=inputs["acceptance_path"],
        hidden_manifest_path=inputs["manifest_path"],
    )
    inputs["preparation"] = _plain(preparation)
    inputs["preparation_path"].write_bytes(
        canonical_json_bytes(preparation)
    )


def test_verified_preflight_is_deterministic_immutable_and_path_free(
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path)
    first = _run(inputs)
    second = _run(inputs)

    assert _plain(first) == _plain(second)
    assert first["schema"] == SEPARATION_BACKEND_PREFLIGHT_SCHEMA
    assert first["status"] == "verified_not_run"
    assert first["blockers"] == ()
    assert set(first["checks"].values()) == {"matched", "not_probed"}
    assert first["checks"]["runtime_metadata"] == "not_probed"
    assert first["probe"]["process_started"] is False
    assert first["arm"]["arm_id"] == "candidate"
    assert (
        first["arm"]["evaluation_scope"]
        == "private-local-evaluation-only"
    )
    assert tuple(first["limitations"]) == (
        "accelerator_availability_not_probed",
        "backend_importability_not_probed",
        "console_scripts_not_probed",
        "installed_dependencies_not_probed",
        "interpreter_identity_not_preregistered",
        "offline_gate_not_tested",
        "site_startup_code_outside_distribution_not_probed",
    )
    assert all(value is False for value in first["effects"].values())
    assert not inputs["import_trap"].exists()
    assert not inputs["pth_trap"].exists()

    with pytest.raises(TypeError):
        first["status"] = "passed"  # type: ignore[index]
    with pytest.raises(TypeError):
        first["effects"]["model_executed"] = True  # type: ignore[index]
    assert isinstance(first["limitations"], tuple)

    exposed = _all_strings(first)
    assert str(tmp_path) not in exposed
    assert not any(str(tmp_path) in value for value in exposed)
    for song in inputs["manifest"]["songs"]:
        assert song["song_id"] not in exposed
        assert song["song_identity_sha256"] not in exposed
        assert song["source_sha256"] not in exposed
        assert song["rights_evidence_sha256"] not in exposed
        for role in song["roles"]:
            assert role["ground_truth_sha256"] not in exposed
    assert not any(
        forbidden in exposed
        for forbidden in (
            "passed",
            "accepted",
            "promotion-ready",
            "promotion_ready",
        )
    )


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("commit", "package_commit_mismatch"),
        ("commit_missing", "package_commit_unverified"),
        ("source", "package_source_hash_mismatch"),
        ("version", "package_version_mismatch"),
    ],
)
def test_package_identity_and_provenance_fail_with_safe_codes(
    tmp_path: Path,
    case: str,
    expected: str,
) -> None:
    inputs = _make_inputs(tmp_path)
    if case == "commit":
        direct = json.loads(inputs["direct_url"].read_text(encoding="utf-8"))
        direct["vcs_info"]["commit_id"] = "f" * 40
        inputs["direct_url"].write_bytes(canonical_json_bytes(direct))
    elif case == "commit_missing":
        inputs["direct_url"].write_bytes(
            canonical_json_bytes(
                {"url": "file:///private/synthetic/source"}
            )
        )
    elif case == "source":
        inputs["init"].write_bytes(
            inputs["init"].read_bytes() + b"# changed without import\n"
        )
    else:
        metadata = inputs["metadata"].read_text(encoding="utf-8")
        inputs["metadata"].write_text(
            metadata.replace("Version: 1.2.3", "Version: 9.9.9"),
            encoding="utf-8",
        )

    report = _run(inputs)
    assert report["status"] == "blocked"
    assert expected in report["blockers"]
    assert all(
        value.replace("_", "").isalnum() for value in report["blockers"]
    )
    assert str(tmp_path) not in _all_strings(report)
    assert all(value is False for value in report["effects"].values())
    assert not inputs["import_trap"].exists()
    assert not inputs["pth_trap"].exists()


@pytest.mark.parametrize(
    ("artifact", "mutation", "expected"),
    [
        ("worker", "missing", "worker_missing"),
        ("worker", "symlink", "worker_unsafe"),
        ("worker", "mismatch", "worker_hash_mismatch"),
        (
            "dependency_lock",
            "missing",
            "dependency_lock_missing",
        ),
        (
            "dependency_lock",
            "symlink",
            "dependency_lock_unsafe",
        ),
        (
            "dependency_lock",
            "mismatch",
            "dependency_lock_hash_mismatch",
        ),
        ("checkpoint", "missing", "checkpoint_missing"),
        ("checkpoint", "symlink", "checkpoint_unsafe"),
        ("checkpoint", "mismatch", "checkpoint_hash_mismatch"),
    ],
)
def test_local_identity_files_block_safely(
    tmp_path: Path,
    artifact: str,
    mutation: str,
    expected: str,
) -> None:
    inputs = _make_inputs(tmp_path)
    path = inputs[artifact]
    if mutation == "missing":
        path.unlink()
    elif mutation == "symlink":
        data = path.read_bytes()
        path.unlink()
        target = tmp_path / f"{artifact}-symlink-target"
        target.write_bytes(data)
        path.symlink_to(target)
    else:
        data = path.read_bytes()
        changed = bytes([data[0] ^ 1]) + data[1:]
        path.write_bytes(changed)

    report = _run(inputs)
    assert report["status"] == "blocked"
    assert expected in report["blockers"]
    assert str(path) not in _all_strings(report)
    assert all(value is False for value in report["effects"].values())


@pytest.mark.parametrize("case", ["missing", "broken_symlink"])
def test_missing_or_broken_runtime_launcher_is_a_safe_blocker(
    tmp_path: Path,
    case: str,
) -> None:
    inputs = _make_inputs(tmp_path)
    launcher = inputs["launcher"]
    launcher.unlink()
    if case == "broken_symlink":
        launcher.symlink_to(tmp_path / "does-not-exist")

    report = _run(inputs)
    assert report["status"] == "blocked"
    assert "runtime_launcher_missing" in report["blockers"]
    assert report["probe"]["process_started"] is False
    assert str(launcher) not in _all_strings(report)
    assert all(value is False for value in report["effects"].values())


def test_executable_script_cannot_masquerade_as_runtime(
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path)
    launcher = inputs["launcher"]
    launcher.unlink()
    launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    launcher.chmod(0o755)

    report = _run(inputs)
    assert report["status"] == "blocked"
    assert "runtime_launcher_unsafe" in report["blockers"]
    assert report["checks"]["runtime_metadata"] == "blocked"
    assert report["checks"]["package_source"] == "not_probed"
    assert report["probe"]["process_started"] is False


def test_invalid_arm_and_tampered_bound_contract_raise(
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path)
    with pytest.raises(ValueError, match="arm_id"):
        _run(inputs, arm_id="control")

    preparation = copy.deepcopy(inputs["preparation"])
    preparation["orchestration"]["arms"][1][
        "separator_identity_id"
    ] = "forged-candidate"
    identity_payload = {
        "schema": preparation["schema"],
        "status": preparation["status"],
        "acceptance": preparation["acceptance"],
        "hidden_evaluation": preparation["hidden_evaluation"],
        "orchestration": preparation["orchestration"],
        "effects": preparation["effects"],
    }
    preparation["preparation_id"] = (
        "separation-bakeoff-preparation:"
        + hashlib.sha256(canonical_json_bytes(identity_payload)).hexdigest()
    )
    preparation["preparation_sha256"] = (
        separation_bakeoff_preparation_sha256(preparation)
    )
    inputs["preparation_path"].write_bytes(canonical_json_bytes(preparation))
    with pytest.raises(ValueError, match="reverified frozen inputs"):
        _run(inputs)


def test_report_hash_detects_tampering(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = _plain(_run(inputs))
    original = report["preflight_sha256"]
    report["preflight_sha256"] = hashlib.sha256(b"forged").hexdigest()

    assert separation_backend_preflight_sha256(report) == original
    with pytest.raises(ValueError, match="preflight_sha256"):
        validate_separation_backend_preflight(report)


def test_acceptance_tamper_is_rejected_before_local_probe(
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path)
    acceptance = copy.deepcopy(inputs["acceptance"])
    acceptance["status"] = "passed"
    inputs["acceptance_path"].write_bytes(canonical_json_bytes(acceptance))

    with pytest.raises(ValueError):
        _run(inputs)
    assert not inputs["import_trap"].exists()
    assert not inputs["pth_trap"].exists()


def test_runtime_launcher_must_be_an_absolute_path(tmp_path: Path) -> None:
    inputs = _make_inputs(tmp_path)
    report = _run(inputs, runtime_python_path=Path("runtime-env/bin/python"))

    assert report["status"] == "blocked"
    assert "runtime_launcher_unsafe" in report["blockers"]
    assert report["probe"]["process_started"] is False


def test_checkpoint_extension_is_bound_without_deserialising(
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path)
    wrong_extension = tmp_path / "model.bin"
    os.replace(inputs["checkpoint"], wrong_extension)

    report = _run(inputs, checkpoint_path=wrong_extension)
    assert report["status"] == "blocked"
    assert "checkpoint_format_mismatch" in report["blockers"]
    assert report["effects"]["checkpoint_deserialized"] is False
    assert report["effects"]["checkpoint_loaded"] is False


def test_validator_rejects_forged_check_mapping_and_started_process(
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path)
    forged_checks = _plain(_run(inputs))
    forged_checks["checks"]["worker"] = "blocked"
    _rehash_report(forged_checks)
    with pytest.raises(ValueError, match="checks do not match blockers"):
        validate_separation_backend_preflight(forged_checks)

    started = _plain(_run(inputs))
    started["probe"]["process_started"] = True
    _rehash_report(started)
    with pytest.raises(ValueError, match="probe evidence"):
        validate_separation_backend_preflight(started)


def test_validator_rejects_embedded_private_path_before_hash_check(
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path)
    report = _plain(_run(inputs))
    report["arm"]["backend_id"] = "candidate:/Users/private/backend"

    with pytest.raises(ValueError, match="private path"):
        validate_separation_backend_preflight(report)


def test_deterministic_no_checkpoint_baseline_can_verify(
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path)
    acceptance = copy.deepcopy(inputs["acceptance"])
    baseline = acceptance["identities"]["baseline_separator"]
    candidate = acceptance["identities"]["candidate_separator"]
    for key in (
        "package_name",
        "package_version",
        "package_commit",
        "package_source_sha256",
        "worker_sha256",
        "runtime",
        "device",
    ):
        baseline[key] = copy.deepcopy(candidate[key])
    baseline["checkpoint"] = {
        "kind": "deterministic-no-checkpoint",
        "reason_code": "deterministic-no-checkpoint",
    }
    acceptance["licence_gate"]["entries"] = [
        entry
        for entry in acceptance["licence_gate"]["entries"]
        if entry["subject_id"] != "baseline-separator:weights"
    ]
    _replace_acceptance(inputs, acceptance)

    report = _run(
        inputs,
        arm_id="baseline",
        checkpoint_path=None,
    )
    assert report["status"] == "verified_not_run"
    assert report["arm"]["checkpoint_id"] == "deterministic-no-checkpoint"
    assert report["arm"]["checkpoint_format"] == "none"
    assert report["checks"]["checkpoint"] == "matched"


def test_requested_derived_output_redistribution_blocks_private_scope(
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path)
    acceptance = copy.deepcopy(inputs["acceptance"])
    deployment = acceptance["deployment_profile"]
    deployment["derived_output_redistribution_requested"] = True
    acceptance["profile_id"] = deployment_profile_id(deployment)
    acceptance["licence_gate"]["deployment_profile_id"] = acceptance[
        "profile_id"
    ]
    _replace_acceptance(inputs, acceptance)

    report = _run(inputs)
    assert report["status"] == "blocked"
    assert "deployment_scope_unsupported" in report["blockers"]
    assert report["checks"]["licence_policy"] == "blocked"


def test_package_source_directory_symlink_is_rejected(
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path)
    package_root = inputs["site_root"] / "synthetic_package"
    outside = tmp_path / "outside-package"
    package_root.rename(outside)
    package_root.symlink_to(outside, target_is_directory=True)

    report = _run(inputs)
    assert report["status"] == "blocked"
    assert "package_inventory_unsafe" in report["blockers"]
    assert report["checks"]["package_source"] == "blocked"
    assert not inputs["import_trap"].exists()


def test_executable_pth_and_undeclared_package_files_are_bound(
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path)
    pth = inputs["site_root"] / "synthetic_package_trap.pth"
    pth.write_text(
        "import pathlib; pathlib.Path('/tmp/other').write_text('x')\n",
        encoding="utf-8",
    )
    pth_report = _run(inputs)
    assert "package_source_hash_mismatch" in pth_report["blockers"]
    assert not inputs["pth_trap"].exists()

    inputs = _make_inputs(tmp_path / "undeclared")
    undeclared = (
        inputs["site_root"] / "synthetic_package" / "undeclared.py"
    )
    undeclared.write_text("VALUE = 'not in RECORD'\n", encoding="utf-8")
    undeclared_report = _run(inputs)
    assert (
        "package_source_hash_mismatch"
        in undeclared_report["blockers"]
    )


def test_duplicate_distribution_blocks_all_package_identity_checks(
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path)
    original = (
        inputs["site_root"] / "synthetic_package-1.2.3.dist-info"
    )
    duplicate = (
        inputs["site_root"] / "synthetic_package-copy.dist-info"
    )
    shutil.copytree(original, duplicate)

    report = _run(inputs)
    assert "package_inventory_unsafe" in report["blockers"]
    for check_id in (
        "package_metadata_identity",
        "package_provenance",
        "package_source",
    ):
        assert report["checks"][check_id] == "blocked"


@pytest.mark.parametrize("editable", [1, "true", None])
def test_malformed_editable_install_metadata_is_rejected(
    tmp_path: Path,
    editable: Any,
) -> None:
    inputs = _make_inputs(tmp_path)
    direct = json.loads(inputs["direct_url"].read_text(encoding="utf-8"))
    direct["dir_info"] = {"editable": editable}
    inputs["direct_url"].write_bytes(canonical_json_bytes(direct))

    report = _run(inputs)
    assert "package_inventory_unsafe" in report["blockers"]
    assert report["checks"]["package_provenance"] == "blocked"


def test_pyvenv_evidence_replacement_is_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _make_inputs(tmp_path)
    original = backend_preflight._read_file_evidence

    def replace_after_read(*args: Any, **kwargs: Any) -> Any:
        evidence = original(*args, **kwargs)
        path = Path(args[0])
        if path.name == "pyvenv.cfg" and evidence is not None:
            path.write_bytes(evidence.data + b"changed = yes\n")
        return evidence

    monkeypatch.setattr(
        backend_preflight,
        "_read_file_evidence",
        replace_after_read,
    )
    report = _run(inputs)
    assert "runtime_launcher_changed" in report["blockers"]
    assert report["checks"]["runtime_metadata"] == "blocked"


@pytest.mark.parametrize(
    ("suffix", "replacement"),
    [
        ("/METADATA", b"X-Changed: yes\n"),
        ("/RECORD", b"synthetic_package/extra.py,,\n"),
        (
            "/direct_url.json",
            canonical_json_bytes(
                {
                    "url": "file:///private/synthetic/replaced",
                    "vcs_info": {
                        "vcs": "git",
                        "commit_id": "f" * 40,
                    },
                }
            ),
        ),
    ],
)
def test_package_evidence_replacement_is_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    replacement: bytes,
) -> None:
    inputs = _make_inputs(tmp_path)
    original = backend_preflight._read_package_file_evidence

    def replace_after_read(*args: Any, **kwargs: Any) -> Any:
        evidence = original(*args, **kwargs)
        relative = str(args[1])
        if relative.endswith(suffix) and evidence is not None:
            path = Path(args[0]) / relative
            if suffix == "/direct_url.json":
                path.write_bytes(replacement)
            else:
                path.write_bytes(evidence.data + replacement)
        return evidence

    monkeypatch.setattr(
        backend_preflight,
        "_read_package_file_evidence",
        replace_after_read,
    )
    report = _run(inputs)
    assert "package_inventory_unsafe" in report["blockers"]
    for check_id in (
        "package_metadata_identity",
        "package_provenance",
        "package_source",
    ):
        assert report["checks"][check_id] == "blocked"


@pytest.mark.parametrize(
    ("artifact", "expected"),
    [
        ("worker", "worker_changed"),
        ("dependency_lock", "dependency_lock_changed"),
        ("checkpoint", "checkpoint_changed"),
    ],
)
def test_local_artifact_post_hash_change_is_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact: str,
    expected: str,
) -> None:
    inputs = _make_inputs(tmp_path)
    original = backend_preflight._measure_file

    def replace_after_measure(*args: Any, **kwargs: Any) -> Any:
        evidence = original(*args, **kwargs)
        if kwargs["label"] == artifact and evidence is not None:
            path = Path(args[0])
            path.write_bytes(path.read_bytes() + b"late change\n")
        return evidence

    monkeypatch.setattr(
        backend_preflight,
        "_measure_file",
        replace_after_measure,
    )
    report = _run(inputs)
    assert expected in report["blockers"]


def test_package_file_post_hash_change_is_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _make_inputs(tmp_path)
    original = backend_preflight._stream_package_file_into_digest

    def replace_after_stream(*args: Any, **kwargs: Any) -> Any:
        evidence = original(*args, **kwargs)
        if (
            kwargs["relative"] == "synthetic_package/__init__.py"
            and evidence is not None
        ):
            path = Path(args[0]) / str(args[1])
            path.write_bytes(path.read_bytes() + b"# late change\n")
        return evidence

    monkeypatch.setattr(
        backend_preflight,
        "_stream_package_file_into_digest",
        replace_after_stream,
    )
    report = _run(inputs)
    assert "package_inventory_unsafe" in report["blockers"]
    assert report["checks"]["package_source"] == "blocked"


def test_post_inventory_file_creation_is_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _make_inputs(tmp_path)
    original = backend_preflight._inventory_package_roots

    def add_after_inventory(*args: Any, **kwargs: Any) -> Any:
        evidence = original(*args, **kwargs)
        late = Path(args[0]) / "synthetic_package" / "late.py"
        late.write_text("LATE = True\n", encoding="utf-8")
        return evidence

    monkeypatch.setattr(
        backend_preflight,
        "_inventory_package_roots",
        add_after_inventory,
    )
    report = _run(inputs)
    assert "package_inventory_unsafe" in report["blockers"]


def test_empty_package_directory_changes_tree_digest(
    tmp_path: Path,
) -> None:
    inputs = _make_inputs(tmp_path)
    empty = inputs["site_root"] / "synthetic_package" / "resources"
    empty.mkdir()

    report = _run(inputs)
    assert "package_source_hash_mismatch" in report["blockers"]
