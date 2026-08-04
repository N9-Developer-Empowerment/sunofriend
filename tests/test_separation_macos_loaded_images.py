from __future__ import annotations

import ctypes
import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

import sunofriend._separation_macos_loaded_images as loaded_images
import sunofriend._separation_macos_process_image as process_image
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS
from sunofriend.separation_contract import _canonical_json_bytes


def test_validates_path_free_bounded_inventory() -> None:
    evidence = loaded_images._validate_private_macos_native_image_inventory(
        _evidence()
    )

    assert evidence["status"] == (
        "stable_file_backed_executable_region_inventory_observed"
    )
    assert evidence["inventory"]["mapped_file_count"] == 2
    assert evidence["conclusion"]["bound_to_model_worker"] is False
    assert all(value is False for value in evidence["permissions"].values())
    assert "/Users/" not in repr(evidence)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: value["permissions"].__setitem__(
                "model_import_permitted", True
            ),
            "permissions",
        ),
        (
            lambda value: value["conclusion"].__setitem__(
                "bound_to_model_worker", True
            ),
            "conclusion",
        ),
        (
            lambda value: value["limitations"].__setitem__(
                "dynamic_native_library_closure_bound", True
            ),
            "limitations",
        ),
        (
            lambda value: value["inventory"].__setitem__("snapshot_count", 1),
            "counts",
        ),
        (
            lambda value: value["inventory"]["artifacts"][0].__setitem__(
                "static_cdhash", None
            ),
            "signature",
        ),
    ],
)
def test_rejects_resigned_semantic_overclaims(mutate: object, message: str) -> None:
    value = _evidence()
    mutate(value)  # type: ignore[operator]
    _resign(value)

    with pytest.raises(ValueError, match=message):
        loaded_images._validate_private_macos_native_image_inventory(value)


def test_rejects_a_tampered_nested_process_binding() -> None:
    value = _evidence()
    value["process_image_binding"]["runtime"]["process_image"][
        "observed_kernel_cdhash"
    ] = "d" * 40
    _resign(value)

    with pytest.raises(ValueError, match="binding self-hash"):
        loaded_images._validate_private_macos_native_image_inventory(value)


def test_sdk_structure_layout_matches_the_supported_libproc_contract() -> None:
    assert ctypes.sizeof(loaded_images._ProcRegionInfo) == 96
    assert ctypes.sizeof(loaded_images._ProcRegionWithPathInfo) == 1272
    assert (
        loaded_images._ProcRegionWithPathInfo.prp_vip.offset
        + loaded_images._VnodeInfoPath.vip_path.offset
        == 248
    )


def test_enumerator_keeps_only_executable_regions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "image"
    data = tmp_path / "data"
    image.write_bytes(b"image")
    data.write_bytes(b"data")
    calls = [
        (0x1000, 0x1000, 5, image),
        (0x3000, 0x1000, 3, data),
        (0x5000, 0x2000, 5, None),
    ]
    function = _FakeProcPidInfo(calls)
    monkeypatch.setattr(loaded_images.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        loaded_images.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: SimpleNamespace(proc_pidinfo=function),
    )

    regions = loaded_images._enumerate_executable_regions(123)

    assert [(region.path, region.size) for region in regions] == [
        (image, 0x1000),
        (None, 0x2000),
    ]


def test_owner_bound_enumerator_uses_opaque_owner_without_pid(
    tmp_path: Path,
) -> None:
    image = tmp_path / "image"
    image.write_bytes(b"image")
    owner = _OpaqueRegionOwner(
        (
            (os.fsencode(image), 0x1000, 0x1000, 0, 5),
            (None, 0x5000, 0x2000, 0, 5),
        )
    )

    regions = loaded_images._enumerate_owned_executable_regions(owner)

    assert owner.calls == 1
    assert [(region.path, region.size) for region in regions] == [
        (image, 0x1000),
        (None, 0x2000),
    ]


def test_owner_bound_enumerator_rejects_transferable_or_invalid_owner(
    tmp_path: Path,
) -> None:
    image = tmp_path / "image"
    image.write_bytes(b"image")
    transferable = SimpleNamespace(
        start_state="started_owned",
        ownership_released=False,
        ownership_lost=False,
        snapshot_owned_executable_regions=lambda: (),
    )

    with pytest.raises(TypeError, match="live opaque owner"):
        loaded_images._enumerate_owned_executable_regions(transferable)
    with pytest.raises(RuntimeError, match="geometry differs"):
        loaded_images._enumerate_owned_executable_regions(
            _OpaqueRegionOwner(((os.fsencode(image), 0x1000, 0, 0, 5),))
        )


