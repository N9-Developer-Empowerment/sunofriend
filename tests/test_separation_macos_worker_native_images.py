from __future__ import annotations

import hashlib
from pathlib import Path
import pytest

import sunofriend._separation_macos_worker_native_images as native_images
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS
from sunofriend.separation_contract import _canonical_json_bytes


def test_observation_waits_for_ready_then_takes_stable_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = object()
    process_image = tmp_path / "Python"
    dependency = tmp_path / "libmlx.dylib"
    for path in (process_image, dependency):
        path.write_bytes(path.name.encode())
    regions = (
        _region(process_image, address=1),
        _region(dependency, address=20),
    )
    measured = (
        _measured(process_image, matches=True),
        _measured(dependency, matches=False),
    )
    order: list[str] = []
    monkeypatch.setattr(
        native_images,
        "_read_worker_ready_handshake",
        lambda *_args, **_kwargs: order.append("ready") or _claim(),
    )
    monkeypatch.setattr(
        native_images,
        "_enumerate_executable_regions",
        lambda _pid: order.append("snapshot") or regions,
    )
    monkeypatch.setattr(native_images.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        native_images,
        "_measure_mapped_files",
        lambda *_args, **_kwargs: order.append("measure") or measured,
    )
    monkeypatch.setattr(
        native_images,
        "_release_worker_ready_handshake",
        lambda _: order.append("release"),
    )

    observed = native_images._observe_macos_worker_native_images(
        prepared,  # type: ignore[arg-type]
        pid=123,
        process_image_path=process_image,
    )

    assert observed.readiness == _claim()
    assert order == ["ready", "snapshot", "snapshot", "measure", "release"]


def test_completion_cross_binds_ready_claim_and_final_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = native_images._ObservedWorkerNativeImages(
        readiness=_claim(),
        regions=(_region(Path("/private/Python"), address=1),),
        measured=(_measured(Path("/private/Python"), matches=True),),
    )
    monkeypatch.setattr(native_images.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(
        native_images,
        "_validate_runtime_process_image_binding",
        lambda value: value,
    )
    monkeypatch.setattr(native_images, "_remeasure_mapped_files", lambda _: None)

    evidence = native_images._complete_macos_worker_native_image_observation(
        observed=observed,
        runtime_process_image=_binding(),
        child=_child(),
    )

    assert evidence["conclusion"]["bound_to_model_worker"] is True
    assert evidence["readiness"]["phase"] == native_images.READY_PHASE
    assert all(value is False for value in evidence["permissions"].values())
    assert "/private/" not in repr(evidence)


def test_completion_rejects_ready_result_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim = _claim()
    claim["source_frames"] = 44_101
    observed = native_images._ObservedWorkerNativeImages(
        readiness=claim,
        regions=(_region(Path("/private/Python"), address=1),),
        measured=(_measured(Path("/private/Python"), matches=True),),
    )
    monkeypatch.setattr(
        native_images,
        "_validate_runtime_process_image_binding",
        lambda value: value,
    )

    with pytest.raises(ValueError, match="readiness and final evidence"):
        native_images._complete_macos_worker_native_image_observation(
            observed=observed,
            runtime_process_image=_binding(),
            child=_child(),
        )


def test_worker_native_image_inventory_has_no_public_route() -> None:
    assert "private-worker-native-image-inventory" not in PUBLIC_COMMANDS
    assert "private-worker-native-image-inventory" not in DIRECT_TUI_COMMANDS
    assert native_images.__all__ == ()


def _claim() -> dict[str, object]:
    return {
        "schema": native_images.READY_SCHEMA,
        "phase": native_images.READY_PHASE,
        "candidate_id": "mlx-melroformer-kim-vocal-2",
        "checkpoint_sha256": "a" * 64,
        "authorised_audio_sha256": "b" * 64,
        "source_frames": 44_100,
        "vocal_float32_sha256": "c" * 64,
        "instrumental_float32_sha256": "d" * 64,
        "release_protocol": native_images.RELEASE_PROTOCOL,
    }


def _child() -> dict[str, object]:
    return {
        "model": {
            "authorisation": {"audio_sha256": "b" * 64},
            "bridge": {
                "candidate_id": "mlx-melroformer-kim-vocal-2",
                "checkpoint": {"sha256": "a" * 64},
            },
            "inference": {
                "geometry": {"frames": 44_100},
                "outputs": {
                    "vocals": {"sha256": "c" * 64},
                    "instrumental": {"sha256": "d" * 64},
                },
            },
        }
    }


def _region(path: Path, *, address: int) -> object:
    from sunofriend._separation_macos_loaded_images import _ExecutableRegion

    return _ExecutableRegion(path, address, 4_096, 0, 5)


def _measured(path: Path, *, matches: bool) -> dict[str, object]:
    return {
        "path": path,
        "identity": {
            "resolved_path": str(path),
            "bytes": 100,
            "sha256": "c" * 64 if matches else "d" * 64,
        },
        "executable_region_count": 1,
        "executable_region_bytes": 4_096,
        "signature_status": "strictly_valid" if matches else "not_strictly_valid",
        "static_cdhash": "c" * 40 if matches else None,
        "matches_process_image": matches,
    }


def _binding() -> dict[str, object]:
    payload: dict[str, object] = {
        "platform": {"machine": "arm64"},
        "status": "fixture",
    }
    payload["evidence_sha256"] = hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest()
    return payload
