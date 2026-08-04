from __future__ import annotations

import hashlib
import json
import platform
import stat
import wave
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from sunofriend import (
    _separation_melroformer_native_attempt_darwin as attempt_module,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _fixture(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    repository = root / "repository"
    repository.mkdir()
    worker = repository / "scripts/private-melroformer-native-worker.py"
    worker.parent.mkdir()
    worker.write_text("worker", encoding="utf-8")
    runtime = root / "runtime"
    runtime.write_text("runtime", encoding="utf-8")
    runtime.chmod(0o700)
    source = root / "source"
    source.mkdir()
    checkpoint = root / "checkpoint.safetensors"
    checkpoint.write_bytes(b"checkpoint")
    checkpoint.chmod(0o600)
    companions = root / "companions"
    companions.mkdir()
    report = root / "authorisation.json"
    report.write_text("{}", encoding="utf-8")
    report.chmod(0o600)
    return {
        "root": root,
        "repository": repository,
        "runtime": runtime,
        "source": source,
        "checkpoint": checkpoint,
        "companions": companions,
        "report": report,
        "report_sha256": _digest("authorisation"),
        "attempt": root / "attempt",
    }


def _install_measurement_substitutions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        attempt_module,
        "_verify_private_melroformer_source_tree",
        lambda _path: {"verified": True},
    )
    monkeypatch.setattr(
        attempt_module,
        "_read_exact_regular_file",
        lambda *_args, **_kwargs: b"{}",
    )
    monkeypatch.setattr(
        attempt_module,
        "_inspect_companion_files",
        lambda _path: {"companions": True},
    )
    monkeypatch.setattr(
        attempt_module,
        "_companion_manifest_identity",
        lambda _value: {"manifest_sha256": _digest("companions")},
    )
    monkeypatch.setattr(
        attempt_module,
        "_regular_file_identity",
        lambda *_args, **_kwargs: {
            "bytes": 6,
            "sha256": _digest("worker"),
        },
    )


def test_private_native_attempt_composes_exact_authorities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    _install_measurement_substitutions(monkeypatch)
    session = object()
    session_observation = object()
    lease = object()
    lease_observation = object()
    reservation = object()
    receipt_holder: list[MappingProxyType[str, Any]] = []
    calls: list[str] = []

    monkeypatch.setattr(
        attempt_module._session,
        "_open_verified_private_melroformer_native_session",
        lambda **kwargs: calls.append("session")
        or (session, session_observation),
    )
    monkeypatch.setattr(
        attempt_module._lease,
        "_acquire_private_melroformer_checkpoint_lease",
        lambda request: calls.append("lease") or (lease, lease_observation),
    )
    monkeypatch.setattr(
        attempt_module._lease,
        "_reserve_private_melroformer_checkpoint_fd5",
        lambda trusted, **kwargs: calls.append("reserve") or reservation,
    )

    def run_one_shot(trusted: Any, **kwargs: Any):
        assert trusted is lease
        assert kwargs["trusted_reservation"] is reservation
        assert kwargs["current_lease_observation"] is lease_observation
        assert kwargs["trusted_native_session"] is session
        assert kwargs["native_session_observation"] is session_observation
        request = kwargs["request"]
        assert request["identities"]["worker_source_sha256"] == _digest(
            "worker"
        )
        assert request["identities"]["companion_manifest_sha256"] == _digest(
            "companions"
        )
        assert kwargs["transport_directory"] == fixture["attempt"] / "transport"
        stems = fixture["attempt"] / "staging/quarantine/STEMS"
        stems.mkdir(parents=True, mode=0o700)
        stems.parent.chmod(0o700)
        stems.chmod(0o700)
        for role in ("vocals", "instrumental"):
            _write_pcm24(stems / f"{role}.wav")
        payload = {
            "schema": "sunofriend.private-melroformer-native-coordinator.v1",
            "status": "private_native_worker_complete_and_terminal",
            "request_sha256": request["request_sha256"],
            "lifecycle": {"terminal": True},
            "permissions": {"accepted": False},
        }
        receipt = MappingProxyType(
            {
                **payload,
                "receipt_sha256": hashlib.sha256(
                    attempt_module._canonical_json(payload)
                ).hexdigest(),
            }
        )
        receipt_holder.append(receipt)
        calls.append("one_shot")
        return receipt

    monkeypatch.setattr(
        attempt_module,
        "_run_reserved_private_melroformer_native_one_shot_darwin",
        run_one_shot,
    )

    result = _run(fixture)
    assert result is receipt_holder[0]
    assert calls == ["session", "lease", "reserve", "one_shot"]
    assert stat.S_IMODE(fixture["attempt"].stat().st_mode) == 0o700
    assert stat.S_IMODE(
        (fixture["attempt"] / "staging").stat().st_mode
    ) == 0o700
    receipt_path = fixture["attempt"] / "native-attempt-receipt.json"
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    assert json.loads(receipt_path.read_bytes()) == dict(receipt_holder[0])
    evidence_path = fixture["attempt"] / "native-attempt-evidence.json"
    evidence = json.loads(evidence_path.read_bytes())
    assert evidence["status"] == "private_native_attempt_verified_not_selected"
    assert [item["role"] for item in evidence["outputs"]] == [
        "instrumental",
        "vocals",
    ]
    assert all(value is False for value in evidence["permissions"].values())
    timing_path = fixture["attempt"] / "native-attempt-timing.json"
    timing = json.loads(timing_path.read_bytes())
    assert timing["status"] == "private_runtime_observation_not_benchmark"
    assert timing["stage_order"] == list(attempt_module._TIMING_STAGES)
    assert set(timing["stage_seconds"]) == set(attempt_module._TIMING_STAGES)
    assert timing["clock"] == {
        "source": "time.monotonic",
        "timestamps_recorded": False,
        "wall_clock_recorded": False,
    }
    assert timing["bindings"]["terminal_receipt_sha256"] == receipt_holder[0][
        "receipt_sha256"
    ]
    assert all(value is False for value in timing["permissions"].values())
    assert stat.S_IMODE(timing_path.stat().st_mode) == 0o600


def test_private_native_attempt_releases_pre_coordinator_authority_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    _install_measurement_substitutions(monkeypatch)
    lease = object()
    observation = object()
    reservation = object()
    primary = RuntimeError("substituted one-shot failure")
    calls: list[str] = []

    monkeypatch.setattr(
        attempt_module._session,
        "_open_verified_private_melroformer_native_session",
        lambda **_kwargs: (object(), object()),
    )
    monkeypatch.setattr(
        attempt_module._lease,
        "_acquire_private_melroformer_checkpoint_lease",
        lambda _request: (lease, observation),
    )
    monkeypatch.setattr(
        attempt_module._lease,
        "_reserve_private_melroformer_checkpoint_fd5",
        lambda *_args, **_kwargs: reservation,
    )
    monkeypatch.setattr(
        attempt_module,
        "_run_reserved_private_melroformer_native_one_shot_darwin",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(primary),
    )
    monkeypatch.setattr(
        attempt_module,
        "_terminalize_checkpoint_authority",
        lambda trusted, reserved: calls.append(
            "terminalize"
            if trusted is lease and reserved is reservation
            else "wrong_authority"
        ),
    )

    with pytest.raises(
        attempt_module._PrivateMelroformerNativeAttemptFailure
    ) as caught:
        _run(fixture)
    assert caught.value.primary_error is primary
    assert caught.value.cleanup_stages == ()
    assert caught.value.cleanup_errors == ()
    assert calls == ["terminalize"]
    assert not (fixture["attempt"] / "native-attempt-timing.json").exists()


@pytest.mark.parametrize("value", [True, -0.1, float("nan"), 3_600.1])
def test_private_native_attempt_rejects_invalid_timing_values(value: object) -> None:
    with pytest.raises(ValueError, match="timing value differs"):
        attempt_module._checked_timing_value(value)


def test_private_native_attempt_accepts_bounded_equal_length_outputs(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "attempt"
    stems = attempt / "staging/quarantine/STEMS"
    stems.mkdir(parents=True)
    for directory in (attempt, attempt / "staging", stems.parent, stems):
        directory.chmod(0o700)
    _write_pcm24(stems / "instrumental.wav", frames=12_345)
    _write_pcm24(stems / "vocals.wav", frames=12_345)

    instrumental = attempt_module._inspect_attempt_pcm24(
        attempt,
        role="instrumental",
    )
    vocals = attempt_module._inspect_attempt_pcm24(
        attempt,
        role="vocals",
        expected_frames=instrumental["geometry"]["frames"],
    )

    assert instrumental["geometry"]["frames"] == 12_345
    assert vocals["geometry"]["frames"] == 12_345


def test_private_native_attempt_requires_fresh_path_before_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    fixture["attempt"].mkdir(mode=0o700)
    _install_measurement_substitutions(monkeypatch)

    with pytest.raises(ValueError, match="must not exist"):
        _run(fixture)


def test_private_native_attempt_has_no_product_route() -> None:
    assert attempt_module.__all__ == ()
    assert not any("melroformer" in command for command in PUBLIC_COMMANDS)
    assert not any("melroformer" in command for command in DIRECT_TUI_COMMANDS)


@pytest.mark.trusted_local
@pytest.mark.skipif(platform.system() != "Darwin", reason="Darwin-only attempt")
def test_real_private_assets_compose_to_the_one_shot_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    private_root = Path(
        "/Users/errolelliott/.local/share/sunofriend/private-evaluation/"
        "kim-vocal-2-mlx-v1"
    )
    report = (
        repository
        / "work/separation-bakeoff/be-alone-authorised-191-206-v2/"
        "authorised-separation-excerpt.json"
    )
    required = (
        repository / ".venv-ai/bin/python",
        private_root / "mlx-audio-source",
        private_root / "model.safetensors",
        private_root / "checkpoint-directory",
        report,
    )
    if not all(path.exists() for path in required):
        pytest.skip("approved private Kim assets are incomplete")
    receipt = {"receipt_sha256": _digest("real-static-attempt")}

    def static_one_shot(trusted: Any, **kwargs: Any):
        attempt_module._lease._release_private_melroformer_checkpoint_fd5(
            trusted,
            kwargs["trusted_reservation"],
        )
        attempt_module._lease._close_private_melroformer_checkpoint_lease(
            trusted
        )
        return receipt

    monkeypatch.setattr(
        attempt_module,
        "_run_reserved_private_melroformer_native_one_shot_darwin",
        static_one_shot,
    )
    monkeypatch.setattr(
        attempt_module,
        "_write_attempt_evidence",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        attempt_module,
        "_write_attempt_timing",
        lambda *_args, **_kwargs: None,
    )

    assert attempt_module._run_private_melroformer_native_attempt_darwin(
        run_nonce=_digest(f"real-static-attempt:{tmp_path}"),
        repository_root=repository,
        runtime_launcher_path=repository / ".venv-ai/bin/python",
        source_root=private_root / "mlx-audio-source",
        checkpoint_path=private_root / "model.safetensors",
        companion_root=private_root / "checkpoint-directory",
        authorisation_report_path=report,
        authorisation_report_sha256=(
            "00685db1ba4d5ac0927c25a5ef40792ab"
            "36c56cdb36dcc20cc5f926fb9774e90"
        ),
        attempt_directory=tmp_path / "real-static-attempt",
        device="cpu",
    ) == receipt


def _run(fixture: dict[str, Any]):
    return attempt_module._run_private_melroformer_native_attempt_darwin(
        run_nonce=_digest(f"attempt:{fixture['attempt']}"),
        repository_root=fixture["repository"],
        runtime_launcher_path=fixture["runtime"],
        source_root=fixture["source"],
        checkpoint_path=fixture["checkpoint"],
        companion_root=fixture["companions"],
        authorisation_report_path=fixture["report"],
        authorisation_report_sha256=fixture["report_sha256"],
        attempt_directory=fixture["attempt"],
        device="cpu",
    )


def _write_pcm24(path: Path, *, frames: int = 661_500) -> None:
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(3)
        writer.setframerate(44_100)
        writer.writeframes(b"\0" * frames * 2 * 3)
    path.chmod(0o600)