def test_mapped_file_measurement_records_signature_status_without_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "Python"
    dependency = tmp_path / "native.so"
    for path in (image, dependency):
        path.write_bytes(path.name.encode())
    regions = (
        loaded_images._ExecutableRegion(image, 1, 10, 0, 5),
        loaded_images._ExecutableRegion(dependency, 20, 30, 0, 5),
        loaded_images._ExecutableRegion(dependency, 50, 40, 4096, 5),
    )
    monkeypatch.setattr(
        loaded_images,
        "_regular_file_identity",
        lambda path: _identity(Path(path)),
    )

    def signature(path: Path) -> dict[str, str]:
        if path == dependency:
            raise RuntimeError("not signed")
        return {"cdhash": "c" * 40}

    monkeypatch.setattr(loaded_images, "_static_code_identity", signature)

    measured = loaded_images._measure_mapped_files(
        regions,
        process_image_path=image,
    )
    artifacts = loaded_images._path_free_artifacts(measured)

    assert artifacts[0]["matches_process_image"] is True
    assert artifacts[1]["executable_region_count"] == 2
    assert artifacts[1]["executable_region_bytes"] == 70
    assert artifacts[1]["static_code_status"] == "not_strictly_valid"
    assert str(tmp_path) not in repr(artifacts)


def test_mapped_file_identity_accepts_regular_library_without_mode_x(
    tmp_path: Path,
) -> None:
    library = tmp_path / "native-extension.so"
    library.write_bytes(b"mapped-native-extension")
    library.chmod(0o600)

    identity = loaded_images._regular_file_identity(library)

    assert identity == {
        "resolved_path": str(library.resolve()),
        "bytes": len(b"mapped-native-extension"),
        "sha256": hashlib.sha256(b"mapped-native-extension").hexdigest(),
    }


class _OpaqueRegionOwner:
    __slots__ = (
        "_snapshot",
        "calls",
        "start_state",
        "ownership_released",
        "ownership_lost",
    )

    def __init__(self, snapshot: tuple[tuple[object, ...], ...]) -> None:
        self._snapshot = snapshot
        self.calls = 0
        self.start_state = "started_owned"
        self.ownership_released = False
        self.ownership_lost = False

    def snapshot_owned_executable_regions(self) -> tuple[tuple[object, ...], ...]:
        self.calls += 1
        return self._snapshot


def test_remeasurement_rejects_changed_mapped_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "image"
    image.write_bytes(b"image")
    before = _identity(image)
    after = {**before, "sha256": "f" * 64}
    monkeypatch.setattr(loaded_images, "_regular_file_identity", lambda _: after)

    with pytest.raises(RuntimeError, match="changed after child"):
        loaded_images._remeasure_mapped_files(
            ({"path": image, "identity": before},)
        )


