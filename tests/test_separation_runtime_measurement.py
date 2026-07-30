from __future__ import annotations

import ast
import hashlib
import inspect
import os
import runpy
import shutil
import threading
from pathlib import Path
from typing import Any

import pytest
import sunofriend.separation_runtime_measurement as measurement_module

from sunofriend.separation_runtime_artifact import (
    SeparationRuntimeArtifactParentEvidence,
    separation_runtime_launcher_chain_sha256,
)
from sunofriend.separation_runtime_measurement import (
    SeparationRuntimeMeasurement,
    SeparationRuntimeTrustedRequest,
    bind_separation_runtime_request,
    measure_separation_runtime,
    remeasure_separation_runtime,
)
from sunofriend.separation_worker_contract import (
    SeparationRuntimeArtifactIdentity,
    build_separation_worker_request,
    separation_worker_request_sha256,
)


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _facts(path: Path) -> dict[str, int]:
    value = path.lstat()
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "mode": value.st_mode,
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
        "ctime_ns": value.st_ctime_ns,
    }


def _plain(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _fixture(tmp_path: Path) -> dict[str, Any]:
    namespace = runpy.run_path(
        str(Path(__file__).with_name("test_separation_worker_contract.py"))
    )
    fixture = namespace["_fixture"](tmp_path / "worker-contract")
    launcher = fixture["inputs"]["launcher"]
    raw_target = os.readlink(launcher)
    target = Path(raw_target)
    if not target.is_absolute():
        target = launcher.parent / target
    target = Path(os.path.abspath(target))
    target_bytes = target.read_bytes()
    chain = [
        {
            "canonical_path": str(launcher),
            "kind": "symlink",
            "lstat": _facts(launcher),
            "raw_target": raw_target,
            "canonical_resolved_target": str(target),
        },
        {
            "canonical_path": str(target),
            "kind": "native_executable",
            "lstat": _facts(target),
            "raw_target": None,
            "canonical_resolved_target": str(target),
        },
    ]
    identity = SeparationRuntimeArtifactIdentity(
        path=launcher,
        sha256=_sha_bytes(target_bytes),
        bytes=len(target_bytes),
        verified_launcher_chain_sha256=(
            separation_runtime_launcher_chain_sha256(chain)
        ),
    )
    fixture["runtime_artifact"] = identity
    fixture["worker_request"] = namespace["_rebuild_request"](fixture)
    fixture["namespace"] = namespace
    _rebind(fixture)
    return fixture


def _kwargs(fixture: dict[str, Any]) -> dict[str, Any]:
    return {
        "trusted_request": fixture["trusted_request"],
        "trusted_preflight": fixture["preflight"],
        "trusted_acceptance": fixture["acceptance"],
        "trusted_separation_request": fixture["separation_request"],
        "trusted_runtime_artifact": fixture["runtime_artifact"],
    }


def _rebind(fixture: dict[str, Any]) -> None:
    fixture["trusted_request"] = bind_separation_runtime_request(
        fixture["worker_request"],
        trusted_preflight=fixture["preflight"],
        trusted_acceptance=fixture["acceptance"],
        trusted_separation_request=fixture["separation_request"],
        trusted_runtime_artifact=fixture["runtime_artifact"],
    )


def _build_request(
    fixture: dict[str, Any],
    *,
    worker_path: Path | None = None,
    dependency_lock_path: Path | None = None,
) -> Any:
    request = fixture["worker_request"]
    identities = request["identities"]
    return build_separation_worker_request(
        preflight=fixture["preflight"],
        trusted_acceptance=fixture["acceptance"],
        separation_request=fixture["separation_request"],
        worker_path=worker_path or fixture["inputs"]["worker"],
        trusted_runtime_artifact=fixture["runtime_artifact"],
        dependency_lock_path=(
            dependency_lock_path or fixture["inputs"]["dependency_lock"]
        ),
        source_bytes=identities["source"]["bytes"],
        checkpoint_bytes=identities["checkpoint"]["bytes"],
        worker_sha256=identities["worker"]["sha256"],
        worker_bytes=identities["worker"]["bytes"],
        runtime_id=identities["runtime"]["runtime_id"],
        runtime_version=identities["runtime"]["runtime_version"],
        python_version=identities["runtime"]["python_version"],
        dependency_lock_sha256=identities["dependency_lock"]["sha256"],
        dependency_lock_bytes=identities["dependency_lock"]["bytes"],
        isolation=_plain(request["isolation"]),
    )


def test_measures_and_remeasures_without_importing_package_startup_code(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    result = measure_separation_runtime(fixture["worker_request"], **_kwargs(fixture))
    repeated = remeasure_separation_runtime(
        result,
        fixture["worker_request"],
        **_kwargs(fixture),
    )

    assert type(result) is SeparationRuntimeMeasurement
    assert type(fixture["trusted_request"]) is SeparationRuntimeTrustedRequest
    assert type(result.parent_evidence) is SeparationRuntimeArtifactParentEvidence
    assert repeated.parent_evidence == result.parent_evidence
    assert repeated.artifact["artifact_sha256"] == result.artifact["artifact_sha256"]
    assert result.artifact["status"] == "private_development_unregistered"
    assert result.artifact["acceptance_eligible"] is False
    assert (
        result.artifact["registration"]["runtime_artifact_sha256_registered"] is False
    )
    assert (
        result.artifact["registration"]["reason_code"]
        == "static-preflight-v1-lacks-runtime-artifact-sha256"
    )
    assert (
        result.artifact["registration"]["evidence_kind"]
        == "parent_asserted_contract_evidence"
    )
    assert result.artifact["registration"]["execution_proven"] is False
    assert result.artifact["registration"]["toctou_closed"] is False
    assert result.artifact["registration"]["remeasure_before_exec_required"] is True
    assert not fixture["inputs"]["import_trap"].exists()
    assert not fixture["inputs"]["pth_trap"].exists()
    with pytest.raises(TypeError):
        result.artifact["runtime"]["site_packages"]["package_tree_sha256"] = "0" * 64  # type: ignore[index]


def test_requires_exact_parent_record_and_rebuilds_validated_frozen_binding(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    kwargs = _kwargs(fixture)
    ordinary_mapping = _plain(fixture["trusted_request"].request)
    kwargs["trusted_request"] = ordinary_mapping

    with pytest.raises(ValueError, match="exact parent-owned record"):
        measure_separation_runtime(fixture["worker_request"], **kwargs)
    with pytest.raises(TypeError):
        SeparationRuntimeTrustedRequest(
            request=fixture["worker_request"],
            request_sha256=fixture["worker_request"]["request_sha256"],
            preflight_sha256=fixture["preflight"]["preflight_sha256"],
            runtime_python_path=fixture["inputs"]["launcher"],
            worker_path=fixture["inputs"]["worker"],
            dependency_lock_path=fixture["inputs"]["dependency_lock"],
        )

    rebuilt = measurement_module._trusted_request_binding(  # noqa: SLF001
        fixture["trusted_request"],
        trusted_preflight=fixture["preflight"],
        trusted_acceptance=fixture["acceptance"],
        trusted_separation_request=fixture["separation_request"],
        trusted_runtime_artifact=fixture["runtime_artifact"],
    )
    assert rebuilt is not fixture["trusted_request"]
    with pytest.raises(TypeError):
        rebuilt.request["request_sha256"] = "0" * 64  # type: ignore[index]

    forged = object.__new__(SeparationRuntimeTrustedRequest)
    for name in (
        "request",
        "request_sha256",
        "preflight_sha256",
        "runtime_python_path",
        "worker_path",
        "dependency_lock_path",
    ):
        object.__setattr__(
            forged,
            name,
            getattr(fixture["trusted_request"], name),
        )
    forged_kwargs = _kwargs(fixture)
    forged_kwargs["trusted_request"] = forged
    with pytest.raises(ValueError, match="lacks parent-process authority"):
        measure_separation_runtime(
            fixture["worker_request"],
            **forged_kwargs,
        )


def test_remeasurement_requires_an_issued_parent_measurement(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    issued = measure_separation_runtime(
        fixture["worker_request"],
        **_kwargs(fixture),
    )
    forged = object.__new__(SeparationRuntimeMeasurement)
    object.__setattr__(forged, "parent_evidence", issued.parent_evidence)
    object.__setattr__(forged, "artifact", issued.artifact)
    object.__setattr__(
        forged,
        "_authority",
        fixture["trusted_request"]._authority,  # noqa: SLF001
    )

    with pytest.raises(ValueError, match="lacks parent-process authority"):
        remeasure_separation_runtime(
            forged,
            fixture["worker_request"],
            **_kwargs(fixture),
        )


def test_worker_and_lock_paths_can_only_come_from_trusted_request(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    replacement = fixture["inputs"]["worker"].with_name("replacement-worker.py")
    replacement.write_bytes(fixture["inputs"]["worker"].read_bytes())
    forged = _plain(fixture["worker_request"])
    forged["paths"]["worker_path"] = str(replacement)
    forged["request_sha256"] = separation_worker_request_sha256(forged)

    with pytest.raises(ValueError, match="substituted after parent validation"):
        measure_separation_runtime(forged, **_kwargs(fixture))


def test_rejects_replacement_during_descriptor_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    worker = fixture["inputs"]["worker"]
    worker_inode = worker.lstat().st_ino
    original_read = measurement_module.os.read
    changed = False

    def replacing_read(descriptor: int, size: int) -> bytes:
        nonlocal changed
        chunk = original_read(descriptor, size)
        if chunk and not changed and os.fstat(descriptor).st_ino == worker_inode:
            changed = True
            worker.write_bytes(b"X" * worker.lstat().st_size)
        return chunk

    monkeypatch.setattr(measurement_module.os, "read", replacing_read)
    with pytest.raises(ValueError, match="changed during descriptor hashing"):
        measure_separation_runtime(fixture["worker_request"], **_kwargs(fixture))
    assert changed


def test_fifo_swap_cannot_block_or_replace_a_regular_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    worker = fixture["inputs"]["worker"]
    original_open = measurement_module.os.open
    replaced = False

    def replacing_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        if Path(path) == worker and not replaced:
            replaced = True
            worker.unlink()
            os.mkfifo(worker)
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(measurement_module.os, "open", replacing_open)
    with pytest.raises(ValueError, match="changed before descriptor read"):
        measure_separation_runtime(fixture["worker_request"], **_kwargs(fixture))
    assert replaced


def test_rejects_leaf_symlink_hardlink_and_ancestor_symlink(
    tmp_path: Path,
) -> None:
    symlink_fixture = _fixture(tmp_path / "leaf")
    worker = symlink_fixture["inputs"]["worker"]
    linked_worker = worker.with_name("linked-worker.py")
    linked_worker.symlink_to(worker.name)
    request = _build_request(symlink_fixture, worker_path=linked_worker)
    symlink_fixture["worker_request"] = request
    _rebind(symlink_fixture)
    with pytest.raises(ValueError, match="regular file"):
        measure_separation_runtime(request, **_kwargs(symlink_fixture))

    hardlink_fixture = _fixture(tmp_path / "hardlink")
    site_root = hardlink_fixture["inputs"]["site_root"]
    os.link(
        hardlink_fixture["inputs"]["init"],
        site_root / "hardlink-alias.py",
    )
    with pytest.raises(
        ValueError,
        match="device/inode alias|hardlink aliases",
    ):
        measure_separation_runtime(
            hardlink_fixture["worker_request"],
            **_kwargs(hardlink_fixture),
        )

    ancestor_fixture = _fixture(tmp_path / "ancestor")
    worker = ancestor_fixture["inputs"]["worker"]
    alias_parent = worker.parent.parent / "worker-parent-alias"
    alias_parent.symlink_to(worker.parent, target_is_directory=True)
    alias_worker = alias_parent / worker.name
    request = _build_request(ancestor_fixture, worker_path=alias_worker)
    ancestor_fixture["worker_request"] = request
    _rebind(ancestor_fixture)
    with pytest.raises(ValueError, match="ancestor must be a real directory"):
        measure_separation_runtime(request, **_kwargs(ancestor_fixture))


def test_rejects_unmeasured_external_hardlink_alias(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    external_alias = tmp_path / "outside-runtime-tree.py"
    os.link(fixture["inputs"]["worker"], external_alias)

    with pytest.raises(ValueError, match="must not have hardlink aliases"):
        measure_separation_runtime(fixture["worker_request"], **_kwargs(fixture))


def test_rejects_launcher_symlink_with_external_hardlink_alias(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    launcher = fixture["inputs"]["launcher"]
    alias = tmp_path / "launcher-symlink-alias"
    os.link(launcher, alias, follow_symlinks=False)

    with pytest.raises(ValueError, match="symlink has hardlink aliases"):
        measure_separation_runtime(fixture["worker_request"], **_kwargs(fixture))


@pytest.mark.parametrize("setting", ["missing", "true", "duplicate"])
def test_rejects_unsafe_system_site_package_configuration_and_does_not_import(
    tmp_path: Path,
    setting: str,
) -> None:
    fixture = _fixture(tmp_path / setting)
    config = fixture["inputs"]["runtime_root"] / "pyvenv.cfg"
    text = config.read_text(encoding="utf-8")
    if setting == "missing":
        text = text.replace("include-system-site-packages = false\n", "")
    elif setting == "true":
        text = text.replace(
            "include-system-site-packages = false",
            "include-system-site-packages = true",
        )
    else:
        text += "include-system-site-packages = false\n"
    config.write_text(text, encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="disable system site packages|ambiguous keys",
    ):
        measure_separation_runtime(fixture["worker_request"], **_kwargs(fixture))
    assert not fixture["inputs"]["pth_trap"].exists()
    assert not fixture["inputs"]["import_trap"].exists()


def test_accepts_zero_byte_site_package_files_as_measured_content(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    empty = fixture["inputs"]["site_root"] / "synthetic_package" / "empty.py"
    assert empty.stat().st_size == 0

    result = measure_separation_runtime(
        fixture["worker_request"],
        **_kwargs(fixture),
    )

    assert (
        result.artifact["runtime"]["site_packages"]["package_tree_algorithm"]
        == "runtime-site-tree-stability-sha256-v1"
    )


def test_tree_mutation_invalidates_immediate_remeasurement(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    first = measure_separation_runtime(fixture["worker_request"], **_kwargs(fixture))
    empty = fixture["inputs"]["site_root"] / "new-empty-directory"
    empty.mkdir()

    with pytest.raises(
        ValueError,
        match="remeasurement changed|runtime node changed",
    ):
        remeasure_separation_runtime(
            first,
            fixture["worker_request"],
            **_kwargs(fixture),
        )


def test_unrelated_ancestor_sibling_churn_does_not_invalidate_identity(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path / "runtime")
    sibling = tmp_path / "unrelated-sibling.tmp"
    started = threading.Event()
    stop = threading.Event()
    errors: list[BaseException] = []

    def churn() -> None:
        try:
            counter = 0
            while not stop.is_set():
                sibling.write_bytes(str(counter).encode("ascii"))
                started.set()
                sibling.unlink(missing_ok=True)
                counter += 1
        except BaseException as exc:  # pragma: no cover - diagnostic guard
            errors.append(exc)
            started.set()

    thread = threading.Thread(target=churn, daemon=True)
    thread.start()
    assert started.wait(timeout=2)
    try:
        first = measure_separation_runtime(
            fixture["worker_request"],
            **_kwargs(fixture),
        )
        repeated = remeasure_separation_runtime(
            first,
            fixture["worker_request"],
            **_kwargs(fixture),
        )
    finally:
        stop.set()
        thread.join(timeout=2)
        sibling.unlink(missing_ok=True)

    assert not thread.is_alive()
    assert errors == []
    assert repeated.artifact["artifact_sha256"] == first.artifact["artifact_sha256"]
    for ancestor in repeated.artifact["runtime"]["ancestor_directories"]:
        facts = ancestor["lstat"]
        assert (facts["size"], facts["mtime_ns"], facts["ctime_ns"]) == (0, 0, 0)


@pytest.mark.parametrize("mutation", ["inode", "mode", "directory"])
def test_site_identity_facts_invalidate_remeasurement(
    tmp_path: Path,
    mutation: str,
) -> None:
    fixture = _fixture(tmp_path / mutation)
    first = measure_separation_runtime(
        fixture["worker_request"],
        **_kwargs(fixture),
    )
    site_root = fixture["inputs"]["site_root"]
    if mutation == "inode":
        target = fixture["inputs"]["init"]
        replacement = target.with_name("same-bytes-replacement.py")
        replacement.write_bytes(target.read_bytes())
        os.replace(replacement, target)
    elif mutation == "mode":
        target = fixture["inputs"]["init"]
        target.chmod(target.stat().st_mode ^ 0o100)
    else:
        target = site_root / "synthetic_package"
        saved = site_root / "synthetic_package-saved"
        target.rename(saved)
        shutil.copytree(saved, target)

    with pytest.raises(
        ValueError,
        match="remeasurement changed|runtime node changed",
    ):
        remeasure_separation_runtime(
            first,
            fixture["worker_request"],
            **_kwargs(fixture),
        )


@pytest.mark.parametrize("mutation", ["add", "delete", "rename"])
def test_site_enumeration_races_are_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    fixture = _fixture(tmp_path / mutation)
    site_root = fixture["inputs"]["site_root"]
    root_inode = site_root.lstat().st_ino
    original_scan = measurement_module._scan_site_directory_entries
    root_scans = 0

    def racing_scan(
        descriptor: int,
        *,
        maximum_entries: int,
    ) -> Any:
        nonlocal root_scans
        if os.fstat(descriptor).st_ino == root_inode:
            root_scans += 1
            if root_scans == 2:
                target = site_root / "synthetic_package_trap.pth"
                if mutation == "add":
                    (site_root / "late-empty-directory").mkdir()
                elif mutation == "delete":
                    target.unlink()
                else:
                    target.rename(site_root / "renamed-trap.pth")
        return original_scan(descriptor, maximum_entries=maximum_entries)

    monkeypatch.setattr(
        measurement_module,
        "_scan_site_directory_entries",
        racing_scan,
    )
    with pytest.raises(
        ValueError,
        match="entries changed|bounded node count",
    ):
        measure_separation_runtime(fixture["worker_request"], **_kwargs(fixture))
    assert root_scans == 2


def test_site_tree_rejects_cross_device_descendant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    site_root = fixture["inputs"]["site_root"]
    root_inode = site_root.lstat().st_ino
    original_scan = measurement_module._scan_site_directory_entries
    changed = False

    def cross_device_scan(
        descriptor: int,
        *,
        maximum_entries: int,
    ) -> Any:
        nonlocal changed
        entries = original_scan(descriptor, maximum_entries=maximum_entries)
        if os.fstat(descriptor).st_ino == root_inode and not changed:
            changed = True
            name, facts = entries[0]
            replacement = (facts[0] + 1, *facts[1:])
            return ((name, replacement), *entries[1:])
        return entries

    monkeypatch.setattr(
        measurement_module,
        "_scan_site_directory_entries",
        cross_device_scan,
    )
    with pytest.raises(ValueError, match="crosses a device boundary"):
        measure_separation_runtime(fixture["worker_request"], **_kwargs(fixture))
    assert changed


@pytest.mark.parametrize("replacement", ["ancestor", "subdirectory"])
def test_pinned_tree_rejects_directory_replacement_during_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: str,
) -> None:
    fixture = _fixture(tmp_path / replacement)
    site_root = fixture["inputs"]["site_root"]
    package = site_root / "synthetic_package"
    target = site_root if replacement == "ancestor" else package
    target_inode = target.lstat().st_ino
    original_scan = measurement_module._scan_site_directory_entries
    changed = False

    def replacing_scan(
        descriptor: int,
        *,
        maximum_entries: int,
    ) -> Any:
        nonlocal changed
        if os.fstat(descriptor).st_ino == target_inode and not changed:
            changed = True
            if replacement == "ancestor":
                ancestor = site_root.parent
                saved = ancestor.with_name(f"{ancestor.name}-saved")
                ancestor.rename(saved)
                site_root.mkdir(parents=True)
            else:
                saved = package.with_name("synthetic_package-saved")
                package.rename(saved)
                shutil.copytree(saved, package)
        return original_scan(descriptor, maximum_entries=maximum_entries)

    monkeypatch.setattr(
        measurement_module,
        "_scan_site_directory_entries",
        replacing_scan,
    )
    with pytest.raises(ValueError, match="site-packages|runtime node changed"):
        measure_separation_runtime(fixture["worker_request"], **_kwargs(fixture))
    assert changed


def test_pinned_tree_rejects_file_replacement_during_descriptor_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    target = fixture["inputs"]["init"]
    target_inode = target.lstat().st_ino
    original_read = measurement_module.os.read
    changed = False

    def replacing_read(descriptor: int, size: int) -> bytes:
        nonlocal changed
        chunk = original_read(descriptor, size)
        if chunk and os.fstat(descriptor).st_ino == target_inode and not changed:
            changed = True
            replacement = target.with_name("same-content-new-inode.py")
            replacement.write_bytes(target.read_bytes())
            os.replace(replacement, target)
        return chunk

    monkeypatch.setattr(measurement_module.os, "read", replacing_read)
    with pytest.raises(ValueError, match="changed during descriptor hashing"):
        measure_separation_runtime(fixture["worker_request"], **_kwargs(fixture))
    assert changed


def test_directory_scan_enforces_bound_before_materialising_all_entries(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "bounded"
    directory.mkdir()
    (directory / "one.py").write_bytes(b"1")
    (directory / "two.py").write_bytes(b"2")

    descriptor = os.open(
        directory,
        os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY,
    )
    try:
        with pytest.raises(ValueError, match="bounded node count"):
            measurement_module._scan_site_directory_entries(  # noqa: SLF001
                descriptor,
                maximum_entries=1,
            )
    finally:
        os.close(descriptor)


@pytest.mark.parametrize(
    ("constant", "value", "message"),
    [
        (
            "MAX_SITE_PACKAGE_DIRECTORIES",
            1,
            "too many directories",
        ),
        ("MAX_SITE_PACKAGE_FILES", 1, "too many files"),
        (
            "MAX_SITE_PACKAGE_FILE_BYTES",
            1,
            "file exceed",
        ),
        (
            "MAX_SITE_PACKAGE_TOTAL_BYTES",
            1,
            "total size bound",
        ),
    ],
)
def test_site_tree_declared_resource_caps_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    constant: str,
    value: int,
    message: str,
) -> None:
    fixture = _fixture(tmp_path / constant)
    monkeypatch.setattr(measurement_module, constant, value)

    with pytest.raises(ValueError, match=message):
        measure_separation_runtime(fixture["worker_request"], **_kwargs(fixture))


@pytest.mark.parametrize(
    "value",
    [
        Path("/private/tmp/bad\0path"),
        Path("/private/tmp/\udcff"),
        Path("/private/tmp") / ("x" * 4096),
        Path("/private") / Path(*(["deep"] * 65)),
    ],
)
def test_rejects_non_utf8_nul_overlong_and_overdeep_runtime_paths(
    value: Path,
) -> None:
    with pytest.raises(ValueError, match="runtime path"):
        measurement_module._canonical_path(value)  # noqa: SLF001


@pytest.mark.parametrize("value", ["bad\0name", "e\u0301.py", "../escape"])
def test_rejects_unsafe_tree_names(value: str) -> None:
    with pytest.raises(ValueError, match="unsafe name"):
        measurement_module._checked_tree_name(value)  # noqa: SLF001


def test_rejects_launcher_loop_max_chain_and_upward_target(
    tmp_path: Path,
) -> None:
    loop_fixture = _fixture(tmp_path / "loop")
    launcher = loop_fixture["inputs"]["launcher"]
    loop_link = launcher.with_name("python-loop")
    launcher.unlink()
    launcher.symlink_to(loop_link.name)
    loop_link.symlink_to(launcher.name)
    with pytest.raises(ValueError, match="loop or path alias"):
        measure_separation_runtime(
            loop_fixture["worker_request"], **_kwargs(loop_fixture)
        )

    max_fixture = _fixture(tmp_path / "maximum")
    launcher = max_fixture["inputs"]["launcher"]
    final_target = Path(os.readlink(launcher))
    launcher.unlink()
    links = [launcher, *(launcher.with_name(f"python-link-{i}") for i in range(1, 8))]
    for current, following in zip(links, links[1:]):
        current.symlink_to(following.name)
    links[-1].symlink_to(final_target)
    with pytest.raises(ValueError, match="exceeds eight"):
        measure_separation_runtime(
            max_fixture["worker_request"], **_kwargs(max_fixture)
        )

    escape_fixture = _fixture(tmp_path / "escape")
    launcher = escape_fixture["inputs"]["launcher"]
    launcher.unlink()
    launcher.symlink_to("../../outside/python")
    with pytest.raises(ValueError, match="upward escape"):
        measure_separation_runtime(
            escape_fixture["worker_request"], **_kwargs(escape_fixture)
        )

    dot_fixture = _fixture(tmp_path / "dot-alias")
    launcher = dot_fixture["inputs"]["launcher"]
    launcher.unlink()
    launcher.symlink_to("subdir/./python")
    with pytest.raises(ValueError, match="upward escape"):
        measure_separation_runtime(
            dot_fixture["worker_request"],
            **_kwargs(dot_fixture),
        )


def test_every_descriptor_open_is_read_only_nonblocking_and_nofollow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    original_open = measurement_module.os.open
    observed: list[tuple[str, int, int | None]] = []

    def recording_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        observed.append((os.fspath(path), flags, dir_fd))
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(measurement_module.os, "open", recording_open)
    measure_separation_runtime(fixture["worker_request"], **_kwargs(fixture))

    assert observed
    for _path, flags, _dir_fd in observed:
        assert flags & os.O_ACCMODE == os.O_RDONLY
        assert flags & os.O_NONBLOCK
        assert flags & os.O_CLOEXEC
        assert flags & os.O_NOFOLLOW
    assert any(path == "." and dir_fd is not None for path, _flags, dir_fd in observed)
    assert any(
        path == "synthetic_package" and dir_fd is not None
        for path, _flags, dir_fd in observed
    )
    assert any(
        path == "__init__.py" and dir_fd is not None
        for path, _flags, dir_fd in observed
    )


def test_runtime_measurement_ast_forbids_execution_network_audio_and_writes() -> None:
    tree = ast.parse(inspect.getsource(measurement_module))
    forbidden_imports = {
        "asyncio",
        "demucs",
        "http",
        "importlib",
        "librosa",
        "multiprocessing",
        "requests",
        "socket",
        "soundfile",
        "subprocess",
        "torch",
        "torchaudio",
        "urllib",
    }
    forbidden_names = {
        "__import__",
        "compile",
        "eval",
        "exec",
        "open",
    }
    forbidden_attributes = {
        "chmod",
        "chown",
        "connect",
        "execv",
        "execve",
        "fork",
        "link",
        "makedirs",
        "mkfifo",
        "mknod",
        "mkdir",
        "remove",
        "rename",
        "replace",
        "rmdir",
        "send",
        "spawnl",
        "spawnv",
        "symlink",
        "system",
        "truncate",
        "unlink",
        "utime",
        "write",
        "write_bytes",
        "write_text",
    }
    forbidden_open_flags = {
        "O_APPEND",
        "O_CREAT",
        "O_EXCL",
        "O_RDWR",
        "O_TRUNC",
        "O_WRONLY",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(
                alias.name.split(".", 1)[0] not in forbidden_imports
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".", 1)[0] not in forbidden_imports
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_names
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_attributes
        elif isinstance(node, ast.Attribute):
            assert node.attr not in forbidden_open_flags