def test_model_free_runner_seals_inventory_and_zero_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = tmp_path / "sandbox-exec"
    launcher = tmp_path / "python"
    image = tmp_path / "Python"
    dependency = tmp_path / "native.so"
    for path in (provider, launcher, image, dependency):
        path.write_bytes(path.name.encode())
    prepared = SimpleNamespace(
        provider_path=provider,
        runtime_launcher_path=launcher,
        process_image_path=image,
    )
    regions = (
        loaded_images._ExecutableRegion(image, 1, 10, 0, 5),
        loaded_images._ExecutableRegion(dependency, 20, 30, 0, 5),
    )
    measured = (
        {
            "path": image,
            "identity": _identity(image),
            "executable_region_count": 1,
            "executable_region_bytes": 10,
            "signature_status": "strictly_valid",
            "static_cdhash": "c" * 40,
            "matches_process_image": True,
        },
        {
            "path": dependency,
            "identity": _identity(dependency),
            "executable_region_count": 1,
            "executable_region_bytes": 30,
            "signature_status": "not_strictly_valid",
            "static_cdhash": None,
            "matches_process_image": False,
        },
    )
    monkeypatch.setattr(loaded_images.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(
        loaded_images,
        "_prepare_runtime_process_image_binding",
        lambda **_kwargs: prepared,
    )
    monkeypatch.setattr(
        loaded_images,
        "_observe_prepared_runtime_process_image",
        lambda *_args, **_kwargs: {"kernel_cdhash": "c" * 40},
    )
    monkeypatch.setattr(
        loaded_images,
        "_complete_runtime_process_image_binding",
        lambda **_kwargs: _binding(),
    )
    monkeypatch.setattr(
        loaded_images,
        "_read_child_ready",
        lambda _process: {
            "native_modules": list(loaded_images._NATIVE_MODULES),
            "probe_id": loaded_images.PROBE_ID,
        },
    )
    monkeypatch.setattr(
        loaded_images, "_enumerate_executable_regions", lambda _pid: regions
    )
    monkeypatch.setattr(
        loaded_images, "_measure_mapped_files", lambda *_args, **_kwargs: measured
    )
    monkeypatch.setattr(loaded_images, "_remeasure_mapped_files", lambda _: None)
    monkeypatch.setattr(loaded_images.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        loaded_images.subprocess,
        "Popen",
        lambda *args, **kwargs: _FakeProcess(args, kwargs),
    )

    evidence = loaded_images._run_private_macos_native_image_inventory_canary(
        runtime_path=launcher
    )

    assert evidence["inventory"]["mapped_file_count"] == 2
    assert evidence["inventory"]["artifacts_unchanged_after_child"] is True
    assert evidence["limitations"]["dynamic_native_library_closure_bound"] is False
    assert evidence["conclusion"]["bound_to_model_worker"] is False
    assert all(value is False for value in evidence["permissions"].values())


def test_private_runner_writes_owner_only_and_never_replaces(
    tmp_path: Path,
) -> None:
    script = (
        Path(__file__).parents[1]
        / "scripts"
        / "private-macos-native-image-inventory.py"
    )
    specification = importlib.util.spec_from_file_location(
        "private_macos_native_image_inventory_script", script
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    destination = tmp_path / "observation.json"

    module._write_private_observation(destination, '{"status":"fixture"}\n')

    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "status": "fixture"
    }
    with pytest.raises(FileExistsError):
        module._write_private_observation(destination, "{}\n")


def test_native_image_inventory_has_no_public_route() -> None:
    assert "private-macos-native-image-inventory" not in PUBLIC_COMMANDS
    assert "private-macos-native-image-inventory" not in DIRECT_TUI_COMMANDS
    assert loaded_images.__all__ == ()


class _FakeProcPidInfo:
    def __init__(self, rows: list[tuple[int, int, int, Path | None]]) -> None:
        self.rows = iter(rows)
        self.argtypes: object = None
        self.restype: object = None

    def __call__(
        self,
        pid: int,
        flavor: int,
        address: int,
        buffer: object,
        size: int,
    ) -> int:
        assert pid == 123
        assert flavor == loaded_images._PROC_PIDREGIONPATHINFO
        assert size == ctypes.sizeof(loaded_images._ProcRegionWithPathInfo)
        try:
            region_address, region_size, protection, path = next(self.rows)
        except StopIteration:
            ctypes.set_errno(22)
            return 0
        assert region_address >= address
        output = ctypes.cast(
            buffer,
            ctypes.POINTER(loaded_images._ProcRegionWithPathInfo),
        ).contents
        output.prp_prinfo.pri_address = region_address
        output.prp_prinfo.pri_size = region_size
        output.prp_prinfo.pri_protection = protection
        if path is not None:
            output.prp_vip.vip_path = os.fsencode(path)
        return size


class _FakeProcess:
    def __init__(self, args: object, kwargs: object) -> None:
        self.args = args
        self.kwargs = kwargs
        self.pid = 123
        self.returncode = 0

    def communicate(self, timeout: float) -> tuple[bytes, bytes]:
        assert timeout == 3.0
        return b"", b""

    def poll(self) -> int:
        return 0

    def kill(self) -> None:
        raise AssertionError("completed fake child must not be killed")

    def wait(self, timeout: float) -> int:
        assert timeout == 3.0
        return 0


def _identity(path: Path) -> dict[str, object]:
    data = path.name.encode()
    return {
        "resolved_path": str(path.absolute()),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _binding() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": process_image.BINDING_SCHEMA,
        "policy_id": process_image.BINDING_POLICY_ID,
        "status": "runtime_process_image_bound_to_exact_child_pid",
        "platform": {"system": "Darwin", "machine": "arm64"},
        "provider": {
            "bytes": 100,
            "sha256": "a" * 64,
            "static_cdhash": "a" * 40,
            "strict_code_signature_valid": True,
            "static_code_validation": process_image._STRICT_VALIDATION,
            "filesystem_read_only": True,
        },
        "runtime": {
            "launcher": {
                "bytes": 101,
                "sha256": "b" * 64,
                "static_cdhash": "b" * 40,
                "strict_code_signature_valid": True,
            },
            "process_image": {
                "bytes": 102,
                "sha256": "c" * 64,
                "static_cdhash": "c" * 40,
                "observed_kernel_cdhash": "c" * 40,
                "strict_code_signature_valid": True,
                "static_and_kernel_cdhash_match": True,
            },
            "transition": "python-org-framework-launcher-to-app-image",
        },
        "observation": {
            "exact_child_pid_observed": True,
            "child_pid_retained": False,
            "parent_proc_pidpath_used": True,
            "parent_csops_cdhash_used": True,
            "process_image_path_matched_expected": True,
            "artifacts_unchanged_after_child": True,
        },
        "conclusion": {
            "provider_path_mutation_confined_by_read_only_filesystem": True,
            "runtime_process_code_identity_bound_to_exact_child_pid": True,
            "runtime_launcher_transition_explicit": True,
        },
        "limitations": {
            "provider_runtime_complete_byte_identity_toctou_closed": False,
            "dynamic_native_library_closure_bound": False,
            "post_observation_image_mutability_excluded": False,
            "code_signature_identity_is_not_full_file_sha256": True,
        },
    }
    payload["evidence_sha256"] = hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest()
    return payload


def _evidence() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": loaded_images.SCHEMA,
        "policy_id": loaded_images.POLICY_ID,
        "status": "stable_file_backed_executable_region_inventory_observed",
        "platform": {"system": "Darwin", "machine": "arm64"},
        "process_image_binding": _binding(),
        "probe": {
            "probe_id": loaded_images.PROBE_ID,
            "native_module_count": len(loaded_images._NATIVE_MODULES),
            "ready_received_before_inventory": True,
            "child_reported_inventory": False,
        },
        "inventory": {
            "source": "libproc-proc-pidregionpathinfo",
            "snapshot_count": 2,
            "stable_consecutive_snapshots": True,
            "executable_region_count": 2,
            "file_backed_executable_region_count": 2,
            "unpathed_executable_region_count": 0,
            "mapped_file_count": 2,
            "artifacts": [
                {
                    "artifact_index": 1,
                    "bytes": 100,
                    "sha256": "c" * 64,
                    "executable_region_count": 1,
                    "executable_region_bytes": 4096,
                    "static_code_status": "strictly_valid",
                    "static_cdhash": "c" * 40,
                    "matches_process_image": True,
                },
                {
                    "artifact_index": 2,
                    "bytes": 101,
                    "sha256": "d" * 64,
                    "executable_region_count": 1,
                    "executable_region_bytes": 8192,
                    "static_code_status": "not_strictly_valid",
                    "static_cdhash": None,
                    "matches_process_image": False,
                },
            ],
            "artifacts_unchanged_after_child": True,
            "paths_retained": False,
        },
        "conclusion": {
            "exact_child_pid_observed": True,
            "parent_owned_inventory": True,
            "stable_file_backed_executable_regions_bound": True,
            "main_process_image_present_once": True,
            "bound_to_model_worker": False,
            "separator_enabled": False,
        },
        "permissions": {
            "model_import_permitted": False,
            "checkpoint_access_permitted": False,
            "authorised_audio_access_permitted": False,
            "separator_execution_permitted": False,
            "source_graph_activation_permitted": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "effects": {
            "process_started": True,
            "filesystem_written": False,
            "network_used": False,
            "checkpoint_opened": False,
            "model_imported": False,
            "audio_read": False,
            "source_graph_changed": False,
        },
        "limitations": {
            "model_free_canary_only": True,
            "authorised_worker_not_bound": True,
            "dyld_shared_cache_constituents_enumerated": False,
            "transient_loads_between_snapshots_excluded": False,
            "mapped_memory_bytes_equal_reopened_file_bytes_proven": False,
            "dynamic_native_library_closure_bound": False,
            "post_observation_image_mutability_excluded": False,
        },
    }
    payload["evidence_sha256"] = hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest()
    return payload


def _resign(value: dict[str, object]) -> None:
    value.pop("evidence_sha256", None)
    value["evidence_sha256"] = hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest()
